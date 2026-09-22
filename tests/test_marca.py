"""La guia de diseño, comprobada sobre los archivos servidos.

La regla que sostiene todo: **ningun hex de la guia se escribe a mano fuera de
`tokens.css`**, que esta portado byte a byte de commercial-activity. Si alguien
teclea `#001A40` en el HTML, esta prueba falla -- y falla tambien si alguien
teclea el verde de un badge, que es igual de facil de desincronizar y mucho mas
facil de no notar.
"""
from __future__ import annotations

import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(RAIZ, "public")


def _leer(nombre: str) -> str:
    with open(os.path.join(PUB, nombre), encoding="utf-8") as fh:
        return fh.read()


TOKENS = _leer("tokens.css")
HOMESI = _leer("homesi.css")
HTML = _leer("index.html")

#: Los valores de la guia -> el token que ya los tenia. Cotejado uno por uno
#: contra el archivo portado: 18 de 19 ya existian.
DE_LA_GUIA = {
    "#001a40": "--navy",
    "#ff4040": "--coral",
    "#a6deff": "--sky",
    "#fcfcfa": "--canvas",
    "#ffffff": "--white",
    "#ecfdf5": "--emerald-50", "#047857": "--emerald-700",
    "#a7f3d0": "--emerald-200",
    "#fff1f2": "--rose-50", "#be123c": "--rose-700", "#fecdd3": "--rose-200",
    "#fffbeb": "--amber-50", "#b45309": "--amber-700", "#fde68a": "--amber-200",
    "#f1f5f9": "--slate-100", "#334155": "--slate-700", "#e2e8f0": "--slate-200",
}

#: La UNICA que la guia pide y el archivo portado no tiene. Vive en homesi.css
#: porque `tokens.css` es una copia que se re-baja, no se edita.
EXCEPCION = {"#34d399": "--emerald-400"}


def test_cada_valor_de_la_guia_ya_es_un_token():
    faltan = []
    for hexa, token in DE_LA_GUIA.items():
        if not re.search(re.escape(token) + r":\s*" + re.escape(hexa) + r"\b",
                         TOKENS.lower()):
            faltan.append((hexa, token))
    assert not faltan, (
        "estos valores de la guia no coinciden con su token en el archivo "
        "portado: %s" % faltan)


def test_ningun_hex_de_la_guia_se_escribe_a_mano_fuera_de_tokens():
    """La unica forma de cambiar la paleta es volver a bajar tokens.css."""
    sueltos = []
    for archivo, texto in (("homesi.css", HOMESI), ("index.html", HTML)):
        bajo = texto.lower()
        for hexa in DE_LA_GUIA:
            # En comentarios si puede aparecer: es donde se explica el mapeo.
            sin_comentarios = re.sub(r"/\*.*?\*/|<!--.*?-->", "", bajo,
                                     flags=re.DOTALL)
            if hexa in sin_comentarios:
                sueltos.append((archivo, hexa, DE_LA_GUIA[hexa]))
    assert not sueltos, (
        "escritos a mano en vez de usar su token: %s" % sueltos)


def test_la_excepcion_esta_declarada_y_es_UNA():
    """#34D399 no existe en los tokens portados. Que viva en homesi.css es una
    decision; que nadie sepa que es una excepcion, un accidente."""
    bajo = HOMESI.lower()
    for hexa, token in EXCEPCION.items():
        assert re.search(re.escape(token) + r":\s*" + re.escape(hexa), bajo), (
            "%s tiene que estar definida como %s en homesi.css" % (hexa, token))
        assert hexa not in HTML.lower(), "y usarse por token, no a mano"

    # Y no puede haber MAS hexes propios que ese. Uno nuevo sin declarar es
    # justo como empieza una paleta a divergir.
    sin_comentarios = re.sub(r"/\*.*?\*/", "", bajo, flags=re.DOTALL)
    hexes = set(re.findall(r"#[0-9a-f]{6}\b", sin_comentarios))
    permitidos = set(EXCEPCION) | {"#f9fbfd"}   # el zebra de la columna fija
    assert hexes <= permitidos, (
        "hexes propios sin declarar en homesi.css: %s" % (hexes - permitidos))


