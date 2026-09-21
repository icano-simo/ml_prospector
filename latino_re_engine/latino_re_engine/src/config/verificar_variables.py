"""Verifica cada codigo de census_variables.py contra el API de Census.

Por que existe
--------------
Un codigo de variable inventado o desactualizado **no falla**: el API lo ignora
o devuelve un error poco claro, y el resultado es una columna vacia que nadie
nota. Esa es la misma familia de error que dejo `ig_is_private` constante en
5.620 filas con importancia 0,000 en el modelo.

Y los codigos cambian entre vintages del ACS: una tabla puede desaparecer, o
renumerarse.

Uso
---
    python -m src.config.verificar_variables
    python -m src.config.verificar_variables --anio 2022
    python -m src.config.verificar_variables --nivel zip%20code%20tabulation%20area

Sale con 1 si algun codigo no existe. Pensado para correr en CI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config.census_variables import CODE_TO_COLUMN, VARIABLE_GROUPS  # noqa: E402

ANIO_POR_DEFECTO = 2023
CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache_variables"


def _url_variables(anio: int) -> str:
    return "https://api.census.gov/data/%d/acs/acs5/variables.json" % anio


def cargar_catalogo(anio: int, *, forzar: bool = False) -> dict:
    """Catalogo de variables del ACS5, cacheado en disco."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / ("acs5_%d_variables.json" % anio)

    if cache.exists() and not forzar:
        with cache.open("r", encoding="utf-8") as fh:
            return json.load(fh).get("variables", {})

    req = Request(_url_variables(anio), headers={"User-Agent": "ml_prospector/1.0"})
    with urlopen(req, timeout=180) as respuesta:  # noqa: S310 - URL fija de census.gov
        datos = json.loads(respuesta.read().decode("utf-8"))

    if "variables" not in datos:
        raise SystemExit(
            "lo que devolvio %s no trae la clave 'variables'. No lo cacheo."
            % _url_variables(anio)
        )
    with cache.open("w", encoding="utf-8") as fh:
        json.dump(datos, fh)
    return datos["variables"]


def verificar(anio: int, *, nivel: str | None = None, forzar: bool = False) -> int:
    catalogo = cargar_catalogo(anio, forzar=forzar)
    print("Catalogo ACS5 %d: %d variables" % (anio, len(catalogo)))
    print("Codigos declarados en census_variables.py: %d" % len(CODE_TO_COLUMN))
    print("")

    faltantes: list[tuple[str, str, str]] = []
    etiquetas_raras: list[tuple[str, str, str]] = []

    for grupo, codigos in VARIABLE_GROUPS.items():
        ausentes = [c for c in codigos if c not in catalogo]
        marca = "FALLA" if ausentes else "ok   "
        print("%s %-24s %3d codigos%s" % (
            marca, grupo, len(codigos),
            "  -> %d AUSENTES: %s" % (len(ausentes), ausentes) if ausentes else "",
        ))
        for codigo in ausentes:
            faltantes.append((grupo, codigo, codigos[codigo]))

        # El nombre interno tiene que tener algo que ver con la etiqueta. No es
        # una verificacion estricta, pero caza el copiar-pegar de la fila de al
        # lado, que es el error real.
        for codigo, nombre in codigos.items():
            info = catalogo.get(codigo)
            if not info:
                continue
            etiqueta = (info.get("label") or "").lower()
            palabras = [p for p in nombre.replace("_", " ").split() if len(p) > 3]
            if palabras and not any(p[:5] in etiqueta for p in palabras):
                etiquetas_raras.append((codigo, nombre, info.get("label") or ""))

    print("")
    if etiquetas_raras:
        print("REVISAR: el nombre interno no se parece a la etiqueta del API.")
        print("No es necesariamente un error, pero es donde se esconde el")
        print("copiar-pegar de la fila de al lado:")
        for codigo, nombre, etiqueta in etiquetas_raras[:40]:
            print("   %-16s %-38s %s" % (codigo, nombre, etiqueta.replace("Estimate!!", "")))
        print("")

    if nivel:
        print("AVISO: la disponibilidad por nivel geografico (%r) no se verifica" % nivel)
        print("aca. El catalogo de variables no la declara: hay que pedir una")
        print("consulta real a ese nivel. Ver el cliente de census.")
        print("")

    if faltantes:
        print("=" * 70)
        print("FALLA: %d codigos no existen en ACS5 %d" % (len(faltantes), anio))
        print("=" * 70)
        for grupo, codigo, nombre in faltantes:
            print("   %-24s %-16s -> %s" % (grupo, codigo, nombre))
        print("")
        print("Un codigo inexistente NO falla en la corrida: produce una columna")
        print("vacia. Corregilo antes de pedir el lote.")
        return 1

    print("OK: los %d codigos existen en ACS5 %d." % (len(CODE_TO_COLUMN), anio))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--anio", type=int, default=ANIO_POR_DEFECTO)
    ap.add_argument("--nivel", default=None)
    ap.add_argument("--forzar", action="store_true", help="ignora el cache local")
    args = ap.parse_args(argv)
    return verificar(args.anio, nivel=args.nivel, forzar=args.forzar)


if __name__ == "__main__":
    sys.exit(main())
