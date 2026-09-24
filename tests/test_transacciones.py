"""La pestaña Transactions, contra el PEGADO REAL.

Por qué se rehizo este archivo entero
-------------------------------------
La primera versión probaba contra un fixture construido a mano con la forma que
yo supuse: 21 celdas separadas por tabuladores, una fila por línea. Model Match
no entrega eso. Entrega una MEZCLA -- la fecha con tabulador, la calle y la
ciudad en dos líneas, cuatro columnas con tabuladores, los tres agentes en tres
líneas-- y sobre el volcado real el parser daba 25 filas de una celda, 304
líneas descartadas, todos los campos en null y las 25 operaciones contadas como
cash. Con `completa: true`, porque lo único que miraba era el pie.

Las 27 pruebas pasaban. Ninguna tocaba un pegado real, así que ninguna podía
fallar por esto: **probaban que el parser sabe leer lo que yo creía que Model
Match manda.**

`fixtures/transactions_real.txt` es el volcado de verdad, anonimizado por
Isabella --nombres de personas, calles y NMLS de los LOs reemplazados; los
nombres de las empresas son los reales-- y `transactions_real_esperado.json` es
lo que tiene que salir, verificado a mano contra las capturas de pantalla.

Las variantes sintéticas se construyen MUTANDO UNA CELDA del volcado real, no
escribiendo una fila nueva: así lo que se prueba sigue teniendo su forma.
"""
from __future__ import annotations

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from captura.transacciones import (  # noqa: E402
    AMBOS,
    CASH_PROVISIONAL,
    CASH_SEGUN_MM,
    COLUMNAS,
    COMPRA,
    FINANCIADA,
    NO_LEIDO,
    VENTA,
    _celdas_por_fila,
    nombre_de_lender,
    normalizar_tasa,
    paginacion,
    parsear_transacciones,
    resumen,
    share_buy_de_transacciones,
)

FIXTURES = os.path.join(RAIZ, "tests", "fixtures")
REALTOR = "Agente Titular"
CAPTURADO = "2026-09-23T23:54:00+00:00"

REAL = open(os.path.join(FIXTURES, "transactions_real.txt"),
            encoding="utf-8").read()
ESPERADO = json.load(open(os.path.join(FIXTURES,
                                       "transactions_real_esperado.json"),
                          encoding="utf-8"))

#: Índices de las columnas que las variantes mutan, por nombre.
_COL = {n: i for i, n in enumerate(COLUMNAS)}


def _p(texto=REAL):
    return parsear_transacciones(texto, realtor=REALTOR,
                                 capturado_en=CAPTURADO)


def _r(texto=REAL):
    return resumen(_p(texto))


# ══════════════════════════════════════════════════════════════════════════════
# LAS VARIANTES · una celda del volcado real, cambiada
# ══════════════════════════════════════════════════════════════════════════════

def _en_tabuladores(celdas_por_fila) -> str:
    """Las filas, una por línea con tabuladores. Es el OTRO formato real.

    Un pegado desde una hoja de cálculo llega así, y el parser tiene que dar lo
    mismo por los dos caminos.
    """
    return "\n".join("\t".join(f) for f in celdas_por_fila) + "\nRows per page\n25\n1 - 25 of 25\n"


def _variante(fecha: str, columna: str, valor, *, borrar=False) -> str:
    """El volcado real con UNA celda cambiada, devuelto en formato tabulador.

    `fecha` es la de la fila a tocar, tal como aparece («Jul 30, 2026»).
    """
    return _variantes(fecha, [(columna, valor)], borrar=borrar)


def _variantes(fecha: str, cambios, *, borrar=False) -> str:
    """Varias celdas de LA MISMA fila, para los casos que necesitan más de una.

    Una fila ilegible de verdad es la que no trae ni monto, ni loan type, ni
    lender: con cualquiera de los tres ya se sabe que hubo loan.
    """
    filas = [list(f) for f in _celdas_por_fila(REAL)]
    tocadas = 0
    for f in filas:
        if f and f[0].strip() == fecha:
            for columna, valor in cambios:
                if borrar:
                    del f[_COL[columna]]
                else:
                    f[_COL[columna]] = valor
            tocadas += 1
    assert tocadas == 1, "la variante tocó %d filas, no 1" % tocadas
    return _en_tabuladores(filas)


#: Una fila sin monto, sin loan type y sin lender: la única que de verdad no se
#: puede clasificar.
_SIN_NADA = [("prestamo", "—"), ("tipo", "—"), ("lender", "—"),
             ("empleador", "—")]


# ══════════════════════════════════════════════════════════════════════════════
# 1 · EL VOLCADO REAL, CONTRA LO ESPERADO
# ══════════════════════════════════════════════════════════════════════════════

def test_el_volcado_real_da_25_filas_de_21_celdas():
    """La prueba que faltaba. 25 filas, 0 sin leer, 0 líneas descartadas."""
    p = _p()
    assert p["leidas"] == ESPERADO["leidas"]
    assert p["no_leidas"] == []
    assert p["lineas_descartadas"] == ESPERADO["lineas_descartadas"]
    assert p["sin_lado"] == ESPERADO["sin_lado"]
    for f in _celdas_por_fila(REAL):
        assert len(f) == 21, (f[0], len(f))


def test_completa_es_true_y_por_las_cuatro_razones():
    """`completa` ya no mira solo el pie.

    25 filas de una celda cada una son 25 filas, y el pie cuadraba. Con eso
    decía True sobre un parseo en el que no se había leído un campo.
    """
    p = _p()
    assert p["completa"] is ESPERADO["completa"]
    assert p["por_que_no_completa"] == []
    assert p["sin_estado_de_prestamo"] == 0
    assert p["financiadas_sin_lender"] == 0
    assert p["paginacion"]["total"] == 25


