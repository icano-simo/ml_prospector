"""Pruebas del Bloque 1-bis: captura cruda, parser y contrato del CSV.

La prueba central es `test_el_ratio_de_espanol_recupera_la_verdad`: se arma un
perfil con un ratio de español **conocido** y se verifica que el parser lo
recupera. Es la unica forma de distinguir "el detector anda" de "el detector
devuelve algo".

    python tests/test_instagram_profundo.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "realtor_scraper"))

from instagram.finder import (  # noqa: E402
    COLUMNAS_CSV,
    MAX_CHARS_CELDA,
    SEP,
    Objetivo,
    guardar_crudo,
    parsear_crudo,
    parsear_crudos,
)
from instagram.idioma import (  # noqa: E402
    Idioma,
    clasificar_comentario,
    clasificar_pieza,
    motor_en_uso,
)

EPOCH = 1_755_000_000  # 2025-08-12 aprox


def _post(caption, *, dias_atras=0, tipo="GraphImage", likes=100,
          n_comentarios=10, etiquetadas=None, geo=None, alt=None, hijos=0):
    fecha = dt.date(2026, 8, 20) - dt.timedelta(days=dias_atras)
    ts = int(dt.datetime(fecha.year, fecha.month, fecha.day,
                         12, 0, tzinfo=dt.timezone.utc).timestamp())
    return {
        "shortcode": "SC%d" % dias_atras,
        "caption": caption,
        "timestamp": ts,
        "typename": tipo,
        "es_video": tipo == "GraphVideo",
        "likes": likes,
        "n_comentarios": n_comentarios,
        "etiquetadas": etiquetadas or [],
        "ubicacion": {"nombre": geo} if geo else None,
        "accesibilidad_alt": alt,
        "n_hijos": hijos,
    }


def _crudo(*, estado="publico_leido", posts=None, comentarios=None,
           bio="Texas REALTOR | Hablo Espanol | ABR GRI",
           nombre_visible="Ana Tapia", handle="anatapia_realtor",
           seguidores=4000, nombre_objetivo="ANA TAPIA",
           destacadas=None, privado=False):
    return {
        "esquema": "ig-crudo-v1",
        "handle_pedido": handle,
        "capturado_en": "2026-09-21T12:00:00+00:00",
        "via": "json",
        "estado_perfil": estado,
        "estado_evidencia": "fixture",
        "perfil": {
            "handle": handle,
            "nombre_visible": nombre_visible,
            "bio": bio,
            "seguidores": seguidores,
            "seguidos": 900,
            "n_publicaciones": 220,
            "enlace_bio": "https://linktr.ee/anatapia",
            "es_privado": privado,
            "es_cuenta_empresa": True,
            "categoria_declarada": "Real Estate Agent",
            "titulos_destacadas": destacadas or ["FHA", "Primera casa", "Testimonios"],
        },
        "posts": posts or [],
        "comentarios_por_post": comentarios or {},
        "destino_enlace_bio": "https://anatapia.kw.com",
        "errores": [],
        "objetivo": {
            "email": "ana@casaprorealty.com",
            "nombre": nombre_objetivo,
            "estado": "Texas",
            "handle_del_libro": handle,
            "nivel": "MQL",
            "tier": "A - PRIORIDAD ALTA",
        },
    }


# ══ EL DETECTOR ═══════════════════════════════════════════════════════════════

def test_el_motor_es_un_detector_real():
    assert motor_en_uso() == "lingua", (
        "sin lingua el ratio de español no es confiable; el conteo de palabras "
        "clave es lo que produjo el 3,29%%"
    )


def test_el_caso_que_langdetect_falla():
    """langdetect daba 'pt' con confianza 1.00 en estos dos."""
    for texto in ("¡Vendida! 🏡🔑 Felicidades",
                  "Casa abierta este sabado 🏠 #openhouse #austin"):
        p = clasificar_pieza(texto)
        assert p.idioma is Idioma.ESPANOL, "%r dio %s" % (texto, p.idioma)


def test_hashtags_solos_no_son_un_idioma():
    p = clasificar_pieza("#realtor #austin #texas #realestate")
    assert p.idioma is Idioma.INDETERMINADO
    assert p.letras == 0


def test_emoji_solo_no_es_ingles():
    assert clasificar_pieza("🏡🔑✨").idioma is Idioma.INDETERMINADO


def test_terminos_de_oficio_no_vuelven_ingles_al_espanol():
    p = clasificar_pieza(
        "Nuevo listing en Austin. Si quieres saber cuanto necesitas para el "
        "down payment, escribeme y lo vemos juntos."
    )
    assert p.idioma is Idioma.ESPANOL


def test_el_piso_de_comentarios_es_mas_corto_que_el_de_captions():
    corto = "Se puede con ITIN?"
    assert clasificar_pieza(corto).idioma is Idioma.INDETERMINADO
    assert clasificar_comentario(corto).idioma is Idioma.ESPANOL, (
        "es justo el comentario que importa para S8"
    )


# ══ EL RATIO · LA PRUEBA CENTRAL ══════════════════════════════════════════════

def test_el_ratio_de_espanol_recupera_la_verdad():
    """12 captions: 8 en español, 4 en ingles. El ratio tiene que dar 8/12."""
    es = [
        "Felicidades a la familia Ramirez por su primera casa, que la disfruten mucho",
        "Nueva propiedad en Round Rock, tres habitaciones y un patio muy lindo",
        "Casa abierta este sabado de doce a tres, los espero con mucho gusto",
        "Cerramos con FHA y ayuda de enganche. Mi cliente no sabia que calificaba",
        "Si declaras con ITIN tambien puedes comprar tu casa, preguntame como",
        "Ya eres dueña de tu casa, felicidades por este paso tan importante",
        "Hablemos de tu credito antes de buscar casa, es el primer paso real",
        "Mi gente, este mercado tiene opciones para ustedes, no se desanimen",
    ]
    en = [
        "Congratulations to the Smith family on closing today, so happy for them",
        "New listing in Round Rock, three bedrooms and a great yard, come see it",
        "Open house this Saturday from noon to three, bring the whole family",
        "Let's talk about your credit before we start looking at homes together",
    ]
    posts = [_post(c, dias_atras=i) for i, c in enumerate(es + en)]
    fila = parsear_crudo(_crudo(posts=posts))

    assert fila["captions_n"] == 12
    assert fila["captions_es_ratio"] == round(8 / 12, 4), fila["captions_es_ratio"]
    assert fila["captions_es_ratio"] > 0.60, (
        "si esto da cerca de 0,03 algo quedo leyendo el alt-text"
    )


def test_el_alt_text_no_contamina_el_caption():
    """El alt de Meta esta en ingles; el caption en español. Manda el caption."""
    posts = [
        _post("Felicidades a la familia Ramirez por su primera casa, disfrutenla",
              dias_atras=i,
              alt="Photo by Ana Tapia on August 20, 2026. May be an image of house.")
        for i in range(10)
    ]
    fila = parsear_crudo(_crudo(posts=posts))
    assert fila["captions_es_ratio"] == 1.0, (
        "el alt-text esta en ingles: si el ratio baja, se esta leyendo el alt"
    )


def test_ratio_de_comentarios_de_terceros():
    posts = [_post("Nueva casa en Austin, vengan a verla este fin de semana",
                   dias_atras=0)]
    comentarios = {"SC0": [
        {"texto": "Cuanto necesito de enganche para una casa asi?",
         "autor_handle": "jose_p"},
        {"texto": "Se puede con ITIN? No tengo seguro social",
         "autor_handle": "maria_l"},
        {"texto": "Mi credito esta malo, califico igual?", "autor_handle": "luis_g"},
        {"texto": "How much do I need for the down payment?", "autor_handle": "kevin"},
        # del agente: no cuenta como tercero
        {"texto": "Claro que si, escribeme por privado y lo vemos",
         "autor_handle": "anatapia_realtor"},
    ]}
    fila = parsear_crudo(_crudo(posts=posts, comentarios=comentarios))

    assert fila["comentarios_n"] == 4, "el del agente no es un tercero"
    assert fila["comentarios_es_ratio"] == round(3 / 4, 4)
    assert fila["comentarios_pregunta_calificacion"] == 4


# ══ ESTADO DEL PERFIL · EL BUG QUE HAY QUE MATAR ══════════════════════════════

def test_privado_deja_las_senales_en_null_no_en_cero():
    fila = parsear_crudo(_crudo(estado="privado", privado=True, posts=[]))
    assert fila["estado_perfil"] == "privado"
    for col in ("captions_n", "captions_es_ratio", "comentarios_n",
                "comentarios_es_ratio", "menciona_itin", "menciona_fha",
                "engagement_rate", "tipo_post_reel_pct"):
        assert fila[col] is None, (
            "%s salio en %r; un perfil privado no es un perfil sin español, "
            "es un perfil que no leimos" % (col, fila[col])
        )


def test_bloqueado_tambien_queda_en_null():
    fila = parsear_crudo(_crudo(estado="bloqueado", posts=[]))
    assert fila["estado_perfil"] == "bloqueado"
    assert fila["captions_es_ratio"] is None
    assert fila["comentarios_n"] is None


def test_no_encontrado():
    fila = parsear_crudo(_crudo(estado="no_encontrado", posts=[]))
    assert fila["estado_perfil"] == "no_encontrado"


def test_sin_handle_se_mapea_a_no_encontrado():
    """El CSV expone los cinco valores del brief; el detalle fino va al JSON."""
    fila = parsear_crudo(_crudo(estado="sin_handle", posts=[]))
    assert fila["estado_perfil"] == "no_encontrado"


def test_los_cinco_estados_del_brief_y_nada_mas():
    permitidos = {"publico_leido", "privado", "no_encontrado", "bloqueado",
                  "handle_dudoso"}
    for estado in ("publico_leido", "privado", "no_encontrado", "bloqueado",
                   "handle_equivocado", "sin_handle"):
        fila = parsear_crudo(_crudo(estado=estado, posts=[]))
        assert fila["estado_perfil"] in permitidos, fila["estado_perfil"]


# ══ VERIFICACION DE HANDLE ════════════════════════════════════════════════════

def test_handle_de_otra_persona_queda_dudoso_y_sin_senales():
    posts = [_post("Felicidades a la familia por su primera casa, disfrutenla",
                   dias_atras=i) for i in range(10)]
    fila = parsear_crudo(_crudo(
        posts=posts, handle="cristiano", nombre_visible="Cristiano Ronaldo",
        bio="Footballer", nombre_objetivo="ANA TAPIA",
    ))
    assert fila["estado_perfil"] == "handle_dudoso"
    assert fila["handle_confianza"] == "baja"
    assert fila["captions_es_ratio"] is None, (
        "un handle equivocado no produce un error: produce catorce señales "
        "sobre la persona equivocada"
    )


def test_handle_correcto_verifica_y_deriva():
    posts = [_post("Nueva casa en Austin, vengan a verla este fin de semana",
                   dias_atras=i) for i in range(10)]
    fila = parsear_crudo(_crudo(posts=posts))
    assert fila["estado_perfil"] == "publico_leido"
    assert fila["handle_confianza"] == "alta"
    assert fila["captions_n"] == 10


# ══ S6 · menciona_lender ══════════════════════════════════════════════════════

def test_menciona_lender_devuelve_el_NOMBRE_no_un_booleano():
    posts = [
        _post("Gracias @maria.loanofficer por cerrar este caso tan rapido",
              dias_atras=0, etiquetadas=["maria.loanofficer"]),
        _post("Otra vez con @maria.loanofficer, gran equipo de trabajo",
              dias_atras=5, etiquetadas=["maria.loanofficer"]),
        _post("Taller de compradores junto a @acme_mortgage este sabado",
              dias_atras=9, etiquetadas=["acme_mortgage"]),
        _post("Felicidades a los Ramirez por su nueva casa preciosa", dias_atras=14),
    ]
    fila = parsear_crudo(_crudo(posts=posts))
    assert fila["menciona_lender"] == "@maria.loanofficer", fila["menciona_lender"]
    assert "acme_mortgage" in fila["cuentas_hipotecarias_etiquetadas"]
    assert "(4)" in fila["cuentas_hipotecarias_etiquetadas"], (
        "maria aparece etiquetada y mencionada en 2 posts = 4 apariciones"
    )


def test_sin_cuenta_hipotecaria_el_lender_es_null():
    posts = [_post("Felicidades a los Ramirez por su nueva casa preciosa",
                   dias_atras=i) for i in range(5)]
    fila = parsear_crudo(_crudo(posts=posts))
    assert fila["menciona_lender"] is None
    assert fila["cuentas_hipotecarias_etiquetadas"] is None


def test_co_marketing_necesita_socio_etiquetado():
    solo = _post("Homebuyer workshop this Saturday, see you all there", dias_atras=0)
    con = _post("Homebuyer workshop junto a @acme_mortgage este sabado",
                dias_atras=5, etiquetadas=["acme_mortgage"])
    assert parsear_crudo(_crudo(posts=[solo]))["posts_comarketing"] == 0
    assert parsear_crudo(_crudo(posts=[con]))["posts_comarketing"] == 1


# ══ PROGRAMAS, CADENCIA, ENGAGEMENT ══════════════════════════════════════════

def test_programas_se_cuentan_por_post():
    posts = [
        _post("Hablemos de FHA y del enganche que necesitas", dias_atras=0),
        _post("Otro caso FHA cerrado hoy, muy contenta con el resultado",
              dias_atras=7),
        _post("Si declaras con ITIN tambien puedes comprar casa", dias_atras=14),
    ]
    fila = parsear_crudo(_crudo(posts=posts, bio="Realtor en Texas"))
    assert fila["menciona_fha"] == 2
    assert fila["menciona_itin"] == 1
    assert fila["menciona_dpa"] >= 1


def test_cadencia_y_hueco():
    posts = [_post("Caption numero %d con texto suficiente para contar" % i,
                   dias_atras=d)
             for i, d in enumerate([0, 2, 4, 40, 42, 44])]
    fila = parsear_crudo(_crudo(posts=posts))
    assert fila["hueco_max_dias"] == 36
    assert fila["dias_entre_posts_mediana"] == 2.0


def test_engagement_usa_seguidores_no_es_el_proxy():
    posts = [_post("Caption con texto suficiente para que cuente aca",
                   dias_atras=i, likes=120, n_comentarios=14)
             for i in range(6)]
    fila = parsear_crudo(_crudo(posts=posts, seguidores=4000))
    assert abs(fila["engagement_rate"] - (134 / 4000)) < 1e-6


def test_engagement_sin_seguidores_es_null():
    posts = [_post("Caption con texto suficiente para que cuente aca",
                   dias_atras=i, likes=120, n_comentarios=14)
             for i in range(6)]
    fila = parsear_crudo(_crudo(posts=posts, seguidores=None))
    assert fila["engagement_rate"] is None


def test_reel_pct_y_geotags():
    posts = [
        _post("Caption con texto suficiente aca para contar bien", dias_atras=0,
              tipo="GraphVideo", geo="Round Rock, Texas"),
        _post("Caption con texto suficiente aca para contar bien", dias_atras=3,
              tipo="GraphVideo", geo="Round Rock, Texas"),
        _post("Caption con texto suficiente aca para contar bien", dias_atras=6,
              tipo="GraphImage", geo="Pflugerville, Texas"),
        _post("Caption con texto suficiente aca para contar bien", dias_atras=9,
              tipo="GraphSidecar", hijos=3),
    ]
    fila = parsear_crudo(_crudo(posts=posts))
    assert fila["tipo_post_reel_pct"] == 50.0
    assert fila["geotags_top"].startswith("Round Rock, Texas (2)")


def test_designaciones_y_destacadas_existen_aun_en_privado():
    fila = parsear_crudo(_crudo(estado="privado", privado=True, posts=[]))
    assert "ABR" in fila["designaciones"]
    assert "GRI" in fila["designaciones"]
    assert "FHA" in fila["destacadas_titulos"]


# ══ FORMATO DEL TEXTO CRUDO ═══════════════════════════════════════════════════

def test_captions_texto_es_cronologico_inverso_con_fecha():
    posts = [
        _post("El mas viejo de todos, con texto suficiente para que cuente",
              dias_atras=30),
        _post("El del medio, tambien con texto suficiente para que cuente",
              dias_atras=15),
        _post("El mas reciente, con texto suficiente para que cuente bien",
              dias_atras=0),
    ]
    fila = parsear_crudo(_crudo(posts=posts))
    piezas = fila["captions_texto"].split(SEP)
    assert len(piezas) == 3
    assert piezas[0].startswith("2026-08-20 | El mas reciente")
    assert piezas[-1].startswith("2026-07-21 | El mas viejo")
    assert " | " in piezas[0]


def test_los_saltos_de_linea_se_vuelven_espacio():
    posts = [_post("Primera linea del caption\n\nSegunda linea con mas texto",
                   dias_atras=0)]
    fila = parsear_crudo(_crudo(posts=posts))
    assert "\n" not in fila["captions_texto"]
    assert "caption Segunda" in fila["captions_texto"]


def test_los_comentarios_van_sin_el_handle_del_autor():
    posts = [_post("Nueva casa en Austin con texto suficiente aca", dias_atras=0)]
    comentarios = {"SC0": [
        {"texto": "Cuanto de enganche necesito?", "autor_handle": "jose_perez_1988"},
        {"texto": "Se puede con ITIN sin seguro social?", "autor_handle": "maria_l"},
        {"texto": "Escribeme por privado y lo vemos", "autor_handle": "anatapia_realtor"},
    ]}
    fila = parsear_crudo(_crudo(posts=posts, comentarios=comentarios))

    assert "jose_perez_1988" not in fila["comentarios_texto"]
    assert "maria_l" not in fila["comentarios_texto"]
    assert "Cuanto de enganche" in fila["comentarios_texto"]
    assert SEP in fila["comentarios_texto"]
    # el del agente va en su propia columna, a proposito
    assert "Escribeme por privado" in fila["comentarios_del_agente"]
    assert "Escribeme por privado" not in fila["comentarios_texto"]


def test_la_respuesta_del_agente_se_separa_porque_dice_tanto_como_el_post():
    posts = [_post("Nueva casa en Austin con texto suficiente aca", dias_atras=0)]
    comentarios = {"SC0": [
        {"texto": "Se puede con ITIN?", "autor_handle": "cliente"},
        {"texto": "Dejame consultarlo con mi lender y te digo",
         "autor_handle": "anatapia_realtor"},
    ]}
    fila = parsear_crudo(_crudo(posts=posts, comentarios=comentarios))
    assert "Dejame consultarlo" in fila["comentarios_del_agente"], (
        "si le preguntan por ITIN y contesta 'dejame consultarlo', ahi hay un "
        "dolor confirmado"
    )
    assert fila["comentarios_n"] == 1


def test_truncado_a_30000_y_declarado():
    largo = "Felicidades a la familia por su casa nueva. " * 900  # ~38.700
    posts = [_post(largo, dias_atras=0)]
    fila = parsear_crudo(_crudo(posts=posts))
    assert len(fila["captions_texto"]) == MAX_CHARS_CELDA
    assert fila["texto_truncado"] is True


def test_sin_truncar_la_bandera_es_falsa():
    posts = [_post("Caption corto pero con texto suficiente aca", dias_atras=0)]
    fila = parsear_crudo(_crudo(posts=posts))
    assert fila["texto_truncado"] is False


# ══ CONTRATO DEL CSV ══════════════════════════════════════════════════════════

def test_el_csv_tiene_las_columnas_exactas_del_brief():
    del_brief = [
        "email", "nombre", "estado", "handle", "estado_perfil", "handle_confianza",
        "captions_n", "captions_es_ratio", "comentarios_n", "comentarios_es_ratio",
        "menciona_lender", "menciona_itin", "menciona_dpa", "menciona_credito",
        "menciona_va", "menciona_fha", "menciona_primera_casa",
        "comentarios_pregunta_calificacion",
        "cuentas_hipotecarias_etiquetadas", "posts_comarketing",
        "tipo_post_reel_pct", "dias_entre_posts_mediana", "hueco_max_dias",
        "engagement_rate", "designaciones", "destacadas_titulos", "geotags_top",
    ]
    agregadas = ["captions_texto", "comentarios_texto", "comentarios_del_agente",
                 "texto_truncado"]
    assert COLUMNAS_CSV == del_brief + agregadas, (
        "el orden y los nombres son contrato con la app que consume el archivo"
    )


def test_ida_y_vuelta_por_disco_con_bom_y_comillas():
    tmp = Path(tempfile.mkdtemp())
    try:
        dir_crudo = tmp / "ig_raw"
        ruta_csv = tmp / "ig_signals.csv"

        objetivo = Objetivo(
            email="ana@casaprorealty.com", nombre="ANA TAPIA", estado="Texas",
            handle_del_libro="anatapia_realtor", nivel="MQL", tier="A",
        )
        posts = [
            _post('Caption con "comillas dobles" y coma, que rompen un CSV mal hecho',
                  dias_atras=0),
            _post("Felicidades a la familia Ramirez por su primera casa hermosa",
                  dias_atras=7),
        ]
        guardar_crudo(objetivo, _crudo(posts=posts), dir_crudo=dir_crudo)

        privado = Objetivo(
            email="luis@x.com", nombre="LUIS GOMEZ", estado="Florida",
            handle_del_libro="luisgomez_re", nivel="MQL", tier="B",
        )
        guardar_crudo(privado,
                      _crudo(estado="privado", privado=True, posts=[],
                             handle="luisgomez_re",
                             nombre_visible="Luis Gomez",
                             nombre_objetivo="LUIS GOMEZ"),
                      dir_crudo=dir_crudo)

        informe = parsear_crudos(dir_crudo=dir_crudo, ruta_csv=ruta_csv)
        assert informe["filas_escritas"] == 2
        assert informe["ilegibles"] == []
        assert informe["motor_idioma"] == "lingua"

        crudo_bytes = ruta_csv.read_bytes()
        assert crudo_bytes.startswith(b"\xef\xbb\xbf"), "falta el BOM para Excel"

        with ruta_csv.open("r", encoding="utf-8-sig", newline="") as fh:
            filas = list(csv.DictReader(fh))
        assert list(filas[0].keys()) == COLUMNAS_CSV
        assert len(filas) == 2

        por_handle = {f["handle"]: f for f in filas}
        ana = por_handle["anatapia_realtor"]
        assert 'comillas dobles' in ana["captions_texto"]
        assert ana["captions_n"] == "2"

        luis = por_handle["luisgomez_re"]
        assert luis["estado_perfil"] == "privado"
        assert luis["captions_es_ratio"] == "", (
            "en el CSV un null es celda vacia, no 0"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_un_crudo_roto_no_tumba_la_pasada():
    tmp = Path(tempfile.mkdtemp())
    try:
        dir_crudo = tmp / "ig_raw"
        dir_crudo.mkdir(parents=True)
        (dir_crudo / "roto.json").write_text("{esto no es json", encoding="utf-8")

        objetivo = Objetivo(email="ok@x.com", nombre="ANA TAPIA", estado="Texas",
                            handle_del_libro="anatapia_realtor", nivel="MQL",
                            tier="A")
        guardar_crudo(objetivo,
                      _crudo(posts=[_post("Caption con texto suficiente aca",
                                          dias_atras=0)]),
                      dir_crudo=dir_crudo)

        informe = parsear_crudos(dir_crudo=dir_crudo, ruta_csv=tmp / "s.csv")
        assert informe["filas_escritas"] == 1
        assert "roto.json" in informe["ilegibles"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_la_clave_de_archivo_prefiere_email_y_se_sanea():
    assert Objetivo(email="Ana.Tapia@KW.com", nombre="A", estado=None,
                    handle_del_libro="x", nivel=None, tier=None
                    ).clave == "ana.tapia@kw.com"
    assert Objetivo(email=None, nombre="A", estado=None,
                    handle_del_libro="@Ana_Tapia", nivel=None, tier=None
                    ).clave == "ana_tapia"
    assert Objetivo(email=None, nombre="Ana Tapia", estado=None,
                    handle_del_libro=None, nivel=None, tier=None
                    ).clave == "ana_tapia"
    # nada de separadores de ruta en un nombre de archivo
    sucio = Objetivo(email="a/b\\c:d@x.com", nombre="A", estado=None,
                     handle_del_libro=None, nivel=None, tier=None).clave
    assert "/" not in sucio and "\\" not in sucio and ":" not in sucio


def test_el_crudo_guardado_conserva_el_objetivo_y_no_deriva_nada():
    tmp = Path(tempfile.mkdtemp())
    try:
        objetivo = Objetivo(email="ana@x.com", nombre="ANA TAPIA", estado="Texas",
                            handle_del_libro="anatapia_realtor", nivel="MQL",
                            tier="A")
        ruta = guardar_crudo(objetivo, _crudo(posts=[_post("Hola", dias_atras=0)]),
                             dir_crudo=tmp)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        assert datos["objetivo"]["email"] == "ana@x.com"
        assert datos["objetivo"]["nivel"] == "MQL"
        assert "capturado_en" in datos
        # nada derivado en el crudo
        for prohibido in ("captions_es_ratio", "menciona_lender", "idioma",
                          "engagement_rate"):
            assert prohibido not in datos, (
                "el crudo no deriva nada: %s no deberia estar" % prohibido
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
