"""La ficha v3: las nueve secciones que el BD lee antes de escribir.

Las reglas de la maqueta, como pruebas
--------------------------------------
No alcanza con que la pantalla se vea igual. Lo que decide si sirve es si se
puede decir en voz alta lo que muestra, y eso son cuatro reglas:

  1 · cada dato con su «de dónde sale»;
  2 · lo que no existe es `Pendiente`, no una estimación;
  3 · las hipótesis se escriben como hipótesis;
  4 · nada de nombres de tablas, ids de regla ni nombres de buyers.

La sección 2 (Salesforce) queda en `Pendiente` hasta que el sync exista.
"""
from __future__ import annotations

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))

from api.ficha import (  # noqa: E402
    DATO,
    HIPOTESIS,
    LO_CUENTA_ELLA,
    PENDIENTES,
    contactos_por_canal,
    dolores_posibles,
    grado_de,
    iniciales,
    objecion,
    razones,
    telefono_para_el_primer_contacto,
    trimestres_de,
)

# ══ 1 · QUIÉN ES ═════════════════════════════════════════════════════════════

def test_las_iniciales_para_el_avatar_sin_foto():
    """La ficha no lleva foto. Decisión del 2026-09-23."""
    assert iniciales("Ana Osorio") == "AO"
    assert iniciales("ANA KAREN OSORIO") == "AO"
    assert iniciales("Cher") == "CH"
    assert iniciales("") == "··"
    assert iniciales(None) == "··"


def test_cada_contacto_lleva_TODAS_sus_fuentes():
    """Un teléfono en tres fuentes y otro en una no valen lo mismo.

    Y el que está en una sola puede ser el bueno --el que usa hoy-- o el que
    quedó de un archivo viejo. Las dos cosas se ven si se muestran las fuentes;
    ninguna se ve si se muestra un teléfono.
    """
    cs = contactos_por_canal([
        {"canal": "telefono", "valor": "(773) 370-1489", "fuente": "lote"},
        {"canal": "telefono", "valor": "(773) 370-1489", "fuente": "Model Match"},
        {"canal": "telefono", "valor": "(773) 362-5798", "fuente": "Instagram"},
        {"canal": "email", "valor": "a@b.com", "fuente": "Model Match"},
    ])
    viejo = next(c for c in cs if c["valor"] == "(773) 370-1489")
    nuevo = next(c for c in cs if c["valor"] == "(773) 362-5798")
    assert sorted(viejo["fuentes"]) == ["Model Match", "lote"]
    assert viejo["una_sola_fuente"] is False
    assert nuevo["una_sola_fuente"] is True


def test_el_primer_contacto_va_al_telefono_que_usa_hoy():
    """El que publica en Instagram es el que contesta; el del archivo puede
    tener dos años."""
    cs = contactos_por_canal([
        {"canal": "telefono", "valor": "VIEJO", "fuente": "archivo original"},
        {"canal": "telefono", "valor": "HOY", "fuente": "Instagram"},
    ])
    assert telefono_para_el_primer_contacto(cs)["valor"] == "HOY"


def test_sin_telefono_lo_dice_en_vez_de_dejar_un_hueco():
    """Un hueco se lee como «no hace falta». Sin teléfono no hay primer
    contacto, y eso es lo primero que hay que resolver."""
    t = telefono_para_el_primer_contacto([])
    assert t["pendiente"]
    assert "no hay ningún teléfono" in t["pendiente"]


# ══ 2 · EL GRADO SALE DEL CAMPO, NO DE LA LETRA ══════════════════════════════

def test_lo_que_mide_model_match_es_un_Dato():
    assert grado_de({"grado": "E1",
                     "campos_leidos": {"mm_share_buy": 0.75}}) == DATO


