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
    assert [c["nombre"] for c in _condados(txt)] == [
        "Orleans", "Juneau", "Baltimore"]


def test_acentos_y_enie():
    txt = "Doña Ana County, NM\t$1.5M\t2\t\n"
    assert [c["nombre"] for c in _condados(txt)] == ["Doña Ana"]


def test_los_condados_de_siempre_siguen_saliendo():
    """El control: los cuatro arreglos no pueden romper lo que ya funcionaba."""
    txt = ("Solano County, CA\t$2.3M\t5\t$2.3M\t5\t$0\t0\n"
           "Contra Costa County, CA\t$1.6M\t3\t$1.6M\t3\t$0\t0\n"
           "Alameda County, CA\t$570K\t1\t$570K\t1\t$0\t0\n")
    assert [c["nombre"] for c in _condados(txt)] == [
        "Solano", "Contra Costa", "Alameda"]
    assert [c["unidades"] for c in _condados(txt)] == [5, 3, 1]


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
