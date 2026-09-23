"""La verificación mecánica de lo que escribe un modelo.

La guarda que importa es la de cifras: es la única que atrapa un número
inventado, y ese es el modo de fallo que no se ve.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.verificar_texto import (  # noqa: E402
    CIFRAS_DE_OFICIO,
    cifras_de_los_insumos,
    cifras_del_texto,
    cifras_habladas,
    verificar_cifras,
    verificar_texto_generado,
)

#: El extracto real que se le daría al modelo para escribir de Armando.
INSUMOS = {
    "agente": {"fha_share": 66.7, "unidades_identificadas": 3,
               "buyer_units": 9, "unidades_ano_libro": 16},
    "mercado": {"donde": "Solano", "mkt_fha": 16.0, "fallout": 35.6,
                "avg_income": 168000},
    "contraste": {"veces": 4.2},
}


# ══ EXTRAER LAS CIFRAS ═══════════════════════════════════════════════════════

def test_lee_el_formato_español_y_el_ingles():
    assert cifras_del_texto("son 7,7 al año") == [7.7]
    assert cifras_del_texto("ingreso de 168.000 dólares") == [168000.0]
    assert cifras_del_texto("un 35.6% de fallout") == [35.6]
    assert cifras_del_texto("4.187 evaluaciones") == [4187.0]


def test_la_forma_hablada_cuenta_como_su_porcentaje():
    """`cuatro de cada diez` afirma un 40%: si el 40 no está en los insumos,
    la cifra se inventó igual que si estuviera en dígitos."""
    assert cifras_habladas("cuatro de cada diez son FHA") == [40.0]
    assert cifras_habladas("tres y medio de cada diez") == [35.0]
    assert cifras_habladas("una y media de cada diez") == [15.0]
    assert cifras_habladas("uno de cada veinte") == [5.0]


def test_el_diez_de_la_forma_hablada_NO_cuenta_como_cifra_suelta():
    """Es el denominador de la construcción, no un número que el texto afirme."""
    assert cifras_del_texto("cuatro de cada diez son FHA") == [40.0]
    assert 10.0 not in cifras_del_texto("cuatro de cada diez son FHA")


def test_las_cifras_de_los_insumos_salen_de_todo_el_jsonb():
    c = cifras_de_los_insumos(INSUMOS)
    for esperada in (66.7, 3, 9, 16, 16.0, 35.6, 168000, 4.2):
        assert float(esperada) in c, esperada


def test_un_booleano_de_los_insumos_no_es_una_cifra():
    """True vale 1 en Python: contarlo dejaría pasar cualquier `1` del texto."""
    assert cifras_de_los_insumos({"activa": True, "x": False}) == set()


# ══ LA GUARDA · UNA CIFRA QUE NO ESTA EN LOS INSUMOS SE RECHAZA ══════════════

def test_una_cifra_inventada_se_rechaza_con_el_numero_que_sobra():
    v = verificar_cifras(
        "En Solano se caen 35,6% de los expedientes y el cierre va en 21 días.",
        INSUMOS)
    assert not v.ok
    assert 21.0 in v.cifras_sobrantes
    assert "21" in v.motivo
    assert "se inventó" in v.motivo


def test_un_texto_que_solo_usa_los_insumos_pasa():
    v = verificar_cifras(
        "Su FHA es 66,7% contra 16% del mercado: 4,2 veces. Son 3 operaciones "
        "con tipo identificado sobre 9 del lado comprador.", INSUMOS)
    assert v.ok, v.cifras_sobrantes
    assert v.cifras_comprobadas >= 5


def test_la_forma_hablada_se_compara_contra_el_dato_con_su_tolerancia():
    """`tres y medio de cada diez` son 35 y el fallout real es 35,6: el
    redondeo de la forma hablada desvía hasta 2,5 puntos, y está declarado."""
    v = verificar_cifras("Se caen tres y medio de cada diez expedientes.",
                         INSUMOS)
    assert v.ok, v.cifras_sobrantes


def test_una_forma_hablada_que_NO_sale_del_dato_se_rechaza():
    """`ocho de cada diez` son 80 y no hay ningún 80 en los insumos."""
    v = verificar_cifras("Ocho de cada diez de sus casos son FHA.", INSUMOS)
    assert not v.ok
    assert 80.0 in v.cifras_sobrantes


def test_rechaza_una_cifra_PLAUSIBLE_de_otra_geografia():
    """El modo de fallo que importa: formato correcto, orden correcto, otro
    condado. `7,1` es el contraste de Contra Costa y `20,8` el de Alameda.

    Los tres primeros PASABAN hasta que la tolerancia del redondeo hablado
    dejó de aplicarse a los dígitos: `7,1` coincidía con el 9 de los insumos
    por estar a 1,9 de distancia.
    """
    for texto, sobra in (("Su FHA va 7,1 veces sobre el mercado.", 7.1),
                         ("Su FHA va 20,8 veces sobre el mercado.", 20.8),
                         ("Cierra 17 operaciones al año.", 17.0),
                         ("Tiene 10 del lado comprador.", 10.0),
                         ("El fallout es 31,1%.", 31.1),
                         ("El ingreso medio es 247.000.", 247000.0)):
        v = verificar_cifras(texto, INSUMOS)
        assert not v.ok, texto
        assert sobra in v.cifras_sobrantes, (texto, v.cifras_sobrantes)


def test_acepta_las_mismas_cifras_cuando_SI_son_las_suyas():
    """La guarda tiene que poder no disparar, o no distingue nada."""
    for texto in ("Su FHA va 4,2 veces sobre el mercado.",
                  "Cierra 16 operaciones al año.",
                  "Tiene 9 del lado comprador.",
                  "El fallout es 35,6%.",
                  "El ingreso medio es 168.000."):
        assert verificar_cifras(texto, INSUMOS).ok, texto


def test_el_redondeo_a_miles_si_se_tolera():
    """`168.000` contra un insumo de 168.123 es redondeo, no invención."""
    assert verificar_cifras("ingreso de 168.000 dólares",
                            {"avg_income": 168123}).ok


def test_las_cifras_del_oficio_no_cuentan_como_inventadas():
    """580 y 669 son el rango de score que trabajamos, no un dato suyo."""
    v = verificar_cifras("Su cliente tiene score entre 580 y 669.", INSUMOS)
    assert v.ok
    assert 580.0 in CIFRAS_DE_OFICIO and 669.0 in CIFRAS_DE_OFICIO


def test_la_lista_de_cifras_de_oficio_es_corta_y_cada_una_dice_por_que():
    """Cada número que se agrega es una cifra que la guarda deja de mirar."""
    assert len(CIFRAS_DE_OFICIO) <= 10
    assert all(isinstance(v, str) and len(v) > 12
               for v in CIFRAS_DE_OFICIO.values())


# ══ CERO CIFRAS NO ES UN APROBADO ════════════════════════════════════════════

def test_un_texto_sin_cifras_lo_declara_en_vez_de_pasar_callando():
    """Es la guarda que pasa porque no tiene nada que verificar."""
    v = verificar_texto_generado("¿Con qué lender estás cerrando hoy?", INSUMOS)
    assert v.ok
    assert v.guardas["cifras"]["comprobadas"] == 0
    assert "no comprobó nada" in v.guardas["cifras"]["aviso"]


def test_el_veredicto_dice_cuantas_cifras_comprobo():
    v = verificar_texto_generado("Su FHA es 66,7% contra 16%.", INSUMOS)
    assert v.ok
    assert v.guardas["cifras"]["comprobadas"] == 2
    assert "aviso" not in v.guardas["cifras"]


# ══ LAS OTRAS CUATRO GUARDAS ═════════════════════════════════════════════════

def test_lo_que_nunca_se_dice_tumba_el_texto():
    v = verificar_texto_generado("Cámbiate de lender y cerramos antes.",
                                 INSUMOS)
    assert not v.ok
    assert not v.guardas["nunca"]["ok"]


def test_el_vocabulario_tumba_el_texto():
    v = verificar_texto_generado("No tiene para el enganche.", INSUMOS)
    assert not v.ok
    assert not v.guardas["vocabulario"]["ok"]


def test_prometer_material_tumba_el_texto():
    v = verificar_texto_generado("Te mando el desglose de documentación.",
                                 INSUMOS)
    assert not v.ok
    assert not v.guardas["promesas_de_material"]["ok"]


def test_si_el_contraste_no_activa_el_texto_no_puede_afirmar():
    afirmando = ("Armando trabaja con compradores que necesitan préstamos de "
                 "gobierno. Es exactamente el cliente que sabemos cerrar.")
    v = verificar_texto_generado(afirmando, INSUMOS, afirma=False)
    assert not v.ok
    assert "afirma" in v.motivo
    # Y el MISMO texto pasa cuando el contraste sí activa.
    assert verificar_texto_generado(afirmando, INSUMOS, afirma=True).ok


def test_preguntar_pasa_aunque_el_contraste_no_active():
    v = verificar_texto_generado(
        "Lo que vemos apunta a préstamos de gobierno, sobre 3 operaciones. "
        "¿Cuántas cerraste con FHA el año pasado?", INSUMOS, afirma=False)
    assert v.ok, v.motivo


def test_las_seis_guardas_dejan_su_veredicto():
    """Seis desde que las entidades se comprueban además de las cifras."""
    v = verificar_texto_generado("Su FHA es 66,7%.", INSUMOS)
    assert set(v.guardas) == {"nunca", "vocabulario", "promesas_de_material",
                              "folleto", "acto_de_habla", "entidades",
                              "cifras"}


# ══ LAS ENTIDADES · no solo las cifras ══════════════════════════════════════

EXTRACTO = {
    "identidad": {"condado_dominante": "Solano", "estado": "CA"},
    "contraste": {"geografia": "Solano"},
    "perfil_del_comprador": {"donde": "Solano"},
    "qualifier_principal": {
        "municion": "LO bilingue de la casa; materiales en español",
        "angulo": 'A18 "Tu comunidad en su idioma"'},
    "narrativa": "uno y medio de cada diez préstamos son FHA",
    "originadores": [{"nombre": "Chris Ruiz", "empresa": "Everett Financial, Inc."}],
    "lenders_del_agente": ["Everett Financial, Inc.", "Chris Ruiz"],
    "_vocabulario": {
        "condados": ["Solano", "Alameda", "Contra Costa", "Travis"],
        "lenders": ["Everett Financial", "Supreme Lending"],
    },
}


def test_un_condado_que_no_es_el_suyo_se_rechaza():
    from motor.verificar_texto import verificar_entidades

    v = verificar_entidades("En Alameda se cae uno de cada tres.", EXTRACTO)
    assert not v.ok
    assert "Alameda" in v.cifras_sobrantes
    assert "se inventó" in v.motivo


def test_su_propio_condado_pasa():
    from motor.verificar_texto import verificar_entidades

    assert verificar_entidades("En Solano el fallout es alto.", EXTRACTO).ok


def test_un_programa_que_no_esta_en_su_municion_se_rechaza():
    from motor.verificar_texto import verificar_entidades

    v = verificar_entidades("Le conseguimos un DSCR.", EXTRACTO)
    assert not v.ok and "DSCR" in v.cifras_sobrantes


def test_el_programa_que_SI_esta_en_su_mix_pasa():
    from motor.verificar_texto import verificar_entidades

    assert verificar_entidades("Trabajamos FHA con score desde 580.",
                               EXTRACTO).ok


def test_SU_lender_pasa_aunque_el_sufijo_societario_no_coincida():
    """`Everett Financial, Inc.` y `Everett Financial` son la misma casa. Sin
    normalizar, la guarda rechazaba justo el nombre que importa -- el de la
    exclusión dura."""
    from motor.verificar_texto import _normalizar_entidad, verificar_entidades

    assert _normalizar_entidad("Everett Financial, Inc.") == "everett financial"
    assert verificar_entidades("Dos de sus originadores son de Everett "
                               "Financial.", EXTRACTO).ok


def test_un_lender_conocido_que_NO_es_suyo_se_rechaza():
    from motor.verificar_texto import verificar_entidades

    v = verificar_entidades("Trabaja con Supreme Lending.", EXTRACTO)
    assert not v.ok and "Supreme Lending" in v.cifras_sobrantes


def test_el_limite_de_la_guarda_esta_declarado():
    """Un lender que el sistema nunca vio PASA. No hay conjunto cerrado de
    `todos los lenders`, y una guarda que parece completa y no lo es se
    confía. Está escrito en el docstring, y esta prueba lo fija."""
    from motor.verificar_texto import verificar_entidades

    assert verificar_entidades("Trabaja con Rocket Mortgage.", EXTRACTO).ok
    assert "nunca vio" in verificar_entidades.__doc__


def test_sin_vocabulario_la_guarda_lo_DICE_en_vez_de_rechazar():
    """Rechazar sobre un extracto incompleto es un falso positivo, y una
    guarda que para tráfico correcto termina desactivada. Lo que hace es
    declarar que no comprobó nada."""
    v = verificar_texto_generado("En Alameda pasa algo.", {"x": 1})
    assert v.ok
    assert v.guardas["entidades"]["revisadas"] == 0
    assert "no comprobó nada" in v.guardas["entidades"]["aviso"]


def test_las_siglas_cortas_no_dan_falso_positivo():
    """`VA` dentro de `vale`, `HE` dentro de `hecho`: el falso positivo más
    obvio de una lista de siglas."""
    from motor.verificar_texto import verificar_entidades

    assert verificar_entidades("Eso vale la pena y ya está hecho.",
                               EXTRACTO).ok


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
