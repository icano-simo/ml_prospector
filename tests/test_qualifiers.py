"""El banco de qualifiers y la narrativa de apertura."""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.lectura import PALABRAS_PROHIBIDAS, verificar_vocabulario  # noqa
from motor.narrativa import narrativa  # noqa: E402
from motor.qualifiers import CATALOGO, enunciado, ficha  # noqa: E402
from motor.reglas import REGLAS  # noqa: E402

#: Los cinco que cubren el 96,5% de los que tienen dolor primario.
PRINCIPALES = ("P-Q06", "P-Q01", "P-Q09", "P-Q11", "P-Q14")


# ══ EL BANCO ═════════════════════════════════════════════════════════════════

def test_los_sesenta_qualifiers_estan():
    assert len(CATALOGO) == 60


def test_un_qualifier_solo_no_le_dice_nada_a_nadie():
    """`P-Q14` sin su enunciado es un código. Con él, es una hipótesis."""
    assert enunciado("P-Q14") == (
        "Sus clientes chocan con la barrera de idioma en el proceso hipotecario")


def test_el_angulo_y_la_municion_son_literales_de_la_matriz():
    """Sin esto el BD sabe qué le duele y no sabe qué ofrecerle."""
    f = ficha("P-Q14")
    assert f["angulo_que_activa"].startswith(
        'A18 "Tu comunidad en su idioma, de punta a punta"')
    assert "LO bilingue de la casa" in f["municion_PR_GC"]


def test_los_cinco_principales_tienen_ficha_completa():
    for q in PRINCIPALES:
        f = ficha(q)
        assert f, q
        for campo in ("enunciado", "angulo_que_activa", "municion_PR_GC",
                      "escala_de_intensidad", "evidencia_minima"):
            assert f.get(campo), "%s sin %s" % (q, campo)


def test_todas_las_reglas_del_motor_tienen_su_ficha_en_el_banco():
    """Un qualifier que el motor activa y el banco no cubre sale en pantalla
    como un código pelado, que es justo lo que se está arreglando."""
    del_motor = {r.qualifier for r in REGLAS}
    faltan = sorted(q for q in del_motor if q not in CATALOGO)
    assert not faltan, "el motor activa %s y el banco no los tiene" % faltan


def test_un_qualifier_desconocido_devuelve_vacio_y_no_revienta():
    """Que el banco no lo cubra es un dato, y la pantalla tiene que poder
    decirlo en vez de romperse."""
    assert ficha("X-Q99") == {}
    assert enunciado("X-Q99") is None


# ══ EL VOCABULARIO · lo mío se corrige, lo literal se declara ════════════════

def test_ningun_texto_de_regla_usa_vocabulario_prohibido():
    """Los textos de las reglas son MÍOS y son lo que el BD lee en la ficha."""
    for r in REGLAS:
        verificar_vocabulario(r.texto)


def test_el_unico_enunciado_de_la_matriz_que_choca_esta_declarado():
    """`P-Q07` dice `enganche`. Es literal de la matriz y NO se reescribe: se
    declara, para que nadie lo corrija por su cuenta creyendo que es un
    descuido nuestro."""
    chocan = sorted(
        q for q, f in CATALOGO.items()
        if any(m in (f.get("enunciado") or "").lower()
               for m in PALABRAS_PROHIBIDAS))
    assert chocan == ["P-Q07"], chocan


# ══ LA NARRATIVA ═════════════════════════════════════════════════════════════

REALTOR = {"nombre_completo": "ARMANDO OCHOA", "estado": "CA",
           "brokerage": "eXp Realty of California Inc", "unidades_ano": 16.0}


def test_la_narrativa_dice_quien_es_antes_de_cualquier_contraste():
    t = narrativa(REALTOR, estado_nombre="California",
                  perfil_mm={"sf_buy": 3, "sf_sell": 0},
                  mercado={"fallout": 35.6, "mkt_fha": 16.0}, donde="Solano",
                  cobertura={"activos": 2})
    assert t.startswith("Armando Ochoa trabaja en eXp Realty")
    assert "16 operaciones" in t
    assert "lado comprador" in t
    assert "Solano" in t
    assert "Podemos originarle" in t


def test_el_nombre_en_mayusculas_no_grita():
    t = narrativa(REALTOR, estado_nombre="California")
    assert "ARMANDO OCHOA" not in t


def test_sin_saber_de_licencias_dice_que_no_sabe_y_no_que_no_tenemos():
    """Son cosas distintas y sólo una es razón para no escribirle."""
    t = narrativa(REALTOR, estado_nombre="California", cobertura={})
    assert "No sabemos si tenemos licencia" in t
    t2 = narrativa(REALTOR, estado_nombre="California",
                   cobertura={"activos": 0})
    assert "No tenemos licencia" in t2


def test_sin_condado_la_narrativa_lo_dice_en_vez_de_callarlo():
    t = narrativa(REALTOR, estado_nombre="California", donde=None)
    assert "no hay contra qué compararlo" in t


def test_la_narrativa_pasa_el_vocabulario():
    for cov in ({}, {"activos": 0}, {"activos": 3}):
        verificar_vocabulario(narrativa(REALTOR, estado_nombre="California",
                                        cobertura=cov))


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
