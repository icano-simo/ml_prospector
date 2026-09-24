"""No pedir de nuevo un mercado que ya está en la biblioteca.

Un benchmark de condado no es del realtor: es del condado. Pedirle a quien
captura que pegue Cook por cuarta vez en un día es pedirle cuatro veces el
mismo dato, y cada pegado es una oportunidad de ponerlo en la caja equivocada.

Lo que NO puede pasar
---------------------
Que un benchmark tomado de la biblioteca produzca un contraste distinto del de
uno pegado. Si lo produjera, ahorrarle el pegado a quien captura sería
cambiarle el resultado al diagnóstico, y nadie lo vería: las dos cifras son
plausibles.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))

import api.rutas as rutas  # noqa: E402
from api.rutas import (  # noqa: E402
    DIAS_BENCHMARK_FRESCO,
    _mercados_enlazados,
    _restar_meses,
    mercados_en_biblioteca,
    promover_a_mercados,
)

HOY = dt.datetime.now(dt.timezone.utc)


def _hace(dias: int) -> str:
    return (HOY - dt.timedelta(days=dias)).isoformat()


#: Lo que devolvería PostgREST. Cook capturado hace 5 días, Kane hace 40,
#: el estado de IL hace 3. Will nunca.
FILAS_MERCADOS = [
    {"id": "m-cook", "nivel": "condado", "estado": "IL",
     "condado_fips": "17031", "capturado_en": _hace(5), "campos": "44",
     "rango_desde": "2025-08-01", "rango_hasta": "2026-09-18",
     "upload_batch_id": "lote-1"},
    {"id": "m-kane", "nivel": "condado", "estado": "IL",
     "condado_fips": "17089", "capturado_en": _hace(40), "campos": "45",
     "rango_desde": None, "rango_hasta": None, "upload_batch_id": "lote-2"},
    {"id": "m-il", "nivel": "estado", "estado": "IL", "condado_fips": None,
     "capturado_en": _hace(3), "campos": "44",
     "rango_desde": None, "rango_hasta": None, "upload_batch_id": "lote-1"},
]

RESPUESTAS = {
    "mercados": FILAS_MERCADOS,
    "capturas_modelmatch": [{"upload_batch_id": "lote-1", "realtor_id": "r-1"},
                            {"upload_batch_id": "lote-2", "realtor_id": "r-2"}],
    "realtors": [{"id": "r-1", "nombre_completo": "REALTOR UNO"},
                 {"id": "r-2", "nombre_completo": "REALTOR DOS"}],
}


class _LeerFalso:
    """Sustituye `api.rutas.leer`. Guarda lo que se le pidió."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.consultas = []

    def __call__(self, tabla, consulta="", **kw):
        self.consultas.append((tabla, consulta))
        filas = self.respuestas.get(tabla, [])
        if tabla == "mercados" and "id=in." in consulta:
            dentro = consulta.split("id=in.(")[1].split(")")[0].split(",")
            filas = [f for f in filas if f["id"] in dentro]
        return 200, list(filas), {}


def _con_lector(respuestas=None):
    falso = _LeerFalso(respuestas or RESPUESTAS)
    rutas.leer = falso
    return falso


def _restaurar():
    from _comun import leer as real
    rutas.leer = real


def _biblioteca(condados="Cook|Kane|Will"):
    _con_lector()
    try:
        return mercados_en_biblioteca({"estado": "IL", "condados": condados})
    finally:
        _restaurar()


# ══ 1 · LOS TRES ESTADOS DE UNA CAJA ═════════════════════════════════════════

def test_un_condado_capturado_hace_5_dias_no_pide_pegar():
    cod, d = _biblioteca()
    assert cod == 200
    cook = next(g for g in d["geografias"] if g["etiqueta"] == "Cook")
    assert cook["estado_biblioteca"] == "fresco"
    assert cook["condado_fips"] == "17031"
    assert cook["dias"] == 5
    assert cook["campos"] == "44"
    assert cook["con_quien"] == "REALTOR UNO"
    assert cook["mercado_id"] == "m-cook"


def test_un_condado_de_hace_40_dias_ofrece_las_dos_opciones():
    """No decide por nadie: `viejo` no es `no_esta` ni es `fresco`."""
    cod, d = _biblioteca()
    kane = next(g for g in d["geografias"] if g["etiqueta"] == "Kane")
    assert kane["estado_biblioteca"] == "viejo"
    assert kane["dias"] == 40
    assert kane["mercado_id"] == "m-kane"
    assert kane["capturado_en"]


def test_un_condado_nunca_capturado_pide_pegar():
    cod, d = _biblioteca()
    will = next(g for g in d["geografias"] if g["etiqueta"] == "Will")
    assert will["estado_biblioteca"] == "no_esta"
    assert will.get("mercado_id") is None


def test_el_estado_y_el_condado_van_por_separado():
    """IL sí y Kane no: son dos filas distintas de la biblioteca.

    Resolver el estado no resuelve sus condados, y al revés tampoco.
    """
    cod, d = _biblioteca(condados="Kane")
    por_nivel = {g["nivel"]: g for g in d["geografias"]}
    assert por_nivel["estado"]["estado_biblioteca"] == "fresco"
    assert por_nivel["condado"]["estado_biblioteca"] == "viejo"


def test_el_corte_es_30_dias_y_esta_declarado():
    cod, d = _biblioteca()
    assert d["dias_fresco"] == DIAS_BENCHMARK_FRESCO == 30