def test_un_ev2_SIN_CITA_es_Hipotesis_y_no_su_palabra():
    """La corrección del 2026-09-24, y el caso que la motivó.

    `ev2_fha_gob` llega por DOS caminos: una columna del libro v3 cuya
    derivación no está documentada, y `menciona_fha` de Instagram, que cuenta
    menciones en los captions. Así que «lo cuenta ella» podía ser un puntaje
    heredado o un post que enumera tipos de financing.

    El BD lo iba a repetir en la llamada como si ella lo hubiera dicho, y lo
    que se cae cuando la realtor no lo reconoce no es la frase: es la
    credibilidad de todo lo demás.
    """
    assert grado_de({"grado": "E1",
                     "campos_leidos": {"ev2_fha_gob": True}}) == HIPOTESIS
    # Y ni una cita sin fecha alcanza: sin fecha no se puede decir «el 15 de
    # junio dijo», que es lo único que el BD puede usar.
    assert grado_de({"grado": "E1", "campos_leidos": {"ev2_fha_gob": True}},
                    {"ev2_fha_gob": {"texto": "hablo de FHA"}}) == HIPOTESIS


def test_con_la_cita_y_su_fecha_SI_es_Lo_cuenta_ella():
    """El control: la regla no es «nunca», es «no sin la cita»."""
    assert grado_de(
        {"grado": "E1", "campos_leidos": {"ev2_dpa_enganche": True}},
        {"ev2_dpa_enganche": {"texto": "ayudo con el down payment",
                              "fecha": "2026-06-15"}}) == LO_CUENTA_ELLA


def test_un_puntaje_del_libro_es_una_Hipotesis():
    assert grado_de({"grado": "E1",
                     "campos_leidos": {"R5_espanol": 8}}) == HIPOTESIS
    assert grado_de({"grado": "E3",
                     "campos_leidos": {"E3_urgencia_sept": 6.5}}) == HIPOTESIS


def test_con_dos_fuentes_gana_la_mas_observada():
    """Una regla que cruza Model Match con la bio se sostiene en Model Match."""
    assert grado_de({"grado": "E0", "campos_leidos": {
        "mm_share_buy": 0.75, "ev2_buy_side": True}}) == DATO


# ══ 3 · POR QUÉ ELLA ═════════════════════════════════════════════════════════

RESUMEN = {
    "compras": {"total": 18, "financiada": 8, "cash_segun_mm": 9,
                "cash_provisional": 1, "no_leido": 0},
    "ventas": {"total": 7, "financiada": 2, "cash_segun_mm": 4,
               "cash_provisional": 1, "no_leido": 0},
    "lenders_compra": {"Guaranteed Rate": 3, "Zillow Home Loans": 2,
                       "Stonehaven Mortgage": 1,
                       "Angel Oak Mortgage Solutions": 1, "Peoples Bank": 1},
}


def test_las_razones_salen_de_lo_medido_y_no_de_un_puntaje():
    """El BD las va a decir en voz alta. Una razón que sale de un score no se
    puede sostener en una llamada."""
    rs = razones(RESUMEN, [], {})
    titulos = [r["titulo"] for r in rs]
    assert "Buy side fuerte y sin lender fijo" in titulos
    assert "Muchos cash buyers" in titulos
    buy = next(r for r in rs if r["titulo"].startswith("Buy side"))
    assert "18 buys y 7 listings" in buy["texto"]
    assert "Guaranteed Rate, el que más usa, tiene solo 3" in buy["texto"]
    # Cada una con su de dónde sale.
    assert all(r["de_donde"] for r in rs)


def test_los_cash_se_cuentan_sobre_los_que_YA_tienen_datos():
    """9 de 17, no 9 de 18: la del 14 sep todavía no tiene datos de loan.

    Meterla en el denominador es contar como «no cash» algo que todavía no se
    sabe.
    """
    r = next(x for x in razones(RESUMEN, [], {})
             if x["titulo"] == "Muchos cash buyers")
    assert "9 de sus 17 closings" in r["texto"]
    assert r["hipotesis"] is True


def test_nunca_son_mas_de_tres_razones():
    activaciones = [{"familia": "P", "intensidad": 3, "texto": "x",
                     "campos_leidos": {}, "origen": "propia",
                     "referencia": "r"}]
    assert len(razones(RESUMEN, activaciones, {})) <= 3


def test_sin_transactions_no_se_inventan_razones():
    assert razones(None, [], {}) == []


