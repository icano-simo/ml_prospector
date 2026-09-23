"""Quien NO entra a una cola de contacto, y por que.

El libro trae una decision ya tomada -- `pacs: nivel_de_calificacion` -- que el
motor nunca leyo. Resultado medido el 2026-09-23: Lisa Munoz salio con dolor
primario P-Q10 y confianza MEDIA, y Andrea Saavedra con P-Q09. Las dos estan
excluidas por metodologia. El motor las devolvia como candidatas normales.

La forma del error es la de siempre en este proyecto: **nadie rechazo nada.**
No hubo una guarda que fallara; hubo una columna que nadie abrio. Un dato que
existe y no se lee se comporta exactamente igual que un dato que no existe --
pero se siente como si estuviera cubierto, porque esta ahi.

Por que la exclusion NO se deduce de los qualifiers
---------------------------------------------------
Se lee del libro y no se recalcula. Un descarte por cobertura, por NMLS propio
o por nombre ambiguo es una decision humana o de otra etapa; el motor PACS-H
no tiene con que reconstruirla. Si la dedujera, el dia que un qualifier cambie
volveria a contactar a alguien que ya se decidio no contactar -- y nadie se
enteraria, porque el motor "funciono".

La exclusion tampoco borra la evaluacion. Lisa Munoz sigue teniendo su P-Q10 y
su Instagram raspado: el raspado no estorba. Lo que no puede pasar es que ese
P-Q10 la ponga en una lista de envio.
"""
from __future__ import annotations

#: Los niveles del libro que significan **no contactable**. Literales del libro,
#: normalizados a mayusculas y sin espacios de sobra.
#:
#: `RECLASIFICADO POR MMI` llega con una coletilla ("· fuera de ICP"), asi que
#: se compara por prefijo y no por igualdad -- una comparacion exacta contra un
#: valor con coletilla es otra guarda que pasa sin comprobar nada.
NO_CONTACTABLES = (
    "DESCARTADO",
    "BLOQUEADO POR COBERTURA",
    "RECLASIFICADO POR MMI",
)

#: Los niveles que SI son contactables. Esta lista existe para que un nivel
#: nuevo en el libro no caiga silenciosamente del lado contactable: si aparece
#: algo que no esta ni aqui ni arriba, `clasificar` lo dice.
CONTACTABLES = ("MQL", "PRE-MQL")


class NivelDesconocido(ValueError):
    """Un nivel del libro que no esta en ninguna de las dos listas."""


def _normalizar(nivel) -> str:
    if nivel is None:
        return ""
    return " ".join(str(nivel).strip().upper().split())


def clasificar(nivel) -> str | None:
    """Devuelve el motivo de exclusion, o `None` si es contactable.

    Un nivel vacio NO es una exclusion: es una fila sin diagnosticar, y eso lo
    gobierna la confianza, no esta regla.
    """
    n = _normalizar(nivel)
    if not n:
        return None
    for malo in NO_CONTACTABLES:
        if n.startswith(malo):
            return malo
    for bueno in CONTACTABLES:
        if n.startswith(bueno):
            return None
    raise NivelDesconocido(
        "nivel de calificacion que no esta clasificado: %r. Agregalo a "
        "NO_CONTACTABLES o a CONTACTABLES; dejarlo caer del lado contactable "
        "por omision es como Lisa Munoz entro a la cola." % (nivel,))


def es_contactable(nivel) -> bool:
    return clasificar(nivel) is None
