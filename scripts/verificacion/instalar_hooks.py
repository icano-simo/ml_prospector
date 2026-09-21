"""Instala los hooks de git de este repo. Idempotente.

    python scripts/verificacion/instalar_hooks.py

Escribe .git/hooks/pre-commit, que corre sin_pii_versionada.py. Los hooks no se
versionan, asi que cada clon tiene que correr esto una vez. Si el hook ya existe
y no es el nuestro, no lo sobrescribe: avisa y sale con 1.
"""
from __future__ import annotations

import os
import subprocess
import sys

MARCA = "# ml_prospector:pre-commit:sin_pii_versionada"

CUERPO = """#!/bin/sh
{marca}
# Generado por scripts/verificacion/instalar_hooks.py -- no editar a mano.
python scripts/verificacion/sin_pii_versionada.py || exit 1
""".format(marca=MARCA)


def main() -> int:
    raiz = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    hooks_dir = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not os.path.isabs(hooks_dir):
        hooks_dir = os.path.join(raiz, hooks_dir)

    os.makedirs(hooks_dir, exist_ok=True)
    destino = os.path.join(hooks_dir, "pre-commit")

    if os.path.exists(destino):
        with open(destino, "r", encoding="utf-8", errors="replace") as fh:
            actual = fh.read()
        if MARCA not in actual:
            print("Ya hay un pre-commit que no es el nuestro: %s" % destino)
            print("No lo sobrescribo. Agregale a mano esta linea:")
            print("    python scripts/verificacion/sin_pii_versionada.py || exit 1")
            return 1

    with open(destino, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(CUERPO)
    os.chmod(destino, 0o755)

    print("Instalado: %s" % destino)
    return 0


if __name__ == "__main__":
    sys.exit(main())