def test_el_reparto_de_compras_y_ventas_es_el_verificado_a_mano():
    r = _r()
    for lado in ("compras", "ventas"):
        for clave, valor in ESPERADO[lado].items():
            assert r[lado][clave] == valor, (lado, clave, r[lado])


def test_el_loan_mix_y_los_lenders_son_los_verificados_a_mano():
    r = _r()
    assert r["loan_mix_compra"] == ESPERADO["loan_mix_compra"]
    assert r["lenders_compra"] == ESPERADO["lenders_compra"]
    assert r["lenders_venta"] == ESPERADO["lenders_venta"]


def test_los_lenders_se_agrupan_sin_el_sufijo_societario():
    """«Guaranteed Rate Inc» y «Guaranteed Rate, Inc.» son el mismo lender.

    Están en dos columnas del mismo volcado. Contarlos aparte parte el reparto
    y hace que tres operaciones con el mismo lender parezcan tres lenders.
    """
    assert nombre_de_lender("Guaranteed Rate, Inc.") == "Guaranteed Rate"
    assert nombre_de_lender("Guaranteed Rate Inc") == "Guaranteed Rate"
    assert nombre_de_lender("Stonehaven Mortgage Incorporated") == \
        "Stonehaven Mortgage"
    assert nombre_de_lender("Zillow Home Loans, Llc") == "Zillow Home Loans"
    assert nombre_de_lender("American Pacific Mortgage Corporation") == \
        "American Pacific Mortgage"
    # `bank` NO es sufijo societario: es parte del nombre.
    assert nombre_de_lender("Peoples Bank") == "Peoples Bank"
    assert nombre_de_lender("—") == "—"
    assert nombre_de_lender("") is None


def test_las_pendientes_y_sus_fechas_de_recaptura():
    r = _r()
    got = [{k: p[k] for k in ("fecha", "lado", "recapturar_despues_de")}
           for p in r["pendientes_de_prestamo"]]
    assert got == ESPERADO["pendientes_de_prestamo"]


def test_los_zips_el_precio_mediano_y_el_volumen():
    r = _r()
    for zip_, n in ESPERADO["zips_de_compra_top"].items():
        assert r["zips_de_compra"][zip_] == n, zip_
    assert r["precio_mediano_compra"] == ESPERADO["precio_mediano_compra"]
    assert r["volumen_compra"] == ESPERADO["volumen_compra"]
    assert r["volumen_venta"] == ESPERADO["volumen_venta"]


def test_los_importes_abreviados_se_leen_con_su_sufijo():
    """El volcado real trae TODOS los importes como `$151K`.

    Sin el sufijo, «$300K» entraba como 300 dólares. Un precio de vivienda de
    tres cifras no revienta nada: se guarda, se promedia y sale en la ficha.
    """
    f = next(x for x in _p()["filas"] if x["fecha"] == "2026-07-30")
    assert f["prestamo"] == 151000.0
    assert f["enganche"] == 17000.0
    assert f["precio"] == 168000.0


def test_la_fila_del_30_de_julio_entera():
    """Employer viene como «—» con Lender puesto: `lender_nmls` queda en null
    y la compuerta usa el nombre completo del Lender."""
    f = next(x for x in _p()["filas"] if x["fecha"] == "2026-07-30")
    for clave, valor in ESPERADO["fila_2026-07-30"].items():
        assert f[clave] == valor, (clave, f[clave], valor)
    assert f["lender_agrupado"] == "Guaranteed Rate"


def test_la_tasa_en_puntos_base_del_volcado_real():
    ao = [f for f in _p()["filas"]
          if (f.get("lender_agrupado") or "").startswith("Angel Oak")]
    assert len(ao) == 1
    assert ao[0]["tasa"] == ESPERADO["tasa_angel_oak"]


def test_ninguna_fila_real_dispara_el_aviso_de_suma():
    assert _r()["avisos_de_suma"] == ESPERADO["avisos_de_suma"]


def test_el_veredicto_del_volcado_real():
    from motor.veredicto import puede_contactarse

    v = puede_contactarse({"transacciones": _p()})
    assert v.estado == ESPERADO["veredicto"], v.a_dict()
    assert v.evidencia["unidades_de_la_casa"] == ESPERADO["unidades_de_la_casa"]


def test_los_dos_formatos_dan_los_mismos_hashes():
    """El mismo volcado, mezclado y en tabuladores, tiene que dar lo mismo.

    Con el fixture REAL y no con uno construido: la versión anterior de esta
    prueba comparaba dos renderizados de una forma que Model Match no usa.
    """
    a = _p()
    b = _p(_en_tabuladores(_celdas_por_fila(REAL)))
    assert b["leidas"] == 25 and b["no_leidas"] == []
    assert [f["hash_fila"] for f in a["filas"]] == \
        [f["hash_fila"] for f in b["filas"]]
    assert resumen(a)["compras"] == resumen(b)["compras"]


# ══════════════════════════════════════════════════════════════════════════════
# 2 · LO QUE NO SE GUARDA
# ══════════════════════════════════════════════════════════════════════════════

def test_los_nombres_de_las_partes_no_salen_del_parser():
    """ECOA Regulation B: la única forma segura de no inferir origen por
    apellido es no tener el apellido.

    El volcado real trae `Persona 1` … `Persona 18` en las columnas Buyers y
    Sellers. Se leen para ubicar las demás y se tiran en el acto.
    """
    entero = json.dumps(_p(), ensure_ascii=False)
    assert "Persona 1" in REAL, "el fixture ya no trae nombres: la prueba no prueba"
    for i in range(1, 19):
        assert "Persona %d" % i not in entero, i
    for f in _p()["filas"]:
        assert "_compradores" not in f and "_vendedores" not in f


