"""Los contrastes y la promocion a la biblioteca de mercados.

Sin red y sin base: son funciones puras sobre dicts.

Los numeros son los REALES de la captura de Armando Ochoa del 2026-09-22.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))

from motor.contrastes import (  # noqa: E402
    MIN_COBERTURA_PCT,
    MIN_OPERACIONES_IDENTIFICADAS,
    mix_de_programa,
)

#: El mix del agente, con su denominador. 2 FHA + 1 HE = 3 identificadas
#: sobre 9 del lado comprador.
MIX_ARMANDO = {
    "filas": [{"tipo": "FHA", "unidades": 2, "share": 66.7},
              {"tipo": "HE (Home Equity)", "unidades": 1, "share": 33.3}],
    "unidades_identificadas": 3.0,
    "buyer_units": 9.0,
    "cobertura": 33.3,
}

#: Los cuatro mercados, tal como salen de pacs.mercados.
MERCADOS = [
    {"nivel": "estado", "estado": "CA", "etiqueta": "CA",
     "metricas": {"mkt_fha": 12.0, "total_volume": 578.7e9}},
    {"nivel": "condado", "estado": "CA", "etiqueta": "Solano",
     "metricas": {"mkt_fha": 16.0, "total_volume": 6.0e9}},
    {"nivel": "condado", "estado": "CA", "etiqueta": "Contra Costa",
     "metricas": {"mkt_fha": 9.4, "total_volume": 17.2e9}},
    {"nivel": "condado", "estado": "CA", "etiqueta": "Alameda",
     "metricas": {"mkt_fha": 3.2, "total_volume": 20.2e9}},
]


# ══ EL MISMO AGENTE, CUATRO LECTURAS ═════════════════════════════════════════

def test_un_agente_da_CUATRO_lecturas_distintas():
    """Es la prueba que decide si el modelo sirve. `FHA 66,7%` solo no dice
    nada; contra el mercado donde opera, dice algo distinto en cada uno."""
    cs = mix_de_programa(MIX_ARMANDO, MERCADOS, tipo="FHA")
    veces = {c.geografia: c.veces for c in cs}
    assert veces["Solano"] == 4.2
    assert veces["Alameda"] == 20.8
    assert veces["Contra Costa"] == 7.1
    assert veces["CA"] == 5.6
    assert len(set(veces.values())) == 4, (
        "cuatro geografias tienen que dar cuatro lecturas: si coinciden, el "
        "contraste se esta calculando contra una constante"
    )


def test_el_valor_del_agente_es_el_mismo_en_los_cuatro():
    """Lo que cambia es el mercado, no el agente. Si cambiara el del agente,
    se estaria leyendo de otro sitio en cada bloque."""
    cs = mix_de_programa(MIX_ARMANDO, MERCADOS, tipo="FHA")
    assert {c.valor_agente for c in cs} == {66.7}


# ══ LA GUARDIA MANDA SOBRE LA LECTURA ════════════════════════════════════════

def test_el_contraste_se_calcula_y_aun_asi_NO_activa():
    """Un 21x con tres operaciones detras es un numero correcto que no
    significa. Devolverlo sin su veredicto seria ofrecerlo para que alguien lo
    cite."""
    cs = mix_de_programa(MIX_ARMANDO, MERCADOS, tipo="FHA")
    alameda = [c for c in cs if c.geografia == "Alameda"][0]
    assert alameda.veces == 20.8, "el ratio existe"
    assert alameda.activa is False, "y no puede activar nada"
    assert "hacen falta %d" % MIN_OPERACIONES_IDENTIFICADAS in alameda.motivo
    assert "hace falta %g" % MIN_COBERTURA_PCT in alameda.motivo


def test_la_lectura_lleva_el_NO_ACTIVA_dentro_del_texto():
    """No en un campo aparte que alguien pueda no mirar al copiar la frase."""
    cs = mix_de_programa(MIX_ARMANDO, MERCADOS, tipo="FHA")
    texto = cs[0].leer()
    assert "NO ACTIVA" in texto
    assert "66,7%" in texto and "veces" in texto


def test_con_base_suficiente_SI_activa():
    """La guardia tiene que poder no dispararse; si no, no distingue nada."""
    bueno = {"filas": [{"tipo": "FHA", "unidades": 18, "share": 60.0}],
             "unidades_identificadas": 30.0, "buyer_units": 40.0,
             "cobertura": 75.0}
    cs = mix_de_programa(bueno, MERCADOS, tipo="FHA")
    assert all(c.activa for c in cs)
    assert all(c.motivo == "" for c in cs)
    assert "NO ACTIVA" not in cs[0].leer()


def test_una_sola_guardia_incumplida_ya_bloquea():
    """Suficientes operaciones pero poca cobertura: sigue sin activar."""
    parcial = {"filas": [{"tipo": "FHA", "unidades": 12, "share": 60.0}],
               "unidades_identificadas": 20.0, "buyer_units": 80.0,
               "cobertura": 25.0}
    cs = mix_de_programa(parcial, MERCADOS, tipo="FHA")
    assert not cs[0].activa
    assert "cobertura" in cs[0].motivo
    assert "operaciones con tipo identificado" not in cs[0].motivo


def test_sin_dato_de_un_lado_no_hay_contraste_ni_ratio_inventado():
    sin_mercado = [{"nivel": "condado", "estado": "CA", "etiqueta": "X",
                    "metricas": {}}]
    c = mix_de_programa(MIX_ARMANDO, sin_mercado, tipo="FHA")[0]
    assert c.veces is None
    # Dice CUAL de los dos lados falta. Con cuatro geografias en pantalla,
    # «sin dato de un lado» obliga a ir a buscar cual.
    assert "sin dato del mercado" in c.leer()
    assert not c.activa

    c2 = mix_de_programa({"filas": [], "unidades_identificadas": 30.0,
                          "cobertura": 80.0}, MERCADOS, tipo="FHA")[0]
    assert c2.valor_agente is None
    assert c2.veces is None


def test_un_mercado_con_FHA_cero_no_da_division_por_cero():
    cero = [{"nivel": "condado", "estado": "CA", "etiqueta": "Z",
             "metricas": {"mkt_fha": 0.0}}]
    c = mix_de_programa(MIX_ARMANDO, cero, tipo="FHA")[0]
    assert c.veces is None, "dividir por cero no da infinito, da nada"


# ══ LA PROMOCION A LA BIBLIOTECA ═════════════════════════════════════════════
#
# `pacs.mercados` estuvo en CERO con cuatro bloques ya parseados y 35 metricas
# cada uno. Nada fallaba: el paso que los promovia no existia dentro del
# guardado, y un paso aparte es un paso que alguien tiene que acordarse de
# correr.

def _bloque(etiqueta, nivel, campos=44, estado="CA"):
    return {"estado": estado, "texto_crudo": "x",
            "parseado": {"seccion": "market_signals", "nivel": nivel,
                         "etiqueta_geografica": etiqueta,
                         "metricas": {"campos": campos, "mkt_fha": 16.0}}}


def test_los_bloques_con_metricas_se_promueven_con_su_FIPS():
    from api.rutas import promover_a_mercados

    filas = [_bloque("CA", "estado"), _bloque("Solano", "condado"),
             _bloque("Alameda", "condado")]
    mercados, fallos = promover_a_mercados(filas, "lote-1", "2026-09-22T00:00:00Z")
    assert fallos == []
    assert len(mercados) == 3
    por_nivel = {m["nivel"]: m for m in mercados}
    assert por_nivel["estado"]["condado_fips"] is None, (
        "el bloque del estado no tiene condado, y la tabla no se lo exige")
    fips = sorted(m["condado_fips"] for m in mercados if m["condado_fips"])
    assert fips == ["06001", "06095"], fips


def test_un_condado_que_no_resuelve_es_un_FALLO_DECLARADO():
    """`pacs.mercados` exige FIPS para nivel condado y geo.fips no adivina.
    Sin declararlo, el bloque desaparece de la biblioteca en silencio."""
    from api.rutas import promover_a_mercados

    mercados, fallos = promover_a_mercados(
        [_bloque("Condado Inventado", "condado")], "l", "t")
    assert mercados == []
    assert len(fallos) == 1
    assert "Condado Inventado" in fallos[0]
    assert "NO entra en la biblioteca" in fallos[0]
    assert "44 metricas parseadas" in fallos[0]


def test_un_bloque_SIN_metricas_no_es_un_fallo_de_promocion():
    """Que el parser no sacara nada ya se reporta por su lado. Contarlo dos
    veces hace que los avisos dejen de leerse."""
    from api.rutas import promover_a_mercados

    mercados, fallos = promover_a_mercados(
        [_bloque("Solano", "condado", campos=0)], "l", "t")
    assert mercados == [] and fallos == []


def test_un_condado_sin_estado_no_se_promueve_y_se_declara():
    from api.rutas import promover_a_mercados

    fila = _bloque("Solano", "condado", estado=None)
    mercados, fallos = promover_a_mercados([fila], "l", "t")
    assert mercados == []
    assert "sin estado" in fallos[0]


def test_las_metricas_viajan_enteras_a_la_biblioteca():
    """Un benchmark recortado es peor que ninguno: nadie sabe que falta."""
    from api.rutas import promover_a_mercados

    fila = _bloque("Solano", "condado")
    fila["parseado"]["metricas"]["fallout"] = 35.6
    fila["parseado"]["metricas"]["total_volume"] = 6.0e9
    mercados, _ = promover_a_mercados([fila], "l", "t")
    m = mercados[0]["metricas"]
    assert m["mkt_fha"] == 16.0 and m["fallout"] == 35.6
    assert m["total_volume"] == 6.0e9


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
