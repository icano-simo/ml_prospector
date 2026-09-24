"""La re-evaluación al guardar, en el entorno de Vercel.

Lo que pasó: la captura de Abby Grimaldi guardó bien y el diagnóstico no se
recalculó — «Falta el driver. Instalalo con:.». `reevaluar` usaba psycopg y
conexión directa, y Vercel no tiene ninguna de las dos (ni debe: serían
credenciales de base en una función pública).

Y había un SEGUNDO bloqueo que el primero tapaba: leía el libro v3 con pandas,
y `Data_inputIA/` está en `.gitignore`, así que el Excel no viaja al deploy.
Aunque psycopg hubiera estado, esto habría fallado igual una línea después.

La prueba de antes pasó solo porque esta máquina sí tiene psycopg. Acá se
simula que NO está.
"""
from __future__ import annotations

import builtins
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.reevaluacion import (  # noqa: E402
    NoSePudoReevaluar,
    base_del_libro,
    reevaluar,
)


class LectorFalso:
    """Un `lector` en memoria. Registra lo que se escribió."""

    def __init__(self, tablas: dict):
        self.tablas = tablas
        self.escrito: list = []

    def leer(self, tabla, consulta="", **kw):
        return 200, list(self.tablas.get(tabla, [])), {}

    def escribir(self, tabla, filas, **kw):
        self.escrito.append((tabla, filas))
        return 201, [], {}


ENTRADA_ANTERIOR = {
    "ev2_fha_gob": True, "ev2_primera_casa": True, "R5_espanol": 7.0,
    "unidades_ano": 18, "ig_seguidores": 900.0,
    "mm_buyside_anualizado": 3.0,
}

PERFIL_MM = {
    "buyer_units": 18.0,
    "buyside_anualizado": 15.4,
    "orig_buyer": [
        {"nombre": "Originador A", "empresa": "Chase Home Lending",
         "unidades": 5, "share": 71.0},
        {"nombre": "Originador B", "empresa": "Guild Mortgage",
         "unidades": 2, "share": 29.0}],
}


def _lector(perfil=PERFIL_MM, entrada=None):
    return LectorFalso({
        "v_evaluacion_actual": [{
            "entrada": dict(entrada or ENTRADA_ANTERIOR),
            "dolor_primario": "P-Q06", "excluido": None,
            "excluido_motivo": None,
            "veredicto_contacto": {"estado": "pendiente_modelmatch"}}],
        "v_ig_senales_current": [],
        "v_ig_clase_actual": [],
        "v_capturas_modelmatch_current": (
            [{"parseado": {"perfil": perfil}, "capturado_en": "2026-09-23"}]
            if perfil else []),
    })


# ══ EL ENTORNO DE VERCEL ═════════════════════════════════════════════════════

def test_reevalua_sin_psycopg_instalado():
    """El caso de producción: no hay driver y la re-evaluación funciona igual.

    La prueba anterior pasaba porque esta máquina tiene psycopg. Acá se hace
    que importarlo FALLE, como en Vercel.
    """
    real = builtins.__import__

    def sin_psycopg(nombre, *a, **kw):
        if nombre == "psycopg" or nombre.startswith("psycopg."):
            raise ImportError("No module named 'psycopg'")
        return real(nombre, *a, **kw)

    lector = _lector()
    builtins.__import__ = sin_psycopg
    try:
        r = reevaluar("r-1", lector=lector)
    finally:
        builtins.__import__ = real

    assert lector.escrito, "no escribió la evaluación"
    assert r["veredicto_ahora"] == "ok"
    assert r["mm_buyside_anualizado"] == 15.4


def test_reevalua_sin_pandas_y_sin_el_libro():
    """El segundo bloqueo: el Excel no viaja al deploy.

    La evidencia del libro sale de la `entrada` anterior, que ya está en la
    base. El libro no cambia entre corridas.
    """
    real = builtins.__import__

    def sin_pandas(nombre, *a, **kw):
        if nombre == "pandas":
            raise ImportError("No module named 'pandas'")
        return real(nombre, *a, **kw)

    builtins.__import__ = sin_pandas
    try:
        r = reevaluar("r-1", lector=_lector())
    finally:
        builtins.__import__ = real
    assert r["veredicto_ahora"] == "ok"