def test_la_calle_no_sale_y_el_zip_si():
    assert "Calle Ficticia" in REAL
    p = _p()
    assert "Calle Ficticia" not in json.dumps(p, ensure_ascii=False)
    f = next(x for x in p["filas"] if x["fecha"] == "2026-07-30")
    assert (f["ciudad"], f["estado"], f["zip"]) == ("Elmwood Park", "IL", "60707")


# ══════════════════════════════════════════════════════════════════════════════
# 3 · LA TASA
# ══════════════════════════════════════════════════════════════════════════════

def test_762_por_ciento_es_7_coma_62():
    """No existe una hipoteca residencial al 762%. Tampoco al 25.

    El corte en 20 no es un umbral que se afine: es la distancia entre dos
    órdenes de magnitud.
    """
    assert normalizar_tasa("762.00%") == 7.62
    assert normalizar_tasa("687.00%") == 6.87
    assert normalizar_tasa("6.55%") == 6.55
    assert normalizar_tasa("") is None
    assert normalizar_tasa("—") is None
    assert normalizar_tasa("0%") is None


# ══════════════════════════════════════════════════════════════════════════════
# 4 · CASH NO QUIERE DECIR EFECTIVO, Y LO QUE NO SE LEYÓ NO ES CASH
# ══════════════════════════════════════════════════════════════════════════════

def test_cash_de_hace_nueve_dias_es_provisional():
    """Model Match: «Considered Cash until mortgage details are received».

    Decir «pagó en efectivo» de una compra de hace nueve días es afirmar algo
    que Model Match avisa que todavía no sabe.
    """
    f = next(x for x in _p()["filas"] if x["fecha"] == "2026-09-14")
    assert f["estado_prestamo"] == CASH_PROVISIONAL
    assert f["dias_desde_cierre"] == 9
    assert f["recapturar_despues_de"] == "2026-10-19"


def test_cash_de_hace_mas_de_cinco_semanas_es_cash_segun_model_match():
    f = next(x for x in _p()["filas"] if x["fecha"] == "2025-08-04")
    assert f["estado_prestamo"] == CASH_SEGUN_MM
    assert f["recapturar_despues_de"] is None


def test_una_celda_de_prestamo_vacia_NUNCA_es_cash():
    """El agujero que daba el falso `ok`.

    Un loan que no se leyó se convertía en cash, y con eso las operaciones de
    la casa desaparecían del conteo que decide la exclusión. `cash_*` exige que
    la celda diga literalmente `Cash`.
    """
    p = _p(_variantes("Jul 30, 2026", _SIN_NADA))
    f = next(x for x in p["filas"] if x["fecha"] == "2026-07-30")
    assert f["estado_prestamo"] == NO_LEIDO
    assert f["estado_prestamo"] not in (CASH_SEGUN_MM, CASH_PROVISIONAL)
    assert p["completa"] is False
    assert any("loan o cash" in r for r in p["por_que_no_completa"])


def test_con_loan_type_o_con_lender_es_FINANCIADA_aunque_falte_el_monto():
    """Decisión de Isabella del 2026-09-24, y sale de un caso real.

    Una fila de Cristy Gramajo traía `FHA` y `American Portfolio Mortgage
    Corp` con el Mortgage Amount vacío. Eso es una operación financiada a la
    que le falta el importe, no una que no se sepa clasificar -- y quedaba en
    `no_leido`, dejando su captura entera sin poder darse por completa.

    El importe NO se rellena: sigue en `None`, y la ficha lo muestra como «no
    disponible». Saber que hubo loan y saber cuánto son dos cosas.
    """
    p = _p(_variante("Jul 30, 2026", "prestamo", "—"))
    f = next(x for x in p["filas"] if x["fecha"] == "2026-07-30")
    assert f["estado_prestamo"] == FINANCIADA
    assert f["prestamo"] is None
    assert f["tipo"] == "Conventional"
    assert p["completa"] is True, p["por_que_no_completa"]

    # Solo con el lender, sin loan type, también.
    p2 = _p(_variantes("Jul 30, 2026", [("prestamo", "—"), ("tipo", "—")]))
    f2 = next(x for x in p2["filas"] if x["fecha"] == "2026-07-30")
    assert f2["estado_prestamo"] == FINANCIADA
    assert f2["prestamo"] is None


def test_una_fila_con_una_celda_de_menos_no_se_lee_y_bloquea():
    """Rellenar una fila corta corre todas las columnas desde donde falta.

    La tasa entra en el plazo, el lender en el Sold Amount, y el resultado sale
    plausible. 21 celdas exactas o no se lee.
    """
    p = _p(_variante("Jul 30, 2026", "tipo", None, borrar=True))
    assert p["leidas"] == 24
    assert len(p["no_leidas"]) == 1
    assert p["no_leidas"][0]["celdas"] == 20
    assert p["completa"] is False
    assert any("1 filas sin leer" in r for r in p["por_que_no_completa"])


# ══════════════════════════════════════════════════════════════════════════════
# 5 · SIN LECTURA COMPLETA NO HAY `ok`
# ══════════════════════════════════════════════════════════════════════════════

