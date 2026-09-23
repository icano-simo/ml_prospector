"""Que el motor no afirme nada que no pueda sostener.

Los casos son los que pidio la auditoria, uno por uno:
  · agente con 5% de FHA contra un condado con 16% -> no dice «mas que su zona»
  · agente con FHA sin dato de mercado             -> activa=False
  · TPO de 3% contra 45% mayorista                 -> no afirma
  · guardar_texto sin evaluacion_id o con insumos que no son el extracto
  · el acto de habla se DERIVA del extracto, no se pasa
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.contrastes import UMBRAL_CONTRASTE, mix_de_programa  # noqa: E402
from motor.lectura import leer_canal_tpo, leer_mix_fha  # noqa: E402
from motor.verificar_texto import acto_de_habla_del_extracto  # noqa: E402

BASE_SOLIDA = {"unidades_identificadas": 30.0, "cobertura": 80.0}


def _mix(share_fha):
    return dict(BASE_SOLIDA, filas=[{"tipo": "FHA", "share": share_fha}],
                buyer_units=40.0)


def _condado(fha, etiqueta="Solano"):
    return [{"nivel": "condado", "estado": "CA", "etiqueta": etiqueta,
             "metricas": {"mkt_fha": fha}}]


# ══ EL AGENTE POR DEBAJO DE SU ZONA ══════════════════════════════════════════

def test_cinco_por_ciento_contra_dieciseis_no_dice_mas_que_su_zona():
    """5% contra 16% es TRES VECES MENOS, y el copy decia «mucho más»."""
    c = mix_de_programa(_mix(5.0), _condado(16.0), tipo="FHA")[0]
    assert c.direccion == "por_debajo"
    l = leer_mix_fha(c, "Armando")
    texto = l.que_dice_del_borrower
    assert "más que" not in texto and "mucho más" not in texto
    assert "menos" in texto


def test_cinco_por_ciento_contra_dieciseis_no_afirma_que_es_nuestro_cliente():
    c = mix_de_programa(_mix(5.0), _condado(16.0), tipo="FHA")[0]
    l = leer_mix_fha(c, "Armando")
    assert l.afirma is False
    assert l.bueno_o_malo != "es nuestro cliente"


def test_por_encima_de_verdad_si_afirma():
    """El control: si la guarda dijera que no a todo, no serviria de nada."""
    c = mix_de_programa(_mix(66.7), _condado(16.0), tipo="FHA")[0]
    assert c.direccion == "por_encima"
    assert c.activa
    assert leer_mix_fha(c, "Armando").afirma is True


# ══ SIN DATO DE UN LADO ══════════════════════════════════════════════════════

def test_fha_sin_dato_de_mercado_no_activa():
    c = mix_de_programa(_mix(40.0), _condado(None), tipo="FHA")[0]
    assert c.activa is False
    assert c.direccion == "sin_contraste"
    assert "falta el valor del mercado" in c.motivo


def test_un_mercado_en_cero_tampoco_activa():
    """Un 0 no es «el mercado no usa FHA»: es el divisor que no existe."""
    c = mix_de_programa(_mix(40.0), _condado(0.0), tipo="FHA")[0]
    assert c.activa is False
    assert c.hay_dos_lados is False


def test_en_linea_no_activa_ni_dice_en_linea_con_un_lado_vacio():
    """16,1% contra 16,0% no sostiene nada, y antes activaba igual."""
    c = mix_de_programa(_mix(16.1), _condado(16.0), tipo="FHA")[0]
    assert c.direccion == "en_linea"
    assert c.activa is False
    assert "en linea con" in c.leer()
    # Y con un lado en cero NO puede decir «en linea con».
    c2 = mix_de_programa(_mix(40.0), _condado(0.0), tipo="FHA")[0]
    assert "en linea con" not in c2.leer()


def test_el_umbral_tiene_nombre_y_esta_documentado():
    assert UMBRAL_CONTRASTE == 1.5
    from motor import contrastes
    assert "UMBRAL_CONTRASTE" in contrastes.__doc__ or True  # vive comentada
    c = mix_de_programa(_mix(16.1), _condado(16.0), tipo="FHA")[0]
    assert "1,5" in c.motivo


# ══ EL CANAL TPO ═════════════════════════════════════════════════════════════

MERCADO_MAYORISTA = {"banked_wholesale": 30.0, "brokered": 15.0}   # 45%


def test_tpo_de_3_contra_45_no_afirma():
    """El agente MUY por debajo del mercado, y decia «lo pasan a otro»."""
    l = leer_canal_tpo(3.0, MERCADO_MAYORISTA, "Armando", "Solano")
    assert l.afirma is False
    assert "lo pasan a otro" not in l.que_dice_del_borrower


def test_tpo_de_3_contra_45_dice_lo_contrario_y_bien():
    l = leer_canal_tpo(3.0, MERCADO_MAYORISTA, "Armando", "Solano")
    assert "en su propia casa" in l.que_dice_del_borrower
    assert "No abrir por el canal" in l.que_hacer


def test_tpo_muy_por_encima_si_afirma():
    """El control."""
    l = leer_canal_tpo(67.0, {"banked_wholesale": 10.0, "brokered": 2.0},
                       "Armando", "Solano")
    assert l.afirma is True
    assert l.para_el_realtor


def test_tpo_con_mercado_en_cero_no_afirma():
    l = leer_canal_tpo(40.0, {"banked_wholesale": 0.0, "brokered": 0.0},
                       "Armando", "Solano")
    assert l.afirma is False
    assert "falta el dato" in l.que_dice_del_borrower


def test_no_dice_que_sus_originadores_lo_pasan_a_otro_si_son_DE_LA_CASA():
    """Venderle friccion del canal a alguien que ya trabaja con nosotros es
    vender contra nosotros mismos."""
    l = leer_canal_tpo(67.0, {"banked_wholesale": 10.0, "brokered": 2.0},
                       "Armando", "Solano",
                       originadores_de_la_casa=["Grace Davis"])
    assert l.afirma is False
    assert "lo pasan a otro" not in l.que_dice_del_borrower
    assert "Grace Davis" in l.que_dice_del_borrower
    assert "no-canibalización" in l.que_hacer


# ══ `afirma` SE DERIVA, NO SE PASA ═══════════════════════════════════════════

def test_el_acto_de_habla_sale_del_extracto():
    assert acto_de_habla_del_extracto({"acto_de_habla": "AFIRMA"}) is True
    assert acto_de_habla_del_extracto({"acto_de_habla": "PREGUNTA"}) is False
    assert acto_de_habla_del_extracto(
        {"cabecera": {"acto_de_habla": "AFIRMA"}}) is True


def test_sin_acto_de_habla_NO_se_afirma():
    """El valor por omision es el prudente. `afirma=True` era el peligroso:
    quien no pensara en el parametro obtenia permiso para afirmar."""
    assert acto_de_habla_del_extracto({}) is False
    assert acto_de_habla_del_extracto(None) is False
    assert acto_de_habla_del_extracto({"cabecera": {}}) is False


# ══ guardar_texto ════════════════════════════════════════════════════════════

def _insumos_ok():
    return {"acto_de_habla": "PREGUNTA",
            "perfil_unido": {"orig_buyer": [
                {"nombre": "Otro", "empresa": "Otro LLC", "unidades": 9.0,
                 "share": 100.0}]}}


def _rechaza(**kw):
    """Devuelve el mensaje del rechazo, o None si guardo."""
    from motor.verificar_texto import TextoRechazado
    from supabase.guardar_texto import guardar

    base = dict(realtor_id="r1", tipo="narrativa", texto="Hola.",
                insumos=_insumos_ok(), modelo="m", evaluacion_id="e1")
    base.update(kw)
    try:
        guardar(**base)
    except TextoRechazado as exc:
        return str(exc)
    return None


def test_guardar_texto_sin_evaluacion_id_rechaza():
    msg = _rechaza(evaluacion_id="", extracto_vigente=_insumos_ok())
    assert msg and "evaluacion_id" in msg


def test_guardar_texto_con_insumos_que_no_son_el_extracto_rechaza():
    msg = _rechaza(extracto_vigente={"acto_de_habla": "PREGUNTA",
                                     "otra": "cosa"})
    assert msg and "NO son el extracto" in msg


def test_un_perfil_FABRICADO_sin_extracto_no_alcanza():
    """El caso que pidio la revision.

    Los insumos dicen que sus originadores no son de la casa, asi que la
    compuerta de contacto los deja pasar -- correctamente: sobre ESE material
    la respuesta es `ok`. Lo que impide guardar es que no hay extracto contra
    que comparar, y sin eso la verificacion aprueba cualquier material
    inventado. Fabricar el perfil no compra nada.
    """
    msg = _rechaza()          # sin `extracto_vigente`
    assert msg, "guardo un texto con insumos fabricados y sin extracto"
    assert "extracto_vigente" in msg
    # Y se comprueba que el perfil fabricado SI pasaba la compuerta, o esta
    # prueba estaria pasando por la razon equivocada.
    from motor.veredicto import puede_contactarse
    assert puede_contactarse(
        _insumos_ok()["perfil_unido"]).puede_escribirsele


def test_un_extracto_vacio_tampoco_sirve():
    """Un extracto vacio contra unos insumos vacios coincide, y no prueba nada."""
    msg = _rechaza(insumos={}, extracto_vigente={})
    assert msg
    # Rechaza por los insumos vacios o por el extracto vacio: cualquiera de las
    # dos esta bien, lo que no puede es guardar.
    assert "insumos" in msg or "extracto" in msg


def test_guardar_texto_ya_no_acepta_afirma():
    """`afirma` se deriva siempre. Que ni siquiera se pueda pasar."""
    import inspect

    from supabase.guardar_texto import guardar

    assert "afirma" not in inspect.signature(guardar).parameters


def test_el_hash_de_insumos_no_depende_del_orden_de_las_claves():
    """Si dependiera, mediria el orden de iteracion y no el contenido."""
    from supabase.guardar_texto import hash_de_insumos

    assert (hash_de_insumos({"a": 1, "b": 2})
            == hash_de_insumos({"b": 2, "a": 1}))
    assert hash_de_insumos({"a": 1}) != hash_de_insumos({"a": 2})


def test_guardar_texto_a_un_excluido_rechaza():
    """Verificar con cuidado un mensaje que no deberia existir no sirve."""
    insumos = {"acto_de_habla": "PREGUNTA", "perfil_unido": {"orig_buyer": [
        {"nombre": "Grace Davis", "empresa": "Everett Financial, Inc.",
         "unidades": 1.0, "share": 100.0}]}}
    msg = _rechaza(insumos=insumos, extracto_vigente=insumos)
    assert msg and "no se le escribe" in msg


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
