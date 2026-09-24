"""Ninguna prueba toca producción.

Decisión del 2026-09-23: las pruebas de re-evaluación van contra datos de
prueba o el WSGI local. En producción solo entran re-evaluaciones de capturas
reales.

`supabase/reevaluar.py` ESCRIBE en `pacs.evaluaciones`. Una prueba que lo
llame contra la base real mete filas de mentira en el histórico append-only de
alguien — y append-only significa que no se borran. Por eso la regla se
comprueba, no se recuerda.

La suite ya corre sin red por diseño. Esto lo fija: si alguien agrega mañana
una prueba que abre una conexión, falla acá y no en producción.
"""
from __future__ import annotations

import glob
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

#: Lo que delata una prueba que ABRE una conexión.
#:
#: `from supabase.cargar import ...` NO está: importar una constante o una
#: función que falla antes de conectar no toca nada, y con ese patrón la guarda
#: acusaba a dos pruebas legítimas de `test_captura.py` -- una de las cuales
#: existe justamente para comprobar que una guarda falla ANTES de abrir la
#: conexión. Una guarda que grita sobre lo bueno se termina apagando.
#:
#: Lo que se busca es el ACTO de conectar, no la cercanía al módulo que sabe.
#:
#: Y se miran solo las líneas de CÓDIGO: un comentario que cita la llamada para
#: explicar por qué no se hace no es una llamada. Pasó con `test_reevaluacion`,
#: y el primer arreglo fue partir el nombre en dos trozos para que el patrón no
#: lo viera -- o sea esquivar la guarda en vez de corregirla, que es peor que
#: no tenerla: la siguiente persona copia el truco.
SEÑALES = (
    r"psycopg\.connect",
    r"SUPABASE_DB_URL",
    r"\bcargar_env\s*\(",
    r"\bconectar\s*\(\s*\)",
    r"urlopen\s*\(",
    r"\brequests\.(get|post)\s*\(",
)

#: Este archivo se nombra a sí mismo al declarar los patrones.
SE_EXCLUYE = {"test_sin_produccion.py"}


def _archivos():
    return [r for r in sorted(glob.glob(os.path.join(RAIZ, "tests", "*.py")))
            if os.path.basename(r) not in SE_EXCLUYE]


def _solo_codigo(texto: str) -> str:
    """El archivo sin sus comentarios de línea.

    No quita docstrings: una llamada dentro de un docstring tampoco se ejecuta,
    pero ahí sí conviene que moleste -- un ejemplo copiable en la documentación
    de una prueba es lo que alguien va a copiar.
    """
    return "\n".join(l.split("#", 1)[0] if "#" in l and not _en_cadena(l) else l
                     for l in texto.splitlines())


def _en_cadena(linea: str) -> bool:
    """¿El primer `#` de la línea está dentro de comillas? Entonces no es comentario."""
    antes = linea.split("#", 1)[0]
    return antes.count('"') % 2 == 1 or antes.count("'") % 2 == 1


def test_ninguna_prueba_abre_una_conexion():
    culpables = []
    for ruta in _archivos():
        with open(ruta, encoding="utf-8") as fh:
            texto = _solo_codigo(fh.read())
        for patron in SEÑALES:
            if re.search(patron, texto):
                culpables.append((os.path.basename(ruta), patron))
    assert not culpables, (
        "estas pruebas salen a la base o a la red: %s. Van contra datos de "
        "prueba o el WSGI local -- `reevaluar` ESCRIBE en un histórico "
        "append-only, y lo que entra ahí no se borra." % culpables)


def test_el_modulo_que_escribe_pide_el_lector_de_afuera():
    """`reevaluar` no abre nada: se le pasa con qué leer y escribir.

    Un módulo que se conecta solo se puede llamar sin querer desde cualquier
    parte, y la única pista de contra qué base escribió es el `.env` que
    hubiera cargado. Recibirlo obliga a que quien lo llame diga contra qué.

    Y es lo que permite que la API use PostgREST y la consola el mismo
    PostgREST, sin que el cálculo sepa de drivers: en Vercel no hay psycopg, y
    no queremos credenciales de conexión directa en una función pública.
    """
    import inspect

    from motor.reevaluacion import reevaluar

    firma = inspect.signature(reevaluar).parameters
    assert "lector" in firma
    assert firma["lector"].default is inspect.Parameter.empty
    assert "conexion" not in firma


def test_la_suite_declara_que_corre_sin_red():
    """El contrato está escrito en el runner, y se comprueba que siga ahí."""
    with open(os.path.join(RAIZ, "tests", "correr_todo.py"),
              encoding="utf-8") as fh:
        doc = fh.read()
    assert "sin red" in doc.lower()


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