# ══ 4 · DOLORES POSIBLES ═════════════════════════════════════════════════════

ACTIVACIONES = [
    {"qualifier": "P-Q01", "familia": "P", "intensidad": 2, "grado": "E1",
     "texto": "su bio menciona un programa de gobierno",
     "campos_leidos": {"ev2_dpa_enganche": True}, "regla_id": "P-Q01-2"},
    {"qualifier": "P-Q11", "familia": "P", "intensidad": 3, "grado": "E1",
     "texto": "producción anualizada del lado comprador",
     "campos_leidos": {"mm_buyside_anualizado": 20.6}, "regla_id": "P-Q11-2"},
    {"qualifier": "J-Q01", "familia": "J", "intensidad": 2, "grado": "E1",
     "texto": "compuerta", "campos_leidos": {"mm_share_buy": 0.7},
     "regla_id": "J-Q01-MM1"},
]


def test_solo_los_dolores_de_familia_P_entran_en_la_tabla():
    """Un J-Q no es un dolor: es un modulador. Ponerlo en la tabla de dolores
    invita a abrir con él."""
    ds = dolores_posibles(ACTIVACIONES, {}, {})
    assert [d["qualifier"] for d in ds] == ["P-Q11", "P-Q01"]


def test_cada_dolor_trae_su_grado_y_su_pregunta():
    ds = dolores_posibles(ACTIVACIONES, {"P-Q11": "Enunciado de P-Q11"},
                          {"P-Q11": "¿Cuántos closings al mes?"})
    p11 = next(d for d in ds if d["qualifier"] == "P-Q11")
    assert p11["grado"] == DATO
    assert p11["dolor"] == "Enunciado de P-Q11"
    assert p11["pregunta"] == "¿Cuántos closings al mes?"
    p01 = next(d for d in ds if d["qualifier"] == "P-Q01")
    assert p01["grado"] == HIPOTESIS, "un ev2_* sin cita no es su palabra"


def test_los_dolores_van_de_mas_fuerte_a_menos():
    ds = dolores_posibles(ACTIVACIONES, {}, {})
    assert [d["intensidad"] for d in ds] == [3, 2]


# ══ 5 y 6 · CONVERSAR ════════════════════════════════════════════════════════

def test_la_objecion_nombra_al_lender_contra_el_que_se_compite():
    o = objecion(RESUMEN)
    assert o["lender"] == "Guaranteed Rate"
    assert "3 de sus 8 financed buys" in o["texto"]
    # Y dice cómo NO plantearlo.
    assert "No busques reemplazarlo" in o["texto"]


def test_sin_lenders_no_hay_objecion_inventada():
    assert objecion(None) is None
    assert objecion({"lenders_compra": {}}) is None


# ══ 7 · PRODUCCIÓN ═══════════════════════════════════════════════════════════

FILAS = [
    {"fecha": "2025-08-04", "lado": "compra"},
    {"fecha": "2025-10-17", "lado": "compra"},
    {"fecha": "2025-11-03", "lado": "compra"},
    {"fecha": "2025-11-10", "lado": "compra"},
    {"fecha": "2026-01-30", "lado": "compra"},
    {"fecha": "2026-09-14", "lado": "compra"},
    {"fecha": "2026-01-12", "lado": "venta"},
]


def test_los_trimestres_incompletos_van_marcados():
    """Un trimestre parcial dibujado igual que uno completo cuenta una caída
    que no pasó: el último siempre va a la mitad porque el trimestre va a la
    mitad."""
    ts = trimestres_de(FILAS)
    assert ts[0]["parcial"] is True, "el primero empieza el 4 ago"
    assert ts[-1]["parcial"] is True, "el último termina el 14 sep"
    assert ts[0]["etiqueta"] == "jul–sep 25"
    completos = [t for t in ts if not t["parcial"]]
    assert completos and all(t["n"] >= 1 for t in completos)


def test_los_trimestres_cuentan_solo_el_lado_pedido():
    ts = trimestres_de(FILAS, lado="venta")
    assert sum(t["n"] for t in ts) == 1


