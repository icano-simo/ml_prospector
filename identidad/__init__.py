"""Capa de identidad: un modulo propio, no un merge por nombre.

    normalizacion.py  las llaves de cruce: E.164, email, nombre, licencia
    valores.py        valores versionados con fuente y fecha. Nada se sobrescribe
    cascada.py        licencia -> telefono -> email -> nombre+condado+volumen
    registro.py       el registro unificado

Un merge por nombre parece funcionar porque produce filas. Lo que no produce es
la informacion de cuanto confiar en cada fila, y esa es la unica cosa que
distingue un registro unificado de un registro inventado.
"""

from identidad.cascada import (  # noqa: F401
    Candidato,
    Confianza,
    Cruce,
    LogDeConflictos,
    cruzar,
    mejor_cruce,
)
from identidad.registro import RegistroUnificado  # noqa: F401
from identidad.valores import Campo, Valor  # noqa: F401