def test_las_dos_hojas_se_cargan_y_en_orden():
    """tokens.css ANTES que homesi.css: la segunda usa las variables de la
    primera y redefine --font-inter, que la primera consume."""
    i_tok = HTML.find('href="tokens.css"')
    i_hom = HTML.find('href="homesi.css"')
    assert i_tok > 0 and i_hom > 0
    assert i_tok < i_hom


# ══ LO QUE LA GUIA PIDE, COMPROBADO ══════════════════════════════════════════

def test_los_datos_numericos_van_en_mono_con_tabular_nums():
    """Para que comas y decimales alineen verticalmente entre filas."""
    assert "font-variant-numeric: tabular-nums" in HOMESI
    regla = re.search(r"\.num,([^{]*)\{([^}]*)\}", HOMESI)
    assert regla, "tiene que existir la clase .num"
    cuerpo = regla.group(0)
    assert "var(--font-mono)" in cuerpo
    assert "tabular-nums" in cuerpo
    # Y las celdas de tabla entran en la misma regla: olvidarse de una columna
    # es como se rompe una tabla de cifras.
    assert "table.piv td" in regla.group(1)


def test_las_tarjetas_siguen_la_especificacion():
    for pieza in ("background: var(--white)", "border: 1px solid var(--slate-200)",
                  "border-radius: var(--radius-lg)", "box-shadow: var(--shadow-xs)"):
        assert pieza in HOMESI, pieza
    assert ".tarjeta:hover { border-color: var(--navy) }" in HOMESI


def test_los_encabezados_de_seccion_son_xs_extrabold_mayusculas():
    bloque = re.search(r"\.seccion \{([^}]*)\}", HOMESI).group(1)
    assert "800" in bloque and "11px" in bloque
    assert "uppercase" in bloque
    assert "letter-spacing: .12em" in bloque
    assert "var(--slate-500)" in bloque


def test_los_cuatro_badges_pastel_existen_y_mapean_a_los_niveles():
    """verde MQL · rojo excluido · amarillo bloqueado · gris sin evaluar."""
    for clase, fondo in ((".badge.mql", "--emerald-50"),
                         (".badge.excluido", "--rose-50"),
                         (".badge.bloqueado", "--amber-50"),
                         (".badge.sin-evaluar", "--slate-100")):
        m = re.search(re.escape(clase) + r"[^{]*\{([^}]*)\}", HOMESI)
        assert m, clase
        assert fondo in m.group(1), "%s tiene que usar %s" % (clase, fondo)


def test_el_panel_lateral_sigue_la_especificacion():
    bloque = re.search(r"\.panel \{([^}]*)\}", HOMESI).group(1)
    for pieza in ("position: fixed", "right: 0", "top: 0", "width: 450px",
                  "height: 100%", "background: var(--white)", "z-index: 50",
                  "padding: 24px"):
        assert pieza in bloque, pieza


def test_el_banner_oscuro_lleva_el_borde_coral_abajo():
    bloque = re.search(r"\.banner \{([^}]*)\}", HOMESI).group(1)
    assert "background: var(--navy)" in bloque
    assert "border-bottom: 2px solid var(--coral)" in bloque
    cifra = re.search(r"\.banner \.cifra \{([^}]*)\}", HOMESI).group(1)
    assert "var(--sky)" in cifra


def test_las_tablas_tienen_borde_y_las_listas_tambien():
    """`nada de tablas sin bordes ni listas planas`."""
    scroll = re.search(r"\.tbl-scroll \{([^}]*)\}", HOMESI).group(1)
    assert "border: 1px solid var(--slate-200)" in scroll
    lista = re.search(r"\.lista \{([^}]*)\}", HOMESI).group(1)
    assert "border: 1px solid var(--slate-200)" in lista


def test_se_cargan_las_dos_familias_tipograficas():
    assert "family=Inter" in HTML
    assert "Plus+Jakarta+Sans" in HTML, (
        "el nombre va con + y no con espacios, o Google Fonts no lo sirve")
    # Y homesi.css cumple el contrato que tokens.css espera.
    assert "--font-inter: 'Inter'" in HOMESI
    assert "--font-barlow:" in HOMESI


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
