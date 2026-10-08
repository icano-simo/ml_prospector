"""Paso 4 del manual: tipo de prestamo, por CONTEO. Cuesta 0 creditos.

Por que existe este script aparte, y por que usa `count`:

  · `extraer.py` hace los pasos 1, 2 y 3. El 4 quedaba en dos scripts
    sueltos --`mix_prestamos.py` y `everett.py`-- que se corrian a mano. Un
    lote nuevo quedaba con las banderas en `no` SIN haberse comprobado, que
    es dato falso: «no produce FHA» afirmado sobre alguien a quien nadie le
    pregunto;
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

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")

#: Los tipos de prestamo, con el nombre de la columna que produce cada uno.
TIPOS = (("fha", "hace_fha"), ("conventional", "hace_convencional"),
         ("va", "hace_va"))

# Everett NO se pregunta aca. Este script tenia un segundo bloque que daba
# «al menos N operaciones» con N = 2, 3, 5, 10, 20, y producia un campo
# --`ops_con_la_casa`-- que ya no es ninguna columna. `everett_bandas.py` lo
# reemplazo con bandas excluyentes que dan el numero en vez de una cota, y en
# dos ventanas en vez de una. Dejar las dos vias vivas significa dos respuestas
# distintas a la misma pregunta en el mismo registro.


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

    con_fha = 0
    for i, (ruta, f) in enumerate(pendientes, 1):
        mm = f["mm_id"]
        for clave, columna in TIPOS:
            f[columna] = tipo_de_prestamo(mm, clave)
        f["paso4_en"] = dt.datetime.now(dt.timezone.utc).isoformat()
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(f, fh, ensure_ascii=False, indent=1)
        if f.get("hace_fha") == "sí":
            con_fha += 1
        if i % 20 == 0 or i == len(pendientes):
            print("   %4d/%d · con FHA hasta ahora: %d · saldo %s"
                  % (i, len(pendientes), con_fha, saldo()))

    s1 = saldo()
    gasto = None if None in (s0, s1) else round(s0 - s1, 2)
    print("")
    print("con FHA: %d de %d" % (con_fha, len(pendientes)))
    print("Everett va aparte: python modelmatch/everett_bandas.py")
    print("gasto: %s creditos  %s"
          % (gasto, "OK, el paso 4 es gratis" if gasto == 0
             else "⚠ DEBIA SER 0 — revisar"))


if __name__ == "__main__":
    main()
