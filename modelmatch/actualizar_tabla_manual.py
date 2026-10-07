"""Regenera la tabla de posiciones del manual desde COLUMNAS. Cero llamadas.

La tabla de «las N columnas con su numero» se desfasa cada vez que se agrega
una columna, y una tabla de posiciones desfasada es peor que ninguna: manda al
agente a la columna equivocada. Pegarla a mano ya fallo.

Asi que se genera. El manual lleva dos marcas y todo lo que hay entre ellas se
reemplaza; el resto del archivo no se toca.

Uso:
    python modelmatch/actualizar_tabla_manual.py
"""
from __future__ import annotations

import io
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.a_excel import (APARTE, CALC, COLUMNAS, FICHA,  # noqa: E402
                                NUESTRO)

MANUAL = os.path.join(RAIZ, ".claude", "skills", "modelmatch-minado",
                      "SKILL.md")
INICIO = "<!-- TABLA-POSICIONES:inicio -->"
FIN = "<!-- TABLA-POSICIONES:fin -->"

ORIGEN = {FICHA: "ficha", APARTE: "aparte", CALC: "calculada"}


def construir() -> str:
    nums = [i for i, c in enumerate(COLUMNAS, 1) if c[3] != NUESTRO]
    nuestras = [i for i, c in enumerate(COLUMNAS, 1) if c[3] == NUESTRO]
    lineas = [
        INICIO,
        "",
        "En la hoja *Realtors*. **Van de la %d a la %d, pero no son "
        "contiguas**: las posiciones %s son de nuestra base y no se le piden "
        "a Model Match."
        % (min(nums), max(nums),
           ", ".join(str(n) for n in nuestras if min(nums) < n < max(nums))),
        "",
        "| nº | encabezado exacto | origen |",
        "|---|---|---|",
    ]
    for i, (_clave, titulo, _an, fuente, _sig) in enumerate(COLUMNAS, 1):
        if fuente == NUESTRO:
            continue
        lineas.append("| %d | `%s` | %s |" % (i, titulo, ORIGEN[fuente]))
    lineas += ["", FIN]
    return "\n".join(lineas)


def main() -> None:
    texto = io.open(MANUAL, encoding="utf-8").read()
    if INICIO not in texto or FIN not in texto:
        raise SystemExit(
            "el manual no tiene las marcas %s / %s alrededor de la tabla de "
            "posiciones. Ponerlas una vez y este script la mantiene."
            % (INICIO, FIN))
    antes = texto[:texto.index(INICIO)]
    despues = texto[texto.index(FIN) + len(FIN):]
    nuevo = antes + construir() + despues
    io.open(MANUAL, "w", encoding="utf-8", newline="\n").write(nuevo)

    n_mm = sum(1 for c in COLUMNAS if c[3] in (FICHA, APARTE))
    n_calc = sum(1 for c in COLUMNAS if c[3] == CALC)
    print("tabla regenerada · %d columnas (%d de la API + %d calculadas)"
          % (n_mm + n_calc, n_mm, n_calc))


if __name__ == "__main__":
    main()