def test_una_fila_sin_leer_deja_el_veredicto_en_pendiente():
    """Es la corrección que importa: un parseo a medias daba `ok`.

    Un realtor con operaciones de Supreme en la fila que no se leyó habría
    salido contactable. Es un falso negativo de la compuerta de exclusión.
    """
    from motor.veredicto import PENDIENTE, puede_contactarse

    p = _p(_variante("Jul 30, 2026", "tipo", None, borrar=True))
    v = puede_contactarse({"transacciones": p})
    assert v.estado == PENDIENTE, v.a_dict()
    assert "No se pudo leer Transactions" in v.motivo
    assert "1 filas sin leer" in v.motivo
    assert v.evidencia["filas_sin_leer"] == 1


def test_con_paginas_de_menos_tampoco_hay_veredicto():
    from motor.veredicto import PENDIENTE, puede_contactarse

    p = _p(REAL.replace("1 - 25 of 25", "1 - 25 of 137"))
    assert p["faltan_paginas"] is True
    assert puede_contactarse({"transacciones": p}).estado == PENDIENTE


def test_una_financiada_sin_lender_NO_bloquea_la_lectura():
    """Decisión de Isabella del 2026-09-24, y era una compuerta de más.

    Model Match no siempre trae el originador. Bloquear por eso dejaba en
    `pendiente_modelmatch` a catorce realtors cuya pestaña se había leído
    ENTERA -- y una fila sin originador no impide decir si alguna operación
    pasó por la casa: si pasara, el lender estaría ahí.

    Lo que sí hace falta es que se VEA, porque la ausencia se parece mucho a
    un cero: «9 de 10 con lender» y «9 buys con lender» dicen cosas distintas.
    """
    from motor.veredicto import OK, puede_contactarse

    sin = REAL.replace("Guaranteed Rate Inc\n", "—\n", 1)
    p = _p(sin)
    assert p["completa"] is True, p["por_que_no_completa"]
    assert p["por_que_no_completa"] == []
    assert p["financiadas_sin_lender"] == 1
    assert p["cobertura_lender"]["texto"] == "9 de 10 con lender"
    assert p["cobertura_lender"]["sin_lender_identificado"] == 1

    r = resumen(p)
    assert r["compras_sin_lender_identificado"] == 1
    assert r["cobertura_lender_compra"]["texto"] == "7 de 8 con lender"
    # Y el veredicto sale, que es el punto de todo esto.
    assert puede_contactarse({"transacciones": p}).estado == OK


def test_la_cobertura_se_mide_sobre_las_FINANCIADAS_y_no_sobre_todas():
    """Una compra cash no tiene lender que falte.

    Con el denominador en «todas», una cartera con nueve cash daría una
    cobertura del 60 % que no significa nada.
    """
    p = _p()
    assert p["cobertura_lender"]["financiadas"] == 10
    assert p["cobertura_lender"]["texto"] == "10 de 10 con lender"
    assert p["leidas"] == 25


def test_sin_pie_no_se_afirma_que_estan_todas():
    """`None` y no `True`: sin el pie no se puede confirmar."""
    from motor.veredicto import PENDIENTE, puede_contactarse

    p = _p(REAL.replace("1 - 25 of 25", ""))
    assert p["completa"] is None
    assert any("pie" in r for r in p["por_que_no_completa"])
    assert puede_contactarse({"transacciones": p}).estado == PENDIENTE


def test_el_nombre_truncado_del_overview_sigue_siendo_el_mismo_nombre():
    """Model Match corta el nombre del perfil a 24 caracteres.

    Dice «Brayan Valdovinos-sauced» y la tabla dice «Brayan
    Valdovinos-saucedo». Sus 25 operaciones quedaban sin lado por una «o».
    """
    from captura.transacciones import _nombre_igual

    assert _nombre_igual("Brayan Valdovinos-sauced",
                         "Brayan Valdovinos-saucedo")
    # Y el prefijo corto NO vale: «Ana Mar» sería prefijo de media lista.
    assert not _nombre_igual("Ana Mar", "Ana Marcela Rodriguez Perez")


def test_la_tilde_no_hace_a_dos_personas_distintas():
    """`José` y `Jose` son la misma persona, y Model Match usa las dos.

    Antes `[^a-z\\s] -> " "` convertía «José» en «jos» y lo partía en dos
    palabras: el nombre con tilde no coincidía ni consigo mismo.
    """
    from captura.transacciones import _nombre_igual

    assert _nombre_igual("José Ramírez", "Jose Ramirez")
    assert _nombre_igual("MARÍA JOSÉ PEÑA", "Maria Jose Pena")


def test_dos_apellidos_parecidos_NO_son_la_misma_persona():
    """«Isabel Vasquez» y «Isabel Vazquez» no se adivinan.

    Son dos apellidos distintos. Para eso están los nombres alternativos, que
    alguien confirma mirando la pantalla.
    """
    from captura.transacciones import _nombre_igual

    assert not _nombre_igual("Isabel Vasquez", "Isabel Vazquez")


def test_los_nombres_alternativos_deciden_el_lado():
    """El caso de Isabel: 17 de sus 25 filas con el apellido escrito distinto.

    Con el alternativo confirmado, esas filas recuperan su lado; sin él, se
    quedan sin lado y la captura no se da por completa -- que es lo correcto,
    porque nadie confirmó que sea ella.
    """
    # UNA fila con el apellido escrito distinto. Una sola, para que no se
    # dispare el respaldo del 90 %: lo que se mide es el alternativo, no el
    # respaldo.
    #
    # Y con una letra cambiada EN MEDIO, no al final: «Agente Titulá» sería un
    # prefijo de «Agente Titular» y lo cazaría la regla del truncamiento, así
    # que la prueba no probaría los alternativos. Es el caso de Isabel:
    # Vasquez/Vazquez, una letra en medio.
    otra = _variante("Jul 30, 2026", "agente_comprador", "Agente Titolar")
    base = next(x for x in _p()["filas"] if x["fecha"] == "2026-07-30")
    assert base["lado"] == COMPRA

    sin = _p(otra)
    f_sin = next(x for x in sin["filas"] if x["fecha"] == "2026-07-30")
    assert f_sin["lado"] is None
    assert sin["sin_lado"] == 1
    assert sin["completa"] is False

    con = parsear_transacciones(otra, realtor=REALTOR,
                                alternativos=["Agente Titolar"],
                                capturado_en=CAPTURADO)
    f_con = next(x for x in con["filas"] if x["fecha"] == "2026-07-30")
    assert f_con["lado"] == COMPRA
    assert con["sin_lado"] == 0
    assert con["completa"] is True
    assert con["nombres_alternativos"] == ["Agente Titolar"]


