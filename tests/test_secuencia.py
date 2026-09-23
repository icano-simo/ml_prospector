"""La secuencia de 7 toques: sin promesas, sin folleto, una idea por mensaje."""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.lectura import ES_NUESTRO_CLIENTE, Lectura, VocabularioInvalido  # noqa
from motor.recursos import CATALOGO  # noqa: E402
from motor.secuencia import (  # noqa: E402
    ADJETIVOS_DE_FOLLETO,
    PROMESAS_DE_MATERIAL,
    TOQUES_PENDIENTES,
    CopyInvalido,
    Toque,
    armar_secuencia,
    verificar_cierra_con_pregunta_u_oferta,
    verificar_sin_folleto,
    verificar_sin_promesas,
    verificar_una_sola_idea,
)

GANCHO = ("¿Te ha pasado que el agente del vendedor sabe más del avance de tu "
          "préstamo que tú?")
SOLANO = {"fallout": 35.6, "time_to_close": 32, "mkt_fha": 16.0}
ZONA = ("Dos y medio de cada diez compradores de Solano son primerizos; uno de "
        "cada veinte son veteranos; el ingreso medio del hogar ronda los "
        "168.000 dólares")
APERTURA = ("¿Con qué lender estás cerrando hoy, y qué es lo que más se te "
            "complica con ellos — el pre-approval, los tiempos o el closing?")


def _seq(lecturas=()):
    return armar_secuencia(nombre="Armando", gancho=GANCHO, mercado=SOLANO,
                           donde="Solano", perfil_zona=ZONA,
                           lecturas=list(lecturas),
                           apertura_sin_dolor=APERTURA)


# ══ NINGUNA PROMESA DE MATERIAL ══════════════════════════════════════════════

def test_ningun_toque_promete_material():
    seq = _seq()
    assert not seq.promete_material
    assert all(t.recursos == () for t in seq.toques)


def test_prometer_material_revienta_al_construir():
    """Es la misma forma que la guarda del vocabulario: regla ejecutable."""
    for frase in ("Te dejo el desglose de documentación.",
                  "Te mando el mapa de DPA de tu condado.",
                  "Te comparto la guía de ITIN.",
                  "Te paso el material completo."):
        try:
            Toque(2, 3, "email", None, frase + "\n\n¿Te sirve?")
        except CopyInvalido as exc:
            assert "promete material" in str(exc)
        else:
            raise AssertionError("%r tendría que reventar" % frase)


def test_la_lista_de_promesas_cubre_las_seis_formas_del_brief():
    for frase in ("te dejo", "te mando", "te comparto", "el mapa de",
                  "el desglose de", "la guía"):
        assert frase in PROMESAS_DE_MATERIAL


def test_el_catalogo_sigue_sin_verificar_y_eso_es_el_estado_real():
    """Los seis quedan registrados como pendientes, no borrados: cuando
    alguien confirme cuáles existen vuelven como refuerzo, no como promesa."""
    assert len(CATALOGO) == 6
    assert all(not r.verificado for r in CATALOGO.values())


def test_ninguna_descripcion_del_catalogo_usa_vocabulario_prohibido():
    """Una descripción que lo incumple se acaba copiando a un mensaje."""
    from motor.lectura import verificar_vocabulario

    for r in CATALOGO.values():
        verificar_vocabulario(r.descripcion)


# ══ NADA DE FOLLETO ══════════════════════════════════════════════════════════

def test_los_adjetivos_de_folleto_revientan():
    for frase in ("Somos tu aliado estratégico.",
                  "Ofrecemos soluciones innovadoras.",
                  "Queremos potenciar tu negocio."):
        try:
            verificar_sin_folleto(frase)
        except CopyInvalido as exc:
            assert "cualquier lender" in str(exc)
        else:
            raise AssertionError("%r es folleto" % frase)


def test_la_lista_de_folleto_trae_los_tres_del_brief():
    for frase in ("soluciones innovadoras", "aliado estratégico",
                  "potenciar tu negocio"):
        assert frase in ADJETIVOS_DE_FOLLETO


