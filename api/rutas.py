"""La logica de los tres endpoints, como funciones puras.

Separadas del transporte a proposito: cada una recibe un dict y devuelve
`(codigo, datos)`. Asi se pueden probar sin levantar un servidor ni tocar
Vercel, que es donde se rompen.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import sys
import urllib.parse
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
for ruta in (AQUI, os.path.dirname(AQUI)):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

from _comun import SinCredenciales, escribir, leer  # noqa: E402

from captura.estados import ESTADOS, normalizar_estado  # noqa: E402
from ingest.instagram.clase_perfil import CLASES_UTILIZABLES  # noqa: E402
from captura.cajas import (  # noqa: E402
    cajas_desde,
    condados_sin_market_insight,
    marcar_del_overview,
    resumen_de_cajas,
)
from captura.pertenencia import comprobar  # noqa: E402
from motor.evaluar import VERSION_REGLAS  # noqa: E402
from motor.fechas import dia_y_mes, fecha_legible  # noqa: E402
from motor.veredicto import puede_contactarse  # noqa: E402
from captura.trampas import es_de_la_casa, share_de_la_casa  # noqa: E402
from captura.parser_mm import (  # noqa: E402
    detectar_inversion,
    parsear_mercado,
    parsear_perfil,
    unir_perfiles,
)
from captura.transacciones import (  # noqa: E402
    NUNCA_SE_GUARDAN,
    crudo_redactado,
    nombre_de_lender,
    parsear_transacciones,
)
from captura.transacciones import resumen as resumen_de_transacciones  # noqa: E402
from captura.protocolo import (  # noqa: E402
    Bloque,
    ProtocoloInvalido,
    condados_del_overview,
    etiquetar_por_posicion,
    separar_volcado,
)

CAMPOS_LISTA = ("id,nombre_completo,brokerage,estado,email_principal,"
                "telefono_e164,unidades_ano,sf_lead_id,sin_llave_dura,"
                "condado_fips")
TOPE = 300

#: Cuantos ids caben en un `id=in.(...)` sin pasarse del largo de URL que
#: PostgREST acepta. Hoy el filtro mas grande devuelve 298.
TOPE_IDS = 400

#: Con que etiqueta entra cada dato de contacto de Model Match.
FUENTE_CONTACTOS = "Model Match"


#: Claves de servicio del perfil: no son dato extraido.
_DE_SERVICIO = ("capturado_en", "fallos", "wallet_share_base")


def _campos_de_perfil(perfil: dict | None) -> int:
    """Cuantos campos con dato trae un perfil parseado.

    Es el denominador de la guarda de secciones sin extraer: texto guardado y
    cero campos es un fallo, y sin contar no se puede decir que hubo cero.
    """
    return sum(1 for k, v in (perfil or {}).items()
               if k not in _DE_SERVICIO
               and v not in (None, "", [], {}, False))


def capturas_que_mandan(realtor_id: str) -> tuple[list, dict]:
    """Las filas de la captura MAS RECIENTE, y cuantas quedaron atras.

    LA REGLA, y por que hace falta
    ------------------------------
    Con dos capturas vivas del mismo realtor el sistema las COMBINABA, y mal:
    `Solano` salia dos veces en los contrastes y `unir_perfiles` tomaba "la
    primera no vacia" de un orden que PostgREST no garantiza. O sea que entre
    dos capturas con cifras distintas ganaba una al azar, y el diagnostico
    cambiaba sin que nadie tocara nada.

    No era ninguna de las dos opciones razonables -- ni la mas reciente manda,
    ni una union declarada-- sino una mezcla no determinista.

    **Manda la mas reciente.** La anterior sigue visible como historico en la
    pestaña Model Match, y no alimenta el diagnostico. Un perfil de Model Match
    describe un momento; mezclar dos momentos no da un momento mejor.
    """
    cod, filas, _ = leer(
        "v_capturas_modelmatch_current",
        "?select=upload_batch_id,capturado_en,parseado,geografia_etiqueta,"
        "geografia_nivel,estado&parseado->>realtor_id=eq.%s"
        "&order=capturado_en.desc" % urllib.parse.quote(realtor_id))
    if cod >= 400:
        return [], {"lotes": 0, "anteriores": 0, "vigente_desde": None}
    return lote_vigente(filas or [])


def lote_vigente(filas: list) -> tuple[list, dict]:
    """De todas las filas, las del lote MAS RECIENTE. Función pura.

    Ordena aquí y no confía en el orden que venga: `order=capturado_en.desc`
    ya se pide en la consulta, pero apoyar la regla en que el servidor
    devuelva lo que se le pidió es apoyarla en algo que no se comprueba.
    """
    if not filas:
        return [], {"lotes": 0, "anteriores": 0, "vigente_desde": None}

    ordenadas = sorted(filas, key=lambda f: f.get("capturado_en") or "",
                       reverse=True)
    vigente = ordenadas[0]["upload_batch_id"]
    lotes = {f["upload_batch_id"] for f in ordenadas}
    return [f for f in ordenadas if f["upload_batch_id"] == vigente], {
        "lotes": len(lotes),
        "anteriores": len(lotes) - 1,
        "vigente_desde": ordenadas[0].get("capturado_en"),
        "anteriores_desde": sorted(
            {f["capturado_en"] for f in ordenadas
             if f["upload_batch_id"] != vigente}, reverse=True),
    }

#: Por debajo de esto, el bloque no trajo metricas de verdad y no hay nada que
#: promover. Un bloque real de Market Signals trae 38-45 campos.
MINIMO_CAMPOS_PARA_PROMOVER = 5


def promover_a_mercados(filas: list[dict], lote: str, ahora: str,
                        ventana_meses: int | None = None
                        ) -> tuple[list[dict], list[str]]:
    """Los Market Signals de una captura -> la biblioteca de benchmarks.

    Por que ocurre AL GUARDAR y no en un paso aparte
    ------------------------------------------------
    Un paso aparte es un paso que alguien tiene que acordarse de correr, y
    mientras no corre **no falla nada**: `capturas_modelmatch` se llena, las
    metricas quedan parseadas, y `pacs.mercados` sigue vacia. Eso es lo que
    paso: cuatro bloques de Armando con sus 35 metricas cada uno, y cero filas
    en la biblioteca. Ningun contraste de Model Match podia correr y nada lo
    decia.

    Un perfil individual expira; un benchmark de condado no. Por eso la
    biblioteca vive aparte de cualquier realtor -- pero solo sirve si se llena.

    Devuelve (filas_de_mercado, fallos). Un bloque con metricas parseadas que
    no produce fila es un FALLO DECLARADO: la tabla exige `condado_fips` para
    nivel condado, y `geo.fips` no adivina.
    """
    from geo.fips import FipsNoResuelto, cargar as cargar_fips, resolver

    salida: list[dict] = []
    fallos: list[str] = []
    tabla = None

    for f in filas:
        p = f["parseado"]
        if p.get("seccion") != "market_signals":
            continue
        metricas = p.get("metricas") or {}
        campos = metricas.get("campos") or 0
        etiqueta = p.get("etiqueta_geografica")
        nivel = p.get("nivel")
        donde = etiqueta or "(sin etiqueta)"

        if campos < MINIMO_CAMPOS_PARA_PROMOVER:
            # Sin metricas no hay benchmark, y eso NO es un fallo de promocion:
            # es que el bloque no traia nada. El fallo del parser ya se reporta
            # por su lado.
            continue

        estado = f.get("estado")
        condado_fips = None
        if nivel == "condado":
            if not (estado and etiqueta):
                fallos.append(
                    "%s · bloque de condado sin estado o sin etiqueta, asi que "
                    "no se puede resolver su FIPS. Tiene %d metricas parseadas "
                    "y NO entra en la biblioteca." % (donde, campos))
                continue
            if tabla is None:
                tabla = cargar_fips()
            try:
                condado_fips = resolver(estado, etiqueta, tabla)[0]
            except FipsNoResuelto as exc:
                fallos.append(
                    "%s · no se pudo resolver el FIPS (%s). Tiene %d metricas "
                    "parseadas y NO entra en la biblioteca: `pacs.mercados` "
                    "exige FIPS para nivel condado, y no se adivina."
                    % (donde, str(exc).split("\n")[0], campos))
                continue

        # LA VENTANA DEL BENCHMARK. Estaba en NULL en todas las filas porque
        # nadie la escribia: `pacs.mercados` tiene las dos columnas desde el
        # principio. Sin ellas la ficha compara al realtor contra un mercado
        # sin poder decir de que periodo es -- y «FHA 14,1%» de hace catorce
        # meses y de hace tres no son el mismo numero.
        #
        # Sale de la ventana que declara EL BLOQUE (`Last N Months` de Market
        # Insight, que tiene su propio selector) y, si no la trae, de la del
        # perfil. Si no hay ninguna, quedan en NULL: una ventana inventada se
        # guarda igual de bien que una correcta.
        meses = metricas.get("ventana_meses") or ventana_meses
        desde = hasta = None
        if meses:
            try:
                hasta = dt.date.fromisoformat(str(ahora)[:10])
                desde = _restar_meses(hasta, int(meses))
            except (TypeError, ValueError):
                desde = hasta = None

        salida.append({
            "upload_batch_id": lote, "uploaded_at": ahora,
            "condado_fips": condado_fips, "estado": estado, "nivel": nivel,
            "fuente": "modelmatch", "metricas": metricas,
            "capturado_en": ahora,
            "rango_desde": desde.isoformat() if desde else None,
            "rango_hasta": hasta.isoformat() if hasta else None,
        })
    return salida, fallos


def _restar_meses(d: "dt.date", meses: int) -> "dt.date":
    """`d` menos N meses, sin dependencias. El dia se recorta al fin de mes."""
    total = (d.year * 12 + (d.month - 1)) - meses
    ano, mes = divmod(total, 12)
    mes += 1
    if mes == 12:
        ultimo = 31
    else:
        ultimo = (dt.date(ano + (mes == 12), (mes % 12) + 1, 1)
                  - dt.timedelta(days=1)).day
    return dt.date(ano, mes, min(d.day, ultimo))


# ══════════════════════════════════════════════════════════════════════════════
# LA FICHA v3 · las nueve secciones que el BD lee antes de escribir
# ══════════════════════════════════════════════════════════════════════════════

def ficha_v3(params: dict) -> tuple[int, dict]:
    """La maqueta v3, con datos de la base. Ver `api/ficha.py` para las reglas.

    Es UNA petición y no nueve: las secciones se contradicen si cada una lee
    por su lado y una llega tarde. El BD abre la ficha y la lee entera o no la
    lee.
    """
    from api.ficha import (
        PENDIENTES,
        contactos_por_canal,
        dolores_posibles,
        iniciales,
        objecion,
        razones,
        telefono_para_el_primer_contacto,
        trimestres_de,
    )
    from captura.transacciones import resumen as resumen_tx
    from motor.ganchos import gancho_de
    from motor.narrativa import narrativa
    from motor.qualifiers import enunciado

    realtor_id = (params.get("realtor_id") or "").strip()
    if not realtor_id:
        return 400, {"error": "falta realtor_id"}
    rid = urllib.parse.quote(realtor_id)

    cod, filas, _ = leer("realtors", "?select=%s&id=eq.%s" % (CAMPOS_LISTA, rid))
    if cod >= 400 or not filas:
        return (cod if cod >= 400 else 404), {"error": "realtor no encontrado"}
    realtor = filas[0]

    _c, evs, _ = leer(
        "v_evaluacion_actual",
        "?select=resultado,dolor_primario,dolores_secundarios,apertura,"
        "gating_qualifier,gating_intensidad,confianza,version_reglas,"
        "evaluado_en,excluido,excluido_motivo,veredicto_contacto"
        "&realtor_id=eq.%s" % rid)
    ev = (evs or [None])[0] or {}
    activaciones = (ev.get("resultado") or {}).get("activaciones") or []

    _c, cts, _ = leer("contactos",
                      "?select=canal,valor,fuente,vigente&realtor_id=eq.%s" % rid)

    # ── Model Match, del lote que manda ─────────────────────────────────────
    crudas, cuantas = capturas_que_mandan(realtor_id)
    perfiles, mercados = [], []
    for f in crudas or []:
        p = f.get("parseado") or {}
        if p.get("perfil"):
            perfiles.append(p["perfil"])
        if p.get("metricas"):
            mercados.append({"nivel": f.get("geografia_nivel"),
                             "estado": f.get("estado"),
                             "etiqueta": f.get("geografia_etiqueta"),
                             "metricas": p["metricas"],
                             "capturado_en": f.get("capturado_en")})
    mercados.extend(_mercados_enlazados(crudas))
    perfil = unir_perfiles(perfiles) if perfiles else {}
    tx = perfil.get("transacciones") if isinstance(perfil, dict) else None
    resumen = resumen_tx(tx) if (tx or {}).get("filas") else None

    # ── Instagram, con su compuerta ─────────────────────────────────────────
    _c, sen, _ = leer("v_ig_senales_current",
                      "?select=handle,estado_perfil,captions_n,comentarios_n,"
                      "senales,capturado_en&realtor_id=eq.%s" % rid)
    _c, cls, _ = leer("v_ig_clase_actual",
                      "?select=clase,motivo,handle&realtor_id=eq.%s" % rid)
    ig = dict(sen[0]) if sen else {}
    if cls:
        ig["clase_perfil"] = cls[0].get("clase")
        ig["clase_motivo"] = cls[0].get("motivo")
        ig.setdefault("handle", cls[0].get("handle"))

    # Los contactos van DESPUÉS de leer Model Match e Instagram, porque salen
    # de las cuatro fuentes. Y usan el MISMO agrupado que el paquete: si la
    # pantalla usara otro, ella y lo que Cowork lee dirían cosas distintas
    # sobre el mismo teléfono.
    from motor.paquete import contactos_del_realtor
    contactos = contactos_del_realtor(realtor, cts or [], perfil or None, ig)

    ganchos = {}
    for a in activaciones:
        if a.get("familia") != "P":
            continue
        g = gancho_de(a["qualifier"], intensidad=a.get("intensidad"),
                      acto_de_habla=a.get("acto"))
        if g:
            ganchos[a["qualifier"]] = g.texto
    enunciados = {a["qualifier"]: enunciado(a["qualifier"])
                  for a in activaciones}

    tel = telefono_para_el_primer_contacto(contactos)
    ver = ev.get("veredicto_contacto") or {}

    return 200, {
        # 1 · quién es y contacto
        "quien_es": {
            "nombre": realtor.get("nombre_completo"),
            # El de la captura, cuando lo hay: Isabella confirmó al capturar
            # que es la misma persona, así que su forma manda sobre la del
            # volcado del libro.
            "nombre_mm": (perfil or {}).get("nombre"),
            "iniciales": iniciales((perfil or {}).get("nombre")
                                   or realtor.get("nombre_completo")),
            "brokerage": realtor.get("brokerage"),
            "estado": ESTADOS.get(realtor.get("estado")) or realtor.get("estado"),
            "unidades_ano": realtor.get("unidades_ano"),
            "bio": narrativa(
                realtor, estado_nombre=ESTADOS.get(realtor.get("estado")),
                perfil_mm=perfil or None,
                mercado=((mercados[0].get("metricas") if mercados else None)),
                donde=(mercados[0].get("etiqueta") if mercados else None)),
            "contactos": contactos,
        },
        # 2 · veredicto y Salesforce
        "veredicto": {
            "estado": ver.get("estado"),
            "motivo": ver.get("motivo"),
            "evidencia": ver.get("evidencia") or {},
        },
        "salesforce": {"pendiente": PENDIENTES["salesforce"],
                       "sf_lead_id": realtor.get("sf_lead_id")},
        # 3 · por qué ella
        "por_que_ella": razones(resumen, activaciones, perfil),
        "prioridad": {"pendiente": PENDIENTES["puntaje"]},
        # 4 · dolores posibles
        "dolores": dolores_posibles(activaciones, enunciados, ganchos),
        # 5 y 6 · cómo abrirle la conversación
        "conversar": {
            "telefono": tel,
            "objecion": objecion(resumen),
            "preguntas": [d["pregunta"] for d in
                          dolores_posibles(activaciones, enunciados, ganchos)
                          if d.get("pregunta")][:4],
            "lo_asignado": {"pendiente": PENDIENTES["lo_asignado"]},
        },
        # 7 · producción
        "produccion": (None if not resumen else {
            "resumen": resumen,
            "trimestres": trimestres_de((tx or {}).get("filas") or []),
            "filas": [
                {k: f.get(k) for k in
                 ("fecha", "lado", "ciudad", "zip", "precio", "prestamo",
                  "enganche", "tipo", "tasa", "lender", "lo_nombre",
                  "estado_prestamo")}
                for f in sorted((tx or {}).get("filas") or [],
                                key=lambda f: f.get("fecha") or "",
                                reverse=True)],
            "completa": (tx or {}).get("completa"),
            "aviso": (tx or {}).get("aviso"),
        }),
        "sin_transactions": (None if resumen else
                             "Falta Transactions: sin esa pestaña no se sabe "
                             "cuáles de sus compras fueron cash, y eso no se "
                             "calcula por diferencia."),
        # 8 · Instagram
        "instagram": _instagram_para_la_ficha(ig),
        # 9 · mercado y Census
        "mercados": [{"etiqueta": m.get("etiqueta"), "nivel": m.get("nivel"),
                      "capturado_en": m.get("capturado_en"),
                      "de_la_biblioteca": m.get("de_la_biblioteca", False),
                      "rango_desde": m.get("rango_desde"),
                      "rango_hasta": m.get("rango_hasta"),
                      "metricas": m.get("metricas") or {}}
                     for m in mercados],
        "census": {"pendiente": PENDIENTES["census_zip"]},
        # 10 · fuentes
        "fuentes": {
            "model_match": (crudas[0].get("capturado_en") if crudas else None),
            "capturas_anteriores": cuantas.get("anteriores"),
            "instagram": ig.get("capturado_en"),
            "evaluado_en": ev.get("evaluado_en"),
            "version_reglas": ev.get("version_reglas"),
        },
        "falta_en_la_ficha": [
            "puntaje · %s" % PENDIENTES["puntaje"],
            "LO de HOMESÍ asignado · %s" % PENDIENTES["lo_asignado"],
            "Census por ZIP · %s" % PENDIENTES["census_zip"],
            "seguidores · %s" % PENDIENTES["seguidores"],
            "Salesforce · %s" % PENDIENTES["salesforce"],
        ],
    }


def ficha_v3_completa(params: dict) -> tuple[int, dict]:
    """La ficha con la forma del esquema: código + IA validada.

    La app VALIDA AL LEER, y no solo confía en que Cowork validó antes de
    escribir. Dos motivos: el paquete cambia --una ficha válida ayer puede
    citar una transacción que hoy se re-capturó-- y una validación que solo
    corre del lado del que produce el texto es una promesa, no una guarda.

    Una sección que no pasa se apaga sola y las de código se muestran igual.
    Nunca se muestra un texto sin validar, y nunca se pierde lo comprobado.
    """
    from motor.validar_ficha import secciones_con_problema, validar

    realtor_id = (params.get("realtor_id") or "").strip()
    if not realtor_id:
        return 400, {"error": "falta realtor_id"}
    rid = urllib.parse.quote(realtor_id)

    cod, base = ficha_v3(params)          # las secciones de código
    if cod >= 400:
        return cod, base

    _c, paqs, _ = leer("v_paquete_ficha",
                       "?select=paquete,hash_paquete&realtor_id=eq.%s" % rid)
    paquete = (paqs or [{}])[0].get("paquete") or {}
    _c, fichas, _ = leer(
        "v_ficha_ia_actual",
        "?select=json,generada_en,generada_por,version_prompt,hash_paquete"
        "&realtor_id=eq.%s" % rid)
    redactada = (fichas or [None])[0]

    ficha = _ficha_solo_codigo(base)
    redaccion: dict = {}
    if redactada:
        problemas = validar(redactada.get("json") or {}, paquete)
        malas = secciones_con_problema(problemas)
        # Se mezcla lo que SÍ pasó, sección por sección.
        for clave, valor in (redactada.get("json") or {}).items():
            if clave in malas:
                continue
            if isinstance(valor, dict) and isinstance(ficha.get(clave), dict):
                ficha[clave] = {**ficha[clave], **valor}
            else:
                ficha[clave] = valor
        ficha["_no_validas"] = malas
        redaccion = {
            "generada_en": redactada.get("generada_en"),
            "generada_por": redactada.get("generada_por"),
            "version_prompt": redactada.get("version_prompt"),
            "problemas": problemas,
            "secciones_apagadas": sorted(malas),
            # No se esconde la ficha vieja: se marca. Una ficha vieja bien
            # marcada es útil; una ficha vieja sin marcar es una mentira con
            # fecha.
            "desactualizada": bool(
                paquete.get("hash_paquete")
                and redactada.get("hash_paquete") != paquete["hash_paquete"]),
        }

    return 200, {"ficha": ficha, "redaccion": redaccion,
                 "hay_paquete": bool(paquete)}


def bloques_ia(params: dict) -> tuple[int, dict]:
    """Los bloques redactados de Instagram, Dossier y Secuencia, validados.

    Es el mismo mecanismo de la ficha --se lee de `pacs.fichas_ia`, se valida
    al leer contra el paquete guardado, y lo que no pasa no se muestra-- con
    una diferencia: **apaga la PARTE, no la sección**.

    La ficha se lee de un tirón y apagar una de sus ocho secciones es una
    decisión razonable. El dossier son siete bloques y la secuencia siete
    toques: apagar los siete porque el toque 4 promete material esconde seis
    textos que sí se sostienen y deja al BD sin secuencia por un párrafo.

    Un endpoint aparte y no dentro de `/api/dossier` por dos razones: la
    lectura es la misma para las tres pestañas --una implementación, no tres--
    y `/api/dossier` responde 409 a un excluido, que es correcto para la
    secuencia y dejaría a Instagram sin texto por una razón que no es la suya.
    """
    from motor.nunca import BLOQUE_F
    from motor.secuencia import DIAS_PACS
    from motor.validar_ficha import partes_con_problema, validar

    realtor_id = (params.get("realtor_id") or "").strip()
    if not realtor_id:
        return 400, {"error": "falta realtor_id"}
    rid = urllib.parse.quote(realtor_id)

    _c, paqs, _ = leer("v_paquete_ficha",
                       "?select=paquete,hash_paquete&realtor_id=eq.%s" % rid)
    paquete = (paqs or [{}])[0].get("paquete") or {}
    _c, fichas, _ = leer(
        "v_ficha_ia_actual",
        "?select=json,generada_en,generada_por,version_prompt,hash_paquete"
        "&realtor_id=eq.%s" % rid)
    redactada = (fichas or [None])[0]

    # El bloque F viaja SIEMPRE, haya o no texto redactado: es lo que el BD
    # tiene que tener delante cuando escribe a mano, y es justo entonces
    # cuando no hay ficha que lo traiga.
    vacio = {
        "instagram_analisis": None,
        "dossier": {"F": [dict(x) for x in BLOQUE_F]},
        "secuencia": None,
        "dias_pacs": list(DIAS_PACS),
        "pendientes": {},
        "redaccion": {},
        "hay_ficha": False,
        "hay_paquete": bool(paquete),
    }
    if not redactada:
        return 200, vacio

    ficha = redactada.get("json") or {}
    problemas = validar(ficha, paquete)
    partes = partes_con_problema(problemas)

    salida = dict(vacio)
    salida["hay_ficha"] = True
    salida["instagram_analisis"] = _solo_lo_valido(
        ficha.get("instagram_analisis"), partes.get("instagram_analisis") or {})
    dos = _solo_lo_valido(ficha.get("dossier"),
                          partes.get("dossier") or {}) or {}
    # F lo pone el código SIEMPRE, y pisa lo que venga: si la IA lo escribió,
    # el validador ya lo marcó, pero el bloque tiene que estar igual.
    dos["F"] = [dict(x) for x in BLOQUE_F]
    salida["dossier"] = dos
    salida["secuencia"] = _secuencia_valida(
        ficha.get("secuencia"), partes.get("secuencia") or {}, DIAS_PACS)
    salida["pendientes"] = {k: v for k, v in partes.items()
                            if k in ("instagram_analisis", "dossier",
                                     "secuencia")}
    salida["redaccion"] = {
        "generada_en": redactada.get("generada_en"),
        "generada_por": redactada.get("generada_por"),
        "version_prompt": redactada.get("version_prompt"),
        "desactualizada": bool(
            paquete.get("hash_paquete")
            and redactada.get("hash_paquete") != paquete["hash_paquete"]),
    }
    return 200, salida


def _solo_lo_valido(seccion, partes: dict):
    """La sección sin las partes que no pasaron, y con su motivo en el hueco.

    El hueco NO se borra: se marca. Un bloque que desaparece se lee como que
    no había nada que decir; un bloque que dice «Pendiente: el número no está
    en la evidencia» se lee como lo que es.
    """
    if not isinstance(seccion, dict):
        return None
    if "" in partes:                  # el problema es de la sección entera
        return {"_pendiente": partes[""]}
    salida = {}
    for clave, valor in seccion.items():
        motivos = partes.get(clave)
        salida[clave] = {"_pendiente": motivos} if motivos else valor
    for clave, motivos in partes.items():
        salida.setdefault(clave, {"_pendiente": motivos})
    return salida


def _secuencia_valida(seq, partes: dict, dias) -> dict | None:
    """Los toques, con los que no pasaron reducidos a su número y su día.

    El número y el día del toque apagado salen de `DIAS_PACS`, no del texto:
    justamente el día pudo ser lo que falló, y repetir el dato equivocado al
    lado del «Pendiente» sería mostrar sin validar lo que no se validó.
    """
    if not isinstance(seq, dict):
        return None
    if "" in partes:
        return {"_pendiente": partes[""], "toques": []}
    toques = []
    for i, t in enumerate(seq.get("toques") or []):
        motivos = partes.get("toques[%d]" % i)
        if motivos:
            toques.append({"n": i + 1,
                           "dia": dias[i] if i < len(dias) else None,
                           "_pendiente": motivos})
        else:
            toques.append(t)
    return {"toques": toques}


def _ficha_solo_codigo(base: dict) -> dict:
    """Las secciones `escribe: codigo`, con la forma del esquema de la ficha."""
    q = base.get("quien_es") or {}
    prod = base.get("produccion") or {}
    r = (prod or {}).get("resumen") or {}
    c = r.get("compras") or {}
    v = r.get("ventas") or {}
    ig = base.get("instagram") or {}
    filas = (prod or {}).get("filas") or []

    return {
        "cabecera": {
            # El nombre de la CAPTURA, no el del libro. El libro los trae en
            # mayúsculas --«ANA OSORIO»-- porque es un volcado, y Model Match
            # trae el que ella usa. En una ficha que el BD lee antes de llamar,
            # gritar el nombre es la primera cosa que se nota.
            "nombre": q.get("nombre_mm") or q.get("nombre"),
            "iniciales": q.get("iniciales"),
            "meta": " · ".join(x for x in (q.get("brokerage"), q.get("estado"))
                               if x),
            "contactos": [
                {"canal": x["canal"], "valor": x["valor"],
                 "fuentes": x["fuentes"], "difiere": x["una_sola_fuente"]}
                for x in (q.get("contactos") or [])],
        },
        "veredicto": {"estado": (base.get("veredicto") or {}).get("estado"),
                      "texto": (base.get("veredicto") or {}).get("motivo")},
        "salesforce": base.get("salesforce") or {},
        "por_que_ella": {"prioridad": "Pendiente"},
        "produccion": (None if not prod else {
            "kpis": [
                {"n": "%s / %s" % (c.get("total") or 0, v.get("total") or 0),
                 "l": "buys / listings"},
                {"n": _mm_dinero(r.get("volumen_compra")),
                 "l": "buy side · %s listing side"
                      % _mm_dinero(r.get("volumen_venta"))},
                {"n": _mm_dinero(r.get("precio_mediano_compra")),
                 "l": "median purchase price"},
                {"n": (filas[0].get("fecha") if filas else "—"),
                 "l": "último closing"},
            ],
            "trimestres": [{"t": t["etiqueta"], "n": t["n"],
                            "parcial": t["parcial"]}
                           for t in (prod.get("trimestres") or [])],
            # La nota y el título los escribe el CÓDIGO con las fechas y el
            # conteo de verdad. En la plantilla estaban fijos, y una frase
            # genérica encima de datos que la app ya sabe es peor que el dato.
            "trimestres_nota": _nota_de_trimestres(filas),
            "loan_mix_titulo": ("Loan type de sus %d buys" % c["total"]
                                if c.get("total") else "Loan type de sus buys"),
            "loan_mix": _loan_mix(r.get("loan_mix_compra") or {}, c),
            "lenders": [{"lender": k, "n": n,
                         "detalle": _los_del_lender(filas, k)}
                        for k, n in (r.get("lenders_compra") or {}).items()],
            "operaciones": filas,
        }),
        "instagram": {"encabezado": (
            None if not ig else
            "Instagram · @%s%s" % (ig.get("handle") or "—",
                                   (" · leído el %s"
                                    % fecha_legible(ig.get("leido_en")))
                                   if ig.get("leido_en") else ""))},
        "fuentes": _texto_de_fuentes(base.get("fuentes") or {}),
        # `{item, motivo, texto_visible}`: el pie muestra el item corto y cada
        # sección usa su texto largo. Antes el texto largo estaba escrito en la
        # plantilla --«con licencia y que hable español»-- y por eso decía algo
        # distinto de la maqueta, que nombra el estado.
        "pendientes": _pendientes_visibles(base, prod),
    }


#: Cómo se llaman los tipos de préstamo cuando alguien los lee. Model Match
#: abrevia; la maqueta los escribe. `HE` es la única que no se entiende sola.
_NOMBRE_DEL_TIPO = {"HE": "Home Equity"}


def _loan_mix(mix: dict, compras: dict) -> list[dict]:
    """El reparto de tipos de préstamo, de mayor a menor y `Pendiente` al final.

    Salía en el orden en que el parser encontró los tipos --Conventional, HE,
    FHA, Cash-- y la maqueta lo muestra ordenado. En una lista de barras el
    orden ES la lectura: sin ordenar hay que recorrer los números para ver cuál
    manda, que es justo lo que la barra venía a evitar.

    `Pendiente` va último aunque tenga más que otro: no es un tipo de préstamo,
    es que Model Match todavía no lo sabe.
    """
    filas = [{"tipo": _NOMBRE_DEL_TIPO.get(k, k), "n": n}
             for k, n in (mix or {}).items()]
    if compras.get("cash_segun_mm"):
        filas.append({"tipo": "Cash", "n": compras["cash_segun_mm"]})
    filas.sort(key=lambda f: -f["n"])
    if compras.get("cash_provisional"):
        filas.append({"tipo": "Pendiente", "n": compras["cash_provisional"]})
    return filas


def _los_del_lender(filas: list[dict], lender: str) -> str:
    """«Fabian Viera (19 mar y 3 abr) · Brian Dombrowski (30 jul)».

    El título de esa caja dice «Lenders y LOs de sus buyers» y el campo
    `detalle` iba en blanco: la ficha prometía los LOs y mostraba solo el
    conteo. El dato estaba --cada operación trae su `lo_nombre`-- y lo que
    faltaba era juntarlo.

    El rate se añade solo cuando el lender aparece UNA vez y la operación lo
    trae: con una sola operación el rate es un dato de esa operación, y es lo
    que delata un non-QM. Con cinco sería un promedio que nadie pidió.

    La fila se busca con `nombre_de_lender`, que es con lo que se CONTÓ. El
    conteo dice «Guaranteed Rate» y la fila dice «Guaranteed Rate Inc»:
    comparando el nombre crudo, cuatro de los cinco lenders se quedaban sin
    LO y el único que salía era «Peoples Bank», que es el que no lleva sufijo.
    Un fallo que se ve como un dato que falta, no como un error.
    """
    suyas = [f for f in filas
             if nombre_de_lender(f.get("lender")) == nombre_de_lender(lender)
             and f.get("lado") != "venta"]
    # Las operaciones llegan de la más nueva a la más vieja, que es como se
    # leen en una tabla y NO como se cuenta una relación: «Fabian Viera (3 abr
    # y 19 mar)» se lee al revés. Dentro de cada LO, las fechas en orden; y los
    # LOs, por la primera vez que aparecen.
    por_lo: dict[str, list[str]] = {}
    for f in suyas:
        quien = (f.get("lo_nombre") or "").strip()
        if not quien or not f.get("fecha"):
            continue
        por_lo.setdefault(quien, []).append(f["fecha"])
    partes = []
    for quien, cuando in sorted(por_lo.items(), key=lambda kv: min(kv[1])):
        dias = [d for d in (dia_y_mes(x) for x in sorted(cuando)) if d]
        partes.append("%s (%s)" % (quien, " y ".join(dias)) if dias else quien)
    texto = " · ".join(partes)
    if len(suyas) == 1 and suyas[0].get("tasa") is not None:
        tasa = str(suyas[0]["tasa"]).replace(".", ",")
        texto = (texto + " · " if texto else "") + "rate %s %%" % tasa
    return texto


def _nota_de_trimestres(filas: list[dict]) -> str | None:
    """«los datos empiezan el X y llegan hasta el Y».

    Sin las fechas, el asterisco de los trimestres parciales no dice nada: hay
    que poder ver POR QUÉ el primero y el último están cortados.
    """
    fechas = sorted(f["fecha"] for f in (filas or []) if f.get("fecha"))
    if not fechas:
        return None
    return ("* Trimestres incompletos: los datos empiezan el %s y llegan hasta "
            "el %s." % (fecha_legible(fechas[0]), fecha_legible(fechas[-1])))


def _pendientes_visibles(base: dict, prod: dict | None) -> list[dict]:
    from api.ficha import PENDIENTES

    zips = sorted(((prod or {}).get("resumen") or {}).get("zips_de_compra")
                  or {}, key=lambda z: -(((prod or {}).get("resumen") or {})
                                         .get("zips_de_compra") or {})[z])[:3]
    return [
        {"item": "puntaje", "motivo": PENDIENTES["puntaje"],
         "texto_visible": "Prioridad: pendiente"},
        {"item": "LO asignado", "motivo": PENDIENTES["lo_asignado"],
         "texto_visible": ("Qué LO de HOMESÍ la atiende (con licencia en %s y "
                           "que hable español)."
                           % ((base.get("quien_es") or {}).get("estado")
                              or "su estado"))},
        {"item": "Census por ZIP", "motivo": PENDIENTES["census_zip"],
         "texto_visible": ("Census por ZIP%s"
                           % ((" (%s)" % ", ".join(zips)) if zips else ""))},
        {"item": "seguidores", "motivo": PENDIENTES["seguidores"],
         "texto_visible": "número de seguidores"},
    ]


def _mm_dinero(n):
    if not n:
        return "—"
    if n >= 1e6:
        return "$%s M" % ("%.1f" % (n / 1e6)).replace(".", ",")
    return "$%dK" % round(n / 1e3)


def _texto_de_fuentes(f: dict) -> str:
    partes = []
    if f.get("model_match"):
        partes.append("Model Match (capturado el %s)"
                      % fecha_legible(f["model_match"]))
    if f.get("instagram"):
        partes.append("Instagram (leído el %s)" % fecha_legible(f["instagram"]))
    if f.get("evaluado_en"):
        partes.append("diagnóstico del %s" % fecha_legible(f["evaluado_en"]))
    return " · ".join(partes)


def pedir_ficha(d: dict) -> tuple[int, dict]:
    """El botón «Pedir actualización». Encola al realtor para que Cowork lo tome.

    Es una cola y no una columna en `realtors` porque se pide varias veces y
    hay que poder ver quién lo pidió y cuándo.
    """
    realtor_id = (d.get("realtor_id") or "").strip()
    if not realtor_id:
        return 400, {"error": "falta realtor_id"}
    _c, paqs, _ = leer("v_paquete_ficha", "?select=hash_paquete&realtor_id=eq.%s"
                       % urllib.parse.quote(realtor_id))
    cod, det, _ = escribir("fichas_ia_pendientes", [{
        "realtor_id": realtor_id,
        "pedida_por": (d.get("pedida_por") or "pantalla"),
        "motivo": (d.get("motivo") or "pedido desde la ficha"),
        "hash_paquete": (paqs or [{}])[0].get("hash_paquete"),
    }], devolver=False)
    if cod >= 400:
        return cod, {"error": "no se pudo encolar", "detalle": det}
    return 200, {"encolado": True}


def _instagram_para_la_ficha(ig: dict) -> dict | None:
    """Lo que Instagram aporta, PASADO POR LA COMPUERTA DE PERFIL.

    Una cuenta que no es de quien creíamos no aporta nada, y la ficha lo dice
    en vez de mostrar sus números: 36 de 39 perfiles no utilizables tenían un
    dolor primario vigente, incluido un criadero de gallos.

    El dato de que un lender le refiere clientes va AQUÍ, como contexto, y
    nunca en «Por qué ella» ni en el mensaje: RESPA §8.
    """
    from ingest.instagram.clase_perfil import CLASES_UTILIZABLES
    from motor.desde_instagram import senales_visibles

    if not ig:
        return None
    clase = ig.get("clase_perfil")
    utilizable = clase in CLASES_UTILIZABLES and clase != "otro_perfil"
    s = senales_visibles(ig)
    return {
        "handle": ig.get("handle"),
        "clase": clase,
        "motivo_de_la_clase": ig.get("clase_motivo"),
        "utilizable": utilizable,
        "leido_en": ig.get("capturado_en"),
        "estado_perfil": ig.get("estado_perfil"),
        # Los conteos NO van sueltos: cada uno con lo que se leyó de él.
        "posts_leidos": ig.get("captions_n"),
        "comentarios_leidos": ig.get("comentarios_n"),
        "idioma": (None if not utilizable else {
            "posts_en_espanol": s.get("idioma_publica_es"),
            "posts_en_ingles": s.get("idioma_publica_en"),
        }),
        "tema_dominante": s.get("tema_dominante") if utilizable else None,
        "audiencia_dominante": s.get("audiencia_dominante") if utilizable else None,
        "destacadas": s.get("destacadas_titulos") if utilizable else None,
        # RESPA §8: contexto, nunca gancho.
        "respa": ("Si menciona que un lender le refiere clientes, es contexto "
                  "para entender su operación. No se usa en el mensaje ni "
                  "como razón para contactarla (RESPA §8)."),
    }


# ══════════════════════════════════════════════════════════════════════════════
# LA BIBLIOTECA YA TIENE ESTE MERCADO
# ══════════════════════════════════════════════════════════════════════════════
#
# Un benchmark de condado no es del realtor: es del condado. Pedirle a quien
# captura que pegue Cook por cuarta vez en un dia es pedirle cuatro veces el
# mismo dato, y cada pegado es una oportunidad de ponerlo en la caja
# equivocada. Sobre 25 capturas eso son 175 oportunidades.
#
# Un perfil individual expira; un benchmark no -- pero tampoco es eterno, y por
# eso hay un corte. A los 30 dias la caja deja de resolverse sola y pasa a
# OFRECER las dos opciones, que es distinto de exigir y distinto de decidir.

#: Por debajo de esto, la caja no pide pegar. Por encima, ofrece.
DIAS_BENCHMARK_FRESCO = 30


def mercados_en_biblioteca(params: dict) -> tuple[int, dict]:
    """¿Cuáles de estas geografías ya están en `pacs.mercados`, y de cuándo?

    Recibe `estado` y `condados` (separados por `|`). Devuelve una entrada por
    geografía con su estado: `fresco`, `viejo` o `no_esta`.

    NO decide por nadie: `viejo` trae los dos caminos y la pantalla pregunta.
    """
    from geo.fips import FipsNoResuelto
    from geo.fips import cargar as cargar_fips
    from geo.fips import resolver

    estado = normalizar_estado((params.get("estado") or "").strip())
    condados = [c.strip() for c in (params.get("condados") or "").split("|")
                if c.strip()]
    if not estado:
        return 400, {"error": "falta el estado"}

    # Se pide TODO de una vez: una consulta por condado son 25 idas y vueltas
    # desde el navegador y la pantalla se queda en blanco mientras tanto.
    cod, filas, _ = leer(
        "mercados",
        "?select=id,nivel,estado,condado_fips,capturado_en,rango_desde,"
        "rango_hasta,metricas->>campos,upload_batch_id"
        "&estado=eq.%s&order=capturado_en.desc&limit=2000"
        % urllib.parse.quote(estado))
    if cod >= 400:
        return cod, {"error": "supabase", "detalle": filas}

    # La MAS NUEVA por geografia. La tabla es append-only, así que hay varias.
    por_geo: dict = {}
    for f in filas or []:
        clave = (f["nivel"], f.get("condado_fips") or "")
        por_geo.setdefault(clave, f)

    # De qué realtor salió cada lote, para poder decirlo.
    lotes = sorted({f["upload_batch_id"] for f in por_geo.values()})
    de_quien: dict = {}
    if lotes:
        _c, caps, _ = leer(
            "capturas_modelmatch",
            "?select=upload_batch_id,realtor_id&upload_batch_id=in.(%s)"
            "&alcance=eq.perfil" % ",".join(lotes))
        ids = sorted({c["realtor_id"] for c in (caps or []) if c.get("realtor_id")})
        nombres = {}
        if ids:
            _c, rs, _ = leer("realtors", "?select=id,nombre_completo&id=in.(%s)"
                             % ",".join(ids))
            nombres = {r["id"]: r["nombre_completo"] for r in (rs or [])}
        for c in caps or []:
            de_quien.setdefault(c["upload_batch_id"],
                                nombres.get(c.get("realtor_id")))

    tabla = None
    hoy = dt.datetime.now(dt.timezone.utc)

    def _entrada(nivel, etiqueta, fips):
        f = por_geo.get((nivel, fips or ""))
        if not f:
            return {"nivel": nivel, "etiqueta": etiqueta, "condado_fips": fips,
                    "estado_biblioteca": "no_esta"}
        dias = None
        try:
            cuando = dt.datetime.fromisoformat(
                str(f["capturado_en"]).replace("Z", "+00:00"))
            dias = (hoy - cuando).days
        except (TypeError, ValueError):
            pass
        return {
            "nivel": nivel, "etiqueta": etiqueta, "condado_fips": fips,
            "estado_biblioteca": ("no_esta" if dias is None else
                                  "fresco" if dias < DIAS_BENCHMARK_FRESCO
                                  else "viejo"),
            "mercado_id": f["id"], "capturado_en": f["capturado_en"],
            "dias": dias, "campos": f.get("campos"),
            "rango_desde": f.get("rango_desde"),
            "rango_hasta": f.get("rango_hasta"),
            "con_quien": de_quien.get(f["upload_batch_id"]),
        }

    salida = [_entrada("estado", estado, None)]
    for nombre in condados:
        fips = None
        try:
            if tabla is None:
                tabla = cargar_fips()
            fips = resolver(estado, nombre, tabla)[0]
        except FipsNoResuelto:
            # Sin FIPS no se puede buscar en la biblioteca, y tampoco se puede
            # promover: la caja tiene que pedir el pegado igual.
            salida.append({"nivel": "condado", "etiqueta": nombre,
                           "condado_fips": None,
                           "estado_biblioteca": "no_esta",
                           "sin_fips": True})
            continue
        salida.append(_entrada("condado", nombre, fips))

    return 200, {"estado": estado, "dias_fresco": DIAS_BENCHMARK_FRESCO,
                 "geografias": salida}


# ══════════════════════════════════════════════════════════════════════════════

def realtors(params: dict) -> tuple[int, dict]:
    texto = (params.get("q") or "").strip()
    estado = (params.get("estado") or "").strip()
    con_mm = (params.get("mm") or "").strip()

    # Un solo realtor por id. Lo pide el ENLACE DIRECTO: la lista trae 300 de
    # 4.249, así que buscar el id entre los cargados fallaría justo para quien
    # no aparece en la primera página, que es casi todo el mundo.
    uno = (params.get("id") or "").strip()
    if uno:
        cod, filas, _ = leer(
            "realtors", "?select=%s&id=eq.%s"
            % (CAMPOS_LISTA, urllib.parse.quote(uno)))
        if cod >= 400:
            return cod, {"error": "supabase", "detalle": filas}
        return 200, {"realtors": filas or [], "total": len(filas or [])}

    partes = ["select=" + CAMPOS_LISTA, "order=nombre_completo.asc",
              "limit=%d" % TOPE]
    if texto:
        t = urllib.parse.quote(texto.replace(",", " ").replace("*", ""))
        partes.append(
            "or=(nombre_completo.ilike.*{0}*,brokerage.ilike.*{0}*,"
            "email_principal.ilike.*{0}*)".format(t))
    if estado:
        partes.append("estado=eq." + urllib.parse.quote(estado))

    # ── LOS FILTROS SE APLICAN ANTES DEL TOPE ───────────────────────────────
    #
    # El filtro «con Model Match» traia los primeros 300 por nombre y filtraba
    # DESPUES. Hay 3 realtors con captura vigente; Aaron Gaston esta en la
    # posicion 2 y los dos Armandos en la 509 y la 511, asi que la pantalla
    # mostraba 1 de 3. Y no es que dijera «1 de 3»: decia «1», que es la forma
    # en que un filtro roto se ve exactamente igual que un dato que no existe.
    #
    # Ademas leia la TABLA `capturas_modelmatch` --con los lotes de ensayo
    # dentro-- y cruzaba por `sf_lead_id`, que es nulo en 62 realtors. Ahora es
    # la vista vigente y `realtor_id`, que es la llave.
    # Un filtro es de DOS clases, y confundirlas costaba caro:
    #
    #   · positivo    «tiene X» -> el conjunto de ids es CHICO (3 con Model
    #                 Match, 298 con Instagram). Va como `id=in.(...)`.
    #   · complemento «NO tiene X» -> el conjunto es TODO menos los de arriba,
    #                 o sea 4.246 ids. Va como `id=not.in.(...)` sobre el
    #                 conjunto CHICO.
    #
    # La version anterior materializaba el complemento --pedia los 4.249
    # realtors y restaba-- y despues cortaba en `TOPE_IDS = 400`. Dos
    # consecuencias, y la segunda es peor que la primera:
    #
    #   1 · el total decia «400», que era el tamaño del recorte y no un dato;
    #   2 · los ids se ordenan por UUID antes de cortar, asi que la lista NO
    #       eran los primeros 400 por nombre sino 400 CUALESQUIERA. Una lista
    #       ordenada alfabeticamente que en realidad es una muestra al azar es
    #       indistinguible de una lista correcta: nada se ve raro.
    ids_incluir: set | None = None
    ids_excluir: set = set()
    truncado_por_ids = False

    def _incluir(nuevos: set) -> None:
        nonlocal ids_incluir
        ids_incluir = nuevos if ids_incluir is None else (ids_incluir & nuevos)

    if con_mm in ("si", "no"):
        _c, capturas, _ = leer(
            "v_capturas_modelmatch_current",
            "?select=realtor_id&alcance=eq.perfil&limit=5000")
        con_captura = {c["realtor_id"] for c in (capturas or [])
                       if c.get("realtor_id")}
        if con_mm == "si":
            _incluir(con_captura)
        else:
            ids_excluir |= con_captura

    # Instagram: utilizable / no aporta / sin raspar.
    ig_filtro = (params.get("ig") or "").strip()
    if ig_filtro in ("utilizable", "no_aporta", "sin_raspar"):
        _c, clases, _ = leer("v_ig_clase_actual",
                             "?select=realtor_id,clase&limit=5000")
        util, no_util = set(), set()
        for c in clases or []:
            (util if c.get("clase") in CLASES_UTILIZABLES
             else no_util).add(c["realtor_id"])
        if ig_filtro == "utilizable":
            _incluir(util)
        elif ig_filtro == "no_aporta":
            _incluir(no_util)
        else:
            # «sin raspar» es el complemento de «tiene clase», que son 298.
            ids_excluir |= (util | no_util)

    # Veredicto de contacto.
    ver_filtro = (params.get("veredicto") or "").strip()
    if ver_filtro in ("excluido", "pendiente_modelmatch", "ok"):
        _c, evs, _ = leer(
            "v_evaluacion_actual",
            "?select=realtor_id&veredicto_contacto->>estado=eq.%s&limit=10000"
            % urllib.parse.quote(ver_filtro))
        _incluir({e["realtor_id"] for e in (evs or []) if e.get("realtor_id")})

    if ids_incluir is not None:
        # Un positivo que se queda sin ids no es «no hay filtro»: es «ninguno
        # cumple», y son cosas distintas.
        efectivos = sorted(ids_incluir - ids_excluir)
        if not efectivos:
            return 200, {"filas": [], "mostradas": 0, "total": "0",
                         "tope": TOPE, "truncado": False, "estados": ESTADOS}
        truncado_por_ids = len(efectivos) > TOPE_IDS
        partes.append("id=in.(%s)" % ",".join(efectivos[:TOPE_IDS]))
    elif ids_excluir:
        fuera = sorted(ids_excluir)
        truncado_por_ids = len(fuera) > TOPE_IDS
        partes.append("id=not.in.(%s)" % ",".join(fuera[:TOPE_IDS]))

    codigo, datos, cabeceras = leer("realtors", "?" + "&".join(partes),
                                    rango="0-%d" % (TOPE - 1))
    if codigo >= 400:
        return codigo, {"error": "supabase", "detalle": datos}

    filas = datos or []

    # Los excluidos van MARCADOS en la lista, no ocultos. Esconderlos haria
    # que alguien los volviera a buscar, los capturara de nuevo y no entendiera
    # por que no aparecen; y una lista que miente por omision es la que hizo
    # falta que Lisa Munoz saliera como MQL para que se notara.
    # Son 158 sobre 4.187: una sola lectura y un `in` sobre un set.
    _c, exc, _ = leer("v_evaluacion_actual",
                      "?select=realtor_id,excluido,excluido_motivo"
                      "&excluido=not.is.null&limit=2000")
    por_id = {e["realtor_id"]: e for e in (exc or []) if e.get("realtor_id")}
    for f in filas:
        e = por_id.get(f.get("id"))
        f["excluido"] = e.get("excluido") if e else None
        f["excluido_motivo"] = e.get("excluido_motivo") if e else None

    rango = cabeceras.get("Content-Range", "")
    total = rango.split("/")[-1] if "/" in rango else str(len(filas))
    # El nombre completo del estado viaja como MAPA, no como columna. En las
    # tablas del motor manda el codigo de dos letras; el nombre es para
    # mostrar, y un solo sitio donde escribirlo es un solo sitio donde puede
    # divergir. `California` en una tabla y `CA` en otra es lo que hizo que
    # ninguna de las 4.249 filas cruzara con ninguno de los 2.261 condados.
    return 200, {"filas": filas, "mostradas": len(filas), "total": total,
                 "tope": TOPE,
                 "truncado": (len(datos or []) >= TOPE) or truncado_por_ids,
                 "estados": ESTADOS}


# ══════════════════════════════════════════════════════════════════════════════

def geografias(_params: dict) -> tuple[int, dict]:
    cod, filas, _ = leer(
        "v_capturas_modelmatch_current",
        "?select=estado,parseado,capturado_en&alcance=eq.mercado"
        "&order=capturado_en.desc&limit=2000")
    if cod >= 400:
        return cod, {"error": "supabase", "detalle": filas}

    por_geo: dict[str, dict] = {}
    for f in filas or []:
        p = f.get("parseado") or {}
        nivel = p.get("nivel")
        etiqueta = p.get("etiqueta_geografica") or f.get("estado") or "?"
        clave = ("%s · %s" % (f.get("estado") or "?", etiqueta)
                 if nivel == "condado" else (f.get("estado") or "?"))
        g = por_geo.setdefault(clave, {
            "clave": clave, "nivel": nivel or "estado",
            "estado": f.get("estado"), "etiqueta": etiqueta,
            "capturas": 0, "_realtors": set(), "ultima": None})
        g["capturas"] += 1
        if p.get("realtor_id"):
            g["_realtors"].add(p["realtor_id"])
        if not g["ultima"] or (f.get("capturado_en") or "") > g["ultima"]:
            g["ultima"] = f.get("capturado_en")

    salida = sorted(
        ({k: v for k, v in g.items() if k != "_realtors"}
         | {"realtors": len(g["_realtors"])} for g in por_geo.values()),
        key=lambda g: (g["nivel"] != "estado", -g["realtors"], g["clave"]))
    return 200, {"geografias": salida, "total": len(salida)}


# ══════════════════════════════════════════════════════════════════════════════

def _contactos_de(perfil: dict, realtor_id: str, lote: str,
                  ahora: str) -> list[dict]:
    """Oficina, telefono y direccion de la cabecera de Model Match.

    **Se acumulan, no sobrescriben.** `unique (realtor_id, canal, valor,
    fuente)` incluye la fuente, asi que el telefono de MM convive con el del
    lote: son dos mediciones distintas del mismo campo y cual gana es una
    decision de lectura, no de carga.
    """
    c = (perfil or {}).get("contacto") or {}
    filas: list[dict] = []

    def agregar(canal: str, valor) -> None:
        if not valor or not str(valor).strip():
            return
        filas.append({
            "realtor_id": realtor_id, "canal": canal,
            "valor": str(valor).strip(), "fuente": FUENTE_CONTACTOS,
            "upload_batch_id": lote, "uploaded_at": ahora, "vigente": True,
        })

    agregar("telefono", c.get("telefono_oficina_e164")
            or c.get("telefono_oficina"))
    # `Direct:` es la linea del agente, no la centralita del brokerage. Se
    # perdia entera: el parser solo miraba `Office:`, asi que un perfil que
    # solo trae `Direct` quedaba sin telefono ninguno.
    #
    # Va como otra fila de canal `telefono` y no como un canal nuevo: el check
    # de `pacs.contactos` tiene cinco canales y agregar uno es una migracion
    # para una distincion que ya queda guardada en `parseado.contacto`, con sus
    # dos campos separados.
    agregar("telefono", c.get("telefono_directo_e164")
            or c.get("telefono_directo"))
    agregar("oficina", c.get("oficina"))
    agregar("direccion", c.get("direccion"))
    return filas


#: Las columnas de `pacs.transacciones`, una por una. Lo que no este aqui NO se
#: escribe, que es lo contrario de mandar el dict entero: una lista blanca no
#: deja pasar el campo que nadie penso en prohibir.
_COLUMNAS_TX = (
    "hash_fila", "fecha", "lado", "ciudad", "estado", "zip",
    "precio", "lista", "prestamo", "enganche",
    "proposito", "tipo", "tasa", "plazo",
    "estado_prestamo", "dias_desde_cierre", "recapturar_despues_de",
    "lo_nombre", "lo_nmls", "empleador", "lender", "lender_nmls", "broker",
    "title", "constructor", "agente_contraparte", "de_la_casa", "aviso_suma",
)

#: Lo que no puede llegar a la base NUNCA. El parser ya no lo devuelve y la
#: lista blanca de arriba ya lo dejaria fuera; esto es la tercera vuelta, y
#: revienta ruidosamente si las dos primeras se rompen a la vez.
#:
#: Es redundante a proposito. La vez que una sustitucion no se aplico, las
#: columnas sensibles se cargaron igual porque la unica guarda era la que
#: fallo, y el typechecker no podia verlo.
_JAMAS_EN_TX = frozenset(
    tuple(NUNCA_SE_GUARDAN)
    + ("buyers", "sellers", "compradores", "vendedores", "direccion", "calle"))


def _filas_de_transacciones(parseado: dict, realtor_id: str, lote: str,
                            ahora: str) -> list[dict]:
    """Las operaciones -> filas de `pacs.transacciones`. Sin nombres de partes.

    Revienta --no filtra en silencio-- si aparece un campo prohibido: un filtro
    callado deja el mismo bug vivo para el campo siguiente.
    """
    filas: list[dict] = []
    for f in parseado.get("filas") or []:
        prohibidos = sorted(set(f) & _JAMAS_EN_TX)
        if prohibidos:
            raise ValueError(
                "el parser de Transactions devolvió %s, que no puede llegar a "
                "la base (ECOA Regulation B). No se escribe ninguna operación."
                % ", ".join(prohibidos))
        fila = {k: f.get(k) for k in _COLUMNAS_TX}
        fila.update({
            "realtor_id": realtor_id, "upload_batch_id": lote,
            "uploaded_at": ahora, "capturado_en": ahora,
            "version_parser": parseado.get("version_parser"),
        })
        filas.append(fila)
    # Dos filas idénticas dentro del mismo pegado violan el unique del lote y
    # tirarían las N. Se deduplican aquí, y se dice cuántas.
    vistas, unicas = set(), []
    for f in filas:
        if f["hash_fila"] in vistas:
            continue
        vistas.add(f["hash_fila"])
        unicas.append(f)
    return unicas


#: Las tres metricas con las que se verifica una geografia de un vistazo.
#: Volumen porque es la que delata el grafico rodante, FHA y fallout porque son
#: las dos mitades de los contrastes que mas se usan.
METRICAS_DE_VISTAZO = (
    ("total_volume", "volumen", "dinero"),
    ("mkt_fha", "FHA", "pct"),
    ("fallout", "fallout", "pct"),
)


#: El orden de captura, que es tambien el de lectura. Las filas vuelven de
#: PostgREST en orden arbitrario cuando comparten `capturado_en` -- y todas las
#: de una captura lo comparten, porque se escriben en la misma peticion.
_ORDEN_SECCION = {"overview": 0, "market_signals": 1, "originators": 2,
                  "lenders": 3}


def _en_orden(filas: list[dict]) -> list[dict]:
    """Overview, los mercados por posicion, Originators, Lenders.

    El orden de los bloques de mercado NO es presentacion: es lo que los
    etiqueta. Mostrarlos desordenados obliga a reconstruir mentalmente cual era
    cual, que es justo lo que la pantalla tiene que ahorrar.
    """
    return sorted(filas, key=lambda f: (
        _ORDEN_SECCION.get(f["parseado"].get("seccion"), 9),
        f["parseado"].get("orden") or 0))


def paquete_de_realtor(realtor_id: str) -> dict | None:
    """El paquete de evidencia de un realtor, leyendo lo mismo que la ficha.

    Vive AQUÍ y no en `supabase/` porque lo llaman los dos: el guardado de una
    captura --que corre en Vercel, donde `supabase/` no viaja-- y el script que
    genera los 9. Dos implementaciones serían dos paquetes distintos para el
    mismo realtor según quién lo pidiera, y el `hash` dejaría de significar
    nada.

    Devuelve `None` si el realtor no existe. Un realtor sin Model Match SÍ
    tiene paquete: lo que le falta entra como `Pendiente` declarado.
    """
    from captura.transacciones import resumen as resumen_tx
    from motor.paquete import construir
    from motor.veredicto import puede_contactarse

    rid = urllib.parse.quote(realtor_id)
    _c, filas, _ = leer("realtors", "?select=%s&id=eq.%s" % (CAMPOS_LISTA, rid))
    realtor = (filas or [None])[0]
    if not realtor:
        return None

    _c, evs, _ = leer(
        "v_evaluacion_actual",
        "?select=resultado,dolor_primario,veredicto_contacto,version_reglas,"
        "evaluado_en&realtor_id=eq.%s" % rid)
    ev = (evs or [None])[0]

    crudas, _cuantas = capturas_que_mandan(realtor_id)
    perfiles, mercados = [], []
    for f in crudas or []:
        p = f.get("parseado") or {}
        if p.get("perfil"):
            perfiles.append(p["perfil"])
        if p.get("metricas"):
            mercados.append({"nivel": f.get("geografia_nivel"),
                             "estado": f.get("estado"),
                             "etiqueta": f.get("geografia_etiqueta"),
                             "metricas": p["metricas"],
                             "capturado_en": f.get("capturado_en")})
    mercados.extend(_mercados_enlazados(crudas))
    perfil = unir_perfiles(perfiles) if perfiles else {}
    tx = perfil.get("transacciones") if isinstance(perfil, dict) else None
    resumen = resumen_tx(tx) if (tx or {}).get("filas") else None

    _c, sen, _ = leer("v_ig_senales_current",
                      "?select=handle,estado_perfil,captions_n,comentarios_n,"
                      "senales,capturado_en&realtor_id=eq.%s" % rid)
    _c, cls, _ = leer("v_ig_clase_actual",
                      "?select=clase,motivo,handle&realtor_id=eq.%s" % rid)
    ig = dict(sen[0]) if sen else None
    if ig and cls:
        from ingest.instagram.clase_perfil import CLASES_UTILIZABLES
        ig["clase_perfil"] = cls[0].get("clase")
        ig["utilizable"] = (cls[0].get("clase") in CLASES_UTILIZABLES
                            and cls[0].get("clase") != "otro_perfil")

    _c, cts, _ = leer("contactos",
                      "?select=canal,valor,fuente&realtor_id=eq.%s" % rid)

    ver = (ev or {}).get("veredicto_contacto") or puede_contactarse(
        perfil or None).a_dict()

    return construir(
        realtor=realtor, evaluacion=ev, perfil_mm=perfil or None,
        resumen_tx=resumen, filas_tx=(tx or {}).get("filas"),
        mercados=mercados, ig=ig, contactos=cts or [],
        census=None, veredicto=ver, salesforce=None)


def guardar_paquete(realtor_id: str) -> dict:
    """Regenera el paquete y lo guarda si CAMBIÓ. Nunca revienta hacia fuera.

    Se llama al guardar una captura: cuando Isabella pega Transactions, lo que
    Cowork lee tiene que reflejarlo sin que nadie corra un script. Sin esto, la
    ficha se redactaría contra el paquete de antes y el `hash` diría que está
    al día -- porque nadie lo habría vuelto a calcular.

    Si el hash no cambió no se escribe: la tabla es append-only, y guardar dos
    veces el mismo contenido es contar la misma evidencia dos veces.
    """
    try:
        p = paquete_de_realtor(realtor_id)
        if not p:
            return {"guardado": False, "motivo": "el realtor no existe"}
        _c, ya, _ = leer("v_paquete_ficha",
                         "?select=hash_paquete&realtor_id=eq.%s"
                         % urllib.parse.quote(realtor_id))
        if (ya or [{}])[0].get("hash_paquete") == p["hash_paquete"]:
            return {"guardado": False, "motivo": "sin cambios",
                    "hash_paquete": p["hash_paquete"]}
        cod, det, _ = escribir("paquetes_ficha", [{
            "realtor_id": realtor_id, "version_paquete": p["version_paquete"],
            "hash_paquete": p["hash_paquete"], "paquete": p}], devolver=False)
        if cod >= 400:
            return {"guardado": False, "error": str(det)[:200]}
        return {"guardado": True, "hash_paquete": p["hash_paquete"],
                "evidencias": len(p["evidencias"])}
    except Exception as exc:  # noqa: BLE001
        # El crudo ya está guardado. Perder la captura por un error al armar el
        # paquete sería cambiar un problema chico por uno caro.
        return {"guardado": False, "error": " ".join(str(exc).split())[:200]}


def _mercados_enlazados(filas_de_captura: list) -> list[dict]:
    """Los benchmarks que la captura tomó de la biblioteca en vez de pegarlos.

    Devuelven la misma forma que un bloque pegado --`nivel`, `estado`,
    `etiqueta`, `metricas`-- para que el contraste no distinga de dónde salió.
    Que el contraste tuviera dos caminos sería la forma de que ahorrarse un
    pegado cambiara un diagnóstico.
    """
    enlaces: list[dict] = []
    for f in filas_de_captura or []:
        enlaces.extend((f.get("parseado") or {}).get("mercados_enlazados") or [])
    ids = sorted({e["mercado_id"] for e in enlaces if e.get("mercado_id")})
    if not ids:
        return []
    cod, filas, _ = leer(
        "mercados", "?select=id,nivel,estado,condado_fips,metricas,"
                    "capturado_en,rango_desde,rango_hasta&id=in.(%s)"
                    % ",".join(ids))
    if cod >= 400:
        return []
    por_id = {m["id"]: m for m in (filas or [])}
    salida = []
    for e in enlaces:
        m = por_id.get(e.get("mercado_id"))
        if not m:
            continue
        salida.append({
            "nivel": m.get("nivel"), "estado": m.get("estado"),
            "etiqueta": e.get("etiqueta"), "metricas": m.get("metricas") or {},
            "de_la_biblioteca": True,
            "capturado_en": m.get("capturado_en"),
            "rango_desde": m.get("rango_desde"),
            "rango_hasta": m.get("rango_hasta"),
        })
    return salida


def _resumen_tx_del_perfil(perfil_unido: dict) -> dict | None:
    """El resumen de Transactions del perfil unido, o `None` si no se pegó."""
    tx = (perfil_unido or {}).get("transacciones")
    if not isinstance(tx, dict) or not tx.get("filas"):
        return None
    return {"leidas": tx.get("leidas"), "completa": tx.get("completa"),
            "aviso": tx.get("aviso"), **resumen_de_transacciones(tx)}


def resumen_de_captura(filas: list[dict], perfil_unido: dict,
                       pertenece: dict | None = None) -> dict:
    """Lo que hay que poder mirar SIN abrir la base.

    Capturar 25 condados a ciegas y descubrir el problema al final es la forma
    cara de descubrirlo. Esto va en la respuesta del guardado para que cada
    captura se audite en el momento, que es cuando el volcado todavia esta en
    el portapapeles y repetirlo cuesta nada.
    """
    filas = _en_orden(filas)
    secciones = [{
        "seccion": f["parseado"]["seccion"],
        "nivel": f["parseado"].get("nivel"),
        "etiqueta": f["parseado"].get("etiqueta_geografica"),
        "orden": f["parseado"].get("orden"),
        "caracteres": len(f["texto_crudo"]),
    } for f in filas]

    geografias = []
    for f in filas:
        if f["parseado"]["seccion"] != "market_signals":
            continue
        m = f["parseado"].get("metricas") or {}
        geografias.append({
            "etiqueta": f["parseado"].get("etiqueta_geografica"),
            "nivel": f["parseado"].get("nivel"),
            "orden": f["parseado"].get("orden"),
            "campos": m.get("campos"),
            **{clave: m.get(clave) for clave, _n, _t in METRICAS_DE_VISTAZO},
        })

    # Dos geografias con el MISMO volumen es la firma del grafico rodante, que
    # muestra el numero del estado para todos los condados. Se marca cual, no
    # solo que pasa: con cuatro bloques hay que saber donde mirar.
    vistos: dict = {}
    for g in geografias:
        v = g.get("total_volume")
        if v is not None:
            vistos.setdefault(v, []).append(g["etiqueta"] or "(estado)")
    for g in geografias:
        v = g.get("total_volume")
        g["volumen_repetido"] = bool(v is not None and len(vistos.get(v, [])) > 1)

    originadores = [{
        "nombre": o.get("nombre"),
        "empresa": o.get("empresa"),
        "unidades": o.get("unidades"),
        "share": o.get("share"),
        "de_la_casa": es_de_la_casa(o),
    } for o in (perfil_unido.get("orig_buyer") or [])]

    # `share_de_la_casa` revienta a proposito sobre un fallo declarado. Aca eso
    # NO puede tumbar el guardado -- el crudo ya esta-- pero si tiene que
    # aparecer en pantalla con su razon.
    try:
        casa = share_de_la_casa(perfil_unido)
    except Exception as exc:  # noqa: BLE001
        casa = {"share": None, "base": "unidades",
                "razon": "no se pudo calcular: %s" % str(exc).split("\n")[0]}

    return {
        "secciones": secciones,
        "geografias": geografias,
        "volumenes_repetidos": [nombres for nombres in vistos.values()
                                if len(nombres) > 1],
        "originadores": originadores,
        "share_de_la_casa": casa,
        # A QUIEN quedo pegada, y si el volcado lo respalda. Va arriba en la
        # confirmacion: es lo primero que hay que poder mirar, porque es lo
        # unico que no se puede deducir mirando el resto.
        "pertenencia": pertenece,
        "realtor_id": (filas[0].get("realtor_id") if filas else None)
                      or (filas[0]["parseado"].get("realtor_id")
                          if filas else None),
        "fallos": perfil_unido.get("fallos") or [],
        # El grano de la operacion, cuando esta. `None` --y no un resumen en
        # cero-- cuando la pestaña no se pego: la ficha tiene que poder decir
        # «falta Transactions» y no «0 compras cash», que son cosas opuestas.
        "transacciones": _resumen_tx_del_perfil(perfil_unido),
        "perfil": {
            "nombre": perfil_unido.get("nombre"),
            "buyer_units": perfil_unido.get("buyer_units"),
            "telefono_directo": (perfil_unido.get("contacto")
                                 or {}).get("telefono_directo"),
            # Para poder decir «5 de 19 sin identificar» sin restar en la
            # pantalla: el numerador viaja, y la resta solo se muestra como lo
            # que falta por saber, nunca como cash.
            "compras_con_originador": sum(
                o.get("unidades") or 0
                for o in (perfil_unido.get("orig_buyer") or [])) or None,
            "los_buyer": perfil_unido.get("los_buyer"),
            "los_seller": perfil_unido.get("los_seller"),
            "tpo_pct": perfil_unido.get("tpo_pct"),
            "lenders": len(perfil_unido.get("tabla_lenders") or []),
            "loan_mix": (perfil_unido.get("loan_mix_buyer") or {}).get("filas"),
            "cobertura_mix": (perfil_unido.get("loan_mix_buyer")
                              or {}).get("cobertura"),
        },
    }


class _LectorPostgREST:
    """Lo que `motor.reevaluacion` necesita, hablando PostgREST.

    Es una clase de cuatro lineas a proposito: el modulo del motor no tiene que
    saber si detras hay un driver, una conexion directa o HTTP. La consola le
    pasa otro adaptador y el codigo del calculo es el mismo.
    """

    leer = staticmethod(leer)
    escribir = staticmethod(escribir)


def _cajas_con_overview(cajas, tipos):
    """El resumen, con las cajas que el Overview ya resolvió marcadas."""
    marcar_del_overview(cajas, tipos)
    return resumen_de_cajas(cajas)


def leer_overview(d: dict) -> tuple[int, dict]:
    """El Overview -> el estado y los condados, para que aparezcan las cajas.

    No guarda nada. Es el paso 1 de la captura por cajas: se pega el Overview,
    se ve QUE se detectó, se corrige a mano lo que haga falta, y recién
    entonces aparecen las cajas de Market Insight con su nombre puesto.

    Si no encuentra la tabla lo dice en una línea y deja agregarlos a mano. Un
    parser que devuelve una lista vacía sin explicar por qué obliga a adivinar
    si el texto estaba mal o la tabla no existe.
    """
    from captura.parser_mm import _condados, parsear_perfil

    texto = str(d.get("overview") or "")
    if not texto.strip():
        return 400, {"error": "La caja del Overview está vacía."}

    filas = _condados(texto)
    perfil, error = None, None
    try:
        perfil = parsear_perfil(texto)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:200]

    estado_detectado = None
    for c in filas:
        if c.get("estado"):
            estado_detectado = c["estado"]
            break

    return 200, {
        "estado": estado_detectado,
        "estado_nombre": ESTADOS.get(estado_detectado or ""),
        "condados": [{"nombre": c["nombre"], "tipo": c.get("tipo"),
                      "es_condado": c.get("es_condado", True),
                      "estado": c.get("estado"), "unidades": c.get("unidades")}
                     for c in filas],
        "nombre": (perfil or {}).get("nombre"),
        "buyer_units": (perfil or {}).get("buyer_units"),
        "ventana_meses": (perfil or {}).get("ventana_meses"),
        "aviso": (None if filas else
                  "No encontré la tabla «View Counties»: agregá los condados a "
                  "mano con el botón de abajo."),
        "error_parser": error,
    }


def guardar(d: dict) -> tuple[int, dict]:
    realtor_id = (d.get("realtor_id") or "").strip()
    sf_lead_id = (d.get("sf_lead_id") or "").strip() or None
    mmi_agent_id = (d.get("mmi_agent_id") or "").strip() or None

    # `CA`, `California` y `CALIFORNIA` entraron como tres etiquetas distintas
    # del mismo mercado. En la biblioteca eso son tres geografias.
    estado_crudo = (d.get("estado") or "").strip()
    estado = normalizar_estado(estado_crudo)
    if estado_crudo and not estado:
        return 400, {"error": (
            "No reconozco %r como estado. Va el codigo de dos letras o el "
            "nombre completo (CA o California).\n"
            "\n"
            "No lo guardo tal cual a proposito: `CA`, `California` y "
            "`CALIFORNIA` ya entraron como tres mercados distintos en la "
            "biblioteca, y la unica pista de que son el mismo es mirarlos uno "
            "al lado del otro." % estado_crudo),
            "conocidos": sorted(ESTADOS)}

    # LA VENTANA DE MODEL MATCH · el mismo problema que `Set Location`.
    #
    # `Set Date Range:` sale en el texto SIN valor, porque vive en un select y
    # Ctrl+A no lo copia. Sin ella no se puede anualizar la produccion, y la
    # produccion anualizada del lado comprador es la que manda para la
    # compuerta -- nueve unidades en catorce meses son 7,7 al año, no nueve.
    #
    # Se declara una vez por captura: el rango es del perfil entero.
    # Y se guarda SI EL VALOR ERA EL DE FABRICA o alguien lo cambió: un 14
    # declarado y un 14 por descuido son el mismo número y no valen lo mismo.
    # Model Match trae 14 de fábrica y casi nadie lo toca.
    ventana = d.get("ventana_meses")
    try:
        ventana = int(ventana) if ventana not in (None, "") else None
    except (TypeError, ValueError):
        ventana = None
    ventana_confirmada = bool(d.get("ventana_confirmada"))
    if ventana is not None and not (1 <= ventana <= 60):
        return 400, {"error": (
            "La ventana de Model Match es %r meses. Va entre 1 y 60: es el "
            "`Set Date Range` del perfil, que no viaja en el texto pegado "
            "porque vive en un desplegable." % ventana)}

    # UNA SOLA CAJA · el volcado trae sus propios cortes. Siete pegados por
    # realtor son siete oportunidades de poner algo en la caja equivocada, y
    # sobre 25 capturas son 175.
    volcado = (d.get("volcado") or "").strip()
    if volcado:
        try:
            s = separar_volcado(volcado)
        except ProtocoloInvalido as exc:
            return 400, {"error": str(exc)}
        overview = s["overview"]
        ms = s["market_signals"]
        d = {**d, "originators": s["originators"], "lenders": s["lenders"]}
    else:
        overview = d.get("overview") or ""
        ms = [str(x) for x in (d.get("market_signals") or [])]

    # ── NINGUNA CAPTURA DE PRUEBA ENTRA A PRODUCCION ────────────────────────
    #
    # El lote 8dd94e61 llego asi: un script de Playwright verificando la
    # pantalla de captura corrio contra el WSGI LOCAL -- que usa las
    # credenciales de produccion-- y toco «Guardar». Quedo un Overview de
    # «Fulana de Tal» con los condados de Ochoa pegado al realtor_id de Crespo,
    # vigente, compitiendo con su captura real.
    #
    # No falto una advertencia: falto que el servidor pudiera decir que no. Por
    # eso la marca va en el PAYLOAD y la rechaza la API, no un comentario en el
    # script. Un script de prueba que manda `fixture: true` no puede escribir
    # aunque apunte a produccion por error.
    if d.get("fixture") or d.get("es_prueba"):
        return 400, {"error": (
            "Esta captura viene marcada como fixture y la base de producción "
            "no las acepta. Si estás verificando la pantalla, apuntá a una "
            "base de prueba."), "fixture": True}

    # Y el nombre que usan todos los fixtures de este repo.
    if "Fulana de Tal" in (d.get("overview") or ""):
        return 400, {"error": (
            "El Overview es el de «Fulana de Tal», que es el fixture de las "
            "pruebas. No se guarda en producción."), "fixture": True}

    if not realtor_id:
        return 400, {"error": "falta realtor_id: se parte del realtor"}
    if not overview.strip():
        return 400, {"error": "el Overview esta vacio"}
    if not (sf_lead_id or mmi_agent_id):
        return 400, {"error": (
            "Este realtor no tiene Lead ID de Salesforce, asi que hace falta "
            "el MMI Agent ID para poder pegarle la captura. Esta en el perfil "
            "de Model Match.")}

    # ── el volcado repetido ──────────────────────────────────────────────────
    # El mismo perfil entro dos veces con un minuto de diferencia. Cada copia
    # cuenta como una captura mas en la biblioteca de geografias.
    # Transactions entra en la huella, y se busca en las DOS vias por las que
    # puede llegar: el campo suelto y la caja de la pantalla. Sin esto, volver
    # a capturar el mismo Overview para AGREGAR la pestaña Transactions --que
    # es exactamente el flujo: primero el perfil, despues la tabla-- salia como
    # duplicado y se rechazaba.
    tx_para_huella = (d.get("transacciones") or "").strip() or next(
        (str(c.get("texto") or "") for c in (d.get("cajas") or [])
         if c.get("tipo") == "transacciones"), "")
    partes_huella = [overview] + list(ms) + [d.get("originators") or "",
                                             d.get("lenders") or "",
                                             tx_para_huella]
    huella = hashlib.sha256(
        "\n\u0000\n".join(partes_huella).encode("utf-8")).hexdigest()
    if not d.get("forzar"):
        cod_h, previas, _ = leer(
            "capturas_modelmatch",
            "?select=capturado_en&hash_volcado=eq.%s&realtor_id=eq.%s"
            "&order=capturado_en.desc&limit=1"
            % (huella, urllib.parse.quote(realtor_id)))
        if cod_h < 400 and previas:
            return 409, {
                "error": (
                    "Este volcado ya esta guardado, identico, desde %s.\n"
                    "\n"
                    "No lo duplico solo: cada copia cuenta como una captura "
                    "mas en la biblioteca de geografias, y el conteo por "
                    "mercado sale inflado sin que se note.\n"
                    "\n"
                    "Si de verdad querias volver a capturarlo -- porque paso "
                    "tiempo y los numeros cambiaron-- mandalo otra vez con "
                    "`forzar`." % previas[0].get("capturado_en")),
                "duplicado_de": previas[0].get("capturado_en"),
                "hash_volcado": huella}

    condados = [n for n, _ in condados_del_overview(overview)]
    avisos_de_cajas: list[str] = []

    # ── CAPTURA POR CAJAS ───────────────────────────────────────────────────
    # Si la pantalla manda `cajas`, el condado lo define LA CAJA. El camino
    # viejo --etiquetar por posicion-- se conserva para las capturas que ya
    # estan en vuelo, pero exige `1 + N` bloques exactos y rechaza la captura
    # ENTERA cuando Model Match muestra 5 condados en el Overview y 3 en Market
    # Insight. Un dato que falta hacia perder los cuatro que si estaban.
    cajas: list = []
    sin_market_insight: list[str] = []
    if d.get("cajas"):
        cajas = cajas_desde(d)
        bloques = []
        orden = 0
        for c in cajas:
            if c.tipo not in ("estado", "condado") or c.estado != "leido":
                continue
            bloques.append(Bloque(
                seccion="market_signals", texto=c.texto, orden=orden,
                nivel=("estado" if c.tipo == "estado" else "condado"),
                etiqueta=(estado if c.tipo == "estado" else c.etiqueta)))
            orden += 1
        sin_market_insight = condados_sin_market_insight(condados, cajas)
        # Las cajas que la pantalla resolvió desde la biblioteca NO son «falta
        # capturar»: su benchmark ya existe y el realtor queda enlazado a esa
        # fila. Se sacan de la lista de faltantes por el mismo camino que las
        # que vinieron en el Overview.
        for m in (d.get("mercados_enlazados") or []):
            eti = (m.get("etiqueta") or "").strip()
            for c in cajas:
                if (c.tipo in ("estado", "condado") and c.estado == "sin_pegar"
                        and (c.etiqueta or "").strip() == eti):
                    c.estado = "del_overview"
                    c.aviso = ("ya está en la biblioteca, capturado el %s: no "
                               "hace falta pegarlo"
                               % str(m.get("capturado_en") or "")[:10])
        enlazadas = {(m.get("etiqueta") or "").strip()
                     for m in (d.get("mercados_enlazados") or [])}
        sin_market_insight = [c for c in sin_market_insight
                              if c.strip() not in enlazadas]
        for c in cajas:
            if c.aviso:
                avisos_de_cajas.append(c.aviso)
        for nombre in sin_market_insight:
            avisos_de_cajas.append(
                "Model Match no muestra Market Insight de %s: se guarda como "
                "«no disponible» y no bloquea la captura." % nombre)
        # Las dos casillas del perfil viajan al parser por el mismo camino que
        # el resto, para que el veredicto las vea.
        for c in cajas:
            if c.tipo == "originators" and c.estado == "vacio_declarado":
                d = {**d, "sin_originadores_declarado": True}
            if c.tipo == "lenders" and c.estado == "vacio_declarado":
                d = {**d, "sin_lenders_declarado": True}
            # La caja de Transactions viaja por el mismo sitio que las demas:
            # un campo del payload que el resto del guardado ya sabe leer.
            if c.tipo == "transacciones" and c.estado == "leido":
                d = {**d, "transacciones": c.texto}
            if c.tipo == "transacciones" and c.estado == "vacio_declarado":
                d = {**d, "sin_transacciones_declarado": True}
    else:
        try:
            bloques = etiquetar_por_posicion(ms, condados)
        except ProtocoloInvalido as exc:
            return 400, {"error": str(exc), "condados": condados}

    # La ficha se lee ACA y no mas abajo porque el parser de Transactions la
    # necesita: el LADO de cada operacion sale de en que columna de agente
    # aparece su nombre, y sin el nombre no hay lado que derivar.
    _c_r, fichas, _ = leer(
        "realtors", "?select=nombre_completo,email_principal,brokerage,estado"
                    "&id=eq.%s" % urllib.parse.quote(realtor_id))
    ficha_del_realtor = (fichas or [{}])[0]

    ahora = dt.datetime.now(dt.timezone.utc).isoformat()
    lote = str(uuid.uuid4())
    # Los avisos de las cajas se calcularon antes de abrir el lote, asi que
    # entran aca: un aviso que se calcula y no se muestra no existe.
    avisos: list[str] = list(avisos_de_cajas)
    #: Cajas cuyo contenido no hizo falta pegar porque vino en el Overview.
    cajas_del_overview: list[str] = []
    filas: list[dict] = []

    def _parsear(funcion, texto, etiqueta_error):
        """Derivar NUNCA puede impedir guardar.

        Si el parser revienta con un texto que no vio antes, el crudo se guarda
        igual y el error queda en `parseado`. Es lo contrario de lo que hacia
        antes: `parsear_perfil` corria fuera de cualquier try, asi que una
        excepcion tiraba la peticion entera y se perdia el volcado.

        Y ese volcado no se puede volver a pedir: la prueba de Model Match vence
        el 1 de octubre. Un parser que falla se arregla y se re-parsea gratis;
        un perfil que no se capturo no vuelve.
        """
        try:
            return funcion(texto), None
        except Exception as exc:  # noqa: BLE001
            aviso = ("el parser fallo en %s (%s: %s). El TEXTO SE GUARDO igual "
                     "y se puede re-parsear sin volver a capturar."
                     % (etiqueta_error, type(exc).__name__, str(exc)[:160]))
            avisos.append(aviso)
            return {"estado_del_parser": "fallo", "error": str(exc)[:400]}, exc

    def agregar(seccion, texto, *, alcance, nivel=None, etiqueta=None,
                orden=0, extra=None):
        # Guarda REDUNDANTE a proposito: `guardar` ya devuelve 400 sin
        # realtor_id, arriba. Pero la columna `realtor_id` estuvo NULL en las
        # 60 capturas durante todo el proyecto porque nadie la escribia, y una
        # captura no pegada a nadie no sirve para nada de lo que existe. Que
        # reviente al construir la fila y no al leerla tres semanas despues.
        if not realtor_id:
            raise ValueError(
                "captura sin realtor_id: no se guarda a ciegas. El crudo es "
                "inutil si no se sabe de quien es.")
        filas.append({
            "upload_batch_id": lote, "uploaded_at": ahora, "alcance": alcance,
            # En COLUMNA y tambien en `parseado`. La columna es la que puede
            # llevar NOT NULL y un indice; el jsonb es el que ya leen
            # `capturas_que_mandan` y `/api/capturas`. Escribir las dos y no
            # migrar una a la otra evita el rato en que la mitad del codigo
            # lee un sitio y la otra mitad el otro.
            "realtor_id": realtor_id,
            "estado": estado, "hash_volcado": huella,
            "condado_fips": None,   # el crosswalk nombre->FIPS todavia no
            # La etiqueta va en COLUMNA, no solo dentro del jsonb: si dos
            # bloques de mercado se ven identicos en la base, la biblioteca no
            # puede saber cual es cual y el error no da ningun aviso.
            "geografia_etiqueta": etiqueta,
            "geografia_nivel": nivel,
            "sf_lead_id": sf_lead_id, "mmi_agent_id": mmi_agent_id,
            "texto_crudo": texto,
            "parseado": {"seccion": seccion, "orden": orden, "nivel": nivel,
                         "etiqueta_geografica": etiqueta,
                         "condados_del_overview": condados,
                         "realtor_id": realtor_id, **(extra or {})},
            "version_parser": "parser_mm 2026-09-22", "capturado_en": ahora,
        })

    perfil, _ = _parsear(parsear_perfil, overview, "el Overview")
    # La ventana declarada gana sobre la del texto, que casi nunca esta.
    if isinstance(perfil, dict) and ventana:
        perfil["ventana_meses"] = ventana
        perfil["ventana_declarada"] = True
        # `de_fabrica` cuando nadie tocó el campo: es el 14 que Model Match
        # trae por defecto y que casi nadie cambia. Sigue siendo usable, pero
        # el que lo lea sabe que nadie lo miró.
        perfil["ventana_origen"] = ("confirmada" if ventana_confirmada
                                    else "de_fabrica")
        if perfil.get("buyer_units"):
            perfil["buyside_anualizado"] = round(
                perfil["buyer_units"] / ventana * 12.0, 1)
    elif isinstance(perfil, dict) and not perfil.get("ventana_meses"):
        avisos.append(
            "sin ventana de Model Match: `Set Date Range` no viaja en el texto "
            "pegado. Sin ella no se puede anualizar la producción, que es el "
            "número que manda para la compuerta.")
    # Los mercados que NO se pegaron porque ya estaban en la biblioteca, con el
    # id de la fila a la que queda enlazado este realtor. Va en el `parseado`
    # del Overview y no en una tabla nueva: el enlace es del lote, y así se
    # audita en el mismo sitio donde se audita todo lo demás de la captura.
    #
    # El contraste de mercado lo lee de aquí, así que un benchmark tomado de la
    # biblioteca produce el MISMO contraste que uno pegado. Si produjera otro,
    # ahorrar el pegado sería cambiar el resultado.
    enlazados = [
        {"etiqueta": (m.get("etiqueta") or "").strip(),
         "nivel": m.get("nivel"), "condado_fips": m.get("condado_fips"),
         "mercado_id": m.get("mercado_id"),
         "capturado_en": m.get("capturado_en"),
         "dias_al_enlazar": m.get("dias"), "campos": m.get("campos")}
        for m in (d.get("mercados_enlazados") or [])
        if m.get("mercado_id")]
    agregar("overview", overview, alcance="perfil",
            extra={"perfil": perfil,
                   "mercados_enlazados": enlazados or None})

    for b in bloques:
        # El bloque del estado no tiene nombre de condado, asi que lleva el
        # codigo del estado como etiqueta. Sin esto quedaba NULL, y una fila de
        # mercado sin etiqueta es justo la que no se puede distinguir de otra
        # al mirar la tabla.
        etiqueta = b.etiqueta or (estado if b.nivel == "estado" else None)
        metricas, _ = _parsear(
            parsear_mercado, b.texto,
            "Market Signals de %s" % (etiqueta or "el estado"))
        agregar("market_signals", b.texto, alcance="mercado", nivel=b.nivel,
                etiqueta=etiqueta, orden=b.orden,
                extra={"metricas": metricas})

    originators = d.get("originators") or None
    if originators:
        p, fallo = _parsear(parsear_perfil, originators, "Originators")
        if not fallo:
            avisos.extend(detectar_inversion(p.get("tab_orig") or []))
        agregar("originators", originators, alcance="perfil",
                extra={"perfil": p})
    # El aviso de los originadores se decide DESPUES de unir el perfil, porque
    # `orig_buyer` vive en el Overview y aca todavia no se sabe si vino.
    sin_pestana_originators = not originators
    if d.get("lenders"):
        # SE PARSEA. Antes se guardaba el texto y nada mas, asi que `tpo_pct` y
        # `tabla_lenders` salian vacios aunque la pestaña estuviera pegada --
        # el parser los saca perfectos de ese mismo texto, solo que nadie lo
        # llamaba. Es lo que la guarda de abajo existe para que no vuelva a
        # pasar en silencio.
        pl, _fallo = _parsear(parsear_perfil, d["lenders"], "Lenders")
        agregar("lenders", d["lenders"], alcance="perfil",
                extra={"perfil": pl})

    # ── LA PESTAÑA TRANSACTIONS ─────────────────────────────────────────────
    #
    # Va con `alcance="perfil"` igual que Originators y Lenders: es un hecho
    # del agente, no de un mercado. Lo que la distingue es `seccion`.
    #
    # Y el parseado entra como un FRAGMENTO DE PERFIL --`{"transacciones": ...}`
    # -- porque `unir_perfiles` es lo que lee la re-evaluacion, y solo mira
    # `parseado.perfil`. Guardarlo en otra llave del jsonb lo dejaria en la
    # base y fuera del motor, que es la forma en que este proyecto ya perdio
    # Instagram durante semanas.
    tx_parseado = None
    texto_tx = (d.get("transacciones") or "").strip()
    if texto_tx:
        # EL NOMBRE DE LA CAPTURA, no el del libro. El libro dice «XOCHIL
        # ESCOBAR» y Model Match «Xochil Wendy Escobar»: sus 37 operaciones
        # quedaron sin lado, y sin que nada fallara, porque «sin lado» es un
        # estado legítimo. Al capturar se confirmó que es la misma persona, así
        # que la forma de la captura manda.
        nombre_del_realtor = ((perfil or {}).get("nombre")
                              if isinstance(perfil, dict) else None)
        tx_parseado, _fallo_tx = _parsear(
            lambda t: parsear_transacciones(t, realtor=nombre_del_realtor,
                                            capturado_en=ahora),
            texto_tx, "Transactions")
        if isinstance(tx_parseado, dict) and tx_parseado.get("nombre_usado") \
                != nombre_del_realtor:
            avisos.append("Transactions · %s"
                          % tx_parseado.get("por_que_ese_nombre"))
        # EL CRUDO DE ESTA SECCION VA REDACTADO, y es la unica que lo hace.
        #
        # El pegado trae el nombre del comprador, el del vendedor y la calle de
        # cada operacion. De nada sirve que `pacs.transacciones` no tenga esas
        # columnas si el texto entero queda al lado en `texto_crudo`, que es
        # una columna que se lee, se exporta y se mira. Ver `crudo_redactado`.
        agregar("transacciones", crudo_redactado(texto_tx), alcance="perfil",
                extra={"perfil": {"transacciones": tx_parseado},
                       "crudo_redactado": True,
                       "por_que_redactado": (
                           "el pegado de Transactions trae nombres de "
                           "compradores y vendedores y la calle de cada "
                           "vivienda (ECOA Regulation B)")})
        if isinstance(tx_parseado, dict) and tx_parseado.get("aviso"):
            avisos.append("Transactions · " + tx_parseado["aviso"])
        if isinstance(tx_parseado, dict) and tx_parseado.get("sin_lado"):
            avisos.append(
                "Transactions · %d operaciones sin lado: el nombre del agente "
                "no coincide con ninguna columna de agente. Se guardan igual y "
                "no cuentan ni como compra ni como venta."
                % tx_parseado["sin_lado"])

    # ── lo que estaba en el texto y no llego al dict ─────────────────────────
    # Un `[]` dice dos cosas a la vez: "este agente no trabaja con nadie" y "el
    # parser no supo leerlo". La primera es un dato y la segunda es un error, y
    # sin esto se guardan identicas.
    perfiles = [f["parseado"].get("perfil") for f in filas
                if f["parseado"]["seccion"] in ("overview", "originators",
                                                "lenders")]
    perfil_unido = unir_perfiles([p for p in perfiles if isinstance(p, dict)])

    # Las dos casillas viajan DENTRO del perfil, que es lo que lee el veredicto.
    # `orig_buyer = []` con casilla y sin casilla son el mismo dato y dos
    # veredictos opuestos; la casilla es el unico sitio donde queda constancia
    # de que alguien miro.
    # ── EL AVISO DE LOS ORIGINADORES, con el perfil ya unido ────────────────
    #
    # Decia «sin bloque de Originators: no se puede detectar si trabaja con
    # Everett» sobre una captura que SI traia el reparto. `Buyer Side
    # Relationships` vive en el OVERVIEW, no en la pestaña Originators.
    #
    # La primera captura real --4 originadores, 14 de 19 unidades, ninguno de
    # la casa-- salio con veredicto `ok` y con ese aviso diciendo lo contrario
    # al lado. Un aviso que contradice al veredicto es peor que no tenerlo:
    # obliga a decidir a cual creerle, y la respuesta no esta en la pantalla.
    reparto_overview = perfil_unido.get("orig_buyer") or []
    if sin_pestana_originators and reparto_overview:
        con_orig = sum(o.get("unidades") or 0 for o in reparto_overview)
        total_compras = perfil_unido.get("buyer_units")
        detalle = ""
        if total_compras and con_orig and total_compras > con_orig:
            detalle = (" · %g de %g compras sin originador identificado"
                       % (total_compras - con_orig, total_compras))
        avisos.append(
            "Originators leída desde el Overview: %d originadores repartidos "
            "por unidades%s" % (len(reparto_overview), detalle))
        cajas_del_overview.append("originators")
    elif sin_pestana_originators and not d.get("sin_originadores_declarado"):
        avisos.append(
            "sin reparto de originadores: no se puede saber si trabaja con "
            "Everett Financial. Si Model Match no se los muestra a este "
            "agente, marcá la casilla «Model Match no muestra originadores».")

    if d.get("sin_originadores_declarado"):
        perfil_unido["sin_originadores_declarado"] = True
        perfil_unido["declarado_por"] = "pantalla de captura"
        avisos.append(
            "Declaraste que Model Match no muestra originadores: el veredicto "
            "queda en `ok` con 0 operaciones con la casa, no en pendiente.")
    if d.get("sin_lenders_declarado"):
        perfil_unido["sin_lenders_declarado"] = True

    # ── LA FICHA DICE «FALTA TRANSACTIONS», Y NO CALCULA CASH POR DIFERENCIA ─
    #
    # Sin la pestaña, las compras sin originador identificado son una AUSENCIA
    # y no un dato: pueden ser cash o pueden ser un originador que Model Match
    # no muestra. Restar «compras - compras con originador» y llamarlo cash es
    # inventarse una categoria que nadie midio y que sale con la misma cara que
    # una medida.
    if not texto_tx and not d.get("sin_transacciones_declarado"):
        sin_orig = None
        total_compras = perfil_unido.get("buyer_units")
        con_orig = sum(o.get("unidades") or 0
                       for o in (perfil_unido.get("orig_buyer") or []))
        if total_compras and con_orig and total_compras > con_orig:
            sin_orig = total_compras - con_orig
        avisos.append(
            "falta Transactions%s. Sin esa pestaña no se sabe cuáles de sus "
            "compras fueron cash y cuáles tienen un originador que Model Match "
            "no muestra, y eso NO se calcula por diferencia."
            % ("" if sin_orig is None
               else " · %g de %g compras sin originador identificado"
                    % (sin_orig, total_compras)))

    for f in perfil_unido.get("fallos") or []:
        avisos.append(
            "FALLO DE LECTURA · la seccion `%s` esta en el texto y `%s` salio "
            "vacio. Es %s. El crudo esta guardado: se arregla el parser y se "
            "re-deriva sin volver a capturar."
            % (f.get("seccion"), f.get("campo"), f.get("por_que_importa")))

    # ── UNA SECCION CON TEXTO QUE NO PRODUCE NINGUN CAMPO ───────────────────
    # Es la guarda que faltaba. El bloque de Lenders se guardaba con 358
    # caracteres y cero campos, y nada avisaba: `fallos_de_seccion` no corria
    # porque la seccion ni se parseaba, asi que la guarda de secciones vacias
    # no tenia nada sobre lo que fallar.
    #
    # Texto guardado y cero campos extraidos es un fallo, siempre. O el parser
    # no supo, o nadie lo llamo -- y las dos cosas hay que verlas.
    for f in filas:
        p = f["parseado"]
        if p.get("seccion") == "market_signals":
            continue
        n_campos = _campos_de_perfil(p.get("perfil"))
        if len(f["texto_crudo"]) > 100 and n_campos == 0:
            avisos.append(
                "SECCION SIN EXTRAER · `%s` se guardó con %d caracteres y no "
                "produjo ningún campo. O el parser no supo leerla, o no se "
                "llamó sobre ella. El crudo está guardado y se re-deriva."
                % (p.get("seccion"), len(f["texto_crudo"])))

    # Y la base del reparto, MEDIDA contra sus propias filas.
    for campo, base in (perfil_unido.get("wallet_share_base") or {}).items():
        if (base or {}).get("coincide") is False:
            avisos.append(
                "la base de `%s` no es la esperada: se esperaba %s y medida "
                "contra sus propias filas da %s. La exclusion por "
                "no-canibalizacion se decide por unidades, asi que esto la "
                "bloquea." % (campo, base.get("esperada"), base.get("medida")))

    # TRAMPA 2 · conforming/jumbo con su denominador. Si el suyo es mayor que
    # las unidades del mercado, el bloque se leyo cruzado con otra geografia.
    for f in filas:
        if f["parseado"]["seccion"] != "market_signals":
            continue
        c = (f["parseado"].get("metricas") or {}).get("conforming") or {}
        donde = f["parseado"].get("etiqueta_geografica") or "el estado"
        if c.get("mayor_que_el_mercado"):
            avisos.append(
                "en %s, el denominador de conforming/jumbo (%s) es mayor que "
                "las unidades del mercado (%s): el bloque parece leido cruzado "
                "con otra geografia."
                % (donde, c.get("denominador_propio"),
                   c.get("unidades_del_mercado")))
        if c.get("cuadra") is False:
            avisos.append(
                "en %s, conforming + jumbo (%s) no suman su propio denominador "
                "(%s)." % (donde, c.get("suma_de_tramos"),
                           c.get("denominador_propio")))

    # TRAMPA 0 · ¿el volcado es de la persona que estaba abierta en la ficha?
    # Se abre a Fulano, se pega el volcado de Mengano, y la captura queda
    # colgada de Fulano sin que falle nada. Es peor que una captura huerfana:
    # una huerfana no sirve para nada y se nota, esta sirve para lo que no es.
    # El Overview trae el nombre y el email del agente, asi que hay con que.
    pertenece = comprobar(perfil_unido, ficha_del_realtor)
    if pertenece["veredicto"] == "discrepa":
        avisos.append(
            "EL VOLCADO NO PARECE DE ESTA PERSONA · %s. Si te equivocaste de "
            "ficha, retira el lote y vuelve a capturar: el diagnostico se "
            "calcularia con la produccion de otro." % pertenece["por"])
    elif pertenece["veredicto"] == "no_consta":
        avisos.append(
            "no se pudo comprobar que el volcado sea de esta persona: %s"
            % pertenece["por"])

    # TRAMPA 1 · las geografias tienen que dar volumenes distintos.
    vols = [(f["parseado"].get("metricas") or {}).get("total_volume")
            for f in filas if f["parseado"]["seccion"] == "market_signals"]
    vols = [v for v in vols if v is not None]
    if len(vols) > 1 and len(set(vols)) == 1:
        avisos.append(
            "las %d geografias dieron el MISMO volumen. Eso es el Rolling "
            "Monthly Performance, que no respeta el filtro de ubicacion: hay "
            "que copiar la seccion Market Overview." % len(vols))

    cod, _, _ = escribir("upload_batch", [{
        "id": lote, "fuente": "modelmatch", "archivo": "mesa de trabajo",
        "uploaded_at": ahora, "es_vigente": True,
        "filas_esperadas": len(filas),
        "nota": "captura desde la ficha · realtor_id=%s · condados=%s"
                % (realtor_id, ", ".join(condados) or "ninguno"),
    }], devolver=False)
    if cod >= 400:
        return 500, {"error": "no se pudo abrir el lote"}

    cod, datos, _ = escribir("capturas_modelmatch", filas, devolver=False)
    if cod >= 400:
        return cod, {"error": "no se guardo", "detalle": datos}

    # ── EL GRANO DE LA OPERACION ─────────────────────────────────────────────
    # Va DESPUES del crudo y no puede tumbar la captura: el texto ya esta
    # guardado y las filas se re-derivan de el. Al reves no.
    transacciones_escritas = 0
    if isinstance(tx_parseado, dict) and tx_parseado.get("filas"):
        try:
            filas_tx = _filas_de_transacciones(tx_parseado, realtor_id, lote,
                                               ahora)
        except ValueError as exc:
            filas_tx = []
            avisos.append("FALLO ECOA · " + str(exc))
        if filas_tx:
            cod_t, det_t, _ = escribir("transacciones", filas_tx,
                                       devolver=False)
            if cod_t >= 400:
                avisos.append(
                    "el texto de Transactions se guardó, pero las %d "
                    "operaciones no entraron en pacs.transacciones: %s. El "
                    "veredicto sigue leyéndolas del jsonb de la captura."
                    % (len(filas_tx), str(det_t)[:200]))
            else:
                transacciones_escritas = len(filas_tx)

    # ── LA BIBLIOTECA DE MERCADOS ────────────────────────────────────────────
    # Va DESPUES del crudo, por lo mismo que los contactos: si falla, el
    # volcado ya esta y se re-deriva. Pero su fallo se declara, no se calla.
    mercados, fallos_promocion = promover_a_mercados(
        filas, lote, ahora,
        ventana_meses=(perfil_unido.get("ventana_meses") if
                       isinstance(perfil_unido, dict) else None))
    for f in fallos_promocion:
        avisos.append("FALLO DE PROMOCION · " + f)

    promovidos = 0
    if mercados:
        cod_m, det_m, _ = escribir("mercados", mercados, devolver=False)
        if cod_m >= 400:
            avisos.append(
                "FALLO DE PROMOCION · el crudo se guardo, pero los %d bloques "
                "de mercado no entraron en la biblioteca: %s. Ningun contraste "
                "de Model Match puede correr sobre ellos hasta que entren."
                % (len(mercados), str(det_m)[:200]))
        else:
            promovidos = len(mercados)

    # La guarda que faltaba: metricas parseadas SIN fila en la biblioteca es un
    # fallo declarado, no un silencio. Es lo que dejo `pacs.mercados` en cero
    # con cuatro bloques ya parseados y nadie enterado.
    con_metricas = sum(
        1 for f in filas
        if f["parseado"].get("seccion") == "market_signals"
        and (f["parseado"].get("metricas") or {}).get("campos", 0)
        >= MINIMO_CAMPOS_PARA_PROMOVER)
    if con_metricas and promovidos < con_metricas:
        avisos.append(
            "FALLO DE PROMOCION · %d bloques traen metricas parseadas y solo "
            "%d entraron en `pacs.mercados`. Los que faltan existen en la "
            "captura y no en la biblioteca, asi que ningun contraste los ve."
            % (con_metricas, promovidos))

    # Los contactos van DESPUES del crudo y no pueden tumbar la captura: si
    # fallan, el volcado ya esta guardado y se pueden re-derivar de el. Al
    # reves no: la prueba de Model Match vence el 1 de octubre.
    contactos = _contactos_de(perfil_unido, realtor_id, lote, ahora)
    nuevos, ya_estaban = [], []
    if contactos:
        # Cuales YA estaban, para poder decir cuantos son nuevos en vez de
        # informar tres cuando dos ya existian.
        _cy, previos, _ = leer(
            "contactos",
            "?select=canal,valor&realtor_id=eq.%s&fuente=eq.%s"
            % (urllib.parse.quote(realtor_id),
               urllib.parse.quote(FUENTE_CONTACTOS)))
        vistos = {(p.get("canal"), p.get("valor")) for p in (previos or [])}
        nuevos = [c for c in contactos if (c["canal"], c["valor"]) not in vistos]
        ya_estaban = [c for c in contactos if (c["canal"], c["valor"]) in vistos]

        # `on_conflict` nombra el unique: sin el, `ignore-duplicates` no
        # aplica y un repetido tira los tres.
        cod_c, det_c, _ = escribir(
            "contactos", contactos, devolver=False, sin_duplicar=True,
            en_conflicto="realtor_id,canal,valor,fuente")
        if cod_c >= 400:
            avisos.append(
                "el crudo se guardo, pero los %d datos de contacto (%s) no "
                "entraron en pacs.contactos: %s"
                % (len(contactos), ", ".join(c["canal"] for c in contactos),
                   str(det_c)[:200]))
            contactos, nuevos, ya_estaban = [], [], []

    # ── VOLVER A EVALUAR, SOLO A ESTE REALTOR ───────────────────────────────
    #
    # Sin esto la captura no movia el diagnostico: entraba el perfil nuevo, se
    # promovian los mercados, cambiaba el veredicto -- y `dolor_primario`
    # seguia siendo el de la corrida anterior, calculado sin Model Match. La
    # pantalla mostraba las dos cosas juntas y nada decia que no se
    # correspondian.
    #
    # Va DESPUES de todo lo demas y en su propio try: el crudo ya esta
    # guardado, y perder la captura por un error al recalcular seria cambiar un
    # problema chico por uno caro.
    # Va por PostgREST, igual que todo lo demas de esta ruta. La primera
    # version usaba psycopg y conexion directa, que en Vercel no existe -- ni
    # queremos que exista: serian credenciales de base en una funcion publica.
    reevaluacion = None
    try:
        from motor.reevaluacion import reevaluar as _reevaluar
        reevaluacion = _reevaluar(realtor_id, lector=_LectorPostgREST())
        if reevaluacion.get("cambio"):
            avisos.append(
                "El diagnóstico se recalculó con esta captura: dolor %s → %s · "
                "veredicto %s → %s"
                % (reevaluacion["dolor_antes"] or "—",
                   reevaluacion["dolor_ahora"] or "—",
                   reevaluacion["veredicto_antes"] or "—",
                   reevaluacion["veredicto_ahora"]))
    except Exception as exc:  # noqa: BLE001
        # En lenguaje de negocio. El detalle tecnico viaja aparte, entero: el
        # mensaje anterior hacia `split("\n")[0]` y tiraba justo la mitad
        # accionable -- «Falta el driver. Instalalo con:» y ahi terminaba.
        avisos.append(
            "La captura se guardó. El diagnóstico se actualizará en la "
            "próxima corrida.")
        reevaluacion = {"error": " ".join(str(exc).split())[:400],
                        "cambio": False}

    # ── EL PAQUETE DE EVIDENCIA, REGENERADO ─────────────────────────────────
    #
    # Va DESPUÉS de la re-evaluación porque lee su resultado, y en su propia
    # función que no puede tumbar el guardado: el crudo ya está.
    #
    # Sin esto, pegar Transactions no movía lo que Cowork lee: la ficha se
    # redactaría contra el paquete de antes y el `hash` diría que está al día,
    # porque nadie lo habría vuelto a calcular.
    paquete = guardar_paquete(realtor_id)
    if paquete.get("guardado"):
        avisos.append(
            "El paquete de evidencia se regeneró con esta captura: %d hechos. "
            "La ficha redactada queda marcada como pendiente de actualizar."
            % paquete["evidencias"])

    return 200, {"upload_batch_id": lote, "bloques": len(filas),
                 "reevaluacion": reevaluacion, "paquete": paquete,
                 "transacciones": (None if not tx_parseado else {
                     "leidas": tx_parseado.get("leidas"),
                     "escritas": transacciones_escritas,
                     "completa": tx_parseado.get("completa"),
                     "resumen": resumen_de_transacciones(tx_parseado)}),
                 "condados": condados, "avisos": avisos, "volumenes": vols,
                 "estado": estado, "hash_volcado": huella,
                 "mercados_promovidos": promovidos,
                 "resumen": resumen_de_captura(filas, perfil_unido,
                                               dict(pertenece,
                                                    realtor=ficha_del_realtor)),
                 # Una linea por caja: leido (N metricas), vacio declarado, o
                 # no se pudo leer. Es lo que se mira despues de guardar.
                 "cajas": (_cajas_con_overview(cajas, cajas_del_overview)
                           if cajas else None),
                 "sin_market_insight": sin_market_insight,
                 "contactos": [{"canal": c["canal"], "valor": c["valor"],
                                "nuevo": c in nuevos} for c in contactos],
                 "contactos_nuevos": len(nuevos),
                 "contactos_ya_estaban": len(ya_estaban)}


# ══════════════════════════════════════════════════════════════════════════════

def capturas(params: dict) -> tuple[int, dict]:
    """Lo capturado de un realtor, ya parseado, para auditarlo en pantalla.

    Lee `v_capturas_modelmatch_current` y no la tabla: la vista deja fuera los
    lotes apagados, que es donde viven los ensayos. Pedirle a la tabla devuelve
    tambien los payloads de prueba, y eso ya costo un diagnostico entero.

    Devuelve lo mismo que el resumen del guardado, para que auditar una captura
    vieja se vea igual que acabar de hacerla.
    """
    realtor_id = (params.get("realtor_id") or "").strip()
    if not realtor_id:
        return 400, {"error": "falta realtor_id"}

    cod, filas, _ = leer(
        "v_capturas_modelmatch_current",
        "?select=upload_batch_id,capturado_en,alcance,estado,"
        "geografia_etiqueta,geografia_nivel,texto_crudo,parseado,"
        "version_parser,hash_volcado"
        "&parseado->>realtor_id=eq.%s&order=capturado_en.desc"
        % urllib.parse.quote(realtor_id))
    if cod >= 400:
        return cod, {"error": "supabase", "detalle": filas}

    _c_r, fichas, _ = leer(
        "realtors", "?select=nombre_completo,email_principal,brokerage,estado"
                    "&id=eq.%s" % urllib.parse.quote(realtor_id))
    ficha_del_realtor = (fichas or [{}])[0]

    por_lote: dict = {}
    for f in filas or []:
        lote = por_lote.setdefault(f["upload_batch_id"], {
            "upload_batch_id": f["upload_batch_id"],
            "capturado_en": f.get("capturado_en"),
            "estado": f.get("estado"),
            "version_parser": f.get("version_parser"),
            "hash_volcado": f.get("hash_volcado"),
            "_filas": [],
        })
        # La ETIQUETA autoritativa es la COLUMNA, no la del jsonb. Se subio a
        # columna justamente para poder distinguir dos bloques que se ven
        # iguales, y la normalizacion de estado corrigio la columna -- asi que
        # el jsonb de las capturas viejas todavia dice `CALIFORNIA` donde la
        # columna ya dice `CA`. Leer el jsonb las mostraria como dos mercados.
        p = dict(f.get("parseado") or {})
        if f.get("geografia_etiqueta") is not None:
            p["etiqueta_geografica"] = f["geografia_etiqueta"]
        if f.get("geografia_nivel") is not None:
            p["nivel"] = f["geografia_nivel"]
        lote["_filas"].append({
            "parseado": p,
            "texto_crudo": f.get("texto_crudo") or "",
        })
        # El crudo viaja para poder AUDITARLO en pantalla. Es el unico dato que
        # no se puede re-derivar de otra cosa: todo lo demas sale de el.
        lote.setdefault("bloques", []).append({
            "seccion": p.get("seccion"),
            "nivel": p.get("nivel"),
            "etiqueta": p.get("etiqueta_geografica"),
            "orden": p.get("orden"),
            "caracteres": len(f.get("texto_crudo") or ""),
            "texto_crudo": f.get("texto_crudo") or "",
        })

    salida = []
    for lote in por_lote.values():
        crudas = lote.pop("_filas")
        lote["bloques"] = _en_orden([
            {"parseado": b, "texto_crudo": b["texto_crudo"]}
            for b in lote.get("bloques", [])])
        lote["bloques"] = [b["parseado"] for b in lote["bloques"]]
        perfiles = [(c["parseado"].get("perfil") or {}) for c in crudas
                    if c["parseado"].get("seccion") in ("overview",
                                                        "originators",
                                                        "lenders")]
        unido = unir_perfiles([p for p in perfiles if isinstance(p, dict)])
        # La pertenencia se recalcula tambien en el historico: las capturas
        # guardadas ANTES de que existiera la trampa 0 nunca se comprobaron, y
        # sin esto seguirian sin comprobarse para siempre.
        lote["resumen"] = resumen_de_captura(
            crudas, unido, dict(comprobar(unido, ficha_del_realtor),
                                realtor=ficha_del_realtor))
        lote["caracteres"] = sum(len(c["texto_crudo"]) for c in crudas)
        salida.append(lote)

    salida.sort(key=lambda x: x.get("capturado_en") or "", reverse=True)
    return 200, {"capturas": salida, "total": len(salida)}


# ══════════════════════════════════════════════════════════════════════════════

def lectura(params: dict) -> tuple[int, dict]:
    """La ficha de un realtor EN PALABRAS, con su cadena de evidencia.

    Devuelve las dos pestañas de una vez -- `Lectura del perfil` y `Como se
    calculo`-- porque son la misma informacion a dos profundidades, y partirlas
    en dos peticiones las dejaria poder discrepar.
    """
    from motor.contrastes import mix_de_programa
    from motor.lectura import (
        leer_canal_tpo,
        leer_mix_fha,
        leer_perfil_del_comprador,
    )
    from motor.narrativa import narrativa
    from motor.sin_dolor import copy_sin_dolor

    realtor_id = (params.get("realtor_id") or "").strip()
    if not realtor_id:
        return 400, {"error": "falta realtor_id"}

    cod, filas, _ = leer(
        "realtors",
        "?select=%s&id=eq.%s" % (CAMPOS_LISTA, urllib.parse.quote(realtor_id)))
    if cod >= 400 or not filas:
        return (cod if cod >= 400 else 404), {"error": "realtor no encontrado"}
    realtor = filas[0]

    # La evaluacion VIGENTE, nunca la tabla: `count(*)` sobre append-only
    # cuenta corridas, no personas.
    _c, evs, _ = leer(
        "v_evaluacion_actual",
        "?select=dolor_primario,dolores_secundarios,moduladores,apertura,"
        "gating_qualifier,gating_intensidad,confianza,campos_ausentes,"
        "no_evaluadas,version_reglas,evaluado_en,excluido,excluido_motivo"
        "&realtor_id=eq.%s" % urllib.parse.quote(realtor_id))
    ev = (evs or [None])[0]

    # SOLO la captura mas reciente. Ver `capturas_que_mandan`.
    crudas, cuantas_capturas = capturas_que_mandan(realtor_id)
    perfiles, mercados = [], []
    for f in crudas or []:
        p = f.get("parseado") or {}
        if p.get("perfil"):
            perfiles.append(p["perfil"])
        if p.get("metricas"):
            mercados.append({
                "nivel": f.get("geografia_nivel") or p.get("nivel"),
                "estado": f.get("estado"),
                "etiqueta": (f.get("geografia_etiqueta")
                             or p.get("etiqueta_geografica")),
                "metricas": p["metricas"]})
    unido = unir_perfiles(perfiles)
    mercados.sort(key=lambda m: (m["nivel"] != "estado", m["etiqueta"] or ""))

    nombre = (realtor.get("nombre_completo") or "").strip()
    if nombre.isupper():
        nombre = nombre.title()

    # El Census del condado donde opera, si lo hay.
    # UNA sola lectura: antes se pedia la misma fila dos veces --una para
    # `variables` y otra, treinta lineas mas abajo, para `nombre`-- con el
    # mismo `condado_fips`. Dos viajes a Supabase por el mismo dato.
    censo = None
    fila_censo = None
    if realtor.get("condado_fips"):
        _c, cc, _ = leer("census_condados",
                         "?select=nombre,variables&condado_fips=eq.%s"
                         % urllib.parse.quote(realtor["condado_fips"]))
        if cc:
            fila_censo = cc[0]
            censo = (fila_censo.get("variables") or {}).get("_derivadas")

    # ── EL CONDADO DOMINANTE, Y SOLO ESE ────────────────────────────────────
    # Cuatro tarjetas de `mix de programa` con el mismo texto palabra por
    # palabra es ruido: lo unico que cambia es el mercado, y Alameda con UNA
    # unidad no sirve para decidir nada. Solo su condado dominante entra en la
    # lectura; el estado queda como referencia secundaria y el resto se va a
    # `Como se calculo`, que es donde se revisa el calculo.
    dominante_fips = realtor.get("condado_fips")
    nombre_dominante = None
    if fila_censo:
        nombre_dominante = (fila_censo.get("nombre") or "").split(" County")[0]

    def _es(m, quien):
        return quien and (m.get("etiqueta") or "").lower() == quien.lower()

    lecturas, lecturas_secundarias = [], []
    mix = unido.get("loan_mix_buyer") or {}
    for c in mix_de_programa(mix, mercados, tipo="FHA"):
        lec = leer_mix_fha(c, nombre)
        fila = {"titulo": "Mix de programa · %s" % c.geografia,
                "geografia": c.geografia, "nivel": c.nivel,
                "que_dice_del_borrower": lec.que_dice_del_borrower,
                "bueno_o_malo": lec.bueno_o_malo,
                "que_hacer": lec.que_hacer,
                "evidencia": lec.evidencia, "afirma": lec.afirma,
                "veces": c.veces, "valor_agente": c.valor_agente,
                "valor_mercado": c.valor_mercado}
        if nombre_dominante and _es({"etiqueta": c.geografia},
                                    nombre_dominante):
            fila["papel"] = "dominante"
            lecturas.append(fila)
        elif c.nivel == "estado":
            fila["papel"] = "referencia"
            lecturas_secundarias.insert(0, fila)
        else:
            fila["papel"] = "otro condado"
            lecturas_secundarias.append(fila)

    # Sin condado dominante resuelto, el estado hace de dominante -- y se dice.
    if not lecturas and lecturas_secundarias:
        ref = next((f for f in lecturas_secundarias
                    if f["papel"] == "referencia"), None)
        if ref:
            ref["papel"] = "dominante por defecto"
            lecturas.append(ref)
            lecturas_secundarias.remove(ref)

    canal = next((m for m in mercados if (m["metricas"] or {}).get(
        "loan_channel")), None)
    if canal:
        lec = leer_canal_tpo(
            unido.get("tpo_pct"), canal["metricas"].get("loan_channel"),
            nombre, canal["etiqueta"] or "su mercado",
            canal["metricas"].get("fallout"))
        lecturas.append({"titulo": "Canal · %s" % canal["etiqueta"],
                         "geografia": canal["etiqueta"],
                         "nivel": canal["nivel"], "papel": "canal",
                         "veces": None, "valor_agente": unido.get("tpo_pct"),
                         "valor_mercado": None,
                         "que_dice_del_borrower": lec.que_dice_del_borrower,
                         "bueno_o_malo": lec.bueno_o_malo,
                         "que_hacer": lec.que_hacer,
                         "evidencia": lec.evidencia, "afirma": lec.afirma})

    # El perfil se lee del condado DOMINANTE, no del primero alfabetico. Para
    # Armando eso es Solano (5 unidades) y no Alameda (1): describir la zona
    # donde casi no opera es describir a otra gente.
    perfil_zona = None
    mercado_dominante = {}
    if mercados:
        dominante = next((x for x in mercados
                          if nombre_dominante
                          and (x["etiqueta"] or "").lower()
                          == nombre_dominante.lower()), None)
        m = (dominante
             or next((x for x in mercados if x["nivel"] == "condado"),
                     mercados[0]))
        mercado_dominante = m["metricas"] or {}
        perfil_zona = {"donde": m["etiqueta"],
                       "texto": leer_perfil_del_comprador(
                           m["metricas"], censo, m["etiqueta"] or "la zona")}

    # ── ¿ESTA EVALUACION LA SACO EL MOTOR DE HOY? ───────────────────────────
    # `pacs.evaluaciones` es append-only y el catalogo cambia. Una evaluacion
    # de una version anterior no es una evaluacion mala: es una evaluacion que
    # todavia no se rehizo. Pero su dolor primario NO es el que el motor de hoy
    # sacaria, y presentarlo como vigente es afirmar algo que ya no se sostiene.
    reglas_viejas = bool(ev) and (ev.get("version_reglas") != VERSION_REGLAS)

    sin_dolor = None
    if not (ev or {}).get("dolor_primario"):
        # `apertura` distingue las dos formas de no tener dolor primario: no
        # saber nada todavía, y saber que el ángulo hipotecario no le aplica.
        # Sin pasarla, un agente de listings caía en el copy de «lo que falta
        # es nuestro» y en la cola de enriquecimiento.
        c = copy_sin_dolor(realtor,
                           nombre_estado=ESTADOS.get(realtor.get("estado")),
                           apertura_motor=(ev or {}).get("apertura"))
        sin_dolor = {"titular": c.titular, "cuerpo": c.cuerpo,
                     "apertura": c.apertura, "cola": c.cola, "rama": c.rama,
                     "falta": list(c.falta)}

    # ── LOS QUALIFIERS, CON SU ENUNCIADO ────────────────────────────────────
    # `P-Q14` solo no le dice nada a nadie. Cada uno trae el enunciado literal
    # de la matriz, su fuerza sobre 3, el grado de evidencia, la regla que lo
    # activo y su fuente -- mas el angulo y la municion, que son lo que el BD
    # necesita para saber QUE ofrecerle.
    from motor.qualifiers import ficha as ficha_q

    activaciones = ((ev or {}).get("resultado") or {}).get("activaciones") or []
    if not activaciones and ev:
        _c, res, _ = leer(
            "v_evaluacion_actual",
            "?select=resultado&realtor_id=eq.%s"
            % urllib.parse.quote(realtor_id))
        activaciones = ((res or [{}])[0].get("resultado") or {}).get(
            "activaciones") or []

    primario = (ev or {}).get("dolor_primario")
    secundarios = set((ev or {}).get("dolores_secundarios") or [])
    vistos, hipotesis = set(), []
    for a in activaciones:
        q = a.get("qualifier")
        if not q or q in vistos or a.get("familia") != "P":
            continue
        vistos.add(q)
        f = ficha_q(q)
        hipotesis.append({
            "qualifier": q,
            "papel": ("principal" if q == primario
                      else "secundario" if q in secundarios else "detectado"),
            "enunciado": f.get("enunciado"),
            "intensidad": a.get("intensidad"),
            "grado": a.get("grado"),
            "acto": a.get("acto"),
            "regla": a.get("texto"),
            "regla_id": a.get("regla_id"),
            "origen": a.get("origen"),
            "escala": f.get("escala_de_intensidad"),
            "evidencia_minima": f.get("evidencia_minima"),
            "angulo": f.get("angulo_que_activa"),
            "municion": f.get("municion_PR_GC"),
            "ruta_de_copy": f.get("ruta_de_copy"),
            "sin_ficha": not f,
        })
    hipotesis.sort(key=lambda h: (h["papel"] != "principal",
                                  h["papel"] != "secundario",
                                  -(h["intensidad"] or 0)))

    # ¿Podemos originarle? Es lo que puede hacer irrelevante todo lo demas: un
    # realtor que califica en un estado donde no tenemos licencia no se
    # contacta, porque activarlo seria gastar credibilidad en una promesa que
    # no podemos cumplir.
    #
    # `pacs.lo_licencias` esta VACIA hoy. La respuesta correcta es "no lo
    # sabemos", no "no tenemos": son cosas distintas y solo una de las dos es
    # una razon para no escribirle.
    cobertura = {"activos": None, "quienes": [], "razon": ""}
    if realtor.get("estado"):
        cod_c, los, _ = leer(
            "lo_licencias",
            "?select=employee_key,vigente&estado=eq.%s&vigente=is.true"
            "&limit=500" % urllib.parse.quote(realtor["estado"]))
        if cod_c < 400:
            claves = {l.get("employee_key") for l in (los or [])
                      if l.get("employee_key") is not None}
            _c2, total, _ = leer("lo_licencias", "?select=id&limit=1")
            if not total:
                cobertura["razon"] = (
                    "pacs.lo_licencias está vacía: la carga de licencias "
                    "todavía no corrió, así que no se puede decir si podemos "
                    "originar en ese estado")
            else:
                cobertura["activos"] = len(claves)
        else:
            cobertura["razon"] = "no se pudo consultar lo_licencias"

    texto_narrativa = narrativa(
        realtor, estado_nombre=ESTADOS.get(realtor.get("estado")),
        perfil_mm=unido, mercado=mercado_dominante,
        donde=nombre_dominante or (perfil_zona or {}).get("donde"),
        cobertura=cobertura)

    return 200, {
        "realtor": {**realtor, "nombre_mostrado": nombre,
                    "estado_nombre": ESTADOS.get(realtor.get("estado"))},
        "narrativa": texto_narrativa,
        "cabecera": {
            "nivel": (ev or {}).get("nivel") or _nivel_desde(ev),
            # El dolor primario NO se presenta como vigente si la evaluacion se
            # calculo con otra version de reglas. Es literalmente lo que pasa
            # hoy con las 4.187: se evaluaron con
            # `2026.09.23-vocabulario-de-oficio` y el catalogo ya es
            # `2026.09.23-sin-r7`, sin R7. Mostrar ese P-Q14 como el dolor de
            # alguien seria mostrar una conclusion que el motor actual no saca.
            "dolor_primario": primario if not reglas_viejas else None,
            "dolor_primario_de_reglas_anteriores": primario if reglas_viejas
                                                   else None,
            "acto_de_habla": next((h["acto"] for h in hipotesis
                                   if h["papel"] == "principal"), None),
            "gating": {"qualifier": (ev or {}).get("gating_qualifier"),
                       "intensidad": (ev or {}).get("gating_intensidad")},
            "confianza": (ev or {}).get("confianza"),
        },
        # La exclusion va SUELTA y no dentro de la cabecera: es lo primero que
        # la pantalla tiene que poder mirar, sin recorrer un diagnostico que
        # aqui ya no decide nada.
        "excluido": (ev or {}).get("excluido"),
        "excluido_motivo": (ev or {}).get("excluido_motivo"),
        "reglas_anteriores": ({
            "aviso": "Evaluada con reglas anteriores, pendiente de re-evaluar",
            "version_de_la_evaluacion": (ev or {}).get("version_reglas"),
            "version_actual": VERSION_REGLAS,
        } if reglas_viejas else None),
        # El veredicto completo tambien en la lectura: la pantalla necesita
        # distinguir «excluido» de «falta Model Match», que son dos avisos
        # distintos y dos trabajos distintos a continuacion.
        "veredicto": puede_contactarse(
            unir_perfiles([p for p in perfiles if isinstance(p, dict)])
            if perfiles else None,
            capturado_en=(cuantas_capturas or {}).get("vigente_desde"),
            excluido_por_el_libro=(ev or {}).get("excluido"),
            motivo_del_libro=(ev or {}).get("excluido_motivo")).a_dict(),
        "hipotesis": hipotesis,
        "evaluacion": ev,
        "lecturas": lecturas,
        "lecturas_secundarias": lecturas_secundarias,
        "condado_dominante": nombre_dominante,
        "cobertura": cobertura,
        "perfil_de_la_zona": perfil_zona,
        "sin_dolor": sin_dolor,
        "mercados": len(mercados),
        # El perfil unido viaja para que `dossier` pueda pedirle el veredicto a
        # `puede_contactarse` sin volver a leer las capturas. Calcularlo dos
        # veces es como se terminan desincronizando dos respuestas a la misma
        # pregunta.
        "perfil_unido": unir_perfiles(
            [p for p in perfiles if isinstance(p, dict)]) if perfiles else None,
        "tiene_census": censo is not None,
        # Cuantas capturas hay y cual manda. Con mas de una, la pantalla lo
        # dice: un diagnostico que cambia porque alguien re-capturo tiene que
        # ser visible, no una sorpresa.
        "capturas": cuantas_capturas,
    }


#: Los cuatro niveles. Se derivan de lo que el motor ya guardo, porque la
#: evaluacion no trae un campo `nivel` -- y ponerlo a mano en dos sitios es
#: como se desincronizan.
def _nivel_desde(ev: dict | None) -> str:
    if not ev:
        return "SIN EVALUAR"
    # Va PRIMERO. Lisa Munoz tiene P-Q10 y gating: por los cuatro niveles de
    # abajo sale MQL, que es exactamente como una excluida termina en una cola.
    if ev.get("excluido"):
        return "EXCLUIDO"
    if not ev.get("gating_qualifier"):
        return "BLOQUEADO"
    if not ev.get("dolor_primario"):
        return "PRE-MQL"
    return "MQL"


# ══════════════════════════════════════════════════════════════════════════════

#: Como se lee cada estado de perfil. Los nueve, y ninguno por descarte:
#: `privado` solo con evidencia afirmativa. Creer que la ausencia de
#: publicaciones era privacidad costo siete perfiles.
ESTADOS_IG = {
    "publico_leido": ("mql", "leído"),
    "privado": ("sin-evaluar", "privado — con evidencia"),
    "no_encontrado": ("sin-evaluar", "no encontrado"),
    "bloqueado": ("excluido", "bloqueado"),
    "handle_dudoso": ("bloqueado", "handle dudoso"),
    "muro_de_sesion": ("bloqueado", "muro de sesión"),
    "sin_grid": ("bloqueado", "sin grid"),
    "degradado": ("bloqueado", "degradado"),
    "vacio": ("sin-evaluar", "vacío"),
}

#: Las señales que se muestran primero, con su etiqueta legible.
SENALES_DESTACADAS = (
    ("desajuste_idioma", "desajuste de idioma"),
    ("audiencia_dominante", "audiencia dominante"),
    ("tema_dominante", "tema dominante"),
    ("ratio_educa_vs_anuncia", "educa vs anuncia"),
    ("engagement_rate", "engagement"),
    ("dias_entre_posts_mediana", "días entre posts"),
    ("hueco_max_dias", "hueco máximo"),
    ("tipo_post_reel_pct", "% reels"),
)


def instagram(params: dict) -> tuple[int, dict]:
    """Lo capturado de Instagram, tal como quedo. Sin motor.

    Lee `v_ig_senales_current`: la vista deja fuera los lotes apagados, o sea
    los raspados viejos. Instagram SI es fuente de reemplazo.
    """
    realtor_id = (params.get("realtor_id") or "").strip()
    if not realtor_id:
        return 400, {"error": "falta realtor_id"}

    cod, filas, _ = leer(
        "v_ig_senales_current",
        "?select=handle,estado_perfil,estado_evidencia,handle_confianza,"
        "senales,captions_n,comentarios_n,paginacion_truncada,capturado_en,"
        "desajuste_idioma&realtor_id=eq.%s&order=capturado_en.desc"
        % urllib.parse.quote(realtor_id))
    if cod >= 400:
        return cod, {"error": "supabase", "detalle": filas}
    if not filas:
        return 200, {"perfiles": [], "total": 0}

    salida = []
    for f in filas:
        s = f.get("senales") or {}
        clase, etiqueta = ESTADOS_IG.get(f.get("estado_perfil"),
                                         ("sin-evaluar", f.get("estado_perfil")))
        destacadas = [{"clave": k, "etiqueta": e, "valor": s.get(k)}
                      for k, e in SENALES_DESTACADAS if s.get(k) not in
                      (None, "")]
        # `desajuste_idioma` vive en columna propia, no en el jsonb.
        if f.get("desajuste_idioma") is not None:
            destacadas.insert(0, {"clave": "desajuste_idioma",
                                  "etiqueta": "desajuste de idioma",
                                  "valor": f["desajuste_idioma"]})
        salida.append({
            "handle": f.get("handle"),
            "estado_perfil": f.get("estado_perfil"),
            "estado_clase": clase,
            "estado_etiqueta": etiqueta,
            "estado_evidencia": f.get("estado_evidencia"),
            "handle_confianza": f.get("handle_confianza"),
            "captions_n": f.get("captions_n"),
            "comentarios_n": f.get("comentarios_n"),
            "paginacion_truncada": f.get("paginacion_truncada"),
            "capturado_en": f.get("capturado_en"),
            "destacadas": destacadas,
            # El resto de las señales, para la tabla de abajo.
            "senales": {k: v for k, v in sorted(s.items())
                        if v not in (None, "")},
        })
    return 200, {"perfiles": salida, "total": len(salida)}


# ══════════════════════════════════════════════════════════════════════════════

def dossier(params: dict) -> tuple[int, dict]:
    """El dossier y la secuencia de 7 toques, sin una sola promesa de material.

    Reusa `/api/lectura`: el dossier ES la lectura ordenada para leerse de un
    tiron, y calcularla dos veces las dejaria discrepar.
    """
    from motor.contrastes import mix_de_programa
    from motor.lectura import leer_mix_fha
    from motor.recursos import CATALOGO
    from motor.secuencia import armar_secuencia

    cod, base = lectura(params)
    if cod >= 400:
        return cod, base

    # ── LA COMPUERTA CORTA AQUI ─────────────────────────────────────────────
    # El dossier no es una lectura: es la secuencia de 7 toques, o sea la cola
    # de contacto misma. Un excluido tiene lectura -- su diagnostico sigue
    # visible en /api/lectura -- pero no tiene secuencia. Devolver el dossier y
    # confiar en que la pantalla no lo mande es la misma omision de antes, un
    # piso mas arriba.
    #
    # Se llama a `motor.veredicto.puede_contactarse`, que es la MISMA que usan
    # `/api/extracto`, `guardar_texto` y `correr_motor`. Cuatro criterios
    # distintos para la misma pregunta dejaban al mismo realtor contactable por
    # un camino e inviable por otro.
    v = puede_contactarse(
        base.get("perfil_unido"),
        capturado_en=(base.get("capturas") or {}).get("vigente_desde"),
        excluido_por_el_libro=base.get("excluido"),
        motivo_del_libro=base.get("excluido_motivo"))
    if not v.puede_escribirsele:
        return 409, {
            "error": v.motivo,
            "veredicto": v.a_dict(),
            # Lo que YA se sabe viaja igual: la pantalla tiene que poder
            # mostrarlo. Lo que no viaja es un solo bloque de mensajes.
            "lo_que_sabemos": {
                "realtor": base.get("realtor"),
                "cabecera": base.get("cabecera"),
                "narrativa": base.get("narrativa"),
                "hipotesis": base.get("hipotesis"),
                "mercados": base.get("mercados"),
            },
            # Las MISMAS claves que la respuesta de 200, vacias. Si el 409
            # usara otras, quien lea `d["secuencia"]["toques"]` reventaria en
            # vez de ver cero toques -- y un KeyError se arregla con un
            # `.get(...)` que devuelve None, que es lo que termina pintandose.
            "bloques": [],
            "secuencia": {"toques": [], "recursos_pendientes": []},
            "que_hacer": (
                "Su lectura sigue disponible en /api/lectura. Lo que no existe "
                "es la secuencia."
                if v.estado == "excluido" else
                "Falta Model Match: capturar antes de dar veredicto."),
        }

    # La obsolescencia va DESPUES de la compuerta, y no al reves.
    #
    # `puede_contactarse` no mira el catalogo de qualifiers: lee el libro y el
    # reparto de originadores de Model Match. Su veredicto vale igual con
    # reglas viejas, y es permanente -- Armando Ochoa trabaja con Everett
    # Financial se re-corra el motor o no. La obsolescencia, en cambio, es un
    # estado temporal de NUESTROS datos.
    #
    # Con el orden al reves, Armando salia «pendiente de re-evaluar» y su
    # exclusion quedaba tapada por un aviso que hoy tienen las 4.187 filas.
    if base.get("reglas_anteriores"):
        ra = base["reglas_anteriores"]
        return 409, {
            "error": ra["aviso"],
            "reglas_anteriores": ra,
            "lo_que_sabemos": {
                "realtor": base.get("realtor"),
                "cabecera": base.get("cabecera"),
                "narrativa": base.get("narrativa"),
                "mercados": base.get("mercados"),
            },
            "bloques": [],
            "secuencia": {"toques": [], "recursos_pendientes": []},
            "que_hacer": ("Volver a correr el motor sobre este realtor. Su "
                          "diagnóstico anterior se conserva como histórico, "
                          "pero no es el que el motor de hoy sacaría."),
        }

    nombre = base["realtor"]["nombre_mostrado"]
    ev = base.get("evaluacion") or {}
    zona = base.get("perfil_de_la_zona") or {}
    donde = zona.get("donde") or base["realtor"].get("estado") or "su zona"

    # ── EL GANCHO · literal de la ficha que le toca ─────────────────────────
    # El enrutado qualifier -> ficha es una DECISION, y esta en `motor/ganchos`.
    # `P-Q01` se abre distinto segun la señal que lo activo, asi que se le pasa
    # la entrada de la evaluacion para elegir la variante.
    from motor.ganchos import gancho_de

    dolor = (base.get("cabecera") or {}).get("dolor_primario")
    señales = ((ev or {}).get("entrada") or {}) if isinstance(ev, dict) else {}
    if not señales and dolor:
        _c, ent, _ = leer(
            "v_evaluacion_actual",
            "?select=entrada&realtor_id=eq.%s"
            % urllib.parse.quote(params.get("realtor_id", "")))
        señales = (ent or [{}])[0].get("entrada") or {}

    # La fuerza y el acto de habla viajan al gancho: con una hipotesis de
    # fuerza 1 el gancho del corpus presupondria el dolor, y una presuposicion
    # falsa tumba el mensaje en la primera linea.
    principal = next((h for h in (base.get("hipotesis") or [])
                      if h.get("papel") == "principal"), {})
    g = gancho_de(dolor, señales,
                  intensidad=principal.get("intensidad"),
                  acto_de_habla=principal.get("acto")) if dolor else None
    if g:
        gancho, fuente_gancho = g.texto, g.fuente
    elif dolor:
        gancho = GANCHO_GENERICO
        fuente_gancho = ("genérico: %s no tiene ficha enrutada ni derivado en "
                         "el corpus" % dolor)
    else:
        gancho = GANCHO_GENERICO
        fuente_gancho = ("genérico: sin evidencia suficiente no hay ficha que "
                         "abrir — no lo sabemos todavía. "
                         "La apertura real es la pregunta del bloque G.")

    # Las lecturas como objetos, para que el toque 4 pueda mirar `afirma`.
    lecturas = []
    if base.get("mercados"):
        crudas, _cuantas = capturas_que_mandan(params.get("realtor_id", ""))
        perfiles, mercados = [], []
        for f in crudas or []:
            p = f.get("parseado") or {}
            if p.get("perfil"):
                perfiles.append(p["perfil"])
            if p.get("metricas"):
                mercados.append({
                    "nivel": f.get("geografia_nivel"),
                    "estado": f.get("estado"),
                    "etiqueta": f.get("geografia_etiqueta"),
                    "metricas": p["metricas"]})
        # ── LOS MERCADOS TOMADOS DE LA BIBLIOTECA ───────────────────────────
        # Un benchmark que no se pegó porque ya estaba tiene que producir el
        # MISMO contraste que uno pegado. Si produjera otro, ahorrarle el
        # pegado a quien captura sería cambiarle el resultado al diagnóstico.
        mercados.extend(_mercados_enlazados(crudas))
        unido = unir_perfiles(perfiles)
        for c in mix_de_programa(unido.get("loan_mix_buyer") or {}, mercados,
                                 tipo="FHA"):
            lecturas.append(leer_mix_fha(c, nombre))
        mercado_de_zona = next(
            (m["metricas"] for m in mercados
             if (m["etiqueta"] or "").lower() == (donde or "").lower()), {})
    else:
        mercado_de_zona = {}

    apertura = (base.get("sin_dolor") or {}).get("apertura") or (
        "¿Con qué lender estás cerrando hoy, y qué es lo que más se te "
        "complica con ellos — el pre-approval, los tiempos o el closing?")

    seq = armar_secuencia(nombre=nombre, gancho=gancho,
                          mercado=mercado_de_zona, donde=donde,
                          perfil_zona=zona.get("texto"), lecturas=lecturas,
                          apertura_sin_dolor=apertura)

    from motor.dossier import armar_dossier

    bloques = armar_dossier(
        realtor=base["realtor"], narrativa=base.get("narrativa") or "",
        cabecera=base.get("cabecera") or {},
        hipotesis=base.get("hipotesis") or [],
        lecturas=base.get("lecturas") or [],
        perfil_zona=base.get("perfil_de_la_zona"),
        condado_dominante=base.get("condado_dominante"),
        gancho=gancho, gancho_fuente=fuente_gancho)

    return 200, {
        **base,
        "bloques": [{"letra": b.letra, "titulo": b.titulo, "texto": b.texto,
                     "datos": b.datos, "fuente": b.fuente,
                     "vacio_porque": b.vacio_porque} for b in bloques],
        "gancho": {"texto": gancho, "fuente": fuente_gancho},
        "secuencia": {
            "toques": [{"numero": t.numero, "dia": t.dia, "canal": t.canal,
                        "cuerpo": t.cuerpo,
                        "fuente_del_valor": t.fuente_del_valor,
                        "recursos": list(t.recursos)} for t in seq.toques],
            "notas": seq.notas,
            "promete_material": seq.promete_material,
        },
        "recursos_pendientes": [
            {"clave": r.clave, "descripcion": r.descripcion,
             "verificado": r.verificado}
            for r in CATALOGO.values()],
        "dolor_primario": ev.get("dolor_primario"),
    }


#: Mientras el enrutado qualifier -> ficha no exista, el gancho es este y se
#: dice que es generico. Elegir una de las 205 fichas al azar daria un mensaje
#: que PARECE calibrado y no lo esta.
GANCHO_GENERICO = ("Una curiosidad de oficio: ¿qué es lo que más se te "
                   "atasca hoy con los lenders con los que cierras?")


# ══════════════════════════════════════════════════════════════════════════════

#: Los conjuntos CERRADOS contra los que se comprueba que un texto no nombro
#: algo ajeno. Son 3.000 condados y 2.500 lenders, y cambian casi nunca -- pero
#: se pedian ENTEROS en cada peticion de `/api/extracto`, que por eso tardaba
#: 5,9 segundos con 1.025 filas leidas.
#:
#: La cache vive en el proceso. En Vercel cada funcion fria la vuelve a llenar,
#: que es lo correcto: no hay invalidacion que mantener, y el costo se paga una
#: vez por instancia en vez de una vez por peticion.
_VOCABULARIO: dict = {}


def _vocabulario_cerrado() -> tuple[list, list]:
    if _VOCABULARIO:
        return _VOCABULARIO["condados"], _VOCABULARIO["lenders"]
    _c, condados, _ = leer("census_condados", "?select=nombre&limit=3000")
    nombres_condado = sorted({(c.get("nombre") or "").split(" County")[0]
                              for c in (condados or []) if c.get("nombre")})
    _c, lenders, _ = leer("lenders", "?select=nombre,nombre_comercial&limit=500")
    _c, origs, _ = leer("originadores", "?select=nombre,empresa_texto&limit=2000")
    nombres_lender = sorted({v for f in ((lenders or []) + (origs or []))
                             for v in f.values() if v})
    # Solo se cachea si vino algo: cachear una lista vacia por un error de red
    # convertiria la guarda de entidades en una que rechaza todo para siempre.
    if nombres_condado and nombres_lender:
        _VOCABULARIO["condados"] = nombres_condado
        _VOCABULARIO["lenders"] = nombres_lender
    return nombres_condado, nombres_lender


def extracto(params: dict) -> tuple[int, dict]:
    """El material EXACTO con el que se escribe. Y es lo que va a `insumos`.

    Reusa `/api/dossier`, que reusa `/api/lectura`: un solo camino de calculo.
    Si el extracto se calculara aparte, la verificacion compararia el texto
    contra algo distinto de lo que se leyo -- y una guarda que compara contra
    otra cosa aprueba.
    """
    from motor.extracto import armar_extracto

    cod, base = dossier(params)
    if cod >= 400:
        return cod, base

    realtor_id = (params.get("realtor_id") or "").strip()

    # Los conjuntos CERRADOS contra los que se puede comprobar que el texto no
    # nombro algo ajeno. Viajan DENTRO del extracto, para que la verificacion
    # no dependa de volver a consultar la base.
    nombres_condado, nombres_lender = _vocabulario_cerrado()

    # Instagram, cuando este cargado: lo que EL escribio es lo unico que un
    # realtor reconoce como suyo.
    cod_ig, ig = instagram({"realtor_id": realtor_id})
    publicaciones = []
    if cod_ig == 200:
        for p in ig.get("perfiles", []):
            s = p.get("senales") or {}
            publicaciones.append({
                "handle": p.get("handle"),
                "estado_perfil": p.get("estado_perfil"),
                "publicaciones_leidas": p.get("captions_n"),
                "comentarios": p.get("comentarios_n"),
                "que_publica": s.get("tema_dominante"),
                "a_quien_le_habla": s.get("audiencia_dominante"),
                "que_le_preguntan": s.get("preguntas_recibidas"),
                "idioma_publica_es": s.get("idioma_publica_es"),
                "idioma_publica_en": s.get("idioma_publica_en"),
                "idioma_comentarios_es": s.get("idioma_comentarios_es"),
                "idioma_comentarios_en": s.get("idioma_comentarios_en"),
                "desajuste_idioma": p.get("desajuste_idioma"),
                "citas": s.get("citas_por_etiqueta"),
            })

    ext = armar_extracto(
        realtor=base["realtor"], narrativa=base.get("narrativa") or "",
        cabecera=base.get("cabecera") or {},
        hipotesis=base.get("hipotesis") or [],
        lecturas=base.get("lecturas") or [],
        perfil_zona=base.get("perfil_de_la_zona"),
        condado_dominante=base.get("condado_dominante"),
        gancho=base.get("gancho") or {},
        cobertura=base.get("cobertura") or {},
        evaluacion=base.get("evaluacion"),
        instagram=publicaciones,
        vocabulario={"condados": nombres_condado, "lenders": nombres_lender})

    # Los originadores del perfil, para que la guarda de lenders sepa cuales SI
    # son suyos. Sin esto, `Everett Financial` -- que ES su originador-- se
    # rechazaria como entidad ajena: un falso positivo que hace inservible la
    # guarda justo en el caso que mas importa, la exclusion.
    crudas_o, _cuantas_o = capturas_que_mandan(realtor_id)
    perfiles_o = [(f.get("parseado") or {}).get("perfil") for f in (crudas_o or [])]
    unido_o = unir_perfiles([p for p in perfiles_o if isinstance(p, dict)])
    suyos, vistos_o = [], set()
    for o in (unido_o.get("orig_buyer") or []) + (unido_o.get("tab_orig") or []):
        for k in ("nombre", "empresa"):
            v = o.get(k)
            if v and v not in vistos_o:
                vistos_o.add(v)
        suyos.append({"nombre": o.get("nombre"), "empresa": o.get("empresa"),
                      "unidades": o.get("unidades"), "share": o.get("share")})
    ext["originadores"] = suyos
    ext["lenders_del_agente"] = sorted(vistos_o)

    return 200, {
        "extracto": ext,
        "como_usarlo": (
            "Esto es lo que va tal cual a `insumos` cuando guardes el texto. "
            "Toda cifra y toda entidad del texto tiene que estar aquí: "
            "`supabase/guardar_texto.py` lo comprueba antes de insertar."),
        "sin_instagram": not publicaciones,
    }


#: ruta -> (funcion, metodo)
RUTAS = {
    "/api/extracto": (extracto, "GET"),
    "/api/realtors": (realtors, "GET"),
    "/api/geografias": (geografias, "GET"),
    "/api/leer_overview": (leer_overview, "POST"),
    "/api/mercados_en_biblioteca": (mercados_en_biblioteca, "GET"),
    "/api/ficha": (ficha_v3, "GET"),
    "/api/ficha_v3": (ficha_v3_completa, "GET"),
    "/api/bloques_ia": (bloques_ia, "GET"),
    "/api/pedir_ficha": (pedir_ficha, "POST"),
    "/api/capturas": (capturas, "GET"),
    "/api/lectura": (lectura, "GET"),
    "/api/instagram": (instagram, "GET"),
    "/api/dossier": (dossier, "GET"),
    "/api/guardar": (guardar, "POST"),
}
