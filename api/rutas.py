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
                "telefono_e164,unidades_ano,sf_lead_id,sin_llave_dura")
TOPE = 300

#: Con que etiqueta entra cada dato de contacto de Model Match.
FUENTE_CONTACTOS = "Model Match"


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
    return 200, {"filas": filas, "mostradas": len(filas), "total": total,
                 "tope": TOPE, "truncado": len(datos or []) >= TOPE}


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
                 "originadores": len(perfil_unido.get("orig_buyer") or []),
                 "contactos": [{"canal": c["canal"], "valor": c["valor"]}
                               for c in contactos]}


#: ruta -> (funcion, metodo)
RUTAS = {
    "/api/realtors": (realtors, "GET"),
    "/api/geografias": (geografias, "GET"),
    "/api/guardar": (guardar, "POST"),
}
