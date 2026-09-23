"""La compuerta unica: excluido, pendiente_modelmatch u ok.

El golden de punta a punta va sobre el volcado crudo de Armando Ochoa que ya
vivia en `test_captura.py`: crudo -> parser -> veredicto -> secuencia. Armando
tiene UNA operacion buyside con Grace Davis, de Everett Financial. Una basta.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from captura.parser_mm import unir_perfiles  # noqa: E402
from captura.protocolo import separar_volcado  # noqa: E402
from motor.veredicto import (  # noqa: E402
    EXCLUIDO,
    OK,
    PENDIENTE,
    UNIDADES_MINIMAS_PARA_EXCLUIR,
    puede_contactarse,
)
from tests.test_captura import VOLCADO  # noqa: E402


#: El volcado de `test_captura` MAS su bloque `Buyer Side Relationships`.
#:
#: El fixture original solo trae la pestaña `Originators`, que reparte por
#: VOLUMEN. La exclusion se decide por UNIDADES y `wallet_share_para_exclusion`
#: se niega a caer al reparto por volumen -- con razon: sobre la captura real de
#: Armando, Chris Ruiz da 50,0% por unidades y 30,7% por volumen, y con un
#: umbral entra o no entra segun cual se lea.
#:
#: Asi que sobre el fixture pelado el veredicto correcto es `pendiente`, y eso
#: tambien se prueba abajo. El golden necesita el bloque que trae el volcado de
#: verdad, y son estas dos lineas.
#: El nombre va en su propia linea y la EMPRESA en la del monto: es la trampa 5
#: del parser, y es lo que permite ver que Everett Financial es Supreme Lending.
#: Va dentro del Overview, que es donde Model Match lo pone de verdad.
VOLCADO_COMPLETO = VOLCADO.replace(
    "Top Builders\n",
    "Buyer Side Relationships\n"
    "Grace Davis\n"
    "Everett Financial, Inc.\t$540K\t1\t50.0%\n"
    "Marco Villa\n"
    "Otro Lender LLC\t$520K\t1\t50.0%\n"
    "Top Builders\n", 1)


def _perfil(volcado: str) -> dict:
    """Del crudo al perfil unido, por el mismo camino que usa el guardado.

    `parsear_perfil` corre sobre CADA seccion y `unir_perfiles` las junta: el
    reparto por unidades vive en la seccion del Overview y la tabla de
    originadores en otra. Parsear una sola daria `pendiente` sobre un volcado
    completo, que es el error que `unir_perfiles` existe para evitar.
    """
    from captura.parser_mm import parsear_perfil

    s = separar_volcado(volcado)
    trozos = [parsear_perfil(s[k]) for k in ("overview", "originators",
                                             "lenders") if s.get(k)]
    return unir_perfiles([t for t in trozos if isinstance(t, dict)])


def _perfil_de_armando() -> dict:
    return _perfil(VOLCADO_COMPLETO)


def test_sin_reparto_por_unidades_el_veredicto_es_PENDIENTE_no_ok():
    """La guarda del §8, vista desde la compuerta.

    El volcado sin `Buyer Side Relationships` trae la tabla de originadores,
    que reparte por volumen. Caer ahi daria un numero plausible con la
    definicion equivocada, asi que no se cae: se dice que no se sabe.
    """
    v = puede_contactarse(_perfil(VOLCADO))
    assert v.estado == PENDIENTE, v.a_dict()
    assert "reparto" in v.motivo


# ══ EL GOLDEN · ARMANDO OCHOA, DE PUNTA A PUNTA ══════════════════════════════

def test_armando_sale_EXCLUIDO_desde_el_volcado_crudo():
    """Una sola operacion con Everett Financial basta. Umbral > 0."""
    v = puede_contactarse(_perfil_de_armando())
    assert v.estado == EXCLUIDO, v.a_dict()
    assert not v.puede_escribirsele
    assert "Grace Davis" in (v.evidencia.get("originadores_de_la_casa") or [])
    assert v.evidencia["unidades_de_la_casa"] == 1
    assert v.evidencia["base"] == "unidades"


def test_el_veredicto_de_armando_trae_su_evidencia_completa():
    """Un estado sin evidencia obliga a recalcularlo para poder discutirlo."""
    v = puede_contactarse(_perfil_de_armando(), capturado_en="2026-09-22")
    # Se afirma el estado ANTES que las claves: la primera version de esta
    # prueba solo miraba que las claves existieran, y pasaba sobre un veredicto
    # `pendiente` -- comprobando la forma de una respuesta equivocada.
    assert v.estado == EXCLUIDO, v.a_dict()
    for clave in ("base", "umbral", "capturado_en", "originadores_de_la_casa",
                  "unidades_de_la_casa", "unidades_totales",
                  "share_de_la_casa"):
        assert clave in v.evidencia, clave
    assert v.evidencia["capturado_en"] == "2026-09-22"


def test_armando_no_produce_NI_UN_toque():
    """Lo que el PR existe para impedir: que un excluido reciba secuencia."""
    from motor.secuencia import armar_secuencia

    v = puede_contactarse(_perfil_de_armando())
    assert not v.puede_escribirsele
    # La secuencia SOLO se arma si la compuerta deja. Quien la llame sin
    # preguntar es el bug; esta prueba fija que el veredicto lo impide.
    toques = [] if not v.puede_escribirsele else armar_secuencia(
        nombre="Armando", lecturas=[], apertura_sin_dolor="¿Y?").toques
    assert toques == []


# ══ SIN MODEL MATCH NO HAY VEREDICTO ═════════════════════════════════════════

def test_sin_captura_es_PENDIENTE_y_no_ok():
    """`pendiente` no es `ok` con menos datos: es no saber."""
    v = puede_contactarse(None)
    assert v.estado == PENDIENTE
    assert not v.puede_escribirsele
    assert "Model Match" in v.motivo


def test_con_captura_pero_sin_reparto_es_PENDIENTE():
    """Hay volcado y no se pudo leer `orig_buyer`: tampoco se sabe."""
    v = puede_contactarse({"nombre": "Fulano", "buyer_units": 30.0})
    assert v.estado == PENDIENTE
    assert not v.puede_escribirsele


def test_pendiente_no_se_confunde_con_excluido():
    """Son dos cosas distintas y la pantalla dice cosas distintas de cada una."""
    assert puede_contactarse(None).estado != EXCLUIDO


# ══ EL UMBRAL ES > 0, NO UN PORCENTAJE ═══════════════════════════════════════

def test_una_sola_operacion_con_la_casa_excluye():
    perfil = {"orig_buyer": [
        {"nombre": "Grace Davis", "empresa": "Everett Financial, Inc.",
         "unidades": 1.0, "share": 5.0},
        {"nombre": "Otro", "empresa": "Otro Lender LLC", "unidades": 19.0,
         "share": 95.0}]}
    v = puede_contactarse(perfil)
    assert v.estado == EXCLUIDO
    assert v.evidencia["share_de_la_casa"] == 5.0
    # El share viaja aunque no decida: «1 de 20» y «18 de 20» son la misma
    # decision con conversaciones muy distintas detras.
    assert v.evidencia["unidades_totales"] == 20.0


def test_cero_operaciones_con_la_casa_es_OK():
    perfil = {"orig_buyer": [
        {"nombre": "Otro", "empresa": "Otro Lender LLC", "unidades": 20.0,
         "share": 100.0}]}
    v = puede_contactarse(perfil)
    assert v.estado == OK
    assert v.puede_escribirsele
    assert v.evidencia["unidades_de_la_casa"] == 0


def test_el_umbral_es_cero_y_esta_declarado():
    """Decision de negocio, no un parametro que se afine sobre la marcha."""
    assert UNIDADES_MINIMAS_PARA_EXCLUIR == 0


# ══ LA EXCLUSION DEL LIBRO MANDA SOBRE TODO ══════════════════════════════════

def test_el_libro_excluye_aunque_no_haya_captura():
    v = puede_contactarse(None, excluido_por_el_libro="DESCARTADO",
                          motivo_del_libro="fuera del ICP")
    assert v.estado == EXCLUIDO
    assert v.evidencia["nivel"] == "DESCARTADO"
    assert v.evidencia["motivo_del_libro"] == "fuera del ICP"


def test_el_libro_excluye_aunque_el_perfil_este_limpio():
    perfil = {"orig_buyer": [{"nombre": "Otro", "empresa": "Otro LLC",
                              "unidades": 20.0, "share": 100.0}]}
    v = puede_contactarse(perfil, excluido_por_el_libro="BLOQUEADO POR COBERTURA")
    assert v.estado == EXCLUIDO


# ══ LA TABLA DE LA SECCION 2: UNA PRUEBA POR FILA ════════════════════════════
#
# Decisión de Isabella del 2026-09-23: si Model Match no muestra originadores,
# está bien y el realtor NO queda bloqueado. Lo que bloquea es no saber.

def test_sin_captura_sigue_siendo_pendiente():
    """Fila 1. No cambia."""
    assert puede_contactarse(None).estado == PENDIENTE


def test_originators_vacio_DECLARADO_es_ok():
    """Fila 2. La casilla es lo único que distingue «no hay» de «no miré»."""
    v = puede_contactarse({"nombre": "Fulana", "buyer_units": 12.0,
                           "sin_originadores_declarado": True})
    assert v.estado == OK, v.a_dict()
    assert v.puede_escribirsele
    assert "no registra originadores" in v.motivo
    assert v.evidencia["unidades_de_la_casa"] == 0
    assert v.evidencia["vacio_declarado"] is True


def test_originators_con_filas_por_unidades_funciona_como_siempre():
    """Fila 3."""
    con_casa = {"orig_buyer": [
        {"nombre": "Grace Davis", "empresa": "Everett Financial, Inc.",
         "unidades": 1.0, "share": 50.0},
        {"nombre": "Otro", "empresa": "Otro LLC", "unidades": 1.0,
         "share": 50.0}]}
    assert puede_contactarse(con_casa).estado == EXCLUIDO
    sin_casa = {"orig_buyer": [
        {"nombre": "Otro", "empresa": "Otro LLC", "unidades": 2.0,
         "share": 100.0}]}
    assert puede_contactarse(sin_casa).estado == OK


def test_solo_la_pestana_por_volumen_es_pendiente_y_lo_dice():
    """Fila 4. El motivo tiene que decir QUE falta pegar."""
    v = puede_contactarse({"tab_orig": [
        {"nombre": "Grace Davis", "empresa": "Everett Financial, Inc.",
         "unidades": 1, "share": 35.3}]})
    assert v.estado == PENDIENTE, v.a_dict()
    assert "Buyer Side Relationships" in v.motivo
    assert "VOLUMEN" in v.motivo


def test_sin_pegar_y_sin_casilla_es_pendiente_y_menciona_la_casilla():
    """Fila 5. El motivo tiene que decir qué hacer, no solo qué falta."""
    v = puede_contactarse({"nombre": "Fulana", "buyer_units": 12.0})
    assert v.estado == PENDIENTE, v.a_dict()
    assert "falta la sección Originators" in v.motivo
    assert "casilla" in v.motivo


def test_la_casilla_NO_salva_a_un_excluido_por_el_libro():
    """El orden importa: la exclusión metodológica manda sobre todo."""
    v = puede_contactarse({"sin_originadores_declarado": True},
                          excluido_por_el_libro="DESCARTADO")
    assert v.estado == EXCLUIDO


def test_armando_ochoa_sigue_excluido():
    """El control de la sección 2: el caso que no puede cambiar."""
    v = puede_contactarse(_perfil_de_armando())
    assert v.estado == EXCLUIDO, v.a_dict()
    assert v.evidencia["unidades_de_la_casa"] == 1


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
