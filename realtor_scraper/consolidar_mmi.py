"""
Consolidar MMI enriched -> sabana de entrada para el motor PACS-H
=================================================================
Era score_mmi.py. Aplicaba el modelo XGBoost y devolvia un propensity_score
0-100 con tiers A/B/C/D. Eso se retiro el 2026-09-21: el label sobre el que se
entreno no es valido (ver la seccion "Que se intento y no funciono" del README),
y no se vuelve a entrenar hasta que existan resultados reales de la prospeccion
de 60 dias con una definicion escrita de que cuenta como conversion.

Lo que queda, y sigue siendo util:

  1. Junta todos los mmi_enriched_*.csv en una sola sabana.
  2. Agrega Census por estado, ponderado por poblacion.
  3. Deriva los flags de brokerage desde el nombre de la empresa.
  4. Escribe output/mmi_consolidado_YYYYMMDD_HHMM.csv

Lo que NO hace, a proposito: no puntua, no ordena por propension y no asigna
tier. El diagnostico lo produce el motor de reglas PACS-H a partir de esta
sabana. Un numero que ordena una cola de llamadas es exactamente el artefacto
que no se puede volver a publicar sin un label valido.

Regla de guardia que se aplica aca: toda señal de contenido ausente queda en
null, nunca en False. La version anterior rellenaba con .fillna(0) antes de
armar la matriz de features, y eso convertia 1.075 perfiles sin datos de
Instagram en 1.075 perfiles con señales negativas.

Usage:
  python consolidar_mmi.py
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pgeocode

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "output"
CENSUS_CSV = (
    ROOT.parent / "latino_re_engine" / "data" / "output" / "latino_market_zip_2024.csv"
)

STATE_ABBREV = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia", "PR": "Puerto Rico",
}

# Lexico de brokerage. Alimenta R6 de la capa de realtor.
#
# Cuidado con las palabras sueltas: se buscan con limite de palabra justamente
# porque "latin" sin limite matchea "platinum". Es la misma familia de error que
# el \bestates?\b que clasifico como lujo a mas de mil agentes por matchear
# "real estate" (documentado en la referencia 11 de la skill homesi-pacs-scoring).
LATINO_BROKERAGES = {
    "la rosa", "casa buena", "movil realty", "vive realty", "agent trust",
    "naim real estate", "home prime", "casa", "hogar", "latin", "hispano",
    "hispanic", "latino", "habla", "bilingual", "multicultural",
}
SPANISH_NAME_WORDS = {
    "casa", "hogar", "vive", "movil", "buena", "bueno", "casas", "hogares",
    "vida", "sol", "estrella", "luna", "tierra", "familia", "unidos",
    "latina", "latino",
}

CENSUS_METRICS = [
    "hispanic_pct", "overall_score", "median_household_income",
    "first_home_buyer_score", "spanish_marketing_opportunity",
    "lep_spanish_pct", "bilingual_spanish_pct", "homeownership_rate",
    "latino_market_score", "first_time_buyer_potential",
]


def _keyword_match(text: str, keywords: set[str]) -> bool:
    n = text.lower()
    for w in keywords:
        if " " in w:  # frase multi-palabra: substring exacto alcanza
            if w in n:
                return True
        elif re.search(r"\b" + re.escape(w) + r"\b", n):
            return True
    return False


def cargar_enriched() -> pd.DataFrame:
    archivos = sorted(OUT_DIR.glob("mmi_enriched_*.csv"), key=lambda p: p.stat().st_mtime)
    if not archivos:
        raise SystemExit(
            "No hay mmi_enriched_*.csv en %s. Corre primero mmi_enricher.py." % OUT_DIR
        )
    print("Cargando %d archivo(s) enriched..." % len(archivos))
    partes = []
    for f in archivos:
        d = pd.read_csv(f, dtype=str)
        if "batch_name" not in d.columns:
            d["batch_name"] = f.stem.replace("mmi_enriched_", "carga_")
        partes.append(d)
    df = pd.concat(partes, ignore_index=True)
    df = df.drop_duplicates(subset=["full_name"], keep="last")
    print("  Realtors unicos: %s" % format(len(df), ","))
    return df


def census_por_estado() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (lookup por nombre de estado, resumen de poblacion por estado)."""
    if not CENSUS_CSV.exists():
        raise SystemExit(
            "No encuentro %s.\nCorre primero el pipeline de latino_re_engine." % CENSUS_CSV
        )
    census = pd.read_csv(CENSUS_CSV)
    nomi = pgeocode.Nominatim("us")
    zips = census["zip_code"].astype(str).str.zfill(5).tolist()
    partes = [nomi.query_postal_code(zips[i:i + 5000]) for i in range(0, len(zips), 5000)]
    geo = pd.concat(partes, ignore_index=True)

    census["state_abbr"] = geo["state_code"].values
    census = census[census["state_abbr"].notna()].copy()
    census[CENSUS_METRICS] = census[CENSUS_METRICS].apply(pd.to_numeric, errors="coerce")
    census["total_population"] = pd.to_numeric(
        census["total_population"], errors="coerce"
    ).fillna(0)

    def promedio_ponderado(grupo: pd.DataFrame) -> pd.Series:
        pob = grupo["total_population"]
        total = pob.sum()
        return pd.Series({
            "census_" + m: (
                (grupo[m].fillna(0) * pob).sum() / total if total > 0 else None
            )
            for m in CENSUS_METRICS
        })

    por_estado = census.groupby("state_abbr").apply(promedio_ponderado).reset_index()
    por_estado["state"] = por_estado["state_abbr"].map(STATE_ABBREV)
    lookup = por_estado.set_index("state")[
        ["state_abbr"] + ["census_" + m for m in CENSUS_METRICS]
    ]
    print("  Estados con Census: %d" % len(por_estado))

    hisp = (
        census["hispanic_population"]
        if "hispanic_population" in census.columns
        else pd.Series(0.0, index=census.index)
    )
    census["_hisp_abs"] = pd.to_numeric(hisp, errors="coerce").fillna(0)
    resumen = census.groupby("state_abbr").agg(
        total_population=("total_population", "sum"),
        hispanic_pop=("_hisp_abs", "sum"),
    ).reset_index()
    resumen["hispanic_pct"] = (
        resumen["hispanic_pop"] / resumen["total_population"].replace(0, np.nan)
    ).fillna(0)
    resumen["state"] = resumen["state_abbr"].map(STATE_ABBREV)
    resumen = resumen.dropna(subset=["state"])
    return lookup, resumen