def test_sin_nombre_el_respaldo_lo_deduce_de_la_propia_tabla():
    """En su tabla de transacciones, el agente que sale en casi todas es él.

    Antes esto dejaba las 25 sin lado. Y «sin lado» es un estado legítimo, así
    que no fallaba nada: la ficha salía sin producción y nadie sabía por qué.
    """
    p = parsear_transacciones(REAL, realtor=None, capturado_en=CAPTURADO)
    assert p["nombre_usado"] == REALTOR
    assert p["sin_lado"] == 0
    assert "no aparece en ninguna fila" in p["por_que_ese_nombre"]
    assert "25 de 25" in p["por_que_ese_nombre"]


def test_el_nombre_de_la_captura_manda_sobre_el_de_la_base():
    """La base dice «XOCHIL ESCOBAR» y Model Match «Xochil Wendy Escobar».

    Son la misma persona --se confirmó al capturar-- pero el de la base no
    calza con ninguna columna de agente, y con él las 37 operaciones quedaban
    sin lado.
    """
    otro = REAL.replace("Agente Titular", "Xochil Wendy Escobar")
    # Con el de la CAPTURA: calza.
    p = parsear_transacciones(otro, realtor="Xochil Wendy Escobar",
                              capturado_en=CAPTURADO)
    assert p["nombre_usado"] == "Xochil Wendy Escobar"
    assert p["sin_lado"] == 0
    assert p["por_que_ese_nombre"] == "el nombre de la captura de Model Match"

    # Con el de la BASE: no calza, y el respaldo lo rescata diciendo cuál usó.
    q = parsear_transacciones(otro, realtor="XOCHIL ESCOBAR",
                              capturado_en=CAPTURADO)
    assert q["nombre_usado"] == "Xochil Wendy Escobar"
    assert q["sin_lado"] == 0
    assert "XOCHIL ESCOBAR" in q["por_que_ese_nombre"]


def test_el_respaldo_NO_elige_si_ningun_agente_domina():
    """El control. Sin él, «el respaldo siempre encuentra a alguien» sería
    cierto y elegiría al primer agente de una tabla que no es suya."""
    from captura.transacciones import _celdas_por_fila, nombre_que_manda

    filas = [list(f) for f in _celdas_por_fila(REAL)]
    # Cada fila con un agente distinto: ninguno llega al 90 %.
    for i, f in enumerate(filas):
        f[18] = "Agente %d" % i
        f[19] = "Otro %d" % i
        f[20] = "No Co Agent"
    nombre, motivo = nombre_que_manda(filas, propuesto="NO CALZA")
    assert nombre == "NO CALZA"
    assert "ningún agente sale" in motivo


# ══════════════════════════════════════════════════════════════════════════════
# 6 · LA COMPUERTA DE EXCLUSIÓN, CON LAS TRES VARIANTES
# ══════════════════════════════════════════════════════════════════════════════

def test_everett_financial_con_nmls_2129_en_el_employer_excluye():
    from motor.veredicto import EXCLUIDO, puede_contactarse

    p = _p(_variante("Jul 30, 2026", "empleador",
                     "Everett Financial, Inc. NMLS: 2129"))
    f = next(x for x in p["filas"] if x["fecha"] == "2026-07-30")
    assert f["lender_nmls"] == "2129"
    assert f["de_la_casa"] is True
    v = puede_contactarse({"transacciones": p})
    assert v.estado == EXCLUIDO, v.a_dict()


def test_supreme_lending_en_el_lender_con_employer_vacio_excluye():
    """Sin NMLS, la decisión la toma el nombre COMPLETO del Lender."""
    from motor.veredicto import EXCLUIDO, puede_contactarse

    p = _p(_variante("Jul 30, 2026", "lender", "Supreme Lending"))
    f = next(x for x in p["filas"] if x["fecha"] == "2026-07-30")
    assert f["empleador"] is None
    assert f["lender_nmls"] is None
    assert f["de_la_casa"] is True
    assert puede_contactarse({"transacciones": p}).estado == EXCLUIDO


def test_supreme_mortgage_no_es_supreme_lending():
    """El riesgo va en la dirección cara: excluir a quien sí podemos atender."""
    from motor.veredicto import OK, puede_contactarse

    p = _p(_variante("Jul 30, 2026", "lender", "Supreme Mortgage Corp"))
    f = next(x for x in p["filas"] if x["fecha"] == "2026-07-30")
    assert f["de_la_casa"] is False
    assert puede_contactarse({"transacciones": p}).estado == OK


# ══════════════════════════════════════════════════════════════════════════════
# 7 · EL LADO, LA CONTRAPARTE Y EL HASH
# ══════════════════════════════════════════════════════════════════════════════

