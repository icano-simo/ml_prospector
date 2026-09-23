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

# El formato REAL de la tabla de condados, del volcado de Armando del
# 2026-09-22. Siete columnas separadas por tabulador:
#
#   nombre, volumen total, UNIDADES totales, vol comprador, unidades comprador,
#   vol vendedor, unidades vendedor
#
# La version sintetica que use antes era `Solano County\t5`, y el patron escrito
# contra ella devolvia CERO condados con el texto de verdad. Un parser que pasa
# sus propias pruebas y falla con el dato real es peor que no tenerlo.
OVERVIEW = """\
Agents
Armando Ochoa

Exp Realty Of California Inc.
Buyer Units

9

Counties
View States
View Counties
County\t
Solano County, CA\t$2.3M\t5\t$2.3M\t5\t$0\t0
Contra Costa County, CA\t$1.6M\t3\t$1.6M\t3\t$0\t0
Alameda County, CA\t$570K\t1\t$570K\t1\t$0\t0
Top Builders
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


# ══ UNA SOLA CAJA · el texto trae sus propios cortes ═════════════════════════
#
# Siete pegados por realtor son 175 sobre 25 capturas, y 175 oportunidades de
# poner algo en la caja equivocada.

def _mercado(nombre, volumen):
    """Un bloque de Market Signals con la forma real: el par de lineas
    `Market Signals` + `Set Location` es lo que lo abre."""
    return ("Market Signals\nSet Location\n\n"
            "Mortgage activity across this agent's active markets\n\n"
            "Market Overview\n\nTotal Loan Volume\n\n%s\n\nTotal Units\n\n"
            "1,096,337\n\nRolling Monthly Performance\n\nVolume\n\n$578.70B\n"
            % volumen)


VOLCADO = (
    OVERVIEW
    + _mercado("California", "$578.7B")
    + _mercado("Solano", "$6.0B")
    + _mercado("Contra Costa", "$17.2B")
    + _mercado("Alameda", "$20.2B")
    + "Originators this agent has worked with and their transaction history\n"
    + "Grace Davis\nNMLS: 862403\nEverett Financial, Inc.\t$540K\t1\t$540K\t35.3%\n"
    + "Lenders this agent has worked with and their transaction history\n"
    + "United Wholesale Mortgage\t$540K\t1\t$540K\t49.9%\n"
)


def test_el_separador_encuentra_las_cuatro_secciones():
    from captura.protocolo import separar_volcado

    s = separar_volcado(VOLCADO)
    assert len(s["market_signals"]) == 4
    assert "Counties" in s["overview"]
    assert "Market Signals" not in s["overview"], (
        "el Overview termina donde empieza el primer bloque de mercado"
    )
    assert s["originators"].startswith("Originators this agent")
    assert s["lenders"].startswith("Lenders this agent")


def test_Market_Signals_solo_NO_abre_un_bloque():
    """Aparece en la barra de pestañas de todas las secciones.

    Lo que abre un bloque de verdad es la pareja con `Set Location`, que solo
    esta en la pestaña de mercado. Sin esa condicion, el separador cortaria una
    vez por pestaña y daria seis bloques donde hay cuatro.
    """
    from captura.protocolo import separar_volcado

    con_barra = ("Agents\nArmando Ochoa\nOverview\nMarket Signals\n"
                 "Transactions\nOriginators\nLenders\nTitle Companies\n"
                 + VOLCADO)
    s = separar_volcado(con_barra)
    assert len(s["market_signals"]) == 4, len(s["market_signals"])


def test_sin_la_seccion_de_Originators_se_rechaza():
    """Sin cierre, el ultimo bloque se come todo el texto que viene despues.

    Las metricas saldrian igual -- solo que del sitio equivocado, que es el
    error que no se ve.
    """
    from captura.protocolo import separar_volcado

    sin_cierre = VOLCADO.split("Originators this agent")[0]
    try:
        separar_volcado(sin_cierre)
    except ProtocoloInvalido as exc:
        assert "no tiene cierre" in str(exc)
        assert "No se guarda nada" in str(exc)
    else:
        raise AssertionError("sin cierre no se puede saber donde termina")


def test_sin_ningun_bloque_de_mercado_se_rechaza():
    from captura.protocolo import separar_volcado

    try:
        separar_volcado(OVERVIEW + "Originators this agent has worked with\n")
    except ProtocoloInvalido as exc:
        assert "ningun bloque de Market Signals" in str(exc)
    else:
        raise AssertionError("hace falta al menos el bloque del estado")


def test_el_separador_y_la_validacion_de_conteo_encajan():
    """El camino entero: separar, leer condados, etiquetar por posicion."""
    from captura.parser_mm import parsear_mercado
    from captura.protocolo import separar_volcado

    s = separar_volcado(VOLCADO)
    condados = [n for n, _ in condados_del_overview(s["overview"])]
    assert condados == ["Solano", "Contra Costa", "Alameda"]

    bloques = etiquetar_por_posicion(s["market_signals"], condados)
    assert [b.nivel for b in bloques] == ["estado", "condado", "condado",
                                          "condado"]
    assert [b.etiqueta for b in bloques[1:]] == condados

    vols = [parsear_mercado(b.texto)["total_volume"] for b in bloques]
    assert vols == [578.7e9, 6.0e9, 17.2e9, 20.2e9], vols
    assert len(set(vols)) == 4, "el rodante dice $578.70B en los cuatro"


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


# ══ LOS CAMPOS QUE FALTABAN · texto real del volcado del 2026-09-22 ══════════
#
# Todos los fixtures de esta seccion son copias literales del volcado de Armando
# Ochoa. La ultima vez que invente el formato, el patron paso sus propias
# pruebas y devolvio cero contra el dato real.

#: La cabecera del perfil, con oficina, direccion y telefono.
CABECERA_REAL = """\
Agents
Armando Ochoa

