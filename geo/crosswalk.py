"""Crosswalk HUD USPS: ZIP <-> census tract <-> condado.

Para que
--------
Las tres fuentes del Bloque 4 hablan geografias distintas:

    Census ACS      ZCTA y tract
    HMDA            condado y tract
    FFIEC / CRA     tract
    Nuestro lote    ZIP (cuando hay) y estado

Sin crosswalk no se pueden unir. Y **un ZIP no es un ZCTA y tampoco es un
tract**: un ZIP puede caer en varios tracts y un tract puede tocar varios ZIPs.
El crosswalk del HUD resuelve eso con pesos de asignacion.

Los cuatro pesos, y por que importa cual se usa
-----------------------------------------------
Cada fila del crosswalk trae cuatro razones de reparto:

    RES_RATIO      direcciones residenciales
    BUS_RATIO      direcciones comerciales
    OTH_RATIO      otras
    TOT_RATIO      todas

**Para cualquier cosa de vivienda va RES_RATIO.** Usar TOT_RATIO mete oficinas
y depositos en el reparto, y en un ZIP con un parque industrial eso corre el
peso hacia tracts donde no vive nadie. Es un error silencioso: el resultado es
plausible y esta mal.

La fuente
---------
https://www.huduser.gov/portal/datasets/usps_crosswalk.html

Requiere registrarse para obtener un token de API gratuito. Se pasa en la
variable de entorno HUD_API_TOKEN, o se baja el Excel a mano y se apunta con
--archivo.

**No se inventa la URL de descarga directa.** El portal cambia los enlaces por
trimestre y bajar el trimestre equivocado produce un crosswalk desactualizado
que nadie nota.
"""
from __future__ import annotations

import csv
import io
import json
import os
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

CACHE = Path(__file__).resolve().parent / "cache"

API_HUD = "https://www.huduser.gov/hudapi/public/usps"

#: Tipos de crosswalk del API del HUD.
TIPO_ZIP_A_TRACT = 1
TIPO_TRACT_A_ZIP = 6
TIPO_ZIP_A_CONDADO = 2

#: El peso que se usa para todo lo de vivienda. Ver el docstring.
PESO_VIVIENDA = "res_ratio"


class CrosswalkNoDisponible(RuntimeError):
    """No hay crosswalk. No se reparte con pesos inventados."""


@dataclass(frozen=True)
class Asignacion:
    """Un trozo de un ZIP que cae en un tract, con su peso."""

    zip_code: str
    geoid: str          # tract de 11 digitos, o condado de 5
    res_ratio: float
    bus_ratio: float
    oth_ratio: float
    tot_ratio: float

    def peso(self, cual: str = PESO_VIVIENDA) -> float:
        return getattr(self, cual)


def descargar(
    tipo: int = TIPO_ZIP_A_TRACT,
    trimestre: str = "1",
    anio: str = "2024",
    *,
    token: str | None = None,
) -> Path:
    """Baja el crosswalk del API del HUD. Requiere token."""
    token = token or os.environ.get("HUD_API_TOKEN")
    if not token:
        raise CrosswalkNoDisponible(
            "Falta el token del API del HUD.\n"
            "\n"
            "Se saca gratis registrandose en\n"
            "  https://www.huduser.gov/portal/dataset/uspszip-api.html\n"
            "y se pone en la variable de entorno HUD_API_TOKEN.\n"
            "\n"
            "Alternativa: bajar el Excel a mano desde\n"
            "  https://www.huduser.gov/portal/datasets/usps_crosswalk.html\n"
            "y pasar --archivo."
        )

    url = "%s?type=%d&query=All&year=%s&quarter=%s" % (API_HUD, tipo, anio, trimestre)
    req = Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urlopen(req, timeout=300) as respuesta:  # noqa: S310 - URL fija
            datos = respuesta.read()
    except HTTPError as exc:
        raise CrosswalkNoDisponible(
            "el API del HUD devolvio HTTP %d. Si es 401, el token no sirve; si "
            "es 400, revisa que el trimestre %s de %s este publicado."
            % (exc.code, trimestre, anio)
        ) from exc

    CACHE.mkdir(parents=True, exist_ok=True)
    destino = CACHE / ("hud_crosswalk_t%d_%sq%s.json" % (tipo, anio, trimestre))
    destino.write_bytes(datos)
    return destino


def _filas_de_json(ruta: Path):
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    resultados = datos.get("data", {}).get("results", [])
    for fila in resultados:
        yield {k.lower(): v for k, v in fila.items()}


def _filas_de_tabular(ruta: Path):
    if ruta.suffix.lower() == ".zip":
        with zipfile.ZipFile(ruta) as z:
            nombres = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))]
            if not nombres:
                raise CrosswalkNoDisponible(
                    "%s no trae csv adentro: %s" % (ruta, z.namelist()[:10])
                )
            contenido = z.read(max(nombres, key=lambda n: z.getinfo(n).file_size))
        fh = io.StringIO(contenido.decode("latin-1"))
    else:
        fh = ruta.open("r", encoding="latin-1", newline="")

    with fh:
        for fila in csv.DictReader(fh):
            yield {(k or "").strip().lower(): v for k, v in fila.items()}


