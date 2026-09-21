"""Pruebas del cliente de HMDA, sin red.

Los numeros del fixture son los MEDIDOS el 2026-09-21 contra el API real para
Harris County TX (48201), año 2023, sin filtro de universo.

    python tests/test_hmda.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hmda.cliente import (  # noqa: E402
    FILTRO_COMPRA_ESTANDAR,
    Fallout,
    MixDeMercado,
)

# Medido contra el API el 2026-09-21. Harris County TX, 2023, sin filtros.
HARRIS_2023 = {
    "1": 55607,   # originada
    "2": 3456,    # aprobada no aceptada
    "3": 24652,   # negada
    "4": 18692,   # retirada
    "5": 5895,    # cerrada por incompleta
    "6": 17266,   # COMPRADA en el secundario -- no es solicitud
    "7": 119,     # preaprobacion negada
    "8": 176,     # preaprobacion aprobada no aceptada
}


def _fallout(filtro=None):
    return Fallout(
        geografia="48201", nivel="condado", anio=2023,
        filtro=dict(filtro or {}), por_accion=dict(HARRIS_2023),
    )


def test_las_compradas_no_entran_al_denominador():
    """Accion 6 son 17.266 de 125.863 registros: 13,7% del archivo."""
    f = _fallout()
    assert f.compradas_excluidas == 17266
    assert f.denominador == 55607 + 52990
    assert f.denominador == 108597
    assert f.denominador != sum(HARRIS_2023.values()), (
        "el denominador no puede ser el archivo entero: incluye las compradas"
    )
    assert sum(HARRIS_2023.values()) - f.denominador == 17266


def test_fallout_medido():
    f = _fallout()
    assert f.originadas == 55607
    assert f.caidas == 52990
    assert abs(f.pct - 0.48796) < 1e-4


def test_si_se_incluyeran_las_compradas_el_fallout_baja():
    """Cuantificar el error, no solo evitarlo."""
    f = _fallout()
    correcto = f.caidas / f.denominador
    con_error = f.caidas / (f.denominador + f.compradas_excluidas)
    assert correcto > con_error
    assert abs(correcto - con_error) > 0.06, (
        "meter las compradas en el denominador baja el fallout mas de 6 puntos"
    )


def test_el_str_siempre_declara_el_universo():
    sin_filtro = str(_fallout())
    assert "SIN FILTRO DE UNIVERSO" in sin_filtro
    assert "(52990/108597)" in sin_filtro
    assert "17266 compradas excluidas" in sin_filtro

    con_filtro = str(_fallout(FILTRO_COMPRA_ESTANDAR))
    assert "SIN FILTRO" not in con_filtro
    assert "loan_purposes=1" in con_filtro
    assert "lien_statuses=1" in con_filtro


def test_denominador_cero_no_inventa_un_porcentaje():
    f = Fallout(geografia="99999", nivel="condado", anio=2023,
                filtro={}, por_accion={})
    assert f.pct is None
    assert "[sin dato: denominador 0]" in str(f)


def test_desglose_trae_las_etiquetas():
    d = _fallout().desglose()
    assert d["6"] == (17266, "comprada en el secundario (NO es solicitud)")
    assert d["3"][1] == "negada"


def test_mix_siempre_con_denominador():
    m = MixDeMercado(
        geografia="48201", nivel="condado", anio=2023,
        filtro=dict(FILTRO_COMPRA_ESTANDAR),
        por_tipo={"1": 7000, "2": 2000, "3": 800, "4": 200},
    )
    assert m.total == 10000
    assert m.pct("2") == "20.0% (2000/10000)"
    assert abs(m.fha_pct - 0.20) < 1e-9
    assert "FHA 20.0% (2000/10000)" in str(m)
    assert "loan_purposes=1" in str(m)


def test_mix_vacio_no_devuelve_cero():
    m = MixDeMercado(geografia="x", nivel="condado", anio=2023,
                     filtro={}, por_tipo={})
    assert m.fha_pct is None
    assert m.pct("2") == "[sin dato: 0/0]"


def _main() -> int:
    pruebas = [(n, o) for n, o in sorted(globals().items())
               if n.startswith("test_") and callable(o)]
    fallos = []
    for nombre, fn in pruebas:
        try:
            fn()
            print("  ok   %s" % nombre)
        except Exception as exc:  # noqa: BLE001
            fallos.append((nombre, exc))
            print("  FALLA %s -- %r" % (nombre, exc))
    print("")
    print("%d pruebas, %d fallas" % (len(pruebas), len(fallos)))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(_main())
