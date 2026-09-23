"""Guarda un texto generado por un modelo, SOLO si pasa las cinco guardas.

    from supabase.guardar_texto import guardar
    guardar(realtor_id=..., tipo="narrativa", texto=..., insumos={...},
            modelo="claude-opus-5", afirma=False)

Por que existe un modulo y no un INSERT a mano
----------------------------------------------
Las guardas corren en Python y la base no puede correrlas. Un INSERT directo
salta la verificacion entera, asi que el camino de escritura tiene que ser
este -- y la tabla exige `verificacion` no nulo justamente para que un insert
sin pasar por aca se note.

Lo que la base SI puede hacer, y hace: exigir que `insumos` y `verificacion`
existan y no vengan vacios. Un texto sin insumos es un texto que nadie puede
comprobar.
"""
from __future__ import annotations

import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)

import psycopg  # noqa: E402

from motor.evaluar import VERSION_REGLAS  # noqa: E402
from motor.verificar_texto import TextoRechazado, verificar_texto_generado  # noqa

TIPOS = ("narrativa", "lectura_contraste", "toque")


def guardar(*, realtor_id: str, tipo: str, texto: str, insumos: dict,
            modelo: str, afirma: bool = True, orden: int | None = None,
            evaluacion_id: str | None = None, conexion=None,
            version_reglas: str = VERSION_REGLAS) -> dict:
    """Verifica y escribe. Levanta `TextoRechazado` si no pasa.

    Devuelve el veredicto completo, que es lo que queda guardado al lado del
    texto: no basta con que pasara, hay que poder ver CUANTAS cifras se
    comprobaron.
    """
    if tipo not in TIPOS:
        raise TextoRechazado("tipo %r no es uno de %s" % (tipo, TIPOS))
    if tipo == "toque" and orden is None:
        raise TextoRechazado("un toque sin orden no se puede secuenciar")
    if not insumos:
        raise TextoRechazado(
            "sin insumos no se puede comprobar nada de lo que dice el texto. "
            "Es el campo que hace auditable todo lo demas.")

    v = verificar_texto_generado(texto, insumos, afirma=afirma)
    if not v.ok:
        raise TextoRechazado(
            "el texto NO se guarda.\n%s\n\nveredicto: %s"
            % (v.motivo, json.dumps(v.guardas, ensure_ascii=False)[:400]))

    veredicto = {"ok": True, "guardas": v.guardas,
                 "cifras_comprobadas": v.cifras_comprobadas}

    propia = conexion is None
    con = conexion or psycopg.connect(os.environ["SUPABASE_DB_URL"])
    try:
        with con.cursor() as cur:
            cur.execute("""
                insert into pacs.textos_generados
                    (realtor_id, evaluacion_id, tipo, orden, texto, modelo,
                     version_reglas, insumos, verificacion)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                returning id
            """, (realtor_id, evaluacion_id, tipo, orden, texto, modelo,
                  version_reglas, json.dumps(insumos, ensure_ascii=False),
                  json.dumps(veredicto, ensure_ascii=False)))
            nuevo = cur.fetchone()[0]
        con.commit()
    finally:
        if propia:
            con.close()
    return {"id": str(nuevo), **veredicto}
