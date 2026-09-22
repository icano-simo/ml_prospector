"""El protocolo de captura y las trampas verificadas de Model Match.

Sin red y sin base: son reglas puras sobre texto.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from captura.protocolo import (  # noqa: E402
    ProtocoloInvalido,
    armar_captura,
    condados_del_overview,
    etiquetar_por_posicion,
)
from captura.trampas import (  # noqa: E402
    MixConforming,
    TrampaDetectada,
    WalletShareCapturado,
    anualizado_buyside,
    es_de_la_casa,
    originadores_con_empresa,
    verificar_no_pisa_el_lote,
    verificar_no_reconciliado,
    verificar_volumenes_distintos,
)

# ── El caso de prueba: Armando Ochoa, eXp Realty of California ──────────────
#
# Condados: Solano 5, Contra Costa 3, Alameda 1. Suman 9, igual a Buyer Units.

OVERVIEW = """\
Armando Ochoa
eXp Realty of California
San Ramon, CA

Counties
Solano County\t5
Contra Costa County\t3
Alameda County\t1
"""

VOLUMENES = {
    "California": 578.7,
    "Solano": 6.0,
    "Contra Costa": 17.2,
    "Alameda": 20.2,
}


# ══ EL ORDEN ES LA ETIQUETA ══════════════════════════════════════════════════

def test_los_condados_salen_en_el_orden_de_la_tabla():
    """El orden es dato, no presentacion: es lo que etiqueta cada bloque."""
    filas = condados_del_overview(OVERVIEW)
    assert [n for n, _ in filas] == ["Solano", "Contra Costa", "Alameda"]
    assert [u for _, u in filas] == [5, 3, 1]


def test_las_unidades_de_los_condados_suman_los_buyer_units():
    filas = condados_del_overview(OVERVIEW)
    assert sum(u for _, u in filas) == 9


def test_el_primer_bloque_es_el_estado_y_el_resto_los_condados():
    """Resuelve el problema del desplegable: Set Location no viaja en el texto."""
    bloques = etiquetar_por_posicion(
        ["ms estado", "ms solano", "ms contra costa", "ms alameda"],
        ["Solano", "Contra Costa", "Alameda"],
    )
    assert bloques[0].nivel == "estado" and bloques[0].etiqueta is None
    assert [b.etiqueta for b in bloques[1:]] == ["Solano", "Contra Costa",
                                                 "Alameda"]
    assert all(b.nivel == "condado" for b in bloques[1:])


# ══ LA VALIDACION QUE NO SE PUEDE ARREGLAR DESPUES ═══════════════════════════

def test_si_faltan_bloques_NO_se_guarda_nada():
    """Etiquetar mal un condado contamina la biblioteca y es invisible.

    Un volumen de Alameda guardado como Solano no se ve raro en ninguna
    consulta: existe, tiene formato de dolares y es del orden correcto.
    """
    try:
        etiquetar_por_posicion(["estado", "uno", "dos"],
                               ["Solano", "Contra Costa", "Alameda"])
    except ProtocoloInvalido as exc:
        assert "Se esperaban 4" in str(exc)
        assert "llegaron 3" in str(exc)
        assert "Solano, Contra Costa, Alameda" in str(exc)
    else:
        raise AssertionError("tiene que fallar antes de tocar nada")


def test_si_sobran_bloques_tampoco():
    try:
        etiquetar_por_posicion(["e", "1", "2", "3", "4"], ["A", "B", "C"])
    except ProtocoloInvalido:
        pass
    else:
        raise AssertionError("un bloque de mas tambien desalinea todo")


def test_la_captura_completa_valida_y_etiqueta():
    cap = armar_captura(
        overview=OVERVIEW,
        market_signals=["ms ca", "ms solano", "ms cc", "ms alameda"],
        originators="orig", lenders="lend",
        realtor="Armando Ochoa", estado="CA",
        mmi_agent_id="MMI-9001",
    )
    assert cap.condados == ["Solano", "Contra Costa", "Alameda"]
    assert len(cap.market_signals) == 4
    assert not cap.advertencias


def test_sin_originators_se_advierte_porque_se_pierde_la_exclusion():
    cap = armar_captura(overview=OVERVIEW,
                        market_signals=["a", "b", "c", "d"],
                        mmi_agent_id="MMI-9001")
    assert any("Everett" in a for a in cap.advertencias)


def test_sin_tabla_de_condados_se_advierte_lo_de_View_Counties():
    cap = armar_captura(overview="Armando Ochoa\neXp Realty",
                        market_signals=["solo el estado"],
                        mmi_agent_id="MMI-9001")
    assert cap.condados == []
    assert any("View Counties" in a for a in cap.advertencias)


# ══ LA LLAVE ═════════════════════════════════════════════════════════════════

def test_sin_llave_no_se_arma_la_captura():
    """La restriccion de la base lo impide igual; esto lo dice ANTES y mejor.

    Se descubrio al primer guardado real: `captura_perfil_trae_llave` exigia
    licencia, que un perfil de Model Match no trae. La restriccion tenia razon
    en el espiritu y no en la lista de llaves aceptadas.
    """
    try:
        armar_captura(overview=OVERVIEW,
                      market_signals=["a", "b", "c", "d"])
    except ProtocoloInvalido as exc:
        assert "MMI Agent ID" in str(exc)
        assert "El nombre no es llave" in str(exc)
    else:
        raise AssertionError("sin llave la captura no se puede pegar a nadie")


def test_el_lead_id_de_salesforce_tambien_sirve_de_llave():
    cap = armar_captura(overview=OVERVIEW,
                        market_signals=["a", "b", "c", "d"],
                        sf_lead_id="00Q5f00000ABCDE")
    assert cap.sf_lead_id == "00Q5f00000ABCDE"
    assert cap.mmi_agent_id is None


# ══ EL PARSER PORTADO · calibrado contra el dato real, no reescrito ══════════

MERCADO_SOLANO = """Market Signals
Set Location
Solano County
Market Overview
Total Loan Volume (i) $6.0B
Total Units (i) 18,442
Avg Household Income $168K
Fall Out (i) 35.6%
First-Time Buyers 26.4%
Fair (580-669) 13.9%
Jumbo 4,120 loans 5.1%
Loan Type Distribution
Conventional 71.2%
FHA 16.0%
Transaction Type Distribution
Purchase 74.0%
Lender Type Distribution
Brokered 18.2%
Rolling Monthly Performance
Total Loan Volume $578.70B
"""


def test_el_volumen_sale_de_Market_Overview_no_del_rodante():
    """TRAMPA 1, sobre texto que trae LOS DOS numeros.

    El rodante dice $578,70B para las cuatro geografias. El parser tiene que
    quedarse con el $6,0B de Market Overview.
    """
    from captura.parser_mm import parsear_mercado

    m = parsear_mercado(MERCADO_SOLANO)
    assert m["total_volume"] == 6.0e9, m["total_volume"]
    assert m["total_volume"] != 578.7e9


def test_los_numeros_de_Solano_coinciden_con_el_caso_de_prueba():
    from captura.parser_mm import parsear_mercado

    m = parsear_mercado(MERCADO_SOLANO)
    assert m["avg_income"] == 168000.0
    assert m["mkt_fha"] == 16.0
    assert m["fallout"] == 35.6
    assert m["credit_fair"] == 13.9
    assert m["ftb"] == 26.4
    assert m["jumbo"] == 5.1, "el jumbo va con SU denominador, no el del mercado"


def test_mval_entiende_las_tres_escalas_y_el_separador_de_millar():
    from captura.parser_mm import mval

    assert mval("$578.7B") == 578.7e9
    assert mval("$613.2K") == 613200
    assert mval("$229K") == 229000
    assert mval("1,096,337") == 1096337
    assert mval(None) is None
    assert mval("sin numero") is None


TAB_ORIGINADORES = """Originators this agent has worked with
Chris Ruiz
NMLS: 2129
Everett Financial Inc $4.1M 2 $2.05M 50.0%
Other Person
NMLS: 3274
Guild Mortgage $2.0M 1 $2.0M 25.0%
Lenders this agent has worked with
"""


def test_la_pestana_originators_saca_nombre_empresa_y_nmls():
    """TRAMPA 5. Sin la empresa no se detecta que Everett es la casa."""
    from captura.parser_mm import _tabla_originadores

    ors = _tabla_originadores(TAB_ORIGINADORES)
    assert len(ors) == 2
    assert ors[0]["nombre"] == "Chris Ruiz"
    assert ors[0]["nmls"] == "2129"
    assert ors[0]["empresa"] == "Everett Financial Inc"
    assert es_de_la_casa(ors[0]) and not es_de_la_casa(ors[1])


def test_una_inversion_de_nombre_y_empresa_se_detecta():
    """El fallo mas peligroso del parser de originadores.

    Los dos campos son texto y los dos se llenan, asi que una inversion no
    rompe nada -- salvo la exclusion: `es_de_la_casa` mira la EMPRESA, y si
    ahi quedo el nombre de la persona, un originador de Everett pasa el filtro.
    """
    from captura.parser_mm import detectar_inversion

    bien = [{"nombre": "Chris Ruiz", "empresa": "Everett Financial Inc"}]
    assert detectar_inversion(bien) == []

    al_reves = [{"nombre": "Everett Financial Inc", "empresa": "Chris Ruiz"}]
    avisos = detectar_inversion(al_reves)
    assert avisos and "parece una empresa" in avisos[0]


# ══ TRAMPA 1 · el grafico rodante ════════════════════════════════════════════

def test_cuatro_geografias_tienen_que_dar_cuatro_volumenes():
    """La prueba obligatoria del brief."""
    verificar_volumenes_distintos(list(VOLUMENES.values()),
                                  list(VOLUMENES))


def test_si_las_cuatro_dan_lo_mismo_es_el_grafico_rodante():
    """578,70B en las cuatro capturas: el rodante no respeta el filtro."""
    try:
        verificar_volumenes_distintos([578.7, 578.7, 578.7, 578.7],
                                      ["CA", "Solano", "CC", "Alameda"])
    except TrampaDetectada as exc:
        assert "Rolling Monthly Performance" in str(exc)
        assert "Market Overview" in str(exc)
    else:
        raise AssertionError("cuatro volumenes iguales son el bug")


# ══ TRAMPA 2 · conforming/jumbo tiene denominador propio ═════════════════════

def test_el_jumbo_se_reporta_sobre_SU_denominador():
    mix = MixConforming(conforming=386.4, jumbo=226.8,
                        denominador_propio=613.2,
                        unidades_del_mercado=1096337)
    texto = mix.porcentaje_jumbo()
    assert "37.0%" in texto or "37,0%" in texto
    assert "613" in texto, "el denominador propio va en la frase"


def test_cruzar_los_denominadores_se_detecta():
    mix = MixConforming(conforming=1.0, jumbo=1.0,
                        denominador_propio=1096337, unidades_del_mercado=613.2)
    try:
        mix.verificar()
    except TrampaDetectada:
        pass
    else:
        raise AssertionError("el denominador propio no puede superar al mercado")


# ══ TRAMPA 3 · dos wallet shares ═════════════════════════════════════════════

def test_el_wallet_share_no_existe_sin_su_base():
    WalletShareCapturado("unidades", "Overview", {"a": 50, "b": 25, "c": 25})
    WalletShareCapturado("volumen", "Originators", {"a": 30.7, "b": 35.3,
                                                    "c": 34.0})
    try:
        WalletShareCapturado("el que sea", "x", {})
    except TrampaDetectada as exc:
        assert "unidades" in str(exc) and "volumen" in str(exc)
    else:
        raise AssertionError("una base inventada tiene que fallar")


def test_los_dos_repartos_conviven_sin_reconciliarse():
    por_unidades = WalletShareCapturado("unidades", "Overview",
                                        {"a": 50, "b": 25, "c": 25})
    por_volumen = WalletShareCapturado("volumen", "Originators",
                                       {"a": 30.7, "b": 35.3, "c": 34.0})
    assert por_unidades.reparto != por_volumen.reparto
    assert por_unidades.base != por_volumen.base


# ══ TRAMPA 4 · los conteos de cabecera no coinciden ══════════════════════════

def test_los_cuatro_conteos_se_guardan_por_separado():
    verificar_no_reconciliado({
        "side_focus_buy": 3, "side_focus_sell": 0,
        "buyer_units": 9, "listing_sold": 3, "suma_condados": 9,
    })


def test_faltar_uno_se_detecta_en_vez_de_reconciliar():
    try:
        verificar_no_reconciliado({"buyer_units": 9})
    except TrampaDetectada as exc:
        assert "side_focus_buy" in str(exc)
    else:
        raise AssertionError("no se completa el que falta: se reporta")


# ══ TRAMPA 5 · la empresa va en la linea ANTERIOR ════════════════════════════

TEXTO_ORIGINADORES = """\
Everett Financial Inc
NMLS #2129
Chris Ruiz
2 units

