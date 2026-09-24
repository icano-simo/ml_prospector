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
    # ── « city» EN MINUSCULA NO ES UN SUFIJO DE TIPO, ES EL NOMBRE ─────────
    #
    # Convencion del Census: una ciudad independiente --que es una entidad
    # aparte del condado del mismo nombre-- se escribe «Baltimore city», con
    # minuscula. Un condado que se llama asi se escribe «Carson City».
    #
    # Quitar las dos dejaba SEIS pares distintos con la misma clave, y como la
    # tabla se llena con asignacion, ganaba el ultimo del archivo:
    #
    #   MD baltimore  -> 24005 Baltimore County  /  24510 Baltimore city
    #   MO st louis   -> 29189 St. Louis County  /  29510 St. Louis city
    #   VA fairfax, franklin, richmond, roanoke: lo mismo
    #
    # O sea que «Baltimore, MD» resolvia a la CIUDAD, en silencio. No fallaba
    # nada: el FIPS existe, tiene cinco digitos y es del estado correcto.
    #
    # `parser_mm` ya distingue los dos --etiqueta «Baltimore» contra «Baltimore
    # city»-- asi que respetarlo aqui es lo unico que faltaba.
    es_ciudad_independiente = nombre.rstrip().endswith(" city")

    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", nombre)
        if unicodedata.category(c) != "Mn"
    )
    n = sin_acentos.lower().strip()
    sufijos = (r"county|parish|borough|census area|city and borough|"
               r"municipality|municipio|planning region")
    if not es_ciudad_independiente:
        sufijos += r"|city"
    n = re.sub(r"\s+(%s)$" % sufijos, "", n)
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def _compacta(nombre: str) -> str:
    """La misma clave, sin espacios. Es la segunda llave de la tabla.

    Model Match escribe «Du Page» y «De Kalb»; el archivo del Census escribe
    «DuPage County» y «DeKalb County». Normalizadas quedan `du page` y `dupage`,
    que son distintas, asi que las 44 metricas de DuPage de una captura real no
    entraron en `pacs.mercados` -- y no fallo nada: la fila se guardo sin FIPS.

    **Sigue siendo match exacto, no fuzzy.** Quitar los espacios no acerca dos
    nombres distintos: los hace iguales o no. Lo que si podria hacer es juntar
    dos condados reales de un mismo estado bajo la misma clave, y por eso
    `cargar` comprueba que eso no pase y revienta si alguna vez pasa.
    """
    return _normalizar(nombre).replace(" ", "")


class ClaveCompactaAmbigua(FipsNoResuelto):
    """Dos condados de un mismo estado comparten clave compacta.

    Medido el 2026-09-23 sobre el archivo de referencia entero: 0 colisiones.
    Si alguna vez aparece una --porque el Census agrega un condado, o porque
    cambia un nombre-- la carga revienta aqui en vez de elegir en silencio.
    Elegir en silencio es lo que convierte un cruce equivocado en un benchmark
    del condado de al lado.
    """


def cargar(ruta: Path = CACHE) -> dict[tuple[str, str], tuple[str, str]]:
    """Devuelve {(estado, clave): (fips, nombre oficial)}.

    Hay DOS claves por condado: el nombre normalizado y el mismo sin espacios.
    La segunda es la que cruza «Du Page» con «DuPage». Ver `_compacta`.
    """
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

            # LAS DOS CLAVES, y ninguna se pisa en silencio.
            #
            # La version anterior asignaba la clave normal directamente, asi
            # que dos condados con la misma clave se resolvian por orden de
            # aparicion en el archivo -- y los seis pares «X County» / «X city»
            # se decidian solos, a favor del ultimo. Que reviente.
            for clave in ((estado, _normalizar(nombre)),
                          (estado, _compacta(nombre))):
                previo = tabla.get(clave)
                if previo is None:
                    tabla[clave] = (fips, nombre)
                elif previo[0] != fips:
                    raise ClaveCompactaAmbigua(
                        "en %s, %r y %r comparten la clave %r y son condados "
                        "distintos (%s y %s).\n"
                        "No elijo uno: un FIPS del condado de al lado es peor "
                        "que ninguno. Hay que resolverlo a mano en geo/fips.py."
                        % (estado, previo[1], nombre, clave[1], previo[0], fips))

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
    # La segunda llave: sin espacios. «Du Page» -> `dupage` -> DuPage County.
    compacta = (clave[0], _compacta(condado))
    if compacta in tabla:
        return tabla[compacta]

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
