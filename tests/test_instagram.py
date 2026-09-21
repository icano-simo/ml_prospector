"""Pruebas del Bloque 1. Cada caso reproduce un fallo medido del sistema viejo.

    python tests/test_instagram.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "realtor_scraper"))

from instagram.comentarios import (  # noqa: E402
    Comentario,
    perfilar_audiencia,
    redactar,
    verificar_anonimato,
)
from instagram.estado import EstadoPerfil, diagnosticar  # noqa: E402
from instagram.idioma import (  # noqa: E402
    Idioma,
    clasificar_pieza,
    declara_acompanamiento,
    perfilar,
)
from instagram.posts import (  # noqa: E402
    Post,
    TipoDePost,
    calcular_cadencia,
    calcular_engagement,
    construir_red,
    geotags_agregados,
    programas_agregados,
)
from instagram.verificacion import (  # noqa: E402
    Confianza,
    comparar_nombre,
    detectar_senal_inmobiliaria,
    extraer_licencias_de_bio,
    verificar,
)


# ══ ESTADO DEL PERFIL ═════════════════════════════════════════════════════════

def test_privado_no_devuelve_false_en_las_senales():
    """El caso ig_is_private: 0 positivos en 5.620 filas era imposible."""
    d = diagnosticar(
        handle="sold_by_ana", codigo_http=200,
        titulo="Ana Tapia (@sold_by_ana) - Instagram",
        texto_body="This Account is Private\nAlready follow sold_by_ana?",
        hay_meta_description=True, n_articulos_con_posts=0,
    )
    assert d.estado is EstadoPerfil.PRIVADO
    assert d.estado.contenido_legible is False, (
        "en un perfil privado las señales de contenido quedan en null"
    )
    assert d.estado.perfil_existe is True
    assert "privada" in d.estado.motivo()


def test_bloqueado_se_distingue_de_privado():
    """Un muro de login dice 'log in to see' y NO significa cuenta privada."""
    d = diagnosticar(
        handle="x", codigo_http=200, titulo="Instagram",
        texto_body="Log in to see photos and videos from friends",
        hay_meta_description=False, n_articulos_con_posts=0,
    )
    assert d.estado is EstadoPerfil.BLOQUEADO
    assert d.estado.conviene_reintentar is True


def test_429_es_bloqueado_no_no_encontrado():
    d = diagnosticar(
        handle="x", codigo_http=429, titulo="", texto_body="",
        hay_meta_description=False, n_articulos_con_posts=0,
    )
    assert d.estado is EstadoPerfil.BLOQUEADO
    assert d.evidencia == "HTTP 429"


def test_no_encontrado():
    d = diagnosticar(
        handle="x", codigo_http=404, titulo="Page Not Found",
        texto_body="Sorry, this page isn't available.",
        hay_meta_description=False, n_articulos_con_posts=0,
    )
    assert d.estado is EstadoPerfil.NO_ENCONTRADO
    assert d.estado.conviene_reintentar is False


def test_pagina_vacia_no_se_lee_como_perfil_sin_senales():
    """La version vieja devolvia {} aca y eso terminaba en False en 14 columnas."""
    d = diagnosticar(
        handle="x", codigo_http=200, titulo="Instagram", texto_body="",
        hay_meta_description=False, n_articulos_con_posts=0,
    )
    assert d.estado is EstadoPerfil.BLOQUEADO
    assert "no se leyo nada" in d.evidencia


def test_publico_leido():
    d = diagnosticar(
        handle="x", codigo_http=200, titulo="Ana (@x) - Instagram",
        texto_body="336 followers", hay_meta_description=True,
        n_articulos_con_posts=30,
    )
    assert d.estado is EstadoPerfil.PUBLICO_LEIDO
    assert d.estado.contenido_legible is True


def test_sin_handle():
    d = diagnosticar(
        handle=None, codigo_http=None, titulo="", texto_body="",
        hay_meta_description=False, n_articulos_con_posts=0,
    )
    assert d.estado is EstadoPerfil.SIN_HANDLE


# ══ VERIFICACION DE HANDLE ════════════════════════════════════════════════════

def test_handle_correcto_verifica_alto():
    v = verificar(
        nombre_realtor="ANA TAPIA", handle="sold_by_ana",
        nombre_perfil="Ana Tapia | Oklahoma Realtor",
        bio="Oklahoma REALTOR at Casa Pro Realty. Hablo Espanol",
    )
    assert v.confianza is Confianza.ALTA
    assert v.senales_usables is True


def test_handle_de_otra_persona_no_verifica():
    """El bug: el primer instagram.com/... del HTML de DuckDuckGo."""
    v = verificar(
        nombre_realtor="ANA TAPIA", handle="cristiano",
        nombre_perfil="Cristiano Ronaldo", bio="Footballer",
    )
    assert v.confianza is Confianza.BAJA
    assert v.senales_usables is False
    assert "catorce señales sobre la persona equivocada" in v.razon


def test_nombre_de_pila_suelto_no_alcanza():
    """'Ana' coincidiendo con 'Ana Gomez' no prueba nada: hay muchas Anas."""
    v = verificar(
        nombre_realtor="ANA TAPIA", handle="ana_gomez_re",
        nombre_perfil="Ana Gomez", bio="Realtor in Texas",
    )
    assert v.confianza is Confianza.BAJA


def test_apellido_largo_solo_alcanza():
    v = verificar(
        nombre_realtor="MARIA VILLANUEVA", handle="villanueva_homes",
        nombre_perfil="Villanueva Homes", bio="Realty group, listings in Dallas",
    )
    assert v.confianza is Confianza.ALTA


def test_perfil_sin_senal_inmobiliaria_es_media():
    v = verificar(
        nombre_realtor="ANA TAPIA", handle="ana.tapia",
        nombre_perfil="Ana Tapia", bio="Mom of three. Coffee lover.",
    )
    assert v.confianza is Confianza.MEDIA
    assert v.senales_usables is True
    assert "cuenta personal" in v.razon


def test_licencia_en_bio_manda_sobre_el_nombre():
    v = verificar(
        nombre_realtor="ANA TAPIA", handle="thecasateam",
        nombre_perfil="The Casa Team", bio="TREC #654321",
        licencia_en_bio="654321",
    )
    assert v.confianza is Confianza.ALTA
    assert "licencia manda" in v.razon


def test_handle_camel_se_separa():
    c = comparar_nombre("Nancy Lopez", None, "NancyLopezRealtor")
    assert c.coincide is True
    assert "nancy" in c.comunes and "lopez" in c.comunes


def test_handle_pegado_se_resuelve_por_subcadena():
    c = comparar_nombre("Ana Tapia", None, "anatapia01")
    assert c.coincide is True


def test_ruido_de_oficio_no_cuenta_como_nombre():
    """'Realtor' coincidiendo no es identidad: casi todos lo ponen."""
    c = comparar_nombre("Ana Tapia", "Jose Realtor Homes Group", None)
    assert c.coincide is False


def test_estates_no_dispara_lujo_via_real_estate():
    """El patron que inflo el sub-nicho de lujo de ~126 a mas de 1.000 filas."""
    p = Post(caption="Your trusted real estate advisor in Austin")
    assert p.marcadores_anti_icp == []


def test_senal_inmobiliaria_en_captions_no_solo_en_bio():
    s = detectar_senal_inmobiliaria(
        bio="Mom of three",
        captions=["Just sold! Congrats to the Ramirez family on their new home"],
    )
    assert s.hay is True
    assert "captions" in s.donde


def test_extrae_licencia_de_bio():
    assert extraer_licencias_de_bio("Realtor | TREC #654321 | Austin TX") == ["654321"]
    assert extraer_licencias_de_bio("DRE# 01998877") == ["01998877"]
    assert extraer_licencias_de_bio("no hay nada aca") == []


# ══ IDIOMA ════════════════════════════════════════════════════════════════════

def test_caption_en_espanol():
    p = clasificar_pieza(
        "Felicidades a la familia Ramirez por su primera casa. "
        "Gracias por confiar en mi para este proceso tan importante."
    )
    assert p.idioma is Idioma.ESPANOL
    assert p.cuenta_para_evidencia is True


def test_caption_en_ingles():
    p = clasificar_pieza(
        "Congratulations to the Ramirez family on their first home! "
        "Thank you for trusting me with this important process."
    )
    assert p.idioma is Idioma.INGLES
    assert p.cuenta_para_evidencia is True


def test_caption_de_emoji_no_es_ingles():
    """82% de 'english' salio de tratar la ausencia de señal como ingles."""
    p = clasificar_pieza("🏡🔑✨ #realtor #austin")
    assert p.idioma is Idioma.INDETERMINADO
    assert p.cuenta_para_evidencia is False


def test_terminos_de_oficio_no_hacen_ingles_a_un_texto_espanol():
    p = clasificar_pieza(
        "Nuevo listing en Austin. Si quieres saber cuanto necesitas para el "
        "down payment, escribeme y lo vemos juntos."
    )
    assert p.idioma is Idioma.ESPANOL


def test_ratio_por_pieza_distingue_intensidad_1_de_2():
    """Lo que el alt-text nunca pudo: medir proporcion, no presencia."""
    ocasional = ["Congratulations to the Smith family on closing today, so happy for them",
                 "New listing in Round Rock, three bedrooms and a great yard, come see it",
                 "Open house this Saturday from noon to three, bring the whole family",
                 "Felicidades a los Ramirez por su nueva casa, que la disfruten mucho"]
    mayoria = ["Felicidades a la familia Ramirez por su nueva casa, que la disfruten",
               "Nueva propiedad en Round Rock, tres habitaciones y un patio muy lindo",
               "Casa abierta este sabado de doce a tres, los espero con mucho gusto",
               "Congratulations to the Smith family on closing today, so happy for them"]

    p1 = perfilar(ocasional)
    p2 = perfilar(mayoria)
    i1, _, t1 = p1.intensidad_pq14()
    i2, _, t2 = p2.intensidad_pq14()
    assert i1 == 1, t1
    assert i2 == 1, "con 4 piezas el techo es 1 aunque el ratio de 2"
    assert p1.ratio_espanol is not None and p2.ratio_espanol is not None
    assert p2.ratio_espanol > p1.ratio_espanol


def test_evidencia_por_debajo_del_estandar_recorta_y_lo_declara():
    """La matriz exige >=10 piezas. Con menos se activa pero se declara."""
    perfil = perfilar(["Felicidades a la familia por su nueva casa, muy contentos"] * 4)
    intensidad, grado, texto = perfil.intensidad_pq14()
    assert perfil.cumple_evidencia_matriz is False
    assert intensidad == 1
    assert "EVIDENCIA POR DEBAJO DEL ESTANDAR" in texto
    assert ">=10 piezas" in texto


def test_con_diez_piezas_se_cumple_el_estandar_y_llega_a_2():
    piezas = ["Felicidades a la familia Ramirez por su nueva casa, que la disfruten"] * 10
    perfil = perfilar(piezas)
    assert perfil.cumple_evidencia_matriz is True
    intensidad, grado, texto = perfil.intensidad_pq14()
    assert intensidad == 2
    assert grado == "E1"
    assert "mayoria del contenido en español" in texto


def test_sin_piezas_la_intensidad_es_none_no_cero():
    """0 significa 'operacion integramente en ingles', que es una afirmacion."""
    perfil = perfilar([])
    intensidad, _, texto = perfil.intensidad_pq14()
    assert intensidad is None
    assert "no se puede afirmar ni negar" in texto


def test_declaracion_explicita_es_intensidad_3():
    hay, fragmento = declara_acompanamiento("Oklahoma Realtor. Hablo Espanol")
    assert hay is True
    assert "Espanol" in fragmento
    perfil = perfilar([])
    intensidad, grado, _ = perfil.intensidad_pq14(declara_acompanamiento=True)
    assert (intensidad, grado) == (3, "E0")


def test_serie_de_ratio_permite_ver_evolucion():
    perfil = perfilar([
        "Congratulations to the Smith family on their closing today, so happy",
        "New listing in Austin, three bedrooms and a lovely backyard to enjoy",
        "Felicidades a la familia Ramirez por su nueva casa, que la disfruten",
        "Nueva propiedad en Round Rock, tres habitaciones y un patio muy lindo",
    ])
    assert len(perfil.serie_ratio) == 4
    assert perfil.serie_ratio[0] is not None
    assert perfil.serie_ratio[0] < perfil.serie_ratio[-1]


# ══ POSTS ═════════════════════════════════════════════════════════════════════

def test_menciones_salen_del_caption_no_del_alt():
    """ig_collaborates tenia 33 positivos en 5.620 porque las @ viven en el caption."""
    p = Post(caption="Gracias @maria.loanofficer por cerrar este caso tan rapido!")
    assert p.menciones == ["maria.loanofficer"]


def test_red_de_menciones_encuentra_candidatas_a_lender():
    posts = [
        Post(caption="Gracias @maria.loanofficer por el cierre"),
        Post(caption="Otra vez con @maria.loanofficer, equipo!"),
        Post(caption="Taller de compradores junto a @acme_mortgage este sabado"),
        Post(caption="Felicidades a los Ramirez"),
    ]
    red = construir_red(posts)
    assert red.conteo["maria.loanofficer"] == 2
    assert red.n_posts_con_menciones == 3
    assert "maria.loanofficer" in red.candidatas_a_lender
    assert "acme_mortgage" in red.candidatas_a_lender


def test_co_marketing_necesita_mencion_ademas_de_la_palabra():
    solo_palabra = Post(caption="Homebuyer workshop this Saturday, see you there")
    con_socio = Post(caption="Homebuyer workshop junto a @acme_mortgage este sabado")
    assert solo_palabra.es_co_marketing is False
    assert con_socio.es_co_marketing is True


def test_programas_declaran_su_qualifier():
    p = Post(caption="Si declaras con ITIN tambien puedes comprar. Pregunta por DPA.")
    assert p.programas["itin"] == "P-Q01"
    assert p.programas["dpa"] == "P-Q07"


def test_programas_agregados_guardan_el_fragmento_literal():
    posts = [
        Post(caption="Hablemos de FHA y del enganche", fecha=dt.date(2026, 3, 1)),
        Post(caption="Otro caso FHA cerrado hoy", fecha=dt.date(2026, 5, 1)),
    ]
    agg = programas_agregados(posts)
    assert agg["fha"]["n_posts"] == 2
    assert agg["fha"]["primer_post"] == dt.date(2026, 3, 1)
    assert agg["fha"]["ultimo_post"] == dt.date(2026, 5, 1)
    assert "FHA" in agg["fha"]["ejemplo"]


def test_anti_icp_con_dos_marcadores():
    p = Post(caption="Luxury waterfront penthouse, by appointment only")
    assert len(p.marcadores_anti_icp) >= 2


def test_cadencia_detecta_hueco_y_pico():
    """Un hueco de tres semanas seguido de un pico: 'lo produzco yo el domingo'."""
    fechas = [dt.date(2026, 1, 5), dt.date(2026, 1, 7), dt.date(2026, 1, 9),
              dt.date(2026, 3, 1), dt.date(2026, 3, 2), dt.date(2026, 3, 3),
              dt.date(2026, 3, 4)]
    cad = calcular_cadencia([Post(fecha=f) for f in fechas])
    assert cad.hueco_maximo_dias is not None and cad.hueco_maximo_dias > 21
    assert cad.n_huecos_mayores_a_21d == 1
    assert cad.pico_tras_hueco is True
    assert "produccion propia" in cad.nota


def test_cadencia_con_un_solo_post_no_inventa():
    cad = calcular_cadencia([Post(fecha=dt.date(2026, 1, 5))])
    assert cad.posts_por_semana is None
    assert "no se puede hablar de cadencia" in cad.nota


def test_engagement_real_no_es_seguidores():
    posts = [Post(likes=120, n_comentarios=14) for _ in range(6)]
    e = calcular_engagement(posts, seguidores=4000)
    assert e.suficiente is True
    assert e.tasa_media is not None
    assert abs(e.tasa_media - (134 / 4000)) < 1e-6


def test_engagement_sin_datos_no_devuelve_cero():
    e = calcular_engagement([Post(likes=None, n_comentarios=None)], seguidores=1000)
    assert e.tasa_media is None
    assert e.engagement_medio is None
    assert "ningun post trae likes" in e.nota


def test_engagement_sin_seguidores_da_absoluto_pero_no_tasa():
    e = calcular_engagement([Post(likes=10, n_comentarios=2)] * 6, seguidores=None)
    assert e.engagement_medio == 12.0
    assert e.tasa_media is None
    assert "no hay tasa" in e.nota or "no tasa" in e.nota


def test_geotags_dan_s7_subestatal():
    posts = [Post(geotag="Round Rock, Texas"), Post(geotag="Round Rock, Texas"),
             Post(geotag="Pflugerville, Texas"), Post(geotag=None)]
    g = geotags_agregados(posts)
    assert g["Round Rock, Texas"] == 2
    assert list(g)[0] == "Round Rock, Texas"


def test_reel_cuenta_como_produccion():
    assert Post(tipo=TipoDePost.REEL).senal_de_produccion is True
    assert Post(tipo=TipoDePost.IMAGEN, caption="Nueva casa").senal_de_produccion is False


# ══ COMENTARIOS ═══════════════════════════════════════════════════════════════

def test_el_handle_del_comentarista_no_se_guarda():
    c = Comentario.desde_crudo(
        texto="Cuanto necesito de enganche?",
        handle_autor="jose_perez_1988", handle_agente="sold_by_ana",
    )
    assert c.autor_es_el_agente is False
    assert "jose_perez_1988" not in repr(c)
    assert not hasattr(c, "handle_autor")
    assert not hasattr(c, "autor")


def test_se_distingue_el_comentario_del_agente():
    c = Comentario.desde_crudo(
        texto="Gracias!", handle_autor="@Sold_By_Ana", handle_agente="sold_by_ana",
    )
    assert c.autor_es_el_agente is True


def test_redacta_email_telefono_y_mencion():
    texto = "Escribeme a jose@gmail.com o al 512-555-0100, o a @otro_agente"
    redactado, que = redactar(texto)
    assert "jose@gmail.com" not in redactado
    assert "512-555-0100" not in redactado
    assert "@otro_agente" not in redactado
    assert set(que) >= {"email", "telefono", "mencion"}


def test_friccion_del_cliente_alimenta_qualifiers():
    crudos = [
        "Cuanto necesito de enganche para una casa asi?",
        "Se puede con ITIN? No tengo seguro social",
        "Mi credito esta malo, califico igual?",
        "Como empiezo el proceso?",
        "How much do I need down?",
    ]
    coms = [
        Comentario.desde_crudo(texto=t, handle_autor="x%d" % i,
                               handle_agente="sold_by_ana", post_url="p1")
        for i, t in enumerate(crudos)
    ]
    perfil = perfilar_audiencia(coms, n_posts_con_comentarios=1)
    assert perfil.n_de_terceros == 5
    assert perfil.fricciones["enganche"]["qualifier"] == "P-Q07"
    assert perfil.fricciones["itin_documentos"]["qualifier"] == "P-Q01"
    assert perfil.fricciones["credito"]["qualifier"] == "P-Q19"
    assert perfil.fricciones["precalificacion"]["qualifier"] == "P-Q12"
    assert perfil.fricciones["enganche"]["n"] == 2


def test_pocos_comentarios_no_activan_qualifiers():
    coms = [
        Comentario.desde_crudo(texto="Cuanto de enganche?", handle_autor="a",
                               handle_agente="b")
    ]
    perfil = perfilar_audiencia(coms)
    assert "NO activa qualifiers" in perfil.nota_de_evidencia
    assert "Tres comentarios no son un perfil de audiencia" in perfil.nota_de_evidencia


def test_idioma_de_terceros_es_la_senal_de_los_clientes():
    crudos_es = ["Cuanto necesito para el enganche de una casa como esta?"] * 10
    crudos_en = ["How much do I need for the down payment on a house like this?"] * 5
    coms = [
        Comentario.desde_crudo(texto=t, handle_autor="x%d" % i,
                               handle_agente="ana")
        for i, t in enumerate(crudos_es + crudos_en)
    ]
    perfil = perfilar_audiencia(coms)
    assert perfil.n_de_terceros == 15
    ratio = perfil.ratio_espanol_terceros
    assert ratio is not None and ratio > 0.5


def test_el_agregado_pasa_la_guarda_de_anonimato():
    coms = [
        Comentario.desde_crudo(
            texto="Cuanto de enganche? escribeme a jose@gmail.com o al 512-555-0100",
            handle_autor="jose", handle_agente="ana",
        )
    ]
    perfil = perfilar_audiencia(coms)
    verificar_anonimato(perfil)  # no debe levantar
    ejemplos = perfil.fricciones["enganche"]["ejemplos"]
    assert "jose@gmail.com" not in " ".join(ejemplos)


def test_la_guarda_de_anonimato_falla_si_se_cuela_algo():
    perfil = perfilar_audiencia([])
    perfil.fricciones["enganche"] = {
        "qualifier": "P-Q07", "descripcion": "x", "n": 1,
        "ejemplos": ["llamame al 512-555-0100"],
    }
    try:
        verificar_anonimato(perfil)
    except AssertionError as exc:
        assert "datos personales de terceros" in str(exc)
    else:
        raise AssertionError("la guarda de anonimato no fallo")


def test_friccion_dominante():
    coms = [
        Comentario.desde_crudo(texto="Cuanto de enganche necesito para esta casa?",
                              handle_autor="x%d" % i, handle_agente="ana")
        for i in range(4)
    ] + [
        Comentario.desde_crudo(texto="Se puede con ITIN sin seguro social?",
                              handle_autor="y", handle_agente="ana")
    ]
    perfil = perfilar_audiencia(coms)
    clave, datos = perfil.friccion_dominante()
    assert clave == "enganche"
    assert datos["n"] == 4


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
