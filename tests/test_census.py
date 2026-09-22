"""El cliente del Census. Sin red: todo lo que importa es texto y forma.

Las respuestas de abajo son las REALES, capturadas contra api.census.gov el
2026-09-22. Los cuatro casos devuelven HTTP 200 -- ese es el punto entero.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from geo.census import (  # noqa: E402
    VARIABLES,
    CensusRechazo,
    ClaveInvalida,
    clave_del_entorno,
    derivadas,
    interpretar,
    url_enmascarada,
)

CLAVE_BUENA = "06e8227f5acb811ec1fdecb24f058770bb05d797"[:40]
DATOS = '[["NAME","state"],\n["California","06"]]'
MISSING = ('<html style="font-size: 14px;"><head><title>Missing Key</title>'
           '</head><body>error: missing key</body></html>')
INVALID = ('<html style="font-size: 14px;"><head><title>Invalid Key</title>'
           '</head><body>error: invalid key</body></html>')


# ══ LA TRAMPA · los cuatro casos son HTTP 200 ════════════════════════════════

def test_los_datos_buenos_se_parsean():
    assert interpretar(DATOS, 200, {}) == [["NAME", "state"],
                                           ["California", "06"]]


def test_un_rechazo_con_HTTP_200_NO_pasa_por_bueno():
    """Es la trampa entera: el Census rechaza con 200 y el motivo en el cuerpo.

    Un cliente que mire `response.status` da el rechazo por bueno y revienta
    despues al parsear, en otro sitio y con otro mensaje.
    """
    for cuerpo, motivo in ((MISSING, "Missing Key"), (INVALID, "Invalid Key")):
        try:
            interpretar(cuerpo, 200, {"get": "NAME"})
        except CensusRechazo as exc:
            assert motivo in str(exc)
            assert "HTTP 200" in str(exc)
            assert "mirar el codigo de estado no sirve" in str(exc)
        else:
            raise AssertionError("un %s con 200 tiene que fallar" % motivo)


def test_el_mensaje_distingue_falta_de_clave_de_clave_mala():
    """No es lo mismo y el arreglo es distinto: una es configuracion y la otra
    es la clave equivocada."""
    try:
        interpretar(MISSING, 200, {})
    except CensusRechazo as exc:
        assert "no llego ninguna clave" in str(exc)
    try:
        interpretar(INVALID, 200, {})
    except CensusRechazo as exc:
        assert "no es la buena" in str(exc)


def test_un_html_sin_titulo_igual_se_rechaza():
    try:
        interpretar("<html>algo raro</html>", 200, {})
    except CensusRechazo as exc:
        assert "algo raro" in str(exc)
    else:
        raise AssertionError("cualquier cosa que no sea JSON es un rechazo")


# ══ LA CLAVE, COMPROBADA ANTES DE SALIR A LA RED ═════════════════════════════

def test_la_clave_buena_pasa():
    assert clave_del_entorno(CLAVE_BUENA) == CLAVE_BUENA


def test_las_comillas_y_los_espacios_se_quitan():
    """Es la basura tipica de un .env editado a mano."""
    assert clave_del_entorno('"%s"' % CLAVE_BUENA) == CLAVE_BUENA
    assert clave_del_entorno("'%s'" % CLAVE_BUENA) == CLAVE_BUENA
    assert clave_del_entorno("  %s\n" % CLAVE_BUENA) == CLAVE_BUENA


def test_una_clave_de_largo_raro_falla_con_el_largo_a_la_vista():
    """El error tiene que decir CUANTO mide, que es el dato que lo resuelve."""
    try:
        clave_del_entorno(CLAVE_BUENA + "x")
    except ClaveInvalida as exc:
        assert "41 caracteres" in str(exc)
        assert "tienen que ser 40" in str(exc)
    else:
        raise AssertionError("41 caracteres no es una clave del Census")


def test_una_clave_no_hexadecimal_falla():
    try:
        clave_del_entorno("z" * 40)
    except ClaveInvalida:
        pass
    else:
        raise AssertionError("las claves del Census son hexadecimales")


def test_sin_clave_el_mensaje_dice_que_no_hay_plan_B():
    """El limite de ~500 consultas por IP sin clave NO aplica a este endpoint:
    responde `Missing Key`. Medido, no supuesto."""
    try:
        clave_del_entorno("")
    except ClaveInvalida as exc:
        assert "Missing Key" in str(exc)
        assert "no aplica" in str(exc)
    else:
        raise AssertionError("sin clave no hay datos")


# ══ EL LOG NO PUEDE MENTIR SOBRE LO QUE SE MANDO ═════════════════════════════

def test_la_url_enmascarada_tapa_la_clave_pero_no_la_inventa():
    """La primera version del diagnostico reinyectaba `key=` en la URL impresa,
    asi que mostraba una clave en la peticion que NO llevaba ninguna. Un log
    que miente sobre lo que se mando es peor que no tener log.
    """
    con = url_enmascarada({"get": "NAME", "key": CLAVE_BUENA})
    assert CLAVE_BUENA not in con
    assert "06e8" in con and "d797" in con

    sin = url_enmascarada({"get": "NAME"})
    assert "key" not in sin, "no habia clave: no puede aparecer una"


# ══ LOS CENTINELAS DEL ACS NO SON NUMEROS ════════════════════════════════════

def test_el_centinela_negativo_del_ACS_entra_como_ausencia():
    """El ACS usa -666666666 para `no estimable`. Guardarlo como numero mete un
    ingreso medio de menos seiscientos millones y destruye cualquier promedio
    que lo toque, sin que nada falle."""
    from geo.census import _num

    assert _num("-666666666") is None
    assert _num("83411") == 83411.0
    assert _num("") is None
    assert _num(None) is None
    assert _num("0") == 0.0, "cero es un dato, no una ausencia"


# ══ LAS RAZONES, CON SU DENOMINADOR ══════════════════════════════════════════

def test_las_derivadas_llevan_su_base_al_lado():
    v = {"viviendas_en_propiedad": 1552164.0, "viviendas_ocupadas": 3363093.0,
         "habla_espanol_en_casa": 3600076.0, "poblacion_5mas": 9398060.0,
         "espanol_ingles_limitado": 1440726.0,
         "propias_con_hipoteca": 1073905.0}
    d = derivadas(v)
    assert d["tasa_propiedad_pct"] == 46.2
    assert d["base_tenencia"] == 3363093.0
    assert d["espanol_en_casa_pct"] == 38.3
    assert d["base_idioma"] == 9398060.0


def test_el_ingles_limitado_va_sobre_los_hispanohablantes_no_sobre_todos():
    """Son dos preguntas distintas: cuanta gente necesita atencion en español,
    y que parte de los hispanohablantes la necesita."""
    v = {"habla_espanol_en_casa": 3600076.0, "poblacion_5mas": 9398060.0,
         "espanol_ingles_limitado": 1440726.0}
    d = derivadas(v)
    assert d["ingles_limitado_sobre_espanol_pct"] == 40.0
    assert d["base_espanol"] == 3600076.0
    # Sobre la poblacion daria 15,3%, que es otra cosa.
    assert d["ingles_limitado_sobre_espanol_pct"] != 15.3


def test_sin_denominador_la_razon_es_None_y_no_cero():
    d = derivadas({"viviendas_en_propiedad": 100.0, "viviendas_ocupadas": None})
    assert d["tasa_propiedad_pct"] is None
    d = derivadas({"viviendas_en_propiedad": 100.0, "viviendas_ocupadas": 0})
    assert d["tasa_propiedad_pct"] is None, "dividir por cero no da cero"


# ══ LAS VARIABLES ════════════════════════════════════════════════════════════

def test_las_variables_estan_verificadas_contra_el_API():
    """Las 28 se probaron una por una contra Los Angeles County el 2026-09-22,
    y su COBERTURA se midio sobre los 58 condados de California. Si se agrega
    una, se verifica igual antes: existir y traer dato son dos cosas."""
    assert len(VARIABLES) == 28
    assert all(c[0] in "BC" and c.endswith("E") for c in VARIABLES)
    assert "ingreso_medio_hogar" in VARIABLES.values()
    assert "cuenta_propia_pct" not in VARIABLES.values(), (
        "las derivadas no son variables del ACS: se calculan, con su base")


def test_ninguna_variable_es_de_raza_ni_de_origen():
    """ECOA Regulation B. Las de condado describen DONDE opera, no quien es --
    y aun asi, las tablas de raza y ancestria no entran."""
    PROHIBIDAS = ("B02", "B03", "B04", "B05")   # raza, hispanidad, ancestria
    for codigo in VARIABLES:
        assert not codigo.startswith(PROHIBIDAS), codigo


# ══ LOS TRES CONTRASTES NUEVOS ═══════════════════════════════════════════════
#
# Los numeros son los REALES de Los Angeles County, acs5 2022.

LA = {
    "ocupados_civiles": 4869620.0,
    "cp_h_incorporado": 175547.0, "cp_h_no_incorporado": 218196.0,
    "cp_m_incorporado": 100034.0, "cp_m_no_incorporado": 154546.0,
    "con_hipoteca_base": 1073905.0,
    "hipoteca_carga_30_35": 92726.0, "hipoteca_carga_35_40": 67494.0,
    "hipoteca_carga_40_50": 87932.0, "hipoteca_carga_50mas": 210551.0,
    "alquiler_base": 1810929.0, "alquiler_no_calculable": 88953.0,
    "alquiler_carga_30_35": 161490.0, "alquiler_carga_35_40": 120923.0,
    "alquiler_carga_40_50": 176809.0, "alquiler_carga_50mas": 526945.0,
}


def test_la_cuenta_propia_suma_las_CUATRO_lineas_correctas():
    """B24080 es SEX BY CLASS OF WORKER y las de cuenta propia son la 005/010
    y la 015/020. El primer intento tomo 004/005/014/015 y dio 71,2% de cuenta
    propia en Los Angeles.

    Lo que caza ese error no es que el numero parezca raro -- con los indices
    corridos de a uno habria salido plausible-- sino comprobar la suma contra
    su base.
    """
    d = derivadas(LA)
    assert d["cuenta_propia_n"] == 648323.0
    assert d["cuenta_propia_pct"] == 13.3
    assert d["base_ocupados"] == 4869620.0
    assert d["cuenta_propia_pct"] < 25, (
        "mas de un cuarto de cuenta propia en un condado grande son indices "
        "equivocados, no un mercado raro")


def test_la_carga_de_alquiler_descuenta_los_no_calculables():
    """Son hogares sin ingreso declarado: la carga no esta DEFINIDA para
    ellos. Dejarlos en el denominador baja el porcentaje de todos los condados
    por igual, y ese sesgo no se ve en ningun sitio."""
    d = derivadas(LA)
    assert d["base_alquiler_calculable"] == 1810929.0 - 88953.0
    assert d["carga_alquiler_30mas_pct"] == 57.3
    # Con la base sin descontar daria 54,5%: casi tres puntos de diferencia.
    sin_descontar = round(100.0 * 986167.0 / 1810929.0, 1)
    assert sin_descontar == 54.5
    assert d["carga_alquiler_30mas_pct"] != sin_descontar


def test_la_carga_de_hipoteca_va_sobre_los_que_TIENEN_hipoteca():
    d = derivadas(LA)
    assert d["carga_hipoteca_30mas_pct"] == 42.7
    assert d["base_con_hipoteca"] == 1073905.0


def test_si_falta_un_tramo_la_suma_es_None_y_no_un_total_mas_chico():
    """Sumar tres de cuatro tramos da un numero con la misma pinta de total."""
    parcial = dict(LA)
    del parcial["hipoteca_carga_50mas"]
    d = derivadas(parcial)
    assert d["carga_hipoteca_30mas_pct"] is None


# ══ LO QUE NO EXISTE A NIVEL CONDADO SE DICE ═════════════════════════════════

def test_los_multigeneracionales_van_con_su_RESOLUCION_declarada():
    """B11017 devuelve null en los 58 condados de California y valor en el
    estado. No se rellena el condado con el del estado: se guarda el del
    estado DICIENDO que es del estado.

    Correr un contraste a otra escala es distinto de correrlo creyendo que es
    de la escala que se pidio.
    """
    d = derivadas(LA, {"hogares_estado": 13315822.0,
                       "multigeneracionales_estado": 802077.0})
    assert d["multigeneracional_pct"] is None, "a nivel condado NO existe"
    assert d["multigeneracional_pct_estado"] == 6.0
    assert d["multigeneracional_resolucion"] == "estado"


def test_sin_dato_de_estado_no_se_inventa_resolucion():
    d = derivadas(LA)
    assert d["multigeneracional_pct_estado"] is None
    assert d["multigeneracional_resolucion"] is None


# ══ LA COBERTURA, QUE ES LO QUE ATRAPA UNA COLUMNA DE NULOS ══════════════════

def test_la_cobertura_cuenta_sobre_cuantas_filas_hay_dato():
    """Una variable puede existir (HTTP 200, JSON) y venir nula en todas las
    filas. Sin medir cobertura, esa columna entra y el contraste que la use no
    dispara nunca -- sin error."""
    from geo.census import cobertura

    condados = [
        {"variables": {"ingreso_medio_hogar": 80000.0, "hogares": 100.0}},
        {"variables": {"ingreso_medio_hogar": None, "hogares": 200.0}},
        {"variables": {"ingreso_medio_hogar": 90000.0, "hogares": 300.0}},
    ]
    c = cobertura(condados)
    assert c["_total"] == 3
    assert c["ingreso_medio_hogar"] == 2
    assert c["hogares"] == 3
    assert c["poblacion_total"] == 0, "la que no vino en ninguna, en cero"


def test_la_cobertura_sobre_una_lista_vacia_no_miente():
    from geo.census import cobertura

    assert cobertura([]) == {}, (
        "con cero condados no hay cobertura que reportar; devolver 100%% "
        "seria la guarda que pasa porque no tiene nada que verificar")


# ══ EL CONDADO DEL LIBRO ═════════════════════════════════════════════════════

def test_la_columna_del_libro_trae_MAS_que_el_dominante():
    """`Travis 103 · Williamson 14 · Hays 7`. El nombre de la columna promete
    uno y trae tres: tirar los otros dos es perder dato que ya esta."""
    from supabase.poblar_condado_fips import condados_del_texto

    assert condados_del_texto("Travis 103 · Williamson 14 · Hays 7") == [
        ("Travis", 103), ("Williamson", 14), ("Hays", 7)]


def test_el_sin_dato_del_libro_no_es_un_condado():
    from supabase.poblar_condado_fips import condados_del_texto

    assert condados_del_texto("[sin dato MMI]") == []
    assert condados_del_texto(None) == []
    assert condados_del_texto("") == []


def test_un_condado_sin_unidades_igual_entra_con_cero_declarado():
    from supabase.poblar_condado_fips import condados_del_texto

    assert condados_del_texto("Travis") == [("Travis", 0)]


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
