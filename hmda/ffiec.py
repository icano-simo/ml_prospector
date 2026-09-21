"""Designacion LMI del census tract, desde los flat files del FFIEC.

Para que
--------
LMI (Low-and-Moderate Income) es la clasificacion regulatoria de un tract segun
su ingreso mediano relativo al del area metropolitana. Es la señal que usan los
programas de CRA y muchos DPA estatales para definir elegibilidad.

Alimenta:

- **P-Q07** (capital de entrada): un tract LMI suele tener programas de
  asistencia de enganche que el comprador no sabe que existen.
- La feature relativa de asequibilidad, porque la designacion **ya es
  relativa** al area: es exactamente lo que el Bloque 4 pide -- una variable que
  no permite memorizar el estado y si captura si opera en zona de entrada o en
  zona cara.

Las categorias del FFIEC
------------------------
Se define sobre el ratio entre el ingreso mediano del tract y el del MSA/MD (o
el del area no metropolitana del estado):

    Low          < 50%
    Moderate     50% - 79,99%
    Middle       80% - 119,99%
    Upper        >= 120%
    Unknown      sin ingreso publicado

**LMI = Low + Moderate**, es decir ratio < 80%.

La fuente
---------
Los "FFIEC Census Flat Files" en
https://www.ffiec.gov/censusapp.htm -- un zip por año con un CSV de ancho fijo
por posicion de campo, documentado en el diccionario del propio año.

**Este modulo NO descarga el archivo automaticamente.** El FFIEC lo publica
detras de una pagina con formulario y el enlace cambia de año a año; adivinar
la URL produciria un 404 silencioso o, peor, el archivo del año equivocado. Se
descarga a mano una vez y se apunta aca.

Si el archivo no esta, `cargar()` falla con instrucciones. No devuelve una
tabla vacia: un tract sin designacion tiene que ser `None`, no "no es LMI".
"""
from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "cache"

#: Posiciones de campo en el flat file del FFIEC. El archivo no trae
#: encabezados: los campos se identifican por su numero, documentado en el
#: diccionario de datos del año. Estos son 1-based como en el diccionario.
CAMPO_ANIO = 1
CAMPO_MSA_MD = 2
CAMPO_ESTADO_FIPS = 3
CAMPO_CONDADO_FIPS = 4
CAMPO_TRACT = 5
#: "Tract Income Level": 1=Low 2=Moderate 3=Middle 4=Upper 0/blank=Unknown
CAMPO_NIVEL_INGRESO = 10
#: Porcentaje del ingreso mediano del tract sobre el del area.
CAMPO_PCT_INGRESO_AREA = 11