Set Date Range:
Exp Realty Of California Inc.
2603 Camino Ramon

San Ramon CA 94583

View more
Office: (888) 584-9427
agentochoa9296@gmail.com
Producer Tier
Mid-Tier
"""

#: El desglose por tipo, con la seccion de arriba que tiene LA MISMA forma.
LOAN_MIX_REAL = """\
Buyer Units

9

Buyer vs. Listing Side
100%
Buyer
Represented
Volume / Units / Share
Buyer
$4.9M / 9 Units
100.0%
Loan Type Breakdown (Buyer)
98%
FHA
Loan Type
Volume / Units / Share
FHA
$1.1M / 2 Units
66.7%
HE (Home Equity)
$23K / 1 Units
33.3%
Monthly Volume
"""

#: La cabecera de Lenders y su tabla.
LENDERS_REAL = """\
Total Lenders
3
Top 5 Concentration
100.0%
TPO %
66.7%
Avg Loan Size
$361K
Lending Companies
Lenders this agent has worked with and their transaction history

All
all
Search by lender name...
United Wholesale Mortgage\t$540K\t1\t$540K\t49.9%
Kings Mortgage Services Inc\t$520K\t1\t$520K\t48.0%
Everett Financial Inc\t$23K\t1\t$23K\t2.1%
Rows per page
"""

#: Conforming vs Jumbo con su denominador, y el del mercado arriba.
CONFORMING_REAL = """\
Market Overview

Total Loan Volume

$578.7B

Total Units

1,096,337

Conforming vs Jumbo
Total Units
613.2K
Role
Volume / Units
Conforming
509,013 loans
83.0%
Jumbo
104,166 loans
17.0%
Borrower Profile
"""

#: Los canales, con `Not Labeled` repetido arriba con OTRO valor.
CANAL_REAL = """\
Transaction Type Distribution
Refinance
38.3%
Purchase
37.2%
Not Labeled
11.6%
Lender Type Distribution
State Licensed
52.6%
Loan Channel Distribution
Banked - Retail
57.9%
Banked - Wholesale
19.3%
Correspondent
16.7%
Brokered
5.1%
Not Labeled
0.9%
"""

#: Buyer Side Relationships: reparto por UNIDADES.
RELACIONES_REAL = """\
Buyer Side Relationships
Originator\tTotal Volume\tTotal Units\tWallet Share
Chris Ruiz
Everett Financial, Inc.

$470K\t2\t50%
Grace Davis
Everett Financial, Inc.

$540K\t1\t25%
Mario Diaz Hernandez Jr
Andy's Home Loans

