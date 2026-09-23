"""El dossier A–G y el bloque F como regla ejecutable."""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.dossier import PREGUNTA_DE_BRECHA, armar_dossier  # noqa: E402
from motor.nunca import BLOQUE_F, NuncaSeDice, verificar_nunca  # noqa: E402
from motor.secuencia import CopyInvalido, Toque  # noqa: E402

REALTOR = {"nombre_mostrado": "Armando Ochoa", "brokerage": "eXp Realty",
           "estado": "CA", "estado_nombre": "California",
           "email_principal": "a@b.com", "sf_lead_id": "00Q123"}
NARRATIVA = ("Armando Ochoa trabaja en eXp Realty, en California. Según el "
             "libro cierra unas 16 operaciones al año.")
HIPOTESIS = [{"qualifier": "P-Q14", "papel": "principal", "intensidad": 3,
              "grado": "E0", "acto": "AFIRMA",
              "enunciado": "Sus clientes chocan con la barrera de idioma en el "
                           "proceso hipotecario",
              "regla": "declara atención en español", "regla_id": "P-Q14-1"}]
LECTURAS = [{"papel": "dominante", "geografia": "Solano", "veces": 4.2,
             "valor_agente": 66.7, "valor_mercado": 16.0,
             "que_dice_del_borrower": "Compradores que necesitan FHA."}]
GANCHO = "¿Te ha pasado que el agente del vendedor sabe más que tú?"


def _dossier(**kw):
    base = dict(realtor=REALTOR, narrativa=NARRATIVA, cabecera={"nivel": "MQL"},
                hipotesis=HIPOTESIS, lecturas=LECTURAS, perfil_zona=None,
                condado_dominante="Solano", gancho=GANCHO,
                gancho_fuente="ficha del corpus")
    return armar_dossier(**{**base, **kw})


# ══ LOS SIETE BLOQUES ════════════════════════════════════════════════════════

def test_estan_los_siete_en_orden():
    letras = [b.letra for b in _dossier()]
    assert letras == ["A", "B", "C", "D", "E", "E2", "F", "G"]


def test_B_es_la_narrativa_en_prosa():
    b = [x for x in _dossier() if x.letra == "B"][0]
    assert b.texto == NARRATIVA
    assert "ventana" in b.fuente or "Model Match" in b.fuente


def test_C_es_el_condado_DOMINANTE_y_no_los_cuatro():
    c = [x for x in _dossier() if x.letra == "C"][0]
    assert "Solano" in c.titulo
    assert {"k": "veces", "v": 4.2} in c.datos


def test_D_trae_enunciado_fuerza_grado_y_la_regla_que_lo_activo():
    d = [x for x in _dossier() if x.letra == "D"][0]
    assert d.texto.startswith("Sus clientes chocan con la barrera de idioma")
    claves = {x["k"]: x["v"] for x in d.datos}
    assert claves["fuerza"] == "3/3"
    assert claves["grado de evidencia"] == "E0"
    assert claves["se activó porque"] == "declara atención en español"
    assert claves["regla"] == "P-Q14-1"
    assert "literal" in d.fuente


def test_E_es_el_gancho_literal():
    e = [x for x in _dossier() if x.letra == "E"][0]
    assert e.texto == GANCHO


def test_E2_trae_angulo_y_municion_literales_de_la_matriz():
    e2 = [x for x in _dossier() if x.letra == "E2"][0]
    claves = {x["k"]: x["v"] for x in e2.datos}
    assert claves["ángulo"].startswith('A18 "Tu comunidad en su idioma')
    assert "LO bilingue de la casa" in claves["munición"]


def test_G_es_la_misma_pregunta_para_todos():
    """Cierra la categoría vacía en el 100% de las filas."""
    g1 = [x for x in _dossier() if x.letra == "G"][0]
    g2 = [x for x in _dossier(hipotesis=[], lecturas=[]) if x.letra == "G"][0]
    assert g1.texto == g2.texto == PREGUNTA_DE_BRECHA
    assert "lender" in g1.texto


# ══ LO QUE FALTA DICE POR QUE FALTA ══════════════════════════════════════════

