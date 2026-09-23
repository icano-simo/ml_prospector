"""Reemplaza los handles reales que se colaron en el codigo y las pruebas.

La correccion C11 pedia fixtures sin handles de personas porque el repo es
PUBLICO. Los fixtures salieron bien; los que se colaron fueron los docstrings y
los comentarios que citan el caso que encontro cada regla -- incluido el handle
de un tercero que no tiene nada que ver con el proyecto.

El comentario que dice de donde salio una regla es valioso y se conserva: lo
que se va es el identificador de la persona.

**El mapeo NO vive aqui.** La primera version lo traia en el codigo, o sea que
el script escrito para sacar los handles del repo los metia de vuelta --
incluido el del tercero. Vive en `Data_inputIA/2A/handles_a_anonimizar.json`,
que `.gitignore` ya excluye.

    python scripts/anonimizar_handles.py           # aplica y verifica
    python scripts/anonimizar_handles.py --revisar # solo comprueba

Sin el archivo de mapeo no falla: no hay nada que reemplazar, y lo dice. Eso
permite que la verificacion corra en una maquina que no tenga el archivo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPEO = os.path.join(RAIZ, "Data_inputIA", "2A", "handles_a_anonimizar.json")

ARCHIVOS = (
    "tests/test_ig_clase_perfil.py",
    "tests/test_ig_senales.py",
    "ingest/instagram/lexico.py",
    "ingest/instagram/clase_perfil.py",
    "ingest/instagram/senales.py",
)


def cargar_mapeo() -> dict:
    if not os.path.exists(MAPEO):
        return {}
    with open(MAPEO, encoding="utf-8") as fh:
        return json.load(fh).get("cambios") or {}


def en_el_arbol(aguja: str) -> list[str]:
    """`git grep` sobre TODO el arbol, no solo sobre `ARCHIVOS`.

    Es la diferencia entre «los limpie donde me acorde de mirar» y «no quedan».
    """
    try:
        r = subprocess.run(["git", "grep", "-l", "-F", "--", aguja],
                           cwd=RAIZ, capture_output=True, text=True)
    except FileNotFoundError:
        return []
    return [l for l in r.stdout.splitlines() if l.strip()]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    solo_revisar = "--revisar" in sys.argv
    cambios = cargar_mapeo()

    if not cambios:
        print("sin archivo de mapeo (%s)" % os.path.relpath(MAPEO, RAIZ))
        print("no hay nada que reemplazar; se verifica igual")
    elif not solo_revisar:
        total = 0
        for rel in ARCHIVOS:
            ruta = os.path.join(RAIZ, rel)
            if not os.path.exists(ruta):
                continue
            with open(ruta, encoding="utf-8") as fh:
                texto = original = fh.read()
            for real, anonimo in cambios.items():
                if real in texto:
                    n = texto.count(real)
                    texto = texto.replace(real, anonimo)
                    print("   %-34s %-26s x%d" % (rel, real, n))
                    total += n
            if texto != original:
                with open(ruta, "w", encoding="utf-8") as fh:
                    fh.write(texto)
        print("")
        print("reemplazos: %d" % total)

    # ── La verificacion, con `git grep` sobre el arbol entero ───────────────
    print("")
    print("VERIFICACION · git grep sobre todo el arbol")
    quedan = []
    for real in cambios:
        archivos = [a for a in en_el_arbol(real)
                    if not a.startswith("Data_inputIA/")]
        if archivos:
            quedan.append((real, archivos))
            print("   QUEDA %-26s en %s" % (real, ", ".join(archivos)))
    if quedan:
        print("")
        print("FALLA: %d handles siguen en el arbol" % len(quedan))
        return 1
    print("   ningun handle real en el arbol versionado"
          if cambios else "   (sin mapeo: no se comprobo nada)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