Everett Financial Inc
NMLS #2129
Grace Davis
1 unit

Guild Mortgage
NMLS #3274
Other Person
1 unit
"""


def test_la_empresa_se_lee_hacia_atras_desde_el_nmls():
    ors = originadores_con_empresa(TEXTO_ORIGINADORES)
    assert len(ors) == 3
    assert ors[0]["empresa"] == "Everett Financial Inc"
    assert ors[0]["nombre"] == "Chris Ruiz"
    assert ors[0]["nmls"] == "2129"


def test_sin_la_empresa_no_hay_exclusion():
    """Es lo que hace que Everett Financial se detecte como Supreme Lending."""
    ors = originadores_con_empresa(TEXTO_ORIGINADORES)
    de_la_casa = [o for o in ors if es_de_la_casa(o)]
    assert [o["nombre"] for o in de_la_casa] == ["Chris Ruiz", "Grace Davis"]


def test_el_nmls_2129_alcanza_aunque_la_empresa_no_diga_supreme():
    assert es_de_la_casa({"nmls": "2129", "empresa": "Otra Cosa SA"})
    assert es_de_la_casa({"nmls": "9999", "empresa": "Supreme Lending"})
    assert not es_de_la_casa({"nmls": "3274", "empresa": "Guild Mortgage"})


# ══ TRAMPA 6 · produccion solo buyside ═══════════════════════════════════════

def test_el_anualizado_es_solo_del_lado_comprador():
    """9 unidades buyside en 14 meses."""
    assert abs(anualizado_buyside(9, 14) - 7.714) < 0.01


def test_no_se_suma_el_lado_vendedor():
    solo_buy = anualizado_buyside(9, 14)
    con_sell = anualizado_buyside(9 + 3, 14)
    assert solo_buy < con_sell, (
        "si fueran iguales el lado vendedor estaria entrando"
    )


def test_model_match_no_pisa_el_unidades_ano_del_lote():
    verificar_no_pisa_el_lote("mm_buyside_anualizado")
    try:
        verificar_no_pisa_el_lote("unidades_ano")
    except TrampaDetectada as exc:
        assert "del lote" in str(exc)
    else:
        raise AssertionError("son dos mediciones distintas y las dos se guardan")


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
