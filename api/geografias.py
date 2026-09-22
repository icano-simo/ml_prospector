"""La biblioteca: que geografias ya se capturaron y cuantos realtors las usan.

Es la ayuda de operacion que pidio el brief: 25 condados en varios dias, y
nadie se acuerda de cuales lleva.
"""
from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _comun import SinCredenciales, leer, responder  # noqa: E402


class handler(BaseHTTPRequestHandler):  # noqa: N801
    def do_GET(self):  # noqa: N802
        try:
            cod, filas, _ = leer(
                "v_capturas_modelmatch_current",
                "?select=estado,parseado,capturado_en&alcance=eq.mercado"
                "&order=capturado_en.desc&limit=2000")
        except SinCredenciales as exc:
            responder(self, {"error": str(exc)}, 500)
            return
        if cod >= 400:
            responder(self, {"error": "supabase", "detalle": filas}, cod)
            return

        por_geo: dict[str, dict] = {}
        for f in filas or []:
            p = f.get("parseado") or {}
            nivel = p.get("nivel")
            etiqueta = p.get("etiqueta_geografica") or f.get("estado") or "?"
            clave = "%s · %s" % (f.get("estado") or "?", etiqueta) \
                if nivel == "condado" else (f.get("estado") or "?")
            g = por_geo.setdefault(clave, {
                "clave": clave, "nivel": nivel or "estado",
                "estado": f.get("estado"), "etiqueta": etiqueta,
                "capturas": 0, "realtors": set(), "ultima": None})
            g["capturas"] += 1
            if p.get("realtor_id"):
                g["realtors"].add(p["realtor_id"])
            if not g["ultima"] or (f.get("capturado_en") or "") > g["ultima"]:
                g["ultima"] = f.get("capturado_en")

        salida = sorted(
            ({**g, "realtors": len(g["realtors"])} for g in por_geo.values()),
            key=lambda g: (g["nivel"] != "estado", -g["realtors"], g["clave"]))
        responder(self, {"geografias": salida, "total": len(salida)})
