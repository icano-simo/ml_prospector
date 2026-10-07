"""Cada campo de la ficha: ¿lo traemos? ¿es derivable? ¿se puede contar gratis?

Cero llamadas: lee la ficha ya pagada del crudo y la cruza contra tres cosas.

  1. las columnas que hoy van al Excel;
  2. los `flatFilters` que acepta `/v1/agents`, que son los MISMOS que acepta
     `/v1/agents/count` -- y contar no cobra. Si un campo esta ahi, se puede
     acorralar su valor gratis;
  3. la aritmetica: varios `average_*` de `scored` son solo un cociente de dos
     campos que ya traemos, asi que no hacen falta ni llamadas ni conteos.

La distincion importa porque las tres respuestas llevan a acciones distintas:
derivable = calcular, contable = preguntar gratis, ninguna = o se paga la
ficha o no se tiene.
"""
from __future__ import annotations

import glob
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.a_excel import APARTE, COLUMNAS, FICHA  # noqa: E402

CRUDO = os.path.join(RAIZ, "data", "raw")

#: Los `flatFilters` de agentes, de la guia del MCP. Todo lo que este aqui se
#: puede acorralar con `count`, que es gratis.
FILTROS = {
    "id", "modelMatchId", "name", "firstName", "lastName", "email",
    "licenseNumber", "office", "state", "city", "zip", "county", "geoPoint",
    "volume", "units", "avgSalePrice",
    "buyerVolume", "buyerUnits", "sellerVolume", "sellerUnits",
    "dualVolume", "dualUnits",
    "mortgagedBuyerVolume", "mortgagedBuyerUnits",
    "mortgagedSellerVolume", "mortgagedSellerUnits",
    "mortgagedDualVolume", "mortgagedDualUnits",
    "avgMortgagedLoanAmount", "percentVolumeMortgaged",
    "percentUnitsMortgaged", "totalOriginatorsWorkedWith",
    "totalLendersWorkedWith", "totalCompaniesWorkedWith", "producersOnly",
}

#: Campo de `scored` -> el filtro equivalente, cuando el nombre no coincide.
EQUIVALE = {
    "total_buyer_side_units": "buyerUnits",
    "total_buyer_side_volume": "buyerVolume",
    "total_seller_side_units": "sellerUnits",
    "total_seller_side_volume": "sellerVolume",
    "total_dual_side_units": "dualUnits",
    "total_dual_side_volume": "dualVolume",
    "total_mortgaged_buyer_units": "mortgagedBuyerUnits",
    "total_mortgaged_buyer_volume": "mortgagedBuyerVolume",
    "total_mortgaged_listing_units": "mortgagedSellerUnits",
    "total_mortgaged_listing_volume": "mortgagedSellerVolume",
    "total_mortgaged_dual_units": "mortgagedDualUnits",
    "total_mortgaged_dual_volume": "mortgagedDualVolume",
    "total_percent_units_mortgaged": "percentUnitsMortgaged",
    "total_percent_volume_mortgaged": "percentVolumeMortgaged",
    "average_mortgaged_loan_amount": "avgMortgagedLoanAmount",
    "average_sold_price": "avgSalePrice",
    "total_sold_units": "units",
    "total_sale_price": "volume",
    "total_originators_worked_with": "totalOriginatorsWorkedWith",
    "total_lenders_worked_with": "totalLendersWorkedWith",
    "total_companies_worked_with": "totalCompaniesWorkedWith",
}

#: (campo, numerador, denominador): un cociente de campos que ya traemos.
COCIENTES = [
    ("average_buyer_side_volume", "buyerVolume", "buyerUnits"),
    ("average_seller_side_volume", "sellerVolume", "sellerUnits"),
    ("average_dual_side_volume", "dualVolume", "dualUnits"),
    ("average_listing_amount", "sellerVolume", "sellerUnits"),
    ("average_mortgaged_buyer_volume",
     "scored.total_mortgaged_buyer_volume", "scored.total_mortgaged_buyer_units"),
    ("average_mortgaged_listing_volume",
     "scored.total_mortgaged_listing_volume",
     "scored.total_mortgaged_listing_units"),
    ("average_mortgaged_dual_volume",
     "scored.total_mortgaged_dual_volume", "scored.total_mortgaged_dual_units"),
    ("average_sold_price", "volume", "units"),
]

