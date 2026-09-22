"""Normalizar el estado a su codigo de dos letras.

Por que existe
--------------
`CA`, `California` y `CALIFORNIA` entraron como etiqueta en tres capturas del
mismo mercado. En la biblioteca de geografias eso son **tres mercados
distintos**, y la unica pista de que son el mismo es que alguien los mire uno al
lado del otro.

Es el error barato de arreglar hoy y caro despues: cuando haya 300 capturas, la
biblioteca dira que hay 40 geografias donde hay 15, y el promedio de cada una se
habra calculado sobre un tercio de sus filas.
"""
from __future__ import annotations

#: codigo -> nombre. Los 50 estados, DC y los territorios que salen en el libro.
ESTADOS = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida",
    "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky",
    "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico", "VI": "U.S. Virgin Islands", "GU": "Guam",
}

#: nombre en minusculas -> codigo.
_POR_NOMBRE = {v.lower(): k for k, v in ESTADOS.items()}


def normalizar_estado(valor: str | None) -> str | None:
    """'california' | 'CALIFORNIA' | ' ca ' -> 'CA'. Desconocido -> None.

    Devuelve None y no el texto original cuando no reconoce: dejar pasar un
    valor libre es lo que produjo las tres variantes. Quien llama decide si eso
    es un error o un aviso, pero no se guarda una cuarta forma.
    """
    if not valor:
        return None
    limpio = " ".join(str(valor).split()).strip(" .,")
    if not limpio:
        return None
    if len(limpio) == 2 and limpio.upper() in ESTADOS:
        return limpio.upper()
    return _POR_NOMBRE.get(limpio.lower())
