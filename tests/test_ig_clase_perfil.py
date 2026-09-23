"""La compuerta de perfil de Instagram, sobre los casos golden anonimizados.

El caso que da origen a todo: `motor/desde_instagram.py` evaluaba Instagram sin
mirar de quién era la cuenta, y 36 de los 39 perfiles no utilizables tenían un
dolor primario vigente.

Los fixtures viven en `tests/fixtures/ig_casos_golden.json`, ya anonimizados:
sin handles de personas, sin emails, y el texto recortado a lo mínimo que
dispara la regla. La correspondencia con los perfiles reales NO va a git.
"""
from __future__ import annotations

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from ingest.instagram.clase_perfil import (  # noqa: E402
    CLASES,
    CLASES_UTILIZABLES,
    clasificar,
    es_post_de_real_estate,
    geotags_extranjeros,
    handles_repetidos_en,
)
from ingest.instagram.lexico import SEP_POST  # noqa: E402

GOLDEN = json.load(open(os.path.join(RAIZ, "tests", "fixtures",
                                     "ig_casos_golden.json"),
                        encoding="utf-8"))


def _fila(**kw):
    """Una fila con lo mínimo, para no repetir el andamiaje en cada caso."""
    captions = kw.pop("captions", None)
    base = {"estado_perfil": "publico_leido", "handle": "cuenta_x",
            "capturado_en": "2026-09-23", "estado": "Texas"}
    if captions is not None:
        base["captions_texto"] = SEP_POST.join(captions)
        base["captions_n"] = len(captions)
    base.update(kw)
    return base


# ══ LAS CUATRO PRUEBAS NUEVAS QUE PIDE EL CRITERIO DE ACEPTACION ═════════════

def test_panama_city_florida_es_EEUU():
    """Corrección A1. `panam[aá]` matchea «Panama City Beach, Florida».

    El geotag existe en el lote real. La regla que decide es el GAZETTEER de
    estados: si el geotag trae un estado de EE. UU., la lista de países ni se
    consulta.
    """
    posts = ["2026-09-01 | Just sold in Panama City Beach real estate"] * 3
    posts += ["2026-09-0%d | New listing 3 bedrooms open house" % i
              for i in range(1, 8)]
    f = _fila(estado="Florida",
              geotags_top="Panama City Beach, Florida (2), Destin, Florida (1)",
              captions=posts)
    c = clasificar(f)
    assert c.clase == "realtor_activo", c.a_dict()
    assert c.utilizable


def test_panama_de_verdad_sigue_siendo_extranjero():
    """El control: sin estado de EE. UU., «Panama City, Panama» SÍ es afuera.

    Sin esta prueba, A1 se podría «arreglar» desactivando la regla entera.
    """
    ext = geotags_extranjeros("Panama City, Panama (2)")
    assert ext == (2, 2)
    assert geotags_extranjeros("Panama City Beach, Florida (2)") == (0, 2)


def test_vacaciones_en_cancun_no_excluyen():
    """Corrección A2. 18 de 20 posts de real estate en TX y 2 geotags de Cancún.

    `re_fuera_eeuu` exige que los POSTS DE REAL ESTATE estén fuera. Un geotag de
    viaje solo dice dónde estuvo de vacaciones.
    """
    posts = ["2026-09-%02d | New listing in San Antonio, 3 bedrooms open house"
             % (i + 1) for i in range(18)]
    posts += ["2026-08-01 | Beach day", "2026-08-02 | Family time"]
    f = _fila(geotags_top="Cancún, Quintana Roo (2)", captions=posts)
    c = clasificar(f)
    assert c.clase == "realtor_activo", c.a_dict()
    assert c.detalle.get("opera_tambien_fuera") is not True


def test_loan_officer_con_nmls_propio():
    """Corrección A6. Sin detección automática, un scraping nuevo nunca lo ve."""
    f = _fila(bio="Loan Officer | NMLS 123456",
              captions=["2026-09-01 | Business owner? I have multiple loan "
                        "strategies for you",
                        "2026-09-02 | New listing 3 bedrooms open house",
                        "2026-09-03 | Just sold, real estate"])
    c = clasificar(f)
    assert c.clase == "otro_perfil", c.a_dict()
    assert c.detalle.get("es_originador") is True
    assert c.detalle.get("nmls") == "123456"
    assert c.revisar is True


