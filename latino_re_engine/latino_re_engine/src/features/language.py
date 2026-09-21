"""
Language feature engineering — Spanish-speaker signals for marketing targeting.
"""

import numpy as np
import pandas as pd

from src.features.demographic import _safe_div


def add_language_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    lang_total = df.get("language_households_total", pd.Series(np.nan, index=df.index))
    spanish_well = df.get("spanish_speak_english_well", pd.Series(np.nan, index=df.index))
    spanish_not_well = df.get("spanish_speak_english_not_well", pd.Series(np.nan, index=df.index))
    spanish_total = df.get("spanish_households_total", pd.Series(np.nan, index=df.index))

    # Total de hogares hispanohablantes: B16002_003E, que YA es el total.
    #
    # Hasta el 2026-09-21 esto era `spanish_well + spanish_not_well`, con
    # spanish_well apuntando por error a _003E -- el total. Es decir que la
    # suma daba total + LEP y **contaba dos veces a los hogares LEP**, dejando
    # spanish_home_pct inflado en toda la serie.
    #
    # Se usa el total publicado y no la suma de sus partes: si no cuadran, es
    # un problema del vintage y hay que verlo, no promediarlo.
    df["spanish_households"] = spanish_total
    df["spanish_home_pct"] = _safe_div(spanish_total, lang_total)

    # Control de consistencia. Las partes tienen que sumar el total; si no,
    # alguna variable cambio de significado entre vintages del ACS.
    partes = spanish_well.fillna(0) + spanish_not_well.fillna(0)
    descuadre = (partes - spanish_total.fillna(0)).abs()
    tolerancia = spanish_total.fillna(0) * 0.02
    df["spanish_parts_mismatch"] = descuadre > tolerancia.clip(lower=1)

    # Limited English proficiency (LEP) — primary Spanish-language marketing target
    df["lep_spanish_pct"] = _safe_div(spanish_not_well, lang_total)

    # English-comfortable Spanish speakers — bilingual segment
    df["bilingual_spanish_pct"] = _safe_div(spanish_well, lang_total)

    # Spanish marketing opportunity:
    # high LEP = high need for Spanish-language loan officers
    # weighted: LEP households matter more than bilingual for outreach urgency
    df["spanish_marketing_opportunity"] = (
        df["lep_spanish_pct"].fillna(0) * 0.65
        + df["bilingual_spanish_pct"].fillna(0) * 0.35
    )

    return df
