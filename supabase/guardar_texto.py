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

import hashlib
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)

import psycopg  # noqa: E402

from motor.evaluar import VERSION_REGLAS  # noqa: E402
from motor.veredicto import puede_contactarse  # noqa: E402
from motor.verificar_texto import TextoRechazado, verificar_texto_generado  # noqa

TIPOS = ("narrativa", "lectura_contraste", "toque")


def hash_de_insumos(insumos) -> str:
    """El sha256 del extracto, canonicalizado.

    `sort_keys` porque dos dicts iguales con las claves en otro orden tienen que
    dar el mismo hash: si no, el hash mide el orden de iteracion y no el
    contenido, y una comparacion contra el extracto fallaria por nada.
    """
    return hashlib.sha256(
        json.dumps(insumos, sort_keys=True, ensure_ascii=False,
                   default=str).encode("utf-8")).hexdigest()


def guardar(*, realtor_id: str, tipo: str, texto: str, insumos: dict,
            modelo: str, evaluacion_id: str, afirma: bool | None = None,
            orden: int | None = None, extracto_vigente: dict | None = None,
            conexion=None,
            version_reglas: str = VERSION_REGLAS) -> dict:
    """Verifica y escribe. Levanta `TextoRechazado` si no pasa.

    Devuelve el veredicto completo, que es lo que queda guardado al lado del
    texto: no basta con que pasara, hay que poder ver CUANTAS cifras se
    comprobaron.

    `evaluacion_id` es OBLIGATORIO. Un texto sin evaluacion no se puede volver a
    comprobar: no hay contra que. Antes era opcional, asi que se podia guardar
    un texto verificado contra unos insumos que nadie podia relacionar con
    ningun diagnostico.

    `afirma` se DERIVA del extracto. Era `True` por omision, que es el valor
    mas peligroso: quien no pensara en el parametro obtenia permiso para
    afirmar.
    """
    if tipo not in TIPOS:
        raise TextoRechazado("tipo %r no es uno de %s" % (tipo, TIPOS))
    if tipo == "toque" and orden is None:
        raise TextoRechazado("un toque sin orden no se puede secuenciar")
    if not (evaluacion_id or "").strip():
        raise TextoRechazado(
            "sin evaluacion_id el texto no se puede volver a comprobar: no hay "
            "contra que. Es el unico dato que ata el texto a un diagnostico.")
    if not insumos:
        raise TextoRechazado(
            "sin insumos no se puede comprobar nada de lo que dice el texto. "
            "Es el campo que hace auditable todo lo demas.")

    # La MISMA compuerta que /api/dossier, /api/extracto y correr_motor. Un
    # texto para alguien excluido o pendiente no se guarda: verificarlo bien y
    # guardarlo igual seria haber comprobado con cuidado un mensaje que no
    # deberia existir.
    v_contacto = puede_contactarse(
        (insumos or {}).get("perfil_unido") or (insumos or {}).get("perfil"),
        capturado_en=(insumos or {}).get("capturado_en"),
        excluido_por_el_libro=(insumos or {}).get("excluido"),
        motivo_del_libro=(insumos or {}).get("excluido_motivo"))
    if not v_contacto.puede_escribirsele:
        raise TextoRechazado(
            "no se le escribe a esta persona: %s [%s]"
            % (v_contacto.motivo, v_contacto.estado))

    # Los insumos tienen que ser EL extracto de esa evaluacion, no unos insumos
    # parecidos. Verificar un texto contra material que no es el que se le dio
    # es la guarda que compara contra otra cosa -- y esa siempre aprueba.
    huella = hash_de_insumos(insumos)
    if extracto_vigente is not None:
        esperada = hash_de_insumos(extracto_vigente)
        if huella != esperada:
            raise TextoRechazado(
                "los insumos NO son el extracto de la evaluacion %s.\n"
                "  insumos recibidos: sha256 %s\n"
                "  extracto vigente : sha256 %s\n"
                "Verificar contra material distinto del que se uso para "
                "escribir no comprueba nada."
                % (evaluacion_id, huella[:16], esperada[:16]))

    v = verificar_texto_generado(texto, insumos, afirma=afirma)
    if not v.ok:
        raise TextoRechazado(
            "el texto NO se guarda.\n%s\n\nveredicto: %s"
            % (v.motivo, json.dumps(v.guardas, ensure_ascii=False)[:400]))

    veredicto = {"ok": True, "guardas": v.guardas,
                 "cifras_comprobadas": v.cifras_comprobadas,
                 # El hash viaja DENTRO del veredicto: asi queda en la misma
                 # fila que el texto y se puede recomprobar despues que los
                 # insumos son los que se verificaron.
                 "hash_insumos": huella,
                 "afirma": bool(v.afirma) if hasattr(v, "afirma") else None}

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
