"""Historical units: unidades del lado comprador, año por año. Cuesta 0.

`buyerUnits` es filtro con rango y `period` acepta años sueltos, asi que
`/v1/agents/count` contesta «¿tuvo entre 3 y 5 compras en 2024?» sin cobrar.
Acorralando con bandas sale el numero.

⛔ **El año EN CURSO no se pide como año literal.** Esta medido: para un
agente con mas de cinco operaciones en `yearToDate`, `period: "2026"` devuelve
0. El bucket del año corriente no esta poblado, y pedirlo asi hace creer que
el realtor dejo de producir -- un cero que parece un dato. El año en curso va
por `yearToDate`.

De los años sale el primer año con produccion, y de ahi la antiguedad
aproximada. Es un PISO: 2017 es el año mas viejo del enum, asi que quien
empezo antes sale subestimado y su fila lo dice.

Uso:
    python modelmatch/anios_buyside.py          # los que les falta
    python modelmatch/anios_buyside.py --todos
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, saldo  # noqa: E402

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
ANIO = dt.date.today().year
#: Años COMPLETOS. El actual se pide como `yearToDate`, no como año.
PERIODOS = [str(a) for a in range(2017, ANIO)] + ["yearToDate", "last3Months"]
#: Finas abajo, gruesas arriba: la diferencia entre 2 y 3 decide, la de 60 a
#: 70 no.
BANDAS = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 7), (7, 10), (10, 15),
          (15, 20), (20, 30), (30, 50), (50, 100), (100, None)]


def cuenta(mm: str, periodo: str, gte: int, lt) -> int | None:
    rango: dict = {"gte": gte}
    if lt is not None:
        rango["lt"] = lt
    d = llamar("/v1/agents/count",
               {"flatFilters": {"id": mm, "buyerUnits": rango},
                "period": periodo},
               etiqueta="ab_%s_%s_%s" % (mm, periodo, gte), silencioso=True)
    if not isinstance(d, dict) or not isinstance(d.get("total"), (int, float)):
        return None
    return int(d["total"])


def unidades(mm: str, periodo: str):
    """El numero exacto, una banda, o '' si no produjo nada ese periodo."""
    if (cuenta(mm, periodo, 1, None) or 0) < 1:
        return ""
    for gte, lt in BANDAS:
        if cuenta(mm, periodo, gte, lt) == 1:
            if lt is None:
                return "%d+" % gte
            return gte if lt == gte + 1 else "%d-%d" % (gte, lt - 1)
    return "100+"


def main() -> None:
    todos = "--todos" in sys.argv
    pendientes = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            f = json.load(fh)
        if f.get("mm_id") and (todos or not f.get("anios_buyside")):
            pendientes.append((a, f))

    s0 = saldo()
    print("realtors a los que les falta la produccion por año: %d"
          % len(pendientes))
    print("periodos por realtor: %d · saldo %s · esto NO debe gastar nada"
          % (len(PERIODOS), s0))
    print("")

    for i, (ruta, f) in enumerate(pendientes, 1):
        mm = f["mm_id"]
        anios = {}
        for p in PERIODOS:
            anios[p] = unidades(mm, p)
        f["anios_buyside"] = anios
        f["anios_buyside_en"] = dt.datetime.now(dt.timezone.utc).isoformat()
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(f, fh, ensure_ascii=False, indent=1)
        if i % 20 == 0 or i == len(pendientes):
            con = sum(1 for v in anios.values() if v != "")
            print("   %4d/%d · ultimo: %d periodos con produccion · saldo %s"
                  % (i, len(pendientes), con, saldo()))

    s1 = saldo()
    gasto = None if None in (s0, s1) else round(s0 - s1, 2)
    print("")
    print("gasto: %s  %s" % (gasto, "OK, fue gratis" if gasto == 0
                             else "⚠ COBRO — revisar"))


if __name__ == "__main__":
    main()
