"""La pestaña Transactions: una fila por cierre, y lo que se deriva de ella.

Los datos son inventados con la forma de una captura real, anonimizados. Las
columnas `Buyers` y `Sellers` llevan nombres a propósito: la prueba que importa
es que NO salen del parser.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from captura.transacciones import (  # noqa: E402
    AMBOS,
    CASH_PROVISIONAL,
    CASH_SEGUN_MM,
    COMPRA,
    FINANCIADA,
    VENTA,
    normalizar_tasa,
    paginacion,
    parsear_transacciones,
    resumen,
    share_buy_de_transacciones,
)

REALTOR = "ANA PRUEBA"
CAPTURADO = "2026-09-23"

#: 21 columnas separadas por tabulador, en el orden confirmado.
_C = "\t".join


def _fila(fecha, direccion, prestamo, enganche, tipo, tasa, lo, empleador,
          lender, precio, ag_comprador, ag_listing, constructor="",
          title="Chicago Title", proposito="Purchase", plazo="30 yr",
          broker="", lista="", ag_colisting=""):
    return _C([fecha, direccion, constructor, "COMPRADOR N", "VENDEDOR N",
               title, prestamo, enganche, proposito, tipo, tasa, plazo, lo,
               empleador, broker, lender, precio, lista, ag_comprador,
               ag_listing, ag_colisting])


PEGADO = "\n".join([
    # 1 · compra convencional
    _fila("03/12/2026", "5321 S Long Ave, Chicago, IL, 60638",
          "$228,000", "$57,000", "Conventional", "6.625%",
          "Fabian Viera NMLS #123456", "Guaranteed Rate NMLS #2611",
          "Guaranteed Rate", "$285,000", REALTOR, "OTRA AGENTE"),
    # 2 · FHA: el enganche aparente es 1,8% porque el UFMIP va DENTRO
    _fila("01/20/2026", "1440 S 58th Ct, Cicero, IL, 60804",
          "$274,928", "$5,072", "FHA", "6.125%",
          "Brian Dombrowski NMLS #654321", "Guaranteed Rate NMLS #2611",
          "Guaranteed Rate", "$280,000", REALTOR, "OTRA AGENTE"),
    # 3 · cash viejo: 449 días, Model Match ya no va a recibir nada
    _fila("07/01/2025", "8102 S Kedzie Ave, Chicago, IL, 60629",
          "Cash", "Cash", "", "", "", "", "", "$296,000", REALTOR,
          "OTRA AGENTE"),
    # 4 · cash de hace 9 días: TODAVÍA no hay datos de préstamo
    _fila("09/14/2026", "3011 N Nordica Ave, Chicago, IL, 60634",
          "Cash", "Cash", "", "", "", "", "", "$265,000", REALTOR,
          "OTRA AGENTE"),
    # 5 · venta financiada: ella es la listing agent
    _fila("05/05/2026", "719 N 19th Ave, Melrose Park, IL, 60160",
          "$310,000", "$40,000", "Conventional", "5.875%",
          "OTRO LO NMLS #999111", "American Pacific NMLS #1850",
          "American Pacific Mortgage", "$350,000", "OTRA AGENTE", REALTOR),
    # 6 · la tasa en puntos base
    _fila("02/17/2026", "2200 N Lincoln Park W, Chicago, IL, 60614",
          "$472,000", "$118,000", "Non-QM", "762.00%",
          "OTRO LO NMLS #777222", "Angel Oak NMLS #1160240",
          "Angel Oak Mortgage Solutions", "$590,000", REALTOR, "OTRA AGENTE"),
    # 7 · doble punta
    _fila("04/03/2026", "5550 W 63rd St, Chicago, IL, 60638",
          "$8,000", "$213,000", "HE", "8.25%",
          "OTRO LO NMLS #333444", "Peoples Bank NMLS #512138",
          "Peoples Bank", "$220,000", REALTOR, REALTOR),
    # 8 · la suma no cuadra ni de lejos
    _fila("06/11/2026", "412 W 25th Pl, Chicago, IL, 60616",
          "$100,000", "$20,000", "Conventional", "6.00%",
          "OTRO LO NMLS #555666", "Stonehaven NMLS #901",
          "Stonehaven Mortgage", "$400,000", REALTOR, "OTRA AGENTE"),
    "1 - 8 of 8",
])

#: La misma tabla pegada como UNA CELDA POR LÍNEA, que es la otra forma en que
#: el portapapeles la entrega.
PEGADO_EN_LINEAS = "\n".join(
    l.replace("\t", "\n") for l in PEGADO.split("\n"))


def _p(texto=PEGADO):
    return parsear_transacciones(texto, realtor=REALTOR,
                                 capturado_en=CAPTURADO)


# ══ 1 · LO QUE NO SE GUARDA ══════════════════════════════════════════════════

def test_los_nombres_de_compradores_y_vendedores_no_salen_del_parser():
    """ECOA Regulation B: la única forma segura de no inferir origen por
    apellido es no tener el apellido.

    Se leen para ubicar las demás columnas y se tiran en el acto. La prueba
    mira el JSON entero, no los campos de a uno: un campo nuevo que los
    arrastre tiene que hacerla fallar.
    """
    import json

    p = _p()
    entero = json.dumps(p, ensure_ascii=False)
    assert "COMPRADOR N" not in entero
    assert "VENDEDOR N" not in entero
    for f in p["filas"]:
        assert "_compradores" not in f
        assert "_vendedores" not in f


def test_la_direccion_se_reduce_a_ciudad_y_zip():
    """La calle identifica una vivienda. El ZIP alcanza para saber dónde opera."""
    import json

    p = _p()
    assert "5321 S Long Ave" not in json.dumps(p)
    f = p["filas"][0]
    assert f["ciudad"] == "Chicago"
    assert f["estado"] == "IL"
    assert f["zip"] == "60638"
    assert "direccion" not in f and "calle" not in f


# ══ 2 · LA TASA ══════════════════════════════════════════════════════════════

def test_762_por_ciento_es_7_coma_62():
    """No existe una hipoteca residencial al 762%. Tampoco al 25.

    El corte en 20 no es un umbral que se afine: es la distancia entre dos
    órdenes de magnitud.
    """
    assert normalizar_tasa("762.00%") == 7.62
    assert normalizar_tasa("6.625%") == 6.625
    assert normalizar_tasa("5.5") == 5.5
    assert normalizar_tasa("662.50%") == 6.625
    assert normalizar_tasa("") is None
    assert normalizar_tasa("—") is None
    assert normalizar_tasa("0%") is None


def test_la_tasa_normalizada_llega_a_la_fila():
    p = _p()
    non_qm = next(f for f in p["filas"] if f["tipo"] == "Non-QM")
    assert non_qm["tasa"] == 7.62


# ══ 3 · CASH NO QUIERE DECIR EFECTIVO ════════════════════════════════════════

def test_cash_de_hace_nueve_dias_es_provisional():
    """Model Match: «Considered Cash until mortgage details are received».

    Decir «pagó en efectivo» de una compra de hace nueve días es afirmar algo
    que Model Match avisa que todavía no sabe.
    """
    p = _p()
    f = next(x for x in p["filas"] if x["fecha"] == "2026-09-14")
    assert f["estado_prestamo"] == CASH_PROVISIONAL
    assert f["dias_desde_cierre"] == 9
    assert f["recapturar_despues_de"] == "2026-10-19"


def test_cash_de_hace_mas_de_cinco_semanas_es_cash_segun_model_match():
    p = _p()
    f = next(x for x in p["filas"] if x["fecha"] == "2025-07-01")
    assert f["estado_prestamo"] == CASH_SEGUN_MM
    assert f["dias_desde_cierre"] == 449
    assert f["recapturar_despues_de"] is None


def test_sin_fecha_legible_no_se_afirma_cash():
    """El estado que no afirma nada es `provisional`, y ahí se queda."""
    fila = _C(["sin fecha", "x, Chicago, IL, 60638"] + [""] * 19)
    p = parsear_transacciones(fila + "\n1 - 0 of 0", realtor=REALTOR,
                              capturado_en=CAPTURADO)
    # Sin fecha en la columna 1 la línea ni siquiera es una fila.
    assert p["leidas"] == 0
    assert p["lineas_descartadas"] == 1


# ══ 4 · EL LADO SALE DE LA COLUMNA, NO DE UN CONTEO ══════════════════════════

def test_el_lado_sale_de_en_que_columna_esta_su_nombre():
    p = _p()
    por_fecha = {f["fecha"]: f for f in p["filas"]}
    assert por_fecha["2026-03-12"]["lado"] == COMPRA
    assert por_fecha["2026-05-05"]["lado"] == VENTA
    assert por_fecha["2026-04-03"]["lado"] == AMBOS


def test_la_contraparte_es_el_agente_del_otro_lado():
    p = _p()
    f = next(x for x in p["filas"] if x["fecha"] == "2026-03-12")
    assert f["agente_contraparte"] == "OTRA AGENTE"


def test_sin_el_nombre_del_realtor_el_lado_queda_declarado_en_None():
    """No se adivina. Una fila sin lado se cuenta aparte y se dice."""
    p = parsear_transacciones(PEGADO, realtor=None, capturado_en=CAPTURADO)
    assert all(f["lado"] is None for f in p["filas"])
    assert p["sin_lado"] == len(p["filas"])


# ══ 5 · LAS DOS FORMAS DE PEGAR ══════════════════════════════════════════════

def test_una_celda_por_linea_da_lo_mismo_que_con_tabuladores():
    """El portapapeles entrega la tabla de las dos formas según de dónde salga.

    Preguntárselo a quien captura es pedirle que sepa algo que no puede ver.
    """
    a = _p(PEGADO)
    b = _p(PEGADO_EN_LINEAS)
    assert a["leidas"] == b["leidas"] == 8
    assert [f["hash_fila"] for f in a["filas"]] == [
        f["hash_fila"] for f in b["filas"]]


# ══ 6 · LA PAGINACIÓN ════════════════════════════════════════════════════════

def test_el_pie_dice_cuantas_son():
    assert paginacion("1 - 25 of 25")["total"] == 25
    assert paginacion("Showing 1 to 25 of 137")["total"] == 137
    assert paginacion("1-25 of 1,204")["total"] == 1204


def test_si_faltan_paginas_no_se_da_el_calculo_por_completo():
    """25 de 137 y calcular el mix es publicar un porcentaje de una quinta parte."""
    p = parsear_transacciones(PEGADO.replace("1 - 8 of 8", "1 - 8 of 137"),
                              realtor=REALTOR, capturado_en=CAPTURADO)
    assert p["faltan_paginas"] is True
    assert p["completa"] is False
    assert "faltan páginas" in p["aviso"]


def test_sin_pie_no_se_afirma_que_estan_todas():
    """`None` y no `True`: sin el pie no se puede confirmar."""
    p = parsear_transacciones(PEGADO.replace("1 - 8 of 8", ""),
                              realtor=REALTOR, capturado_en=CAPTURADO)
    assert p["completa"] is None
    assert p["faltan_paginas"] is False
    assert "no se encontró el pie" in p["aviso"]


# ══ 7 · LA SUMA COMO CONTROL DE FILA ═════════════════════════════════════════

def test_la_suma_que_no_cuadra_avisa_y_la_fila_se_guarda_igual():
    """Avisa, no descarta: una fila mal leída que se tira desaparece del
    denominador y nadie la echa de menos."""
    p = _p()
    f = next(x for x in p["filas"] if x["fecha"] == "2026-06-11")
    assert f["aviso_suma"] is not None
    assert "-70,0%" in f["aviso_suma"] or "-70.0%" in f["aviso_suma"]
    assert f in p["filas"]


def test_el_fha_con_ufmip_dentro_del_prestamo_no_avisa():
    """El enganche aparente es 1,8%; recalculado es el mínimo de 3,5%.

    No es señal de DPA, y la suma cuadra porque Model Match calcula el Down
    Payment como precio menos préstamo.
    """
    p = _p()
    f = next(x for x in p["filas"] if x["tipo"] == "FHA")
    assert f["aviso_suma"] is None
    assert round(100.0 * f["enganche"] / f["precio"], 1) == 1.8


# ══ 8 · LO QUE SE DERIVA ═════════════════════════════════════════════════════

def test_cash_y_financiadas_se_cuentan_NUNCA_se_restan():
    """Restar del total convierte cualquier fila mal leída en una categoría
    inventada que nadie revisa."""
    r = resumen(_p())
    c = r["compras"]
    assert c["total"] == 7          # 6 compras + la doble punta
    assert c[FINANCIADA] == 5
    assert c[CASH_SEGUN_MM] == 1
    assert c[CASH_PROVISIONAL] == 1
    assert c[FINANCIADA] + c[CASH_SEGUN_MM] + c[CASH_PROVISIONAL] == c["total"]


def test_el_loan_mix_sale_del_grano_y_solo_de_las_financiadas():
    r = resumen(_p())
    assert r["loan_mix_compra"] == {"Conventional": 2, "FHA": 1, "HE": 1,
                                    "Non-QM": 1}


def test_los_lenders_van_por_lado():
    r = resumen(_p())
    assert r["lenders_compra"]["Guaranteed Rate"] == 2
    assert "American Pacific Mortgage" not in r["lenders_compra"]
    assert r["lenders_venta"]["Peoples Bank"] == 1


def test_los_zips_de_compra_contestan_donde_trabaja():
    r = resumen(_p())
    assert r["zips_de_compra"]["60638"] == 2


def test_las_compras_pendientes_traen_su_fecha_de_recaptura():
    """Una de esas compras puede terminar financiada por la casa."""
    r = resumen(_p())
    p = r["pendientes_de_prestamo"]
    assert len(p) == 1
    assert p[0]["fecha"] == "2026-09-14"
    assert p[0]["recapturar_despues_de"] == "2026-10-19"


def test_el_share_buy_sale_del_conteo_de_operaciones():
    """7 compras y 2 ventas contando la doble punta en las dos."""
    r = resumen(_p())
    assert r["ventas"]["total"] == 2
    assert share_buy_de_transacciones(r) == round(7 / 9.0, 4)
    assert share_buy_de_transacciones(None) is None
    assert share_buy_de_transacciones({"compras": {"total": 0},
                                       "ventas": {"total": 0}}) is None


# ══ 9 · LA COMPUERTA, DESDE EL GRANO ═════════════════════════════════════════

CON_LA_CASA = PEGADO.replace(
    "Stonehaven NMLS #901\t\tStonehaven Mortgage",
    "Everett Financial Inc NMLS #2129\t\tSupreme Lending")


def test_una_sola_operacion_con_la_casa_se_ve_en_el_grano():
    p = parsear_transacciones(CON_LA_CASA, realtor=REALTOR,
                              capturado_en=CAPTURADO)
    r = resumen(p)
    assert r["unidades_de_la_casa"] == 1
    assert "Supreme Lending" in r["lenders_de_la_casa"]


def test_el_nmls_2129_basta_aunque_el_nombre_no_diga_supreme():
    fila = _fila("03/12/2026", "1 Main St, Chicago, IL, 60638",
                 "$200,000", "$50,000", "Conventional", "6.5%",
                 "ALGUIEN NMLS #1", "Una Empresa Cualquiera NMLS #2129",
                 "Una Empresa Cualquiera", "$250,000", REALTOR, "OTRA")
    p = parsear_transacciones(fila + "\n1 - 1 of 1", realtor=REALTOR,
                              capturado_en=CAPTURADO)
    assert p["filas"][0]["de_la_casa"] is True


def test_supreme_mortgage_no_es_supreme_lending():
    """El riesgo va en la dirección cara: excluir a quien sí podemos atender."""
    fila = _fila("03/12/2026", "1 Main St, Chicago, IL, 60638",
                 "$200,000", "$50,000", "Conventional", "6.5%",
                 "ALGUIEN NMLS #1", "Supreme Mortgage Corp NMLS #77",
                 "Supreme Mortgage Corp", "$250,000", REALTOR, "OTRA")
    p = parsear_transacciones(fila + "\n1 - 1 of 1", realtor=REALTOR,
                              capturado_en=CAPTURADO)
    assert p["filas"][0]["de_la_casa"] is False


# ══ 10 · EL HASH DE FILA ═════════════════════════════════════════════════════

def test_el_hash_no_cambia_cuando_una_cash_pasa_a_financiada():
    """Es LA MISMA operación actualizada, no una fila nueva.

    Si el monto entrara en la huella, volver a capturar después de que Model
    Match reciba los datos duplicaría la operación y doblaría el denominador.
    """
    cash = _fila("09/14/2026", "3011 N Nordica Ave, Chicago, IL, 60634",
                 "Cash", "Cash", "", "", "", "", "", "$265,000", REALTOR,
                 "OTRA AGENTE")
    luego = _fila("09/14/2026", "3011 N Nordica Ave, Chicago, IL, 60634",
                  "$212,000", "$53,000", "Conventional", "6.25%",
                  "ALGUIEN NMLS #1", "Un Lender NMLS #2", "Un Lender",
                  "$265,000", REALTOR, "OTRA AGENTE")
    a = parsear_transacciones(cash, realtor=REALTOR, capturado_en=CAPTURADO)
    b = parsear_transacciones(luego, realtor=REALTOR, capturado_en=CAPTURADO)
    assert a["filas"][0]["hash_fila"] == b["filas"][0]["hash_fila"]
    assert a["filas"][0]["estado_prestamo"] == CASH_PROVISIONAL
    assert b["filas"][0]["estado_prestamo"] == FINANCIADA


def test_dos_operaciones_distintas_no_comparten_hash():
    p = _p()
    hashes = [f["hash_fila"] for f in p["filas"]]
    assert len(set(hashes)) == len(hashes)


# ══ 11 · LA COMPUERTA LEE EL GRANO ═══════════════════════════════════════════

def _perfil(texto=PEGADO):
    return {"transacciones": parsear_transacciones(
        texto, realtor=REALTOR, capturado_en=CAPTURADO)}


def test_sin_operaciones_con_la_casa_el_veredicto_es_ok_y_cuenta_el_cash():
    """Las «compras sin originador» dejan de ser una ausencia: son cash."""
    from motor.veredicto import OK, puede_contactarse

    v = puede_contactarse(_perfil())
    assert v.estado == OK, v.a_dict()
    e = v.evidencia
    assert e["grano"] == "transacción"
    assert e["compras_totales"] == 7
    assert e["compras_financiadas"] == 5
    assert e["compras_cash_segun_mm"] == 1
    assert e["unidades_de_la_casa"] == 0


def test_una_operacion_con_la_casa_excluye_desde_el_grano():
    from motor.veredicto import EXCLUIDO, puede_contactarse

    v = puede_contactarse(_perfil(CON_LA_CASA))
    assert v.estado == EXCLUIDO, v.a_dict()
    assert "Supreme Lending" in v.motivo
    assert v.evidencia["unidades_de_la_casa"] == 1


def test_con_paginas_de_menos_no_hay_veredicto():
    """25 filas de 137 no son un veredicto: son una quinta parte de uno."""
    from motor.veredicto import PENDIENTE, puede_contactarse

    v = puede_contactarse(_perfil(PEGADO.replace("1 - 8 of 8", "1 - 8 of 137")))
    assert v.estado == PENDIENTE, v.a_dict()
    assert "a medias" in v.motivo


def test_las_compras_pendientes_salen_en_el_veredicto_con_su_fecha():
    """«1 compra del 14 sep todavía sin datos de préstamo», y cuándo volver."""
    from motor.veredicto import puede_contactarse

    v = puede_contactarse(_perfil())
    assert "2026-10-19" in v.motivo
    assert len(v.evidencia["compras_pendientes_de_prestamo"]) == 1


def test_transactions_manda_sobre_el_reparto_del_overview():
    """El Overview es un resumen. Cuando hay grano, el grano.

    El control importa: el mismo perfil SIN Transactions cae en el camino
    viejo, así que la diferencia es la pestaña y no otra cosa.
    """
    from motor.veredicto import OK, PENDIENTE, puede_contactarse

    p = _perfil()
    p["orig_buyer"] = []          # el Overview no trae reparto
    assert puede_contactarse(p).estado == OK
    assert puede_contactarse({"orig_buyer": []}).estado == PENDIENTE


def test_el_share_buy_del_motor_prefiere_el_grano():
    """Side Focus dice «3 buy / 0 sell» y las operaciones dicen 7 de 9."""
    from supabase.correr_motor import share_del_lado_comprador

    p = _perfil()
    p.update({"sf_buy": 3, "sf_sell": 0})
    assert share_del_lado_comprador(p) == round(7 / 9.0, 4)
    # Sin Transactions, Side Focus. No se pierde la fuente: se ordena.
    assert share_del_lado_comprador({"sf_buy": 3, "sf_sell": 0}) == 1.0
    # Y con páginas de menos no se calcula ninguna de las dos desde el grano.
    p2 = _perfil(PEGADO.replace("1 - 8 of 8", "1 - 8 of 137"))
    p2.update({"sf_buy": 3, "sf_sell": 0})
    assert share_del_lado_comprador(p2) == 1.0


def test_sin_transactions_la_ficha_lo_dice_y_no_calcula_cash_por_diferencia():
    """19 compras y 14 con originador: 5 sin identificar, NO 5 cash.

    Restar y llamarlo cash inventa una categoría que nadie midió y que sale con
    la misma cara que una medida. La ficha dice qué falta y qué pegar.
    """
    from motor.veredicto import OK, puede_contactarse

    v = puede_contactarse({
        "buyer_units": 19.0,
        "orig_buyer": [{"nombre": "Originador A", "empresa": "Chase",
                        "unidades": 14, "share": 100.0}]})
    assert v.estado == OK
    assert v.evidencia["falta_transactions"] is True
    assert v.evidencia["grano"] == "resumen del Overview"
    assert v.evidencia["compras_sin_originador_identificado"] == 5
    assert "Transactions" in v.motivo
    # Y en ningún sitio se dice que esas 5 fueron cash.
    assert "cash" not in v.evidencia
    assert "compras_cash_segun_mm" not in v.evidencia


def test_con_transactions_el_veredicto_deja_de_decir_que_falta():
    """El control: el aviso tiene que APAGARSE cuando el dato llega."""
    from motor.veredicto import puede_contactarse

    v = puede_contactarse(_perfil())
    assert v.evidencia.get("falta_transactions") is None
    assert v.evidencia["grano"] == "transacción"


# ══ 12 · LA GUARDA REDUNDANTE ANTES DE ESCRIBIR ══════════════════════════════

def test_las_filas_que_van_a_la_base_no_llevan_nombres_ni_calle():
    from api.rutas import _filas_de_transacciones

    fs = _filas_de_transacciones(_p(), "r-1", "lote-1",
                                 "2026-09-23T00:00:00Z")
    assert len(fs) == 8
    for f in fs:
        assert "_compradores" not in f and "_vendedores" not in f
        assert "direccion" not in f and "calle" not in f
        assert f["realtor_id"] == "r-1"
    assert fs[0]["hash_fila"]


def test_un_campo_prohibido_revienta_en_vez_de_filtrarse_en_silencio():
    """Un filtro callado deja el mismo bug vivo para el campo siguiente.

    Es la guarda redundante: el parser ya no los devuelve y la lista blanca ya
    los dejaría fuera. Esta es la tercera vuelta, y es la que se ve.
    """
    from api.rutas import _filas_de_transacciones

    p = _p()
    p["filas"][0]["buyers"] = "ALGUIEN"
    try:
        _filas_de_transacciones(p, "r-1", "lote-1", "2026-09-23T00:00:00Z")
    except ValueError as exc:
        assert "buyers" in str(exc)
        assert "ECOA" in str(exc)
        return
    raise AssertionError("escribió una fila con el nombre del comprador")


# ══ 13 · LO QUE EL OVERVIEW NO LEÍA ══════════════════════════════════════════

CABECERA = """Agents
ALGUIEN DE PRUEBA
Office: (888) 584-9427
Direct: (312) 555-0134
Side Focus
Buyer Heavy
18 buy / 7 sell · 7 buyer · 2 seller LOs
Buyer Units 18
Una Oficina
100 Main St
Chicago IL 60638
"""


def test_el_telefono_directo_se_lee_y_no_pisa_al_de_la_oficina():
    """Llamar a la centralita y llamarle a él son dos cosas distintas."""
    from captura.parser_mm import parsear_perfil

    c = parsear_perfil(CABECERA)["contacto"]
    assert c["telefono_oficina"] == "(888) 584-9427"
    assert c["telefono_directo"] == "(312) 555-0134"
    assert c["telefono_directo_e164"] == "+13125550134"


def test_el_telefono_directo_llega_a_contactos():
    from api.rutas import _contactos_de
    from captura.parser_mm import parsear_perfil

    fs = _contactos_de(parsear_perfil(CABECERA), "r-1", "l-1", "2026-09-23")
    telefonos = [f["valor"] for f in fs if f["canal"] == "telefono"]
    assert "+13125550134" in telefonos
    assert "+18885849427" in telefonos


def test_los_LOs_por_lado_se_leen_de_la_cabecera():
    """Es el denominador de Originators: con cuántos de cada lado hay relación."""
    from captura.parser_mm import parsear_perfil

    p = parsear_perfil(CABECERA)
    assert p["los_buyer"] == 7
    assert p["los_seller"] == 2
    assert (p["sf_buy"], p["sf_sell"]) == (18, 7)


# ══ 14 · EL CAMINO COMPLETO, POR DONDE PASA DE VERDAD ════════════════════════

def test_la_caja_de_transactions_entra_como_las_demas():
    from captura.cajas import LEIDO, SIN_PEGAR, cajas_desde, resumen_de_cajas

    cajas = cajas_desde({"cajas": [
        {"clave": "trx", "tipo": "transacciones", "etiqueta": "Transactions",
         "texto": PEGADO},
        {"clave": "lend", "tipo": "lenders", "etiqueta": "Lenders"}]})
    assert cajas[0].estado == LEIDO
    assert cajas[1].estado == SIN_PEGAR
    # Y una caja sin pegar sale en «faltan», que es lo que la ficha muestra.
    assert "Transactions" not in resumen_de_cajas(cajas)["faltan"]
    assert "Lenders" in resumen_de_cajas(cajas)["faltan"]


def test_unir_perfiles_lleva_las_transacciones_hasta_el_veredicto():
    """El camino real: la re-evaluación solo mira `parseado.perfil`.

    Guardar el parseado en otra llave del jsonb lo dejaría en la base y fuera
    del motor, que es como este proyecto ya perdió Instagram durante semanas.
    """
    from captura.parser_mm import unir_perfiles
    from motor.veredicto import OK, puede_contactarse

    del_overview = {"nombre": "ALGUIEN", "buyer_units": 18.0, "orig_buyer": []}
    de_transacciones = {"transacciones": parsear_transacciones(
        PEGADO, realtor=REALTOR, capturado_en=CAPTURADO)}

    unido = unir_perfiles([del_overview, de_transacciones])
    assert unido["buyer_units"] == 18.0
    assert unido["transacciones"]["leidas"] == 8
    v = puede_contactarse(unido)
    assert v.estado == OK
    assert v.evidencia["grano"] == "transacción"


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
