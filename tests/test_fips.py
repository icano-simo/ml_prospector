"""El cruce de nombre de condado a FIPS, con la clave compacta.

El caso que lo motivó
---------------------
Model Match escribe «Du Page» y el archivo del Census escribe «DuPage County».
Normalizados quedan `du page` y `dupage`, que son distintos, así que las 44
métricas de DuPage de una captura real no entraron en `pacs.mercados`.

Y no falló nada: la fila se guardó con `condado_fips` en NULL, que es
exactamente la forma en que este proyecto pierde datos -- una ausencia que no
se declara.

Sigue siendo match exacto. Quitar los espacios no acerca dos nombres distintos:
los hace iguales o no.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from geo.fips import (  # noqa: E402
    CACHE,
    ClaveCompactaAmbigua,
    FipsNoResuelto,
    _compacta,
    _normalizar,
    cargar,
    resolver,
)

HAY_REFERENCIA = CACHE.exists()
TABLA = cargar() if HAY_REFERENCIA else {}

#: Los seis de Illinois que Model Match parte en dos palabras, con su FIPS.
PARTIDOS_EN_DOS = {
    "Du Page": "17043",
    "De Kalb": "17037",
    "La Salle": "17099",
    "Mc Henry": "17111",
    "St Clair": "17163",
    "De Witt": "17039",
}

#: Los que ya funcionaban. El control: si el arreglo los rompe, se ve acá.
LOS_DE_SIEMPRE = {"Cook": "17031", "Kane": "17089", "Will": "17197"}


def test_los_seis_condados_partidos_en_dos_resuelven():
    """Los que Model Match escribe con un espacio de más."""
    assert HAY_REFERENCIA, "falta geo/cache: correr `python -m geo.fips --descargar`"
    for nombre, fips in PARTIDOS_EN_DOS.items():
        got, oficial = resolver("IL", nombre, TABLA)
        assert got == fips, (nombre, got, fips, oficial)


def test_los_que_ya_andaban_siguen_andando():
    """El control. Un arreglo que rompe lo que funcionaba no es un arreglo."""
    assert HAY_REFERENCIA
    for nombre, fips in LOS_DE_SIEMPRE.items():
        assert resolver("IL", nombre, TABLA)[0] == fips, nombre


def test_tambien_con_el_sufijo_County_puesto():
    """Model Match manda las dos formas según la sección."""
    assert HAY_REFERENCIA
    assert resolver("IL", "Du Page County", TABLA)[0] == "17043"
    assert resolver("IL", "DuPage County", TABLA)[0] == "17043"
    assert resolver("IL", "DUPAGE", TABLA)[0] == "17043"


def test_sigue_sin_ser_fuzzy():
    """Un FIPS aproximado es un FIPS equivocado.

    La clave compacta hace iguales a dos escrituras del mismo nombre. No acerca
    dos nombres distintos, y esta prueba es la que lo fija.
    """
    assert HAY_REFERENCIA
    for inventado in ("Du Pag", "Dupageee", "Cok", "Sant Clair", "DeKal"):
        try:
            resolver("IL", inventado, TABLA)
        except FipsNoResuelto:
            continue
        raise AssertionError("resolvió %r, que no existe" % inventado)


def test_el_estado_sigue_separando():
    """Hay 31 condados llamados Washington. El estado es parte de la llave."""
    assert HAY_REFERENCIA
    assert resolver("IL", "Washington", TABLA)[0] != resolver(
        "TX", "Washington", TABLA)[0]
    try:
        resolver("TX", "Du Page", TABLA)
    except FipsNoResuelto:
        return
    raise AssertionError("resolvió Du Page en Texas")


def test_no_hay_ninguna_colision_de_clave_compacta_en_todo_el_archivo():
    """Medido, no supuesto. Y si algún día aparece una, `cargar` revienta.

    Esta prueba comprueba las dos cosas: que hoy no hay ninguna, y que el
    mecanismo que lo detecta existe -- con un caso construido, porque una
    guarda que nunca se dispara no se sabe si funciona.
    """
    assert HAY_REFERENCIA
    por_compacta: dict = {}
    for (estado, _clave), (fips, oficial) in TABLA.items():
        por_compacta.setdefault((estado, _compacta(oficial)), set()).add(fips)
    colisiones = {k: v for k, v in por_compacta.items() if len(v) > 1}
    assert not colisiones, colisiones


def test_la_guarda_de_colision_revienta_de_verdad(tmp=None):
    """El control de la guarda. Sin esto, «0 colisiones» podría ser
    «la comprobación no corre»."""
    import tempfile
    from pathlib import Path

    contenido = (
        "STATE|STATEFP|COUNTYFP|COUNTYNS|COUNTYNAME|CLASSFP|FUNCSTAT\n"
        "IL|17|001|00000001|Du Page|H1|A\n"
        "IL|17|003|00000002|DuPage|H1|A\n")
    with tempfile.TemporaryDirectory() as d:
        ruta = Path(d) / "falso.txt"
        ruta.write_text(contenido, encoding="utf-8")
        try:
            cargar(ruta)
        except ClaveCompactaAmbigua as exc:
            assert "comparten la clave" in str(exc), str(exc)
            assert "17001" in str(exc) and "17003" in str(exc)
            return
    raise AssertionError("no detectó dos condados distintos con la misma clave")


def test_la_ciudad_independiente_no_es_el_condado_del_mismo_nombre():
    """Seis pares se resolvían solos, a favor del último del archivo.

    «Baltimore, MD» daba **24510**, que es la ciudad, y no 24005, que es el
    condado. No fallaba nada: el FIPS existe, tiene cinco dígitos y es del
    estado correcto. La guarda de colisión de `cargar` es la que lo destapó.

    Convención del Census: la ciudad independiente lleva « city» en minúscula.
    """
    assert HAY_REFERENCIA
    pares = {
        ("MD", "Baltimore"): "24005", ("MD", "Baltimore city"): "24510",
        ("MO", "St. Louis"): "29189", ("MO", "St. Louis city"): "29510",
        ("VA", "Fairfax"): "51059", ("VA", "Fairfax city"): "51600",
        ("VA", "Franklin"): "51067", ("VA", "Franklin city"): "51620",
        ("VA", "Richmond"): "51159", ("VA", "Richmond city"): "51760",
        ("VA", "Roanoke"): "51161", ("VA", "Roanoke city"): "51770",
    }
    for (estado, nombre), fips in pares.items():
        assert resolver(estado, nombre, TABLA)[0] == fips, (estado, nombre)


def test_un_condado_que_SE_LLAMA_City_sigue_resolviendo():
    """«Carson City» lleva City con mayúscula: es el nombre, no el tipo."""
    assert HAY_REFERENCIA
    assert resolver("NV", "Carson City", TABLA)[0] == "32510"


def test_la_normalizacion_y_la_compacta_son_lo_que_dicen():
    assert _normalizar("DuPage County") == "dupage"
    assert _normalizar("Du Page County") == "du page"
    assert _compacta("Du Page County") == "dupage"
    assert _compacta("DuPage County") == "dupage"
    assert _compacta("St. Clair County") == "stclair"
    # Y no pisa lo que ya distinguía: acentos y sufijos.
    assert _compacta("Doña Ana County") == "donaana"


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
