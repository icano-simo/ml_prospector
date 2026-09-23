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
from captura.trampas import es_de_la_casa, share_de_la_casa  # noqa: E402
from captura.parser_mm import (  # noqa: E402
    detectar_inversion,
    parsear_mercado,
    parsear_perfil,
    unir_perfiles,
)
from captura.protocolo import (  # noqa: E402
    ProtocoloInvalido,
    condados_del_overview,
    etiquetar_por_posicion,
    separar_volcado,
)

CAMPOS_LISTA = ("id,nombre_completo,brokerage,estado,email_principal,"
                "telefono_e164,unidades_ano,sf_lead_id,sin_llave_dura,"
                "condado_fips")
TOPE = 300

#: Con que etiqueta entra cada dato de contacto de Model Match.
FUENTE_CONTACTOS = "Model Match"

#: Por debajo de esto, el bloque no trajo metricas de verdad y no hay nada que
#: promover. Un bloque real de Market Signals trae 38-45 campos.
MINIMO_CAMPOS_PARA_PROMOVER = 5


def promover_a_mercados(filas: list[dict], lote: str,
                        ahora: str) -> tuple[list[dict], list[str]]:
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

        salida.append({
            "upload_batch_id": lote, "uploaded_at": ahora,
            "condado_fips": condado_fips, "estado": estado, "nivel": nivel,
            "fuente": "modelmatch", "metricas": metricas,
            "capturado_en": ahora,
        })
    return salida, fallos


# ══════════════════════════════════════════════════════════════════════════════

