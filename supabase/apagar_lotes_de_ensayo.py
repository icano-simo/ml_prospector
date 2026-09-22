"""Apaga los lotes que fueron ENSAYOS, por la via disenada: `es_vigente`.

    python supabase/apagar_lotes_de_ensayo.py            # solo clasifica
    python supabase/apagar_lotes_de_ensayo.py --aplicar

Sin DELETE. `pacs.upload_batch.es_vigente` es exactamente el mecanismo para
esto y `v_capturas_modelmatch_current` ya lee por ahi: apagar el lote saca sus
filas de toda consulta sin perder el crudo ni la fecha.

Por que hace falta
------------------
Seis capturas de prueba mias y una real convivian en la misma tabla sin nada
que las distinguiera. Leyendo la tabla con un filtro razonable -- los bloques
mas grandes-- se llega a las de prueba, porque el payload de ensayo era el mas
grande de todos. De ahi salio un diagnostico entero sobre datos inventados.

La clasificacion va por EVIDENCIA en el texto, no por fecha ni por tamano, y se
imprime entera antes de escribir nada.
"""
from __future__ import annotations

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import psycopg  # noqa: E402

from supabase.config import cargar_env  # noqa: E402

#: Marcas que SOLO aparecen en los payloads de ensayo. Cada una es literal del
#: generador: `TOP PRODUCER` y `Peñasco ...` son el relleno del ensayo de
#: 49.392 caracteres, y `ZZMARCA_` marcaba cada seccion en las pruebas de corte.
MARCAS_DE_ENSAYO = ("TOP PRODUCER", "Peñasco", "ZZMARCA_")

#: Por debajo de esto un bloque no es una pestaña de Model Match: es un stub.
#: El Overview real mas chico que vimos mide 2.252 caracteres.
UMBRAL_STUB = 500

#: La marca va en la nota del lote, no en una tabla aparte: es el unico sitio
#: donde la va a ver quien lea la tabla directamente, que es justo como se
#: llego a analizar los payloads de ensayo creyendo que eran capturas.
MARCA = "[ENSAYO]"
NOTA = (MARCA + " payload de prueba, NO es una captura de Model Match. "
        "clase=%s (%s). Apagado con es_vigente=false el %s.")


def clasificar(bloques: list[tuple[str, int]]) -> tuple[str, str]:
    """(clase, evidencia). Las clases son 'ensayo', 'stub' y 'real'."""
    for texto, _n in bloques:
        for marca in MARCAS_DE_ENSAYO:
            if marca in texto:
                return "ensayo", "contiene %r" % marca
    mayor = max((n for _t, n in bloques), default=0)
    if mayor < UMBRAL_STUB:
        return "stub", "el bloque mayor mide %d caracteres" % mayor
    return "real", "sin marcas de ensayo; bloque mayor de %d caracteres" % mayor


def main(aplicar: bool) -> int:
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL")
        return 1
    import datetime as dt
    hoy = dt.date.today().isoformat()

    with psycopg.connect(url) as con:
        cur = con.cursor()
        cur.execute("""
            select b.id, b.uploaded_at, b.es_vigente, b.nota,
                   c.texto_crudo, length(c.texto_crudo)
              from pacs.upload_batch b
              join pacs.capturas_modelmatch c on c.upload_batch_id = b.id
             where b.fuente = 'modelmatch'
             order by b.uploaded_at
        """)
        por_lote: dict = {}
        for lid, cuando, vigente, nota, texto, n in cur.fetchall():
            e = por_lote.setdefault(lid, {"cuando": cuando, "vigente": vigente,
                                          "nota": nota, "bloques": []})
            e["bloques"].append((texto, n))

        print("CLASIFICACION POR EVIDENCIA EN EL TEXTO")
        print("%-20s %-7s %5s %7s  %-8s %s"
              % ("uploaded_at", "vigente", "filas", "chars", "clase",
                 "evidencia"))
        apagar = []
        for lid, e in sorted(por_lote.items(), key=lambda kv: kv[1]["cuando"]):
            clase, evidencia = clasificar(e["bloques"])
            total = sum(n for _t, n in e["bloques"])
            print("%-20s %-7s %5d %7d  %-8s %s"
                  % (str(e["cuando"])[:19], e["vigente"], len(e["bloques"]),
                     total, clase, evidencia))
            # Se toca tambien un lote que YA esta apagado si le falta la marca:
            # `es_vigente=false` dice "no cuenta" y no dice POR QUE. Los seis de
            # ensayo ya estaban apagados y aun asi se analizaron como reales,
            # porque nada en la fila decia que eran pruebas.
            falta_marca = MARCA not in (e["nota"] or "")
            if clase in ("ensayo", "stub") and (e["vigente"] or falta_marca):
                apagar.append((lid, clase, evidencia, len(e["bloques"]),
                               e["vigente"], falta_marca))

        quedan = [e for lid, e in por_lote.items()
                  if clasificar(e["bloques"])[0] == "real"]
        print("")
        print("a marcar : %d lotes, %d filas  (%d hay que apagar, %d solo "
              "les falta la marca)"
              % (len(apagar), sum(c[3] for c in apagar),
                 sum(1 for c in apagar if c[4]),
                 sum(1 for c in apagar if not c[4] and c[5])))
        print("quedan   : %d lotes reales, %d filas"
              % (len(quedan), sum(len(e["bloques"]) for e in quedan)))

        # Guarda redundante a proposito: esto no puede vaciar la tabla viva.
        if not quedan:
            print("\nABORTADO: no quedaria ningun lote vigente. No se escribe "
                  "nada: apagarlos todos deja la biblioteca en cero y eso no "
                  "es lo que se pidio nunca.")
            return 1
        if not apagar:
            print("\nno hay nada que apagar")
            return 0

        if not aplicar:
            print("\n(solo clasifica; pasar --aplicar para escribir)")
            return 0

        for lid, clase, evidencia, _n, _viv, _falta in apagar:
            cur.execute("""
                update pacs.upload_batch
                   set es_vigente = false,
                       nota = coalesce(nota || ' | ', '') || %s
                 where id = %s and position(%s in coalesce(nota, '')) = 0
            """, (NOTA % (clase, evidencia, hoy), lid, MARCA))
        con.commit()

        # El DESPUES, leido de la base y no del script.
        cur.execute("""
            select count(*) from pacs.capturas_modelmatch
        """)
        todas = cur.fetchone()[0]
        cur.execute("""
            select count(*) from pacs.v_capturas_modelmatch_current
        """)
        vivas = cur.fetchone()[0]
        print("\nDESPUES, leido de la base")
        print("   pacs.capturas_modelmatch          : %d filas (el historico "
              "no se toca)" % todas)
        print("   v_capturas_modelmatch_current     : %d filas" % vivas)
        cur.execute("""
            select uploaded_at, es_vigente, nota
              from pacs.upload_batch
             where fuente = 'modelmatch'
             order by uploaded_at
        """)
        for cuando, vigente, nota in cur.fetchall():
            print("   %-20s vigente=%-5s %s"
                  % (str(cuando)[:19], vigente, (nota or "")[:70]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--aplicar" in sys.argv))