#: Lo que el Excel ya trae, por el campo de la API del que sale.
YA_EN_EXCEL = {
    "id", "office", "email", "phone", "linkedProfileCount", "city", "state",
    "zip", "licenseNumber", "units", "volume", "avgSoldPrice", "buyerUnits",
    "buyerVolume", "sellerUnits", "sellerVolume", "dualUnits",
    "totalLendersWorkedWith", "totalOriginatorsWorkedWith",
    "totalCompaniesWorkedWith",
    "scored.total_mortgaged_buyer_units",
    "scored.total_mortgaged_buyer_volume",
    "scored.total_mortgaged_listing_units",
    "scored.total_percent_units_mortgaged",
    "scored.total_percent_volume_mortgaged",
    "scored.average_mortgaged_loan_amount",
}


def valor(det: dict, ruta: str):
    if ruta.startswith("scored."):
        return (det.get("scored") or {}).get(ruta[7:])
    return det.get(ruta)


def ficha(mm: str | None = None) -> dict:
    """La ficha guardada. Con `mm`, la de ese agente; si no, cualquiera.

    Los valores que se imprimen son de UN agente, pero el analisis es sobre
    los CAMPOS, que son los mismos para todos.
    """
    mejor = None
    for a in sorted(glob.glob(os.path.join(CRUDO, "mm_agent_detalle_*.json"))
                    + glob.glob(os.path.join(CRUDO, "mm_det_*.json"))):
        with open(a, encoding="utf-8") as fh:
            d = json.load(fh)
        data = d.get("data")
        if not (isinstance(data, dict) and data.get("scored")):
            continue
        if mm and data.get("id") != mm:
            continue
        mejor = data
        if mm:
            break
    return mejor or {}


def main() -> None:
    pedido = next((a for a in sys.argv[1:] if a.startswith("mma_")), None)
    det = ficha(pedido)
    if not det:
        raise SystemExit("no hay ficha guardada%s en data/raw"
                         % (" de %s" % pedido if pedido else ""))
    print("ficha de: %s · %d campos de primer nivel + %d en `scored`"
          % (det.get("fullName"), len(det) - 1, len(det.get("scored") or {})))

    cociente_de = {c[0]: (c[1], c[2]) for c in COCIENTES}
    filas = []
    for raiz, campos in (("", [k for k in det if k != "scored"]),
                         ("scored.", list((det.get("scored") or {})))):
        for k in campos:
            ruta = raiz + k
            v = valor(det, ruta)
            en_excel = ruta in YA_EN_EXCEL
            filtro = k if k in FILTROS else EQUIVALE.get(k)
            cont = filtro in FILTROS if filtro else False
            filas.append((ruta, v, en_excel, cont, filtro,
                          cociente_de.get(k)))

    print("")
    print("══ LO QUE NO TRAEMOS Y SE PUEDE CONTAR GRATIS ══")
    n = 0
    for ruta, v, en_excel, cont, filtro, coc in filas:
        if en_excel or not cont or coc:
            continue
        n += 1
        print("   %-42s %-14s  filtro: %s"
              % (ruta, str(v)[:14], filtro))
    if not n:
        print("   (ninguno)")

    print("")
    print("══ LO QUE NO TRAEMOS Y ES UN COCIENTE DE LO QUE YA TENEMOS ══")
    print("   (no hace falta ni llamada ni conteo: se calcula)")
    for ruta, v, en_excel, cont, filtro, coc in filas:
        if en_excel or not coc:
            continue
        num, den = coc
        a, b = valor(det, num), valor(det, den)
        calc = round(a / b) if (isinstance(a, (int, float))
                                and isinstance(b, (int, float)) and b) else None
        marca = "coincide" if calc == v else ("≈ %s" % calc)
        print("   %-42s %-10s = %s / %s   %s"
              % (ruta, str(v)[:10], num, den, marca))

    print("")
    print("══ LO QUE NO TRAEMOS Y NO SE PUEDE CONTAR NI DERIVAR ══")
    print("   (o se paga la ficha, o no se tiene)")
    for ruta, v, en_excel, cont, filtro, coc in filas:
        if en_excel or cont or coc:
            continue
        print("   %-42s %s" % (ruta, str(v)[:40]))


if __name__ == "__main__":
    main()
