"""Pruebas de google_places, sin red y sin clave.

    python tests/test_google_places.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_places.cliente import Lugar, Review  # noqa: E402


def _review(texto, idioma="es", rating=5):
    return Review.desde_api({
        "originalText": {"text": texto, "languageCode": idioma},
        "rating": rating,
        "publishTime": "2026-03-01T10:00:00Z",
        "authorAttribution": {"displayName": "Jose Perez"},
    })


def test_el_autor_de_la_review_no_se_guarda():
    r = _review("Excelente agente, nos ayudo mucho con nuestra primera casa")
    assert "Jose Perez" not in repr(r)
    assert not hasattr(r, "autor")
    assert not hasattr(r, "author")


def test_se_redactan_email_y_telefono_de_la_review():
    r = _review("Llamalo al 512-555-0100 o escribile a jose@gmail.com, es buenisimo")
    assert "512-555-0100" not in r.texto
    assert "jose@gmail.com" not in r.texto
    assert "[telefono]" in r.texto
    assert "[email]" in r.texto


def test_idioma_sin_declarar_es_none_no_false():
    r = Review.desde_api({"text": {"text": "Great agent"}})
    assert r.es_espanol is None, "None no es False: la API no declaro idioma"


def test_idioma_declarado():
    assert _review("Muy buena", "es-419").es_espanol is True
    assert _review("Very good", "en").es_espanol is False


def test_pct_de_espanol_siempre_con_denominador_y_es_sobre_las_devueltas():
    """La API devuelve 5 como maximo y las elige ella: el denominador es 5."""
    lugar = Lugar(
        place_id="x", n_reviews_total=180,
        reviews=[_review("Muy buena atencion, nos explico todo", "es"),
                 _review("Excelente, muy recomendable la verdad", "es"),
                 _review("Great experience with this agent", "en"),
                 _review("Nos acompanio en todo el proceso", "es"),
                 _review("Would recommend to anyone buying", "en")],
    )
    texto = lugar.pct_reviews_en_espanol()
    assert "(3/5 de las reviews devueltas" in texto
    assert "de 180 totales que tiene el lugar" in texto, (
        "hay que decir que el denominador no es userRatingCount"
    )


def test_sin_idioma_declarado_no_inventa_un_porcentaje():
    lugar = Lugar(place_id="x", n_reviews_total=40,
                  reviews=[Review.desde_api({"text": {"text": "ok"}})])
    assert "[sin dato" in lugar.pct_reviews_en_espanol()


def test_umbral_de_la_matriz_son_5_reviews():
    pocas = Lugar(place_id="x", reviews=[_review("Muy buena atencion aca")] * 4)
    justas = Lugar(place_id="x", reviews=[_review("Muy buena atencion aca")] * 5)
    assert pocas.cumple_umbral_matriz is False
    assert justas.cumple_umbral_matriz is True


def test_rating_ausente_es_none_no_cero():
    lugar = Lugar(place_id="x")
    assert lugar.rating is None
    assert lugar.a_fila_persistible()["places_rating"] is None


def test_la_fila_persistible_no_lleva_el_texto_de_las_reviews():
    """La politica de Google limita guardar contenido de Places."""
    lugar = Lugar(
        place_id="ChIJxxxx", n_reviews_total=12,
        reviews=[_review("Nos ayudo con el enganche y fue clarisimo", "es")],
    )
    fila = lugar.a_fila_persistible()
    plano = " ".join(str(v) for v in fila.values())
    assert "enganche" not in plano, "el texto crudo no se persiste"
    assert fila["places_place_id"] == "ChIJxxxx"
    assert fila["places_n_reviews_con_texto"] == 1
    # pero si esta disponible en memoria para el lexico de friccion
    assert "enganche" in " ".join(lugar.textos())


def test_falta_de_clave_falla_con_instrucciones():
    from google_places.cliente import PlacesNoDisponible, _clave

    anterior = os.environ.pop("GOOGLE_PLACES_API_KEY", None)
    try:
        _clave()
    except PlacesNoDisponible as exc:
        assert "GOOGLE_PLACES_API_KEY" in str(exc)
        assert "historial del shell" in str(exc)
    else:
        raise AssertionError("no fallo sin clave")
    finally:
        if anterior is not None:
            os.environ["GOOGLE_PLACES_API_KEY"] = anterior


def _main() -> int:
    pruebas = [(n, o) for n, o in sorted(globals().items())
               if n.startswith("test_") and callable(o)]
    fallos = []
    for nombre, fn in pruebas:
        try:
            fn()
            print("  ok   %s" % nombre)
        except Exception as exc:  # noqa: BLE001
            fallos.append((nombre, exc))
            print("  FALLA %s -- %r" % (nombre, exc))
    print("")
    print("%d pruebas, %d fallas" % (len(pruebas), len(fallos)))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(_main())
