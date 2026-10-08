"""Las bandas y el verificador del manual, probados contra lo que falla.

Dos cosas se comprueban aca, y las dos por un fallo que ya ocurrio:

  · las ETIQUETAS de las bandas. El manual listaba «1 · 2 · 3 · 4 · 5-9»
    cuando el codigo agrupa 3 y 4 en una sola celda. Un numero de operaciones
    con Everett mal leido decide una exclusion, asi que la etiqueta se prueba,
    no se mira;

  · que el verificador del manual CACE. La leccion de la revision 4 fue que un
    verificador que solo comprueba presencia da falsa seguridad: paso en verde
    durante una version entera mientras el manual explicaba columnas
    retiradas. Asi que cada chequeo nuevo se corre contra un manual roto a
    proposito, y si el roto pasa, la prueba falla.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from modelmatch import verificar_manual as vm  # noqa: E402
from modelmatch.anios_buyside import BANDAS as B_ANIOS  # noqa: E402
from modelmatch.anios_buyside import etiqueta as etq_anios  # noqa: E402
from modelmatch.everett_bandas import BANDAS as B_EVERETT  # noqa: E402
from modelmatch.everett_bandas import etiqueta as etq_everett  # noqa: E402

#: Lo que el manual promete que se escribe en la celda, banda por banda.
ETIQUETAS_EVERETT = [1, 2, "3-4", "5-9", "10-19", "20-49", 50]
ETIQUETAS_ANIOS = [1, 2, 3, 4, "5-6", "7-9", "10-14", "15-19", "20-29",
                   "30-49", "50-99", "100+"]


def test_etiquetas_de_everett():
    visto = [etq_everett(g, l) for g, l in B_EVERETT]
    assert visto == ETIQUETAS_EVERETT, visto


def test_etiquetas_de_historical_units():
    visto = [etq_anios(g, l) for g, l in B_ANIOS]
    assert visto == ETIQUETAS_ANIOS, visto


def test_las_bandas_no_se_pisan_ni_dejan_huecos():
    """Excluyentes y contiguas: por eso «la primera que da 1» es correcta."""
    for bandas in (B_EVERETT, B_ANIOS):
        for (_g1, lt), (gte, _l2) in zip(bandas, bandas[1:]):
            assert lt == gte, (lt, gte)
        assert bandas[0][0] == 1, bandas[0]
        assert bandas[-1][1] is None, bandas[-1]


def _verificador_sobre(texto, tmp):
    """Corre el verificador contra un manual dado. Devuelve sus fallos."""
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(texto)
    original, vm.MANUAL = vm.MANUAL, tmp
    salida = io.StringIO()
    try:
        with contextlib.redirect_stdout(salida):
            vm.main()
        return []
    except SystemExit:
        return [l.strip() for l in salida.getvalue().splitlines()
                if l.startswith("   · ")]
    finally:
        vm.MANUAL = original
        if os.path.exists(tmp):
            os.remove(tmp)


#: (que se rompe, patron a reemplazar, con que). Cada una tiene que ser cazada.
ROTURAS = [
    ("el tope: el manual autoriza el doble de lo que el codigo permite",
     "TOPE_POR_REALTOR = 1", "TOPE_POR_REALTOR = 2"),
    ("los ids de Everett: se cae el del typo de la fuente",
     "dba_evertt_financial_lending_supreme\n", ""),
    ("las bandas: 3 y 4 separadas, como estaba mal",
     "| 3 | 5 | `3-4` |", "| 3 | 4 | `3` |\n| 4 | 5 | `4` |"),
    ("una etiqueta cambiada a mano",
     "| 5 | 7 | `5-6` |", "| 5 | 7 | `5-7` |"),
]


def test_el_manual_real_pasa():
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "_manual_ok.md")
    bueno = open(vm.MANUAL, encoding="utf-8").read()
    assert _verificador_sobre(bueno, tmp) == []


def test_el_verificador_caza_cada_rotura():
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "_manual_roto.md")
    bueno = open(vm.MANUAL, encoding="utf-8").read()
    for nombre, viejo, nuevo in ROTURAS:
        assert viejo in bueno, "no se pudo romper %s: el patron no esta" % nombre
        fallos = _verificador_sobre(bueno.replace(viejo, nuevo, 1), tmp)
        assert fallos, "paso en verde con el manual roto: %s" % nombre