def test_un_condado_sin_FIPS_pide_pegar_y_lo_dice():
    """Sin FIPS no se puede buscar en la biblioteca NI promover."""
    cod, d = _biblioteca(condados="Condado Inventado")
    g = next(g for g in d["geografias"] if g["nivel"] == "condado")
    assert g["estado_biblioteca"] == "no_esta"
    assert g["sin_fips"] is True


def test_se_pide_la_biblioteca_de_una_sola_vez():
    """Una consulta por condado son 25 idas y vueltas desde el navegador."""
    falso = _con_lector()
    try:
        mercados_en_biblioteca({"estado": "IL", "condados": "Cook|Kane|Will"})
    finally:
        _restaurar()
    a_mercados = [c for c in falso.consultas if c[0] == "mercados"]
    assert len(a_mercados) == 1, falso.consultas


# ══ 2 · EL CONTRASTE SALE IGUAL ══════════════════════════════════════════════

def test_un_benchmark_de_la_biblioteca_da_el_mismo_bloque_que_uno_pegado():
    """La forma tiene que ser la misma: `nivel`, `estado`, `etiqueta`,
    `metricas`. Si el contraste distinguiera de dónde salió, ahorrarse el
    pegado cambiaría el diagnóstico."""
    respuestas = dict(RESPUESTAS, mercados=[
        {"id": "m-cook", "nivel": "condado", "estado": "IL",
         "condado_fips": "17031", "metricas": {"mkt_fha": 14.1, "campos": 44},
         "capturado_en": _hace(5), "rango_desde": "2025-08-01",
         "rango_hasta": "2026-09-18"}])
    _con_lector(respuestas)
    try:
        bloques = _mercados_enlazados([
            {"parseado": {"mercados_enlazados": [
                {"etiqueta": "Cook", "mercado_id": "m-cook"}]}}])
    finally:
        _restaurar()
    assert len(bloques) == 1
    b = bloques[0]
    assert b["nivel"] == "condado"
    assert b["estado"] == "IL"
    assert b["etiqueta"] == "Cook"
    assert b["metricas"]["mkt_fha"] == 14.1
    assert b["de_la_biblioteca"] is True
    # Y trae de qué período es, que es lo que la ficha tiene que poder decir.
    assert b["rango_desde"] == "2025-08-01"


def test_sin_enlaces_no_se_consulta_la_biblioteca():
    falso = _con_lector()
    try:
        assert _mercados_enlazados([{"parseado": {}}]) == []
    finally:
        _restaurar()
    assert falso.consultas == []


# ══ 3 · LA VENTANA DEL BENCHMARK ═════════════════════════════════════════════

def test_la_ventana_del_bloque_manda_sobre_la_del_perfil():
    """Market Insight tiene su propio selector de período.

    `rango_desde` y `rango_hasta` estaban en NULL en TODAS las filas de
    `pacs.mercados`, así que la ficha comparaba al realtor contra un mercado
    sin poder decir de qué período es el dato.
    """
    filas = [{"parseado": {"seccion": "market_signals", "nivel": "estado",
                           "etiqueta_geografica": "IL",
                           "metricas": {"campos": 40, "ventana_meses": 12}},
              "estado": "IL"}]
    ms, fallos = promover_a_mercados(filas, "lote-x", "2026-09-23T10:00:00Z",
                                     ventana_meses=14)
    assert not fallos
    assert ms[0]["rango_hasta"] == "2026-09-23"
    assert ms[0]["rango_desde"] == "2025-09-23", "12 meses, la del bloque"


def test_sin_ventana_del_bloque_se_usa_la_del_perfil():
    filas = [{"parseado": {"seccion": "market_signals", "nivel": "estado",
                           "etiqueta_geografica": "IL",
                           "metricas": {"campos": 40}},
              "estado": "IL"}]
    ms, _f = promover_a_mercados(filas, "lote-x", "2026-09-23T10:00:00Z",
                                 ventana_meses=14)
    assert ms[0]["rango_desde"] == "2025-07-23"


def test_sin_ninguna_ventana_quedan_en_null_y_no_se_inventan():
    """Una ventana inventada se guarda igual de bien que una correcta."""
    filas = [{"parseado": {"seccion": "market_signals", "nivel": "estado",
                           "etiqueta_geografica": "IL",
                           "metricas": {"campos": 40}},
              "estado": "IL"}]
    ms, _f = promover_a_mercados(filas, "lote-x", "2026-09-23T10:00:00Z")
    assert ms[0]["rango_desde"] is None
    assert ms[0]["rango_hasta"] is None


def test_restar_meses_no_se_pasa_de_fin_de_mes():
    assert _restar_meses(dt.date(2026, 3, 31), 1) == dt.date(2026, 2, 28)
    assert _restar_meses(dt.date(2026, 1, 15), 14) == dt.date(2024, 11, 15)
    assert _restar_meses(dt.date(2026, 9, 23), 12) == dt.date(2025, 9, 23)


def test_el_parser_lee_la_ventana_del_bloque():
    from captura.parser_mm import parsear_mercado

    m = parsear_mercado("Set Location\nCook County\nLast 12 Months\n"
                        "Market Status: Warm\n")
    assert m["ventana_meses"] == 12
    assert parsear_mercado("Set Location\nCook\n")["ventana_meses"] is None


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
        finally:
            _restaurar()
    print("")
    print("  %d pruebas, %d fallas" % (len(fns), len(fallas)))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(_correr())
