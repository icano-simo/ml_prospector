"""Los condados del ACS, de Postgres a un archivo plano.

**No hay un crudo del API en disco.** `geo/census.py` consulta api.census.gov
y `supabase/cargar_census.py` inserta directo en `pacs.census_condados`: entre
la respuesta y la base no queda archivo. Lo mas cercano al crudo son los
valores tal como llegaron, que viven en la columna `variables`.

Este script los saca. Dos reglas de forma, y las dos importan:

  · **lo crudo y lo derivado van marcados.** Las 29 variables del ACS salen
    con su nombre pelado; las 19 que calculamos nosotros salen con prefijo
    `der_`. Mezclarlas sin marcar es como se termina citando un porcentaje
    nuestro como si fuera del Census.
  · **se pagina.** `pacs.census_condados` tiene 2.261 filas y PostgREST
    devuelve 1.000 sin avisar. Una exportacion que no pagine entrega dos
    tercios del pais y parece completa.

Uso:
    python geo/exportar_census.py             # CSV
    python geo/exportar_census.py --xlsx      # ademas, un Excel
"""
from __future__ import annotations

import csv
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from supabase.config import cargar_env  # noqa: E402

cargar_env()
from _comun import leer  # noqa: E402

SALIDA = os.path.join(RAIZ, "data", "salida")
FIJAS = ("estado", "condado_fips", "nombre", "anio_acs")


def todos() -> list[dict]:
    filas, desde, paso = [], 0, 1000
    while True:
        cod, tr, _ = leer("census_condados",
                          "?select=estado,condado_fips,nombre,anio_acs,"
                          "variables&order=estado.asc,condado_fips.asc"
                          "&limit=%d&offset=%d" % (paso, desde))
        if cod >= 400:
            raise SystemExit("census_condados: %s" % str(tr)[:300])
        filas.extend(tr or [])
        print("   %d filas..." % len(filas))
        if len(tr or []) < paso:
            return filas
        desde += paso


def main() -> None:
    print("leyendo pacs.census_condados (paginado)")
    filas = todos()

    crudas: list[str] = []
    derivadas: list[str] = []
    for f in filas:
        v = f.get("variables") or {}
        for k in v:
            if k == "_derivadas":
                continue
            if k not in crudas:
                crudas.append(k)
        for k in (v.get("_derivadas") or {}):
            if k not in derivadas:
                derivadas.append(k)
    crudas.sort()
    derivadas.sort()

    cabecera = (list(FIJAS) + crudas + ["der_%s" % k for k in derivadas])
    salida = []
    for f in filas:
        v = f.get("variables") or {}
        der = v.get("_derivadas") or {}
        salida.append([f.get(k) for k in FIJAS]
                      + [v.get(k) for k in crudas]
                      + [der.get(k) for k in derivadas])

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, "census_condados_acs.csv")
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cabecera)
        w.writerows(salida)

    print("")
    print("condados      : %d" % len(salida))
    print("estados       : %d" % len({f["estado"] for f in filas}))
    print("años ACS      : %s" % sorted({f["anio_acs"] for f in filas}))
    print("columnas      : %d  (%d fijas + %d del ACS + %d derivadas)"
          % (len(cabecera), len(FIJAS), len(crudas), len(derivadas)))
    print("guardado en %s" % ruta)

    if "--xlsx" in sys.argv:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "Condados ACS"
        ws.append(cabecera)
        for fila in salida:
            ws.append(fila)
        # Las derivadas en otro color: que se vea de un vistazo que ese
        # numero lo calculamos nosotros y no viene del Census.
        for i, nombre in enumerate(cabecera, 1):
            c = ws.cell(row=1, column=i)
            c.font = Font(bold=True, color="FFFFFF", size=10)
            c.fill = PatternFill("solid", fgColor=(
                "7F6000" if nombre.startswith("der_") else "1F3864"))
        ws.freeze_panes = "E2"
        ws.auto_filter.ref = ws.dimensions
        rx = os.path.join(SALIDA, "census_condados_acs.xlsx")
        wb.save(rx)
        print("guardado en %s" % rx)


if __name__ == "__main__":
    main()
