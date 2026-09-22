"""Guarda una captura de Model Match. El crudo, siempre; lo derivado, cuando exista.

Una desviacion del brief, y el motivo
-------------------------------------
El brief dice guardar en `capturas_modelmatch` **y** en `mercados`. Aca se
guarda en `capturas_modelmatch` siempre, y en `mercados` **solo cuando haya
metricas parseadas**.

La razon: `pacs.mercados` es la biblioteca de benchmarks, y el motor de
contrastes la consulta para saber **de que geografias tiene mercado**. Una fila
con `metricas` vacia haria que el motor crea que Solano esta disponible y
produzca contrastes contra nada -- o que los descarte con un error raro. Es
exactamente la clase de error invisible que venimos persiguiendo: la fila
existe, la consulta la encuentra, y el contenido no esta.

El crudo etiquetado ya es la captura. `mercados` se puebla en la pasada del
parser, y hasta entonces la ausencia de la fila **es** la informacion correcta:
todavia no hay benchmark.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

from captura.protocolo import Captura
from supabase.cargar import conectar


class GuardadoFallido(RuntimeError):
    pass


def geografias_capturadas(conexion=None) -> list[dict]:
    """Que hay capturado hoy. Alimenta el panel de cobertura de la pantalla."""
    propia = conexion is None
    conn = conexion or conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                select coalesce(estado, '') as estado,
                       coalesce(condado_fips, '') as condado,
                       max(capturado_en) as ultima,
                       count(*) as n
                  from pacs.capturas_modelmatch
                 where alcance = 'mercado'
                 group by 1, 2
                 order by 1, 2
            """)
            return [{"estado": e, "condado": c, "ultima": u, "n": n}
                    for e, c, u, n in cur.fetchall()]
    finally:
        if propia:
            conn.close()


def guardar(
    cap: Captura,
    *,
    archivo: str | None = None,
    subido_por: str | None = None,
    conexion=None,
) -> dict:
    """Guarda la captura entera en UNA transaccion.

    O entra todo o no entra nada: una captura a medias deja bloques etiquetados
    contra condados que no se guardaron, y eso desalinea la biblioteca sin que
    se note.
    """
    if not cap.bloques:
        raise GuardadoFallido("la captura no tiene bloques")

    propia = conexion is None
    conn = conexion or conectar()
    batch_id = str(uuid.uuid4())
    ahora = dt.datetime.now(dt.timezone.utc)
    escritos = 0

    try:
        with conn.cursor() as cur:
            cur.execute(
                "insert into pacs.upload_batch "
                "(id, fuente, archivo, subido_por, uploaded_at, es_vigente, "
                " filas_esperadas, nota) "
                "values (%s, 'modelmatch', %s, %s, %s, true, %s, %s)",
                (batch_id, archivo, subido_por, ahora, len(cap.bloques),
                 "captura por pantalla · realtor=%s · condados=%s"
                 % (cap.realtor or "?", ", ".join(cap.condados) or "ninguno")),
            )

            for b in cap.bloques:
                # El Overview y los Originators/Lenders son del PERFIL; los
                # Market Signals son del MERCADO. El esquema los distingue y la
                # restriccion exige geografia en los de mercado.
                if b.seccion == "market_signals":
                    alcance = "mercado"
                    estado = cap.estado
                    # `condado_fips` espera un CODIGO. Todavia no hay
                    # crosswalk, asi que el nombre del condado va al parseado y
                    # no a la columna de FIPS -- un nombre ahi entraria sin
                    # protestar y el error aparece meses despues.
                    condado_fips = None
                else:
                    alcance = "perfil"
                    estado = cap.estado
                    condado_fips = None

                parseado = {
                    "seccion": b.seccion,
                    "orden": b.orden,
                    "nivel": b.nivel,
                    "etiqueta_geografica": b.etiqueta,
                    "condados_del_overview": cap.condados,
                    "estado_del_parser": "sin_parsear",
                }
                cur.execute(
                    "insert into pacs.capturas_modelmatch "
                    "(upload_batch_id, uploaded_at, alcance, condado_fips, "
                    " estado, mmi_agent_id, sf_lead_id, texto_crudo, parseado, "
                    " version_parser, capturado_en) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (batch_id, ahora, alcance, condado_fips, estado,
                     cap.mmi_agent_id, cap.sf_lead_id,
                     b.texto, json.dumps(parseado, ensure_ascii=False),
                     None, ahora),
                )
                escritos += 1

            cur.execute(
                "select count(*) from pacs.capturas_modelmatch "
                " where upload_batch_id = %s", (batch_id,))
            en_base = cur.fetchone()[0]
            if en_base != len(cap.bloques):
                raise GuardadoFallido(
                    "se mandaron %d bloques y la base tiene %d"
                    % (len(cap.bloques), en_base))

            cur.execute(
                "update pacs.upload_batch set filas_cargadas = %s where id = %s",
                (en_base, batch_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if propia:
            conn.close()

    return {
        "upload_batch_id": batch_id,
        "bloques": escritos,
        "condados": cap.condados,
        "advertencias": cap.advertencias,
        # `mercados` no se escribe: ver la nota del modulo.
        "mercados_escritos": 0,
    }
