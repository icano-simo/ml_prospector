"""Codigos FIPS de condado, leidos del archivo de referencia oficial de Census.

Por que se descarga y no se escribe a mano
------------------------------------------
La alucinacion numero 2 documentada en la skill homesi-pacs-scoring es "listas
de entidades escritas a mano": los estados punitivos y santuario estaban
hardcodeados, incluyendo cinco que ni aparecian en el lote, y coincidian con el
ILRC real por suerte y no por metodo.

Un FIPS escrito a mano es peor que eso, porque nadie lo revisa: 48201 y 48021
son los dos codigos validos y uno es Harris, Texas y el otro Bastrop, Texas.

Y hace falta el FIPS y no el nombre porque **hay 31 condados llamados
Washington** y 26 llamados Jefferson. Ademas Connecticut reemplazo sus ocho
condados por nueve regiones de planificacion en 2022, con FIPS nuevos: una
tabla de 2020 no los tiene y una de 2023 si.

Fuente
------
https://www2.census.gov/geo/docs/reference/codes2020/national_county2020.txt

Formato: STATE|STATEFP|COUNTYFP|COUNTYNS|COUNTYNAME|CLASSFP|FUNCSTAT
El FIPS de 5 digitos es STATEFP + COUNTYFP.

Uso
---
    python -m geo.fips --descargar
    python -m geo.fips --adjuntar lista.csv --salida lista_con_fips.csv
    python -m geo.fips --buscar "Harris" --estado TX
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import unicodedata
from pathlib import Path

URL_REFERENCIA = (
    "https://www2.census.gov/geo/docs/reference/codes2020/national_county2020.txt"
)

#: Donde se guarda la copia local. Es cache, no fuente: se puede borrar.
CACHE = Path(__file__).resolve().parent / "cache" / "national_county2020.txt"


class FipsNoResuelto(LookupError):
    """No se pudo resolver el FIPS sin adivinar. No se devuelve un valor plausible."""


def descargar(destino: Path = CACHE, *, forzar: bool = False) -> Path:
    """Baja el archivo de referencia. Requiere `requests` o urllib."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and not forzar:
        return destino

    from urllib.request import Request, urlopen

    peticion = Request(
        URL_REFERENCIA,
        headers={"User-Agent": "ml_prospector/1.0 (+geo.fips)"},
    )
    with urlopen(peticion, timeout=60) as respuesta:  # noqa: S310 - URL fija de census.gov
        datos = respuesta.read()

    texto = datos.decode("latin-1")
    if "STATEFP" not in texto.split("\n", 1)[0].upper():
        raise FipsNoResuelto(
            "lo que bajo de %s no parece el archivo de referencia: la primera "
            "linea es %r. No lo guardo: un cache con basura es peor que sin cache."
            % (URL_REFERENCIA, texto.split(chr(10), 1)[0][:120])
        )
    destino.write_text(texto, encoding="utf-8")
    return destino


def _normalizar(nombre: str) -> str:
    """Normaliza un nombre de condado para comparar.

    Quita acentos, pasa a minusculas y saca los sufijos de tipo de division,
    que es donde se pierden los cruces: "Miami-Dade County" contra
    "Miami-Dade", "Dona Ana County" contra "Doña Ana County", "San Juan
    Municipio" contra "San Juan".
    """
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", nombre)
        if unicodedata.category(c) != "Mn"
    )
    n = sin_acentos.lower().strip()
    n = re.sub(
        r"\s+(county|parish|borough|census area|city and borough|municipality|"
        r"municipio|planning region|city)$",
        "",
        n,
    )
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def cargar(ruta: Path = CACHE) -> dict[tuple[str, str], tuple[str, str]]:
    """Devuelve {(estado, nombre normalizado): (fips, nombre oficial)}."""
    if not ruta.exists():
        raise FipsNoResuelto(
            "no hay copia local del archivo de referencia en %s.\n"
            "Corre primero:  python -m geo.fips --descargar" % ruta
        )
    tabla: dict[tuple[str, str], tuple[str, str]] = {}
    with ruta.open("r", encoding="utf-8") as fh:
        lector = csv.reader(fh, delimiter="|")
        encabezado = next(lector, None)
        if not encabezado or "STATEFP" not in [c.strip().upper() for c in encabezado]:
            raise FipsNoResuelto(
                "el archivo %s no trae el encabezado esperado. Bajalo de nuevo "
                "con --descargar --forzar." % ruta
            )
        cols = {c.strip().upper(): i for i, c in enumerate(encabezado)}
        for fila in lector:
            if len(fila) < len(cols):
                continue
            estado = fila[cols["STATE"]].strip().upper()
            statefp = fila[cols["STATEFP"]].strip()
            countyfp = fila[cols["COUNTYFP"]].strip()
            nombre = fila[cols["COUNTYNAME"]].strip()
            if not (estado and statefp and countyfp and nombre):
                continue
            fips = "%s%s" % (statefp.zfill(2), countyfp.zfill(3))
            tabla[(estado, _normalizar(nombre))] = (fips, nombre)
    if not tabla:
        raise FipsNoResuelto("el archivo de referencia quedo vacio al parsear: %s" % ruta)
    return tabla


