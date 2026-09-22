"""La logica de los tres endpoints, como funciones puras.

Separadas del transporte a proposito: cada una recibe un dict y devuelve
`(codigo, datos)`. Asi se pueden probar sin levantar un servidor ni tocar
Vercel, que es donde se rompen.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import urllib.parse
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
for ruta in (AQUI, os.path.dirname(AQUI)):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

from _comun import SinCredenciales, escribir, leer  # noqa: E402

from captura.parser_mm import (  # noqa: E402
    detectar_inversion,
    parsear_mercado,
    parsear_perfil,
)
from captura.protocolo import (  # noqa: E402
    ProtocoloInvalido,
    condados_del_overview,
    etiquetar_por_posicion,
)

CAMPOS_LISTA = ("id,nombre_completo,brokerage,estado,email_principal,"
                "telefono_e164,unidades_ano,sf_lead_id,sin_llave_dura")
TOPE = 300


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

def guardar(d: dict) -> tuple[int, dict]:
    realtor_id = (d.get("realtor_id") or "").strip()
    sf_lead_id = (d.get("sf_lead_id") or "").strip() or None
    mmi_agent_id = (d.get("mmi_agent_id") or "").strip() or None
    estado = (d.get("estado") or "").strip().upper() or None
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

    condados = [n for n, _ in condados_del_overview(overview)]
    try:
        bloques = etiquetar_por_posicion(ms, condados)
    except ProtocoloInvalido as exc:
        return 400, {"error": str(exc), "condados": condados}

    ahora = dt.datetime.now(dt.timezone.utc).isoformat()
    lote = str(uuid.uuid4())
    avisos: list[str] = []
    filas: list[dict] = []

    def agregar(seccion, texto, *, alcance, nivel=None, etiqueta=None,
                orden=0, extra=None):
        filas.append({
            "upload_batch_id": lote, "uploaded_at": ahora, "alcance": alcance,
            "estado": estado,
            "condado_fips": None,   # el crosswalk nombre->FIPS todavia no
            "sf_lead_id": sf_lead_id, "mmi_agent_id": mmi_agent_id,
            "texto_crudo": texto,
            "parseado": {"seccion": seccion, "orden": orden, "nivel": nivel,
                         "etiqueta_geografica": etiqueta,
                         "condados_del_overview": condados,
                         "realtor_id": realtor_id, **(extra or {})},
            "version_parser": "parser_mm 2026-09-22", "capturado_en": ahora,
        })

    agregar("overview", overview, alcance="perfil",
            extra={"perfil": parsear_perfil(overview)})
    for b in bloques:
        agregar("market_signals", b.texto, alcance="mercado", nivel=b.nivel,
                etiqueta=b.etiqueta, orden=b.orden,
                extra={"metricas": parsear_mercado(b.texto)})

    originators = d.get("originators") or None
    if originators:
        p = parsear_perfil(originators)
        avisos.extend(detectar_inversion(p.get("tab_orig") or []))
        agregar("originators", originators, alcance="perfil",
                extra={"perfil": p})
    else:
        avisos.append("sin bloque de Originators: no se puede detectar si "
                      "trabaja con Everett Financial, que es la exclusion dura")
    if d.get("lenders"):
        agregar("lenders", d["lenders"], alcance="perfil")

    # TRAMPA 1 · las geografias tienen que dar volumenes distintos.
    vols = [f["parseado"]["metricas"].get("total_volume") for f in filas
            if f["parseado"]["seccion"] == "market_signals"]
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

    return 200, {"upload_batch_id": lote, "bloques": len(filas),
                 "condados": condados, "avisos": avisos, "volumenes": vols}


#: ruta -> (funcion, metodo)
RUTAS = {
    "/api/realtors": (realtors, "GET"),
    "/api/geografias": (geografias, "GET"),
    "/api/guardar": (guardar, "POST"),
}
