"""Las señales de Instagram: qualifiers con ancla, idioma, S6 y la compuerta.

Cada caso `sen_*` del golden es una cita real anonimizada, y cada negativo salió
de un falso positivo medido sobre el lote.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from ingest.instagram.lexico import LEX, NO_USAR, SEP_POST, VERSION_LEXICO  # noqa
from ingest.instagram.parseo import (  # noqa: E402
    engagement_utilizable,
    hits_distintos,
    parsear_conteo,
)
from ingest.instagram.senales import (  # noqa: E402
    clasificar_cuenta,
    idioma_de,
    senales_de_posts,
)
from motor.desde_instagram import (  # noqa: E402
    CAMPOS_PERMITIDOS,
    PROHIBIDOS_POR_ECOA,
    bio_legible,
    categorias_acreditadas,
    senales_de,
)


def _fila(captions, **kw):
    base = {"estado_perfil": "publico_leido", "handle": "x", "estado": "Texas",
            "capturado_en": "2026-09-23",
            "captions_texto": SEP_POST.join(captions),
            "captions_n": len(captions)}
    base.update(kw)
    return base


def _q(captions, qualifier, clase="realtor_activo"):
    s = [x for x in senales_de_posts(_fila(captions), clase)
         if x.qualifier == qualifier]
    return (s[0].intensidad, s[0].grado) if s else None


# ══ P-Q01 · MENCION NO ES VERBALIZACION ══════════════════════════════════════

def test_itin_en_su_propio_texto_es_3_E0():
    """sen_01."""
    assert _q(["2026-09-01 | Aceptamos ITIN (Personas con ITIN califican)"],
              "P-Q01") == (3, "E0")


def test_una_firma_repetida_12_veces_cuenta_1():
    """sen_02. Contarla 12 veces convertía una firma en una especialización."""
    posts = ["2026-09-%02d | PRESTAMOS CON TAX ID ✔️ PRESTAMO SIN CRÉDITO"
             % (i + 1) for i in range(12)]
    n_hits, n_distintos, _ancla = hits_distintos(posts, LEX["itin"])
    assert n_hits == 12
    assert n_distintos == 1
    s = [x for x in senales_de_posts(_fila(posts), "realtor_activo")
         if x.qualifier == "P-Q01"][0]
    assert s.posts_distintos == 1
    assert (s.intensidad, s.grado) == (3, "E0")


def test_cuenta_propia_en_contexto_de_financiamiento_es_3_E0():
    """sen_03."""
    assert _q(["2026-09-01 | Trabajas por tu cuenta y pensabas que necesitabas "
               "tus taxes para comprar casa?"], "P-Q01") == (3, "E0")


def test_owner_financing_es_2_E1():
    """sen_04. Es un atributo de la operación, no su especialización."""
    assert _q(["2026-09-01 | Got denied by the bank? This home doesn't require "
               "bank approval. Owner financing available"],
              "P-Q01") == (2, "E1")


def test_business_owners_solo_no_activa():
    """sen_05. Aparece en comercial, golf y seguros: 3 perfiles."""
    assert _q(["2026-09-01 | help business owners, investors, and property "
               "owners make confident moves #CommercialRealEstate"],
              "P-Q01") is None


def test_trabajadores_independientes_sin_financiamiento_no_activa():
    """sen_06. «ideal para contratistas... trabajadores independientes»."""
    assert _q(["2026-09-01 | ideal para contratistas, carpinteros, "
               "constructores o trabajadores independientes que buscan mayor "
               "capacidad"], "P-Q01") is None


def test_estudio_independiente_no_activa():
    """sen_07. «independiente» es un edificio separado: 8 perfiles."""
    assert _q(["2026-09-01 | potencial estudio independiente ¡Uno de ellos "
               "tiene su propia entrada!"], "P-Q01") is None


def test_bank_statements_como_lista_de_documentos_no_activa():
    """sen_08."""
    assert _q(["2026-09-01 | 2 months of recent Paystubs • 2 most recent bank "
               "statements"], "P-Q01") is None


# ══ P-Q07, P-Q17, P-Q19 ══════════════════════════════════════════════════════

def test_cero_down_como_atributo_de_listado_es_2_E1():
    """sen_09. Es un atributo del listado, no su especialización."""
    assert _q(["2026-09-01 | Qualifies for 0% down financing 3 beds, 2 baths"],
              "P-Q07") == (2, "E1")


def test_un_solo_post_de_dpa_es_2_E1_y_dos_son_3_E0():
    """sen_10. 3/E0 solo con >=2 posts DISTINTOS."""
    uno = ["2026-09-01 | helped MANY families become homeowners with zero "
           "money down using grants, down payment assistance programs"]
    assert _q(uno, "P-Q07") == (2, "E1")
    dos = uno + ["2026-08-15 | Nuevo programa de asistencia para el down "
                 "payment en el condado"]
    assert _q(dos, "P-Q07") == (3, "E0")


def test_va_buyer_es_historia_de_cierre_no_especializacion():
    """sen_11. Un solo post de `va_aud` es una anécdota: no activa."""
    assert _q(["2026-09-01 | Congratulations to my amazing VA buyer"],
              "P-Q17") is None
    dos = ["2026-09-01 | Congratulations to my amazing VA buyer",
           "2026-08-01 | Working with a veteran family on their VA loan"]
    assert _q(dos, "P-Q17") == (2, "E1")


def test_MRP_es_especializacion_3_E0():
    """sen_12. Military Relocation Professional es una designación."""
    assert _q(["2026-09-01 | #MilitaryFamilies ... MRP MilitaryCityUSA"],
              "P-Q17") == (3, "E0")


def test_foreclosure_como_comentario_de_mercado_no_da_3():
    """sen_13."""
    r = _q(["2026-09-01 | Foreclosure activity is rising, and Texas continues "
            "to see significant foreclosure activity"], "P-Q19")
    assert r is None or r[0] < 3


def test_credit_restoration_es_3_E0():
    """sen_14."""
    assert _q(["2026-09-01 | Credit repair companies. ... 30 DAYS LATER: "
               "credit restoration GRADUATE ➡️ HOMEOWNER"],
              "P-Q19") == (3, "E0")


# ══ IDIOMA ═══════════════════════════════════════════════════════════════════

def test_comunidad_bilingue_no_es_declaracion():
    """sen_15. Describe un barrio, no un servicio."""
    posts = ["2026-09-01 | Una comunidad bilingüe que sigue creciendo en el "
             "suroeste de Florida"]
    assert hits_distintos(posts, LEX["es_decl"])[1] == 0


def test_te_conecto_con_un_lender_que_habla_espanol_si_declara():
    """sen_16."""
    posts = ["2026-09-01 | Te conecto con un lender de confianza que habla "
             "español"]
    assert hits_distintos(posts, LEX["es_decl"])[1] == 1


def test_la_bio_bilingue_con_20_posts_en_ingles_no_llega_a_3():
    """sen_17. En 47 de los 300 perfiles v3 daba 3/E0 por la bio."""
    posts = ["2026-09-%02d | New listing open house" % (i + 1)
             for i in range(20)]
    f = _fila(posts, bio="Bilingual | English & Español",
              senales={"idioma_publica_es": 0, "idioma_publica_en": 20})
    r = idioma_de(f, "realtor_activo")
    assert r["intensidad"] <= 1, r
    assert r["pub_es_mayoria"] is False


def test_publica_en_espanol_y_lo_declara_es_3_E0():
    posts = ["2026-09-%02d | Se habla español, nueva casa en venta"
             % (i + 1) for i in range(12)]
    f = _fila(posts, senales={"idioma_publica_es": 12, "idioma_publica_en": 0})
    r = idioma_de(f, "realtor_activo")
    assert (r["intensidad"], r["grado"]) == (3, "E0"), r


def test_publica_en_espanol_sin_declararlo_es_2_E1():
    posts = ["2026-09-%02d | Nueva casa en venta, tres recámaras"
             % (i + 1) for i in range(12)]
    f = _fila(posts, senales={"idioma_publica_es": 12, "idioma_publica_en": 0})
    r = idioma_de(f, "realtor_activo")
    assert (r["intensidad"], r["grado"]) == (2, "E1"), r


# ══ LA COMPUERTA ═════════════════════════════════════════════════════════════

def test_un_perfil_no_utilizable_no_produce_NI_UN_qualifier():
    """La regla dura 1. Es el caso de los 36 de 39."""
    posts = ["2026-09-01 | Aceptamos ITIN, personas con ITIN califican"] * 3
    for clase in ("sin_datos", "persona_equivocada", "re_fuera_eeuu",
                  "inactivo", "personal_sin_re"):
        assert senales_de_posts(_fila(posts), clase) == [], clase


def test_otro_perfil_no_se_evalua_como_realtor_transaccional():
    """Corrección B10: entra solo como fuente de referidos."""
    posts = ["2026-09-01 | Aceptamos ITIN, personas con ITIN califican"] * 3
    assert senales_de_posts(_fila(posts), "otro_perfil") == []


def test_senales_de_devuelve_vacio_si_la_clase_no_es_utilizable():
    """Y por la vía que usa el motor, no solo por la interna."""
    f = _fila(["2026-09-01 | Family dinner"] * 8,
              senales={"menciona_itin": 1, "captions_texto": SEP_POST.join(
                  ["2026-09-01 | Family dinner"] * 8)})
    assert senales_de(f) == {}
    assert categorias_acreditadas(f) == set()
    assert bio_legible(f) is None


def test_poca_evidencia_tiene_techo_2_E1():
    posts = ["2026-09-01 | Aceptamos ITIN, personas con ITIN califican"]
    r = _q(posts, "P-Q01", clase="poca_evidencia")
    assert r == (2, "E1"), r


# ══ EVIDENCIA OBLIGATORIA ════════════════════════════════════════════════════

def test_toda_senal_trae_ancla_regla_fuente_y_version():
    posts = ["2026-09-01 | Aceptamos ITIN, personas con ITIN califican",
             "2026-09-02 | Credit repair y credit restoration"]
    for s in senales_de_posts(_fila(posts), "realtor_activo"):
        assert s.evidencia_ancla and "«" in s.evidencia_ancla, s
        assert s.evidencia_regla and "posts distintos" in s.evidencia_regla
        assert s.fuente == "instagram"
        assert s.version_lexico == VERSION_LEXICO
        assert len(s.huella_lexico) == 16


# ══ ECOA · marcadores_culturales FUERA ═══════════════════════════════════════

def test_marcadores_culturales_no_esta_en_la_lista_blanca():
    assert "marcadores_culturales" not in CAMPOS_PERMITIDOS
    assert "marcadores_culturales" in PROHIBIDOS_POR_ECOA


def test_ningun_prohibido_se_colo_en_la_lista_blanca():
    assert not (set(PROHIBIDOS_POR_ECOA) & CAMPOS_PERMITIDOS)


def test_el_resultado_es_IDENTICO_con_y_sin_marcadores_culturales():
    """La regla dura 2, probada como pide la spec."""
    posts = ["2026-09-%02d | New listing open house" % (i + 1)
             for i in range(12)]
    base = {"captions_texto": SEP_POST.join(posts),
            "idioma_publica_es": 12, "idioma_publica_en": 0,
            "menciona_itin": 1}
    sin = _fila(posts, senales=dict(base))
    con = _fila(posts, senales=dict(base, marcadores_culturales=[
        "bandera_mx", "latina", "fe", "familia", "hispanic_heritage"]))
    assert senales_de(sin) == senales_de(con)
    assert categorias_acreditadas(sin) == categorias_acreditadas(con)
    assert bio_legible(sin) == bio_legible(con)
    assert idioma_de(sin, "realtor_activo") == idioma_de(con, "realtor_activo")


def test_S8_ya_no_se_acredita_desde_identidad():
    from motor.desde_instagram import CATEGORIAS_POR_SEÑAL
    assert "S8" not in set(CATEGORIAS_POR_SEÑAL.values())


# ══ S6 · POR TOKEN, NUNCA POR SUBCADENA ══════════════════════════════════════

def test_las_seis_cuentas_del_golden():
    assert clasificar_cuenta("@titleist")[0] != "title"
    assert clasificar_cuenta("@providencetitlecompany")[0] == "title"
    assert clasificar_cuenta("@creditbyana_ejemplo")[0] == "credit_repair"
    assert clasificar_cuenta("@youragent_ejemplo")[0] == "agente"
    assert clasificar_cuenta("carlo_ejemplo")[0] != "lender"
    assert clasificar_cuenta("@ejemploloans")[0] == "lender"


def test_lo_que_no_se_puede_clasificar_queda_en_verificar():
    """NUNCA en `lender` por descarte."""
    for h in ("@algoraro", "@xyz123", "@"):
        assert clasificar_cuenta(h)[0] == "verificar", h


# ══ PARSEO ═══════════════════════════════════════════════════════════════════

def test_los_cinco_casos_de_seguidores():
    assert parsear_conteo("1.234") == 1234
    assert parsear_conteo("12,5K") == 12500
    assert parsear_conteo("12.5K") == 12500
    assert parsear_conteo("1,2 M") == 1200000
    assert parsear_conteo("") is None


def test_lo_que_no_es_un_conteo_da_None_y_no_cero():
    for v in (None, "muchos", "1.5", "abc", "12,,5K"):
        assert parsear_conteo(v) is None, v


def test_engagement_mayor_que_uno_no_se_usa():
    assert engagement_utilizable(0.04) == (0.04, False)
    assert engagement_utilizable(1.8) == (None, True)


# ══ EL LEXICO ════════════════════════════════════════════════════════════════

def test_ningun_patron_de_NO_USAR_esta_suelto_en_LEX():
    """La tabla de lo que no se usa es DATO, no un comentario.

    Un comentario que dice «no usar X» no impide que alguien use X.
    """
    import re

    def alternativas_de_primer_nivel(patron: str) -> list[str]:
        """Partir por `|` SOLO fuera de paréntesis.

        La primera versión partía la cadena entera y sacaba `foreclosure` de
        dentro de `(after|después de) (…|foreclosure|…)`, donde sí tiene el
        contexto que lo hace válido. Una prueba que acusa a lo bueno se termina
        apagando, que es peor que no tenerla.
        """
        partes, actual, prof = [], [], 0
        for ch in patron:
            if ch == "(":
                prof += 1
            elif ch == ")":
                prof -= 1
            if ch == "|" and prof == 0:
                partes.append("".join(actual))
                actual = []
            else:
                actual.append(ch)
        partes.append("".join(actual))
        return partes

    culpables = []
    for malo in NO_USAR:
        for clave, patron in LEX.items():
            for alt in alternativas_de_primer_nivel(patron.pattern):
                pelado = re.sub(r"[\\()\[\]]|\\b", "", alt).strip()
                if pelado == malo:
                    culpables.append((clave, malo, alt))
    assert not culpables, culpables


def test_primera_casa_sola_en_UN_post_no_activa_P_Q07():
    """La regla 6 medida: `primera` en 1 post disparaba en el 37,9% del lote.

    Las citas reales dicen por qué: «Perfect for families, first-time buyers»
    es un atributo de listado y «el cierre de su primera casa» es una historia
    de cierre. Las dos son mención, no verbalización.
    """
    uno = ["2026-09-01 | Perfect for families, first-time buyers, or anyone "
           "looking for a property"]
    assert _q(uno, "P-Q07") is None
    dos = uno + ["2026-08-01 | ¿Quieres comprar tu primera casa? Te explico "
                 "el proceso"]
    assert _q(dos, "P-Q07") == (2, "E1")


def test_la_tasa_de_disparo_se_puede_medir_sin_red():
    """La alarma del 25% de la regla 6, sobre un lote sintético.

    La medición que vale es la del lote real y va en el reporte; esto fija el
    MECANISMO, para que exista una prueba que falle si alguien afloja un léxico
    y lo dispara en todo el mundo.
    """
    lote = []
    for i in range(20):
        posts = ["2026-09-01 | New listing open house 3 bedrooms"]
        if i < 3:                      # 3 de 20 = 15%, por debajo del 25%
            posts.append("2026-09-02 | Aceptamos ITIN, personas con ITIN "
                         "califican")
        lote.append(posts)

    disparos: dict = {}
    for posts in lote:
        for s in senales_de_posts(_fila(posts), "realtor_activo"):
            disparos[s.qualifier] = disparos.get(s.qualifier, 0) + 1
    for q, n in disparos.items():
        assert n / len(lote) <= 0.25, (q, n / len(lote))


def test_la_huella_del_lexico_cambia_si_cambia_un_patron():
    from ingest.instagram import lexico
    antes = lexico.huella()
    original = lexico._LEX_CRUDO["itin"]
    try:
        lexico._LEX_CRUDO["itin"] = original + "|zzz"
        assert lexico.huella() != antes
    finally:
        lexico._LEX_CRUDO["itin"] = original
    assert lexico.huella() == antes


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
