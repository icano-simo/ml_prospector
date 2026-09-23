"""Reemplaza los handles reales que se colaron en el codigo y las pruebas.

La correccion C11 pedia fixtures sin handles de personas porque el repo es
PUBLICO. Los fixtures salieron bien; los que se colaron son los docstrings y
los comentarios que citan el caso que encontro cada regla -- incluido
`@jeen.yim`, que es un tercero que no tiene nada que ver con el proyecto.

El comentario que dice de donde salio una regla es valioso y se conserva: lo
que se va es el identificador de la persona.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: real -> anonimo. El sufijo describe QUE era, que es lo unico que aporta.
CAMBIOS = {
    "@ezequiel_bolanos_": "`perfil_R` (realtor con varios lenders)",
    "@realtor_geo": "`perfil_V` (realtor de Virginia)",
    "@jeen.yim": "@un_loan_officer",
    "@jenniferwyattloanofficer": "@la_loan_officer",
    "@thepianateam": "`perfil_D` (doble licencia)",
}

ARCHIVOS = (
    "tests/test_ig_clase_perfil.py",
    "tests/test_ig_senales.py",
    "ingest/instagram/lexico.py",
    "ingest/instagram/clase_perfil.py",
    "ingest/instagram/senales.py",
)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    total = 0
    for rel in ARCHIVOS:
        ruta = os.path.join(RAIZ, rel)
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8") as fh:
            texto = original = fh.read()
        for real, anonimo in CAMBIOS.items():
            if real in texto:
                n = texto.count(real)
                texto = texto.replace(real, anonimo)
                print("   %-34s %-22s x%d" % (rel, real, n))
                total += n
        if texto != original:
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(texto)

    print("")
    print("reemplazos: %d" % total)

    # La verificacion: que no quede ninguno. Que el script saliera con 0 no
    # prueba que aplico -- hay que preguntarle al archivo.
    quedan = []
    for rel in ARCHIVOS:
        ruta = os.path.join(RAIZ, rel)
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8") as fh:
            texto = fh.read()
        for real in CAMBIOS:
            if real in texto:
                quedan.append((rel, real))
    if quedan:
        print("QUEDAN SIN REEMPLAZAR: %s" % quedan)
        return 1
    print("verificado sobre los archivos: no queda ningun handle real")
    return 0


if __name__ == "__main__":
    sys.exit(main())
