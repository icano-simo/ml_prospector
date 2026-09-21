"""Calibra los benchmarks de Model Match contra HMDA. Paso 3 del Bloque 5.

Por que este es el uso mas rentable de la prueba
------------------------------------------------
La prueba de Model Match caduca; HMDA no. Si el fallout % y la cuota FHA que
muestra Model Match coinciden con los que se derivan de HMDA, **tenemos el
reemplazo gratuito y nacional** y la prueba ya rindio lo que tenia que rendir.

Y si NO coinciden, eso tambien es un resultado: dice que el fallout de Model
Match se calcula sobre un universo distinto del nuestro, y hay que preguntarles
cual **antes** de citarlo a un realtor.

Lo que este modulo NO hace
--------------------------
No ajusta, no promedia y no elige un ganador. Reporta la diferencia y, cuando
hay varios universos de HMDA probados, dice **cual se parece mas** -- que es la
forma de descubrir el filtro de Model Match por ingenieria inversa.

La primera medicion ya dice algo
--------------------------------
Harris County TX, 2023, HMDA **sin filtro de universo**: fallout 48,8%
(52.990 / 108.597, excluyendo 17.266 prestamos comprados). El orden de magnitud
que muestra Model Match en su pantalla es ~22%.

Esa brecha no es un error de nadie: es que Model Match filtra. El filtro
estandar del oficio -- compra de vivienda, 1-4 unidades site-built, una unidad,
primer lien -- es la primera hipotesis a probar. **No se probo**: el endpoint
de HMDA devolvio 403 por limite de tasa despues de la primera llamada.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hmda.cliente import (  # noqa: E402
    FILTRO_COMPRA_ESTANDAR,
    SIN_FILTRO,
    HmdaNoDisponible,
    fallout,
    mix_de_mercado,
)
from modelmatch.esquema import BenchmarkCondado  # noqa: E402
from modelmatch.parser import leer_benchmark_condado  # noqa: E402

#: Universos de HMDA a probar. El nombre es la hipotesis sobre que filtra
#: Model Match, y el objetivo es ver cual se parece mas.
UNIVERSOS: dict[str, dict[str, str]] = {
    "sin_filtro": dict(SIN_FILTRO),
    "compra_estandar": dict(FILTRO_COMPRA_ESTANDAR),
    "compra_sin_lien": {
        "loan_purposes": "1",
        "dwelling_categories": "Single Family (1-4 Units):Site-Built",
        "total_units": "1",
    },
    "solo_compra": {"loan_purposes": "1"},
}

#: Por debajo de esto se consideran coincidentes, en puntos porcentuales.
#: Es una regla propia y esta escrita aca para que alguien pueda discutirla.
TOLERANCIA_PP = 3.0


@dataclass
class Comparacion:
    fips: str
    anio: int
    campo: str
    valor_modelmatch: float | None
    denominador_modelmatch: int | None
    #: {nombre del universo: (valor, texto con denominador)}
    valores_hmda: dict[str, tuple[float | None, str]]

    @property
    def mejor_universo(self) -> tuple[str, float] | None:
        """El universo de HMDA mas cercano al numero de Model Match."""
        if self.valor_modelmatch is None:
            return None
        candidatos = [
            (nombre, abs(valor - self.valor_modelmatch) * 100)
            for nombre, (valor, _) in self.valores_hmda.items()
            if valor is not None
        ]
        if not candidatos:
            return None
        return min(candidatos, key=lambda kv: kv[1])

    @property
    def coincide(self) -> bool | None:
        mejor = self.mejor_universo
        if mejor is None:
            return None
        return mejor[1] <= TOLERANCIA_PP

    def informe(self) -> str:
        lineas = ["%s %d · %s" % (self.fips, self.anio, self.campo)]
        if self.valor_modelmatch is None:
            lineas.append("  Model Match: [sin dato]")
        else:
            den = (" sobre %d" % self.denominador_modelmatch
                   if self.denominador_modelmatch else " SIN DENOMINADOR DECLARADO")
            lineas.append("  Model Match: %.1f%%%s" % (self.valor_modelmatch * 100, den))
        for nombre, (valor, detalle) in sorted(self.valores_hmda.items()):
            if valor is None:
                lineas.append("  HMDA %-18s [sin dato] %s" % (nombre, detalle))
            else:
                lineas.append("  HMDA %-18s %.1f%%  %s"
                              % (nombre, valor * 100, detalle))

        mejor = self.mejor_universo
        if mejor is None:
            lineas.append("  -> no se pudo comparar")
        elif self.coincide:
            lineas.append(
                "  -> COINCIDE con el universo %r (diferencia %.1f pp). "
                "HMDA puede reemplazar esta metrica." % mejor
            )
        else:
            lineas.append(
                "  -> NO coincide. El mas cercano es %r con %.1f pp de "
                "diferencia. Antes de citar esta cifra a un realtor hay que "
                "preguntarle a Model Match sobre que universo la calcula."
                % mejor
            )
        return "\n".join(lineas)


def comparar_fallout(bench: BenchmarkCondado, *, anio: int,
                     universos: dict[str, dict] | None = None) -> Comparacion:
    if not bench.fips:
        raise ValueError("el benchmark no trae FIPS")

    valores: dict[str, tuple[float | None, str]] = {}
    for nombre, filtro in (universos or UNIVERSOS).items():
        try:
            f = fallout(anio=anio, condado=bench.fips, filtro_universo=filtro)
            valores[nombre] = (
                f.pct,
                "(%d/%d, %d compradas excluidas)"
                % (f.caidas, f.denominador, f.compradas_excluidas),
            )
        except HmdaNoDisponible as exc:
            valores[nombre] = (None, "no disponible: %s" % exc)

    return Comparacion(
        fips=bench.fips, anio=anio, campo="fallout %",
        valor_modelmatch=bench.fallout_pct,
        denominador_modelmatch=bench.fallout_denominador,
        valores_hmda=valores,
    )


def comparar_fha(bench: BenchmarkCondado, *, anio: int,
                 universos: dict[str, dict] | None = None) -> Comparacion:
    valores: dict[str, tuple[float | None, str]] = {}
    for nombre, filtro in (universos or UNIVERSOS).items():
        try:
            m = mix_de_mercado(anio=anio, condado=bench.fips, filtro_universo=filtro)
            valores[nombre] = (m.fha_pct, "(%s)" % m.pct("2"))
        except HmdaNoDisponible as exc:
            valores[nombre] = (None, "no disponible: %s" % exc)

    return Comparacion(
        fips=bench.fips or "?", anio=anio, campo="cuota FHA",
        valor_modelmatch=bench.mix_tipo_prestamo.get("FHA"),
        denominador_modelmatch=bench.mix_denominador,
        valores_hmda=valores,
    )


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mm", type=Path, required=True,
                    help="archivo o directorio de capturas de condado")
    ap.add_argument("--anio", type=int, default=2023,
                    help="año de HMDA contra el que comparar")
    args = ap.parse_args(argv)

    if args.mm.is_dir():
        archivos = sorted(args.mm.glob("condado_*.txt"))
    else:
        archivos = [args.mm]

    if not archivos:
        print("No encontre capturas de condado en %s." % args.mm)
        print("El nombre tiene que ser condado_{FIPS}_{YYYYMMDD}.txt")
        return 1

    coincidencias = 0
    comparadas = 0
    for archivo in archivos:
        try:
            bench = leer_benchmark_condado(archivo)
        except Exception as exc:  # noqa: BLE001
            print("%s: no se pudo leer -- %s" % (archivo.name, exc))
            print("")
            continue

        print("=" * 74)
        print("%s  (%s, %s)" % (archivo.name, bench.nombre_condado, bench.estado))
        print("=" * 74)
        faltan = bench.falta()
        if faltan:
            print("  campos vacios en la captura: %s" % ", ".join(faltan))

        for comparacion in (comparar_fallout(bench, anio=args.anio),
                            comparar_fha(bench, anio=args.anio)):
            print(comparacion.informe())
            print("")
            if comparacion.coincide is not None:
                comparadas += 1
                coincidencias += int(comparacion.coincide)

    print("=" * 74)
    if comparadas == 0:
        print("No se pudo comparar ninguna metrica.")
        return 1
    print("Coinciden %d de %d metricas comparadas (tolerancia %.1f pp)."
          % (coincidencias, comparadas, TOLERANCIA_PP))
    if coincidencias == comparadas:
        print("")
        print("HMDA reemplaza estas metricas. Es gratis, nacional y no caduca:")
        print("la prueba de Model Match ya rindio lo que tenia que rendir.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