def resolver(estado: str, condado: str, tabla: dict | None = None) -> tuple[str, str]:
    """(fips, nombre oficial). Levanta FipsNoResuelto si no hay match exacto.

    No hace fuzzy matching a proposito. Un FIPS aproximado es un FIPS
    equivocado, y un benchmark de condado atribuido al condado de al lado es
    peor que no tener benchmark.
    """
    if tabla is None:
        tabla = cargar()
    clave = (estado.strip().upper(), _normalizar(condado))
    if clave in tabla:
        return tabla[clave]

    candidatos = [
        oficial for (est, _), (_, oficial) in tabla.items()
        if est == clave[0] and _normalizar(oficial).startswith(clave[1][:6])
    ]
    raise FipsNoResuelto(
        "no encuentro FIPS para %r en %s (normalizado: %r).%s\n"
        "No adivino: un FIPS aproximado es un FIPS equivocado."
        % (condado, estado, clave[1],
           ("\nParecidos en %s: %s" % (clave[0], sorted(candidatos)[:8]))
           if candidatos else "")
    )


def adjuntar(
    entrada: str | Path,
    salida: str | Path,
    *,
    col_estado: str = "estado",
    col_condado: str = "condado",
) -> tuple[int, list[str]]:
    """Agrega una columna `fips` a un CSV. Devuelve (resueltos, no resueltos)."""
    tabla = cargar()
    entrada = Path(entrada)
    salida = Path(salida)
    with entrada.open("r", encoding="utf-8", newline="") as fh:
        filas = list(csv.DictReader(fh))
    if not filas:
        raise FipsNoResuelto("%s esta vacio" % entrada)
    for col in (col_estado, col_condado):
        if col not in filas[0]:
            raise FipsNoResuelto(
                "%s no tiene la columna %r. Columnas: %s"
                % (entrada, col, list(filas[0]))
            )

    fallos: list[str] = []
    resueltos = 0
    for fila in filas:
        try:
            fips, oficial = resolver(fila[col_estado], fila[col_condado], tabla)
            fila["fips"] = fips
            fila["condado_oficial"] = oficial
            resueltos += 1
        except FipsNoResuelto:
            fila["fips"] = ""
            fila["condado_oficial"] = ""
            fallos.append("%s / %s" % (fila[col_estado], fila[col_condado]))

    campos = list(filas[0])
    with salida.open("w", encoding="utf-8", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=campos)
        escritor.writeheader()
        escritor.writerows(filas)
    return resueltos, fallos


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--descargar", action="store_true")
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--adjuntar", metavar="CSV")
    ap.add_argument("--salida", metavar="CSV")
    ap.add_argument("--buscar", metavar="CONDADO")
    ap.add_argument("--estado", metavar="XX")
    args = ap.parse_args(argv)

    if args.descargar:
        ruta = descargar(forzar=args.forzar)
        tabla = cargar(ruta)
        print("Descargado: %s" % ruta)
        print("Condados en la referencia: %d" % len(tabla))
        estados = sorted({e for e, _ in tabla})
        print("Estados/territorios: %d (%s...)" % (len(estados), ", ".join(estados[:8])))
        return 0

    if args.buscar:
        if not args.estado:
            print("--buscar necesita --estado")
            return 2
        try:
            fips, oficial = resolver(args.estado, args.buscar)
        except FipsNoResuelto as exc:
            print(exc)
            return 1
        print("%s  %s, %s" % (fips, oficial, args.estado.upper()))
        return 0

    if args.adjuntar:
        if not args.salida:
            print("--adjuntar necesita --salida")
            return 2
        resueltos, fallos = adjuntar(args.adjuntar, args.salida)
        print("Resueltos: %d" % resueltos)
        if fallos:
            print("NO resueltos: %d" % len(fallos))
            for f in fallos[:25]:
                print("   " + f)
            if len(fallos) > 25:
                print("   ... y %d mas" % (len(fallos) - 25))
            print("")
            print("Estos quedaron con fips vacio. Resolvelos a mano contra la")
            print("referencia antes de capturar: el parser de Model Match")
            print("rechaza una captura sin FIPS de 5 digitos.")
        print("Escrito: %s" % args.salida)
        return 1 if fallos else 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(_main())