def realtors(params: dict) -> tuple[int, dict]:
    texto = (params.get("q") or "").strip()
    estado = (params.get("estado") or "").strip()
    con_mm = (params.get("mm") or "").strip()

    partes = ["select=" + CAMPOS_LISTA, "order=nombre_completo.asc",
              "limit=%d" % TOPE]
    if texto:
        t = urllib.parse.quote(texto.replace(",", " ").replace("*", ""))
        partes.append(
            "or=(nombre_completo.ilike.*{0}*,brokerage.ilike.*{0}*,"
            "email_principal.ilike.*{0}*)".format(t))
    if estado:
        partes.append("estado=eq." + urllib.parse.quote(estado))

    codigo, datos, cabeceras = leer("realtors", "?" + "&".join(partes),
                                    rango="0-%d" % (TOPE - 1))
    if codigo >= 400:
        return codigo, {"error": "supabase", "detalle": datos}

    filas = datos or []
    if con_mm in ("si", "no"):
        _, capturas, _ = leer(
            "capturas_modelmatch",
            "?select=sf_lead_id&alcance=eq.perfil&limit=5000")
        con_captura = {c.get("sf_lead_id") for c in (capturas or [])
                       if c.get("sf_lead_id")}
        filas = [f for f in filas
                 if (f.get("sf_lead_id") in con_captura) == (con_mm == "si")]

    rango = cabeceras.get("Content-Range", "")
    total = rango.split("/")[-1] if "/" in rango else str(len(filas))
    # El nombre completo del estado viaja como MAPA, no como columna. En las
    # tablas del motor manda el codigo de dos letras; el nombre es para
    # mostrar, y un solo sitio donde escribirlo es un solo sitio donde puede
    # divergir. `California` en una tabla y `CA` en otra es lo que hizo que
    # ninguna de las 4.249 filas cruzara con ninguno de los 2.261 condados.
    return 200, {"filas": filas, "mostradas": len(filas), "total": total,
                 "tope": TOPE, "truncado": len(datos or []) >= TOPE,
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
    agregar("oficina", c.get("oficina"))
    agregar("direccion", c.get("direccion"))
    return filas


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


def resumen_de_captura(filas: list[dict], perfil_unido: dict) -> dict:
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
        "fallos": perfil_unido.get("fallos") or [],
        "perfil": {
            "nombre": perfil_unido.get("nombre"),
            "buyer_units": perfil_unido.get("buyer_units"),
            "tpo_pct": perfil_unido.get("tpo_pct"),
            "lenders": len(perfil_unido.get("tabla_lenders") or []),
            "loan_mix": (perfil_unido.get("loan_mix_buyer") or {}).get("filas"),
            "cobertura_mix": (perfil_unido.get("loan_mix_buyer")
                              or {}).get("cobertura"),
        },
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
    ventana = d.get("ventana_meses")
    try:
        ventana = int(ventana) if ventana not in (None, "") else None
    except (TypeError, ValueError):
        ventana = None
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
    partes_huella = [overview] + list(ms) + [d.get("originators") or "",
                                             d.get("lenders") or ""]
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
    try:
        bloques = etiquetar_por_posicion(ms, condados)
    except ProtocoloInvalido as exc:
        return 400, {"error": str(exc), "condados": condados}

    ahora = dt.datetime.now(dt.timezone.utc).isoformat()
    lote = str(uuid.uuid4())
    avisos: list[str] = []
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
        filas.append({
            "upload_batch_id": lote, "uploaded_at": ahora, "alcance": alcance,
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
        if perfil.get("buyer_units"):
            perfil["buyside_anualizado"] = round(
                perfil["buyer_units"] / ventana * 12.0, 1)
    elif isinstance(perfil, dict) and not perfil.get("ventana_meses"):
        avisos.append(
            "sin ventana de Model Match: `Set Date Range` no viaja en el texto "
            "pegado. Sin ella no se puede anualizar la producción, que es el "
            "número que manda para la compuerta.")
    agregar("overview", overview, alcance="perfil", extra={"perfil": perfil})

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
    else:
        avisos.append("sin bloque de Originators: no se puede detectar si "
                      "trabaja con Everett Financial, que es la exclusion dura")
    if d.get("lenders"):
        agregar("lenders", d["lenders"], alcance="perfil")

    # ── lo que estaba en el texto y no llego al dict ─────────────────────────
    # Un `[]` dice dos cosas a la vez: "este agente no trabaja con nadie" y "el
    # parser no supo leerlo". La primera es un dato y la segunda es un error, y
    # sin esto se guardan identicas.
    perfiles = [f["parseado"].get("perfil") for f in filas
                if f["parseado"]["seccion"] in ("overview", "originators",
                                                "lenders")]
    perfil_unido = unir_perfiles([p for p in perfiles if isinstance(p, dict)])
    for f in perfil_unido.get("fallos") or []:
        avisos.append(
            "FALLO DE LECTURA · la seccion `%s` esta en el texto y `%s` salio "
            "vacio. Es %s. El crudo esta guardado: se arregla el parser y se "
            "re-deriva sin volver a capturar."
            % (f.get("seccion"), f.get("campo"), f.get("por_que_importa")))

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

    # ── LA BIBLIOTECA DE MERCADOS ────────────────────────────────────────────
    # Va DESPUES del crudo, por lo mismo que los contactos: si falla, el
    # volcado ya esta y se re-deriva. Pero su fallo se declara, no se calla.
    mercados, fallos_promocion = promover_a_mercados(filas, lote, ahora)
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
    if contactos:
        cod_c, det_c, _ = escribir("contactos", contactos, devolver=False,
                                   sin_duplicar=True)
        if cod_c >= 400:
            avisos.append(
                "el crudo se guardo, pero los %d datos de contacto (%s) no "
                "entraron en pacs.contactos: %s"
                % (len(contactos), ", ".join(c["canal"] for c in contactos),
                   str(det_c)[:200]))
            contactos = []

    return 200, {"upload_batch_id": lote, "bloques": len(filas),
                 "condados": condados, "avisos": avisos, "volumenes": vols,
                 "estado": estado, "hash_volcado": huella,
                 "mercados_promovidos": promovidos,
                 "resumen": resumen_de_captura(filas, perfil_unido),
                 "contactos": [{"canal": c["canal"], "valor": c["valor"]}
                               for c in contactos]}


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
        lote["resumen"] = resumen_de_captura(crudas, unido)
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
        "no_evaluadas,version_reglas,evaluado_en"
        "&realtor_id=eq.%s" % urllib.parse.quote(realtor_id))
    ev = (evs or [None])[0]

    # El perfil y los mercados de sus capturas vivas.
    _c, crudas, _ = leer(
        "v_capturas_modelmatch_current",
        "?select=parseado,geografia_etiqueta,geografia_nivel,estado"
        "&parseado->>realtor_id=eq.%s" % urllib.parse.quote(realtor_id))
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
    censo = None
    if realtor.get("condado_fips"):
        _c, cc, _ = leer("census_condados",
                         "?select=nombre,variables&condado_fips=eq.%s"
                         % urllib.parse.quote(realtor["condado_fips"]))
        if cc:
            censo = (cc[0].get("variables") or {}).get("_derivadas")

    # ── EL CONDADO DOMINANTE, Y SOLO ESE ────────────────────────────────────
    # Cuatro tarjetas de `mix de programa` con el mismo texto palabra por
    # palabra es ruido: lo unico que cambia es el mercado, y Alameda con UNA
    # unidad no sirve para decidir nada. Solo su condado dominante entra en la
    # lectura; el estado queda como referencia secundaria y el resto se va a
    # `Como se calculo`, que es donde se revisa el calculo.
    dominante_fips = realtor.get("condado_fips")
    nombre_dominante = None
    if dominante_fips:
        _c, nc, _ = leer("census_condados",
                         "?select=nombre&condado_fips=eq.%s"
                         % urllib.parse.quote(dominante_fips))
        if nc:
            nombre_dominante = (nc[0].get("nombre") or "").split(" County")[0]

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

    sin_dolor = None
    if not (ev or {}).get("dolor_primario"):
        c = copy_sin_dolor(realtor,
                           nombre_estado=ESTADOS.get(realtor.get("estado")))
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
            "dolor_primario": primario,
            "acto_de_habla": next((h["acto"] for h in hipotesis
                                   if h["papel"] == "principal"), None),
            "gating": {"qualifier": (ev or {}).get("gating_qualifier"),
                       "intensidad": (ev or {}).get("gating_intensidad")},
            "confianza": (ev or {}).get("confianza"),
        },
        "hipotesis": hipotesis,
        "evaluacion": ev,
        "lecturas": lecturas,
        "lecturas_secundarias": lecturas_secundarias,
        "condado_dominante": nombre_dominante,
        "cobertura": cobertura,
        "perfil_de_la_zona": perfil_zona,
        "sin_dolor": sin_dolor,
        "mercados": len(mercados),
        "tiene_census": censo is not None,
    }