def test_sin_operaciones_no_hay_trimestres():
    assert trimestres_de([]) == []


# ══ LO QUE NO EXISTE ES `Pendiente` ══════════════════════════════════════════

def test_los_cinco_pendientes_estan_declarados_con_su_motivo():
    """«Pendiente» sin motivo es un hueco con otro nombre: nadie sabe qué hay
    que hacer para resolverlo."""
    assert set(PENDIENTES) == {"puntaje", "lo_asignado", "census_zip",
                               "seguidores", "salesforce"}
    for clave, motivo in PENDIENTES.items():
        assert motivo and len(motivo) > 15, clave


def test_la_seccion_de_salesforce_esta_pendiente_y_no_estimada():
    assert "sync" in PENDIENTES["salesforce"]


# ══ LO QUE NO PUEDE APARECER EN PANTALLA ═════════════════════════════════════

def test_ningun_texto_de_la_ficha_nombra_una_tabla_o_una_regla():
    """Los ids de regla y los nombres de tabla van en «Cómo se calculó».

    `regla_id` viaja en el dato --se necesita para auditar-- pero ningún TEXTO
    de los que la pantalla pinta puede traerlo.
    """
    ds = dolores_posibles(ACTIVACIONES, {}, {})
    rs = razones(RESUMEN, ACTIVACIONES, {})
    textos = ([d["dolor"] for d in ds] + [d["evidencia"] for d in ds]
              + [r["titulo"] for r in rs] + [r["texto"] for r in rs]
              + [objecion(RESUMEN)["texto"]]
              + list(PENDIENTES.values()))
    entero = " ".join(t for t in textos if t)
    for prohibido in ("pacs.", "v_evaluacion_actual", "upload_batch_id",
                      "P-Q01-2", "J-Q01-MM1", "mm_share_buy", "ev2_"):
        assert prohibido not in entero, prohibido


def test_el_vocabulario_de_lending_va_en_ingles():
    """Traducirlo obliga al BD a volver a traducirlo en la llamada."""
    rs = razones(RESUMEN, [], {})
    entero = " ".join(r["texto"] for r in rs) + objecion(RESUMEN)["texto"]
    assert "financed buys" in entero
    assert "cash" in entero
    for traducido in ("compras financiadas", "prestamista", "tasa de interés",
                      "pago inicial"):
        assert traducido not in entero, traducido


def test_una_hipotesis_viene_marcada_como_hipotesis():
    """«2 buys con Zillow podría indicar…», no «le llegan buyers por Zillow»."""
    r = next(x for x in razones(RESUMEN, [], {})
             if x["titulo"] == "Muchos cash buyers")
    assert r["hipotesis"] is True
    assert "No sabemos si" in r["texto"]


# ══ 7 · PRODUCCIÓN: los LOs bajo cada lender y el orden del loan mix ════════

def test_los_LOs_se_buscan_con_el_nombre_AGRUPADO_del_lender():
    """El conteo dice «Guaranteed Rate» y la fila «Guaranteed Rate Inc».

    Comparando el nombre crudo, los cuatro lenders con sufijo societario
    salían sin un solo LO y el único con detalle era «Peoples Bank», que es el
    que no lleva sufijo. No fallaba nada: la caja se titula «Lenders y LOs» y
    mostraba lenders sin LOs, que se lee como que el dato no existe.
    """
    from api.rutas import _los_del_lender

    # En el orden en que llegan de verdad: de la más nueva a la más vieja.
    filas = [
        {"lado": "compra", "lender": "Guaranteed Rate Inc",
         "lo_nombre": "Brian Dombrowski", "fecha": "2026-07-30", "tasa": None},
        {"lado": "compra", "lender": "Guaranteed Rate, Inc.",
         "lo_nombre": "Fabian Viera", "fecha": "2026-04-03", "tasa": None},
        {"lado": "compra", "lender": "Guaranteed Rate Inc",
         "lo_nombre": "Fabian Viera", "fecha": "2026-03-19", "tasa": None},
        {"lado": "venta", "lender": "Guaranteed Rate Inc",
         "lo_nombre": "Nadie De Este Lado", "fecha": "2026-05-05",
         "tasa": None},
    ]
    d = _los_del_lender(filas, "Guaranteed Rate")
    assert d == "Fabian Viera (19 mar y 3 abr) · Brian Dombrowski (30 jul)", d
    # El lado vendedor no entra: la caja es de los buyers de ella.
    assert "Nadie" not in d


