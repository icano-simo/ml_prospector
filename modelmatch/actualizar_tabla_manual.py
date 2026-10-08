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
                                NUESTRO, cargar, columnas_ig, preparar)

MANUAL = os.path.join(RAIZ, ".claude", "skills", "modelmatch-minado",
                      "SKILL.md")
INICIO = "<!-- TABLA-POSICIONES:inicio -->"
FIN = "<!-- TABLA-POSICIONES:fin -->"

ORIGEN = {FICHA: "ficha", APARTE: "aparte", CALC: "calculada"}


def construir() -> str:
    nums = [i for i, c in enumerate(COLUMNAS, 1) if c[3] != NUESTRO]
    nuestras = [i for i, c in enumerate(COLUMNAS, 1) if c[3] == NUESTRO]
    ig = columnas_ig([preparar(f) for f in cargar()])
    total = len(COLUMNAS) + len(ig)
    lineas = [
        INICIO,
        "",
        "#### El plano entero de la hoja *Realtors*",
        "",
        "Son **%d columnas** en una sola tabla, en este orden y sin huecos:"
        % total,
        "",
        "| posiciones | qué | de dónde |",
        "|---|---|---|",
        "| %d a %d | %s | nuestra base: no se le piden a nadie |"
        % (min(nuestras), max(n for n in nuestras if n < min(nums)),
           " · ".join("`%s`" % COLUMNAS[n - 1][1] for n in nuestras
                      if n < min(nums))),
        "| %d a %d | las aprobadas de Model Match, **intercaladas** con el "
        "resto de las nuestras | la tabla de abajo |" % (min(nums), max(nums)),
        "| %d a %d | Instagram | scraper propio, fuera de este manual |"
        % (max(nums) + 1, total),
        "",
        "Las **%d columnas de Instagram no se listan acá y no se listan en "
        "ninguna parte a mano**: el generador las descubre de los datos, así "
        "que una señal nueva del scraper aparece sola. Listarlas sería "
        "prometer que están todas." % len(ig),
        "",
        "#### Las columnas de Model Match, con su número de posición",
        "",
        "**Van de la %d a la %d, pero no son contiguas**: las posiciones %s "
        "son de nuestra base y no se le piden a Model Match."
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
