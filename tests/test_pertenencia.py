"""¿El volcado pegado es de la persona que estaba abierta en la ficha?

El caso: la captura e4032178 entro perfecta -- 10 buyer units, ventana 14, TPO
33,3%, 3 originadores, 3 lenders, 4 mercados -- y la pregunta que nadie podia
contestar mirando la pantalla era de quien era.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from captura.pertenencia import comprobar, piezas_del_nombre  # noqa: E402

#: El caso real, tal como quedo en la base.
CRESPO = {"nombre_completo": "ARMANDO CRESPO", "brokerage": "eXp Realty LLC",
          "estado": "FL", "email_principal": "armandoaperales@gmail.com"}
OCHOA = {"nombre_completo": "ARMANDO OCHOA", "estado": "CA",
         "email_principal": "armando@sq-re.com"}
VOLCADO_CRESPO = {"nombre": "Armando Perales Crespo",
                  "emails": ["armandoaperales@gmail.com"]}


def test_el_caso_real_respalda_por_email():
    """El volcado de e4032178 trae el email exacto de la ficha de Crespo."""
    v = comprobar(VOLCADO_CRESPO, CRESPO)
    assert v["veredicto"] == "respalda"
    assert "email" in v["por"]


def test_el_segundo_apellido_no_rompe_el_nombre():
    """`Armando Perales Crespo` en el volcado, `ARMANDO CRESPO` en el libro.

    Exigir igualdad de cadena habria dado `discrepa` sobre una captura
    correcta, y una guarda que grita sobre lo bueno se termina apagando.
    """
    v = comprobar({"nombre": "Armando Perales Crespo"}, CRESPO)
    assert v["veredicto"] == "respalda"
    assert v["piezas_en_comun"] == ["armando", "crespo"]


def test_los_dos_armandos_no_se_confunden():
    """Armando Ochoa (CA) y Armando Crespo (FL) son dos personas.

    Es el caso que hace falta distinguir de verdad: si el volcado de uno se
    pega estando abierto el otro, el diagnostico sale con la produccion ajena.
    """
    v = comprobar(VOLCADO_CRESPO, OCHOA)
    assert v["veredicto"] == "discrepa", v


def test_un_solo_apellido_no_alcanza():
    """MARIA CRESPO y ARMANDO CRESPO son dos realtors de eXp en Florida.

    Con una sola pieza en comun el veredicto tiene que ser `discrepa`: aceptar
    por apellido es aceptar a la familia entera.
    """
    v = comprobar({"nombre": "Maria Crespo"}, CRESPO)
    assert v["veredicto"] == "discrepa", v


def test_sin_nada_que_comparar_dice_no_consta():
    """`no_consta` NO es `respalda`.

    Es la distincion que este proyecto ya pago cinco veces: una comprobacion
    que no tuvo nada que comparar no comprobo nada.
    """
    v = comprobar({}, CRESPO)
    assert v["veredicto"] == "no_consta"
    v = comprobar(VOLCADO_CRESPO, {"nombre_completo": None,
                                   "email_principal": None})
    assert v["veredicto"] == "no_consta"


def test_el_email_manda_sobre_el_nombre():
    """Un realtor puede estar en el libro con otro nombre y el mismo email."""
    v = comprobar({"nombre": "A. P. Crespo Jr",
                   "emails": ["armandoaperales@gmail.com"]}, CRESPO)
    assert v["veredicto"] == "respalda"


def test_el_veredicto_siempre_trae_los_dos_lados():
    """Para poder decidir hay que ver que decia cada uno, no solo el fallo."""
    for perfil, ficha in ((VOLCADO_CRESPO, OCHOA), ({}, CRESPO),
                          (VOLCADO_CRESPO, CRESPO)):
        v = comprobar(perfil, ficha)
        assert "nombre_en_el_volcado" in v and "nombre_en_el_libro" in v
        assert v["por"]


def test_las_piezas_ignoran_tildes_y_ruido():
    assert piezas_del_nombre("José de la Cruz Jr") == {"jose", "cruz"}
    assert piezas_del_nombre(None) == set()


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