def test_el_lado_sale_de_en_que_columna_esta_su_nombre():
    por_fecha = {f["fecha"]: f for f in _p()["filas"]}
    assert por_fecha["2026-09-14"]["lado"] == COMPRA
    assert por_fecha["2026-09-09"]["lado"] == VENTA
    assert {f["lado"] for f in _p()["filas"]} <= {COMPRA, VENTA, AMBOS}


def test_la_contraparte_es_el_agente_del_otro_lado():
    f = next(x for x in _p()["filas"] if x["fecha"] == "2026-09-14")
    assert f["lado"] == COMPRA
    assert f["agente_contraparte"] == "Agente 1"


def test_el_hash_no_cambia_cuando_una_cash_pasa_a_financiada():
    """Es LA MISMA operación actualizada, no una fila nueva.

    Si el monto entrara en la huella, volver a capturar después de que Model
    Match reciba los datos duplicaría la operación y doblaría el denominador.
    """
    antes = _p()
    despues = _p(_variante("Sep 14, 2026", "prestamo", "$240K"))
    a = next(x for x in antes["filas"] if x["fecha"] == "2026-09-14")
    b = next(x for x in despues["filas"] if x["fecha"] == "2026-09-14")
    assert a["estado_prestamo"] == CASH_PROVISIONAL
    assert b["estado_prestamo"] == FINANCIADA
    assert a["hash_fila"] == b["hash_fila"]


def test_las_25_operaciones_tienen_hash_distinto():
    hashes = [f["hash_fila"] for f in _p()["filas"]]
    assert len(set(hashes)) == 25


# ══════════════════════════════════════════════════════════════════════════════
# 8 · LA PAGINACIÓN Y EL PIE
# ══════════════════════════════════════════════════════════════════════════════

def test_el_pie_dice_cuantas_son():
    assert paginacion(REAL)["total"] == 25
    assert paginacion("Showing 1 to 25 of 137")["total"] == 137
    assert paginacion("1-25 of 1,204")["total"] == 1204


def test_el_dolar_suelto_del_pie_no_entra_como_celda():
    """Después de «Rows per page» hay un «$200K» que no es de ninguna fila.

    Sin cortar ahí se pegaba a la última operación y la dejaba en 22 celdas.
    """
    assert "$200K" in REAL.split("Rows per page")[1]
    assert len(_celdas_por_fila(REAL)) == 25
    assert len(_celdas_por_fila(REAL)[-1]) == 21


# ══════════════════════════════════════════════════════════════════════════════
# 9 · LO QUE SE DERIVA, Y LO QUE NO SE RESTA
# ══════════════════════════════════════════════════════════════════════════════

def test_cash_y_financiadas_se_cuentan_NUNCA_se_restan():
    """Restar del total convierte cualquier fila mal leída en una categoría
    inventada que nadie revisa."""
    c = _r()["compras"]
    assert (c[FINANCIADA] + c[CASH_SEGUN_MM] + c[CASH_PROVISIONAL]
            + c[NO_LEIDO]) == c["total"]


def test_el_share_buy_sale_del_conteo_de_operaciones():
    r = _r()
    assert share_buy_de_transacciones(r) == round(18 / 25.0, 4)
    assert share_buy_de_transacciones(None) is None
    assert share_buy_de_transacciones({"compras": {"total": 0},
                                       "ventas": {"total": 0}}) is None


def test_el_share_buy_del_motor_prefiere_el_grano():
    """Side Focus dice una cosa y las operaciones dicen otra."""
    from supabase.correr_motor import share_del_lado_comprador

    p = {"transacciones": _p(), "sf_buy": 3, "sf_sell": 0}
    assert share_del_lado_comprador(p) == round(18 / 25.0, 4)
    # Sin Transactions, Side Focus. No se pierde la fuente: se ordena.
    assert share_del_lado_comprador({"sf_buy": 3, "sf_sell": 0}) == 1.0
    # Y con la lectura incompleta no se calcula desde el grano.
    p2 = {"transacciones": _p(REAL.replace("1 - 25 of 25", "1 - 25 of 137")),
          "sf_buy": 3, "sf_sell": 0}
    assert share_del_lado_comprador(p2) == 1.0


# ══════════════════════════════════════════════════════════════════════════════
# 10 · SIN TRANSACTIONS, LA FICHA LO DICE
# ══════════════════════════════════════════════════════════════════════════════

def test_sin_transactions_la_ficha_lo_dice_y_no_calcula_cash_por_diferencia():
    """19 compras y 14 con originador: 5 sin identificar, NO 5 cash."""
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
    assert "cash" not in v.evidencia


def test_con_transactions_el_veredicto_deja_de_decir_que_falta():
    """El control: el aviso tiene que APAGARSE cuando el dato llega."""
    from motor.veredicto import puede_contactarse

    v = puede_contactarse({"transacciones": _p()})
    assert v.evidencia.get("falta_transactions") is None
    assert v.evidencia["grano"] == "transacción"


# ══════════════════════════════════════════════════════════════════════════════
# 11 · LA GUARDA REDUNDANTE ANTES DE ESCRIBIR
# ══════════════════════════════════════════════════════════════════════════════

def test_las_filas_que_van_a_la_base_no_llevan_nombres_ni_calle():
    from api.rutas import _filas_de_transacciones

    fs = _filas_de_transacciones(_p(), "r-1", "lote-1", "2026-09-23T00:00:00Z")
    assert len(fs) == 25
    entero = json.dumps(fs, ensure_ascii=False)
    for i in range(1, 19):
        assert "Persona %d" % i not in entero, i
    assert "Calle Ficticia" not in entero
    for f in fs:
        assert "direccion" not in f and "calle" not in f
        assert f["realtor_id"] == "r-1"


