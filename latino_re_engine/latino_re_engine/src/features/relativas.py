"""Features relativas: el ZCTA del agente dividido por la mediana de su condado.

El cambio de tratamiento
------------------------
El modelo anterior **excluia** las metricas de Census para que no memorizara
estados. El README lo decia asi: "Las metricas del Census (% hispano por estado)
fueron excluidas del modelo para evitar que el modelo memorizara estados en
lugar de evaluar el perfil individual del realtor."

Excluir resuelve la memorizacion tirando la señal. Este modulo hace otra cosa:
**normaliza contra el condado.**

Una feature relativa no permite memorizar el estado -- California y Texas tienen
los dos condados de entrada y condados caros, y el ratio los pone en la misma
escala -- y si captura lo que interesa: si la persona opera en zona de entrada o
en zona cara **para su propio mercado**.

Por que el condado y no el estado
---------------------------------
Porque el estado es demasiado grueso. El valor mediano de vivienda de California
esta dominado por el area de la bahia y Los Angeles; un agente en Bakersfield
comparado contra la mediana estatal parece barato en un estado caro, cuando en
su propio condado puede estar en el tramo alto. El condado es la unidad en la
que un agente compite.

La guarda que aplica
--------------------
Estas variables **describen donde opera una persona, no quien es**. Ninguna se
usa para clasificar a nadie. La barrera esta en
`pacs.guardas.verificar_uso_de_tract`, que exige declarar el proposito, y el
proposito legitimo aca es `"feature_relativa"`.

Y el techo de evidencia: una feature de mercado es **E3, plausibilidad de
mercado, techo de intensidad 1 y nunca mas.** Un ratio de asequibilidad del ZCTA
no verbaliza nada: sugiere.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: Metricas que tiene sentido relativizar contra el condado. Son de nivel y no
#: de proporcion: un ratio de proporciones no significa lo mismo.
METRICAS_DE_NIVEL = (
    "median_home_value",
    "median_gross_rent",
    "median_household_income",
    "hispanic_median_income",
)

#: Proporciones. Se relativizan por DIFERENCIA de puntos, no por cociente:
#: 40% sobre 20% da un ratio de 2,0 que suena enorme, mientras 60% sobre 30% da
#: el mismo 2,0 -- el cociente pierde la escala, la diferencia no.
METRICAS_DE_PROPORCION = (
    "hispanic_pct",
    "spanish_home_pct",
    "lep_spanish_pct",
    "homeownership_rate",
    "hispanic_renter_pct",
    "multigen_pct",
    "self_employed_not_inc_pct",
    "cost_burden_pct",
)

#: Minimo de ZCTAs por condado para que la mediana del condado signifique algo.
#: Con dos ZCTAs la "mediana del condado" es el promedio de dos numeros.
MIN_ZCTAS_POR_CONDADO = 4


def agregar_features_relativas(
    df: pd.DataFrame,
    *,
    columna_condado: str = "county_fips",
    metricas_nivel: tuple[str, ...] = METRICAS_DE_NIVEL,
    metricas_proporcion: tuple[str, ...] = METRICAS_DE_PROPORCION,
) -> pd.DataFrame:
    """Agrega `<metrica>_rel_condado` para cada metrica disponible.

    Para metricas de nivel: cociente contra la mediana del condado.
    Para proporciones: diferencia en puntos contra la mediana del condado.

    Donde el condado no tiene suficientes ZCTAs, la feature queda en **NaN, no
    en 1.0 ni en 0.0**. Un ratio de 1,0 significa "igual a su condado", que es
    una afirmacion; la ausencia de dato no lo es.
    """
    df = df.copy()

    if columna_condado not in df.columns:
        df["rel_condado_disponible"] = False
        df["rel_condado_motivo"] = (
            "falta la columna %r: sin condado no hay contra que relativizar. "
            "Usa geo.crosswalk para asignar el condado desde el ZIP."
            % columna_condado
        )
        return df

    condado = df[columna_condado].astype("string")
    tamanos = condado.map(condado.value_counts())
    condado_suficiente = tamanos >= MIN_ZCTAS_POR_CONDADO

    df["rel_condado_n_zctas"] = tamanos
    df["rel_condado_disponible"] = condado_suficiente
    df["rel_condado_motivo"] = np.where(
        condado_suficiente, "",
        "el condado tiene menos de %d ZCTAs: su mediana no es una referencia"
        % MIN_ZCTAS_POR_CONDADO,
    )

    for metrica in metricas_nivel:
        if metrica not in df.columns:
            continue
        valores = pd.to_numeric(df[metrica], errors="coerce")
        mediana = valores.groupby(condado).transform("median")
        # Mediana 0 o nula: el cociente no existe. No se rellena con 1.
        ratio = valores / mediana.replace(0, np.nan)
        df[metrica + "_rel_condado"] = ratio.where(condado_suficiente)
        df[metrica + "_mediana_condado"] = mediana.where(condado_suficiente)

    for metrica in metricas_proporcion:
        if metrica not in df.columns:
            continue
        valores = pd.to_numeric(df[metrica], errors="coerce")
        mediana = valores.groupby(condado).transform("median")
        df[metrica + "_rel_condado"] = (valores - mediana).where(condado_suficiente)
        df[metrica + "_mediana_condado"] = mediana.where(condado_suficiente)

    return df


def clasificar_tramo_de_entrada(
    df: pd.DataFrame,
    *,
    columna: str = "median_home_value_rel_condado",
) -> pd.DataFrame:
    """Etiqueta si el ZCTA es de entrada, medio o caro PARA SU CONDADO.

    Los cortes son una regla propia, no vienen de ningun archivo, y por eso
    estan escritos aca para que alguien pueda discutirlos:

        < 0,80        zona de entrada
        0,80 - 1,25   zona media
        > 1,25        zona cara

    La etiqueta es `None` donde el ratio no existe. Y la evidencia que sostiene
    es **E3**: techo de intensidad 1.
    """
    df = df.copy()
    if columna not in df.columns:
        df["tramo_de_entrada"] = None
        return df

    ratio = pd.to_numeric(df[columna], errors="coerce")
    tramo = pd.Series(pd.NA, index=df.index, dtype="string")
    tramo[ratio < 0.80] = "entrada"
    tramo[(ratio >= 0.80) & (ratio <= 1.25)] = "medio"
    tramo[ratio > 1.25] = "caro"
    df["tramo_de_entrada"] = tramo
    df["tramo_de_entrada_grado_evidencia"] = np.where(tramo.notna(), "E3", None)
    return df


def reporte_de_cobertura(df: pd.DataFrame) -> dict:
    """Cuantas filas tienen feature relativa y cuantas no, con el motivo.

    Es el reporte de lote de esta capa. Va a la salida, no a un log.
    """
    total = len(df)
    if total == 0:
        return {"filas": 0}

    disponible = int(df.get("rel_condado_disponible", pd.Series(dtype=bool)).sum())
    motivos: dict[str, int] = {}
    if "rel_condado_motivo" in df.columns:
        for motivo, n in df["rel_condado_motivo"].value_counts().items():
            if str(motivo).strip():
                motivos[str(motivo)] = int(n)

    relativas = sorted(c for c in df.columns if c.endswith("_rel_condado"))
    por_metrica = {
        c: "%d de %d (%.1f%%)" % (
            int(df[c].notna().sum()), total,
            df[c].notna().mean() * 100,
        )
        for c in relativas
    }

    return {
        "filas": total,
        "con_condado_suficiente": "%d de %d (%.1f%%)" % (
            disponible, total, disponible / total * 100,
        ),
        "motivos_de_ausencia": motivos,
        "cobertura_por_metrica": por_metrica,
        "nota": (
            "las features relativas son evidencia E3, plausibilidad de mercado: "
            "techo de intensidad 1 y nunca mas. Describen donde opera una "
            "persona, no quien es."
        ),
    }
