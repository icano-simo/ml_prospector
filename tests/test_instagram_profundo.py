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

from instagram.extraccion import _evaluar_truncamiento  # noqa: E402
from instagram.finder import (  # noqa: E402
    COLUMNAS_CSV,
    MAX_CHARS_CELDA,
    RUTA_LIBRO_PACS,
    SEP,
    Objetivo,
    cargar_objetivo,
    guardar_crudo,
    parsear_crudo,
    parsear_crudos,
    revisar_piloto,
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


def test_un_email_en_el_caption_no_inventa_un_lender():
    """El caso que habria producido un socio hipotecario inexistente.

    `maria@titlecompanyx.com` contiene la pista `title`, asi que con el patron
    ingenuo `menciona_lender` habria salido `@titlecompanyx.com`: una cuenta
    que no existe, presentada como el lender del agente. Una firma de contacto
    inventando la categoria S6 es peor que S6 vacia.
    """
    posts = [
        _post("Escribime a maria@titlecompanyx.com para cualquier consulta",
              dias_atras=i)
        for i in range(5)
    ]
    fila = parsear_crudo(_crudo(posts=posts))
    assert fila["menciona_lender"] is None, fila["menciona_lender"]
    assert fila["cuentas_hipotecarias_etiquetadas"] is None


def test_la_firma_de_contacto_no_infla_el_co_marketing():
    """`tiene_socio` se ponia en True con cualquier email en el caption, asi
    que casi todo post con firma y la palabra taller contaba como
    co-marketing."""
    solo = _post("Taller de compradores este sabado. Escribime a ana@exp.com",
                 dias_atras=0)
    assert parsear_crudo(_crudo(posts=[solo]))["posts_comarketing"] == 0


def test_mencionarse_a_si_mismo_no_es_un_socio():
    """En la captura real el agente se menciona en sus propios captions.

    `_crudo` usa @anatapia_realtor como handle del perfil.
    """
    posts = [
        _post("Taller de compradores este sabado con @anatapia_realtor",
              dias_atras=0, etiquetadas=["anatapia_realtor"]),
    ]
    fila = parsear_crudo(_crudo(posts=posts))
    assert fila["posts_comarketing"] == 0
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


# ══ REDACCION EN LA COLUMNA DE TEXTO ══════════════════════════════════════════
#
# El hueco que estas pruebas cierran: redactar() existia en comentarios.py y
# corria en Comentario.desde_crudo, pero parsear_crudo armaba
# comentarios_texto leyendo el crudo directo, sin pasar por ahi. La guarda
# estaba escrita y no enchufada, y en el piloto real aparecio un comentario con
# telefono y email dentro.

def test_el_telefono_de_un_tercero_no_llega_al_csv():
    posts = [_post("Nueva casa en Austin con texto suficiente aca", dias_atras=0)]
    comentarios = {"SC0": [
        {"texto": "Me interesa, llamame al (773) 362-5798 cuando puedas",
         "autor_handle": "cliente_interesado"},
    ]}
    fila = parsear_crudo(_crudo(posts=posts, comentarios=comentarios))

    assert "773" not in fila["comentarios_texto"]
    assert "362-5798" not in fila["comentarios_texto"]
    assert "[telefono]" in fila["comentarios_texto"]
    assert "Me interesa" in fila["comentarios_texto"], (
        "se redacta el dato personal, no el comentario: el texto es la senal S8"
    )
    assert "telefono (1)" in fila["comentarios_redactados"]


def test_el_email_y_la_mencion_de_un_tercero_tampoco():
    posts = [_post("Nueva casa en Austin con texto suficiente aca", dias_atras=0)]
    comentarios = {"SC0": [
        {"texto": "Escribeme a jose.perez@gmail.com o hablale a @otro_agente",
         "autor_handle": "cliente"},
    ]}
    fila = parsear_crudo(_crudo(posts=posts, comentarios=comentarios))

    assert "gmail.com" not in fila["comentarios_texto"]
    assert "@otro_agente" not in fila["comentarios_texto"]
    assert "[email]" in fila["comentarios_texto"]
    assert "[cuenta]" in fila["comentarios_texto"]
    assert "email" in fila["comentarios_redactados"]
    assert "mencion" in fila["comentarios_redactados"]


def test_el_comentario_del_agente_conserva_su_contacto():
    """El agente es nuestro prospecto: su telefono ya lo tenemos de MMI.

    Que lo publique en sus propios comentarios es informacion de negocio, no
    un dato de tercero. La asimetria es deliberada.
    """
    posts = [_post("Nueva casa en Austin con texto suficiente aca", dias_atras=0)]
    comentarios = {"SC0": [
        {"texto": "Llamame al (773) 362-5798 y lo vemos",
         "autor_handle": "anatapia_realtor"},
    ]}
    fila = parsear_crudo(_crudo(posts=posts, comentarios=comentarios))

    assert "(773) 362-5798" in fila["comentarios_del_agente"]
    assert fila["comentarios_texto"] is None
    assert fila["comentarios_redactados"] is None


def test_sin_datos_personales_no_hay_nada_que_declarar():
    posts = [_post("Nueva casa en Austin con texto suficiente aca", dias_atras=0)]
    comentarios = {"SC0": [
        {"texto": "Cuanto de enganche necesito para esa?", "autor_handle": "x"},
    ]}
    fila = parsear_crudo(_crudo(posts=posts, comentarios=comentarios))
    assert fila["comentarios_redactados"] is None
    assert "Cuanto de enganche" in fila["comentarios_texto"]


def test_la_guarda_redundante_falla_ruidosamente():
    """La guarda es redundante a proposito: si otra via arma la columna sin
    redactar, tiene que reventar y no publicar el telefono."""
    from instagram.finder import _verificar_sin_pii_de_terceros

    _verificar_sin_pii_de_terceros(None)
    _verificar_sin_pii_de_terceros("Cuanto de enganche necesito?")

    for crudo in ("llamame al (773) 362-5798", "escribe a a@b.com", "id 12345678"):
        try:
            _verificar_sin_pii_de_terceros(crudo)
        except AssertionError:
            pass
        else:
            raise AssertionError("no fallo con %r" % crudo)


def test_la_pregunta_de_calificacion_sobrevive_a_la_redaccion():
    """La redaccion no puede comerse la senal S8."""
    posts = [_post("Nueva casa en Austin con texto suficiente aca", dias_atras=0)]
    comentarios = {"SC0": [
        {"texto": "Se puede con ITIN? mi numero es 773-362-5798",
         "autor_handle": "cliente"},
    ]}
    fila = parsear_crudo(_crudo(posts=posts, comentarios=comentarios))
    assert fila["comentarios_pregunta_calificacion"] == 1
    assert "[telefono]" in fila["comentarios_texto"]


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
                 "texto_truncado", "comentarios_redactados", "paginacion_truncada"]
    # Las 17 del Bloque 1-ter, en el orden exacto de ese brief.
    del_brief_1ter = [
        "audiencia_segmentos", "audiencia_dominante",
        "temas", "tema_dominante", "ratio_educa_vs_anuncia",
        "idioma_publica_es", "idioma_publica_en",
        "idioma_comentarios_es", "idioma_comentarios_en", "desajuste_idioma",
        "registro", "marcadores_culturales",
        "precios_mencionados", "barrios_mencionados", "programas_mencionados",
        "preguntas_recibidas",
        "citas_por_etiqueta",
    ]
    assert COLUMNAS_CSV == del_brief + agregadas + del_brief_1ter, (
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


# ══ PAGINACION TRUNCADA ═══════════════════════════════════════════════════════
#
# La regla: si el perfil declara N publicaciones y se recuperaron menos del 60%
# de las solicitadas SIN que haya llegado el fin de la paginacion, se marca
# paginacion_truncada y captions_es_ratio va a null.
#
# Un ratio sobre una muestra truncada no es una medicion peor: es otra cosa.

def _crudo_paginado(*, recuperados, solicitados, declaradas, fin_paginacion,
                    captions_es=None):
    """Crudo con la contabilidad de paginacion puesta a mano."""
    if captions_es is None:
        captions_es = recuperados  # todos en español, para que el ratio sea 1.0
    posts = []
    for i in range(recuperados):
        if i < captions_es:
            texto = ("Felicidades a la familia Ramirez por su casa nueva, "
                     "que la disfruten mucho")
        else:
            texto = ("Congratulations to the Smith family on closing today, "
                     "so happy for them")
        posts.append(_post(texto, dias_atras=i * 3))

    c = _crudo(posts=posts)
    c["perfil"]["n_publicaciones"] = declaradas
    c["posts_solicitados"] = solicitados
    c["posts_recuperados"] = recuperados
    c["n_publicaciones_declaradas"] = declaradas
    c["fin_de_paginacion"] = fin_paginacion
    _evaluar_truncamiento(c, solicitados)
    return c


def test_doce_de_treinta_con_mas_paginas_es_truncada():
    """El caso del query_hash caducado: llegan 12 clavados y hay mas."""
    c = _crudo_paginado(recuperados=12, solicitados=30, declaradas=340,
                        fin_paginacion=False)
    assert c["paginacion_truncada"] is True
    assert "12 de 30" in c["motivo_truncamiento"]
    assert "340 publicaciones" in c["motivo_truncamiento"]

    fila = parsear_crudo(c)
    assert fila["paginacion_truncada"] is True
    assert fila["captions_es_ratio"] is None, (
        "un ratio sobre muestra truncada no se reporta"
    )
    assert fila["captions_n"] == 12, (
        "captions_n SI se conserva: es la evidencia de por que el ratio esta vacio"
    )


def test_dieciocho_de_treinta_alcanza_el_60_por_ciento():
    """18/30 = 60% exacto: no esta truncada."""
    c = _crudo_paginado(recuperados=18, solicitados=30, declaradas=340,
                        fin_paginacion=False)
    assert c["paginacion_truncada"] is False
    fila = parsear_crudo(c)
    assert fila["captions_es_ratio"] == 1.0


def test_diecisiete_de_treinta_no_alcanza():
    c = _crudo_paginado(recuperados=17, solicitados=30, declaradas=340,
                        fin_paginacion=False)
    assert c["paginacion_truncada"] is True
    assert parsear_crudo(c)["captions_es_ratio"] is None


def test_perfil_chico_agotado_no_es_truncamiento():
    """Pedirle 30 posts a quien tiene 8 no es un truncamiento: es un perfil chico."""
    c = _crudo_paginado(recuperados=8, solicitados=30, declaradas=8,
                        fin_paginacion=True)
    assert c["paginacion_truncada"] is False
    fila = parsear_crudo(c)
    assert fila["captions_es_ratio"] == 1.0, (
        "8 de 8 es la muestra completa, no el 27% de 30"
    )


def test_perfil_chico_sin_llegar_al_final_se_mide_contra_lo_declarado():
    """Declara 10, pedimos 30, trajimos 7: el umbral es 60% de 10, no de 30."""
    c = _crudo_paginado(recuperados=7, solicitados=30, declaradas=10,
                        fin_paginacion=False)
    assert c["posts_esperados"] == 10
    assert c["paginacion_truncada"] is False, "7 de 10 es el 70%"


def test_fin_de_paginacion_gana_sobre_el_umbral():
    """Si el timeline se agoto, no hay nada truncado por definicion."""
    c = _crudo_paginado(recuperados=3, solicitados=30, declaradas=3,
                        fin_paginacion=True)
    assert c["paginacion_truncada"] is False
    assert c["motivo_truncamiento"] is None


def test_privado_no_tiene_truncamiento_sino_estado():
    """No se leyo el timeline: no hay muestra que truncar. El estado ya lo dice."""
    c = _crudo(estado="privado", privado=True, posts=[])
    c["perfil"]["n_publicaciones"] = 400
    c["fin_de_paginacion"] = None
    _evaluar_truncamiento(c, 30)
    assert c["paginacion_truncada"] is None
    fila = parsear_crudo(c)
    assert fila["paginacion_truncada"] is None
    assert fila["captions_es_ratio"] is None
    assert fila["estado_perfil"] == "privado"


def test_la_columna_de_truncamiento_esta_en_el_contrato():
    from instagram.audiencia import COLUMNAS_AUDIENCIA

    assert "paginacion_truncada" in COLUMNAS_CSV
    # Era la ultima hasta que el Bloque 1-ter agrego 17 columnas DESPUES. Lo
    # que el contrato protege es que nada se inserte ANTES, o sea que ningun
    # indice de lo que la app ya consume se mueva.
    corte = len(COLUMNAS_CSV) - len(COLUMNAS_AUDIENCIA)
    assert COLUMNAS_CSV[corte - 1] == "paginacion_truncada", (
        "lo nuevo va al final para no mover el orden que ya consume la app"
    )


def test_el_truncamiento_llega_al_csv():
    tmp = Path(tempfile.mkdtemp())
    try:
        dir_crudo = tmp / "ig_raw"
        ruta_csv = tmp / "s.csv"
        obj = Objetivo(email="ana@x.com", nombre="ANA TAPIA", estado="Texas",
                       handle_del_libro="anatapia_realtor", nivel="MQL", tier="A")
        guardar_crudo(obj, _crudo_paginado(recuperados=12, solicitados=30,
                                           declaradas=340, fin_paginacion=False),
                      dir_crudo=dir_crudo)
        parsear_crudos(dir_crudo=dir_crudo, ruta_csv=ruta_csv)
        with ruta_csv.open("r", encoding="utf-8-sig", newline="") as fh:
            fila = list(csv.DictReader(fh))[0]
        assert fila["paginacion_truncada"] == "True"
        assert fila["captions_es_ratio"] == ""
        assert fila["captions_n"] == "12"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_el_crudo_registra_la_contabilidad_de_paginacion():
    """Son hechos de la captura, no derivaciones: van en el crudo."""
    tmp = Path(tempfile.mkdtemp())
    try:
        obj = Objetivo(email="ana@x.com", nombre="ANA TAPIA", estado="Texas",
                       handle_del_libro="anatapia_realtor", nivel="MQL", tier="A")
        ruta = guardar_crudo(obj, _crudo_paginado(recuperados=12, solicitados=30,
                                                  declaradas=340,
                                                  fin_paginacion=False),
                             dir_crudo=tmp)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        for campo in ("posts_solicitados", "posts_recuperados",
                      "fin_de_paginacion", "paginacion_truncada",
                      "motivo_truncamiento", "posts_esperados",
                      "n_publicaciones_declaradas"):
            assert campo in datos, campo
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══ EL PILOTO · DOCE CLAVADOS ═════════════════════════════════════════════════

def test_el_piloto_detecta_los_doce_clavados():
    """Si todos los perfiles traen exactamente 12, el query_hash caduco."""
    tmp = Path(tempfile.mkdtemp())
    try:
        dir_crudo = tmp / "ig_raw"
        for i in range(4):
            obj = Objetivo(email="r%d@x.com" % i, nombre="ANA TAPIA",
                           estado="Texas", handle_del_libro="anatapia_realtor",
                           nivel="MQL", tier="A")
            guardar_crudo(obj, _crudo_paginado(recuperados=12, solicitados=30,
                                               declaradas=200,
                                               fin_paginacion=False),
                          dir_crudo=dir_crudo)
        informe = revisar_piloto(dir_crudo=dir_crudo, n=20)
        assert informe["exactamente_doce"] == 4
        assert informe["hashes_caducados"] is True
        assert informe["parar"] is True
        assert informe["paginacion_truncada"] == 4
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_doce_de_doce_declarados_y_agotados_no_es_alarma():
    """La falsa alarma real: @miguelsanchezz7_ declara 12 y trajo 12.

    Una alarma que suena cuando todo esta bien entrena a ignorarla, y esta en
    particular es la que decide si hay que parar el lote.
    """
    import io
    from contextlib import redirect_stdout

    tmp = Path(tempfile.mkdtemp())
    try:
        dir_crudo = tmp / "ig_raw"
        dir_crudo.mkdir()
        c = _crudo(posts=[_post("Caption con texto suficiente numero %d" % i,
                                dias_atras=i) for i in range(12)])
        c["posts_recuperados"] = 12
        c["n_publicaciones_declaradas"] = 12
        c["fin_de_paginacion"] = True
        (dir_crudo / "uno.json").write_text(json.dumps(c), encoding="utf-8")

        salida = io.StringIO()
        with redirect_stdout(salida):
            revisar_piloto(dir_crudo=dir_crudo)
        texto = salida.getvalue()

        assert "DETENERSE" not in texto, texto
        assert "exactamente 12 posts" not in texto, (
            "12 de 12 declarados y agotados es un perfil completo"
        )
        assert "la paginacion corrio" in texto
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_el_piloto_no_alarma_cuando_la_paginacion_corre():
    tmp = Path(tempfile.mkdtemp())
    try:
        dir_crudo = tmp / "ig_raw"
        for i, n_posts in enumerate((30, 28, 24, 30)):
            obj = Objetivo(email="r%d@x.com" % i, nombre="ANA TAPIA",
                           estado="Texas", handle_del_libro="anatapia_realtor",
                           nivel="MQL", tier="A")
            guardar_crudo(obj, _crudo_paginado(recuperados=n_posts,
                                               solicitados=30, declaradas=200,
                                               fin_paginacion=False),
                          dir_crudo=dir_crudo)
        informe = revisar_piloto(dir_crudo=dir_crudo, n=20)
        assert informe["exactamente_doce"] == 0
        assert informe["hashes_caducados"] is False
        assert informe["paginacion_truncada"] == 0
        assert informe["sospecha_alt_text"] is False
        assert informe["parar"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_el_piloto_alarma_si_el_ratio_ronda_el_tres_por_ciento():
    """El criterio de parada: si ronda el 3%, algo sigue mal."""
    tmp = Path(tempfile.mkdtemp())
    try:
        dir_crudo = tmp / "ig_raw"
        for i in range(4):
            obj = Objetivo(email="r%d@x.com" % i, nombre="ANA TAPIA",
                           estado="Texas", handle_del_libro="anatapia_realtor",
                           nivel="MQL", tier="A")
            # 30 captions, ninguno en español
            guardar_crudo(obj, _crudo_paginado(recuperados=30, solicitados=30,
                                               declaradas=200,
                                               fin_paginacion=False,
                                               captions_es=0),
                          dir_crudo=dir_crudo)
        informe = revisar_piloto(dir_crudo=dir_crudo, n=20)
        assert informe["captions_es_ratio_media"] == 0.0
        assert informe["sospecha_alt_text"] is True
        assert informe["parar"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ══ LA COMPROBACION DE SESION ═════════════════════════════════════════════════
#
# Esta comprobacion dio un FALSO POSITIVO el 2026-09-21: decia "sesion
# detectada" porque encontraba `a[href^='/explore/']`, que tambien existe en la
# pagina sin sesion. El endpoint JSON devolvia 401 con require_login=true y no
# habia ni una cookie de sesion.
#
# El veredicto lo dan las cookies, que son el token, no el DOM.

class _ContextoFalso:
    def __init__(self, cookies):
        self._cookies = cookies

    def cookies(self, url):  # noqa: ARG002
        return self._cookies


class _PaginaFalsa:
    def __init__(self, cookies, selectores_presentes=()):
        self.context = _ContextoFalso(cookies)
        self._presentes = set(selectores_presentes)

    def goto(self, *a, **k):  # noqa: ARG002
        return None

    def query_selector(self, selector):
        return object() if selector in self._presentes else None


def _cookie(nombre, valor="x" * 20):
    return {"name": nombre, "value": valor}


# ══ ENLACE DE BIO · el badge de Threads y el destino envuelto ════════════════
#
# Tres defectos medidos en la captura real del piloto:
#
#   el selector devolvia `https://www.threads.com/@gussellz?xmt=...` en 3 de 9
#   perfiles -- el badge de Threads del header, no un enlace del agente;
#
#   `destino_enlace_bio` era null en los 14, aunque el envoltorio traia el
#   destino a la vista en el parametro `u=`. El paso que lo resolvia vive en
#   `capturar_crudo` DESPUES del `return` de la ruta DOM, o sea que nunca corria
#   en el camino que se ejecuta;
#
#   y al arreglarlo puse `instagram.com` en la lista de exclusion, que mata el
#   caso bueno: `l.instagram.com` ES el envoltorio legitimo. Los 13 destinos se
#   fueron a None de golpe. Esa es la ultima prueba de este bloque.

class _PaginaConEnlaces:
    """Devuelve varios <a> por selector, en orden de DOM."""

    def __init__(self, por_selector):
        self._por_selector = por_selector

    def query_selector_all(self, selector):
        hrefs = self._por_selector.get(selector, [])
        return [_Elemento(h) for h in hrefs]


class _Elemento:
    def __init__(self, href):
        self._href = href

    def get_attribute(self, nombre):
        return self._href if nombre == "href" else None


# ══ EL `privado` INFERIDO POR AUSENCIA ════════════════════════════════════════

def test_un_privado_heredado_sin_aviso_se_reclasifica_a_sin_grid():
    """Los 7 del piloto. El HTML no se guardaba, pero la evidencia si.

    `estado_evidencia` dice literalmente «cero posts y sin aviso de cuenta
    privada», o sea que el propio crudo registra que no se vio ningun texto de
    privacidad. Eso alcanza para descartar `privado`.
    """
    from instagram.finder import reclasificar_estado_heredado

    crudo = _crudo(posts=[], estado="privado")
    crudo["estado_evidencia"] = (
        "se leyo el meta pero cero posts y sin aviso de cuenta privada: puede "
        "ser cuenta sin publicaciones o render parcial"
    )
    crudo["perfil"]["n_publicaciones"] = 731
    assert reclasificar_estado_heredado(crudo) == "sin_grid"

    fila = parsear_crudo(crudo)
    assert fila["estado_perfil"] == "sin_grid"
    assert fila["captions_es_ratio"] is None, "las señales siguen en null"
    assert fila["captions_n"] is None


def test_un_privado_heredado_CON_aviso_se_respeta():
    """Si el crudo viejo si vio el texto de privacidad, era privado."""
    from instagram.finder import reclasificar_estado_heredado

    crudo = _crudo(posts=[], estado="privado")
    crudo["estado_evidencia"] = "texto de cuenta privada: 'this account is private'"
    assert reclasificar_estado_heredado(crudo) == "privado"


def test_un_crudo_nuevo_no_se_reclasifica():
    """Trae `marcadores_de_estado`, asi que el diagnostico ya corrio bien."""
    from instagram.finder import reclasificar_estado_heredado

    crudo = _crudo(posts=[], estado="privado")
    crudo["estado_evidencia"] = "el JSON del perfil trae is_private = true"
    crudo["marcadores_de_estado"] = {"is_private_json": True}
    assert reclasificar_estado_heredado(crudo) == "privado"


def test_cero_publicaciones_declaradas_va_a_vacio_no_a_sin_grid():
    from instagram.finder import reclasificar_estado_heredado

    crudo = _crudo(posts=[], estado="privado")
    crudo["estado_evidencia"] = "cero posts y sin aviso de cuenta privada"
    crudo["perfil"]["n_publicaciones"] = 0
    assert reclasificar_estado_heredado(crudo) == "vacio"


def test_los_estados_nuevos_llegan_al_csv_con_su_nombre():
    """El enum del CSV pasa de 5 valores a 9, a proposito.

    Mapearlos de vuelta a los cinco viejos escondería la distincion que existen
    para hacer. Lo que NO cambia es `publico_leido`, que es el valor sobre el
    que se filtra para saber si hay contenido.
    """
    from instagram.finder import MAPA_ESTADO_CSV

    for nuevo in ("muro_de_sesion", "sin_grid", "degradado", "vacio"):
        assert MAPA_ESTADO_CSV[nuevo] == nuevo
    assert MAPA_ESTADO_CSV["publico_leido"] == "publico_leido"


def test_el_freno_por_degradacion_no_salta_con_la_tasa_del_piloto():
    """7 de 20 repartidos NO es degradacion, y el freno no debe confundirlos.

    Un freno que salta con la tasa normal de perfiles raros para el lote de
    diez horas sin motivo, y uno que nunca salta no sirve de nada.
    """
    from instagram.finder import (
        MAX_SIN_CONTENIDO_EN_VENTANA,
        VENTANA_DEGRADACION,
    )

    # El patron real del piloto: posiciones 2,3,5,9,13,16,20 de 20.
    piloto = [i in (2, 3, 5, 9, 13, 16, 20) for i in range(1, 21)]
    salto = False
    ventana = []
    for sin_contenido in piloto:
        ventana.append(sin_contenido)
        if len(ventana) > VENTANA_DEGRADACION:
            ventana.pop(0)
        if (len(ventana) == VENTANA_DEGRADACION
                and sum(ventana) >= MAX_SIN_CONTENIDO_EN_VENTANA):
            salto = True
    assert not salto, "el piloto no fue degradacion y el freno no debe decir que si"


def test_el_freno_si_salta_con_una_sesion_que_se_cae():
    """Diez perfiles seguidos sin contenido despues de una racha buena."""
    from instagram.finder import (
        MAX_SIN_CONTENIDO_EN_VENTANA,
        VENTANA_DEGRADACION,
    )

    caida = [False] * 10 + [True] * 10
    salto_en = None
    ventana = []
    for i, sin_contenido in enumerate(caida, 1):
        ventana.append(sin_contenido)
        if len(ventana) > VENTANA_DEGRADACION:
            ventana.pop(0)
        if (len(ventana) == VENTANA_DEGRADACION
                and sum(ventana) >= MAX_SIN_CONTENIDO_EN_VENTANA
                and salto_en is None):
            salto_en = i
    assert salto_en is not None, "una sesion caida tiene que frenar el lote"
    assert salto_en <= 17, (
        "y frenar pronto: cada perfil de mas son tres minutos escribiendo nulos"
    )


def test_solo_vuelven_al_monton_los_que_no_se_leyeron():
    """`--reintentar-ilegibles` sobre un checkpoint con los cuatro casos."""
    from instagram.finder import _claves_reintentables, guardar_crudo
    from instagram.finder import Objetivo

    tmp = Path(tempfile.mkdtemp())
    try:
        dir_crudo = tmp / "ig_raw"
        dir_crudo.mkdir()

        casos = {
            # el caso de los siete del piloto: `privado` heredado por ausencia
            "viejo@x.com": ("privado", "cero posts y sin aviso de cuenta privada"),
            # un privado de verdad
            "priv@x.com": ("privado", "texto de cuenta privada: 'this account is private'"),
            "singrid@x.com": ("sin_grid", "la cuadricula no rindio"),
            "vacio@x.com": ("vacio", "declara 0 publicaciones"),
            "ok@x.com": ("publico_leido", "20 contenedores de post leidos"),
        }
        for clave, (estado, evidencia) in casos.items():
            c = _crudo(posts=[], estado=estado)
            c["estado_evidencia"] = evidencia
            c["perfil"]["n_publicaciones"] = 0 if estado == "vacio" else 300
            (dir_crudo / ("%s.json" % clave)).write_text(
                json.dumps(c), encoding="utf-8")

        vuelven = _claves_reintentables(set(casos), dir_crudo=dir_crudo)
        assert vuelven == {"viejo@x.com", "singrid@x.com"}, vuelven
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_un_crudo_que_falta_en_disco_vuelve_al_monton():
    from instagram.finder import _claves_reintentables

    tmp = Path(tempfile.mkdtemp())
    try:
        dir_crudo = tmp / "ig_raw"
        dir_crudo.mkdir()
        assert _claves_reintentables({"fantasma@x.com"},
                                     dir_crudo=dir_crudo) == {"fantasma@x.com"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sin_grid_es_reintentable_y_privado_no():
    """La mitad del punto de separarlos: el reintento alcanza a uno y al otro no."""
    from instagram.estado import EstadoPerfil

    assert EstadoPerfil.SIN_GRID.conviene_reintentar is True
    assert EstadoPerfil.MURO_DE_SESION.conviene_reintentar is True
    assert EstadoPerfil.DEGRADADO.conviene_reintentar is True
    assert EstadoPerfil.PRIVADO.conviene_reintentar is False
    assert EstadoPerfil.VACIO.conviene_reintentar is False, (
        "una cuenta sin publicaciones no mejora reintentando"
    )


# ══ EL CARRUSEL DE SUGERENCIAS ════════════════════════════════════════════════

def test_el_carrusel_de_sugerencias_no_son_destacadas():
    """@alanlozano_12: veinte entradas, diez pares de handle y nombre.

    Son cuentas que Instagram sugiere, no personas con las que el agente tiene
    relacion.
    """
    carrusel = [
        "lauren.fischerhomes", "Lauren | Fischer Homes",
        "rajabovdavron282", "Davron Rajabov",
        "chela.aguilar.94", "Chela Aguilar",
        "carsonthacker", "Carson Thacker",
        "quietskysmedia", "Indiana Real Estate Media",
        "caleybendell.realtor", "Caley Bendell | IN Real Estate",
    ]
    crudo = _crudo(posts=[], estado="privado")
    crudo["perfil"]["titulos_destacadas"] = carrusel
    fila = parsear_crudo(crudo)
    assert fila["destacadas_titulos"] is None, fila["destacadas_titulos"]


def test_las_destacadas_de_verdad_sobreviven():
    reales = ["⭐️⭐️⭐️⭐️⭐️", "2026 Vibes", "Recognitions 🙏", "New Listings 🏡",
              "2023 Sales", "R E A L T O R", "closings", "home tours"]
    crudo = _crudo(posts=[], estado="privado")
    crudo["perfil"]["titulos_destacadas"] = reales
    fila = parsear_crudo(crudo)
    for r in reales:
        assert r in fila["destacadas_titulos"], r


def test_un_solo_titulo_con_punto_no_es_el_carrusel():
    """Hacen falta tres. Uno podria ser una destacada que se llama asi."""
    crudo = _crudo(posts=[], estado="privado")
    crudo["perfil"]["titulos_destacadas"] = ["2023 Sales", "casa.nueva", "Closings"]
    fila = parsear_crudo(crudo)
    assert "2023 Sales" in fila["destacadas_titulos"]
    assert "Closings" in fila["destacadas_titulos"]


def test_el_carrusel_no_llego_nunca_a_S6():
    """Verificado sobre el piloto: S6 no lee `titulos_destacadas`.

    Esta prueba lo fija, porque el carrusel son cuentas de otros agentes y si
    alguna se llamara `algo_lending` entraria como socio hipotecario.
    """
    crudo = _crudo(posts=[], estado="privado")
    crudo["perfil"]["titulos_destacadas"] = [
        "maria.loanofficer", "Maria | Loan Officer",
        "acme_mortgage_co", "Acme Mortgage",
        "first.lending", "First Lending",
    ]
    fila = parsear_crudo(crudo)
    assert fila["menciona_lender"] is None
    assert fila["cuentas_hipotecarias_etiquetadas"] is None
    assert fila["destacadas_titulos"] is None


def test_el_geotag_del_pie_de_pagina_no_entra_al_csv():
    """«Locations» salio 106 veces de unos 180 geotags del piloto.

    Es el enlace del pie de pagina de Instagram, que apunta a
    `/explore/locations/` y existe en todas las paginas. Se colo en
    `geotags_top`, una columna ya entregada. El scraper ya no lo captura, pero
    los crudos de antes lo tienen dentro y el crudo no se reescribe: el filtro
    del parser es lo que los deja limpios sin volver a raspar.
    """
    posts = [
        _post("Nueva casa en el sur de la ciudad, con texto suficiente",
              dias_atras=0, geo="Locations"),
        _post("Otra casa mas en la misma zona, con texto suficiente",
              dias_atras=5, geo="Locations"),
        _post("Y una tercera casa preciosa, con texto suficiente aca",
              dias_atras=9, geo="Pilsen, Chicago"),
    ]
    fila = parsear_crudo(_crudo(posts=posts))
    assert "Locations" not in (fila["geotags_top"] or ""), fila["geotags_top"]
    assert "Pilsen, Chicago" in fila["geotags_top"]


def test_el_badge_de_threads_no_es_el_enlace_de_la_bio():
    from instagram.extraccion import _link_de_bio

    pagina = _PaginaConEnlaces({
        "header a[href^='http']:not([href*='instagram.com'])":
            ["https://www.threads.com/@gussellz?xmt=AQG0LuZ"],
    })
    assert _link_de_bio(pagina) is None


def test_si_el_badge_viene_primero_el_enlace_real_no_se_pierde():
    """`query_selector` devuelve la PRIMERA coincidencia, asi que filtrar
    despues no alcanzaba: ya habia elegido."""
    from instagram.extraccion import _link_de_bio

    pagina = _PaginaConEnlaces({
        "header a[href^='http']:not([href*='instagram.com'])": [
            "https://www.threads.com/@gussellz?xmt=AQG0LuZ",
            "https://compratucasanc.com/",
        ],
    })
    assert _link_de_bio(pagina) == "https://compratucasanc.com/"


def test_el_envoltorio_de_instagram_si_es_el_enlace_de_la_bio():
    """El error que cometi arreglando lo de arriba: `instagram.com` en la lista
    de exclusion se lleva puesto `l.instagram.com`, que es el caso bueno."""
    from instagram.extraccion import _link_de_bio

    envuelto = ("https://l.instagram.com/?u=https%3A%2F%2Fbit.ly%2Fx&e=AUBt")
    pagina = _PaginaConEnlaces({
        "header a[href^='https://l.instagram.com']": [envuelto],
    })
    assert _link_de_bio(pagina) == envuelto


def test_el_destino_sale_del_envoltorio_sin_navegar():
    from instagram.extraccion import destino_envuelto

    assert destino_envuelto(
        "https://l.instagram.com/?u=https%3A%2F%2Fzenlist.com%2Fa%2Fjavier"
        ".hernandez%3Futm_source%3Dig&e=AUBxcCVL"
    ) == "https://zenlist.com/a/javier.hernandez?utm_source=ig"

    assert destino_envuelto("https://compratucasanc.com/") is None, (
        "si no es envoltorio devuelve None, para que quien llame sepa que "
        "tiene que navegar"
    )
    assert destino_envuelto(None) is None
    assert destino_envuelto("https://l.instagram.com/?e=AUBt") is None


def test_el_destino_se_limpia_de_los_parametros_de_rastreo():
    from instagram.extraccion import destino_limpio

    assert destino_limpio(
        "http://compratucasanc.com/?utm_source=ig&utm_medium=social"
        "&fbclid=PAcGRvZgJleHRu"
    ) == "http://compratucasanc.com/"
    assert destino_limpio(
        "https://zenlist.com/a/javier?utm_source=ig&ref=tarjeta"
    ) == "https://zenlist.com/a/javier?ref=tarjeta", (
        "se saca el rastreo de Instagram, no los parametros del agente"
    )
    assert destino_limpio(None) is None


def test_sin_cookies_de_sesion_no_hay_sesion_aunque_el_dom_diga_que_si():
    """El falso positivo real: explore existe sin sesion."""
    from navegador import sesion_de_instagram_iniciada

    anonimas = [_cookie(n) for n in
                ("csrftoken", "datr", "ig_did", "ig_nrcb", "mid", "wd")]
    pagina = _PaginaFalsa(anonimas, selectores_presentes=["a[href^='/explore/']"])
    hay, evidencia = sesion_de_instagram_iniciada(pagina, ir_a_home=False)

    assert hay is False, "6 cookies anonimas no son una sesion"
    assert "sessionid" in evidencia
    assert "anonimas" in evidencia


def test_con_sessionid_y_ds_user_id_si_hay_sesion():
    from navegador import sesion_de_instagram_iniciada

    cookies = [_cookie(n) for n in
               ("sessionid", "ds_user_id", "csrftoken", "mid")]
    hay, evidencia = sesion_de_instagram_iniciada(
        _PaginaFalsa(cookies), ir_a_home=False)
    assert hay is True
    assert "sessionid" in evidencia


def test_una_cookie_de_sesion_vacia_no_cuenta():
    from navegador import sesion_de_instagram_iniciada

    cookies = [{"name": "sessionid", "value": ""},
               {"name": "ds_user_id", "value": "123"}]
    hay, evidencia = sesion_de_instagram_iniciada(
        _PaginaFalsa(cookies), ir_a_home=False)
    assert hay is False
    assert "sessionid" in evidencia


def test_falta_ds_user_id_tampoco_alcanza():
    from navegador import sesion_de_instagram_iniciada

    hay, _ = sesion_de_instagram_iniciada(
        _PaginaFalsa([_cookie("sessionid")]), ir_a_home=False)
    assert hay is False


def test_el_dom_solo_sirve_como_evidencia_secundaria():
    """Si se ve el formulario de login, el mensaje lo dice."""
    from navegador import sesion_de_instagram_iniciada

    pagina = _PaginaFalsa([_cookie("mid")],
                          selectores_presentes=["input[name='username']"])
    hay, evidencia = sesion_de_instagram_iniciada(pagina, ir_a_home=False)
    assert hay is False
    assert "formulario de login" in evidencia


# ══ TOP 300 ═══════════════════════════════════════════════════════════════════

def test_el_cruce_con_top300_es_uno_a_uno():
    """Dio 301 sobre 300 filas, con un TIER D adentro. Era el cruce por nombre."""
    if not RUTA_LIBRO_PACS.exists():
        print("      (sin el libro PACS: prueba omitida)")
        return
    objetivos, informe = cargar_objetivo(solo_top300=True)
    recorte = informe["recorte_top300"]

    assert len(objetivos) == recorte["filas_en_top300"], (
        "el recorte no puede tener mas ni menos filas que la hoja"
    )
    assert recorte["filas_de_top300_sin_cruzar"] == 0

    tiers = set(informe["composicion_por_tier"])
    assert tiers <= {"A - PRIORIDAD ALTA", "B - PRIORIDAD MEDIA"}, (
        "el Top 300 es solo Tier A y B; un TIER C o D es un falso positivo "
        "del cruce: %s" % tiers
    )
    assert informe["composicion_por_tier"]["A - PRIORIDAD ALTA"] == 168
    assert informe["composicion_por_tier"]["B - PRIORIDAD MEDIA"] == 132


def test_top300_es_subconjunto_del_objetivo():
    if not RUTA_LIBRO_PACS.exists():
        print("      (sin el libro PACS: prueba omitida)")
        return
    completo, _ = cargar_objetivo()
    top, _ = cargar_objetivo(solo_top300=True)
    claves_completo = {o.clave for o in completo}
    assert {o.clave for o in top} <= claves_completo
    assert len(top) < len(completo)


def test_top300_conserva_el_orden_de_la_hoja():
    """El piloto toma los primeros N, asi que el orden tiene que ser el de la hoja.

    La hoja esta ordenada por SCORE ACCION SEPT descendente, **no por TIER**:
    hay Tier B entre los primeros veinte. Eso es correcto y esta prueba existe
    para no volver a asumir lo contrario.
    """
    if not RUTA_LIBRO_PACS.exists():
        print("      (sin el libro PACS: prueba omitida)")
        return
    from instagram.finder import cargar_top300

    top, _ = cargar_objetivo(solo_top300=True)
    por_email, por_nombre, orden = cargar_top300()

    puestos = []
    for o in top:
        clave = (o.email or "").strip().lower()
        datos = por_email.get(clave)
        if datos is None:
            from instagram.finder import _clave_de_nombre
            datos = por_nombre.get(_clave_de_nombre(o.nombre))
        assert datos is not None, o.nombre
        puestos.append(datos["puesto"])

    assert puestos == sorted(puestos), "el orden de la hoja no se conservo"
    assert puestos[0] == 1, "el primero del lote tiene que ser el puesto 1"
    assert len(set(puestos)) == len(puestos), "hay puestos repetidos"

    # Y solo Tier A o B, que es de lo que esta hecha la hoja.
    assert all(o.tier and o.tier[0] in "AB" for o in top[:20]), (
        [o.tier for o in top[:20]]
    )


def test_el_handle_se_completa_desde_la_url_del_top300():
    from instagram.finder import _con_handle

    sin_handle = Objetivo(email="a@x.com", nombre="A B", estado="TX",
                          handle_del_libro=None, nivel="MQL", tier="A")
    con = _con_handle(sin_handle, {"handle_de_url": "ana_realtor", "puesto": 1})
    assert con.handle_del_libro == "ana_realtor"

    ya_tenia = Objetivo(email="a@x.com", nombre="A B", estado="TX",
                        handle_del_libro="el_bueno", nivel="MQL", tier="A")
    assert _con_handle(ya_tenia, {"handle_de_url": "otro", "puesto": 1}
                       ).handle_del_libro == "el_bueno"


def test_handle_de_url():
    from instagram.finder import _handle_de_url

    assert _handle_de_url("https://www.instagram.com/agent.ochoa/") == "agent.ochoa"
    assert _handle_de_url("instagram.com/Realtor_Javi") == "realtor_javi"
    assert _handle_de_url(None) is None
    assert _handle_de_url("no es una url") is None


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
