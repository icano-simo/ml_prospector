"""Vuelca el catalogo de reglas a filas, para cargarlas en `reglas`.

Por que existe. Si las reglas viven en Python y ademas en una tabla, hay dos
fuentes de verdad y se desincronizan en silencio. Aca el Python manda y la
tabla es una proyeccion: este modulo la genera, nunca al reves.

No se conecta a Supabase. Emite el INSERT y las filas; quien tenga credenciales
lo aplica. Asi corre en cualquier maquina y en las pruebas.
"""
from __future__ import annotations

import json

from motor.evaluar import VERSION_REGLAS, huella_del_catalogo
from motor.reglas import REGLAS


def filas() -> list[dict]:
    """Una fila por regla, con los mismos nombres que la tabla."""
    return [
        {
            "id": r.id,
            "qualifier": r.qualifier,
            "familia": r.familia,
            "intensidad": r.intensidad,
            "grado": r.grado,
            "texto": r.texto,
            "campos": list(r.campos),
            "origen": r.origen,
            "referencia": r.referencia,
            "discrepancia": r.discrepancia,
            "gancho": r.gancho,
            "version": VERSION_REGLAS,
            "activa": True,
        }
        for r in REGLAS
    ]


def _sql_literal(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "array[%s]" % ", ".join(_sql_literal(x) for x in v)
    return "'%s'" % str(v).replace("'", "''")


def a_sql() -> str:
    """Un upsert idempotente. Se puede correr dos veces sin duplicar.

    Las reglas que ya no existen en el catalogo se marcan `activa = false` en
    vez de borrarse: una evaluacion vieja apunta a su id y tiene que poder
    resolverlo.
    """
    cols = ["id", "qualifier", "familia", "intensidad", "grado", "texto",
            "campos", "origen", "referencia", "discrepancia", "gancho",
            "version", "activa"]
    valores = [
        "  (%s)" % ", ".join(_sql_literal(f[c]) for c in cols)
        for f in filas()
    ]
    actualiza = ", ".join(
        "%s = excluded.%s" % (c, c) for c in cols if c != "id"
    )
    ids = ", ".join(_sql_literal(r.id) for r in REGLAS)
    return "\n".join([
        "-- Generado por motor/sincronizar_reglas.py. No editar a mano:",
        "-- el catalogo de Python es la fuente de verdad y esto es su proyeccion.",
        "-- version: %s" % VERSION_REGLAS,
        "-- huella:  %s" % huella_del_catalogo(),
        "",
        "insert into reglas (%s) values" % ", ".join(cols),
        ",\n".join(valores),
        "on conflict (id) do update set %s;" % actualiza,
        "",
        "-- Lo que ya no esta en el catalogo se desactiva, no se borra: una",
        "-- evaluacion vieja apunta a su id y tiene que poder resolverlo.",
        "update reglas set activa = false where id not in (%s);" % ids,
    ])


def a_json() -> str:
    return json.dumps(filas(), ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(a_sql())
