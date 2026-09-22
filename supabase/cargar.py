"""Carga por conexion directa a Postgres. Sin PostgREST.

Por que directo y no por PostgREST
----------------------------------
Exponer `pacs` en `pgrst.db_schemas` para habilitar un cargador batch es riesgo
a cambio de nada: esa lista se reescribe entera y su modo de fallo es PERDER uno
de los trece esquemas, no dejar de agregar el nuevo. La exposicion se hace
cuando el front la necesite.

Efecto lateral util: sin PostgREST tampoco aplica el `statement_timeout = 8s`
del rol `authenticator`. Los lotes de 500 se conservan igual, por poder
reanudar: si el lote 6 de 9 falla, los cinco anteriores ya estan y el
`upload_batch` dice hasta donde llego.

El patron append-only, en el cargador
-------------------------------------
Cada carga abre un `upload_batch`. Las filas se insertan apuntando a el. Al
terminar bien, el lote anterior de esa fuente se apaga y el nuevo queda vigente
-- en esa transaccion, no antes. Si la carga falla a la mitad, el lote nuevo
queda con `es_vigente = false` y las vistas `v_*_current` siguen devolviendo el
anterior: **una carga a medias no se ve nunca.**
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import uuid
from dataclasses import dataclass

from supabase.config import credenciales

#: Filas por lote. Sin PostgREST no hay timeout de 8 s, pero un lote grande que
#: falla obliga a repetir todo.
TAMANO_LOTE = 500


class CargaFallida(RuntimeError):
    pass


@dataclass
class Resultado:
    upload_batch_id: str
    fuente: str
    filas_esperadas: int
    filas_cargadas: int
    lotes: int
    vigente_anterior: str | None

    def __str__(self) -> str:
        return ("%s · %d de %d filas en %d lotes · batch %s"
                % (self.fuente, self.filas_cargadas, self.filas_esperadas,
                   self.lotes, self.upload_batch_id))


def conectar():
    """Una conexion directa. Falla con el mensaje de donde sacar la cadena."""
    try:
        import psycopg
    except ImportError:
        raise CargaFallida(
            "Falta el driver. Instalalo con:\n"
            "    python -m pip install \"psycopg[binary]\""
        ) from None

    cred = credenciales(exigir_db=True)
    # `sslmode=require`: Supabase lo exige y sin esto el error es de red, que
    # manda a mirar el lugar equivocado.
    return psycopg.connect(cred.db_url, sslmode="require", autocommit=False)


def _columnas_de(filas: list[dict]) -> list[str]:
    """Las columnas de la primera fila. Todas las filas tienen que coincidir.

    Se verifica en vez de suponer: una fila con una clave de mas se insertaria
    con esa columna en NULL y nadie lo notaria hasta leerla.
    """
    if not filas:
        return []
    cols = list(filas[0])
    esperado = set(cols)
    for i, f in enumerate(filas[1:], 1):
        if set(f) != esperado:
            faltan = esperado - set(f)
            sobran = set(f) - esperado
            raise CargaFallida(
                "la fila %d no tiene las mismas columnas que la primera. "
                "faltan=%s sobran=%s" % (i, sorted(faltan), sorted(sobran))
            )
    return cols


def cargar(
    tabla: str,
    filas: list[dict],
    *,
    fuente: str,
    archivo: str | None = None,
    nota: str | None = None,
    tamano_lote: int = TAMANO_LOTE,
    conexion=None,
) -> Resultado:
    """Inserta `filas` en `pacs.<tabla>` bajo un lote nuevo.

    `filas` son dicts con las columnas de la tabla, SIN `upload_batch_id`: lo
    pone el cargador.
    """
    if not filas:
        raise CargaFallida("no hay filas que cargar")

    cols = _columnas_de(filas)
    if "upload_batch_id" in cols:
        raise CargaFallida(
            "las filas no llevan upload_batch_id: lo pone el cargador, y que "
            "venga de afuera permite escribir en un lote ajeno"
        )

    propia = conexion is None
    conn = conexion or conectar()
    batch_id = str(uuid.uuid4())
    cargadas = 0
    n_lotes = 0
    anterior = None

    try:
        with conn.cursor() as cur:
            # 1 · el lote, apagado. Se enciende al final.
            cur.execute(
                "insert into pacs.upload_batch "
                "(id, fuente, archivo, uploaded_at, es_vigente, "
                " filas_esperadas, nota) "
                "values (%s, %s, %s, %s, false, %s, %s)",
                (batch_id, fuente, archivo,
                 dt.datetime.now(dt.timezone.utc), len(filas), nota),
            )

            # 2 · las filas, en lotes.
            plantilla = "insert into pacs.%s (%s, upload_batch_id) values (%s)" % (
                tabla,
                ", ".join('"%s"' % c for c in cols),
                ", ".join(["%s"] * (len(cols) + 1)),
            )
            for i in range(0, len(filas), tamano_lote):
                trozo = filas[i:i + tamano_lote]
                datos = [
                    tuple(
                        json.dumps(f[c], ensure_ascii=False)
                        if isinstance(f[c], (dict, list)) else f[c]
                        for c in cols
                    ) + (batch_id,)
                    for f in trozo
                ]
                cur.executemany(plantilla, datos)
                cargadas += len(trozo)
                n_lotes += 1

            # 3 · verificar contando en la BASE, no en Python.
            cur.execute(
                "select count(*) from pacs.%s where upload_batch_id = %%s" % tabla,
                (batch_id,),
            )
            en_base = cur.fetchone()[0]
            if en_base != len(filas):
                raise CargaFallida(
                    "se mandaron %d filas y la base tiene %d. No enciendo el "
                    "lote." % (len(filas), en_base)
                )

            # 4 · recien ahora: apagar el anterior y encender este.
            cur.execute(
                "select id from pacs.upload_batch "
                "where fuente = %s and es_vigente and id <> %s",
                (fuente, batch_id),
            )
            previos = [str(r[0]) for r in cur.fetchall()]
            anterior = previos[0] if previos else None

            cur.execute(
                "update pacs.upload_batch set es_vigente = false "
                "where fuente = %s and id <> %s",
                (fuente, batch_id),
            )
            cur.execute(
                "update pacs.upload_batch "
                "set es_vigente = true, filas_cargadas = %s where id = %s",
                (en_base, batch_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if propia:
            conn.close()

    return Resultado(batch_id, fuente, len(filas), cargadas, n_lotes, anterior)


def volver_al_anterior(fuente: str, *, conexion=None) -> str | None:
    """Apaga el lote vigente y enciende el inmediatamente anterior.

    Es lo que hace que una captura mala no cueste un backup: una fila cambia y
    las vistas `v_*_current` vuelven a la version buena.
    """
    propia = conexion is None
    conn = conexion or conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select id from pacs.upload_batch where fuente = %s "
                "order by uploaded_at desc limit 2",
                (fuente,),
            )
            filas = cur.fetchall()
            if len(filas) < 2:
                raise CargaFallida(
                    "no hay lote anterior de %r al cual volver" % fuente
                )
            actual, previo = str(filas[0][0]), str(filas[1][0])
            cur.execute("update pacs.upload_batch set es_vigente = false "
                        "where id = %s", (actual,))
            cur.execute("update pacs.upload_batch set es_vigente = true "
                        "where id = %s", (previo,))
        conn.commit()
        return previo
    except Exception:
        conn.rollback()
        raise
    finally:
        if propia:
            conn.close()


def estado(conexion=None) -> list[dict]:
    """Que hay cargado hoy, por fuente. Solo lectura."""
    propia = conexion is None
    conn = conexion or conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select fuente, id, uploaded_at, es_vigente, "
                "       filas_esperadas, filas_cargadas "
                "  from pacs.upload_batch order by fuente, uploaded_at desc"
            )
            return [
                {"fuente": r[0], "id": str(r[1]), "uploaded_at": r[2],
                 "es_vigente": r[3], "esperadas": r[4], "cargadas": r[5]}
                for r in cur.fetchall()
            ]
    finally:
        if propia:
            conn.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for fila in estado():
        print("%-12s %s  vigente=%-5s %s/%s"
              % (fila["fuente"], fila["uploaded_at"], fila["es_vigente"],
                 fila["cargadas"], fila["esperadas"]))