$520K\t1\t25%
Seller Side Relationships
No originator relationships found for this period.
"""


# ── el contraste FHA: la mitad del agente, CON su denominador ───────────────

def test_el_loan_mix_del_agente_sale_con_sus_unidades():
    from captura.parser_mm import parsear_perfil

    p = parsear_perfil(LOAN_MIX_REAL)
    mix = p["loan_mix_buyer"]
    assert [f["tipo"] for f in mix["filas"]] == ["FHA", "HE (Home Equity)"]
    assert [f["unidades"] for f in mix["filas"]] == [2, 1]
    assert [f["share"] for f in mix["filas"]] == [66.7, 33.3]
    assert mix["filas"][0]["volumen"] == 1.1e6


def test_el_loan_mix_NO_se_come_el_Buyer_vs_Listing_de_arriba():
    """`Buyer / $4.9M / 9 Units / 100.0%` tiene exactamente la misma forma.

    Sin acotar la seccion entraria como un tipo de prestamo llamado `Buyer` con
    9 unidades, que es mas de las que tiene el desglose entero.
    """
    from captura.parser_mm import parsear_perfil

    mix = parsear_perfil(LOAN_MIX_REAL)["loan_mix_buyer"]
    assert "Buyer" not in [f["tipo"] for f in mix["filas"]]
    assert mix["unidades_identificadas"] == 3


def test_el_share_de_FHA_NO_es_sobre_los_buyer_units():
    """66,7% de FHA son 2 operaciones sobre 3 identificadas, no 6 sobre 9.

    La guardia de PACS-H pide 10 operaciones con tipo identificado y 50% de
    cobertura. Sin `cobertura` esa guardia no tiene con que correr, y una
    guardia que no puede correr pasa siempre.
    """
    from captura.parser_mm import parsear_perfil

    mix = parsear_perfil(LOAN_MIX_REAL)["loan_mix_buyer"]
    assert mix["buyer_units"] == 9
    assert mix["unidades_identificadas"] == 3
    assert mix["cobertura"] == 33.3
    assert mix["cobertura"] < 50, (
        "este perfil NO pasa la guardia de cobertura, y el parser tiene que "
        "dejar verlo en vez de reportar un 66,7% pelado"
    )


# ── el contraste de canal: las dos mitades, cada una de su lado ─────────────

def test_el_TPO_del_agente_sale_de_la_cabecera_de_Lenders():
    from captura.parser_mm import parsear_perfil

    p = parsear_perfil(LENDERS_REAL)
    assert p["tpo_pct"] == 66.7
    assert p["cabecera_lenders"]["total_lenders"] == 3
    assert p["cabecera_lenders"]["top5_concentracion"] == 100.0


def test_el_Avg_Loan_Size_de_Lenders_no_se_mezcla_con_el_del_comprador():
    """Sale dos veces en el mismo perfil: $444K arriba y $361K en Lenders."""
    from captura.parser_mm import parsear_perfil

    texto = "Avg Loan Size\n\n$444K\n\n" + LENDERS_REAL
    p = parsear_perfil(texto)
    assert p["cabecera_lenders"]["avg_loan_size"] == 361000.0


def test_la_tabla_de_lenders_sale_completa():
    from captura.parser_mm import parsear_perfil

    filas = parsear_perfil(LENDERS_REAL)["tabla_lenders"]
    assert [f["nombre"] for f in filas] == [
        "United Wholesale Mortgage", "Kings Mortgage Services Inc",
        "Everett Financial Inc"]
    assert [f["unidades"] for f in filas] == [1, 1, 1]
    assert [f["share"] for f in filas] == [49.9, 48.0, 2.1]
    assert filas[0]["volumen"] == 540000.0


def test_los_canales_del_mercado_salen_los_cinco():
    from captura.parser_mm import parsear_mercado

    c = parsear_mercado(CANAL_REAL)["loan_channel"]
    assert c["banked_retail"] == 57.9
    assert c["banked_wholesale"] == 19.3
    assert c["correspondent"] == 16.7
    assert c["brokered"] == 5.1


def test_el_Not_Labeled_del_canal_no_es_el_de_Transaction_Type():
    """11,6% arriba y 0,9% abajo. Sin acotar se lleva el primero."""
    from captura.parser_mm import parsear_mercado

    c = parsear_mercado(CANAL_REAL)["loan_channel"]
    assert c["not_labeled"] == 0.9, c["not_labeled"]


# ── conforming vs jumbo: el denominador propio, explicito ───────────────────

def test_conforming_trae_SU_denominador_y_no_el_del_mercado():
    from captura.parser_mm import parsear_mercado

    m = parsear_mercado(CONFORMING_REAL)
    c = m["conforming"]
    assert m["total_units"] == 1096337, "el del mercado"
    assert c["denominador_propio"] == 613200.0, "el de conforming/jumbo"
    assert c["unidades_del_mercado"] == 1096337
    assert c["denominador_propio"] != c["unidades_del_mercado"]


def test_los_dos_tramos_suman_su_propio_denominador():
    """509.013 + 104.166 = 613.179 contra 613,2K. Si no cuadra, se leyo cruzado."""
    from captura.parser_mm import parsear_mercado

    c = parsear_mercado(CONFORMING_REAL)["conforming"]
    assert c["conforming_loans"] == 509013
    assert c["jumbo_loans"] == 104166
    assert c["suma_de_tramos"] == 613179
    assert c["cuadra"] is True


def test_un_denominador_mayor_que_el_mercado_se_marca():
    """Si el suyo supera al del mercado, el bloque se leyo cruzado.

    La misma comprobacion existe en `MixConforming.verificar`, que hay que
    construir a mano. Esta corre sola en cada captura: es redundante a
    proposito, como toda guarda que protege de un error invisible.
    """
    from captura.parser_mm import parsear_mercado

    sano = parsear_mercado(CONFORMING_REAL)["conforming"]
    assert sano["mayor_que_el_mercado"] is False

    cruzado = parsear_mercado(
        CONFORMING_REAL.replace("Total Units\n\n1,096,337",
                                "Total Units\n\n14,315"))["conforming"]
    assert cruzado["mayor_que_el_mercado"] is True


def test_el_17_por_ciento_de_jumbo_NO_se_multiplica_por_el_mercado():
    """Sobre 1.096.337 daria 186.377 jumbos. Los que hay son 104.166."""
    from captura.parser_mm import parsear_mercado

    c = parsear_mercado(CONFORMING_REAL)["conforming"]
    inventado = 0.17 * c["unidades_del_mercado"]
    assert abs(inventado - c["jumbo_loans"]) > 80000, (
        "la diferencia entre usar un denominador y el otro es de 82.000 "
        "operaciones: por eso el denominador va guardado al lado"
    )


# ── el wallet share de la exclusion se decide por UNIDADES ──────────────────

def test_el_reparto_por_unidades_sale_de_Buyer_Side_Relationships():
    from captura.parser_mm import parsear_perfil

    p = parsear_perfil(RELACIONES_REAL)
    assert [o["nombre"] for o in p["orig_buyer"]] == [
        "Chris Ruiz", "Grace Davis", "Mario Diaz Hernandez Jr"]
    assert [o["unidades"] for o in p["orig_buyer"]] == [2, 1, 1]
    assert p["orig_buyer"][0]["share"] == 50.0


def test_Chris_Ruiz_da_50_por_unidades_y_30_7_por_volumen():
    """El caso exacto donde la eleccion de base cambia el resultado.

    Con un umbral en 40% el mismo originador entra o no entra segun que base se
    use, y las dos lecturas salen del mismo perfil sin que nada avise.
    """
    from captura.parser_mm import _tabla_originadores, parsear_perfil

    por_unidades = parsear_perfil(RELACIONES_REAL)["orig_buyer"]
    chris_u = [o for o in por_unidades if o["nombre"] == "Chris Ruiz"][0]

    por_volumen = _tabla_originadores(
        "Originators this agent has worked with\n"
        "Chris Ruiz\nNMLS: 1544562\n"
        "Everett Financial, Inc.\t$470K\t2\t$235K\t30.7%\n"
        "Lenders this agent has worked with\n")
    chris_v = [o for o in por_volumen if o["nombre"] == "Chris Ruiz"][0]

    assert chris_u["share"] == 50.0
    assert chris_v["share"] == 30.7
    assert chris_u["share"] > 40 > chris_v["share"], (
        "un umbral en 40% lo deja de un lado o del otro segun la base"
    )


def test_la_exclusion_lee_unidades_y_NUNCA_cae_al_de_volumen():
    from captura.parser_mm import parsear_perfil
    from captura.trampas import (
        BASE_PARA_EXCLUSION,
        wallet_share_para_exclusion,
    )

    assert BASE_PARA_EXCLUSION == "unidades"

    p = parsear_perfil(RELACIONES_REAL)
    assert [o["nombre"] for o in wallet_share_para_exclusion(p)] == [
        "Chris Ruiz", "Grace Davis", "Mario Diaz Hernandez Jr"]

    # Sin Buyer Side Relationships devuelve vacio: NO usa `tab_orig`.
    solo_volumen = {"tab_orig": [{"nombre": "Chris Ruiz", "share": 30.7}]}
    assert wallet_share_para_exclusion(solo_volumen) == []


def test_el_share_de_la_casa_va_con_su_denominador():
    """Chris y Grace son de Everett: 3 de las 4 unidades del reparto.

    Y esas 4 no son las 9 unidades compradoras del agente -- la tabla de
    relaciones tiene su propio alcance. Por eso el denominador viaja al lado.
    """
    from captura.parser_mm import parsear_perfil
    from captura.trampas import share_de_la_casa

    s = share_de_la_casa(parsear_perfil(RELACIONES_REAL))
    assert s["originadores"] == ["Chris Ruiz", "Grace Davis"]
    assert s["unidades"] == 3
    assert s["unidades_totales"] == 4
    assert s["share"] == 75.0
    assert s["base"] == "unidades"


def test_sin_reparto_el_share_de_la_casa_es_None_y_no_cero():
    """Un cero dice `no trabaja con la casa`. Es la conclusion contraria."""
    from captura.trampas import share_de_la_casa

    s = share_de_la_casa({"tab_orig": [{"nombre": "X", "share": 99.0}]})
    assert s["share"] is None
    assert "no trajo Buyer Side Relationships" in s["razon"]


def test_decidir_la_exclusion_por_volumen_falla_ruidosamente():
    from captura.trampas import verificar_base_de_exclusion

    verificar_base_de_exclusion("unidades")
    try:
        verificar_base_de_exclusion("volumen")
    except TrampaDetectada as exc:
        assert "50,0%" in str(exc) and "30,7%" in str(exc)
    else:
        raise AssertionError("la base cambia el resultado: no puede pasar")


# ── la cabecera del perfil: oficina, direccion y telefono ───────────────────

def test_la_cabecera_da_oficina_direccion_y_telefono():
    from captura.parser_mm import parsear_perfil

    c = parsear_perfil(CABECERA_REAL)["contacto"]
    assert c["oficina"] == "Exp Realty Of California Inc."
    assert c["calle"] == "2603 Camino Ramon"
    assert c["ciudad"] == "San Ramon"
    assert c["estado_postal"] == "CA"
    assert c["cp"] == "94583"
    assert c["direccion"] == "2603 Camino Ramon, San Ramon CA 94583"
    assert c["telefono_oficina"] == "(888) 584-9427"
    assert c["telefono_oficina_e164"] == "+18885849427"


def test_sin_la_linea_de_ciudad_la_direccion_queda_en_None():
    """Una direccion adivinada se guarda igual de bien que una correcta."""
    from captura.parser_mm import parsear_perfil

    c = parsear_perfil("Agents\nArmando Ochoa\nProducer Tier\nMid-Tier\n")["contacto"]
    assert c["direccion"] is None
    assert c["oficina"] is None
    assert c["calle"] is None


def test_Set_Date_Range_no_se_toma_como_nombre_de_oficina():
    """Es la etiqueta de la interfaz que esta justo encima cuando no hay empresa."""
    from captura.parser_mm import parsear_perfil

    sin_empresa = ("Agents\nArmando Ochoa\nSet Date Range:\n"
                   "2603 Camino Ramon\nSan Ramon CA 94583\nView more\n")
    c = parsear_perfil(sin_empresa)["contacto"]
    assert c["oficina"] is None
    assert c["calle"] == "2603 Camino Ramon"


def test_los_contactos_van_a_pacs_contactos_con_fuente_Model_Match():
    """Se ACUMULAN: la unique key incluye la fuente."""
    sys.path.insert(0, os.path.join(RAIZ, "api"))
    from api.rutas import FUENTE_CONTACTOS, _contactos_de

    from captura.parser_mm import parsear_perfil

    filas = _contactos_de(parsear_perfil(CABECERA_REAL), "r-1", "lote-1",
                          "2026-09-22T00:00:00Z")
    por_canal = {f["canal"]: f["valor"] for f in filas}
    assert por_canal["telefono"] == "+18885849427"
    assert por_canal["oficina"] == "Exp Realty Of California Inc."
    assert por_canal["direccion"] == "2603 Camino Ramon, San Ramon CA 94583"
    assert all(f["fuente"] == FUENTE_CONTACTOS for f in filas)
    assert all(f["realtor_id"] == "r-1" for f in filas)


def test_un_perfil_sin_contacto_no_escribe_filas_vacias():
    from api.rutas import _contactos_de

    assert _contactos_de({}, "r-1", "l-1", "t") == []
    assert _contactos_de({"contacto": {"oficina": "  "}}, "r-1", "l-1", "t") == []


# ── los cortes de seccion: cada cabecera con su pestaña ─────────────────────

def test_la_cabecera_de_Lenders_no_queda_en_Originators():
    """El `TPO %` es la mitad de agente del contraste de canal.

    Cortar por la frase `Lenders this agent has worked with` dejaba las cuatro
    tarjetas de cabecera -- Total Lenders, Top 5, TPO %, Avg Loan Size-- dentro
    de la seccion de Originators. El texto se guardaba entero, asi que nada
    avisaba: solo quedaba bajo la etiqueta equivocada.
    """
    from captura.protocolo import separar_volcado

    completo = (
        OVERVIEW
        + _mercado("California", "$578.7B")
        + "Total Originators\n3\nTop 3 Concentration\n100.0%\n"
        + "Originators this agent has worked with\n"
        + "Grace Davis\nNMLS: 862403\n"
          "Everett Financial, Inc.\t$540K\t1\t$540K\t35.3%\n"
        + LENDERS_REAL
    )
    s = separar_volcado(completo)
    assert "TPO %" in s["lenders"]
    assert "TPO %" not in s["originators"]
    assert s["lenders"].startswith("Total Lenders")


def test_la_cabecera_de_Originators_no_queda_en_el_ultimo_mercado():
    from captura.protocolo import separar_volcado

    completo = (
        OVERVIEW
        + _mercado("California", "$578.7B")
        + "Total Originators\n3\nTop 3 Concentration\n100.0%\n"
        + "Originators this agent has worked with\n"
        + "Grace Davis\nNMLS: 862403\n"
          "Everett Financial, Inc.\t$540K\t1\t$540K\t35.3%\n"
    )
    s = separar_volcado(completo)
    assert "Total Originators" not in s["market_signals"][-1]
    assert s["originators"].startswith("Total Originators")


def test_sin_cabecera_el_corte_sigue_siendo_la_frase():
    """No todos los volcados la traen: el marcador seguro sigue siendo la frase."""
    from captura.protocolo import separar_volcado

    s = separar_volcado(VOLCADO)
    assert s["originators"].startswith("Originators this agent")
    assert s["lenders"].startswith("Lenders this agent")


# ══ LA BASE DEL REPARTO SE MIDE, NO SE DECLARA ══════════════════════════════
#
# `wallet_share_base` era un dict fijo copiado en cada fila. En el payload de
# ensayo decia "volumen" sobre porcentajes de unidades y nada fallaba, porque
# una etiqueta que nadie comprueba no puede fallar.

#: Los tres del Overview real, con sus unidades y volumenes.
REPARTO_POR_UNIDADES = [
    {"nombre": "Chris Ruiz", "empresa": "Everett Financial, Inc.",
     "volumen": 470000.0, "unidades": 2, "share": 50.0},
    {"nombre": "Grace Davis", "empresa": "Everett Financial, Inc.",
     "volumen": 540000.0, "unidades": 1, "share": 25.0},
    {"nombre": "Mario Diaz Hernandez Jr", "empresa": "Andy's Home Loans",
     "volumen": 520000.0, "unidades": 1, "share": 25.0},
]

#: Los mismos tres de la pestaña Originators: mismas unidades, otro share.
REPARTO_POR_VOLUMEN = [
    {"nombre": "Grace Davis", "empresa": "Everett Financial, Inc.",
     "volumen": 540000.0, "unidades": 1, "share": 35.3},
    {"nombre": "Mario Diaz Hernandez Jr", "empresa": "Andy's Home Loans",
     "volumen": 520000.0, "unidades": 1, "share": 34.0},
    {"nombre": "Chris Ruiz", "empresa": "Everett Financial, Inc.",
     "volumen": 470000.0, "unidades": 2, "share": 30.7},
]


def test_la_base_se_mide_recalculando_el_share():
    """Las mismas tres personas, los mismos volumenes, distinta base."""
    from captura.parser_mm import base_del_reparto

    assert base_del_reparto(REPARTO_POR_UNIDADES) == "unidades"
    assert base_del_reparto(REPARTO_POR_VOLUMEN) == "volumen"


def test_una_base_que_no_reproduce_ninguna_de_las_dos_es_None():
    """Es lo que pasaba con el payload de ensayo: 50,0 y 25,0 sobre 2 y 1
    unidades no salen ni por unidades (66,7/33,3) ni por volumen (66,1/33,9).

    Antes eso se guardaba etiquetado 'volumen' y se creia.
    """
    from captura.parser_mm import base_del_reparto

    inventado = [
        {"nombre": "Chris Ruiz", "volumen": 4.1e6, "unidades": 2, "share": 50.0},
        {"nombre": "Grace Davis", "volumen": 2.1e6, "unidades": 1, "share": 25.0},
    ]
    assert base_del_reparto(inventado) is None


def test_con_una_sola_relacion_la_base_es_indistinguible():
    """Al 100% las dos bases dan lo mismo: la eleccion no cambia nada."""
    from captura.parser_mm import base_del_reparto

    uno = [{"nombre": "X", "volumen": 500000.0, "unidades": 3, "share": 100.0}]
    assert base_del_reparto(uno) == "indistinguible"


def test_la_etiqueta_de_base_dice_si_coincide_con_lo_esperado():
    from captura.parser_mm import parsear_perfil

    base = parsear_perfil(RELACIONES_REAL)["wallet_share_base"]
    assert base["orig_buyer"]["medida"] == "unidades"
    assert base["orig_buyer"]["esperada"] == "unidades"
    assert base["orig_buyer"]["coincide"] is True
    assert base["orig_buyer"]["filas"] == 3
    # `tab_orig` no esta en este texto: no se afirma nada sobre el.
    assert base["tab_orig"]["medida"] is None
    assert base["tab_orig"]["filas"] == 0


def test_la_exclusion_se_bloquea_si_la_base_medida_no_es_unidades():
    from captura.trampas import TrampaDetectada, wallet_share_para_exclusion

    perfil = {
        "orig_buyer": REPARTO_POR_VOLUMEN,
        "wallet_share_base": {"orig_buyer": {"esperada": "unidades",
                                             "medida": "volumen",
                                             "coincide": False, "filas": 3}},
    }
    try:
        wallet_share_para_exclusion(perfil)
    except TrampaDetectada as exc:
        assert "NO reparte por unidades" in str(exc)
    else:
        raise AssertionError("usar el de volumen da la definicion equivocada")


# ══ UN ARRAY VACIO NO PUEDE SIGNIFICAR DOS COSAS ═════════════════════════════

def test_si_la_seccion_esta_y_el_campo_sale_vacio_es_un_fallo_declarado():
    """Sin esto, `[]` dice a la vez `no trabaja con nadie` y `no supe leerlo`.

    La primera es un dato y la segunda es un error, y se guardaban identicas.
    """
    from captura.parser_mm import fallos_de_seccion

    roto = ("Buyer Side Relationships\n"
            "Originator\tTotal Volume\tTotal Units\tWallet Share\n"
            "Chris Ruiz\nEverett Financial, Inc.\n"
            "470K | 2 | 50\n"          # sin '$' ni '%': el patron no la ve
            "Seller Side Relationships\n")
    fallos = fallos_de_seccion(roto, {"orig_buyer": []})
    assert [f["campo"] for f in fallos] == ["orig_buyer"]
    assert "no-canibalizacion" in fallos[0]["por_que_importa"]


def test_una_seccion_que_la_fuente_declara_vacia_NO_es_un_fallo():
    """`No originator relationships found for this period.` es un dato."""
    from captura.parser_mm import fallos_de_seccion

    vacia = ("Seller Side Relationships\n"
             "No originator relationships found for this period.\n")
    assert fallos_de_seccion(vacia, {"orig_seller": []}) == []


def test_una_seccion_ausente_tampoco_es_un_fallo():
    """El payload de ensayo no traia Buyer Side Relationships: no hay nada
    que leer mal, y decir que fallo seria inventar un error."""
    from captura.parser_mm import fallos_de_seccion

    assert fallos_de_seccion("Originators this agent has worked with\n"
                             "Chris Ruiz\nNMLS: 2129\n"
                             "Everett Financial Inc $4.1M 2 $2.05M 50.0%\n",
                             {"tab_orig": [{"nombre": "Chris Ruiz"}]}) == []


def test_la_exclusion_revienta_sobre_un_fallo_declarado():
    """Un `[]` con fallo declarado NO puede leerse como `no trabaja con nadie`."""
    from captura.trampas import TrampaDetectada, wallet_share_para_exclusion

    perfil = {"orig_buyer": [],
              "fallos": [{"campo": "orig_buyer", "seccion": "Buyer Side "
                          "Relationships", "detalle": "la seccion esta en el "
                          "texto y el campo salio vacio"}]}
    try:
        wallet_share_para_exclusion(perfil)
    except TrampaDetectada as exc:
        assert "conclusion contraria" in str(exc)
    else:
        raise AssertionError("Armando con 75% en Everett pasaria el filtro")


# ══ EL PERFIL VIVE EN DOS FILAS ══════════════════════════════════════════════

def test_orig_buyer_y_tab_orig_estan_en_FILAS_DISTINTAS():
    """`orig_buyer` sale del Overview y `tab_orig` de Originators.

    Preguntarle a una sola fila devuelve la mitad del perfil sin que nada
    avise: la fila de Originators -- la que PARECE traer los originadores-- da
    `orig_buyer = []`, y con eso la exclusion no dispara.
    """
    from captura.parser_mm import parsear_perfil

    del_overview = parsear_perfil(RELACIONES_REAL)
    de_originators = parsear_perfil(TAB_ORIGINADORES)

    assert len(del_overview["orig_buyer"]) == 3
    assert del_overview["tab_orig"] == []
    assert de_originators["orig_buyer"] == []
    assert len(de_originators["tab_orig"]) == 2


def test_unir_perfiles_junta_las_dos_mitades():
    from captura.parser_mm import parsear_perfil, unir_perfiles

    unido = unir_perfiles([parsear_perfil(RELACIONES_REAL),
                           parsear_perfil(TAB_ORIGINADORES)])
    assert len(unido["orig_buyer"]) == 3
    assert len(unido["tab_orig"]) == 2
    assert unido["filas_unidas"] == 2
    assert unido["wallet_share_base"]["orig_buyer"]["medida"] == "unidades"


def test_sobre_el_perfil_unido_la_exclusion_si_dispara():
    from captura.parser_mm import parsear_perfil, unir_perfiles
    from captura.trampas import share_de_la_casa

    unido = unir_perfiles([parsear_perfil(CABECERA_REAL),
                           parsear_perfil(RELACIONES_REAL),
                           parsear_perfil(TAB_ORIGINADORES)])
    s = share_de_la_casa(unido)
    assert s["originadores"] == ["Chris Ruiz", "Grace Davis"]
    assert s["unidades_totales"] == 4
    assert s["share"] == 75.0
    # Y la cabecera no se perdio al unir.
    assert unido["contacto"]["oficina"] == "Exp Realty Of California Inc."


def test_preguntarle_solo_a_la_fila_de_originators_da_None_con_su_razon():
    """No cero: cero diria `no trabaja con la casa`."""
    from captura.parser_mm import parsear_perfil
    from captura.trampas import share_de_la_casa

    s = share_de_la_casa(parsear_perfil(TAB_ORIGINADORES))
    assert s["share"] is None
    assert "unir_perfiles" in s["razon"]


# ══ EL ESTADO, NORMALIZADO ═══════════════════════════════════════════════════

def test_las_tres_formas_del_estado_dan_el_mismo_codigo():
    """`CA`, `California` y `CALIFORNIA` entraron como tres mercados."""
    from captura.estados import normalizar_estado

    assert normalizar_estado("CA") == "CA"
    assert normalizar_estado("ca") == "CA"
    assert normalizar_estado(" California ") == "CA"
    assert normalizar_estado("CALIFORNIA") == "CA"
    assert normalizar_estado("california") == "CA"


def test_un_estado_desconocido_da_None_y_no_el_texto_original():
    """Dejar pasar el valor libre es lo que produjo las tres variantes."""
    from captura.estados import normalizar_estado

    assert normalizar_estado("Californa") is None
    assert normalizar_estado("") is None
    assert normalizar_estado(None) is None


# ══ LAS CAPTURAS ACUMULAN · un lote no reemplaza al anterior ════════════════
#
# `cargar.py` apaga el lote previo de la misma fuente al encender el nuevo. Es
# correcto para el libro -- llega una version nueva y la vieja se apaga entera--
# y es destructivo para las capturas, donde cada lote es UN realtor distinto.
#
# Se comprobo contra la base que no hay trigger ni nada automatico que lo haga.
# Pero el camino existe y es una linea: correr el cargador con fuente
# 'modelmatch' dejaria viva solo la ultima captura. Las filas seguirian en la
# tabla, la vista devolveria menos, y nada fallaria.

def test_modelmatch_esta_declarada_como_fuente_que_acumula():
    from supabase.cargar import FUENTES_QUE_ACUMULAN

    assert "modelmatch" in FUENTES_QUE_ACUMULAN
    assert "libro_v3" not in FUENTES_QUE_ACUMULAN, (
        "el libro SI se reemplaza entero: apagar el lote anterior es lo "
        "correcto ahi"
    )


def test_volver_atras_en_capturas_falla_sin_tocar_la_base():
    """Y falla ANTES de abrir la conexion: una guarda que necesita la base
    para decidir ya toco la base."""
    from supabase.cargar import CargaFallida, volver_al_anterior

    try:
        volver_al_anterior("modelmatch")
    except CargaFallida as exc:
        assert "acumulan" in str(exc)
        assert "dos realtors distintos" in str(exc)
    else:
        raise AssertionError(
            "volver atras encenderia la captura de otro realtor")


# ══ LA CONFIRMACION EN PANTALLA ══════════════════════════════════════════════
#
# Capturar 25 condados a ciegas y descubrir el problema al final es la forma
# cara de descubrirlo.

def _fila_mercado(etiqueta, nivel, volumen, fha=12.0, fallout=31.1, orden=0):
    return {"parseado": {"seccion": "market_signals", "nivel": nivel,
                         "etiqueta_geografica": etiqueta, "orden": orden,
                         "metricas": {"total_volume": volumen, "mkt_fha": fha,
                                      "fallout": fallout, "campos": 44}},
            "texto_crudo": "x" * 3000}


def test_el_resumen_lista_los_bloques_con_su_geografia_en_orden():
    """Y los ORDENA. PostgREST devuelve las filas de una captura en orden
    arbitrario porque todas comparten `capturado_en` -- se escriben en la misma
    peticion. El orden de los bloques de mercado no es presentacion: es lo que
    los etiqueta.
    """
    from api.rutas import resumen_de_captura

    # A proposito revueltas, como vuelven de la base.
    filas = [
        _fila_mercado("Alameda", "condado", 20.2e9, 3.2, 29.7, orden=2),
        {"parseado": {"seccion": "originators", "orden": 0}, "texto_crudo": "r" * 1522},
        _fila_mercado("Solano", "condado", 6.0e9, 16.0, 35.6, orden=1),
        {"parseado": {"seccion": "overview", "orden": 0}, "texto_crudo": "o" * 2252},
        _fila_mercado("CA", "estado", 578.7e9, orden=0),
    ]
    r = resumen_de_captura(filas, {})
    assert [s["seccion"] for s in r["secciones"]] == [
        "overview", "market_signals", "market_signals", "market_signals",
        "originators"]
    assert [g["etiqueta"] for g in r["geografias"]] == ["CA", "Solano",
                                                        "Alameda"]
    assert r["secciones"][0]["caracteres"] == 2252


def test_dos_geografias_con_el_mismo_volumen_se_marcan_LAS_DOS():
    """Es la firma del grafico rodante. Y se dice CUALES: con cuatro bloques
    saber que pasa no alcanza, hay que saber donde mirar."""
    from api.rutas import resumen_de_captura

    filas = [_fila_mercado("CA", "estado", 578.7e9, orden=0),
             _fila_mercado("Solano", "condado", 578.7e9, orden=1),
             _fila_mercado("Alameda", "condado", 20.2e9, orden=2)]
    r = resumen_de_captura(filas, {})
    assert r["volumenes_repetidos"] == [["CA", "Solano"]]
    marcadas = [g["etiqueta"] for g in r["geografias"] if g["volumen_repetido"]]
    assert marcadas == ["CA", "Solano"]


def test_volumenes_distintos_no_marcan_nada():
    """La guarda tiene que poder NO disparar; si no, no distingue nada."""
    from api.rutas import resumen_de_captura

    r = resumen_de_captura(
        [_fila_mercado("CA", "estado", 578.7e9, orden=0),
         _fila_mercado("Solano", "condado", 6.0e9, orden=1)], {})
    assert r["volumenes_repetidos"] == []
    assert not any(g["volumen_repetido"] for g in r["geografias"])


def test_el_resumen_marca_quien_es_de_la_casa():
    from api.rutas import resumen_de_captura
    from captura.parser_mm import parsear_perfil

    r = resumen_de_captura([], parsear_perfil(RELACIONES_REAL))
    de_la_casa = [o["nombre"] for o in r["originadores"] if o["de_la_casa"]]
    assert de_la_casa == ["Chris Ruiz", "Grace Davis"]
    assert r["share_de_la_casa"]["share"] == 75.0


def test_un_fallo_declarado_no_tumba_el_resumen_pero_sale_en_el():
    """`share_de_la_casa` revienta a proposito sobre un fallo declarado. En la
    pantalla eso tiene que aparecer con su razon, no tirar el guardado: el
    crudo ya esta guardado cuando se arma el resumen."""
    from api.rutas import resumen_de_captura

    perfil = {"orig_buyer": [],
              "fallos": [{"campo": "orig_buyer",
                          "seccion": "Buyer Side Relationships",
                          "por_que_importa": "la exclusion",
                          "detalle": "vacio"}]}
    r = resumen_de_captura([], perfil)
    assert r["share_de_la_casa"]["share"] is None
    assert "no se pudo calcular" in r["share_de_la_casa"]["razon"]
    assert [f["campo"] for f in r["fallos"]] == ["orig_buyer"]


# ══ LA FORMA VIEJA DE wallet_share_base ══════════════════════════════════════
#
# Hasta hoy era un string plano. Las capturas ya guardadas lo tienen asi, y
# quien las lea se encuentra las dos formas en la misma tabla.

def test_la_forma_vieja_no_pasa_por_medicion():
    """Era una etiqueta declarada. Convertirla en medida le daria una autoridad
    que nunca tuvo."""
    from captura.parser_mm import base_normalizada

    v = base_normalizada("unidades")
    assert v["medida"] is None, "declarada no es medida"
    assert v["esperada"] == "unidades"
    assert v["heredada"] == "unidades"
    assert v["filas"] == 0


def test_unir_perfiles_tolera_la_forma_vieja():
    from captura.parser_mm import parsear_perfil, unir_perfiles

    viejo = {"orig_buyer": [], "tab_orig": [],
             "wallet_share_base": {"orig_buyer": "unidades",
                                   "tab_orig": "volumen"}}
    unido = unir_perfiles([viejo, parsear_perfil(RELACIONES_REAL)])
    assert len(unido["orig_buyer"]) == 3
    # Gana la MEDIDA sobre la heredada, porque tiene filas detras.
    assert unido["wallet_share_base"]["orig_buyer"]["medida"] == "unidades"
    assert unido["wallet_share_base"]["orig_buyer"]["filas"] == 3


def test_la_exclusion_sobre_la_forma_vieja_no_se_bloquea_ni_se_cree_la_etiqueta():
    """Sin medicion no hay con que bloquear, asi que se deja pasar -- pero la
    etiqueta heredada no se convierte en un `medida` que nadie comprobo."""
    from captura.parser_mm import base_normalizada
    from captura.trampas import wallet_share_para_exclusion

    perfil = {"orig_buyer": REPARTO_POR_UNIDADES,
              "wallet_share_base": {"orig_buyer": "unidades"}}
    assert len(wallet_share_para_exclusion(perfil)) == 3
    assert base_normalizada("unidades")["medida"] is None


# ══ DOS CAPTURAS DEL MISMO REALTOR · manda la mas reciente ══════════════════
#
# Antes las COMBINABA, y mal: `Solano` salia dos veces en los contrastes y
# `unir_perfiles` tomaba "la primera no vacia" de un orden que PostgREST no
# garantiza. Entre dos capturas con cifras distintas ganaba una al azar, y el
# diagnostico cambiaba sin que nadie tocara nada.

def _fila(lote, cuando, etiqueta):
    return {"upload_batch_id": lote, "capturado_en": cuando,
            "geografia_etiqueta": etiqueta, "parseado": {}}


def test_manda_la_captura_mas_reciente():
    from api.rutas import lote_vigente

    filas = [_fila("A", "2026-09-22T20:07:00Z", "Solano"),
             _fila("A", "2026-09-22T20:07:00Z", "Alameda"),
             _fila("B", "2026-09-23T10:00:00Z", "Solano"),
             _fila("B", "2026-09-23T10:00:00Z", "Alameda")]
    vivas, cuantas = lote_vigente(filas)
    assert {f["upload_batch_id"] for f in vivas} == {"B"}
    assert len(vivas) == 2
    assert cuantas["lotes"] == 2 and cuantas["anteriores"] == 1


def test_no_se_duplica_una_geografia_entre_capturas():
    """Dos tarjetas de Solano con cifras distintas son la misma geografía
    leída dos veces, y el BD no sabe cuál mirar."""
    from api.rutas import lote_vigente

    vivas, _ = lote_vigente([_fila("A", "2026-09-22T20:07:00Z", "Solano"),
                             _fila("B", "2026-09-23T10:00:00Z", "Solano")])
    assert [f["geografia_etiqueta"] for f in vivas] == ["Solano"]


def test_el_orden_se_calcula_aqui_y_no_se_confia_en_el_que_venga():
    """Apoyar la regla en que el servidor devuelva lo que se le pidió es
    apoyarla en algo que no se comprueba."""
    from api.rutas import lote_vigente

    # A propósito al revés de lo que pide la consulta.
    vivas, _ = lote_vigente([_fila("B", "2026-09-23T10:00:00Z", "Solano"),
                             _fila("A", "2026-09-24T10:00:00Z", "Solano")])
    assert vivas[0]["upload_batch_id"] == "A"


def test_con_una_sola_captura_no_hay_anteriores():
    from api.rutas import lote_vigente

    _v, cuantas = lote_vigente([_fila("A", "2026-09-22T20:07:00Z", "Solano")])
    assert cuantas["lotes"] == 1 and cuantas["anteriores"] == 0


def test_sin_capturas_devuelve_vacio_sin_reventar():
    from api.rutas import lote_vigente

    vivas, cuantas = lote_vigente([])
    assert vivas == [] and cuantas["lotes"] == 0


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
