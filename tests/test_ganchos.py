"""El enrutado qualifier -> ficha, y el gancho literal del corpus."""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.ganchos import (  # noqa: E402
    CORPUS,
    DERIVADOS,
    MAPA,
    NO_SE_CONVERSA,
    VARIANTES,
    gancho_de,
)
from motor.reglas import REGLAS  # noqa: E402


def test_el_gancho_de_P_Q14_es_literal_de_P_N06():
    g = gancho_de("P-Q14")
    assert g.ficha == "P-N06"
    assert g.texto == (
        "¿Tus clientes te llaman a ti cuando les llega un documento del banco? "
        "Me interesa cuántas horas a la semana estás traduciendo papeles que "
        "no escribiste.")
    assert g.derivado is False
    assert "corpus" in g.fuente


def test_el_mapa_es_el_del_prototipo():
    assert MAPA["P-Q01"] == "P-082"
    assert MAPA["P-Q06"] == "P-074"
    assert MAPA["P-Q07"] == "P-023"
    assert MAPA["P-Q09"] == "P-062"
    assert MAPA["P-Q10"] == "P-091"
    assert MAPA["P-Q11"] == "P-095"
    assert MAPA["P-Q12"] == "P-013"
    assert MAPA["P-Q13"] == "P-N10"
    assert MAPA["P-Q14"] == "P-N06"
    assert MAPA["P-Q17"] == "P-083"
    assert MAPA["P-Q19"] == "P-089"
    assert MAPA["P-Q20"] == "P-086"
    assert MAPA["P-Q21"] == "P-097"


def test_todas_las_fichas_del_mapa_existen_en_el_corpus():
    """Un mapa que apunta a una ficha que no está devuelve None sin decir por
    qué, y el gancho sale genérico sin que nadie sepa que fue por esto."""
    faltan = sorted(f for f in MAPA.values() if f not in CORPUS)
    assert not faltan, faltan
    for variantes in VARIANTES.values():
        for _campo, ficha in variantes:
            assert ficha in CORPUS, ficha


# ══ LAS DOS VARIANTES DE P-Q01 ═══════════════════════════════════════════════

def test_P_Q01_se_abre_distinto_segun_la_señal_que_lo_activo():
    """El mismo dolor -- el lender rechaza el caso de nicho-- no se conversa
    igual con quien declara ITIN que con quien declara cuenta propia."""
    assert gancho_de("P-Q01").ficha == "P-082"
    assert gancho_de("P-Q01", {"ev2_itin": True}).ficha == "P-N01"
    assert gancho_de("P-Q01", {"ev2_self_employed": True}).ficha == "P-081"


def test_el_ITIN_gana_sobre_cuenta_propia_cuando_estan_los_dos():
    """Es el orden declarado en VARIANTES, no un azar del diccionario."""
    g = gancho_de("P-Q01", {"ev2_itin": True, "ev2_self_employed": True})
    assert g.ficha == "P-N01"
    assert VARIANTES["P-Q01"][0][1] == "P-N01"


def test_los_tres_ganchos_de_P_Q01_son_distintos():
    textos = {gancho_de("P-Q01", s).texto for s in
              ({}, {"ev2_itin": True}, {"ev2_self_employed": True})}
    assert len(textos) == 3


def test_la_regla_que_dispara_P_Q01_nombra_las_dos_variantes():
    """La nota de enrutado vive en la regla desde antes: que coincidan con el
    mapa es lo que impide que se separen."""
    r = next(x for x in REGLAS if x.id == "P-Q01-1")
    assert "P-N01" in (r.gancho or "") and "P-081" in (r.gancho or "")
    assert set(r.campos) == {"ev2_itin", "ev2_self_employed"}
    assert [c for c, _f in VARIANTES["P-Q01"]] == ["ev2_itin",
                                                   "ev2_self_employed"]


# ══ LO DERIVADO VA MARCADO ═══════════════════════════════════════════════════

def test_J_Q05_y_J_Q06_salen_MARCADOS_como_derivados():
    """Un gancho inventado que parece calibrado es peor que uno que se declara
    inventado."""
    for q in ("J-Q05", "J-Q06"):
        g = gancho_de(q)
        assert g.derivado is True, q
        assert g.ficha is None
        assert "DERIVADO" in g.fuente
        assert q in g.fuente


def test_los_derivados_son_exactamente_dos():
    """Si aparece un tercero, que se vea en el diff: cada derivado es un hueco
    del corpus que alguien decidió tapar a mano."""
    assert set(DERIVADOS) == {"J-Q05", "J-Q06"}


def test_ninguna_ficha_del_corpus_es_derivada():
    assert not (set(DERIVADOS) & set(MAPA))


# ══ LO QUE NO SE CONVERSA ════════════════════════════════════════════════════

def test_la_compuerta_no_tiene_gancho():
    """J-Q01 es compuerta: decide si se contacta, no de qué se habla."""
    assert "J-Q01" in NO_SE_CONVERSA
    assert gancho_de("J-Q01") is None


def test_un_qualifier_sin_enrutar_devuelve_None_y_no_inventa():
    """Es un dato -- el enrutado no lo cubre-- y la pantalla tiene que poder
    decirlo en vez de mostrar una frase que parezca de la matriz."""
    assert gancho_de("P-Q99") is None


# ══ EL CORPUS ════════════════════════════════════════════════════════════════

def test_el_corpus_sale_de_las_dos_hojas():
    hojas = {c["hoja"] for c in CORPUS.values()}
    assert hojas == {"1 · Dolores", "4 · Nicho latino v2"}
    assert len(CORPUS) >= 110


def test_ningun_gancho_viene_vacio_ni_con_comillas_pegadas():
    for fid, c in CORPUS.items():
        assert c["gancho"], fid
        assert not c["gancho"].startswith(('"', "“")), fid
        assert not c["gancho"].endswith(('"', "”")), fid


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
