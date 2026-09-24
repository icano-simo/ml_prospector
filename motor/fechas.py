"""Una fecha para leer, no para ordenar.

`2026-09-14` es una fecha para ordenar. En una ficha que alguien mira treinta
segundos antes de llamar se lee como un código, y eso fue justo lo que Isabella
marcó al ver la ficha dentro de la app.

Está en `motor/` y no en `api/rutas.py` --que es donde nació-- porque
`motor/veredicto.py` también necesita escribir una fecha que alguien va a leer
(«hay que volver a capturar Transactions después del …»), y el motor no importa
de la API: es al revés.
"""
from __future__ import annotations

#: Los meses en la forma en que se leen.
MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun",
                "jul", "ago", "sep", "oct", "nov", "dic")


def dia_y_mes(iso) -> str:
    """`2026-03-19` -> `19 mar`. Vacío si no es una fecha.

    Sin el año, para las listas donde el año ya está dicho arriba --los LOs de
    un lender, todos dentro de la misma ventana de 14 meses--. Es como lo
    escribe la maqueta.
    """
    largo = fecha_legible(iso)
    partes = largo.split()
    return " ".join(partes[:2]) if len(partes) == 3 else ""


def fecha_legible(iso) -> str:
    """`2026-09-14` -> `14 sep 2026`.

    Lo que NO es una fecha vuelve tal cual, entero. La primera versión cortaba
    a diez caracteres antes de mirar, así que «cierre + 35 días» salía como
    «cierre + 3»: un texto que no era una fecha, mutilado por el formateador de
    fechas. El corte va después de comprobar, no antes.
    """
    s = str(iso or "").strip()
    partes = s[:10].split("-")
    if len(partes) != 3 or not all(p.isdigit() for p in partes):
        return s
    try:
        return "%d %s %s" % (int(partes[2]),
                             MESES_CORTOS[int(partes[1]) - 1], partes[0])
    except (IndexError, ValueError):
        return s