def test_sin_contraste_dominante_el_bloque_C_dice_por_que():
    c = [x for x in _dossier(lecturas=[]) if x.letra == "C"][0]
    assert not c.texto
    assert "condado dominante" in c.vacio_porque


def test_sin_hipotesis_los_bloques_D_y_E2_dicen_por_que():
    bs = {b.letra: b for b in _dossier(hipotesis=[])}
    assert "intensidad acreditable" in bs["D"].vacio_porque
    assert "sin hipótesis principal" in bs["E2"].vacio_porque


def test_un_qualifier_fuera_del_banco_lo_dice_en_E2():
    h = [{**HIPOTESIS[0], "qualifier": "X-Q99"}]
    e2 = [x for x in _dossier(hipotesis=h) if x.letra == "E2"][0]
    assert "no está en el banco" in e2.vacio_porque


# ══ EL BLOQUE F · REGLA EJECUTABLE ═══════════════════════════════════════════

def test_F_trae_los_tres_completos():
    f = [x for x in _dossier() if x.letra == "F"][0]
    assert len(f.datos) == 3
    assert len(BLOQUE_F) == 3
    junto = " ".join(x["no"] + x["si"] + x["por_que"] for x in f.datos).lower()
    assert "lender" in junto
    assert "203k" in junto and "usda" in junto and "down payment" in junto
    assert "respa" in junto


def test_proponer_sustituir_al_lender_revienta():
    for frase in ("Cambiate de lender y cerramos en 15 días.",
                  # Ignorar mayúsculas no ignora tildes: `Cámbiate` se escapaba.
                  "Cámbiate de lender.",
                  "Deja a tu prestamista actual, nosotros lo hacemos mejor."):
        try:
            verificar_nunca(frase)
        except NuncaSeDice as exc:
            assert "sustituir a su lender" in str(exc)
            assert "ampliar su capacidad" in str(exc)
        else:
            raise AssertionError("%r propone sustituir" % frase)


def test_presentar_un_programa_publico_como_ventaja_propia_revienta():
    for frase in ("Con nuestro FHA 203k puedes financiar la remodelación.",
                  "Te damos nuestra exención de tasación.",
                  "Las ayudas de down payment assistance son exclusivas nuestras.",
                  "USDA solo con nosotros."):
        try:
            verificar_nunca(frase)
        except NuncaSeDice as exc:
            assert "programa público" in str(exc)
        else:
            raise AssertionError("%r se apropia de un programa público" % frase)


def test_prometer_pago_por_referir_revienta():
    for frase in ("Te pagamos por cada referido que nos mandes.",
                  "Hay comisión por referir.",
                  # `refiera` NO contiene `refer`: el verbo cambia de raíz, y
                  # un patrón que solo mira `refer` deja pasar justo esta.
                  "Pagamos comisión a quien nos refiera.",
                  "Hay un bono para quien nos refiera clientes.",
                  "Te damos 500 dólares por cada cliente."):
        try:
            verificar_nunca(frase)
        except NuncaSeDice as exc:
            assert "RESPA" in str(exc)
        else:
            raise AssertionError("%r promete pago por referir" % frase)


def test_hablar_de_los_programas_SIN_apropiarselos_pasa():
    """La guarda tiene que poder NO disparar, o no distingue nada."""
    verificar_nunca(
        "El FHA 203k existe y lo operamos; lo que cambia es en cuántos días "
        "sale y quién sostiene el expediente. Con USDA y VA igual.")
    verificar_nunca(
        "Le sostenemos el pre-approval antes de que escriba la oferta.")


def test_el_bloque_F_corre_sobre_TODO_el_copy_generado():
    """Prometerlo en un toque es peor que escribirlo en la ficha: se envía."""
    try:
        Toque(4, 21, "email", None,
              "Te pagamos por cada referido.\n\n¿Te interesa?")
    except (NuncaSeDice, CopyInvalido) as exc:
        assert "RESPA" in str(exc)
    else:
        raise AssertionError("un toque tampoco puede prometer pago por referir")


def test_un_bloque_con_texto_prohibido_no_se_puede_construir():
    from motor.dossier import Bloque

    try:
        Bloque("B", "x", texto="Cámbiate de lender.")
    except NuncaSeDice:
        pass
    else:
        raise AssertionError("la guarda corre al construir el bloque")


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
