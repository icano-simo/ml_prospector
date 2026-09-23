"""Corre las 22 pruebas y resume. Un runner, no 22 invocaciones a mano.

Cada archivo de `tests/` expone funciones `test_*` y un `_correr()` que las
ejecuta e imprime. Este script las importa y llama a ese `_correr`, para que el
resumen de la suite sea UNO y no la lectura a ojo de 22 salidas.
"""
from __future__ import annotations

import glob
import importlib.util
import io
import os
import sys
from contextlib import redirect_stdout

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    total = fallas = 0
    rotos: list[str] = []

    for ruta in sorted(glob.glob(os.path.join(AQUI, "test_*.py"))):
        nombre = os.path.basename(ruta)[len("test_"):-len(".py")]
        spec = importlib.util.spec_from_file_location("t_" + nombre, ruta)
        mod = importlib.util.module_from_spec(spec)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                spec.loader.exec_module(mod)
                # Los 22 archivos traen su propio arranque, y NO se llama
                # igual en todos: 15 lo llaman `_correr` y 7 `_main`. Buscar
                # solo uno reportaba "no se pudo ni importar" sobre pruebas que
                # estaban perfectas -- un runner que miente sobre la suite.
                arrancar = getattr(mod, "_correr", None) or getattr(mod, "_main")
                cod = arrancar()
        except Exception as exc:  # noqa: BLE001
            rotos.append("%s no se pudo ni importar: %r" % (nombre, exc))
            print("  %-22s NO CORRIO  %r" % (nombre, exc))
            fallas += 1
            continue

        salida = buf.getvalue()
        n = salida.count("  ok   ") + salida.count("  FALLA ")
        malas = [ln for ln in salida.splitlines() if ln.startswith("  FALLA")]
        total += n
        fallas += len(malas)
        print("  %-22s %3d pruebas · %s"
              % (nombre, n, "%d fallas" % len(malas) if malas else "ok"))
        for ln in malas:
            print("      %s" % ln.strip())
        if cod and not malas:
            rotos.append("%s devolvio %s sin imprimir ninguna FALLA" % (nombre, cod))

    print("")
    print("  %d pruebas en total · %d fallas" % (total, fallas))
    for r in rotos:
        print("  ATENCION: %s" % r)
    return 1 if (fallas or rotos) else 0


if __name__ == "__main__":
    sys.exit(main())