def test_el_rate_solo_acompana_al_lender_de_UNA_sola_operacion():
    """Con una operación el rate es un dato; con cinco sería un promedio."""
    from api.rutas import _los_del_lender

    una = [{"lado": "compra", "lender": "Angel Oak Mortgage Solutions Llc",
            "lo_nombre": "Mason Sorrels", "fecha": "2026-02-17",
            "tasa": 7.62}]
    assert (_los_del_lender(una, "Angel Oak Mortgage Solutions")
            == "Mason Sorrels (17 feb) · rate 7,62 %")

    dos = una + [{"lado": "compra", "lender": "Angel Oak Mortgage Solutions",
                  "lo_nombre": "Otra Persona", "fecha": "2026-03-01",
                  "tasa": 6.1}]
    assert "rate" not in _los_del_lender(dos, "Angel Oak Mortgage Solutions")


def test_el_loan_mix_va_de_mayor_a_menor_y_Pendiente_al_final():
    """El orden ES la lectura: una barra sin ordenar obliga a leer números."""
    from api.rutas import _loan_mix

    filas = _loan_mix(
        {"Conventional": 5, "HE": 1, "FHA": 2},
        {"cash_segun_mm": 9, "cash_provisional": 1})
    assert [f["tipo"] for f in filas] == [
        "Cash", "Conventional", "FHA", "Home Equity", "Pendiente"], filas
    # `HE` no se entiende sola; `Pendiente` no es un tipo de préstamo, es que
    # Model Match todavía no lo sabe, así que va último aunque empate.
    assert filas[-1] == {"tipo": "Pendiente", "n": 1}


def test_sin_cash_no_se_muestra_una_barra_de_cero():
    from api.rutas import _loan_mix

    filas = _loan_mix({"FHA": 2}, {"cash_segun_mm": 0, "cash_provisional": 0})
    assert filas == [{"tipo": "FHA", "n": 2}], filas


# ══ 11 · LO QUE SE APAGA ES LA PARTE, NO LA PESTAÑA ══════════════════════════

def test_el_bloque_que_no_pasa_deja_su_motivo_en_el_hueco():
    """Un bloque que desaparece se lee como que no había nada que decir."""
    from api.rutas import _solo_lo_valido

    salida = _solo_lo_valido(
        {"A": {"texto": "Quién es."}, "D": {"texto": "La hipótesis."}},
        {"D": ["AFIRMA sin una activación de intensidad 3 y grado E0"]})
    assert salida["A"] == {"texto": "Quién es."}
    assert salida["D"] == {
        "_pendiente": ["AFIRMA sin una activación de intensidad 3 y grado E0"]}


def test_un_problema_de_la_seccion_entera_apaga_la_seccion():
    from api.rutas import _solo_lo_valido

    salida = _solo_lo_valido({"A": {"texto": "Quién es."}},
                             {"": ["el realtor está excluido"]})
    assert salida == {"_pendiente": ["el realtor está excluido"]}


def test_el_toque_apagado_conserva_su_numero_y_su_dia_de_PACS():
    """Y el día sale de PACS, no del texto: el día pudo ser lo que falló."""
    from api.rutas import _secuencia_valida
    from motor.secuencia import DIAS_PACS

    seq = {"toques": [{"n": 1, "dia": 0, "texto": "Hola."},
                      {"n": 2, "dia": 99, "texto": "Te mando la guía."}]}
    salida = _secuencia_valida(seq, {"toques[1]": ["promete material"]},
                               DIAS_PACS)
    assert salida["toques"][0]["texto"] == "Hola."
    assert salida["toques"][1] == {"n": 2, "dia": 3,
                                   "_pendiente": ["promete material"]}


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