def test_wholesaler():
    """Corrección A6. Compra para revender: no representa compradores."""
    f = _fila(captions=[
        "2026-09-01 | We purchased this property below market value from our "
        "direct-to-seller marketing",
        "2026-09-02 | Another wholesale deal closed",
        "2026-09-03 | New listing 3 bedrooms open house"])
    c = clasificar(f)
    assert c.clase == "otro_perfil", c.a_dict()
    assert c.revisar is True


#: Los falsos positivos MEDIDOS de `otro_perfil` sobre el lote real: 16 de 18.
#: `otro_perfil` no produce ningún qualifier transaccional, así que cada uno es
#: un realtor real que pierde su diagnóstico entero. Los patrones matcheaban
#: MENCIONAR a un loan officer, no SERLO.
FALSOS_OTRO_PERFIL = [
    ("speaker suelto", "I'm a true Austinite and fluent Spanish speaker"),
    ("Costco", "Coming Soon! Costco Wholesale, Walmart. Vail AZ is growing"),
    ("modismo", "one block, zero arguments over where to eat. That's a win "
                "in my book"),
    ("estante", "The Gold Butterfly is a bookend I store below to hold my "
                "books"),
    ("el LO del open house", "We will have our preferred loan officer ready "
                             "to pre-qualify you"),
    ("credito a otro", "shout out to one of the best loan officers in the "
                       "game, @jeen.yim, for helping make this happen"),
    ("descripción de listado", "remains is cosmetic, making this a great "
                               "opportunity for a fix and flip or buy and hold"),
    ("comprando a uno", "We negotiated it down from the wholesaler's asking "
                        "price, walked in knowing it was old"),
    ("elogio en un evento", "Amy was such an incredibly strong speaker on "
                            "social media and business growth"),
]


def test_los_dieciseis_falsos_positivos_de_otro_perfil():
    """Mencionar a un loan officer no es serlo. Regla 4, del lado correcto."""
    for etiqueta, cita in FALSOS_OTRO_PERFIL:
        posts = ["2026-09-01 | " + cita]
        posts += ["2026-09-%02d | New listing, open house, 3 bedrooms"
                  % (i + 2) for i in range(9)]
        c = clasificar(_fila(captions=posts))
        assert c.clase != "otro_perfil", (etiqueta, c.a_dict())


def test_los_verdaderos_otro_perfil_siguen_saliendo():
    """El control: si la guarda dijera que no a todo, no serviría de nada."""
    verdaderos = [
        "I have multiple loan strategies for business owners",
        "We purchased this property below market value from our "
        "direct-to-seller marketing",
    ]
    for cita in verdaderos:
        posts = ["2026-09-01 | " + cita]
        posts += ["2026-09-%02d | New listing, open house" % (i + 2)
                  for i in range(9)]
        assert clasificar(_fila(captions=posts)).clase == "otro_perfil", cita


def test_reproducible_contra_capturado_en():
    """Corrección A4. Con `hoy`, el mismo crudo da otra clase mañana."""
    posts = ["2026-05-01 | New listing 3 bedrooms open house"] * 2
    posts += ["2026-05-0%d | Just sold real estate" % i for i in range(2, 9)]
    f = _fila(capturado_en="2026-09-23", captions=posts)
    assert clasificar(f).clase != "inactivo"
    # La MISMA fila, capturada mucho después, sí está inactiva. Y la clase
    # depende solo de la fila: no de cuándo se corra esto.
    f2 = dict(f, capturado_en="2027-06-01")
    assert clasificar(f2).clase == "inactivo"


# ══ LOS CASOS GOLDEN ═════════════════════════════════════════════════════════

def test_gallos_en_panama_es_persona_equivocada():
    """perfil_A. «disponible» solo NO hace post de real estate."""
    f = _fila(geotags_top="Panama City, Panama (2)", captions=[
        "2023-05-27 | GALLO ESPAÑOL IMPORTADO DISPONIBLE PARA ENTREGA EN PANAMA",
        "2023-01-07 | DISPONIBLE LINEA GALLINO"])
    c = clasificar(f)
    assert c.clase == "persona_equivocada", c.a_dict()
    assert not c.utilizable


def test_portugues_es_persona_equivocada():
    """perfil_B."""
    f = _fila(estado="California", captions=[
        "2026-09-13 | Às vezes precisamos colocar toda energia pra fora",
        "2026-08-24 | Obrigada por tudo, você é meu amor, não esqueça"])
    c = clasificar(f)
    assert c.clase == "persona_equivocada"
    assert c.detalle.get("idioma") == "pt"