def test_el_modulo_del_motor_no_importa_psycopg():
    """Ni siquiera de forma perezosa: no hay una rama que lo intente.

    Se miran los IMPORTS del árbol sintáctico, no el texto del archivo: el
    docstring nombra psycopg para explicar por qué no está, y buscar la palabra
    acusaba a la explicación.
    """
    import ast
    import inspect

    import motor.reevaluacion as m

    arbol = ast.parse(inspect.getsource(m))
    importados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados |= {a.name.split(".")[0] for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module.split(".")[0])
    assert "psycopg" not in importados, importados
    # Y tampoco llama a `conectar()`, que es la otra vía a una conexión directa.
    assert "conectar(" not in inspect.getsource(m)


def test_la_evidencia_del_libro_se_hereda_sin_tocar_el_excel():
    base = base_del_libro(ENTRADA_ANTERIOR)
    assert base["ev2_fha_gob"] is True
    assert base["R5_espanol"] == 7.0
    # Lo que se recalcula NO se hereda: heredarlo dejaria el valor viejo si la
    # captura nueva no lo trae.
    assert "mm_buyside_anualizado" not in base
    assert "mm_share_buy" not in base
    # `ig_seguidores` SI se hereda desde el 2026-09-23. El libro v3 trae la
    # columna y en la corrida completa el libro gana --decisión de Isabella,
    # sin cambios-- así que borrarlo aquí le quitaba los seguidores a todo el
    # que no tiene muro leído, y las reglas que los leen pasaban a «no
    # evaluada». Las dos vías tienen que decir lo mismo.
    assert base["ig_seguidores"] == ENTRADA_ANTERIOR["ig_seguidores"]


def test_la_simulacion_no_escribe_nada_y_calcula_igual():
    """`--simular` mide el impacto de un cambio de reglas sin desplegarlo.

    Una simulación que igual escribe es peor que no tenerla: deja en producción
    evaluaciones de una versión que la pantalla todavía no corre, y ahí salen
    marcadas como «de una versión anterior» siendo las más nuevas.

    Y tiene que calcular lo MISMO: si la simulación tomara otro camino, estaría
    midiendo el otro camino.
    """
    seco = _lector()
    r = reevaluar("r-1", lector=seco, guardar=False)
    assert seco.escrito == [], seco.escrito
    assert r["guardado"] is False

    mojado = _lector()
    r2 = reevaluar("r-1", lector=mojado, guardar=True)
    assert len(mojado.escrito) == 1
    assert r2["guardado"] is True
    # El mismo resultado por los dos caminos, salvo la marca de si guardó.
    assert {k: v for k, v in r.items() if k != "guardado"} == {
        k: v for k, v in r2.items() if k != "guardado"}


def test_sin_evaluacion_anterior_se_dice_que_hacer():
    vacio = LectorFalso({"v_evaluacion_actual": []})
    try:
        reevaluar("r-1", lector=vacio)
    except NoSePudoReevaluar as exc:
        assert "motor completo" in str(exc)
        return
    raise AssertionError("re-evaluó sin evaluación anterior")


def test_el_mensaje_del_driver_no_se_corta():
    """El aviso decía «Falta el driver. Instalalo con:» y ahí terminaba.

    `split("\\n")[0]` tiraba justo la mitad accionable. Ahora el detalle
    técnico viaja entero, en una línea.
    """
    import inspect

    from supabase import cargar

    # Se lee el texto del mensaje, NO se abre nada: llamar a la función que
    # conecta, en una máquina con el driver instalado, sale a la base real --
    # que es lo que la guarda de `test_sin_produccion` prohíbe, y que cazó a
    # esta misma prueba en su primera versión.
    fuente = inspect.getsource(cargar.conectar)
    assert "Falta el driver" in fuente
    assert "pip install" in fuente

    # Y el aviso de la ruta no puede partir el mensaje por la primera línea:
    # ahí se perdía la mitad accionable.
    with open(os.path.join(RAIZ, "api", "rutas.py"), encoding="utf-8") as fh:
        rutas = fh.read()
    bloque = rutas.split("La captura se guardó. El diagnóstico")[1][:400]
    assert 'split("\\n")[0]' not in bloque


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
