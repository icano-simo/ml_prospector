"""Los 13 casos del manual de minado, pasados por el codigo de verdad.

El verificador de textos no alcanza: comprueba que las cadenas correctas esten
en el manual y que las prohibidas no, pero **no puede ver una contradiccion de
logica**, porque ahi los dos textos existen y cada uno es valido por separado.

Eso ya paso. El manual decia que un match por nombre sin estado «no gasta ni
un credito», y la tabla de casos le asignaba una confianza que solo se puede
conocer DESPUES de comprar la ficha. Las dos frases estaban bien escritas y
eran incompatibles: un agente que siguiera una no gastaba y otro que siguiera
la otra si.

Esta prueba cierra ese hueco: arma una entrada por cada fila de la tabla de
casos, la pasa por `elegir()` y por `confianza_final()` --el codigo real-- y
compara contra lo que el manual promete.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from modelmatch.a_excel import confianza_final  # noqa: E402
from modelmatch.extraer import elegir  # noqa: E402

#: El realtor nuestro, igual en todos los casos salvo lo que cada uno cambie.
NUESTRO = {"nombre": "Maria Perez", "estado_mmi": "TX",
           "emails_mmi": ["maria@ejemplo.com"],
           "telefonos_mmi": ["+15125551234"]}


def _cand(id_, nombre="Maria Perez", estado="TX", email="otro@ejemplo.com",
          volumen=1000):
    return {"id": id_, "fullName": nombre, "state": estado, "email": email,
            "volume": volumen}


def _elige(candidatos, criterio_esperado, id_esperado):
    elegido, criterio, _conf = elegir(candidatos, NUESTRO)
    assert criterio == criterio_esperado, (criterio, criterio_esperado)
    if id_esperado is None:
        assert elegido is None, "no debia elegir a nadie: %s" % criterio
    else:
        assert elegido is not None, "debia elegir a alguien: %s" % criterio
        assert elegido["id"] == id_esperado, (elegido["id"], id_esperado)


# ── las siete filas de la tabla de identificacion ───────────────────────────

def test_email_exacto():
    _elige([_cand("A", email="maria@ejemplo.com"), _cand("B")],
           "email_exacto", "A")


def test_email_en_varios_perfiles_gana_el_de_mas_volumen():
    _elige([_cand("A", email="maria@ejemplo.com", volumen=10),
            _cand("B", email="maria@ejemplo.com", volumen=99)],
           "email_exacto_varios_perfiles", "B")


def test_nombre_y_estado_unico():
    _elige([_cand("A"), _cand("B", nombre="Otra Persona")],
           "nombre_exacto_y_estado", "A")


def test_varios_con_nombre_y_estado_gana_el_de_mas_volumen():
    _elige([_cand("A", volumen=10), _cand("B", volumen=99)],
           "nombre_y_estado_varios", "B")


def test_nombre_exacto_pero_en_otro_estado():
    _elige([_cand("A", estado="CA")], "nombre_exacto_sin_estado", "A")


def test_ambiguo_no_elige_a_nadie():
    _elige([_cand("A", nombre="Otra Persona", estado="CA")], "ambiguo", None)


def test_sin_candidatos():
    _elige([], "sin_candidatos", None)


# ── la contradiccion que esta prueba existe para no repetir ─────────────────

def test_los_cinco_primeros_compran_ficha():
    """El manual decia que los casos flojos no gastaban. Si gastan, y deben.

    El telefono que devuelve la ficha es lo UNICO que confirma o refuta una
    identificacion hecha por nombre, y la busqueda gratis no trae telefonos.
    """
    casos = [
        ([_cand("A", email="maria@ejemplo.com")], "email_exacto"),
        ([_cand("A", email="maria@ejemplo.com", volumen=1),
          _cand("B", email="maria@ejemplo.com", volumen=2)],
         "email_exacto_varios_perfiles"),
        ([_cand("A")], "nombre_exacto_y_estado"),
        ([_cand("A", volumen=1), _cand("B", volumen=2)],
         "nombre_y_estado_varios"),
        ([_cand("A", estado="CA")], "nombre_exacto_sin_estado"),
    ]
    for candidatos, criterio in casos:
        elegido, visto, _ = elegir(candidatos, NUESTRO)
        assert visto == criterio, (visto, criterio)
        assert elegido is not None, (
            "%s tiene que elegir candidato: sin ficha no hay telefono con que "
            "confirmarlo" % criterio)


def test_los_dos_ultimos_no_gastan():
    for candidatos, criterio in (
            ([_cand("A", nombre="Otra", estado="CA")], "ambiguo"),
            ([], "sin_candidatos")):
        elegido, visto, _ = elegir(candidatos, NUESTRO)
        assert visto == criterio, (visto, criterio)
        assert elegido is None, "%s no debe gastar un credito" % criterio


# ── las trece combinaciones de criterio x telefono ──────────────────────────

#: (criterio, confianza del paso 1, telefono_coincide, Confianza final)
TABLA = [
    ("email_exacto", "alta", "si", "alta"),
    ("email_exacto", "alta", "no", "alta"),
    ("email_exacto", "alta", "sin_dato", "alta"),
    ("email_exacto_varios_perfiles", "alta", "sin_dato", "alta"),
    ("nombre_exacto_y_estado", "media", "si",
     "alta · confirmada por teléfono"),
    ("nombre_exacto_y_estado", "media", "sin_dato", "media"),
    ("nombre_exacto_y_estado", "media", "no", "contradicha por el teléfono"),
    ("nombre_y_estado_varios", "baja", "si",
     "alta · confirmada por teléfono"),
    ("nombre_y_estado_varios", "baja", "sin_dato", "baja"),
    ("nombre_y_estado_varios", "baja", "no", "contradicha por el teléfono"),
    ("nombre_exacto_sin_estado", "baja", "si",
     "alta · confirmada por teléfono"),
    ("nombre_exacto_sin_estado", "baja", "sin_dato", "baja"),
    ("nombre_exacto_sin_estado", "baja", "no",
     "contradicha por el teléfono"),
]


def test_cada_combinacion_de_confianza():
    for criterio, conf1, tel, esperada in TABLA:
        fila = {"encontrado": True, "match_criterio": criterio,
                "match_confianza": conf1, "telefono_coincide": tel}
        visto = confianza_final(fila)
        assert visto == esperada, (criterio, tel, visto, esperada)


def test_no_encontrado_dice_no_encontrado():
    visto = confianza_final({"encontrado": False,
                             "match_criterio": "ambiguo",
                             "match_confianza": "ninguna"})
    assert visto == "no encontrado", visto


def test_un_correo_que_coincide_no_lo_tumba_un_telefono_distinto():
    """La regla que mas realtors mueve: 189 filas dependen de ella."""
    fila = {"encontrado": True, "match_criterio": "email_exacto",
            "match_confianza": "alta", "telefono_coincide": "no"}
    assert confianza_final(fila) == "alta"


def test_ninguna_nunca_llega_a_la_columna():
    """`ninguna` es un valor intermedio: la columna no lo muestra jamas."""
    salidas = {confianza_final(
        {"encontrado": True, "match_criterio": c, "match_confianza": c1,
         "telefono_coincide": t}) for c, c1, t, _ in TABLA}
    salidas.add(confianza_final({"encontrado": False,
                                 "match_criterio": "ambiguo",
                                 "match_confianza": "ninguna"}))
    assert "ninguna" not in salidas, salidas
