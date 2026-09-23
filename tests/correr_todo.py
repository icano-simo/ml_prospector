"""Corre todas las suites. Sin pytest, sin pandas, sin red.

    python tests/correr_todo.py

Que las pruebas no necesiten pandas ni red es deliberado: son la unica cosa que
se puede verificar en cualquier maquina, y cuando algo falle en una corrida
real, que pasen dice que el problema esta en el selector o en el entorno y no en
la logica.

Sale con 1 si alguna falla. Sirve en CI.
"""
from __future__ import annotations

import importlib
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "realtor_scraper"))

SUITES = [
    ("guardas", "tests.test_guardas", "las reglas de guardia de PACS-H"),
    ("instagram", "tests.test_instagram", "estado, verificacion, idioma, posts, comentarios"),
    ("instagram_profundo", "tests.test_instagram_profundo",
     "captura cruda, parser y contrato de ig_signals.csv"),
    ("captura", "tests.test_captura",
     "protocolo de Model Match y las seis trampas verificadas"),
    ("reglas", "tests.test_reglas",
     "una prueba por regla: activa, no activa, y sin dato"),
    ("audiencia", "tests.test_audiencia",
     "lexicos bilingues, etiqueta con cita, desajuste de idioma"),
    ("modelmatch", "tests.test_modelmatch", "las cuatro trampas verificadas"),
    ("identidad", "tests.test_identidad", "normalizacion, cascada, registro"),
    ("hmda", "tests.test_hmda", "fallout y mix, con el denominador correcto"),
    ("google_places", "tests.test_google_places", "reviews, anonimato, denominadores"),
    ("census", "tests.test_census", "el rechazo con HTTP 200, la clave y los denominadores"),
    ("contrastes", "tests.test_contrastes", "cuatro lecturas de un agente, y la guardia que manda"),
    ("lectura", "tests.test_lectura", "de numero a lectura, vocabulario y el caso sin dolor"),
    ("cargar_ig", "tests.test_cargar_instagram", "la llave, la PII del agente y la coherencia CSV/crudo"),
    ("marca", "tests.test_marca", "la guia de diseño sobre los archivos servidos"),
]


def main() -> int:
    total = 0
    fallas = 0
    por_suite: list[tuple[str, int, int]] = []

    for nombre, modulo_ruta, descripcion in SUITES:
        print("")
        print("=" * 72)
        print("%s · %s" % (nombre, descripcion))
        print("=" * 72)
        try:
            modulo = importlib.import_module(modulo_ruta)
        except Exception as exc:  # noqa: BLE001
            print("  NO SE PUDO IMPORTAR: %r" % exc)
            por_suite.append((nombre, 0, 1))
            fallas += 1
            continue

        pruebas = [
            (n, o) for n, o in sorted(vars(modulo).items())
            if n.startswith("test_") and callable(o)
        ]
        fallas_suite = 0
        for nombre_prueba, fn in pruebas:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                fallas_suite += 1
                print("  FALLA %s -- %r" % (nombre_prueba, exc))
        print("  %d pruebas, %d fallas" % (len(pruebas), fallas_suite))
        total += len(pruebas)
        fallas += fallas_suite
        por_suite.append((nombre, len(pruebas), fallas_suite))

    print("")
    print("=" * 72)
    print("RESUMEN")
    print("=" * 72)
    for nombre, n, f in por_suite:
        marca = "ok   " if f == 0 else "FALLA"
        print("  %s %-16s %3d pruebas, %d fallas" % (marca, nombre, n, f))
    print("")
    print("TOTAL: %d pruebas, %d fallas" % (total, fallas))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
