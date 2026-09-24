"""Cuando hay una medicion, la declaracion no manda.

Las dos correcciones de la comparacion contra la evaluacion ciega del
orquestador. No son dos arreglos parecidos: son el mismo, en dos lugares.

    J-Q01   el registro buy/sell de Model Match manda sobre la bio, y con
            J-Q01 <= 1 ningun dolor hipotecario puede ser el primario.
    P-Q14   el idioma del muro de Instagram manda sobre la bio, y una bio sin
            muro que la sostenga llega a 1/E1, no a 3/E0.

Los dos casos medidos, anonimizados: un realtor de 3 buy / 6 sell al que el
motor le ponia un angulo hipotecario de apertura, y otro de 9 / 3 con la bio
declarando atencion en español y 0 de 20 posts en español.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.desde_instagram import senales_de  # noqa: E402
from motor.evaluar import (  # noqa: E402
    APERTURA_SIN_HIPOTECA,
    UMBRAL_APERTURA,
    evaluar,
)
from supabase.correr_motor import (  # noqa: E402
    CAMPOS_MM,
    campos_de_modelmatch,
    share_del_lado_comprador,
)

#: Lo que el libro trae de los dos, sin Model Match ni Instagram todavia.
#: `E6_asequibilidad` en 3 activa P-Q06-2, que es el dolor hipotecario que
#: el motor le puso de apertura al que vive de listings.
DEL_LIBRO = {
    "E6_asequibilidad": 3,
    "ev2_primera_casa": True,
    "ev2_buy_side": True,
    "ev2_listing_side": False,
}


def _ev(reg):
    return evaluar(dict(reg), realtor_id="T-1")


# ══ 1 · EL SHARE SALE DE SIDE FOCUS, Y DE NADA MAS ═══════════════════════════

def test_el_share_sale_de_side_focus():
    """«3 buy / 6 sell» -> 0,3333. Es la unica fuente."""
    assert share_del_lado_comprador({"sf_buy": 3, "sf_sell": 6}) == 0.3333
    assert share_del_lado_comprador({"sf_buy": 9, "sf_sell": 3}) == 0.75


def test_sin_side_focus_el_share_es_None_y_no_cero():
    """Un cero diria «no cierra del lado comprador», que es otra afirmacion.

    `buyer_units` esta ahi y tienta, pero cuenta otra cosa con otro
    denominador: dos derivaciones que dan numeros parecidos y distintos son
    peores que una sola, porque nadie sabe cual leyo el motor.
    """
    assert share_del_lado_comprador({"buyer_units": 19.0}) is None
    assert share_del_lado_comprador({"sf_buy": 3}) is None
    assert share_del_lado_comprador({}) is None
    assert share_del_lado_comprador(None) is None
    # Y el 0/0 tampoco: sin operaciones no hay reparto que medir.
    assert share_del_lado_comprador({"sf_buy": 0, "sf_sell": 0}) is None
    # Pero 0 de 6 SI es una medicion: cero del lado comprador.
    assert share_del_lado_comprador({"sf_buy": 0, "sf_sell": 6}) == 0.0


def test_el_share_llega_al_motor_con_los_demas_mm():
    c = campos_de_modelmatch({"sf_buy": 3, "sf_sell": 6,
                              "buyside_anualizado": 2.6})
    assert c == {"mm_share_buy": 0.3333, "mm_buyside_anualizado": 2.6}
    assert "mm_share_buy" in CAMPOS_MM


# ══ 2 · LA COMPUERTA J-Q01, CON LOS DOS CASOS MEDIDOS ════════════════════════

def test_seller_heavy_no_recibe_un_angulo_hipotecario_de_apertura():
    """3 buy / 6 sell -> J-Q01 = 1 -> ningun dolor P abre la conversacion.

    El caso que lo motivo: el motor le puso P-Q06 de dolor primario a alguien
    que cierra dos tercios del lado vendedor. No es un dolor mal medido -- la
    evidencia de asequibilidad esta-- es un angulo que a el no le aplica.
    """
    reg = dict(DEL_LIBRO)
    reg.update(campos_de_modelmatch({"sf_buy": 3, "sf_sell": 6}))
    ev = _ev(reg)

    assert ev.gating is not None
    assert ev.gating.regla_id == "J-Q01-MM2"
    assert ev.gating.intensidad == 1
    assert ev.gating.intensidad <= UMBRAL_APERTURA
    assert ev.dolor_primario is None, ev.dolor_primario
    assert ev.apertura == APERTURA_SIN_HIPOTECA


def test_los_dolores_no_se_borran_solo_dejan_de_abrir():
    """Siguen en la cadena de evidencia. Lo que cambia es que no son la apertura.

    Borrarlos seria perder lo que si se midio; lo que no se puede es abrir con
    ellos.
    """
    reg = dict(DEL_LIBRO)
    reg.update(campos_de_modelmatch({"sf_buy": 3, "sf_sell": 6}))
    ev = _ev(reg)

    activados = {a.qualifier for a in ev.activaciones}
    assert "P-Q06" in activados, sorted(activados)
    assert ev.dolor_primario is None


def test_buy_heavy_si_recibe_su_angulo():
    """El control. 9 / 3 -> J-Q01 = 2 -> la compuerta queda abierta.

    Sin esto, la compuerta se «arregla» cerrandola para todos.
    """
    reg = dict(DEL_LIBRO)
    reg.update(campos_de_modelmatch({"sf_buy": 9, "sf_sell": 3}))
    ev = _ev(reg)

    assert ev.gating.regla_id == "J-Q01-MM1"
    assert ev.gating.intensidad == 2
    assert ev.gating.intensidad > UMBRAL_APERTURA
    assert ev.dolor_primario is not None
    assert ev.apertura != APERTURA_SIN_HIPOTECA


def test_con_model_match_la_bio_no_habla():
    """La bio declara buy_side y no listing_side: 3/E0, la mas fuerte que hay.

    Contra un registro de 3 de 9 operaciones del lado comprador, esa bio ganaba
    por grado. El dato mas fuerte perdia contra la declaracion.
    """
    reg = dict(DEL_LIBRO)
    reg.update(campos_de_modelmatch({"sf_buy": 3, "sf_sell": 6}))
    ev = _ev(reg)

    assert ev.gating.regla_id == "J-Q01-MM2"
    assert "J-Q01-1" not in ev.gating.tambien_activaron
    # Y sin Model Match la bio vuelve a hablar: no se le quito la voz, se le
    # dio prioridad a la medicion.
    ev2 = _ev(DEL_LIBRO)
    assert ev2.gating.regla_id == "J-Q01-1"
    assert ev2.gating.intensidad == 3


def test_sin_model_match_la_compuerta_no_se_inventa():
    """Sin registro y sin bio, J-Q01 queda sin evaluar y no cierra nada.

    Una compuerta que se cierra por falta de dato apagaria el diagnostico de
    todo el libro que todavia no tiene captura.
    """
    ev = _ev({"E6_asequibilidad": 3})
    assert ev.gating is None
    assert ev.dolor_primario == "P-Q06"
    assert ev.apertura is None
    assert "J-Q01-MM1" in {n.regla_id for n in ev.no_evaluadas}


# ══ 3 · P-Q14 · EL MURO MANDA SOBRE LA BIO ═══════════════════════════════════

MURO_EN_INGLES = {
    "estado_perfil": "publico_leido",
    "clase_perfil": "realtor_activo",
    "captions_n": 20,
    "senales": {"idioma_publica_es": 0, "idioma_publica_en": 20},
}
MURO_EN_ESPANOL = {
    "estado_perfil": "publico_leido",
    "clase_perfil": "realtor_activo",
    "captions_n": 20,
    "senales": {"idioma_publica_es": 17, "idioma_publica_en": 3},
}
BIO_QUE_DECLARA_ESPANOL = {"ev2_espanol_decl": True, "ev_caracteres_espanol": 4,
                           "R5_espanol": 8}


def test_instagram_emite_su_medicion_en_campo_propio():
    """`ev2_espanol_decl` no alcanza: el libro lo pisa. Hace falta un campo suyo."""
    s = senales_de(MURO_EN_INGLES)
    assert s["ig_idioma_es"] is False
    assert s["ig_idioma_posts"] == 20
    s2 = senales_de(MURO_EN_ESPANOL)
    assert s2["ig_idioma_es"] is True


def test_con_menos_de_diez_posts_no_hay_medicion():
    """La muestra minima ya estaba y sigue: 9 posts no acreditan idioma.

    Sin esta guarda, un muro de dos posts en ingles apagaria P-Q14 entero.
    """
    poco = dict(MURO_EN_INGLES, captions_n=9)
    s = senales_de(poco)
    assert "ig_idioma_es" not in s
    assert "ig_idioma_posts" not in s


def test_cero_de_veinte_posts_en_espanol_apaga_P_Q14():
    """El caso medido: bio que declara atencion en español, muro que no.

    Antes: P-Q14 = 3, grado E0, acto AFIRMA. O sea el motor afirmaba, sobre la
    base de una frase de la bio, algo que 20 posts suyos contradecian.
    """
    reg = dict(BIO_QUE_DECLARA_ESPANOL)
    reg.update(senales_de(MURO_EN_INGLES))
    ev = _ev(reg)

    assert "P-Q14" not in {a.qualifier for a in ev.activaciones}
    assert ev.dolor_primario != "P-Q14"


def test_diecisiete_de_veinte_si_lo_enciende_y_afirma():
    """El control, y la otra mitad de la decision: medido en español, 3/E0."""
    reg = dict(BIO_QUE_DECLARA_ESPANOL)
    reg.update(senales_de(MURO_EN_ESPANOL))
    ev = _ev(reg)

    a = next(x for x in ev.activaciones if x.qualifier == "P-Q14")
    assert a.regla_id == "P-Q14-IG"
    assert a.intensidad == 3
    assert a.grado == "E0"
    assert a.acto == "AFIRMA"


def test_la_bio_sola_llega_a_uno_y_pregunta():
    """Sin muro medido, la bio habla -- pero a 1/E1, y por lo tanto PREGUNTA.

    Estaba en 3/E0, que es AFIRMA: el motor le decia a un realtor que sus
    clientes chocan con la barrera del idioma con la misma fuerza que si lo
    hubiera medido, cuando la unica evidencia era su propia bio.
    """
    ev = _ev(BIO_QUE_DECLARA_ESPANOL)
    a = next(x for x in ev.activaciones if x.qualifier == "P-Q14")
    assert a.intensidad == 1
    assert a.grado == "E1"
    assert a.acto == "PREGUNTA"


def test_un_perfil_no_utilizable_no_apaga_nada():
    """La compuerta de perfil sigue primero: sin clase utilizable no hay medicion.

    Si un criadero de gallos pudiera apagar P-Q14, la compuerta de Instagram
    habria pasado de no dejar entrar señales a dejar entrar una negacion.
    """
    ajeno = dict(MURO_EN_INGLES, clase_perfil="personal_sin_re")
    assert senales_de(ajeno) == {}
    reg = dict(BIO_QUE_DECLARA_ESPANOL)
    reg.update(senales_de(ajeno))
    a = next(x for x in _ev(reg).activaciones if x.qualifier == "P-Q14")
    assert a.intensidad == 1, "la bio sigue hablando, ni mas ni menos"


# ══ 4 · LO QUE LA PANTALLA DICE CUANDO LA COMPUERTA CIERRA ══════════════════

REALTOR = {"nombre_completo": "NOMBRE DE PRUEBA", "estado": "FL",
           "unidades_ano": 30}


def test_la_compuerta_cerrada_no_se_cuenta_como_no_lo_sabemos():
    """Las dos formas de no tener dolor primario NO son la misma.

    Sin esto, un agente de listings caia en el copy de «lo que falta es
    nuestro» y en la cola de enriquecimiento -- cuando de el sabemos bastante,
    incluido lo que descarta el angulo. Es la diferencia entre no saber y saber
    que no.
    """
    from motor.sin_dolor import COLA_CONTACTO, COLA_ENRIQUECIMIENTO, copy_sin_dolor

    c = copy_sin_dolor(REALTOR, apertura_motor=APERTURA_SIN_HIPOTECA)
    assert c.rama == "sin apertura hipotecaria"
    assert c.cola == COLA_CONTACTO
    assert "lado vendedor" in c.cuerpo

    # El control: sin la compuerta, el copy de siempre y la cola de siempre.
    c2 = copy_sin_dolor(REALTOR)
    assert c2.cola == COLA_ENRIQUECIMIENTO
    assert c2.rama != "sin apertura hipotecaria"


def test_la_apertura_de_la_compuerta_no_promete_una_hipoteca():
    """Abrirle con financiamiento del comprador es decirle que no lo conocemos.

    Lo que si le duele: una venta suya que se cae porque al comprador no le
    sale el prestamo. Es el unico lugar donde una hipoteca le toca el negocio a
    un agente de listings.
    """
    from motor.sin_dolor import copy_sin_dolor

    c = copy_sin_dolor(REALTOR, apertura_motor=APERTURA_SIN_HIPOTECA)
    assert "?" in c.apertura
    assert "comprador no le salió el préstamo" in c.apertura
    # Y no es la pregunta del lender, que es la del otro caso.
    assert "Con qué lender estás cerrando" not in c.apertura


def test_ningun_codigo_interno_llega_al_texto_visible():
    """`sin_apertura_hipotecaria` es un identificador, no una frase."""
    from motor.sin_dolor import copy_sin_dolor

    c = copy_sin_dolor(REALTOR, apertura_motor=APERTURA_SIN_HIPOTECA)
    for campo in (c.titular, c.cuerpo, c.apertura):
        assert APERTURA_SIN_HIPOTECA not in campo
        assert "J-Q01" not in campo
        assert "mm_share_buy" not in campo


# ══ 5 · LO QUE NO SE PUEDE HEREDAR DE LA EVALUACION ANTERIOR ═════════════════

def test_todo_campo_de_model_match_se_recalcula_al_reevaluar():
    """El candado contra la forma de siempre.

    Un `mm_*` nuevo que no entre en `SE_RECALCULAN` se hereda de la `entrada`
    vieja, y la captura nueva no lo mueve: el valor de la captura anterior gana
    en silencio y nada falla.
    """
    from motor.reevaluacion import SE_RECALCULAN, base_del_libro

    faltan = set(CAMPOS_MM) - set(SE_RECALCULAN)
    assert not faltan, (
        "se heredarian de la evaluacion anterior en vez de recalcularse: %s"
        % sorted(faltan))

    base = base_del_libro({"ev2_itin": True, "mm_share_buy": 0.9,
                           "mm_buyside_anualizado": 30.0})
    assert base == {"ev2_itin": True}


def test_los_seguidores_del_libro_sobreviven_a_una_reevaluacion():
    """`ig_seguidores` SALIO de `SE_RECALCULAN`, y no es un descuido.

    El libro v3 trae la columna y en la corrida completa el libro gana --
    decision de Isabella, sin cambios. Pero la re-evaluacion lo borraba de la
    base heredada, asi que a quien no tiene muro leido se le perdian los
    seguidores en cada captura y las reglas que los leen pasaban de activarse a
    «no evaluada» sin que nadie tocara un dato.
    """
    from motor.reevaluacion import SE_RECALCULAN, base_del_libro

    assert "ig_seguidores" not in SE_RECALCULAN
    assert base_del_libro({"ig_seguidores": 12000.0}) == {
        "ig_seguidores": 12000.0}
    # Y con ellos, la regla que los lee se sigue activando.
    ev = _ev({"ig_seguidores": 12000.0})
    assert "G-Q04" in {a.qualifier for a in ev.activaciones}


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
