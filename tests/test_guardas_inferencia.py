"""La guarda ECOA: lo que atrapa por nombre y lo que atrapa por procedencia.

El caso que da origen a estas pruebas: `R7_identidad_hispana` se calcula desde
el apellido y el nombre de pila, y la guarda lo dejaba pasar entero porque
compara nombres de campo -- y ese campo esta nombrado por lo que dice medir.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from pacs.guardas import (  # noqa: E402
    CAMPOS_DE_PROCEDENCIA_PROHIBIDA,
    ViolacionDeGuarda,
    verificar_entradas_de_inferencia,
)


def _rechaza(campos, qualifier="P-Q99"):
    try:
        verificar_entradas_de_inferencia(set(campos), qualifier)
    except ViolacionDeGuarda as exc:
        return str(exc)
    return None


def test_hispanic_surname_score_no_pasa():
    """El caso de la tarea 5: no esta en la lista exacta y contiene `surname`.

    Antes del cambio la guarda solo comparaba nombres completos, asi que
    `hispanic_surname_score` entraba sin que nada lo mirara.
    """
    msg = _rechaza(["hispanic_surname_score", "ev2_fha_gob"])
    assert msg, "hispanic_surname_score paso la guarda"
    assert "hispanic_surname_score" in msg


def test_los_otros_trozos_tampoco():
    for campo in ("borrower_apellido_norm", "ethnic_match_pct",
                  "flag_etnia_declarada", "score_national_origin"):
        assert _rechaza([campo]), campo


def test_r7_no_se_parece_a_nada_prohibido():
    """Ni la lista exacta ni los trozos lo atrapan: hace falta la procedencia.

    Esta prueba fija POR QUE hace falta el tercer mecanismo. Si alguien un dia
    borra `CAMPOS_DE_PROCEDENCIA_PROHIBIDA` creyendo que los trozos alcanzan,
    esto falla.
    """
    from pacs.guardas import CAMPOS_PROHIBIDOS_PARA_INFERENCIA, TROZOS_PROHIBIDOS
    nombre = "R7_identidad_hispana"
    assert nombre.lower() not in CAMPOS_PROHIBIDOS_PARA_INFERENCIA
    assert not any(t in nombre.lower() for t in TROZOS_PROHIBIDOS)
    # Y aun asi tiene que ser rechazado.
    msg = _rechaza([nombre])
    assert msg, "R7_identidad_hispana paso la guarda"
    assert "apellido" in msg


def test_el_rechazo_de_r7_explica_su_procedencia():
    """No basta con rechazar: hay que decir de donde sale, o nadie lo cree."""
    msg = _rechaza(["R7_identidad_hispana"])
    assert "nombre de pila" in msg
    assert "docs/r7-identidad-hispana.md" in msg


def test_las_señales_transaccionales_pasan():
    """La guarda no puede volverse un no a todo: lo legitimo tiene que pasar."""
    for campos in (["ev2_fha_gob", "unidades_ano"],
                   ["R5_espanol", "ev_caracteres_espanol"],
                   ["mkt_fha", "condado_fips", "ev2_primera_casa"]):
        assert _rechaza(campos) is None, campos


def test_r5_espanol_pasa_y_r7_no():
    """La distincion que importa.

    R5 mide el idioma de lo que la persona PUBLICA -- conducta, y la señal que
    el propio libro de reglas llama legitima. R7 mide de que apellido es. Las
    dos suenan parecido y solo una es inferencia sobre el origen.
    """
    assert _rechaza(["R5_espanol"]) is None
    assert _rechaza(["R7_identidad_hispana"])


def test_el_registro_de_procedencia_trae_su_razon():
    """Un campo listado sin explicacion es un campo que nadie va a poder sacar."""
    assert CAMPOS_DE_PROCEDENCIA_PROHIBIDA
    for campo, razon in CAMPOS_DE_PROCEDENCIA_PROHIBIDA.items():
        assert campo == campo.lower(), campo
        assert len(razon) > 40, campo


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
