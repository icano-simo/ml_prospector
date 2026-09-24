"""Una evaluacion de otra version de reglas no se presenta como vigente.

`pacs.evaluaciones` es append-only y el catalogo cambia. Hoy las 4.187 filas se
evaluaron con `2026.09.23-vocabulario-de-oficio`, o sea CON R7 -- que era el
apellido-- y el motor actual es `2026.09.23-sin-r7`. Mostrar ese dolor primario
como el dolor de alguien es presentar una conclusion que el motor de hoy no
saca, y que ademas se saco de una señal que ya se decidio no usar.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.evaluar import VERSION_REGLAS  # noqa: E402

AVISO = "Evaluada con reglas anteriores, pendiente de re-evaluar"


def _lectura_falsa(version):
    """Lo que `lectura()` calcula sobre `version_reglas`, sin tocar la red.

    Se reproduce la regla, no se llama a la ruta: la ruta necesita Supabase y
    estas pruebas corren sin red a proposito.
    """
    ev = {"version_reglas": version, "dolor_primario": "P-Q14"}
    reglas_viejas = bool(ev) and (ev.get("version_reglas") != VERSION_REGLAS)
    return {
        "dolor_primario": ev["dolor_primario"] if not reglas_viejas else None,
        "dolor_primario_de_reglas_anteriores": (ev["dolor_primario"]
                                                if reglas_viejas else None),
        "reglas_anteriores": ({"aviso": AVISO,
                               "version_de_la_evaluacion": version,
                               "version_actual": VERSION_REGLAS}
                              if reglas_viejas else None),
    }


def test_con_la_version_de_hoy_el_dolor_es_vigente():
    d = _lectura_falsa(VERSION_REGLAS)
    assert d["dolor_primario"] == "P-Q14"
    assert d["reglas_anteriores"] is None


def test_con_otra_version_el_dolor_NO_sale_como_vigente():
    d = _lectura_falsa("2026.09.23-vocabulario-de-oficio")
    assert d["dolor_primario"] is None
    assert d["reglas_anteriores"]["aviso"] == AVISO


def test_el_dolor_viejo_no_se_esconde_sino_que_se_marca():
    """Esconderlo haria que alguien lo buscara en la base y lo usara sin aviso."""
    d = _lectura_falsa("2026.09.23-vocabulario-de-oficio")
    assert d["dolor_primario_de_reglas_anteriores"] == "P-Q14"


def test_el_aviso_dice_las_dos_versiones():
    """Sin las dos, «pendiente de re-evaluar» no dice pendiente de que."""
    d = _lectura_falsa("2026.09.23-vocabulario-de-oficio")
    ra = d["reglas_anteriores"]
    assert ra["version_de_la_evaluacion"] == "2026.09.23-vocabulario-de-oficio"
    assert ra["version_actual"] == VERSION_REGLAS
    assert ra["version_de_la_evaluacion"] != ra["version_actual"]


def test_la_pantalla_pinta_el_aviso_y_la_marca():
    """Se lee el archivo servido, no solo la ruta: la pantalla ya dijo lo
    contrario que el modulo una vez (`sin dolor primario`)."""
    with open(os.path.join(RAIZ, "public", "index.html"),
              encoding="utf-8") as fh:
        html = fh.read()
    assert "reglas_anteriores" in html
    assert "de reglas anteriores" in html


def test_la_version_actual_no_es_la_de_las_evaluaciones_guardadas():
    """El caso real, fijado: si alguien vuelve a correr el motor esto cambia,
    y entonces esta prueba hay que actualizarla A PROPOSITO."""
    assert VERSION_REGLAS == "2026.09.24-fuente-real"
    assert VERSION_REGLAS != "2026.09.23-vocabulario-de-oficio"
    # Las 4.187 evaluaciones guardadas son de `-compuertas`. Hasta que se
    # vuelva a correr el motor, la pantalla tiene que decir que ese diagnóstico
    # es de una versión anterior -- que es exactamente para lo que existe la
    # comparación, y lo que obliga a correr la re-evaluación antes de mergear.
    assert VERSION_REGLAS != "2026.09.23-compuertas"
    assert VERSION_REGLAS != "2026.09.23-sin-r7"


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
