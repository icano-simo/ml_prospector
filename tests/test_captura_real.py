"""Los tres hallazgos de la primera captura real. Casos anonimizados.

Lote 74889ff6: 6 filas, etiquetas de condado correctas, un condado sin Market
Insight y 5 mercados promovidos. Lo que salió mal no fue el dato: fueron tres
cosas que el sistema decía o dejaba de hacer alrededor de un dato correcto.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from captura.cajas import (  # noqa: E402
    DEL_OVERVIEW,
    SIN_PEGAR,
    cajas_desde,
    marcar_del_overview,
    resumen_de_cajas,
)
from captura.parser_mm import tolerancia_de_redondeo  # noqa: E402
from motor.veredicto import OK, puede_contactarse  # noqa: E402

#: El perfil de la primera captura real, anonimizado: 4 originadores, 14 de 19
#: unidades con originador identificado, ninguno de la casa.
PERFIL_CON_ORIG_EN_EL_OVERVIEW = {
    "buyer_units": 19.0,
    "orig_buyer": [
        {"nombre": "Originador A", "empresa": "Wells Fargo Bank, National A",
         "unidades": 11, "share": 79.0},
        {"nombre": "Originador B", "empresa": "Originpoint Llc",
         "unidades": 1, "share": 7.0},
        {"nombre": "Originador C", "empresa": "Travis Credit Union",
         "unidades": 1, "share": 7.0},
        {"nombre": "Originador D", "empresa": "Hsbc Bank Usa National Assoc",
         "unidades": 1, "share": 7.0},
    ],
    "tab_orig": [],
}


# ══ 1 · EL REPARTO VIENE EN EL OVERVIEW ══════════════════════════════════════

def test_con_orig_buyer_del_overview_el_veredicto_es_ok():
    """`Buyer Side Relationships` vive en el Overview, no en Originators.

    Una captura sin la pestaña Originators puede traer el reparto completo, y
    el veredicto lo lee bien. Lo que estaba mal era el aviso al lado.
    """
    v = puede_contactarse(PERFIL_CON_ORIG_EN_EL_OVERVIEW)
    assert v.estado == OK, v.a_dict()
    assert v.evidencia["unidades_de_la_casa"] == 0
    assert v.evidencia["unidades_totales"] == 14
    assert v.evidencia["originadores_leidos"] == 4


def test_las_compras_sin_originador_identificado_se_cuentan():
    """19 compras y 14 con originador: 5 sin identificar.

    No es un error ni una exclusión: es lo que Model Match no muestra, y tiene
    que decirse para que nadie lea «14» como si fuera el total.
    """
    p = PERFIL_CON_ORIG_EN_EL_OVERVIEW
    con_orig = sum(o["unidades"] for o in p["orig_buyer"])
    assert con_orig == 14
    assert p["buyer_units"] - con_orig == 5


def test_la_caja_de_originators_no_queda_como_falta_capturar():
    """Pedía pegar una sección que ya estaba leída."""
    cajas = cajas_desde({"cajas": [
        {"clave": "orig", "tipo": "originators", "etiqueta": "Originators"},
        {"clave": "lend", "tipo": "lenders", "etiqueta": "Lenders"}]})
    assert cajas[0].estado == SIN_PEGAR
    marcar_del_overview(cajas, ["originators"])
    assert cajas[0].estado == DEL_OVERVIEW
    assert "vino en el Overview" in cajas[0].aviso
    # Lenders no se toca: su dato no está en el Overview.
    assert cajas[1].estado == SIN_PEGAR
    # Y deja de aparecer en «faltan».
    r = resumen_de_cajas(cajas)
    assert "Originators" not in r["faltan"]
    assert "Lenders" in r["faltan"]


# ══ 2 · LA TOLERANCIA AL REDONDEO ════════════════════════════════════════════

def test_2636_contra_2600_mostrado_en_K_no_avisa():
    """El caso medido. «2.6K» significa cualquier valor entre 2.550 y 2.650.

    La regla era relativa --1% de 2.600 son 26-- así que avisaba por 36 de
    diferencia: avisaba de que la fuente se redondeó a sí misma.
    """
    t = tolerancia_de_redondeo("2.6K")
    assert t == 50.0
    assert abs(2636 - 2600) <= t
    # Con la regla vieja no pasaba.
    assert not abs(2636 - 2600) < 2600 * 0.01


def test_la_tolerancia_sale_de_como_se_MOSTRO_el_numero():
    """Un decimal de K son ±50; sin decimales, ±500; sin sufijo, ±0,5."""
    assert tolerancia_de_redondeo("613.2K") == 50.0
    assert tolerancia_de_redondeo("613K") == 500.0
    assert tolerancia_de_redondeo("2.6M") == 50_000.0
    assert tolerancia_de_redondeo("1096337") == 0.5
    assert tolerancia_de_redondeo("") == 0.5


def test_un_bloque_CRUZADO_de_verdad_sigue_avisando():
    """El control: sin esto, la tolerancia se «arregla» apagando la guarda."""
    t = tolerancia_de_redondeo("2.6K")
    for otro in (3200, 1900, 5200):
        assert abs(otro - 2600) > t, otro


# ══ 3 · LAS MÉTRICAS DE MODEL MATCH LLEGAN AL MOTOR ══════════════════════════

def test_el_motor_recibe_la_produccion_anualizada():
    """P-Q11-2 la pide y nunca llegaba: no podía activarse.

    `correr_motor` usaba el perfil para el veredicto y no lo metía al registro,
    así que todos caían en P-Q11-3 «según el libro», que no distingue lado ni
    ventana.
    """
    from supabase.correr_motor import campos_de_modelmatch

    assert campos_de_modelmatch({"buyside_anualizado": 7.7}) == {
        "mm_buyside_anualizado": 7.7}
    # Sin dato NO se inventa un cero: la regla queda sin evaluar.
    assert campos_de_modelmatch({}) == {}
    assert campos_de_modelmatch(None) == {}


def test_la_regla_que_lo_pide_existe_y_lo_nombra_igual():
    """Si alguien renombra el campo en un lado, esto falla."""
    from motor.reglas import REGLAS

    piden = {c for r in REGLAS for c in r.campos if c.startswith("mm_")}
    from supabase.correr_motor import DEL_PERFIL_MM

    assert piden, "ninguna regla pide campos de Model Match"
    assert piden <= set(DEL_PERFIL_MM.values()), (
        piden - set(DEL_PERFIL_MM.values()))


def test_modelmatch_salio_de_los_campos_ausentes():
    """Estaba declarado como «lo que el motor todavía no mira», y ya lo mira."""
    from supabase.correr_motor import FALTAN_HOY

    assert "modelmatch" not in FALTAN_HOY
    assert "contrastes_de_mercado" in FALTAN_HOY


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
