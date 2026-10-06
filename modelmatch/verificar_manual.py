"""¿El manual dice los MISMOS textos exactos que produce el código?

Un manual que escribe «alta, confirmada por teléfono» cuando el código emite
«alta · confirmada por teléfono» no es un manual impreciso: es un manual que
rompe el scoring, porque el scoring filtra por igualdad exacta. Con la coma,
51 realtors perderian su identificacion valida.

Por eso los vocabularios no se escriben a mano en el manual y se cruzan los
dedos: se comprueban. Este script recorre los valores que el codigo PUEDE
emitir en cada columna de vocabulario cerrado, los busca en el texto del
manual, y falla nombrando el que falte.

Uso:
    python modelmatch/verificar_manual.py
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.a_excel import (APARTE, CALC, COLUMNAS, FICHA,  # noqa: E402
                                NUESTRO, cargar, preparar)

MANUAL = os.path.join(RAIZ, ".claude", "skills", "modelmatch-minado",
                      "SKILL.md")

#: Columnas de vocabulario CERRADO: solo pueden tomar estos valores. Si el
#: codigo emite uno que no esta aqui, el manual tampoco lo tendra y este
#: script lo caza.
VOCABULARIOS = {
    "confianza_final": [
        "alta",
        "alta · confirmada por teléfono",
        "contradicha por el teléfono",
        "media",
        "baja",
        "ninguna",
        "no encontrado",
    ],
    "match_criterio": [
        "email_exacto",
        "email_exacto_varios_perfiles",
        "nombre_exacto_y_estado",
        "nombre_y_estado_varios",
        "nombre_exacto_sin_estado",
        "ambiguo",
        "sin_candidatos",
    ],
    "fidelidad": [
        "sin operaciones financiadas atribuidas",
        "CAUTIVO · 1 solo LO",
        "muy concentrado · 2-3 LOs",
        "concentrado · 4-6 LOs",
        "reparte · 7-12 LOs",
        "reparte mucho · 13+ LOs",
    ],
    "revisar_por": [
        "no se encontró en Model Match",
        "identificado solo por nombre y el teléfono NO coincide: puede ser "
        "otra persona con el mismo nombre",
        "identificado solo por nombre, sin confirmar con correo ni teléfono",
    ],
    "telefono_coincide": ["si", "no", "sin_dato"],
    "cambio_de_brokerage": ["si", "no", "sin_dato"],
    "encontrado_txt": ["sí", "NO"],
    "hace_fha": ["sí", "no", "sin comprobar"],
    "trabaja_con_la_casa": ["SÍ", "no", "sin comprobar"],
}


def main() -> None:
    texto = open(MANUAL, encoding="utf-8").read()
    fallos = []

    print("── 1 · vocabularios cerrados ──")
    for col, valores in VOCABULARIOS.items():
        faltan = [v for v in valores if v not in texto]
        print("   %-22s %d valores · faltan %d" % (col, len(valores),
                                                   len(faltan)))
        for v in faltan:
            fallos.append("vocabulario %s: falta %r" % (col, v))

    print("")
    print("── 2 · el codigo no emite valores fuera del vocabulario ──")
    filas = [preparar(f) for f in cargar()]
    for col, valores in VOCABULARIOS.items():
        emitidos = {f.get(col) for f in filas}
        raros = sorted(x for x in emitidos
                       if x not in valores and x not in (None, ""))
        if raros:
            print("   %-22s ⚠ emite %s" % (col, raros))
            for x in raros:
                fallos.append("%s emite %r y no esta en VOCABULARIOS" % (col, x))
        else:
            print("   %-22s ok" % col)

    print("")
    print("── 3 · toda columna esta nombrada en el manual ──")
    for clave, titulo, _an, fuente, _sig in COLUMNAS:
        if fuente == NUESTRO:
            continue
        if "`%s`" % titulo not in texto:
            fallos.append("columna sin nombrar en el manual: %s" % titulo)
    n_mm = sum(1 for c in COLUMNAS if c[3] in (FICHA, APARTE))
    n_calc = sum(1 for c in COLUMNAS if c[3] == CALC)
    print("   de Model Match %d · calculadas %d · total a documentar %d"
          % (n_mm, n_calc, n_mm + n_calc))

    print("")
    if fallos:
        print("FALLA · %d problemas:" % len(fallos))
        for f in fallos:
            print("   · %s" % f)
        raise SystemExit(1)
    print("OK · el manual y el codigo dicen lo mismo, carácter a carácter.")


if __name__ == "__main__":
    main()
