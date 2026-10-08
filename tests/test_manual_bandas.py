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
#: La ultima lleva el `+`: un `50` pelado afirma cincuenta exactas, que es lo
#: unico que esa llamada --sin cota superior-- no puede saber.
ETIQUETAS_EVERETT = [1, 2, "3-4", "5-9", "10-19", "20-49", "50+"]
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
    ("una columna de Instagram que el manual deja de congelar",
     "\nIG · handle confianza\n", "\n"),
    ("la fila de la banda sin tope vuelve a decir `50`",
     "| 50 | — | `50+` |", "| 50 | — | `50` |"),
]


def test_un_periodo_pendiente_vacia_la_antiguedad():
    """Si falta un periodo NO se puede saber cual fue el primer año.

    Omitir solo el periodo que fallo no alcanza: en la celda, un periodo
    ausente se ve igual que uno sin produccion, asi que si el que fallo fue el
    mas viejo, `Primer año` avanza y la antiguedad sale un año MENOR. El
    hueco se vuelve una afirmacion falsa.
    """
    from modelmatch.a_excel import preparar

    completo = {"encontrado": True, "mm_id": "x",
                "anios_buyside": {"2019": 3, "2020": 5, "2021": ""},
                "anios_buyside_en": "2026-10-08T00:00:00+00:00"}
    d = preparar(completo)
    assert d["primer_anio"] == "2019"
    assert d["anios_produciendo"] == 2
    assert d["antiguedad_aprox"] != ""
    assert d["historical_units_txt"] != ""

    # El mismo realtor, pero 2017 fallo: sin sello, todo vacio.
    pendiente = dict(completo)
    pendiente.pop("anios_buyside_en")
    d = preparar(pendiente)
    for clave in ("primer_anio", "anios_produciendo", "antiguedad_aprox",
                  "historical_units_txt"):
        assert d[clave] == "", (clave, d[clave])
    assert "producción por año" in d["pendientes"]
    assert d["pendientes"].endswith("NO PUNTUAR")


def test_everett_sin_comprobar_sale_marcado_como_pendiente():
    """El riesgo es de scoring: «sin comprobar» se salta el tope de Everett."""
    from modelmatch.a_excel import preparar

    f = {"encontrado": True, "mm_id": "x", "paso4_en": "ya",
         "anios_buyside": {"2020": 1}, "anios_buyside_en": "ya",
         "everett_historico": "sin comprobar", "everett_12m": "no"}
    assert "Everett" in preparar(f)["pendientes"]
    f["everett_historico"] = "no"
    assert preparar(f)["pendientes"] == ""


def test_un_fallo_de_red_no_inventa_una_banda():
    """Lo que un fallo NO puede producir: un numero, ni un «no».

    Si una llamada que falla contara como «no es esta banda», el recorrido
    seguiria y terminaria escribiendo la ultima --50+--, que en el scoring
    dispara el tope T1. Un fallo de red no puede convertirse en una
    afirmacion sobre el realtor.
    """
    from modelmatch import everett_bandas as eb

    llamadas = []

    def falla_en(cual):
        """Un realtor de 5 operaciones: responde la banda [5,10), la cuarta.

        Asi las llamadas 1 a 5 ocurren de verdad y se puede hacer fallar
        cualquiera de ellas, incluida la que iba a dar el numero bueno.
        """
        def fake(mm, periodo, gte=None, lt=None, etq=""):
            llamadas.append((gte, lt))
            if len(llamadas) == cual:
                return None              # el fallo de red
            # La BASE es gte=1 SIN lt; la banda [1,2) es gte=1 CON lt. Se
            # distinguen por eso y no por el gte, que comparten.
            if lt is None:
                return 1                 # la base: si trabajo con Everett
            return 1 if gte == 5 else 0
        return fake

    original = eb.cuenta
    try:
        # sin fallos, el camino bueno da la banda de 5
        eb.cuenta = falla_en(0)
        llamadas.clear()
        assert eb.unidades("x", "allTime") == "5-9"
        # y con un fallo en cualquiera de las cinco, FALLO y nada mas
        for cual in (1, 2, 3, 4, 5):
            llamadas.clear()
            eb.cuenta = falla_en(cual)
            visto = eb.unidades("x", "allTime")
            assert visto is eb.FALLO, "fallo en la llamada %d dio %r" % (
                cual, visto)
    finally:
        eb.cuenta = original


def test_sin_fallos_la_primera_banda_responde():
    """Y el camino bueno sigue dando el numero, no FALLO."""
    from modelmatch import everett_bandas as eb

    original = eb.cuenta
    try:
        eb.cuenta = lambda mm, p, gte=None, lt=None, etq="": 1
        assert eb.unidades("x", "allTime") == 1   # base si, banda [1,2) si
        eb.cuenta = lambda mm, p, gte=None, lt=None, etq="": 0
        assert eb.unidades("x", "allTime") == ""  # la base dice que no
    finally:
        eb.cuenta = original


def test_las_fechas_de_licencia_se_ordenan_por_fecha_y_no_por_texto():
    """`03/31/2027` es texto menor que `09/30/2025` y fecha MAYOR."""
    from modelmatch.rellenar_ficha import fecha_licencia

    crudas = ["03/31/2027", "09/30/2025"]
    convertidas = sorted(fecha_licencia(x) for x in crudas)
    assert convertidas[0] == "2025-09-30", convertidas
    assert sorted(crudas)[0] == "03/31/2027"   # el orden de texto, al reves
    assert fecha_licencia("") == ""
    assert fecha_licencia(None) == ""
    assert fecha_licencia("13/45/2027") == ""


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
