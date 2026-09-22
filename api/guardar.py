"""Guarda una captura de Model Match desde la ficha de un realtor.

Se parte del realtor, no de la captura: la llave sale de la fila, no se escribe
a mano. Eso resuelve solo el problema de a quien pertenece lo que se pega.

Lo que NO cambia respecto de la pantalla local: la validacion de conteo y el
etiquetado por posicion. El bloque 1 es el estado y del 2 en adelante son los
condados en el orden del Overview, y si el conteo no cuadra no se guarda nada.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import uuid
from http.server import BaseHTTPRequestHandler

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))  # para importar `captura`

from _comun import SinCredenciales, cuerpo_json, escribir, responder  # noqa: E402

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


class handler(BaseHTTPRequestHandler):  # noqa: N801
    def do_POST(self):  # noqa: N802
        d = cuerpo_json(self)
        realtor_id = (d.get("realtor_id") or "").strip()
        sf_lead_id = (d.get("sf_lead_id") or "").strip() or None
        estado = (d.get("estado") or "").strip().upper() or None
        overview = d.get("overview") or ""
        ms = d.get("market_signals") or []
        originators = d.get("originators") or None
        lenders = d.get("lenders") or None

        if not realtor_id:
            responder(self, {"error": "falta realtor_id: se parte del realtor"},
                      400)
            return
        if not overview.strip():
            responder(self, {"error": "el Overview esta vacio"}, 400)
            return

        condados = [n for n, _ in condados_del_overview(overview)]
        try:
            bloques = etiquetar_por_posicion([str(x) for x in ms], condados)
        except ProtocoloInvalido as exc:
            responder(self, {"error": str(exc), "condados": condados}, 400)
            return

        perfil = parsear_perfil(overview)
        mmi_agent_id = (d.get("mmi_agent_id") or "").strip() or None
        avisos = []

        # La llave. Se toma de la fila del realtor, no se escribe a mano; si el
        # realtor no tiene sf_lead_id hace falta el MMI Agent ID.
        if not (sf_lead_id or mmi_agent_id):
            responder(self, {
                "error": ("Este realtor no tiene Lead ID de Salesforce, asi que "
                          "hace falta el MMI Agent ID para poder pegar la "
                          "captura a el. Esta en el perfil de Model Match.")},
                400)
            return

        ahora = dt.datetime.now(dt.timezone.utc).isoformat()
        lote = str(uuid.uuid4())

        filas = []

        def agregar(seccion, texto, *, alcance, nivel=None, etiqueta=None,
                    orden=0, parseado_extra=None):
            filas.append({
                "upload_batch_id": lote,
                "uploaded_at": ahora,
                "alcance": alcance,
                "estado": estado,
                "condado_fips": None,   # el crosswalk nombre->FIPS todavia no
                "sf_lead_id": sf_lead_id,
                "mmi_agent_id": mmi_agent_id,
                "texto_crudo": texto,
                "parseado": {
                    "seccion": seccion, "orden": orden, "nivel": nivel,
                    "etiqueta_geografica": etiqueta,
                    "condados_del_overview": condados,
                    "realtor_id": realtor_id,
                    **(parseado_extra or {}),
                },
                "version_parser": "parser_mm 2026-09-22",
                "capturado_en": ahora,
            })

        agregar("overview", overview, alcance="perfil",
                parseado_extra={"perfil": perfil})

        for b in bloques:
            metricas = parsear_mercado(b.texto)
            agregar("market_signals", b.texto, alcance="mercado",
                    nivel=b.nivel, etiqueta=b.etiqueta, orden=b.orden,
                    parseado_extra={"metricas": metricas})

        if originators:
            p = parsear_perfil(originators)
            inv = detectar_inversion(p.get("tab_orig") or [])
            avisos.extend(inv)
            agregar("originators", originators, alcance="perfil",
                    parseado_extra={"perfil": p})
        else:
            avisos.append(
                "sin bloque de Originators: no se puede detectar si trabaja con "
                "Everett Financial, que es la exclusion dura")
        if lenders:
            agregar("lenders", lenders, alcance="perfil")

        # TRAMPA 1 · las geografias tienen que dar volumenes distintos. Si dan
        # el mismo, se leyo del grafico rodante.
        vols = [f["parseado"]["metricas"].get("total_volume")
                for f in filas if f["parseado"]["seccion"] == "market_signals"]
        vols = [v for v in vols if v is not None]
        if len(vols) > 1 and len(set(vols)) == 1:
            avisos.append(
                "las %d geografias dieron el MISMO volumen (%s). Eso es el "
                "Rolling Monthly Performance, que no respeta el filtro de "
                "ubicacion. Revisar que se copio la seccion Market Overview."
                % (len(vols), vols[0]))

        try:
            cod_lote, _, _ = escribir("upload_batch", [{
                "id": lote, "fuente": "modelmatch",
                "archivo": "mesa de trabajo", "uploaded_at": ahora,
                "es_vigente": True, "filas_esperadas": len(filas),
                "nota": "captura desde la ficha · realtor_id=%s · condados=%s"
                        % (realtor_id, ", ".join(condados) or "ninguno"),
            }], devolver=False)
            if cod_lote >= 400:
                responder(self, {"error": "no se pudo abrir el lote"}, 500)
                return

            cod, datos, _ = escribir("capturas_modelmatch", filas,
                                     devolver=False)
        except SinCredenciales as exc:
            responder(self, {"error": str(exc)}, 500)
            return

        if cod >= 400:
            responder(self, {"error": "no se guardo", "detalle": datos}, cod)
            return

        responder(self, {
            "upload_batch_id": lote,
            "bloques": len(filas),
            "condados": condados,
            "avisos": avisos,
            "volumenes": vols,
        })