# ══ UNA SOLA COSA, Y EL CIERRE ═══════════════════════════════════════════════

def test_mas_de_dos_parrafos_es_mas_de_una_idea():
    try:
        verificar_una_sola_idea("uno\n\ndos\n\ntres")
    except CopyInvalido as exc:
        assert "sobra una" in str(exc)
    else:
        raise AssertionError("tres párrafos son dos ideas de más")


def test_el_ultimo_parrafo_lleva_pregunta_u_oferta():
    verificar_cierra_con_pregunta_u_oferta("Un dato.\n\n¿Te cuadra?")
    verificar_cierra_con_pregunta_u_oferta("Un dato.\n\nSi querés lo reviso.")
    try:
        verificar_cierra_con_pregunta_u_oferta(
            "Un dato.\n\nQuedo atento a tus comentarios. Saludos cordiales.")
    except CopyInvalido as exc:
        assert "cierre de cortesía" in str(exc)
    else:
        raise AssertionError("el último párrafo es el que se lee primero")


def test_todos_los_toques_cierran_con_pregunta_u_oferta():
    for t in _seq().toques:
        verificar_cierra_con_pregunta_u_oferta(t.cuerpo)


# ══ EL GANCHO NO SE TOCA ═════════════════════════════════════════════════════

def test_el_toque_1_es_el_gancho_literal():
    """Son literales de la matriz y están calibrados: no se reescriben ni se
    envuelven en una presentación."""
    t1 = _seq().toques[0]
    assert t1.cuerpo == GANCHO
    assert "HomeSí" not in t1.cuerpo, "no empieza por quiénes somos"


# ══ EL TOQUE 2 ENTREGA UN DATO REAL ══════════════════════════════════════════

def test_el_toque_2_da_el_dato_de_SU_mercado():
    t2 = [t for t in _seq().toques if t.numero == 2][0]
    assert "Solano" in t2.cuerpo
    # Masculino: el sustantivo que sigue es `expedientes`. Y sin `de los`
    # detrás: `_hablado` ya trae el `de cada diez`.
    assert "tres y medio de cada diez expedientes" in t2.cuerpo
    assert "de cada diez de los" not in t2.cuerpo
    assert "35.6" in t2.fuente_del_valor


def test_el_toque_7_no_dice_un_numero_de_intentos_que_no_es():
    """Decir `tres veces` cuando fueron dos es la clase de error que el lector
    sí nota, y quema todo lo demás que el mensaje afirma."""
    t7 = [t for t in _seq().toques if t.numero == 7][0]
    assert "cuatro veces" in t7.cuerpo

    sin_t2 = armar_secuencia(nombre="X", gancho=GANCHO, mercado={},
                             donde="Solano", perfil_zona=ZONA, lecturas=[],
                             apertura_sin_dolor=APERTURA)
    t7b = [t for t in sin_t2.toques if t.numero == 7][0]
    assert "tres veces" in t7b.cuerpo


def test_el_toque_2_da_UNA_cifra_no_tres():
    """La regla dice una sola cosa: apilar fallout, días y FHA son tres."""
    t2 = [t for t in _seq().toques if t.numero == 2][0]
    assert "32 días" not in t2.cuerpo
    assert "FHA" not in t2.cuerpo


def test_sin_dato_de_mercado_el_toque_2_NO_sale_y_se_dice():
    seq = armar_secuencia(nombre="X", gancho=GANCHO, mercado={},
                          donde="Solano", perfil_zona=None, lecturas=[],
                          apertura_sin_dolor=APERTURA)
    assert not [t for t in seq.toques if t.numero == 2]
    assert any("sin dato de mercado" in n for n in seq.notas)


# ══ EL TOQUE 4 · OBSERVACION O PREGUNTA ══════════════════════════════════════

