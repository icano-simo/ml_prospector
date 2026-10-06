"""Paso 4 del manual: banderas y exclusion, por CONTEO. Cuesta 0 creditos.

Por que existe este script aparte, y por que usa `count`:

  · `extraer.py` hace los pasos 1, 2, 3 y 5. El 4 quedaba en dos scripts
    sueltos --`mix_prestamos.py` y `everett.py`-- que se corrian a mano. Un
    lote nuevo quedaba con las banderas en `no` SIN haberse comprobado, que
    es dato falso: «no produce FHA» y «no trabaja con la casa» afirmados
    sobre alguien a quien nadie le pregunto;
  · y esos dos usan `POST /v1/agents`, que cobra 1 por FILA. El manual manda
    `POST /v1/agents/count`, que devuelve un numero y **no cobra**. La
    diferencia no es de estilo: el mix de tipo de prestamo costo 1.207
    creditos haciendolo con la lista, y con conteos cuesta 0.

Escribe el resultado DENTRO del registro de cada realtor, que es donde el
generador del Excel lo busca primero.

Uso:
    python modelmatch/paso4.py            # los que les falta
    python modelmatch/paso4.py --todos    # tambien los que ya lo tienen
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
from modelmatch.everett import CASA  # noqa: E402

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")

#: Los tipos de prestamo, con el nombre de la columna que produce cada uno.
TIPOS = (("fha", "hace_fha"), ("conventional", "hace_convencional"),
         ("va", "hace_va"))
#: Los tramos del peso de la relacion con la casa.
TRAMOS = (2, 3, 5, 10, 20)


def cuenta(cuerpo: dict, etiqueta: str) -> int | None:
    """`total` de un conteo. Devuelve None si la llamada fallo."""
    d = llamar("/v1/agents/count", cuerpo, etiqueta=etiqueta, silencioso=True)
    if not isinstance(d, dict):
        return None
    t = d.get("total")
    return int(t) if isinstance(t, (int, float)) else None


def tipo_de_prestamo(mm: str, clave: str) -> str:
    """¿Produce este tipo? SIN umbral de porcentaje.

    El manual lo prohibe expresamente: con `dimension: lender` y sin lender
    fijo, `shareOfUnits` mide la proporcion DENTRO de un bucket de lender
    suelto, no la del agente. Solo el si/no es valido.
    """
    t = cuenta({"flatFilters": {"id": mm},
                "footprint": {"dimension": "lender",
                              "product": {"mix": "loanType", "key": clave}},
                "period": "last24Months"},
               "p4_%s_%s" % (clave, mm))
    return "sin comprobar" if t is None else ("sí" if t >= 1 else "no")


def con_la_casa(mm: str) -> tuple[str, object]:
    """¿Financia con la casa, y con cuantas operaciones?

    `allTime`, no 24 meses: para una exclusion, una operacion de hace tres
    años sigue contando. Con 24 meses daban 28 realtors y con el historial
    completo 79.
    """
    base = cuenta({"flatFilters": {"id": mm},
                   "footprint": {"lender": CASA},
                   "period": "allTime"}, "p4_casa_%s" % mm)
    if base is None:
        return "sin comprobar", ""
    if base < 1:
        return "no", ""
    # Aca el umbral SI significa lo que dice: el lender es explicito.
    alto = 1
    for n in TRAMOS:
        t = cuenta({"flatFilters": {"id": mm},
                    "footprint": {"lender": CASA, "units": {"gte": n}},
                    "period": "allTime"}, "p4_casa%d_%s" % (n, mm))
        if t is None or t < 1:
            break
        alto = n
    return "SÍ", alto


def main() -> None:
    todos = "--todos" in sys.argv
    pendientes = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            f = json.load(fh)
        if not f.get("mm_id"):
            continue                       # no identificado: no se comprueba
        if f.get("paso4_en") and not todos:
            continue
        pendientes.append((a, f))

    s0 = saldo()
    print("realtors con id: a los que les falta el paso 4: %d" % len(pendientes))
    print("saldo: %s · este paso NO debe gastar nada" % s0)
    print("")

    con_casa = 0
    for i, (ruta, f) in enumerate(pendientes, 1):
        mm = f["mm_id"]
        for clave, columna in TIPOS:
            f[columna] = tipo_de_prestamo(mm, clave)
        f["trabaja_con_la_casa"], f["ops_con_la_casa"] = con_la_casa(mm)
        f["paso4_en"] = dt.datetime.now(dt.timezone.utc).isoformat()
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(f, fh, ensure_ascii=False, indent=1)
        if f["trabaja_con_la_casa"] == "SÍ":
            con_casa += 1
        if i % 20 == 0 or i == len(pendientes):
            print("   %4d/%d · con la casa hasta ahora: %d · saldo %s"
                  % (i, len(pendientes), con_casa, saldo()))

    s1 = saldo()
    gasto = None if None in (s0, s1) else round(s0 - s1, 2)
    print("")
    print("con la casa: %d de %d" % (con_casa, len(pendientes)))
    print("gasto: %s creditos  %s"
          % (gasto, "OK, el paso 4 es gratis" if gasto == 0
             else "⚠ DEBIA SER 0 — revisar"))


if __name__ == "__main__":
    main()
