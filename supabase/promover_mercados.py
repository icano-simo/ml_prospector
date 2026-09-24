"""Promueve a `pacs.mercados` las capturas que ya estaban guardadas.

    python supabase/promover_mercados.py            # solo reporta
    python supabase/promover_mercados.py --aplicar

Existe SOLO para lo que se capturo antes de que la promocion corriera dentro
del guardado. De ahora en adelante no hace falta: `api.rutas.guardar` promueve
en la misma peticion, y un bloque con metricas que no llega a la biblioteca es
un fallo declarado.

Un paso aparte es un paso que alguien tiene que acordarse de correr, y mientras
no corre no falla nada. Por eso este script es de una vez y no de rutina.

Usa la MISMA funcion que el endpoint -- `promover_a_mercados`-- para que el
backfill y la via viva no puedan divergir.
"""
from __future__ import annotations

import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))

import psycopg  # noqa: E402

from api.rutas import promover_a_mercados  # noqa: E402
from supabase.config import cargar_env  # noqa: E402


def main(aplicar: bool) -> int:
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL")
        return 1

    with psycopg.connect(url) as con:
        cur = con.cursor()
        cur.execute("select count(*) from pacs.mercados")
        print("pacs.mercados antes: %d filas" % cur.fetchone()[0])

        # Solo los lotes VIVOS: los ensayos estan apagados y no deben entrar en
        # la biblioteca de benchmarks.
        cur.execute("""
            select c.upload_batch_id, c.estado, c.geografia_etiqueta,
                   c.geografia_nivel, c.parseado, c.capturado_en
              from pacs.v_capturas_modelmatch_current c
             where c.alcance = 'mercado'
             order by c.capturado_en, c.parseado->>'orden'
        """)
        por_lote: dict = {}
        for lote, estado, etiqueta, nivel, parseado, cuando in cur.fetchall():
            p = dict(parseado or {})
            # La COLUMNA manda sobre el jsonb, igual que en /api/capturas.
            if etiqueta is not None:
                p["etiqueta_geografica"] = etiqueta
            if nivel is not None:
                p["nivel"] = nivel
            por_lote.setdefault(lote, {"cuando": cuando, "filas": []})
            por_lote[lote]["filas"].append({"parseado": p, "estado": estado,
                                            "texto_crudo": ""})

        # Lo que YA esta promovido, para no duplicar. POR GEOGRAFIA y no por
        # lote: la version anterior saltaba el lote entero en cuanto tuviera
        # una fila, y una promocion PARCIAL --el bloque del estado entro, el de
        # DuPage no porque su FIPS no resolvia-- quedaba imposible de
        # completar. El backfill decia «ya promovido» sobre un lote al que le
        # faltaban 44 metricas.
        cur.execute("""
            select upload_batch_id, nivel, coalesce(estado, ''),
                   coalesce(condado_fips, '')
              from pacs.mercados
        """)
        ya = {(str(a), b, c, d) for a, b, c, d in cur.fetchall()}

        total, fallos_todos = [], []
        for lote, datos in por_lote.items():
            ahora = datos["cuando"].isoformat()
            mercados, fallos = promover_a_mercados(datos["filas"], str(lote),
                                                   ahora)
            antes = len(mercados)
            mercados = [m for m in mercados
                        if (str(lote), m["nivel"], m["estado"] or "",
                            m["condado_fips"] or "") not in ya]
            if antes and not mercados and not fallos:
                print("   %s · sus %d geografias ya estan promovidas"
                      % (str(lote)[:8], antes))
                continue
            print("   %s · %d bloques -> %d filas de mercado%s"
                  % (str(lote)[:8], len(datos["filas"]), len(mercados),
                     "  FALLOS: %d" % len(fallos) if fallos else ""))
            for m in mercados:
                print("      %-8s %-14s fips=%-6s %d metricas"
                      % (m["nivel"], m["estado"] or "-",
                         m["condado_fips"] or "-",
                         m["metricas"].get("campos") or 0))
            for f in fallos:
                print("      FALLO · %s" % f)
            total.extend(mercados)
            fallos_todos.extend(fallos)

        print("")
        print("a insertar: %d filas · fallos: %d"
              % (len(total), len(fallos_todos)))
        if not aplicar:
            print("\n(solo reporta; pasar --aplicar para escribir)")
            return 0
        if not total:
            print("nada que promover")
            return 0

        for m in total:
            cur.execute("""
                insert into pacs.mercados
                    (upload_batch_id, condado_fips, estado, nivel, fuente,
                     metricas, capturado_en)
                values (%s, %s, %s, %s, %s, %s, %s)
            """, (m["upload_batch_id"], m["condado_fips"], m["estado"],
                  m["nivel"], m["fuente"], json.dumps(m["metricas"]),
                  m["capturado_en"]))
        con.commit()

        cur.execute("""
            select nivel, estado, condado_fips,
                   metricas->>'total_volume', metricas->>'mkt_fha',
                   metricas->>'fallout', metricas->>'campos'
              from pacs.mercados order by nivel desc, condado_fips
        """)
        print("")
        print("DESPUES, leido de la base")
        print("   %-8s %-4s %-7s %14s %7s %9s %7s"
              % ("nivel", "est", "fips", "volumen", "FHA", "fallout", "campos"))
        for niv, est, fips, vol, fha, fo, campos in cur.fetchall():
            print("   %-8s %-4s %-7s %14s %7s %9s %7s"
                  % (niv, est or "-", fips or "-",
                     "$%.1fB" % (float(vol) / 1e9) if vol else "-",
                     fha, fo, campos))
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--aplicar" in sys.argv))
