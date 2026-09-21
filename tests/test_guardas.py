"""Las guardas tienen que fallar. Estas pruebas verifican que fallan.

Una guarda que no se prueba es un comentario con sintaxis de codigo. Cada caso
de abajo reproduce una trampa concreta, verificada en datos reales.

    python -m pytest tests/test_guardas.py -q
    python tests/test_guardas.py          (sin pytest, corre igual)
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pacs.guardas import (  # noqa: E402
    Cifra,
    MixDePrograma,
    Senal,
    ViolacionDeGuarda,
    WalletShare,
    acto_de_habla,
    intensidad_con_techo,
    porcentaje,
    verificar_entradas_de_inferencia,
    verificar_uso_de_tract,
)


# ── porcentaje ────────────────────────────────────────────────────────────────

def test_porcentaje_siempre_trae_denominador():
    assert porcentaje(3, 14) == "21.4% (3/14)"
    assert porcentaje(0, 29) == "0.0% (0/29)"


def test_porcentaje_sin_datos_no_inventa_cero():
    assert porcentaje(0, 0) == "[sin dato: 0/0]"
    assert porcentaje(None, 10) == "[sin dato]"
    assert porcentaje(5, None) == "[sin dato]"


def test_porcentaje_detecta_grano_mezclado():
    """Una seccion suma 29 y otra dice 728: dos universos en un solo libro."""
    try:
        porcentaje(728, 29)
    except ViolacionDeGuarda as exc:
        assert "grano" in str(exc)
    else:
        raise AssertionError("no fallo con numerador mayor que denominador")


# ── Senal: ausente es null, nunca False ───────────────────────────────────────

def test_senal_ausente_no_es_negativa():
    """El caso ig_is_private: 0 positivos y 5.620 negativos en 5.620 filas."""
    s = Senal.falta("perfil privado: no se pudieron leer los posts")
    assert s.disponible is False
    assert s.es_positiva() is False
    assert s.es_negativa() is False, (
        "una señal ausente NO es negativa. Esto es lo que convirtio 1.075 "
        "perfiles sin datos en 1.075 perfiles que 'no hablaban español'."
    )


def test_senal_medida_falsa_si_es_negativa():
    s = Senal.medida(False)
    assert s.es_negativa() is True
    assert s.es_positiva() is False


def test_senal_no_se_puede_usar_en_un_if():
    """`if senal:` trata lo ausente como falso. Se bloquea en __bool__."""
    s = Senal.falta("handle no verificado")
    try:
        bool(s)
    except ViolacionDeGuarda as exc:
        assert "es_positiva" in str(exc)
    else:
        raise AssertionError("Senal se dejo evaluar como booleano")


def test_senal_ausente_exige_motivo():
    try:
        Senal(valor=None, disponible=False)
    except ViolacionDeGuarda as exc:
        assert "motivo" in str(exc)
    else:
        raise AssertionError("acepto una señal ausente sin motivo")


def test_senal_no_puede_estar_disponible_y_vacia():
    try:
        Senal(valor=None, disponible=True)
    except ViolacionDeGuarda:
        pass
    else:
        raise AssertionError("acepto disponible=True con valor None")


# ── MixDePrograma ─────────────────────────────────────────────────────────────

def test_mix_insuficiente_no_activa_nada():
    """El perfil de prueba: 3 de 14 unidades del lado comprador identificadas."""
    mix = MixDePrograma(
        ops_con_tipo=3, ops_total=14,
        buyside_con_tipo=3, buyside_total=14,
        conteos={"Conventional": 3},
    )
    assert mix.utilizable is False
    assert mix.etiqueta_insuficiencia == "[insuficiente: 3 de 14]"
    assert mix.pct("FHA") == "[insuficiente: 3 de 14]"
    assert mix.puede_descartar_por_cero_fha() is False, (
        "con 3 de 14 identificadas, cero FHA no significa nada"
    )


def test_mix_suficiente_si_activa():
    """El caso verificado: cero FHA en 29 operaciones saca del ICP."""
    mix = MixDePrograma(
        ops_con_tipo=29, ops_total=29,
        buyside_con_tipo=29, buyside_total=29,
        conteos={"Conventional": 26, "VA": 3},
    )
    assert mix.utilizable is True
    assert mix.pct("FHA") == "0.0% (0/29)"
    assert mix.puede_descartar_por_cero_fha() is True


def test_mix_falla_si_buyside_poco_identificado():
    """20 ops con tipo pero solo 20% del buyside identificado: no alcanza."""
    mix = MixDePrograma(
        ops_con_tipo=20, ops_total=100,
        buyside_con_tipo=10, buyside_total=100,
        conteos={"FHA": 5, "Conventional": 15},
    )
    assert mix.utilizable is False


# ── WalletShare ───────────────────────────────────────────────────────────────

def test_wallet_share_listside_no_es_interpretable():
    ws = WalletShare(
        lender="Rocket Mortgage", share=0.42, base="unidades",
        ops_buyside_identificadas=2, ops_buyside_total=6,
        es_libro_buyside=False,
    )
    assert ws.interpretable is False
    assert "NO INTERPRETABLE" in ws.lectura()
    assert "listside" in ws.lectura()


def test_wallet_share_exige_declarar_la_base():
    """33/33/33 por unidades contra 40,6/35,3/24,0 por volumen, mismo perfil."""
    try:
        WalletShare(
            lender="X", share=0.33, base="porcentaje",  # type: ignore[arg-type]
            ops_buyside_identificadas=3, ops_buyside_total=3,
            es_libro_buyside=True,
        )
    except ViolacionDeGuarda as exc:
        assert "base" in str(exc)
    else:
        raise AssertionError("acepto un wallet share sin base declarada")


def test_wallet_share_rechaza_porcentaje_sin_normalizar():
    try:
        WalletShare(
            lender="X", share=40.6, base="volumen",
            ops_buyside_identificadas=3, ops_buyside_total=3,
            es_libro_buyside=True,
        )
    except ViolacionDeGuarda as exc:
        assert "fuera de" in str(exc)
    else:
        raise AssertionError("acepto share=40.6")


def test_wallet_share_lecturas_por_tramo():
    def hacer(share):
        return WalletShare(
            lender="Guild", share=share, base="unidades",
            ops_buyside_identificadas=19, ops_buyside_total=19,
            es_libro_buyside=True,
        ).lectura()

    assert "LENDER CAUTIVO" in hacer(0.70)
    assert "DOMINANTE PERO NO EXCLUSIVA" in hacer(0.45)
    assert "FRAGMENTADO" in hacer(0.24)
    # y siempre con la cobertura del denominador
    assert "(19/19)" in hacer(0.24)


# ── Cifra ─────────────────────────────────────────────────────────────────────

def test_cifra_exige_fuente():
    try:
        Cifra(valor=22, fuente="", fecha=dt.date(2026, 9, 21), medicion="estimada")
    except ViolacionDeGuarda as exc:
        assert "fuente" in str(exc)
    else:
        raise AssertionError("acepto una cifra sin fuente")


def test_cifra_exige_medida_o_estimada():
    try:
        Cifra(valor=22, fuente="hoja Scoring estados",
              fecha=dt.date(2026, 9, 21), medicion="quizas")  # type: ignore[arg-type]
    except ViolacionDeGuarda as exc:
        assert "medida o estimada" in str(exc)
    else:
        raise AssertionError("acepto una medicion desconocida")


def test_cifra_se_imprime_con_procedencia():
    c = Cifra(valor="22%", fuente="hoja Scoring estados",
              fecha=dt.date(2026, 9, 21), medicion="estimada",
              ventana="trailing 14m")
    texto = str(c)
    assert "22%" in texto
    assert "Scoring estados" in texto
    assert "2026-09-21" in texto
    assert "estimada" in texto
    assert "trailing 14m" in texto


# ── Techo de intensidad ───────────────────────────────────────────────────────

def test_e3_nunca_pasa_de_1():
    """J-Q05 por caida invernal del estado: techo 1 y no se sube."""
    intensidad, nota = intensidad_con_techo(3, "E3")
    assert intensidad == 1
    assert nota is not None and "E3" in nota


def test_e2_nunca_pasa_de_2():
    assert intensidad_con_techo(3, "E2")[0] == 2


def test_e0_llega_a_3():
    assert intensidad_con_techo(3, "E0") == (3, None)


def test_e1_llega_a_3_solo_con_excepcion_escrita():
    assert intensidad_con_techo(3, "E1")[0] == 2
    intensidad, nota = intensidad_con_techo(
        3, "E1", excepcion_e1_declarada="serie mensual de cierres de MMI"
    )
    assert intensidad == 3
    assert "serie mensual" in nota


def test_acto_de_habla_solo_afirma_con_e0_y_3():
    assert acto_de_habla(3, "E0") == "AFIRMA"
    assert acto_de_habla(3, "E1") == "PREGUNTA"
    assert acto_de_habla(2, "E0") == "PREGUNTA"
    assert acto_de_habla(1, "E3") == "PREGUNTA"


# ── Inferencia prohibida ──────────────────────────────────────────────────────

def test_no_se_infiere_nicho_desde_apellido():
    try:
        verificar_entradas_de_inferencia({"last_name", "state"}, "P-Q01")
    except ViolacionDeGuarda as exc:
        assert "ECOA" in str(exc)
    else:
        raise AssertionError("dejo inferir un qualifier desde el apellido")


def test_senales_transaccionales_si_pasan():
    verificar_entradas_de_inferencia(
        {"mix_fha", "banda_precio", "zcta", "lmi_tract", "idioma_caption"},
        "P-Q01",
    )


# ── Uso de variables de tract ─────────────────────────────────────────────────

def test_tract_no_clasifica_personas():
    try:
        verificar_uso_de_tract("clasificar_persona")
    except ViolacionDeGuarda as exc:
        assert "donde opera" in str(exc)
    else:
        raise AssertionError("dejo usar un tract para clasificar a una persona")


def test_tract_para_feature_relativa_si():
    verificar_uso_de_tract("feature_relativa")
    verificar_uso_de_tract("describir_mercado")


# ── Corrida sin pytest ────────────────────────────────────────────────────────

def _main() -> int:
    pruebas = [
        (n, o) for n, o in sorted(globals().items())
        if n.startswith("test_") and callable(o)
    ]
    fallos = []
    for nombre, fn in pruebas:
        try:
            fn()
            print("  ok   %s" % nombre)
        except Exception as exc:  # noqa: BLE001
            fallos.append((nombre, exc))
            print("  FALLA %s -- %s" % (nombre, exc))
    print("")
    print("%d pruebas, %d fallas" % (len(pruebas), len(fallos)))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(_main())