def test_el_toque_4_usa_el_contraste_cuando_AFIRMA():
    lec = Lectura(
        que_dice_del_borrower=("Cuatro de cada diez de sus operaciones son "
                               "FHA, cuando en Solano son una y media."),
        bueno_o_malo=ES_NUESTRO_CLIENTE,
        que_hacer="Le sostenemos el pre-approval antes de la oferta.",
        evidencia="FHA 40% contra 16%", afirma=True,
        para_el_realtor=("Cuatro de cada diez de tus operaciones cierran con "
                         "FHA, contra una y media en Solano.\n\n"
                         "¿Lo ves igual desde tu lado?"))
    t4 = [t for t in _seq([lec]).toques if t.numero == 4][0]
    assert "FHA" in t4.cuerpo
    assert "contraste activo" in t4.fuente_del_valor


def test_el_toque_4_le_habla_a_EL_y_no_de_el():
    """El cuerpo es lo que se le manda, no la lectura interna.

    Antes se pegaba `que_dice_del_borrower` --tercera persona, con su nombre--
    mas `que_hacer`, que es una instruccion para el BD. A Armando le llegaba
    «Armando trabaja con compradores que…» y «Ofrecerle que el caso se origine».
    """
    lec = Lectura(
        que_dice_del_borrower="Armando trabaja con compradores que usan FHA.",
        bueno_o_malo=ES_NUESTRO_CLIENTE,
        que_hacer="Ofrecerle que el caso se origine en la misma casa.",
        evidencia="FHA 40% contra 16%", afirma=True,
        para_el_realtor=("Cuatro de cada diez de tus operaciones son FHA.\n\n"
                         "¿Lo ves igual?"))
    t4 = [t for t in _seq([lec]).toques if t.numero == 4][0]
    assert t4.cuerpo.startswith("Cuatro de cada diez de tus operaciones")
    assert "Armando trabaja" not in t4.cuerpo
    assert "Ofrecerle" not in t4.cuerpo


def test_una_lectura_que_afirma_sin_segunda_persona_no_se_puede_construir():
    """La guarda esta en `Lectura`, no en el toque: nace verificada."""
    try:
        Lectura(que_dice_del_borrower="Usa FHA.",
                bueno_o_malo=ES_NUESTRO_CLIENTE,
                que_hacer="Abrir por el perfil del comprador.",
                afirma=True)
    except ValueError:
        return
    raise AssertionError("una lectura que afirma sin `para_el_realtor` se creó")


def test_sin_contraste_que_active_el_toque_4_es_la_pregunta_del_lender():
    t4 = [t for t in _seq().toques if t.numero == 4][0]
    assert t4.cuerpo == APERTURA
    assert "cierre de brecha" in t4.fuente_del_valor


def test_una_lectura_que_NO_afirma_no_alcanza_para_el_toque_4():
    """Afirmar sobre una base corta es lo que las guardias evitan."""
    lec = Lectura(que_dice_del_borrower="Base corta.", bueno_o_malo="neutro",
                  que_hacer="Preguntarle cuántas cerró con FHA.",
                  evidencia="no activo", afirma=False)
    t4 = [t for t in _seq([lec]).toques if t.numero == 4][0]
    assert t4.cuerpo == APERTURA


# ══ LOS QUE NO ESTAN ═════════════════════════════════════════════════════════

def test_los_toques_5_y_6_no_se_rellenan_para_llegar_a_siete():
    seq = _seq()
    numeros = [t.numero for t in seq.toques]
    assert 5 not in numeros and 6 not in numeros
    assert TOQUES_PENDIENTES == (5, 6)
    assert any("no están escritos" in n for n in seq.notas)


def test_todo_el_copy_generado_pasa_las_tres_guardas():
    """Corre sobre los cinco toques, no sobre uno."""
    from motor.lectura import verificar_vocabulario

    toques = _seq().toques
    assert len(toques) == 5
    for t in toques:
        verificar_vocabulario(t.cuerpo)
        verificar_sin_promesas(t.cuerpo)
        verificar_sin_folleto(t.cuerpo)


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