# Señales booleanas de contenido. La lista existe para una sola cosa: para que
# el mapa de disponibilidad sepa cuales NO se pueden rellenar con False.
SENALES_CONTENIDO = [
    "ig_spanish_signals", "ig_realtor_signals", "ig_posts_spanish",
    "ig_mentions_latino", "ig_nahrep", "ig_collaborates", "ig_is_private",
]


def normalizar_booleanos(df: pd.DataFrame) -> pd.DataFrame:
    """Pasa las señales a booleano nullable. Ausente queda <NA>, no False.

    Esta es la correccion mas importante del archivo. La version anterior hacia
    .fillna(0).astype(int) y eso le decia al modelo que 1.075 perfiles sin datos
    de Instagram no hablaban español, no mencionaban a la comunidad y no eran
    privados. Tres afirmaciones, ninguna medida.
    """
    mapa = {
        True: True, False: False,
        "True": True, "False": False,
        "true": True, "false": False,
        1: True, 0: False, "1": True, "0": False,
    }
    for col in SENALES_CONTENIDO:
        if col in df.columns:
            df[col] = df[col].map(mapa).astype("boolean")
    return df


def main() -> None:
    print("=" * 62)
    print("Consolidar MMI enriched -> sabana de entrada para PACS-H")
    print("=" * 62)

    df = cargar_enriched()
    if "ig_handle" in df.columns:
        hit = df["ig_handle"].notna()
        print("  Handle de Instagram presente: %s (%.0f%%)" % (
            format(int(hit.sum()), ","), hit.mean() * 100))
        print("  OJO: 'presente' no es 'verificado'. La verificacion de handle")
        print("       la hace instagram/verificacion.py; sin ella este numero no")
        print("       significa que el perfil sea de esa persona.")

    print("\nComputando Census por estado...")
    census_lookup, resumen_estado = census_por_estado()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    resumen_estado.to_csv(OUT_DIR / "state_census_summary.csv", index=False, encoding="utf-8")
    print("  Guardado: state_census_summary.csv (%d estados)" % len(resumen_estado))

    print("\nDerivando features...")
    df["state_clean"] = df["state"].str.strip()
    es_abbr = df["state_clean"].str.len() == 2
    df.loc[es_abbr, "state_clean"] = (
        df.loc[es_abbr, "state_clean"].str.upper().map(STATE_ABBREV)
    )
    df = df.merge(census_lookup, left_on="state_clean", right_index=True, how="left")

    empresa = df["company"].fillna("")
    df["company_has_spanish_name"] = empresa.apply(
        lambda n: _keyword_match(n, SPANISH_NAME_WORDS)
    )
    df["company_is_latino_brokerage"] = empresa.apply(
        lambda n: _keyword_match(n, LATINO_BROKERAGES)
    )

    for col in ("ig_followers", "ig_posts"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = normalizar_booleanos(df)

    # Guarda redundante: ninguna señal de contenido puede haber quedado en
    # False donde el perfil no se leyo. Falla ruidosamente si pasa.
    if "ig_handle" in df.columns:
        sin_perfil = df["ig_handle"].isna()
        for col in SENALES_CONTENIDO:
            if col not in df.columns:
                continue
            falsos_inventados = int((sin_perfil & (df[col] == False)).sum())  # noqa: E712
            if falsos_inventados:
                raise AssertionError(
                    "%d filas sin handle tienen %s=False. Eso es una afirmacion "
                    "que nadie midio: tiene que ser null." % (falsos_inventados, col)
                )

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    salida = OUT_DIR / ("mmi_consolidado_%s.csv" % ts)
    df.to_csv(salida, index=False, encoding="utf-8")

    print("\n" + "=" * 62)
    print("RESULTADO: %s filas consolidadas" % format(len(df), ","))
    print("=" * 62)
    print("\nDisponibilidad de las señales de contenido (el reporte de lote):")
    for col in SENALES_CONTENIDO:
        if col not in df.columns:
            print("  %-22s ausente del archivo" % col)
            continue
        disp = int(df[col].notna().sum())
        print("  %-22s medida en %s de %s (%.1f%%)" % (
            col, format(disp, ","), format(len(df), ","), disp / len(df) * 100))

    print("\nGuardado en: %s" % salida)
    print("\nEste archivo NO trae score ni tier. El diagnostico lo produce el")
    print("motor de reglas PACS-H; aca solo se preparan sus insumos.")


if __name__ == "__main__":
    main()
