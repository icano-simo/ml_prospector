"""La exclusion del libro: la columna que el motor nunca leyo.

El caso que da origen a estas pruebas: Lisa Munoz, DESCARTADO en el libro, salio
con dolor primario P-Q10 y confianza MEDIA. Nada fallo -- nadie miro la columna.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.exclusion import (  # noqa: E402
    CONTACTABLES,
    NO_CONTACTABLES,
    NivelDesconocido,
    clasificar,
    es_contactable,
)


def test_los_no_contactables_se_excluyen():
    for nivel in NO_CONTACTABLES:
        assert clasificar(nivel) == nivel, nivel
        assert not es_contactable(nivel), nivel


def test_los_contactables_pasan():
    for nivel in CONTACTABLES:
        assert clasificar(nivel) is None, nivel
        assert es_contactable(nivel), nivel


def test_reclasificado_llega_con_coletilla():
    """El valor real del libro trae `· fuera de ICP` pegado.

    Una comparacion por igualdad contra 'RECLASIFICADO POR MMI' devolveria
    contactable -- y esa es exactamente la forma de la guarda que pasa porque
    no tiene nada que comparar.
    """
    assert (clasificar("RECLASIFICADO POR MMI · fuera de ICP")
            == "RECLASIFICADO POR MMI")


def test_no_depende_de_mayusculas_ni_de_espacios():
    for nivel in ("descartado", "  Descartado  ", "Bloqueado  por   Cobertura"):
        assert not es_contactable(nivel), nivel


def test_sin_nivel_no_es_una_exclusion():
    """Sin diagnosticar no es lo mismo que descartado.

    Quien no tiene nivel no esta excluido: esta sin evaluar, y eso lo gobierna
    la confianza. Excluirlo aqui seria dejar fuera a los 3.332 PRE-MQL por no
    haber llegado a mirarlos.
    """
    for vacio in (None, "", "   "):
        assert clasificar(vacio) is None, repr(vacio)


def test_un_nivel_nuevo_no_cae_del_lado_contactable():
    """Si el libro estrena un nivel, tiene que doler -- no colarse.

    El error original fue una omision silenciosa. Que la omision siguiente
    grite es lo unico que evita repetirlo.
    """
    try:
        clasificar("PAUSADO POR LEGAL")
    except NivelDesconocido:
        return
    raise AssertionError("un nivel desconocido se trato como contactable")


def test_los_cinco_niveles_del_libro_estan_clasificados():
    """Los valores reales, contados en la base el 2026-09-23."""
    reales = {
        "MQL": 756, "PRE-MQL": 3332, "DESCARTADO": 135,
        "BLOQUEADO POR COBERTURA": 25,
        "RECLASIFICADO POR MMI · fuera de ICP": 1,
    }
    excluidos = sum(n for niv, n in reales.items() if clasificar(niv))
    assert excluidos == 161, excluidos
    contactables = sum(n for niv, n in reales.items() if not clasificar(niv))
    assert contactables == 4088, contactables


def test_la_exclusion_no_borra_el_diagnostico():
    """Lisa Munoz conserva su P-Q10; lo que pierde es la cola de contacto.

    El raspado de Instagram y la evaluacion PACS-H no estorban. La regla solo
    gobierna si la persona se puede contactar, y no toca ni un qualifier.
    """
    import motor.exclusion as m
    assert clasificar("DESCARTADO") == "DESCARTADO"
    assert not [n for n in dir(m) if "dolor" in n.lower() or "qualif" in n.lower()]


def _correr():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    fallas = []
    for nombre, fn in fns:
        try:
            fn()
            print("  ok   %s" % nombre)
        except Exception as exc:  # noqa: BLE001
            fallas.append((nombre, exc))
            print("  FALLA %s -- %r" % (nombre, exc))
    print("")
    print("  %d pruebas, %d fallas" % (len(fns), len(fallas)))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(_correr())