def cargar(ruta: Path | str | None = None) -> dict[str, list[Asignacion]]:
    """{zip: [Asignacion, ...]}. Las asignaciones de cada ZIP suman ~1."""
    if ruta is None:
        candidatos = sorted(CACHE.glob("hud_crosswalk*")) if CACHE.exists() else []
        if not candidatos:
            raise CrosswalkNoDisponible(
                "No hay crosswalk en %s.\n"
                "  python -m geo.crosswalk --descargar     (necesita HUD_API_TOKEN)\n"
                "  python -m geo.crosswalk --archivo RUTA  (Excel/CSV bajado a mano)"
                % CACHE
            )
        ruta = candidatos[-1]

    ruta = Path(ruta)
    filas = (_filas_de_json(ruta) if ruta.suffix.lower() == ".json"
             else _filas_de_tabular(ruta))

    tabla: dict[str, list[Asignacion]] = defaultdict(list)
    for fila in filas:
        zip_code = str(fila.get("zip") or fila.get("zip_code") or "").strip().zfill(5)
        geoid = str(
            fila.get("tract") or fila.get("geoid") or fila.get("county") or ""
        ).strip()
        if not zip_code.isdigit() or not geoid.isdigit():
            continue

        def num(clave: str) -> float:
            try:
                return float(fila.get(clave) or 0.0)
            except (TypeError, ValueError):
                return 0.0

        tabla[zip_code].append(Asignacion(
            zip_code=zip_code, geoid=geoid,
            res_ratio=num("res_ratio"), bus_ratio=num("bus_ratio"),
            oth_ratio=num("oth_ratio"), tot_ratio=num("tot_ratio"),
        ))

    if not tabla:
        raise CrosswalkNoDisponible(
            "%s se leyo pero no produjo asignaciones. Revisa que sea el archivo "
            "de crosswalk y no el diccionario." % ruta
        )
    return dict(tabla)


def repartir(
    zip_code: str,
    tabla: dict[str, list[Asignacion]],
    *,
    peso: str = PESO_VIVIENDA,
) -> list[tuple[str, float]]:
    """[(geoid, peso normalizado)] para un ZIP. Lista vacia si no esta.

    Los pesos se normalizan para que sumen 1: el crosswalk del HUD a veces no
    suma exacto por redondeo, y un reparto que suma 0,98 sesga el agregado
    hacia abajo sin que nadie lo note.
    """
    asignaciones = tabla.get(str(zip_code).strip().zfill(5), [])
    if not asignaciones:
        return []
    total = sum(a.peso(peso) for a in asignaciones)
    if total <= 0:
        return []
    return [(a.geoid, a.peso(peso) / total) for a in asignaciones]


def valor_por_zip(
    zip_code: str,
    valores_por_geoid: dict[str, float],
    tabla: dict[str, list[Asignacion]],
    *,
    peso: str = PESO_VIVIENDA,
) -> tuple[float | None, str]:
    """Promedia un valor de tract hacia un ZIP. Devuelve (valor, cobertura).

    `cobertura` dice que fraccion del ZIP tenia dato, con su denominador. Si es
    baja, el promedio es de una parte del ZIP y **eso hay que saberlo**: un
    valor calculado sobre el 30% de un ZIP no es el valor del ZIP.
    """
    reparto = repartir(zip_code, tabla, peso=peso)
    if not reparto:
        return None, "[sin dato: el ZIP no esta en el crosswalk]"

    acumulado = 0.0
    peso_con_dato = 0.0
    n_con_dato = 0
    for geoid, w in reparto:
        valor = valores_por_geoid.get(geoid)
        if valor is None:
            continue
        acumulado += valor * w
        peso_con_dato += w
        n_con_dato += 1

    if peso_con_dato <= 0:
        return None, "[sin dato: ningun tract del ZIP tiene valor]"

    cobertura = "%.0f%% del ZIP (%d/%d tracts)" % (
        peso_con_dato * 100, n_con_dato, len(reparto),
    )
    return acumulado / peso_con_dato, cobertura


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--descargar", action="store_true")
    ap.add_argument("--archivo", type=Path, default=None)
    ap.add_argument("--anio", default="2024")
    ap.add_argument("--trimestre", default="1")
    ap.add_argument("--zip", dest="zip_code", help="ZIP a inspeccionar")
    args = ap.parse_args(argv)

    try:
        if args.descargar:
            ruta = descargar(anio=args.anio, trimestre=args.trimestre)
            print("Descargado: %s" % ruta)
            args.archivo = ruta
        tabla = cargar(args.archivo)
    except CrosswalkNoDisponible as exc:
        print(exc)
        return 1

    print("ZIPs en el crosswalk: %d" % len(tabla))
    print("Asignaciones totales: %d" % sum(len(v) for v in tabla.values()))

    if args.zip_code:
        reparto = repartir(args.zip_code, tabla)
        if not reparto:
            print("El ZIP %s no esta en el crosswalk." % args.zip_code)
            return 1
        print("")
        print("ZIP %s se reparte en %d tracts (peso %s):"
              % (args.zip_code, len(reparto), PESO_VIVIENDA))
        for geoid, w in sorted(reparto, key=lambda kv: -kv[1]):
            print("   %s  %.4f" % (geoid, w))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main())
