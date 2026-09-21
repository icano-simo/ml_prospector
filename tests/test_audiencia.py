"""Bloque 1-ter · perfil de audiencia derivado de los crudos.

Sin red, sin navegador, sin pandas. La prueba que mas importa de este archivo
es `test_todos_los_lexicos_son_bilingues`: un lexico que solo detecta en
español reproduce el sesgo que este bloque existe para corregir, y eso hay que
poder verificarlo mecanicamente, no prometerlo en un comentario.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "realtor_scraper"))

from instagram.audiencia import (  # noqa: E402
    BANDERAS_HISPANAS,
    COLUMNAS_AUDIENCIA,
    LARGO_CITA,
    LEX_AUDIENCIA,
    LEX_MARCADORES,
    LEX_PREGUNTAS,
    LEX_TEMAS,
    MAX_CITAS_CSV,
    TEMAS_ANUNCIA,
    TEMAS_EDUCA,
    ConteoDeIdioma,
    columnas_vacias,
    desajuste_idioma,
    etiquetar,
    lugares,
    perfilar_audiencia_1ter,
    precios,
    registro,
)
from instagram.finder import COLUMNAS_CSV, parsear_crudo  # noqa: E402

HOY = dt.date(2026, 8, 20)


def _post(caption, dias_atras=0, **extra):
    fecha = HOY - dt.timedelta(days=dias_atras)
    p = {
        "caption": caption,
        "fecha_iso": fecha.isoformat() + "T12:00:00.000Z",
        "likes": 40,
        "n_comentarios": 3,
        "typename": "GraphImage",
        "es_video": False,
        "shortcode": "SC%d" % dias_atras,
        "etiquetadas": [],
        "ubicacion": None,
    }
    p.update(extra)
    return p


def _crudo(posts=(), comentarios=None, bio=None, estado="publico_leido"):
    return {
        "handle_pedido": "anatapia_realtor",
        "estado_perfil": estado,
        "objetivo": {"email": "ana@x.com", "nombre": "ANA TAPIA", "estado": "TX"},
        "perfil": {
            "handle": "anatapia_realtor",
            "nombre_visible": "Ana Tapia",
            "bio": bio,
            "seguidores": 2000,
            "n_publicaciones": len(posts),
            "titulos_destacadas": [],
        },
        "posts": list(posts),
        "comentarios_por_post": comentarios or {},
        "posts_recuperados": len(posts),
        "posts_esperados": len(posts),
        "n_publicaciones_declaradas": len(posts),
        "fin_de_paginacion": True,
        "errores": [],
    }


# ══ LO QUE GOBIERNA TODO EL BLOQUE ════════════════════════════════════════════

def test_todos_los_lexicos_son_bilingues():
    """Cada entrada de cada lexico necesita patrones en los DOS idiomas.

    Es la regla del brief hecha prueba. Un lexico que solo detecta en español
    descarta al realtor que habla de credito y enganche en ingles, que es
    exactamente el prospecto que este bloque viene a recuperar.
    """
    faltantes = []
    for nombre_lex, lex in (("audiencia", LEX_AUDIENCIA), ("temas", LEX_TEMAS),
                            ("preguntas", LEX_PREGUNTAS),
                            ("marcadores", LEX_MARCADORES)):
        for etiqueta, (pat_es, pat_en) in lex.items():
            if not pat_es:
                faltantes.append("%s/%s sin patrones en español" % (nombre_lex, etiqueta))
            if not pat_en:
                faltantes.append("%s/%s sin patrones en ingles" % (nombre_lex, etiqueta))
    assert not faltantes, faltantes


def test_cada_etiqueta_llega_con_su_cita():
    """Conteo y cita, siempre juntos. Si dice credito:4, muestra las cuatro."""
    textos = [
        "Most people think their credit score isn't good enough to buy a home",
        "Mucha gente cree que su puntaje de credito no es suficiente",
        "Let's talk about your credit report and what it really means",
        "Reparar tu credito es mas rapido de lo que crees",
    ]
    et = etiquetar(textos, LEX_TEMAS)
    assert et.conteos["credito"] == 4
    assert len(et.citas["credito"]) == 4
    for cita in et.citas["credito"]:
        assert cita in textos
    assert et.denominador == 4


def test_no_hay_ninguna_etiqueta_sin_cita():
    """La invariante, sobre un texto cualquiera: toda clave contada tiene cita."""
    textos = [
        "Just listed! Open house this Saturday in Pilsen",
        "Felicidades a la familia Ramirez por su nueva casa",
        "Did you know FHA lets you buy with 3.5% down?",
        "Mi familia y yo de vacaciones, gracias a Dios",
    ]
    for lex in (LEX_AUDIENCIA, LEX_TEMAS, LEX_MARCADORES):
        et = etiquetar(textos, lex)
        assert set(et.conteos) == set(et.citas), lex
        for clave, n in et.conteos.items():
            assert len(et.citas[clave]) == n


def test_una_pieza_cuenta_una_vez_por_etiqueta():
    """Tres patrones de credito en un caption son UN caption, no tres."""
    et = etiquetar(
        ["Your credit score and credit history matter: bad credit is fixable"],
        LEX_TEMAS,
    )
    assert et.conteos["credito"] == 1


def test_una_pieza_puede_caer_en_varias_etiquetas():
    """Multi-etiqueta: un realtor puede tener dos o tres segmentos."""
    et = etiquetar(
        ["First-time home buyers: this investment property could be your start"],
        LEX_AUDIENCIA,
    )
    assert et.conteos["primera_compra"] == 1
    assert et.conteos["inversion"] == 1


def test_el_formato_de_multietiqueta_es_por_conteo_descendente():
    et = etiquetar(
        ["Did you know FHA allows 3.5% down?"] * 9
        + ["Your credit score is fixable"] * 4
        + ["Just listed in Logan Square"] * 5,
        LEX_TEMAS,
    )
    partes = et.formatear().split(" | ")
    conteos = [int(p.split(":")[1]) for p in partes]
    assert conteos == sorted(conteos, reverse=True), et.formatear()
    assert partes[0].startswith("educacion:9")


def test_no_hay_ningun_puntaje_compuesto():
    """Nada de «audiencia latina: 7,3». Ninguna columna mezcla señales."""
    prohibidas = ("score", "puntaje", "indice", "afinidad", "latinidad")
    for col in COLUMNAS_AUDIENCIA:
        assert not any(p in col for p in prohibidas), col


# ══ EL CASO QUE JUSTIFICA EL BLOQUE ══════════════════════════════════════════

def test_el_realtor_que_habla_de_credito_en_INGLES_no_se_pierde():
    """El prospecto que el sistema anterior descartaba.

    Ratio de español 0,0 y aun asi habla de credito, enganche y primera
    compra. Antes salia con un solo numero en cero y se iba a la basura.
    """
    posts = [
        _post("Most people think their credit score isn't good enough to buy "
              "a home. Here's what actually matters", dias_atras=2),
        _post("Did you know there are down payment assistance programs that "
              "cover up to $15,000?", dias_atras=9),
        _post("First-time home buyers: stop renting and let me show you the "
              "numbers", dias_atras=16),
        _post("Here's how the pre-approval process works, step by step",
              dias_atras=23),
    ]
    fila = parsear_crudo(_crudo(posts=posts))

    assert fila["captions_es_ratio"] == 0.0, "publica en ingles, medido"
    # Y sin embargo:
    assert "credito" in fila["temas"]
    assert "enganche" in fila["temas"]
    assert "primera_compra" in fila["audiencia_segmentos"]
    assert fila["tema_dominante"] is not None
    citas = json.loads(fila["citas_por_etiqueta"])
    assert any("credit score" in c for c in citas["tema:credito"])


def test_el_caption_real_del_piloto_cae_en_credito():
    """«Mucha gente cree que su puntaje de credito...» es P-Q19 casi literal."""
    real = ("Mucha gente cree que su puntaje de crédito no es lo "
            "suficientemente bueno para comprar una casa. Esto puede ser un "
            "mito que te está costando dinero.")
    et = etiquetar([real], LEX_TEMAS)
    assert et.conteos.get("credito") == 1
    assert et.conteos.get("educacion") == 1, "«mucha gente cree» es educar"


def test_el_mismo_caption_traducido_cae_igual():
    """La simetria que la prueba anterior no alcanza a demostrar sola."""
    es = "Mucha gente cree que su puntaje de credito no es suficiente"
    en = "Most people think their credit score isn't good enough"
    a = etiquetar([es], LEX_TEMAS)
    b = etiquetar([en], LEX_TEMAS)
    assert set(a.conteos) == set(b.conteos), (a.conteos, b.conteos)


# ══ EL CAMPO QUE MAS IMPORTA ══════════════════════════════════════════════════

def test_desajuste_positivo_es_audiencia_mas_latina_que_el_contenido():
    """Le escriben en español y el publica en ingles.

    Conversion que se esta dejando en la mesa, y una conversacion distinta a
    la de un agente que no atiende ese mercado.
    """
    publica = ConteoDeIdioma(es=1, en=9, total=10)
    comenta = ConteoDeIdioma(es=8, en=2, total=10)
    d = desajuste_idioma(comenta, publica)
    assert d is not None and d > 0.5, d


def test_desajuste_negativo_es_lo_contrario():
    publica = ConteoDeIdioma(es=9, en=1, total=10)
    comenta = ConteoDeIdioma(es=2, en=8, total=10)
    assert desajuste_idioma(comenta, publica) < 0


def test_el_desajuste_no_se_calcula_sin_base():
    """Sin piezas clasificables no hay resta, y un 0 seria una afirmacion."""
    assert desajuste_idioma(ConteoDeIdioma(total=12),
                            ConteoDeIdioma(es=5, en=5)) is None
    assert desajuste_idioma(ConteoDeIdioma(es=5, en=5),
                            ConteoDeIdioma(total=0)) is None


def test_un_solo_comentario_no_sostiene_un_desajuste():
    """El caso real: @miguelsanchezz7_ encabezaba el ranking con 0,9167.

    Salia de UN comentario en español y ninguno en ingles. Un 0,92 con n=1 es
    ruido presentado como señal, y manda a alguien a la conversacion
    equivocada con toda confianza.
    """
    from instagram.audiencia import MIN_BASE_DESAJUSTE

    uno = ConteoDeIdioma(es=1, en=0, total=1)
    publica = ConteoDeIdioma(es=1, en=11, total=12)
    assert desajuste_idioma(uno, publica) is None

    justo = ConteoDeIdioma(es=MIN_BASE_DESAJUSTE, en=0, total=MIN_BASE_DESAJUSTE)
    assert desajuste_idioma(justo, publica) is not None


def test_el_minimo_no_esconde_el_dato_solo_la_conclusion():
    """Los conteos van igual al CSV, asi que se puede mirar a mano."""
    aud = perfilar_audiencia_1ter(
        captions=["Just listed in Pilsen, come and see this one today"],
        comentarios_de_terceros=["Que bonita casa amiga, felicidades"],
        geotags=[],
    )
    cols = aud.a_columnas()
    assert cols["desajuste_idioma"] is None
    assert cols["idioma_comentarios_es"] == 1
    assert cols["idioma_publica_en"] == 1


def test_el_emoji_no_arrastra_el_desajuste():
    """Medido: el 26% de los comentarios del piloto son casi solo emoji.

    Con el total como denominador la resta saldria negativa por construccion, y
    el campo diria «su audiencia es menos latina» cuando lo que pasa es que su
    audiencia aplaude con emoji. De ahi la base de clasificables.
    """
    publica = ConteoDeIdioma(es=5, en=5, total=10)
    # Misma mezcla de idioma, pero 30 de 40 comentarios son emoji:
    comenta = ConteoDeIdioma(es=5, en=5, total=40)
    assert desajuste_idioma(comenta, publica) == 0.0, (
        "mitad y mitad en los dos lados es desajuste cero, con o sin emoji"
    )


def test_los_conteos_van_al_csv_para_poder_recalcularlo_a_mano():
    """La version con el total tambien tiene que ser computable."""
    for c in ("idioma_publica_es", "idioma_publica_en",
              "idioma_comentarios_es", "idioma_comentarios_en"):
        assert c in COLUMNAS_AUDIENCIA


# ══ REGLAS DE GUARDIA ════════════════════════════════════════════════════════

def test_un_privado_no_tiene_cero_temas_sino_ninguno():
    """Etiqueta ausente es null, nunca 0."""
    fila = parsear_crudo(_crudo(posts=[], estado="privado"))
    for col in COLUMNAS_AUDIENCIA:
        assert fila[col] is None, col


def test_bloqueado_y_no_encontrado_tampoco():
    for estado in ("bloqueado", "no_encontrado", "handle_dudoso"):
        fila = parsear_crudo(_crudo(posts=[], estado=estado))
        for col in COLUMNAS_AUDIENCIA:
            assert fila[col] is None, (estado, col)


def test_columnas_vacias_cubre_exactamente_el_contrato():
    assert sorted(columnas_vacias()) == sorted(COLUMNAS_AUDIENCIA)
    assert all(v is None for v in columnas_vacias().values())


def test_la_cita_de_un_comentario_va_sin_autor():
    """Los comentarios se agregan como perfil de audiencia. Nadie se perfila."""
    aud = perfilar_audiencia_1ter(
        captions=["Just listed in Pilsen, come see it"],
        comentarios_de_terceros=["How much down payment do I need?"],
        geotags=[],
    )
    assert aud.preguntas.conteos["calificacion"] == 1
    for citas in aud.preguntas.citas.values():
        for c in citas:
            assert "@" not in c, c


def test_el_handle_del_comentarista_no_puede_llegar_a_las_citas():
    """La funcion nunca recibe el autor, asi que no puede filtrarlo."""
    import inspect

    firma = inspect.signature(perfilar_audiencia_1ter)
    assert "comentarios_de_terceros" in firma.parameters
    assert not any("autor" in p or "handle" in p for p in firma.parameters), (
        list(firma.parameters)
    )


def test_el_nombre_del_agente_solo_sirve_para_EXCLUIR():
    """Se le resta, no se le suma.

    El nombre entra unicamente como veto de `barrios_mencionados`, porque «Ana
    Osorio» salia listada como un barrio de si misma. No alimenta ningun
    lexico y no produce ninguna etiqueta: no hay inferencia desde el nombre.
    """
    comun = dict(
        captions=["Nueva propiedad en el Pilsen neighborhood, ven a verla",
                  "Ana Osorio te ayuda. Ana Osorio tiene las llaves"],
        comentarios_de_terceros=[],
        geotags=[],
    )
    sin_veto = perfilar_audiencia_1ter(**comun)
    con_veto = perfilar_audiencia_1ter(**comun, nombres_a_vetar=("Ana Osorio",))

    # Lo unico que cambia es que el nombre deja de figurar como lugar.
    assert con_veto.audiencia.conteos == sin_veto.audiencia.conteos
    assert con_veto.temas.conteos == sin_veto.temas.conteos
    assert con_veto.marcadores.conteos == sin_veto.marcadores.conteos
    assert not any("Osorio" in k for k in con_veto.lugares.conteos), (
        con_veto.lugares.conteos
    )
    assert any("Pilsen" in k for k in con_veto.lugares.conteos)


def test_los_marcadores_describen_el_contenido_no_a_la_persona():
    """Una bandera cuenta porque se publico, no porque diga de donde es nadie."""
    aud = perfilar_audiencia_1ter(
        captions=["Feliz dia \U0001F1F8\U0001F1FB para toda mi gente"],
        comentarios_de_terceros=[],
        geotags=[],
    )
    assert "bandera_sv" in aud.marcadores.conteos
    # La cita muestra el contenido, que es lo unico que se afirma.
    assert aud.marcadores.citas["bandera_sv"]


def test_ninguna_columna_afirma_un_origen():
    """Las etiquetas describen contenido publicado. Ninguna nombra un origen
    de la persona."""
    from instagram.audiencia import BANDERAS_HISPANAS

    for codigo in BANDERAS_HISPANAS.values():
        clave = "bandera_%s" % codigo.lower()
        assert clave.startswith("bandera_"), clave
    # Y el vocabulario regional se llama `vocabulario_`, no `origen_`.
    et = registro(["La recamara tiene alberca", "Vamos a platicar de tu casa"])
    for k in et.conteos:
        assert not k.startswith("origen"), k


def test_todo_lleva_su_denominador():
    aud = perfilar_audiencia_1ter(
        captions=["Did you know FHA allows 3.5% down?"] * 12,
        comentarios_de_terceros=["Congrats!"] * 5,
        geotags=[],
    )
    assert aud.temas.denominador == 12
    assert aud.n_captions == 12
    assert aud.n_comentarios == 5
    assert aud.idioma_publica.total == 12


def test_el_ratio_educa_vs_anuncia_lleva_sus_dos_conteos():
    """9 de 10 y 90 de 100 son el mismo 0,9 y no son la misma evidencia."""
    posts = (
        [_post("Did you know FHA allows 3.5%% down? Here's how it works %d" % i,
               dias_atras=i) for i in range(9)]
        + [_post("Just listed! Open house Saturday number %d" % i,
                 dias_atras=20 + i) for i in range(3)]
    )
    fila = parsear_crudo(_crudo(posts=posts))
    texto = fila["ratio_educa_vs_anuncia"]
    assert "educa" in texto and "anuncia" in texto, texto
    assert texto.startswith("0.")


def test_sin_temas_de_ninguno_de_los_dos_lados_el_ratio_es_null():
    posts = [_post("Mi familia y yo de vacaciones en la playa", dias_atras=i)
             for i in range(4)]
    fila = parsear_crudo(_crudo(posts=posts))
    assert fila["ratio_educa_vs_anuncia"] is None
    assert "vida_personal" in fila["temas"]


def test_los_dos_conjuntos_de_temas_no_se_solapan():
    assert not (set(TEMAS_EDUCA) & set(TEMAS_ANUNCIA))
    for t in TEMAS_EDUCA + TEMAS_ANUNCIA:
        assert t in LEX_TEMAS, t


# ══ CITAS EN EL CSV ═══════════════════════════════════════════════════════════

def test_maximo_tres_citas_por_etiqueta_y_recortadas_a_200():
    largo = "Your credit score is what most people get wrong about buying. " * 10
    posts = [_post(largo + " numero %d" % i, dias_atras=i) for i in range(6)]
    fila = parsear_crudo(_crudo(posts=posts))
    citas = json.loads(fila["citas_por_etiqueta"])
    assert citas, "tiene que haber citas"
    for clave, lista in citas.items():
        assert len(lista) <= MAX_CITAS_CSV, (clave, len(lista))
        for c in lista:
            assert len(c) <= LARGO_CITA, (clave, len(c))


def test_la_cita_contiene_la_frase_que_disparo_la_etiqueta():
    """El bug que casi me hace perseguir un falso positivo inexistente.

    La cita era el caption entero recortado a 200 caracteres DESDE EL
    PRINCIPIO. En un caption de 1.200 caracteres cuya coincidencia esta en el
    800, la cita no contenia la frase -- o sea que se rompia la regla que
    gobierna el bloque, y justo en los captions largos, que son los educativos.

    El caso es real: `@anakaren_properties` mostraba «How I meet my clients??
    My marketing strategies vary...» para la etiqueta `credito`, y la frase
    estaba 800 caracteres mas adelante.
    """
    relleno = "How I meet my clients? My marketing strategies vary a lot. " * 14
    caption = relleno + " He worked on his credit and then he called me back."
    assert len(caption) > 800

    et = etiquetar([caption], LEX_TEMAS)
    assert et.conteos["credito"] == 1
    cita = et.citas_para_csv()["credito"][0]
    assert "credit" in cita, cita
    assert len(cita) <= LARGO_CITA + 6, len(cita)  # + los puntos suspensivos


def test_la_cita_corta_no_se_toca():
    et = etiquetar(["Your credit score is fixable"], LEX_TEMAS)
    assert et.citas_para_csv()["credito"][0] == "Your credit score is fixable"


def test_el_texto_completo_sobrevive_en_el_derivado():
    """La ventana es para el CSV; el derivado guarda todo."""
    largo = "palabra " * 200 + "your credit score"
    et = etiquetar([largo], LEX_TEMAS)
    assert len(et.citas["credito"][0]) > LARGO_CITA
    assert len(et.citas_para_csv()["credito"][0]) <= LARGO_CITA + 6


def test_no_hay_conteo_sin_cita_en_ninguna_familia():
    """`anotar` es la unica via de conteo, asi que la invariante es estructural."""
    aud = perfilar_audiencia_1ter(
        captions=["Just listed at $625,000 in the Pilsen neighborhood \U0001F1F2\U0001F1FD",
                  "Just listed at $625,000 in the Pilsen neighborhood again",
                  "Tu credito puede mejorar, escribeme y te explico como"],
        comentarios_de_terceros=["How much down payment do I need?"],
        geotags=["Little Village, Chicago"],
        bio="Bilingual REALTOR | FHA specialist",
    )
    for nombre, et in (("audiencia", aud.audiencia), ("temas", aud.temas),
                       ("registro", aud.registro_), ("marcadores", aud.marcadores),
                       ("precios", aud.precios), ("barrios", aud.lugares),
                       ("programas", aud.programas), ("preguntas", aud.preguntas)):
        assert set(et.conteos) == set(et.citas), nombre
        assert set(et.conteos) == set(et.ventanas), nombre
        for clave, n in et.conteos.items():
            assert len(et.citas[clave]) == n, (nombre, clave)
            assert len(et.ventanas[clave]) == n, (nombre, clave)


def test_las_citas_del_csv_son_json_valido_en_una_celda():
    posts = [_post("Did you know FHA allows 3.5% down?", dias_atras=0)]
    fila = parsear_crudo(_crudo(posts=posts))
    texto = fila["citas_por_etiqueta"]
    assert "\n" not in texto, "una celda, una linea"
    cargado = json.loads(texto)
    assert isinstance(cargado, dict)
    assert all(isinstance(v, list) for v in cargado.values())


def test_el_derivado_conserva_todas_las_citas():
    """El CSV recorta; el derivado no. Por eso existen los dos."""
    posts = [_post("Your credit score matters more than you think, post %d" % i,
                   dias_atras=i) for i in range(7)]
    aud = perfilar_audiencia_1ter(
        captions=[p["caption"] for p in posts],
        comentarios_de_terceros=[],
        geotags=[],
    )
    assert len(aud.temas.citas["credito"]) == 7
    assert len(aud.temas.citas_para_csv()["credito"]) == MAX_CITAS_CSV
    assert len(aud.citas_completas()["temas"]["credito"]) == 7


# ══ LO QUE NO SALE DE UN LEXICO ══════════════════════════════════════════════

def test_los_precios_se_normalizan_a_la_misma_etiqueta():
    et = precios(["What does $625,000 get you in Logan Square?",
                  "Listed at $625K and already under contract"])
    assert et.conteos.get("625k") == 2, et.conteos


def test_un_millon_se_lee_como_millon():
    et = precios(["Just closed at $1.2M", "Nueva propiedad de $1,200,000"])
    assert et.conteos.get("1.2m") == 2, et.conteos


def test_un_precio_de_cafe_no_es_un_precio_de_casa():
    """Sin separador ni sufijo no entra: `$5` no es el rango de nadie."""
    et = precios(["Coffee was $5 and worth it", "Entrada de $20 al evento"])
    assert et.conteos == {}, et.conteos


def test_el_geotag_cuenta_solo_y_el_titlecase_necesita_apoyo():
    et = lugares(
        textos=["Happy New Year everyone", "Happy New Year to all of you"],
        geotags=["Pilsen, Chicago"],
    )
    assert "Pilsen, Chicago" in et.conteos
    assert not any("Happy New Year" in k for k in et.conteos), et.conteos


def test_un_barrio_pegado_a_la_palabra_barrio_si_entra():
    et = lugares(
        textos=["New listing in the Little Village neighborhood, come see it"],
        geotags=[],
    )
    assert any("Little Village" in k for k in et.conteos), et.conteos


def test_el_pin_avala_un_lugar():
    """En esta data el pin es la marca de lugar mas fiable."""
    et = lugares(textos=["ALERT 2-Story Townhouse \U0001F4CDDoral, Florida"],
                 geotags=[])
    assert any("Doral" in k for k in et.conteos), et.conteos


def test_cerca_de_un_pin_no_es_ser_un_lugar():
    """`Download:8` entraba porque el pin estaba en la misma linea del CTA.

    La ventana era de 30 caracteres. Ahora el aval tiene que estar pegado.
    """
    et = lugares(
        textos=["Download my free guide \U0001F4CD link in bio"] * 8,
        geotags=[],
    )
    assert "Download" not in et.conteos, et.conteos


def test_el_pin_pegado_si_avala():
    et = lugares(textos=["Ubicacion \U0001F4CDDoral, Florida"], geotags=[])
    assert any("Doral" in k for k in et.conteos), et.conteos


def test_los_hashtags_no_son_fuente_de_lugares():
    """Parecian buena fuente y la revision a mano lo desmintio.

    En inmobiliaria los hashtags son abrumadoramente tematicos: salieron
    «Dream Home», «Homes For Sale», «Real Estate Life» e «Investment Property»
    presentados como barrios. No hay forma lexica de separar #LoganSquare de
    #DreamHome, asi que la fuente se descarta entera -- perdiendo los buenos.
    """
    et = lugares(
        textos=["Beautiful place #DreamHome #HomesForSale #RealEstateLife"],
        geotags=[],
    )
    assert et.conteos == {}, et.conteos


def test_locations_del_pie_de_pagina_no_es_un_barrio():
    """106 veces de unos 180 geotags en el piloto. Es el enlace del pie."""
    from instagram.finder import _GEOTAGS_QUE_NO_SON_LUGARES

    assert "locations" in _GEOTAGS_QUE_NO_SON_LUGARES


def test_la_basura_que_la_revision_a_mano_encontro_ya_no_entra():
    """Los candidatos reales que salieron listados como barrios.

    La regla vieja era «entra si aparece dos veces», y repetirse dos veces no
    le cuesta nada a la primera palabra de una frase. Una columna con
    `Would:1` y `Congratulations:1` presentados como barrios no se puede leer,
    y una columna que no se puede leer es peor que no tenerla: invita a
    creerle.
    """
    textos = [
        "Would you pay $1.3M for a condo? Before you answer take a look",
        "Would you believe this one? Send me a message today",
        "Send me a DM. Looking for the perfect location to grow",
        "Looking for your first home? This could be it",
        "Congratulations to this cutie pie. Friends, family and more",
        "Congratulations on the closing! This was a long road",
        "Download my free guide. Download it now",
        "This is not your ordinary rental. This one is different",
    ]
    et = lugares(textos, geotags=[])
    for basura in ("Would", "Send", "Looking", "Congratulations",
                   "Download", "This", "Before"):
        assert basura not in et.conteos, (basura, et.conteos)


def test_el_recorte_de_la_celda_se_declara():
    """Si se recorto, que se vea. Un recorte silencioso miente por omision."""
    et = lugares(
        textos=["Casa en el barrio %s Park, ven a verla" % chr(65 + i)
                for i in range(12)],
        geotags=["Lugar %d, Chicago" % i for i in range(12)],
    )
    texto = et.formatear(tope=8)
    assert "(+" in texto and "mas)" in texto, texto
    assert len(texto.split(" | ")) == 9  # 8 + el aviso


def test_el_registro_distingue_tuteo_de_usted():
    tu = registro(["Tu casa puede valer mas de lo que crees, escribeme"])
    assert tu.conteos.get("tuteo") == 1
    assert "usted" not in tu.conteos

    usted = registro(["Su casa puede valer mas de lo que cree, escribame"])
    assert usted.conteos.get("usted") == 1
    assert "tuteo" not in usted.conteos


def test_la_jerga_tecnica_se_cuenta_aparte():
    et = registro(["Your DTI and LTV decide the escrow structure here"])
    assert et.conteos.get("jerga_tecnica") == 1


def test_una_palabra_regional_suelta_no_declara_una_variedad():
    """Hace falta variedad de vocabulario, no una palabra.

    Y la etiqueta dice `vocabulario:` a proposito: es una observacion sobre
    palabras, no una afirmacion sobre de donde es nadie.
    """
    una = registro(["La recamara principal es amplia"])
    assert not any(k.startswith("vocabulario_") for k in una.conteos), una.conteos

    dos = registro(["La recamara principal es amplia y tiene alberca",
                    "Vamos a platicar de tu casa"])
    assert "vocabulario_mx" in dos.conteos, dos.conteos


def test_las_banderas_hispanas_son_marcadores_de_contenido():
    aud = perfilar_audiencia_1ter(
        captions=["Bilingual REALTOR \U0001F1EC\U0001F1F9 serving Chicago"],
        comentarios_de_terceros=[],
        geotags=[],
    )
    assert "bandera_gt" in aud.marcadores.conteos
    assert aud.marcadores.citas["bandera_gt"]


def test_hay_banderas_de_mas_de_un_pais():
    assert len(set(BANDERAS_HISPANAS.values())) >= 15


# ══ PREGUNTAS RECIBIDAS ══════════════════════════════════════════════════════

def test_las_preguntas_se_clasifican_por_tipo():
    coms = [
        "How much down payment do I need for this one?",
        "Se puede con ITIN sin seguro social?",
        "Precio?",
        "What area is that in?",
        "Is this still available?",
        "Como empiezo el proceso?",
    ]
    et = etiquetar(coms, LEX_PREGUNTAS)
    assert et.conteos.get("calificacion") == 2
    assert et.conteos.get("precio") == 1
    assert et.conteos.get("zona") == 1
    assert et.conteos.get("disponibilidad") == 1
    assert et.conteos.get("proceso") == 1


def test_una_felicitacion_no_es_una_pregunta():
    """Medido: el 26% de los comentarios del piloto son casi solo emoji."""
    et = etiquetar(["Congrats! \U0001F525\U0001F525\U0001F525",
                    "Felicidades!!", "\U0001F44F\U0001F44F"], LEX_PREGUNTAS)
    assert et.conteos == {}, et.conteos


def test_el_idioma_de_los_comentarios_va_aparte_del_de_las_publicaciones():
    aud = perfilar_audiencia_1ter(
        captions=["Just listed in Pilsen, three bedrooms and a big yard"],
        comentarios_de_terceros=[
            "Que bonita casa, felicidades por el logro amiga",
            "Me encanta esa cocina, cuanto piden por ella",
        ],
        geotags=[],
    )
    assert aud.idioma_publica.en == 1
    assert aud.idioma_publica.es == 0
    assert aud.idioma_comentarios.es == 2


# ══ INTEGRACION CON EL CSV ═══════════════════════════════════════════════════

def test_las_17_columnas_estan_en_el_contrato_y_al_final():
    assert COLUMNAS_CSV[-len(COLUMNAS_AUDIENCIA):] == COLUMNAS_AUDIENCIA
    assert len(COLUMNAS_AUDIENCIA) == 17, len(COLUMNAS_AUDIENCIA)


def test_la_bio_alimenta_marcadores_pero_no_temas():
    """Lo que la bio dice es permanente; un tema es algo con fecha."""
    aud = perfilar_audiencia_1ter(
        captions=["Beautiful sunset over the lake today"],
        comentarios_de_terceros=[],
        geotags=[],
        bio="Bilingual REALTOR | Se Habla Espanol | FHA and VA specialist",
    )
    assert "idioma_declarado" in aud.marcadores.conteos
    assert "fha" in aud.programas.conteos
    assert "programas_gobierno" not in aud.temas.conteos, (
        "la bio no cuenta como una publicacion sobre el tema"
    )


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
