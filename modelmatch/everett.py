"""¿Cuales de los 298 ya financian con la casa? La exclusion, barata.

El listado de lenders de un agente cuesta 1 credito POR FILA, y un agente con
43 lenders cuesta 43: preguntarle a cada uno «¿con quien trabajas?» no entra
en el presupuesto. Pero la pregunta que importa no es esa, es la inversa:
«¿quien de estos trabaja con Everett?». Y esa se contesta con `footprint`, que
filtra del lado del servidor y **solo cobra las filas que devuelve**.

Si de los 298 hay 20 con Everett, cuesta 20 creditos. Si no hay ninguno, 0.

Los ids del diccionario de lenders de la casa salen de la guia del MCP.
`lending_mortgage_supreme` NO es la casa: es «Supreme Mortgage Lending Inc.»,
otra empresa con un nombre parecido. Confundirlas excluiria a gente que si se
puede trabajar.
"""
from __future__ import annotations

import glob
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, saldo  # noqa: E402

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
SALIDA = os.path.join(RAIZ, "data", "trabajo", "everett.json")

#: Everett Financial, Inc. (NMLS 2129) y sus variantes en el diccionario.
CASA = ["everett_financial", "everett_financial_texas",
        "dba_everett_financial_financial_supr",
        "dba_everett_financial_lending_spureme",
        "everett_financial_incdba_lending_supreme",
        "dba_everett_financial_superme",
        "dba_dupreme_everett_financial_lending"]

LOTE = 100


def main() -> None:
    ids, nombre_de = [], {}
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        f = json.load(open(a, encoding="utf-8"))
        if f.get("mm_id"):
            ids.append(f["mm_id"])
            nombre_de[f["mm_id"]] = f.get("nombre")

    print("agentes identificados en Model Match: %d" % len(ids))
    s0 = saldo()
    print("saldo: %s" % s0)

    con_casa = []
    for i in range(0, len(ids), LOTE):
        trozo = ids[i:i + LOTE]
        d = llamar("/v1/agents",
                   {"flatFilters": {"id": trozo},
                    "footprint": {"lender": CASA},
                    "period": "last24Months",
                    "pagination": {"size": 100}},
                   etiqueta="everett_lote%d" % (i // LOTE), silencioso=True)
        filas = (d or {}).get("data") or []
        print("   lote %d (%d ids) · con la casa: %d"
              % (i // LOTE + 1, len(trozo), len(filas)))
        for f in filas:
            con_casa.append({
                "mm_id": f.get("id"), "nombre_nuestro": nombre_de.get(f.get("id")),
                "mm_nombre": f.get("fullName"), "office": f.get("office"),
                "unidades": f.get("units"), "volumen": f.get("volume")})

    with open(SALIDA, "w", encoding="utf-8") as fh:
        json.dump(con_casa, fh, ensure_ascii=False, indent=1)

    s1 = saldo()
    print("")
    print("CON EVERETT (la casa): %d de %d" % (len(con_casa), len(ids)))
    for c in con_casa:
        print("   %-28s %-34s %s u"
              % ((c["nombre_nuestro"] or "")[:28], (c["office"] or "")[:34],
                 c["unidades"]))
    print("")
    print("costo: %s creditos" % ("?" if None in (s0, s1) else round(s0 - s1, 2)))
    print("guardado en %s" % SALIDA)


if __name__ == "__main__":
    main()
