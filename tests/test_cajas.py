"""Captura por cajas: el condado lo define la caja, no la posición.

`etiquetar_por_posicion` exigía exactamente `1 + N` bloques y rechazaba la
captura ENTERA cuando Model Match mostraba 5 condados en el Overview y 3 en
Market Insight. Un dato que falta hacía perder los cuatro que sí estaban.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from captura.cajas import (  # noqa: E402
    LEIDO,
    SIN_PEGAR,
    VACIO_DECLARADO,
    cajas_desde,
    condados_sin_market_insight,
    control_suave,
    resumen_de_cajas,
    set_location_de,
)
from captura.parser_mm import _condados  # noqa: E402


def _payload(*cajas):
    return {"cajas": list(cajas)}


def _c(clave, tipo, etiqueta=None, texto="", vacio=False):
    return {"clave": clave, "tipo": tipo, "etiqueta": etiqueta,
            "texto": texto, "vacio_declarado": vacio}


# ══ LOS TRES ESTADOS DE UNA CAJA ═════════════════════════════════════════════

def test_caja_con_texto_es_leida():
    cajas = cajas_desde(_payload(
        _c("c1", "condado", "Solano", "MARKET SIGNALS ... Total Volume $6.0B")))
    assert cajas[0].estado == LEIDO


def test_caja_vacia_SIN_casilla_es_falta_capturar():
    cajas = cajas_desde(_payload(_c("c1", "condado", "Solano")))
    assert cajas[0].estado == SIN_PEGAR


def test_caja_vacia_CON_casilla_es_capturado_no_tiene():
    """Son dos cosas distintas y el veredicto las trata distinto."""
    cajas = cajas_desde(_payload(
        _c("o", "originators", "Originators", vacio=True)))
    assert cajas[0].estado == VACIO_DECLARADO


def test_texto_y_casilla_a_la_vez_gana_el_texto_y_avisa():
    """Es una contradicción del usuario: hay dato, así que el dato manda."""
    cajas = cajas_desde(_payload(
        _c("o", "originators", "Originators", texto="Grace Davis ...",
           vacio=True)))
    assert cajas[0].estado == LEIDO
    assert cajas[0].vacio_declarado is False
    assert "se guarda el texto" in cajas[0].aviso


# ══ EL CASO QUE MOTIVA TODO: 5 CONDADOS, 3 CAJAS ═════════════════════════════

def test_cinco_condados_y_tres_cajas_no_bloquea():
    """El caso de la spec. Se guarda con 2 condados «no disponible»."""
    condados = ["Solano", "Contra Costa", "Alameda", "Napa", "Sonoma"]
    cajas = cajas_desde(_payload(
        _c("e", "estado", "CA", "MARKET SIGNALS CALIFORNIA"),
        _c("c1", "condado", "Solano", "MARKET SIGNALS SOLANO"),
        _c("c2", "condado", "Contra Costa", "MARKET SIGNALS CONTRA COSTA"),
        _c("c3", "condado", "Alameda", "MARKET SIGNALS ALAMEDA"),
        _c("c4", "condado", "Napa"),
        _c("c5", "condado", "Sonoma")))
    faltan = condados_sin_market_insight(condados, cajas)
    assert faltan == ["Napa", "Sonoma"], faltan
    # Y las tres que sí llegaron quedan leídas: no se pierde ninguna.
    assert sum(1 for c in cajas if c.estado == LEIDO) == 4


def test_el_orden_de_las_cajas_no_etiqueta_nada():
    """La etiqueta manda. Pegar en otro orden no mueve un condado.

    Con el etiquetado por posición, las métricas de Solano se guardaban bajo
    Alameda y nada fallaba.
    """
    al_derecho = cajas_desde(_payload(
        _c("a", "condado", "Solano", "S"), _c("b", "condado", "Alameda", "A")))
    al_reves = cajas_desde(_payload(
        _c("b", "condado", "Alameda", "A"), _c("a", "condado", "Solano", "S")))
    por_etiqueta = {c.etiqueta: c.texto for c in al_derecho}
    assert por_etiqueta == {c.etiqueta: c.texto for c in al_reves}
    assert por_etiqueta["Solano"] == "S"


# ══ EL CONTROL SUAVE ═════════════════════════════════════════════════════════

def test_avisa_si_pegaste_alameda_en_la_caja_de_solano():
    aviso = control_suave("Solano", "Set Location: Alameda County\nTotal ...")
    assert aviso and "Alameda" in aviso and "Solano" in aviso


def test_el_control_suave_NO_bloquea():
    """Avisa y ya. La captura que se rechaza es la que no se repite."""
    cajas = cajas_desde(_payload(
        _c("c", "condado", "Solano", "Set Location: Alameda County\nTotal")))
    assert cajas[0].estado == LEIDO
    assert cajas[0].aviso


def test_sin_set_location_no_inventa_un_aviso():
    assert control_suave("Solano", "MARKET SIGNALS sin ubicacion") is None
    assert set_location_de("MARKET SIGNALS") is None


def test_el_mismo_condado_escrito_distinto_no_avisa():
    """«Solano» y «Solano County» son el mismo sitio."""
    assert control_suave("Solano", "Set Location: Solano County") is None
    assert control_suave("Solano County", "Set Location: Solano") is None


# ══ EL RESUMEN QUE SE MUESTRA ════════════════════════════════════════════════

def test_el_resumen_dice_que_falta_y_que_no():
    cajas = cajas_desde(_payload(
        _c("e", "estado", "CA", "texto"),
        _c("c1", "condado", "Solano", "texto"),
        _c("c2", "condado", "Napa"),
        _c("o", "originators", "Originators", vacio=True)))
    r = resumen_de_cajas(cajas)
    assert r["por_estado"][LEIDO] == 2
    assert r["por_estado"][VACIO_DECLARADO] == 1
    assert r["faltan"] == ["Napa"]
    assert len(r["cajas"]) == 4


# ══ LOS CUATRO ARREGLOS DEL PARSER DE CONDADOS ═══════════════════════════════

def test_condados_con_espacios_en_vez_de_tabuladores():
    """Al copiar desde el navegador a veces llegan espacios.

    Sin esto la fila no matcheaba, o sea CERO condados -- el peor resultado,
    porque no parece un error.
    """
    txt = "Solano County, CA   $2.3M   5   $2.3M   5\n"
    assert [c["nombre"] for c in _condados(txt)] == ["Solano"]


def test_parish_borough_y_city():
    txt = ("Orleans Parish, LA\t$1.0M\t3\t\n"
           "Juneau Borough, AK\t$2.0M\t4\t\n"
           "Baltimore city, MD\t$3.0M\t5\t\n")
    filas = _condados(txt)
    # `Parish` y `Borough` SÍ son el condado del estado, así que el nombre va
    # pelado. `city` es otra cosa y conserva el sufijo: ver el test de los dos
    # Baltimore.
    assert [c["nombre"] for c in filas] == [
        "Orleans Parish", "Juneau Borough", "Baltimore city"]
    assert [c["nombre_base"] for c in filas] == [
        "Orleans", "Juneau", "Baltimore"]
    assert [c["es_condado"] for c in filas] == [True, True, False]


def test_acentos_y_enie():
    txt = "Doña Ana County, NM\t$1.5M\t2\t\n"
    assert [c["nombre"] for c in _condados(txt)] == ["Doña Ana"]


#: Los cinco estados donde una ciudad independiente comparte nombre con el
#: condado que la rodea. Son FIPS distintos.
LOS_DOS_BALTIMORE = (
    "Baltimore city, MD\t$1.0M\t3\t\n"
    "Baltimore County, MD\t$2.0M\t5\t\n"
    "St. Louis city, MO\t$1.1M\t2\t\n"
    "St. Louis County, MO\t$2.1M\t4\t\n"
    "Richmond city, VA\t$1.2M\t1\t\n"
    "Richmond County, VA\t$2.2M\t6\t\n"
    "Fairfax city, VA\t$1.3M\t2\t\n"
    "Fairfax County, VA\t$2.3M\t7\t\n"
    "Roanoke city, VA\t$1.4M\t1\t\n"
    "Roanoke County, VA\t$2.4M\t3\t\n"
)


def test_una_ciudad_y_su_condado_no_son_el_mismo_mercado():
    """Baltimore city (24510) y Baltimore County (24005) son FIPS distintos.

    Quitar el sufijo los convertía en «Baltimore» a secas, así que dos filas
    del Overview con volúmenes y unidades distintos colapsaban en un mercado y
    la biblioteca promediaba una ciudad de 570.000 habitantes con el condado
    suburbano de al lado.

    Es el mismo error de CA contra California, al revés: allí dos nombres del
    mismo sitio, aquí un nombre para dos sitios.
    """
    filas = _condados(LOS_DOS_BALTIMORE)
    assert len(filas) == 10, len(filas)
    nombres = [f["nombre"] for f in filas]
    assert len(set(nombres)) == 10, sorted(nombres)
    assert "Baltimore city" in nombres and "Baltimore" in nombres


def test_cada_fila_dice_su_tipo_y_si_es_condado():
    """El sufijo en el nombre resuelve la etiqueta; `tipo` resuelve el resto."""
    porn = {f["nombre"]: f for f in _condados(LOS_DOS_BALTIMORE)}
    assert porn["Baltimore city"]["tipo"] == "city"
    assert porn["Baltimore city"]["es_condado"] is False
    assert porn["Baltimore city"]["nombre_base"] == "Baltimore"
    assert porn["Baltimore"]["tipo"] == "County"
    assert porn["Baltimore"]["es_condado"] is True


def test_las_unidades_no_se_mezclan_entre_la_ciudad_y_el_condado():
    """Lo que de verdad costaba: 3 unidades de la ciudad y 5 del condado."""
    porn = {f["nombre"]: f["unidades"] for f in _condados(LOS_DOS_BALTIMORE)}
    assert porn["Baltimore city"] == 3
    assert porn["Baltimore"] == 5


def test_los_condados_de_siempre_siguen_saliendo():
    """El control: los cuatro arreglos no pueden romper lo que ya funcionaba."""
    txt = ("Solano County, CA\t$2.3M\t5\t$2.3M\t5\t$0\t0\n"
           "Contra Costa County, CA\t$1.6M\t3\t$1.6M\t3\t$0\t0\n"
           "Alameda County, CA\t$570K\t1\t$570K\t1\t$0\t0\n")
    assert [c["nombre"] for c in _condados(txt)] == [
        "Solano", "Contra Costa", "Alameda"]
    assert [c["unidades"] for c in _condados(txt)] == [5, 3, 1]


def test_los_nombres_alternativos_llegan_de_la_caja_de_Transactions():
    """Escritos por una persona, así que se aceptan las tres formas.

    Coma, salto de línea o lista: es la misma intención. Lo que no hace es
    inventar uno cuando el campo está vacío.
    """
    from captura.cajas import cajas_desde

    cajas = cajas_desde({"cajas": [
        {"clave": "trx", "tipo": "transacciones", "texto": "algo",
         "nombres_alternativos": "Isabel Vazquez, I. Vazquez"},
        {"clave": "trx2", "tipo": "transacciones", "texto": "algo",
         "nombres_alternativos": ["Ana Osorio"]},
        {"clave": "trx3", "tipo": "transacciones", "texto": "algo"},
    ]})
    assert cajas[0].nombres_alternativos == ["Isabel Vazquez", "I. Vazquez"]
    assert cajas[1].nombres_alternativos == ["Ana Osorio"]
    assert cajas[2].nombres_alternativos == []


def test_los_nombres_alternativos_no_se_repiten_ni_traen_espacios():
    from captura.cajas import cajas_desde

    cajas = cajas_desde({"cajas": [
        {"clave": "trx", "tipo": "transacciones", "texto": "algo",
         "nombres_alternativos": "  Isabel   Vazquez , isabel vazquez ,, "},
    ]})
    assert cajas[0].nombres_alternativos == ["Isabel Vazquez"]


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