class NivelDeIngreso(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    MIDDLE = "middle"
    UPPER = "upper"
    DESCONOCIDO = "desconocido"

    @property
    def es_lmi(self) -> bool | None:
        """None para desconocido. **Desconocido no es 'no es LMI'.**"""
        if self is NivelDeIngreso.DESCONOCIDO:
            return None
        return self in (NivelDeIngreso.LOW, NivelDeIngreso.MODERATE)


_CODIGO_A_NIVEL = {
    "1": NivelDeIngreso.LOW,
    "2": NivelDeIngreso.MODERATE,
    "3": NivelDeIngreso.MIDDLE,
    "4": NivelDeIngreso.UPPER,
}


class FfiecNoDisponible(RuntimeError):
    """Falta el flat file. No se devuelve una tabla vacia."""


@dataclass(frozen=True)
class TractFfiec:
    geoid: str                 # 11 digitos: estado(2)+condado(3)+tract(6)
    anio: int
    nivel: NivelDeIngreso
    pct_ingreso_del_area: float | None

    @property
    def es_lmi(self) -> bool | None:
        return self.nivel.es_lmi


def _abrir(ruta: Path):
    """Devuelve un iterador de lineas, ya sea .zip o .csv/.dat plano."""
    if ruta.suffix.lower() == ".zip":
        with zipfile.ZipFile(ruta) as z:
            candidatos = [
                n for n in z.namelist()
                if n.lower().endswith((".csv", ".dat", ".txt"))
            ]
            if not candidatos:
                raise FfiecNoDisponible(
                    "%s no trae ningun csv/dat/txt adentro. Contenido: %s"
                    % (ruta, z.namelist()[:10])
                )
            # El mas grande es el flat file; los otros suelen ser el diccionario.
            elegido = max(candidatos, key=lambda n: z.getinfo(n).file_size)
            datos = z.read(elegido)
        return io.StringIO(datos.decode("latin-1"))
    return ruta.open("r", encoding="latin-1")


def cargar(ruta: Path | str | None = None, *, anio: int | None = None
           ) -> dict[str, TractFfiec]:
    """{GEOID de 11 digitos: TractFfiec}.

    Si `ruta` es None busca en hmda/cache/ un archivo cuyo nombre contenga
    "census" y el año.
    """
    if ruta is None:
        patron = "*census*%s*" % (anio or "")
        candidatos = sorted(CACHE.glob(patron)) if CACHE.exists() else []
        if not candidatos:
            raise FfiecNoDisponible(
                "No encuentro el flat file del FFIEC.\n"
                "\n"
                "Se descarga a mano UNA vez desde https://www.ffiec.gov/censusapp.htm\n"
                "y se guarda en %s. No lo bajo automaticamente porque el enlace\n"
                "cambia de año a año y adivinarlo produce un 404 silencioso o,\n"
                "peor, el archivo del año equivocado.\n"
                "\n"
                "Despues: python -m hmda.ffiec --resumen" % CACHE
            )
        ruta = candidatos[-1]

    ruta = Path(ruta)
    tabla: dict[str, TractFfiec] = {}
    mal_formadas = 0

    with _abrir(ruta) as fh:
        for fila in csv.reader(fh):
            if len(fila) < CAMPO_PCT_INGRESO_AREA:
                mal_formadas += 1
                continue
            try:
                anio_fila = int(fila[CAMPO_ANIO - 1].strip())
                estado = fila[CAMPO_ESTADO_FIPS - 1].strip().zfill(2)
                condado = fila[CAMPO_CONDADO_FIPS - 1].strip().zfill(3)
                tract = fila[CAMPO_TRACT - 1].strip().replace(".", "").zfill(6)
            except (ValueError, IndexError):
                mal_formadas += 1
                continue

            geoid = estado + condado + tract
            if len(geoid) != 11 or not geoid.isdigit():
                mal_formadas += 1
                continue

            nivel = _CODIGO_A_NIVEL.get(
                fila[CAMPO_NIVEL_INGRESO - 1].strip(), NivelDeIngreso.DESCONOCIDO
            )
            try:
                pct = float(fila[CAMPO_PCT_INGRESO_AREA - 1].strip())
            except ValueError:
                pct = None

            tabla[geoid] = TractFfiec(
                geoid=geoid, anio=anio_fila, nivel=nivel,
                pct_ingreso_del_area=pct,
            )

    if not tabla:
        raise FfiecNoDisponible(
            "%s se leyo pero no produjo ningun tract (%d filas mal formadas).\n"
            "Las posiciones de campo cambian entre años: revisa el diccionario\n"
            "del año contra las constantes CAMPO_* de este modulo."
            % (ruta, mal_formadas)
        )

    if mal_formadas > len(tabla) * 0.05:
        print(
            "AVISO: %d filas mal formadas sobre %d tracts (%.1f%%). Si es mucho, "
            "las posiciones de campo del año no coinciden con las constantes "
            "CAMPO_* de este modulo."
            % (mal_formadas, len(tabla), mal_formadas / len(tabla) * 100)
        )
    return tabla


def resumen(tabla: dict[str, TractFfiec]) -> dict:
    conteo: dict[str, int] = {}
    for t in tabla.values():
        conteo[t.nivel.value] = conteo.get(t.nivel.value, 0) + 1
    total = len(tabla)
    lmi = conteo.get("low", 0) + conteo.get("moderate", 0)
    conocidos = total - conteo.get("desconocido", 0)
    return {
        "tracts": total,
        "por_nivel": conteo,
        "lmi": lmi,
        "lmi_pct_sobre_conocidos": (
            "%.1f%% (%d/%d)" % (lmi / conocidos * 100, lmi, conocidos)
            if conocidos else "[sin dato: 0/0]"
        ),
        "desconocidos": conteo.get("desconocido", 0),
    }


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--archivo", type=Path, default=None)
    ap.add_argument("--anio", type=int, default=None)
    ap.add_argument("--resumen", action="store_true")
    ap.add_argument("--tract", help="GEOID de 11 digitos a consultar")
    args = ap.parse_args(argv)

    try:
        tabla = cargar(args.archivo, anio=args.anio)
    except FfiecNoDisponible as exc:
        print(exc)
        return 1

    if args.tract:
        t = tabla.get(args.tract)
        if not t:
            print("El tract %s no esta en el archivo." % args.tract)
            return 1
        print("%s  %s  %s%% del area  LMI=%s"
              % (t.geoid, t.nivel.value, t.pct_ingreso_del_area, t.es_lmi))
        return 0

    print(json.dumps(resumen(tabla), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main())
