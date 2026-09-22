"""Que entra al motor, y que no puede entrar.

Dos barreras distintas, y hacen falta las dos
---------------------------------------------
`pacs.guardas.verificar_entradas_de_inferencia` impide que una REGLA lea un
campo prohibido. Es necesaria y no alcanza: deja el campo dentro del dataset.

    Un campo que existe y que la guarda bloquea es una tentacion esperando:
    alguien lo va a usar en seis meses cuando la guarda le parezca un estorbo.

Asi que el campo se saca del dataset ANTES de que el motor lo vea. Si alguien
quiere usarlo tiene que ir a buscarlo a otra tabla, marcada como no utilizable,
y esa friccion es el punto.
"""
from __future__ import annotations

#: Columnas del libro v3 que NO entran al motor, con la razon escrita.
#:
#: No se borran del libro -- ahi viven por trazabilidad de la v2-- pero no
#: llegan al dataset de evaluacion.
CAMPOS_FUERA_DEL_MOTOR: dict[str, str] = {
    "ev: broker apellido hisp": (
        "infiere origen a partir del apellido. ECOA Regulation B: no se infiere "
        "nicho, idioma ni mercado desde apellido, etnia u origen, ni del "
        "realtor ni de sus clientes ni de los loan officers. La señal legitima "
        "es transaccional: FHA, bandas de precio, geografia, LMI, y el idioma "
        "de lo que la persona publica."
    ),
    "ev: broker palabras es": (
        "misma familia: deduce el perfil del brokerage de su nombre. Se deja "
        "fuera por precaucion hasta que alguien documente que mide y contra "
        "que. Si resulta legitima, se saca de esta lista con su justificacion."
    ),
}


class CampoProhibidoEnElDataset(AssertionError):
    """Un campo que no puede llegar al motor llego igual."""


def limpiar_entrada(registro: dict) -> tuple[dict, list[str]]:
    """Saca los campos prohibidos. Devuelve (registro limpio, que se saco).

    Se registra lo que se saco en vez de sacarlo en silencio: si un dia la
    lista cambia, el log de una evaluacion vieja dice con que entro.
    """
    sacados = [c for c in registro if c in CAMPOS_FUERA_DEL_MOTOR]
    if not sacados:
        return dict(registro), []
    limpio = {k: v for k, v in registro.items() if k not in CAMPOS_FUERA_DEL_MOTOR}
    return limpio, sorted(sacados)


def verificar_dataset(columnas) -> None:
    """Falla si una columna prohibida quedo en el dataset que entra al motor.

    Es la guarda redundante, a proposito: `limpiar_entrada` ya las saca. Esta
    existe porque la leccion de `redactar()` fue que una guarda que no esta en
    el camino que produce el archivo no es una guarda, y la unica forma de
    saberlo es que reviente.
    """
    presentes = sorted(set(columnas) & set(CAMPOS_FUERA_DEL_MOTOR))
    if presentes:
        detalle = "\n".join(
            "  %s: %s" % (c, CAMPOS_FUERA_DEL_MOTOR[c]) for c in presentes
        )
        raise CampoProhibidoEnElDataset(
            "estas columnas no pueden entrar al motor:\n%s" % detalle
        )