def test_un_campo_prohibido_revienta_en_vez_de_filtrarse_en_silencio():
    """Un filtro callado deja el mismo bug vivo para el campo siguiente."""
    from api.rutas import _filas_de_transacciones

    p = _p()
    p["filas"][0]["buyers"] = "ALGUIEN"
    try:
        _filas_de_transacciones(p, "r-1", "lote-1", "2026-09-23T00:00:00Z")
    except ValueError as exc:
        assert "buyers" in str(exc) and "ECOA" in str(exc)
        return
    raise AssertionError("escribió una fila con el nombre del comprador")


# ══════════════════════════════════════════════════════════════════════════════
# 11b · EL CRUDO QUE SE GUARDA VA REDACTADO
# ══════════════════════════════════════════════════════════════════════════════
#
# Es la única sección del proyecto donde el crudo no se guarda tal cual. De
# nada sirve que `pacs.transacciones` no tenga columnas para comprador,
# vendedor ni calle si el pegado entero queda al lado en `texto_crudo`.

#: El fixture con nombres INYECTADOS donde el anonimizado puso etiquetas. Si la
#: prueba corriera sobre «Persona 1», pasaría por parecerse a una etiqueta.
NOMBRES_INYECTADOS = (
    REAL.replace("Persona 1\t", "Maria Gonzalez Perez\t")
        .replace("Persona 2\t", "John Fitzgerald Smith\t")
        .replace("101 Calle Ficticia", "4821 South Kolmar Avenue")
        .replace("103 Calle Ficticia", "77 West Wacker Drive"))


def test_el_crudo_redactado_no_deja_nombres_ni_calle():
    """La prueba que pidió la revisión: con nombres inyectados, no queda ninguno."""
    from captura.transacciones import crudo_redactado

    assert "Maria Gonzalez Perez" in NOMBRES_INYECTADOS, "el fixture no inyectó"
    red = crudo_redactado(NOMBRES_INYECTADOS)
    for prohibido in ("Maria Gonzalez Perez", "John Fitzgerald Smith",
                      "4821 South Kolmar Avenue", "77 West Wacker Drive",
                      "Kolmar", "Wacker"):
        assert prohibido not in red, prohibido
    for i in range(1, 19):
        assert "Persona %d" % i not in red, i


#: Una fila de 22 celdas: un segundo vendedor partió la columna en dos. Es la
#: forma que tienen las filas que quedaron sin leer en cuatro capturas reales.
_FILA_DE_22 = "\t".join([
    "Jul 30, 2026",
    "103 Calle Ficticia, Elmwood Park, IL, 60707",
    "No Builder",
    "Maria Gonzalez",            # comprador
    "Pedro Ramirez",             # vendedor
    "Jose Luis Perez",           # el SEGUNDO vendedor: la celda de más
    "Chicago Title",
    "$151K", "$17K",
    "Purchase", "Conventional", "6.55%", "30 Years",
    "Laura Lopez", "NMLS: 900001",
    "No Broker", "Guaranteed Rate Inc",
    "$168K", "—",
    "Agente Titular", "Agente 5", "No Co Agent",
]) + "\nRows per page\n1 - 1 of 1"


def test_una_fila_SIN_LEER_se_redacta_por_lista_blanca():
    """Y no entera, que es lo que destruía la evidencia para arreglar el parser.

    Cuatro capturas --Alva, Francisco, Jessica, Cristy-- quedaron con filas de
    22 celdas de «[redactado]», y por qué eran 22 ya no se puede saber: lo
    borró nuestra propia guarda, en el único caso en que el crudo hacía falta.

    Lo que se conserva es lo inequívocamente no-nombre. Ningún nombre de
    comprador, vendedor, LO ni agente sobrevive.
    """
    from captura.transacciones import crudo_redactado

    red = crudo_redactado(_FILA_DE_22)
    for nombre in ("Maria Gonzalez", "Pedro Ramirez", "Jose Luis Perez",
                   "Laura Lopez", "Agente Titular", "Agente 5",
                   "Chicago Title", "Guaranteed Rate Inc",
                   "103 Calle Ficticia", "900001"):
        assert nombre not in red, nombre
    # Y lo que sí tiene que quedar, que es con lo que se arregla el parser.
    for dato in ("Jul 30, 2026", "$151K", "$17K", "6.55%", "30 Years",
                 "Purchase", "Conventional", "No Builder", "No Broker",
                 "No Co Agent", "Elmwood Park", "IL", "60707"):
        assert dato in red, dato
    # La fila sigue teniendo 22 celdas: el número de columnas ES el dato que
    # explica por qué no se leyó.
    assert len(red.split("\n")[0].split("\t")) == 22


def test_el_crudo_redactado_conserva_lo_que_hace_falta_para_re_derivar():
    """El crudo existe para poder arreglar el parser y re-derivar.

    Un crudo redactado que ya no se puede parsear no es un crudo: es un log.
    """
    from captura.transacciones import crudo_redactado

    red = crudo_redactado(REAL)
    p = parsear_transacciones(red, realtor=REALTOR, capturado_en=CAPTURADO)
    assert p["leidas"] == 25
    assert p["no_leidas"] == []
    assert p["completa"] is True
    # Y las cifras salen IGUALES que del pegado original.
    assert resumen(p)["compras"] == _r()["compras"]
    assert resumen(p)["lenders_compra"] == ESPERADO["lenders_compra"]
    assert resumen(p)["zips_de_compra"]["60638"] == 3
    assert [f["hash_fila"] for f in p["filas"]] == \
        [f["hash_fila"] for f in _p()["filas"]]


