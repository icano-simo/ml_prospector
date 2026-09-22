"""La lista lateral: busca por nombre, brokerage o email, y filtra.

Devuelve solo lo que la lista necesita pintar. El dossier completo se pide por
realtor cuando se abre la ficha: 4.249 filas con todo seria medio mega por
teclazo.
"""
from __future__ import annotations

import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _comun import SinCredenciales, leer, responder  # noqa: E402

CAMPOS = ("id,nombre_completo,brokerage,estado,email_principal,telefono_e164,"
          "unidades_ano,sf_lead_id,sin_llave_dura")
TOPE = 300


class handler(BaseHTTPRequestHandler):  # noqa: N801 - lo exige Vercel
    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        texto = (q.get("q", [""])[0] or "").strip()
        estado = (q.get("estado", [""])[0] or "").strip()
        con_mm = (q.get("mm", [""])[0] or "").strip()

        partes = ["select=" + CAMPOS, "order=nombre_completo.asc",
                  "limit=%d" % TOPE]
        if texto:
            # PostgREST: `or` con ilike sobre los tres campos que el prototipo
            # busca. Se escapan las comas, que separan condiciones.
            t = texto.replace(",", " ").replace("*", "")
            partes.append(
                "or=(nombre_completo.ilike.*{0}*,brokerage.ilike.*{0}*,"
                "email_principal.ilike.*{0}*)".format(urllib.parse.quote(t)))
        if estado:
            partes.append("estado=eq." + urllib.parse.quote(estado))

        try:
            codigo, datos, cabeceras = leer(
                "realtors", "?" + "&".join(partes), rango="0-%d" % (TOPE - 1))
        except SinCredenciales as exc:
            responder(self, {"error": str(exc)}, 500)
            return

        if codigo >= 400:
            responder(self, {"error": "supabase", "detalle": datos}, codigo)
            return

        filas = datos or []

        # Filtro por Model Match: se resuelve aca porque vive en otra tabla y
        # PostgREST no hace el anti-join comodo. Con 300 filas es barato.
        if con_mm in ("si", "no"):
            c2, capturas, _ = leer(
                "capturas_modelmatch",
                "?select=sf_lead_id,mmi_agent_id&alcance=eq.perfil&limit=5000")
            con_captura = {c.get("sf_lead_id") for c in (capturas or [])
                           if c.get("sf_lead_id")}
            if con_mm == "si":
                filas = [f for f in filas if f.get("sf_lead_id") in con_captura]
            else:
                filas = [f for f in filas
                         if f.get("sf_lead_id") not in con_captura]

        rango = cabeceras.get("Content-Range", "")
        total = rango.split("/")[-1] if "/" in rango else str(len(filas))
        responder(self, {
            "filas": filas,
            "mostradas": len(filas),
            "total": total,
            "tope": TOPE,
            "truncado": len(datos or []) >= TOPE,
        })
