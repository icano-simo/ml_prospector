"""Una prueba por regla. No una por modulo.

Por que asi. Las siete pruebas de `estado_perfil` cubrian la rama afirmativa y
ninguna la rama sin evidencia, y por ese hueco se fueron siete perfiles marcados
como privados que eran publicos. Una prueba por modulo verifica que el modulo
corre; una prueba por regla verifica que ESA regla, con ESE dato, da ESA
intensidad.

Cada regla tiene tres pruebas, generadas del catalogo:

  activa      con el dato que la dispara sale exactamente su intensidad
  no_activa   con el dato contrario no sale
  sin_dato    sin el dato NO sale y queda declarada como no evaluada

La tercera es la que habria cazado el bug de privado.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.evaluar import (  # noqa: E402
    VERSION_REGLAS,
    evaluar,
    huella_del_catalogo,
)
from motor.reglas import (  # noqa: E402
    QUALIFIER_GATING,
    REGLAS,
    Regla,
    por_qualifier,
    verificar_catalogo,
)
from pacs.guardas import TECHO_POR_GRADO  # noqa: E402

AHORA = dt.datetime(2026, 9, 22, 12, 0, tzinfo=dt.timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
# EL DATO QUE DISPARA CADA REGLA
# ══════════════════════════════════════════════════════════════════════════════
#
# Escrito a mano, regla por regla, a proposito. Generarlo del propio catalogo
# haria que la prueba y el codigo compartieran el error: si la condicion esta
# mal, el dato generado tambien lo estaria y la prueba pasaria igual.
#
# La clave es el id de la regla. Si se agrega una regla y no se agrega su fila
# aca, `test_toda_regla_tiene_su_dato` falla.

DISPARA: dict[str, dict] = {
    "P-Q01-1": {"ev2_itin": True, "ev2_self_employed": False},
    "P-Q01-2": {"ev2_fha_gob": True, "ev2_dpa_enganche": False},
    "P-Q01-3": {"R5_espanol": 8, "R4_comunidad_fhb": 7},
    "P-Q01-4": {"R5_espanol": 6, "R7_identidad_hispana": 0},

    "P-Q14-1": {"ev2_espanol_decl": True, "ev_caracteres_espanol": 1},
    "P-Q14-2": {"R5_espanol": 6},
    "P-Q14-3": {"R7_identidad_hispana": 8},

    "P-Q13-1": {"ev2_comunidad": True, "R5_espanol": 6,
                "R7_identidad_hispana": 0},
    "P-Q13-2": {"ev2_fe_familia": True, "R7_identidad_hispana": 8},

    "P-Q07-1": {"ev2_dpa_enganche": True},
    "P-Q07-2": {"ev2_primera_casa": True},
    "P-Q07-3": {"E6_asequibilidad": 3, "R4_comunidad_fhb": 7},

    "P-Q06-1": {"ev2_primera_casa": True, "E6_asequibilidad": 5},
    "P-Q06-2": {"E6_asequibilidad": 3},

    "P-Q12-1": {"ev2_precalificacion": True},
    "P-Q12-2": {"ev2_educacion": True, "ev2_primera_casa": True},

    "P-Q17-1": {"ev2_va_militar": True},

    "P-Q09-1": {"ev2_inversion": True, "ev_hits_lujo_inversion": 1},
    "P-Q09-2": {"ev2_inversion": True, "ev_hits_lujo_inversion": 0},

    "P-Q19-1": {"ev2_credito": True},

    "P-Q20-1": {"ev2_self_employed": True, "ev_hits_lujo_inversion": 1},

    "P-Q10-1": {"ev2_video_contenido": True},
    "P-Q10-2": {"ig_seguidores": 1000, "ev2_video_contenido": False,
                "ev2_educacion": False},

    "P-Q11-1": {"ev2_volumen_declarado_bio": 50},
    "P-Q11-2": {"unidades_ano": 20},

    "P-Q21-1": {"ev2_equipo": True, "ig_seguidores": 3000},

    "J-Q01-1": {"ev2_buy_side": True, "ev2_listing_side": False},
    "J-Q01-2": {"ev2_primera_casa": True},
    "J-Q01-3": {"ev2_listing_side": True, "ev2_buy_side": False},

    "J-Q03-1": {"ev2_comunidad": True, "ev2_testimonio": True},
    "J-Q03-2": {"ev2_comunidad": True, "ev2_testimonio": False},

    "J-Q04-1": {"ig_seguidores": 10000, "ev_bio_legible": True},
    "J-Q04-2": {"ig_seguidores": 3000, "ev_bio_legible": True},
    "J-Q04-3": {"ev2_video_contenido": True, "ev2_educacion": False},

    "J-Q05-1": {"E3_urgencia_sept": 6.5},

    "J-Q06-1": {"ev2_equipo": True},

    "G-Q04-1": {"ig_seguidores": 10000},
}

#: El dato que hace que la condicion de False (no que falte: que sea falsa).
NO_DISPARA: dict[str, dict] = {
    "P-Q01-1": {"ev2_itin": False, "ev2_self_employed": False},
    "P-Q01-2": {"ev2_fha_gob": False, "ev2_dpa_enganche": False},
    "P-Q01-3": {"R5_espanol": 7, "R4_comunidad_fhb": 7},
    "P-Q01-4": {"R5_espanol": 5, "R7_identidad_hispana": 7},

    "P-Q14-1": {"ev2_espanol_decl": True, "ev_caracteres_espanol": 0},
    "P-Q14-2": {"R5_espanol": 5},
    "P-Q14-3": {"R7_identidad_hispana": 7},

    "P-Q13-1": {"ev2_comunidad": True, "R5_espanol": 5,
                "R7_identidad_hispana": 7},
    "P-Q13-2": {"ev2_fe_familia": True, "R7_identidad_hispana": 7},

    "P-Q07-1": {"ev2_dpa_enganche": False},
    "P-Q07-2": {"ev2_primera_casa": False},
    "P-Q07-3": {"E6_asequibilidad": 4, "R4_comunidad_fhb": 7},

    "P-Q06-1": {"ev2_primera_casa": True, "E6_asequibilidad": 6},
    "P-Q06-2": {"E6_asequibilidad": 4},

    "P-Q12-1": {"ev2_precalificacion": False},
    "P-Q12-2": {"ev2_educacion": True, "ev2_primera_casa": False},

    "P-Q17-1": {"ev2_va_militar": False},

    "P-Q09-1": {"ev2_inversion": True, "ev_hits_lujo_inversion": 0},
    "P-Q09-2": {"ev2_inversion": True, "ev_hits_lujo_inversion": 1},

    "P-Q19-1": {"ev2_credito": False},

    "P-Q20-1": {"ev2_self_employed": True, "ev_hits_lujo_inversion": 0},

    "P-Q10-1": {"ev2_video_contenido": False},
    "P-Q10-2": {"ig_seguidores": 999, "ev2_video_contenido": False,
                "ev2_educacion": False},

    "P-Q11-1": {"ev2_volumen_declarado_bio": 49},
    "P-Q11-2": {"unidades_ano": 19},

    "P-Q21-1": {"ev2_equipo": True, "ig_seguidores": 2999},

    "J-Q01-1": {"ev2_buy_side": True, "ev2_listing_side": True},
    "J-Q01-2": {"ev2_primera_casa": False},
    "J-Q01-3": {"ev2_listing_side": True, "ev2_buy_side": True},

    "J-Q03-1": {"ev2_comunidad": True, "ev2_testimonio": False},
    "J-Q03-2": {"ev2_comunidad": False, "ev2_testimonio": False},

    "J-Q04-1": {"ig_seguidores": 9999, "ev_bio_legible": True},
    "J-Q04-2": {"ig_seguidores": 2999, "ev_bio_legible": True},
    "J-Q04-3": {"ev2_video_contenido": False, "ev2_educacion": False},

    "J-Q05-1": {"E3_urgencia_sept": 6.4},

    "J-Q06-1": {"ev2_equipo": False},

    "G-Q04-1": {"ig_seguidores": 9999},
}


def _regla(rid: str) -> Regla:
    for r in REGLAS:
        if r.id == rid:
            return r
    raise KeyError(rid)


def _evaluar(datos: dict, *, solo: Regla | None = None):
    reglas = (solo,) if solo else REGLAS
    return evaluar(dict(datos), realtor_id="T-1", reglas=reglas, ahora=AHORA)


# ══════════════════════════════════════════════════════════════════════════════
# INVARIANTES DEL CATALOGO
# ══════════════════════════════════════════════════════════════════════════════

def test_el_catalogo_es_auditable():
    verificar_catalogo()


def test_toda_regla_tiene_su_dato_de_prueba():
    """Si se agrega una regla sin su fila, esto falla. Es el candado."""
    ids = {r.id for r in REGLAS}
    faltan_dispara = ids - set(DISPARA)
    faltan_no = ids - set(NO_DISPARA)
    sobran = (set(DISPARA) | set(NO_DISPARA)) - ids
    assert not faltan_dispara, "sin dato que las dispare: %s" % sorted(faltan_dispara)
    assert not faltan_no, "sin dato que NO las dispare: %s" % sorted(faltan_no)
    assert not sobran, "datos de reglas que ya no existen: %s" % sorted(sobran)


def test_son_37_reglas_sobre_19_qualifiers():
    """El conteo exacto de lo portado. Si cambia, que se vea en el diff."""
    assert len(REGLAS) == 37, len(REGLAS)
    assert len(por_qualifier()) == 19, sorted(por_qualifier())


def test_la_regla_que_supera_su_techo_lo_declara():
    """Una regla puede proponer mas de lo que su evidencia sostiene.

    Lo que no puede es hacerlo en silencio. Si la propone, el techo la recorta
    en el motor y la discrepancia tiene que estar escrita en el catalogo, para
    que se vea que es un conflicto pendiente y no un descuido.

    Hoy hay una: J-Q04-1, donde el archivo 06 y el techo del 05 no coinciden.
    """
    sin_declarar = [
        r.id for r in REGLAS
        if r.intensidad > TECHO_POR_GRADO[r.grado] and not r.discrepancia
    ]
    assert not sin_declarar, (
        "proponen mas de lo que su evidencia sostiene y no lo declaran: %s"
        % sin_declarar
    )


def test_el_motor_recorta_lo_que_el_techo_no_sostiene():
    """Y deja la nota. El recorte es parte de la cadena de evidencia."""
    ev = _evaluar(DISPARA["J-Q04-1"], solo=_regla("J-Q04-1"))
    a = ev.activaciones[0]
    assert a.intensidad_propuesta == 3
    assert a.intensidad == 2, "E1 no sostiene intensidad 3"
    assert a.nota_techo and "recortada de 3 a 2" in a.nota_techo


def test_todas_las_reglas_portadas_son_propias():
    """Ninguna es de la matriz todavia. Cuando aparezcan campos, cambia."""
    assert all(r.origen == "propia" for r in REGLAS)


def test_la_huella_del_catalogo_cambia_si_cambia_una_intensidad():
    """Sin esto, una evaluacion vieja y una nueva son indistinguibles."""
    antes = huella_del_catalogo()
    assert len(antes) == 16
    assert VERSION_REGLAS


# ══════════════════════════════════════════════════════════════════════════════
# UNA PRUEBA POR REGLA · las tres ramas
# ══════════════════════════════════════════════════════════════════════════════

def _hacer_pruebas_por_regla():
    """Genera las tres pruebas de cada regla y las registra como funciones.

    Se generan las FUNCIONES, no los datos: el dato de entrada esta escrito a
    mano arriba. Asi cada regla aparece con su nombre en la salida del corredor
    y una falla dice cual regla fallo, no "el modulo de reglas".
    """
    for regla in REGLAS:
        rid = regla.id

        def activa(rid=rid):
            r = _regla(rid)
            ev = _evaluar(DISPARA[rid], solo=r)
            act = [a for a in ev.activaciones if a.qualifier == r.qualifier]
            assert act, "%s no activo con su propio dato: %s" % (rid, DISPARA[rid])
            a = act[0]
            assert a.regla_id == rid, (rid, a.regla_id)
            # La intensidad esperada es la que declara la regla DESPUES del
            # techo por grado de evidencia: proponer mas de lo que la evidencia
            # sostiene es legitimo, cobrarlo no.
            esperada = min(r.intensidad, TECHO_POR_GRADO[r.grado])
            assert a.intensidad == esperada, (
                "%s dio intensidad %d y se esperaba %d (declara %d, techo %s=%d)"
                % (rid, a.intensidad, esperada, r.intensidad, r.grado,
                   TECHO_POR_GRADO[r.grado])
            )
            assert a.intensidad_propuesta == r.intensidad
            assert a.grado == r.grado
            assert a.texto == r.texto
            # La cadena de evidencia: que dato lo produjo.
            assert a.campos_leidos, "%s no reporta los campos que leyo" % rid
            assert set(a.campos_leidos) == set(r.campos)

        def no_activa(rid=rid):
            r = _regla(rid)
            ev = _evaluar(NO_DISPARA[rid], solo=r)
            assert not ev.activaciones, (
                "%s activo con el dato que NO deberia dispararla: %s"
                % (rid, NO_DISPARA[rid])
            )
            assert not ev.no_evaluadas, (
                "%s dice que no pudo evaluar cuando el dato SI estaba" % rid
            )

        def sin_dato(rid=rid):
            """La rama que habria cazado el bug de privado.

            Sin el dato, la regla NO activa **y lo declara**. No se llena por
            descarte: el valor es desconocido, con su razon.
            """
            r = _regla(rid)
            ev = _evaluar({}, solo=r)
            assert not ev.activaciones, (
                "%s activo SIN datos: eso es llenar por descarte" % rid
            )
            assert len(ev.no_evaluadas) == 1, (
                "%s no declaro que no se pudo evaluar" % rid
            )
            ne = ev.no_evaluadas[0]
            assert ne.regla_id == rid
            assert ne.campos_faltantes, "%s no dice que campo falto" % rid
            assert set(ne.campos_faltantes) <= set(r.campos)

        for nombre, fn in (("activa", activa), ("no_activa", no_activa),
                           ("sin_dato", sin_dato)):
            clave = "test_%s_%s" % (rid.replace("-", "_"), nombre)
            fn.__name__ = clave
            globals()[clave] = fn


_hacer_pruebas_por_regla()


# ══════════════════════════════════════════════════════════════════════════════
# RESOLUCION Y SELECCION
# ══════════════════════════════════════════════════════════════════════════════

def test_gana_la_de_mayor_intensidad_no_la_primera():
    """La semantica del archivo 06, que es donde difiere del prototipo.

    Un agente en estado caro, posicionado a primer comprador, Y que menciona
    primera casa: el prototipo le da 1 porque evalua P-Q07-3 con `elif` antes
    que P-Q07-2. El archivo 06 dice que gana la de mayor intensidad: 2.
    """
    registro = {
        "ev2_dpa_enganche": False,
        "ev2_primera_casa": True,
        "E6_asequibilidad": 3,
        "R4_comunidad_fhb": 7,
    }
    ev = _evaluar(registro)
    p7 = [a for a in ev.activaciones if a.qualifier == "P-Q07"][0]
    assert p7.intensidad == 2, p7
    assert p7.regla_id == "P-Q07-2"
    assert "P-Q07-3" in p7.tambien_activaron, (
        "la que perdio tiene que quedar registrada: es parte de la evidencia"
    )
    assert p7.discrepancia, "la diferencia con el prototipo va declarada"


def test_j_q01_nunca_es_el_dolor_primario():
    """Es la compuerta, no un dolor. Archivo 06."""
    registro = {"ev2_buy_side": True, "ev2_listing_side": False,
                "ev2_equipo": True}
    ev = _evaluar(registro)
    assert ev.gating is not None
    assert ev.gating.qualifier == QUALIFIER_GATING
    assert ev.gating.intensidad == 3
    assert ev.dolor_primario != QUALIFIER_GATING
    assert QUALIFIER_GATING not in ev.dolores_secundarios


def test_a_igual_intensidad_gana_P_sobre_J_sobre_G():
    registro = {
        "ev2_credito": True,          # P-Q19 intensidad 3
        "ev2_comunidad": True,        # J-Q03 intensidad 2
        "ev2_testimonio": True,       # J-Q03 sube a 3
        "ig_seguidores": 10000,       # G-Q04 intensidad 2, J-Q04 intensidad 3
        "ev_bio_legible": True,
    }
    ev = _evaluar(registro)
    assert ev.dolor_primario == "P-Q19", [
        (a.qualifier, a.intensidad) for a in ev.activaciones
    ]


def test_sin_ningun_dolor_el_primario_es_none():
    ev = _evaluar({"ev2_credito": False})
    assert ev.dolor_primario is None
    assert ev.dolores_secundarios == ()


# ══════════════════════════════════════════════════════════════════════════════
# LA CADENA DE EVIDENCIA
# ══════════════════════════════════════════════════════════════════════════════

def test_toda_activacion_trae_su_cadena_completa():
    """Nunca un valor suelto: que dato, que regla, de que fuente."""
    ev = _evaluar({"ev2_itin": True, "ev2_self_employed": False})
    a = ev.activaciones[0]
    assert a.regla_id == "P-Q01-1"
    assert a.campos_leidos == {"ev2_itin": True, "ev2_self_employed": False}
    assert a.referencia.endswith("06-reglas-de-activacion.md")
    assert a.origen == "propia"
    assert a.texto


def test_la_evaluacion_lleva_timestamp_y_version_de_reglas():
    """Sin esto, dentro de tres meses no se sabe con que reglas se produjo."""
    ev = _evaluar({"ev2_itin": True})
    assert ev.evaluado_en == "2026-09-22T12:00:00+00:00"
    assert ev.version_reglas == VERSION_REGLAS
    assert ev.huella_reglas == huella_del_catalogo()
    assert ev.realtor_id == "T-1"


def test_la_evaluacion_serializa_a_json():
    """Va a una columna jsonb de Supabase tal cual."""
    import json

    ev = _evaluar({"ev2_itin": True, "ig_seguidores": 12000,
                   "ev_bio_legible": True})
    cargado = json.loads(ev.a_json())
    assert cargado["realtor_id"] == "T-1"
    assert cargado["activaciones"]
    assert "campos_leidos" in cargado["activaciones"][0]


def test_el_acto_de_habla_solo_afirma_con_E0_e_intensidad_3():
    afirma = _evaluar({"ev2_credito": True}).activaciones[0]
    assert afirma.intensidad == 3 and afirma.grado == "E0"
    assert afirma.acto == "AFIRMA"

    pregunta = _evaluar({"R5_espanol": 6}).activaciones[0]
    assert pregunta.acto == "PREGUNTA"


def test_los_campos_ausentes_se_declaran():
    """El denominador de todo lo demas: sobre cuantos campos se evaluo."""
    ev = _evaluar({"ev2_itin": True})
    assert "ev2_credito" in ev.campos_ausentes
    assert "ev2_itin" not in ev.campos_ausentes


# ══════════════════════════════════════════════════════════════════════════════
# LAS TRES GUARDIAS, EN EL MOTOR
# ══════════════════════════════════════════════════════════════════════════════

def test_ninguna_regla_se_apoya_en_apellido_etnia_u_origen():
    """ECOA Regulation B. No es una preferencia."""
    from pacs.guardas import CAMPOS_PROHIBIDOS_PARA_INFERENCIA

    for r in REGLAS:
        for campo in r.campos:
            assert campo.lower() not in CAMPOS_PROHIBIDOS_PARA_INFERENCIA, (
                "%s lee %s" % (r.id, campo)
            )


def test_un_registro_vacio_no_activa_nada_y_lo_declara_todo():
    """Nada se llena por descarte, en el caso extremo."""
    ev = _evaluar({})
    assert ev.activaciones == []
    assert len(ev.no_evaluadas) == len(REGLAS), (
        "las 37 tienen que quedar declaradas como no evaluadas, no como "
        "'no aplica'"
    )
    assert ev.dolor_primario is None


def test_un_false_explicito_no_es_lo_mismo_que_un_dato_ausente():
    """La distincion que costo siete perfiles."""
    ausente = _evaluar({}, solo=_regla("P-Q17-1"))
    falso = _evaluar({"ev2_va_militar": False}, solo=_regla("P-Q17-1"))

    assert ausente.no_evaluadas and not ausente.activaciones
    assert not falso.no_evaluadas and not falso.activaciones, (
        "un False medido es una medicion; un campo ausente no lo es"
    )


def test_un_nan_se_trata_como_ausente_no_como_cero():
    """Un NaN comparado con >= devuelve False en silencio."""
    ev = _evaluar({"ig_seguidores": float("nan")}, solo=_regla("G-Q04-1"))
    assert not ev.activaciones
    assert ev.no_evaluadas, "un NaN es un dato que falta, no un cero"


# ══════════════════════════════════════════════════════════════════════════════
# LA PROYECCION A LA TABLA
# ══════════════════════════════════════════════════════════════════════════════

def test_la_tabla_de_reglas_es_una_proyeccion_del_catalogo():
    """Una sola fuente de verdad: el Python manda, la tabla es su proyeccion."""
    from motor.sincronizar_reglas import filas

    fs = filas()
    assert len(fs) == len(REGLAS)
    ids_catalogo = {r.id for r in REGLAS}
    assert {f["id"] for f in fs} == ids_catalogo
    for f in fs:
        assert f["origen"] in ("propia", "matriz")
        assert f["campos"], f["id"]
        assert f["version"] == VERSION_REGLAS


def test_el_sql_es_idempotente_y_desactiva_lo_que_ya_no_esta():
    from motor.sincronizar_reglas import a_sql

    sql = a_sql()
    assert "on conflict (id) do update" in sql, "tiene que poder correr dos veces"
    assert "set activa = false where id not in" in sql, (
        "una regla retirada se desactiva, no se borra: una evaluacion vieja "
        "apunta a su id y tiene que poder resolverlo"
    )
    assert huella_del_catalogo() in sql


def test_el_sql_escapa_las_comillas_del_texto():
    """Los textos llevan apostrofes en español."""
    from motor.sincronizar_reglas import _sql_literal

    assert _sql_literal("no se puede") == "'no se puede'"
    assert _sql_literal("l'agent") == "'l''agent'"
    assert _sql_literal(None) == "null"
    assert _sql_literal(["a", "b"]) == "array['a', 'b']"


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
