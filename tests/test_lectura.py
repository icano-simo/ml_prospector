"""La capa de lectura: tres campos, vocabulario y la guardia que manda.

Sin red y sin base.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.contrastes import mix_de_programa  # noqa: E402
from motor.lectura import (  # noqa: E402
    ES_NUESTRO_CLIENTE,
    FRICCION_RESOLUBLE,
    NEUTRO,
    PALABRAS_PROHIBIDAS,
    VEREDICTOS,
    Lectura,
    VocabularioInvalido,
    de_cada_diez,
    leer_canal_tpo,
    leer_mix_fha,
    leer_perfil_del_comprador,
    verificar_vocabulario,
)
from motor.sin_dolor import (  # noqa: E402
    COLA_CONTACTO,
    COLA_ENRIQUECIMIENTO,
    copy_sin_dolor,
    titular_del_reporte,
)

MIX_ARMANDO = {
    "filas": [{"tipo": "FHA", "unidades": 2, "share": 66.7},
              {"tipo": "HE (Home Equity)", "unidades": 1, "share": 33.3}],
    "unidades_identificadas": 3.0, "buyer_units": 9.0, "cobertura": 33.3,
}
MIX_SOLIDO = {
    "filas": [{"tipo": "FHA", "unidades": 18, "share": 40.0}],
    "unidades_identificadas": 45.0, "buyer_units": 60.0, "cobertura": 75.0,
}
SOLANO = [{"nivel": "condado", "estado": "CA", "etiqueta": "Solano",
           "metricas": {"mkt_fha": 16.0, "fallout": 35.6}}]


# ══ NUMEROS EN LENGUAJE HABLADO ══════════════════════════════════════════════

def test_los_numeros_se_dicen_hablados():
    """`cuatro de cada diez` antes que `40%`: se lee sin traducir."""
    assert de_cada_diez(40.0) == "cuatro de cada diez"
    assert de_cada_diez(16.0, femenino=True) == "una y media de cada diez"
    assert de_cada_diez(22.2) == "dos de cada diez"
    assert de_cada_diez(66.7) == "seis y medio de cada diez"
    # `medio de cada diez` se entiende y suena torpe: es el único caso donde
    # la forma de veinte se lee mejor y dice exactamente lo mismo.
    assert de_cada_diez(5.1) == "uno de cada veinte"
    assert de_cada_diez(5.1, femenino=True) == "una de cada veinte"


def test_por_debajo_del_5_por_ciento_no_hay_forma_hablada():
    """3,8% redondearia a `medio de cada diez` -- 5%. El desvio absoluto es
    chico y el RELATIVO es un tercio: a esa escala el numero hablado deja de
    describir el dato."""
    assert de_cada_diez(3.8) is None
    assert de_cada_diez(3.2) is None
    assert de_cada_diez(5.0) is not None


def test_el_redondeo_no_se_desvia_mas_de_lo_declarado():
    """Redondear al medio decimo desvia como mucho 2,5 puntos, y eso esta
    dicho. El numero exacto viaja siempre en la evidencia."""
    from motor.lectura import DESVIO_MAXIMO_PP, MINIMO_HABLADO, _CARDINALES

    inverso = {v: k for k, v in _CARDINALES.items()}
    for centesima in range(int(MINIMO_HABLADO * 10), 951):
        pct = centesima / 10.0
        dicho = de_cada_diez(pct)
        assert dicho is not None, "%s no tiene forma hablada" % pct
        if dicho == "uno de cada veinte":
            valor = 0.5
            assert abs(valor * 10 - pct) <= DESVIO_MAXIMO_PP, (pct, dicho)
            continue
        palabra = dicho.replace(" de cada diez", "")
        if " y medio" in palabra:
            valor = inverso[palabra.split(" y ")[0]] + 0.5
        else:
            valor = inverso[palabra]
        assert abs(valor * 10 - pct) <= DESVIO_MAXIMO_PP, (pct, dicho)


def test_fuera_de_rango_no_hay_forma_hablada():
    assert de_cada_diez(None) is None
    assert de_cada_diez(98.0) is None, "por arriba de 95 la forma estorba"
    assert de_cada_diez(-1) is None


# ══ EL VOCABULARIO, COMPROBABLE ══════════════════════════════════════════════

def test_enganche_esta_prohibido():
    """Es de Mexico y Centroamerica, no del sector en EE.UU."""
    try:
        verificar_vocabulario("Tiene poco para el enganche.")
    except VocabularioInvalido as exc:
        assert "down payment" in str(exc)
    else:
        raise AssertionError("`enganche` no se usa acá")


def test_banda_baja_de_credito_esta_prohibida():
    """No existe. Se dice el rango."""
    try:
        verificar_vocabulario("Cliente de banda baja de crédito.")
    except VocabularioInvalido as exc:
        assert "580 y 669" in str(exc)
    else:
        raise AssertionError("no existe esa expresión")


def test_los_tecnicos_traducidos_tambien_estan_prohibidos():
    """Traducirlos suena a folleto y delata que no se conoce el oficio."""
    for mala in ("pago inicial", "costos de cierre", "puntaje de crédito",
                 "pre-aprobación", "informe de crédito",
                 "relación deuda-ingreso"):
        try:
            verificar_vocabulario("Le explicamos el %s." % mala)
        except VocabularioInvalido:
            pass
        else:
            raise AssertionError("%r tendría que estar prohibido" % mala)


def test_los_terminos_en_ingles_pasan():
    verificar_vocabulario(
        "Le sostenemos el pre-approval, le explicamos los closing costs y el "
        "DTI, y trabajamos score desde 580 con su credit report al día. "
        "El down payment lo armamos aparte.")


def test_una_Lectura_con_vocabulario_malo_no_se_puede_construir():
    """La guarda corre al construir, no al revisar despues."""
    try:
        Lectura(que_dice_del_borrower="No tiene para el enganche.",
                bueno_o_malo=NEUTRO, que_hacer="Preguntar.")
    except VocabularioInvalido:
        pass
    else:
        raise AssertionError("tiene que fallar al construirla")


def test_un_veredicto_fuera_de_la_lista_no_se_puede_construir():
    """`bueno_o_malo` es explicito, nunca a interpretacion."""
    try:
        Lectura(que_dice_del_borrower="x", bueno_o_malo="mas o menos",
                que_hacer="y")
    except ValueError as exc:
        assert "nunca se deja a interpretacion" in str(exc)
    else:
        raise AssertionError("los veredictos son cinco y cerrados")


def test_los_cinco_veredictos_son_los_del_brief():
    assert set(VEREDICTOS) == {
        "es nuestro cliente", "no es nuestro cliente",
        "fricción que podemos resolver", "señal de alerta", "neutro"}


# ══ TRES CAMPOS, NO UNO ══════════════════════════════════════════════════════

def test_el_contraste_devuelve_los_tres_campos():
    c = mix_de_programa(MIX_SOLIDO, SOLANO, tipo="FHA")[0]
    lec = leer_mix_fha(c, "Armando")
    assert lec.que_dice_del_borrower and lec.bueno_o_malo and lec.que_hacer
    assert lec.bueno_o_malo == ES_NUESTRO_CLIENTE


def test_la_lectura_habla_del_BORROWER_no_del_agente():
    """El agente es el intermediario; lo que importa es quien es su cliente."""
    c = mix_de_programa(MIX_SOLIDO, SOLANO, tipo="FHA")[0]
    texto = leer_mix_fha(c, "Armando").que_dice_del_borrower
    assert "down payment" in texto
    assert "score entre 580 y 669" in texto
    assert "compradores" in texto or "cliente" in texto


def test_la_lectura_dice_los_numeros_hablados():
    c = mix_de_programa(MIX_SOLIDO, SOLANO, tipo="FHA")[0]
    texto = leer_mix_fha(c, "Armando").que_dice_del_borrower
    assert "Cuatro de cada diez de sus operaciones son FHA" in texto
    assert "una y media de cada diez" in texto


# ══ LA GUARDIA MANDA SOBRE LA LECTURA ════════════════════════════════════════

def test_un_contraste_que_no_activa_NO_afirma():
    """Escribir `es exactamente el cliente que sabemos cerrar` sobre tres
    operaciones es justo lo que las guardias existen para impedir."""
    c = mix_de_programa(MIX_ARMANDO, SOLANO, tipo="FHA")[0]
    lec = leer_mix_fha(c, "Armando")
    assert lec.afirma is False
    assert lec.bueno_o_malo == NEUTRO
    assert "es exactamente el cliente" not in lec.que_dice_del_borrower


def test_cuando_no_afirma_el_que_hacer_es_la_PREGUNTA_que_lo_confirma():
    c = mix_de_programa(MIX_ARMANDO, SOLANO, tipo="FHA")[0]
    lec = leer_mix_fha(c, "Armando")
    assert lec.que_hacer.strip().startswith("Preguntarle")
    assert "?" in lec.que_hacer or "cuántas" in lec.que_hacer


def test_cuando_SI_activa_el_que_hacer_es_una_frase_usable():
    c = mix_de_programa(MIX_SOLIDO, SOLANO, tipo="FHA")[0]
    lec = leer_mix_fha(c, "Armando")
    assert lec.afirma is True
    assert "pre-approval" in lec.que_hacer


def test_la_evidencia_viaja_con_la_lectura():
    """Para `Cómo se calculó`: la lectura sin su evidencia es una opinion."""
    c = mix_de_programa(MIX_ARMANDO, SOLANO, tipo="FHA")[0]
    lec = leer_mix_fha(c, "Armando")
    assert "NO activo" in lec.evidencia
    # 4,2 y no 20,8: este contraste es contra SOLANO. El 20,8 es Alameda, y
    # confundirlos en la prueba es exactamente el error que la capa evita.
    assert "4.2" in lec.evidencia
    assert "hacen falta 10" in lec.evidencia


# ══ EL CANAL ═════════════════════════════════════════════════════════════════

def test_el_canal_es_FRICCION_no_descarte():
    """Cada mano extra en el expediente es un punto mas donde el caso se cae.
    Eso se resuelve, no se descarta."""
    lec = leer_canal_tpo(66.7, {"banked_wholesale": 19.3, "brokered": 5.1},
                         "Armando", "Solano", fallout_mercado=35.6)
    assert lec.bueno_o_malo == FRICCION_RESOLUBLE
    assert "no colocan el préstamo en su propia casa" in lec.que_dice_del_borrower
    assert "misma casa" in lec.que_hacer


def test_sin_dato_de_canal_se_pregunta_y_no_se_concluye():
    lec = leer_canal_tpo(None, None, "Armando", "Solano")
    assert lec.bueno_o_malo == NEUTRO
    assert lec.afirma is False


# ══ EL PERFIL DEL COMPRADOR · describe a quien le VENDE ══════════════════════

def test_el_perfil_va_como_parrafo_y_describe_a_los_compradores():
    texto = leer_perfil_del_comprador(
        {"ftb": 26.4, "veterans": 3.2, "credit_fair": 13.9,
         "avg_income": 168000.0},
        {"cuenta_propia_pct": 8.7, "espanol_en_casa_pct": 20.0,
         "ingles_limitado_sobre_espanol_pct": 40.0,
         "carga_hipoteca_30mas_pct": 34.8},
        "Solano")
    assert "primerizos" in texto
    assert "score entre 580 y 669" in texto
    assert "hablan español en casa" in texto
    assert "W-2" in texto
    assert ";" in texto, "va como párrafo, no como lista"


def test_sin_datos_el_perfil_lo_dice_en_vez_de_inventar():
    assert "No tenemos perfil" in leer_perfil_del_comprador({}, None, "X")


# ══ EL CASO MAS FRECUENTE · 40,4% SIN DOLOR ══════════════════════════════════

def test_el_titular_va_arriba_y_en_lenguaje_hablado():
    t = titular_del_reporte(1716, 4249)
    assert "cuatro" in t
    assert "1.716" in t and "4.249" in t
    assert "no es un fallo del motor" in t.lower()


def test_el_copy_se_ramifica_por_lo_poco_que_si_sabemos():
    """Un generico igual para todos desperdicia los cuatro datos que si hay."""
    alto = copy_sin_dolor({"nombre_completo": "LISA MUNOZ", "estado": "TX",
                           "unidades_ano": 124.0, "brokerage": "eXp"})
    bajo = copy_sin_dolor({"nombre_completo": "OTRO", "estado": "TX",
                           "unidades_ano": 3.0})
    assert alto.cuerpo != bajo.cuerpo
    assert "relación establecida" in alto.cuerpo
    assert "part-time" in bajo.cuerpo
    assert "eXp" in alto.cuerpo
    assert alto.rama != bajo.rama


def test_el_nombre_en_mayusculas_del_libro_no_grita_en_la_frase():
    c = copy_sin_dolor({"nombre_completo": "LISA MUNOZ", "estado": "TX",
                        "unidades_ano": 124.0})
    assert "Lisa Munoz" in c.cuerpo
    assert "LISA MUNOZ" not in c.cuerpo


def test_la_apertura_es_SIEMPRE_la_pregunta_del_lender():
    """Cierra la categoria vacia en el 100% de las filas: es lo unico que
    sabemos que falta en todas."""
    aperturas = {copy_sin_dolor(r).apertura for r in (
        {"nombre_completo": "A", "estado": "TX", "unidades_ano": 100.0},
        {"nombre_completo": "B", "estado": "CA"},
        {"nombre_completo": "C", "estado": "FL", "unidades_ano": 2.0,
         "brokerage": "Keller"})}
    assert len(aperturas) == 1, "la apertura no se ramifica"
    assert "lender" in aperturas.pop()


def test_van_a_cola_de_ENRIQUECIMIENTO_y_no_de_contacto():
    """Llamar sin saber nada quema el contacto y no devuelve informacion."""
    c = copy_sin_dolor({"nombre_completo": "A", "estado": "TX"})
    assert c.cola == COLA_ENRIQUECIMIENTO
    assert c.cola != COLA_CONTACTO
    assert "su Instagram" in c.falta
    assert "su perfil de Model Match" in c.falta


def test_el_titular_dice_que_lo_que_falta_es_NUESTRO():
    c = copy_sin_dolor({"nombre_completo": "A", "estado": "TX"})
    assert "no es del realtor" in c.titular


def test_todo_el_copy_sin_dolor_pasa_el_vocabulario():
    """La guarda corre al construir; esto comprueba que corre de verdad sobre
    las tres ramas y no solo sobre una."""
    for r in ({"nombre_completo": "A", "estado": "TX", "unidades_ano": 100.0},
              {"nombre_completo": "B", "estado": "CA", "unidades_ano": 10.0},
              {"nombre_completo": "C", "estado": "FL", "unidades_ano": 1.0},
              {"nombre_completo": "D", "estado": "NV"}):
        c = copy_sin_dolor(r)
        for campo in (c.titular, c.cuerpo, c.apertura):
            verificar_vocabulario(campo)


def test_la_lista_de_prohibidas_no_esta_vacia():
    """Una guarda sobre una lista vacia pasa siempre."""
    assert len(PALABRAS_PROHIBIDAS) >= 10
    assert "enganche" in PALABRAS_PROHIBIDAS


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
