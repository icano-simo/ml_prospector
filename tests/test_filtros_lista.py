"""Los filtros de la lista, y la diferencia entre positivo y complemento.

Sin red: se reproduce la lógica de `realtors()` sobre conjuntos, que es donde
estaba el error. La comprobación contra la base real va en el reporte.

El error medido: `mm=no` mostraba «300 de 400». El 400 era `TOPE_IDS`, o sea el
tamaño del recorte, no un dato. Y como los ids se ordenan por UUID antes de
cortar, la lista no eran los primeros 400 por nombre sino 400 cualesquiera --
una lista ordenada alfabéticamente que en realidad es una muestra al azar, y
que no se ve rara por ningún lado.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from api.rutas import TOPE_IDS  # noqa: E402

#: El lote real: 4.249 realtors, 3 con Model Match, 298 con clase de Instagram.
TOTAL = 4249
CON_MM = {"mm-1", "mm-2", "mm-3"}
CON_IG = {"ig-%d" % i for i in range(298)}


def _plan(con_mm=None, ig=None):
    """Qué consulta arma `realtors()`: (incluir, excluir).

    Es la misma decisión que toma la ruta, aislada de la red.
    """
    incluir, excluir = None, set()
    if con_mm == "si":
        incluir = set(CON_MM)
    elif con_mm == "no":
        excluir |= CON_MM
    if ig == "sin_raspar":
        excluir |= CON_IG
    elif ig == "utilizable":
        incluir = CON_IG if incluir is None else (incluir & CON_IG)
    return incluir, excluir


def test_un_positivo_va_por_in():
    incluir, excluir = _plan(con_mm="si")
    assert incluir == CON_MM
    assert not excluir
    assert len(incluir) <= TOPE_IDS


def test_un_complemento_va_por_NOT_in_sobre_el_conjunto_chico():
    """«No tiene Model Match» son 4.246 ids, y se filtra con los 3 que sí."""
    incluir, excluir = _plan(con_mm="no")
    assert incluir is None, "no hay que materializar el complemento"
    assert excluir == CON_MM
    assert len(excluir) == 3


def test_el_complemento_nunca_se_trunca():
    """Lo que rompía: 4.246 ids cortados en 400.

    Con `not.in` sobre el conjunto chico, lo que viaja en la URL son 3 ids y
    298, muy por debajo del tope. El complemento no se materializa nunca.
    """
    for caso in ({"con_mm": "no"}, {"ig": "sin_raspar"},
                 {"con_mm": "no", "ig": "sin_raspar"}):
        _inc, exc = _plan(**caso)
        assert len(exc) <= TOPE_IDS, (caso, len(exc))


def test_sin_raspar_excluye_los_298_y_no_los_3951():
    incluir, excluir = _plan(ig="sin_raspar")
    assert incluir is None
    assert len(excluir) == 298
    # El resultado es el complemento, y es grande: eso es correcto y es el
    # numero que tiene que salir en pantalla.
    assert TOTAL - len(excluir) == 3951


def test_positivo_y_complemento_a_la_vez():
    """`mm=si&ig=sin_raspar`: incluir 3, excluir 298."""
    incluir, excluir = _plan(con_mm="si", ig="sin_raspar")
    assert incluir == CON_MM
    assert excluir == CON_IG


def test_dos_positivos_se_intersecan():
    incluir, excluir = _plan(con_mm="si", ig="utilizable")
    assert incluir == (CON_MM & CON_IG)
    assert not excluir


def test_un_positivo_vacio_no_es_lo_mismo_que_sin_filtro():
    """«Ninguno cumple» y «no hay filtro» dan listas muy distintas."""
    incluir, _e = _plan(con_mm="si", ig="utilizable")
    assert incluir == set()
    assert incluir is not None


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