def test_hashtag_regional_fuera_de_su_estado():
    """perfil_C. #dmvrealestate en un lead de Texas."""
    f = _fila(captions=["2026-09-04 | He was soo proud #dmvrealestate"],
              geotags_top="Arlington, Virginia (1), Washington D. C. (1)")
    assert clasificar(f).clase == "persona_equivocada"


def test_handle_repetido_anula_los_dos_leads():
    """perfil_E. Se anula en TODOS hasta verificar, no en uno."""
    filas = [{"handle": "@mismo", "realtor_id": "lead_1"},
             {"handle": "@mismo", "realtor_id": "lead_2"}]
    reps = handles_repetidos_en(filas)
    assert "mismo" in reps
    for rid in ("lead_1", "lead_2"):
        c = clasificar(_fila(handle="@mismo", realtor_id=rid,
                             captions=["2026-09-01 | real estate listing"]),
                       handles_repetidos=reps)
        assert c.clase == "persona_equivocada", rid
        assert "más de un lead" in c.motivo


def test_new_mexico_es_EEUU():
    """perfil_F. «New Mexico» matchea `mexico` sin el lookbehind."""
    g = geotags_extranjeros(
        "El Paso County (2), Santa Teresa, New Mexico (1), "
        "Sunland Park, New Mexico (1)")
    assert g[0] == 0, g


def test_publico_leido_con_cero_captions_es_sin_datos():
    """perfil_G. `publico_leido` + 0 captions no es «se miró y no había nada»."""
    c = clasificar(_fila(estado_perfil="publico_leido", captions=[]))
    assert c.clase == "sin_datos"
    assert not c.utilizable


def test_personal_viejo_es_personal_sin_re_no_inactivo():
    """perfil_H. Corrección A5: el contenido manda sobre la inactividad.

    «Tiene otra cuenta de negocio: buscar handle» y «pedir la cuenta vigente»
    son dos acciones distintas para el BD, y solo una es la correcta.
    """
    posts = ["2022-10-%02d | Family dinner and a walk" % (i + 1)
             for i in range(19)]
    c = clasificar(_fila(capturado_en="2026-09-23", captions=posts))
    assert c.clase == "personal_sin_re", c.a_dict()


def test_terminos_debiles_sueltos_no_hacen_post_de_real_estate():
    """Corrección A3, y el caso `nuevo_personal_con_palabras_debiles`.

    Es el único de los 4 desacuerdos medidos que iba del lado peligroso: una
    cuenta personal salía `realtor_mixto` y filtraba al motor.
    """
    for post in ("Finally got the keys to our new boat!",
                 "Closing out summer with the family",
                 "Pending: my birthday party"):
        assert not es_post_de_real_estate(post), post
    # Dos débiles distintos en el mismo post sí cuentan.
    assert es_post_de_real_estate("Closing on the house this Friday")
    # Y un fuerte solo basta.
    assert es_post_de_real_estate("Just sold! #realestate")


# ══ LAS REGLAS DURAS ═════════════════════════════════════════════════════════

def test_ninguna_clase_cae_del_lado_utilizable_por_omision():
    """Toda clase que exista está declarada, y las utilizables son 4."""
    assert CLASES_UTILIZABLES <= CLASES
    assert CLASES_UTILIZABLES == {"realtor_activo", "realtor_mixto",
                                  "poca_evidencia", "otro_perfil"}
    assert len(CLASES) == 9


def test_toda_clase_trae_su_motivo_legible():
    """Un motivo vacío deja al BD sin saber qué hacer con el perfil."""
    casos = [
        _fila(captions=[]),
        _fila(captions=["2026-09-01 | Family dinner"] * 8),
        _fila(captions=["2026-09-01 | real estate listing open house"] * 8),
        _fila(captions=["2026-09-01 | GALLO gallina criadero"] * 4),
    ]
    for f in casos:
        c = clasificar(f)
        assert c.clase in CLASES, c.clase
        assert c.motivo and len(c.motivo) > 10, c.a_dict()


def test_el_golden_se_puede_leer_y_no_trae_PII():
    """El fixture es público: sin emails ni handles de personas."""
    import re
    crudo = json.dumps(GOLDEN, ensure_ascii=False)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}", crudo)
    assert GOLDEN["version_lexico"] == "ig-2026.09.23-v2"
    assert len(GOLDEN["clase_perfil"]) >= 13


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