#: Los cuatro niveles. Se derivan de lo que el motor ya guardo, porque la
#: evaluacion no trae un campo `nivel` -- y ponerlo a mano en dos sitios es
#: como se desincronizan.
def _nivel_desde(ev: dict | None) -> str:
    if not ev:
        return "SIN EVALUAR"
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

    nombre = base["realtor"]["nombre_mostrado"]
    ev = base.get("evaluacion") or {}
    zona = base.get("perfil_de_la_zona") or {}
    donde = zona.get("donde") or base["realtor"].get("estado") or "su zona"

    # El gancho del corpus, literal. Sin ficha enrutada todavia, se usa el
    # generico de oficio -- y se DICE que falta el enrutado, en vez de elegir
    # uno al azar y que parezca calibrado.
    gancho, fuente_gancho = GANCHO_GENERICO, "genérico: falta enrutar el qualifier a su ficha"

    # Las lecturas como objetos, para que el toque 4 pueda mirar `afirma`.
    lecturas = []
    if base.get("mercados"):
        _c, crudas, _ = leer(
            "v_capturas_modelmatch_current",
            "?select=parseado,geografia_etiqueta,geografia_nivel,estado"
            "&parseado->>realtor_id=eq.%s"
            % urllib.parse.quote(params.get("realtor_id", "")))
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

    return 200, {
        **base,
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


#: ruta -> (funcion, metodo)
RUTAS = {
    "/api/realtors": (realtors, "GET"),
    "/api/geografias": (geografias, "GET"),
    "/api/capturas": (capturas, "GET"),
    "/api/lectura": (lectura, "GET"),
    "/api/instagram": (instagram, "GET"),
    "/api/dossier": (dossier, "GET"),
    "/api/guardar": (guardar, "POST"),
}
