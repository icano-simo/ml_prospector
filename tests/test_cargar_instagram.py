"""El cargador de Instagram: la llave, la PII y la coherencia CSV/crudo.

Sin red y sin base: son reglas puras sobre dicts.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from supabase.cargar_instagram import (  # noqa: E402
    A_COLUMNA,
    DE_IDENTIDAD,
    ESTADOS_VALIDOS,
    CargaInstagramFallida,
    _mismo_contacto,
    verificar_sin_pii_de_terceros,
)


def _fila(**kw):
    base = {"email": "agente@brokerage.com", "handle": "unagente",
            "estado_perfil": "publico_leido", "captions_texto": "",
            "comentarios_texto": "", "comentarios_del_agente": "",
            "citas_por_etiqueta": "", "preguntas_recibidas": ""}
    return {**base, **kw}


# ══ EL CONTACTO DEL AGENTE NO ES UNA FUGA ════════════════════════════════════
#
# La primera version de la guarda freno la carga por diez hallazgos que eran
# del propio agente: realtors que publican su telefono en sus propios captions.
# Es la misma equivocacion que ya se cometio una vez, y el motivo por el que
# una guarda tiene que mirar el trafico correcto.

def test_el_telefono_del_agente_en_su_propio_caption_pasa():
    filas = [_fila(
        captions_texto="Llámame al (773) 362-5798 para ver esta casa",
        citas_por_etiqueta='{"audiencia:vendedor": ["(773) 362-5798"]}')]
    hallado = verificar_sin_pii_de_terceros(filas)
    assert len(hallado["del_agente"]) == 1


def test_el_mismo_telefono_con_OTRO_formato_tambien_se_reconoce():
    """`(773) 362-5798`, `773.362.5798` y `7733625798` son el mismo numero.
    Comparar las cadenas daria que no coinciden, y eso convertiria el dato del
    agente en un falso positivo."""
    filas = [_fila(
        captions_texto="Escríbeme al 773.362.5798",
        citas_por_etiqueta='{"x": ["(773) 362-5798"]}')]
    verificar_sin_pii_de_terceros(filas)   # no revienta


def test_el_email_del_agente_pasa():
    filas = [_fila(
        captions_texto="Escríbeme a aosorio@captivatereg.com",
        citas_por_etiqueta='{"x": ["aosorio@captivatereg.com"]}')]
    verificar_sin_pii_de_terceros(filas)


# ══ EL DE UN TERCERO, NO ══════════════════════════════════════════════════════

def test_el_telefono_de_quien_comenta_FRENA_la_carga():
    filas = [_fila(
        captions_texto="Casa nueva en Solano",
        comentarios_texto="Me interesa, llámame al (415) 555-0142",
        citas_por_etiqueta='{"x": ["llámame al (415) 555-0142"]}')]
    try:
        verificar_sin_pii_de_terceros(filas)
    except CargaInstagramFallida as exc:
        assert "NO son del agente" in str(exc)
        assert "en comentarios de terceros" in str(exc)
    else:
        raise AssertionError("un dato de contacto de un tercero no entra")


def test_la_procedencia_desconocida_TAMPOCO_pasa():
    """No aparecer en ninguna de las dos columnas no es un aprobado."""
    filas = [_fila(citas_por_etiqueta='{"x": ["(415) 555-0142"]}')]
    try:
        verificar_sin_pii_de_terceros(filas)
    except CargaInstagramFallida as exc:
        assert "procedencia desconocida" in str(exc)
    else:
        raise AssertionError("sin saber de quién es, no entra")


def test_sin_texto_la_guarda_no_inventa_hallazgos():
    hallado = verificar_sin_pii_de_terceros([_fila()])
    assert hallado["del_agente"] == []


def test_mismo_contacto_no_confunde_dos_numeros_distintos():
    assert _mismo_contacto("(773) 362-5798", "773.362.5798")
    assert not _mismo_contacto("(773) 362-5798", "(773) 362-5799")
    assert not _mismo_contacto("a@b.com", "c@d.com")
    assert not _mismo_contacto("(773) 362-5798", "")


# ══ LAS COLUMNAS ═════════════════════════════════════════════════════════════

def test_las_de_identidad_no_entran_en_el_jsonb_de_señales():
    """`email` y `nombre` son identidad, no señal. El handle SI es señal y por
    eso tiene columna propia."""
    assert "email" in DE_IDENTIDAD and "nombre" in DE_IDENTIDAD
    assert not (DE_IDENTIDAD & A_COLUMNA)


def test_los_nueve_estados_son_los_del_check():
    assert ESTADOS_VALIDOS == {
        "publico_leido", "privado", "no_encontrado", "bloqueado",
        "handle_dudoso", "muro_de_sesion", "sin_grid", "degradado", "vacio"}
    assert "privado" in ESTADOS_VALIDOS
    assert len(ESTADOS_VALIDOS) == 9


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