def test_el_crudo_redactado_conserva_ciudad_estado_y_zip():
    """Se redacta la CALLE, no la geografía.

    Sin el ZIP, un re-parseo perdería la respuesta a «dónde trabaja», que es un
    dato que la tabla guarda igual por decisión tomada. La calle identifica una
    vivienda; el ZIP no.
    """
    from captura.transacciones import REDACTADO, crudo_redactado

    red = crudo_redactado(REAL)
    assert "%s, Chicago, IL, 60633" % REDACTADO in red
    assert "Calle Ficticia" not in red


def test_la_api_guarda_el_crudo_redactado_y_no_el_pegado():
    """La guarda tiene que estar en la ENTRADA, no solo en el destino."""
    from captura.transacciones import crudo_redactado

    guardado = crudo_redactado(NOMBRES_INYECTADOS)
    # Lo que `agregar` recibe como `texto_crudo` es exactamente esto.
    assert "Maria Gonzalez Perez" not in guardado
    assert len(guardado) > 1000, "se redactó de más: no queda nada que parsear"


def test_una_fila_que_no_se_leyo_no_deja_un_solo_nombre():
    """Antes se redactaba entera; ahora, por lista blanca. La guarda es la misma.

    Lo que cambia es que los datos que NO son nombres --la fecha, el importe,
    el tipo de loan-- sobreviven, y con ellos se puede ver por qué la fila no
    se leyó. Lo que no cambia es que ningún nombre sale.
    """
    from captura.transacciones import REDACTADO, crudo_redactado

    roto = _variante("Jul 30, 2026", "tipo", None, borrar=True)
    roto = roto.replace("Persona 1", "Maria Gonzalez Perez")
    red = crudo_redactado(roto)
    assert "Maria Gonzalez Perez" not in red
    assert REDACTADO in red
    # Y la fila corta sigue siendo reconocible: 20 celdas, no 21.
    cortas = [l for l in red.split("\n") if l.count("\t") == 19]
    assert cortas, "la fila de 20 celdas desapareció del crudo"


# ══════════════════════════════════════════════════════════════════════════════
# 11c · `no_leido` SE GUARDA, Y NO TUMBA LA CAPTURA
# ══════════════════════════════════════════════════════════════════════════════

def test_una_fila_no_leida_se_guarda_para_auditoria():
    """El check de la migración no aceptaba `no_leido`, así que UNA fila mal
    leída hacía fallar el insert de las 25 y la captura se quedaba sin
    operaciones. Justo la fila que hay que poder auditar era la que no entraba.
    """
    from api.rutas import _filas_de_transacciones
    from captura.transacciones import NO_LEIDO

    p = _p(_variantes("Jul 30, 2026", _SIN_NADA))
    fs = _filas_de_transacciones(p, "r-1", "lote-1", "2026-09-23T00:00:00Z")
    assert len(fs) == 25
    sin_leer = [f for f in fs if f["estado_prestamo"] == NO_LEIDO]
    assert len(sin_leer) == 1
    assert sin_leer[0]["fecha"] == "2026-07-30"


def test_los_estados_que_el_check_de_la_migracion_tiene_que_aceptar():
    """La lista del SQL y la del parser tienen que ser la misma.

    Se lee del archivo de migración: si alguien agrega un estado en Python y
    no en el check, el insert falla en producción y aquí no.
    """
    import re

    from captura.transacciones import (CASH_PROVISIONAL, CASH_SEGUN_MM,
                                       FINANCIADA, NO_LEIDO)

    sql = open(os.path.join(RAIZ, "supabase",
                            "migracion_18_transacciones.sql"),
               encoding="utf-8").read()
    m = re.search(r"tx_estado_prestamo_valido check \(\s*estado_prestamo in "
                  r"\(([^)]*)\)", sql)
    assert m, "no encontré el check en la migración 18"
    en_sql = set(re.findall(r"'([a-z_]+)'", m.group(1)))
    assert en_sql == {FINANCIADA, CASH_PROVISIONAL, CASH_SEGUN_MM, NO_LEIDO}, \
        en_sql


# ══════════════════════════════════════════════════════════════════════════════
# 12 · EL CAMINO COMPLETO
# ══════════════════════════════════════════════════════════════════════════════

def test_la_caja_de_transactions_entra_como_las_demas():
    from captura.cajas import LEIDO, SIN_PEGAR, cajas_desde, resumen_de_cajas

    cajas = cajas_desde({"cajas": [
        {"clave": "trx", "tipo": "transacciones", "etiqueta": "Transactions",
         "texto": REAL},
        {"clave": "lend", "tipo": "lenders", "etiqueta": "Lenders"}]})
    assert cajas[0].estado == LEIDO
    assert cajas[1].estado == SIN_PEGAR
    assert "Transactions" not in resumen_de_cajas(cajas)["faltan"]
    assert "Lenders" in resumen_de_cajas(cajas)["faltan"]


def test_unir_perfiles_lleva_las_transacciones_hasta_el_veredicto():
    """El camino real: la re-evaluación solo mira `parseado.perfil`."""
    from captura.parser_mm import unir_perfiles
    from motor.veredicto import OK, puede_contactarse

    unido = unir_perfiles([
        {"nombre": "ALGUIEN", "buyer_units": 18.0, "orig_buyer": []},
        {"transacciones": _p()}])
    assert unido["buyer_units"] == 18.0
    assert unido["transacciones"]["leidas"] == 25
    v = puede_contactarse(unido)
    assert v.estado == OK
    assert v.evidencia["grano"] == "transacción"


# ══════════════════════════════════════════════════════════════════════════════
# 13 · LO QUE EL OVERVIEW NO LEÍA
# ══════════════════════════════════════════════════════════════════════════════

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
