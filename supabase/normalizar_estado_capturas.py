"""Deja `estado` y la etiqueta del bloque de estado en codigo de dos letras.

    python supabase/normalizar_estado_capturas.py           # solo muestra
    python supabase/normalizar_estado_capturas.py --aplicar

`CA`, `California` y `CALIFORNIA` son tres mercados distintos en la biblioteca
de geografias, y la unica pista de que son el mismo es mirarlos uno al lado del
otro. Corregir la etiqueta NO cambia ninguna medicion: el crudo no se toca y las
metricas se derivan de el.

Imprime el antes y el despues leidos de la base, porque "corrio sin error" no
prueba que quedo aplicado.
"""
from __future__ import annotations

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import psycopg  # noqa: E402

from captura.estados import normalizar_estado  # noqa: E402
from supabase.config import cargar_env  # noqa: E402


def main(aplicar: bool) -> int:
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL")
        return 1

    consulta = """
        select estado, geografia_nivel, geografia_etiqueta, count(*)
        from pacs.capturas_modelmatch
        group by 1, 2, 3 order by 1, 2, 3
    """

    with psycopg.connect(url) as con:
        cur = con.cursor()
        cur.execute(consulta)
        filas = cur.fetchall()

        print("ANTES")
        cambios = []
        for estado, nivel, etiq, n in filas:
            e2 = normalizar_estado(estado)
            # La etiqueta SOLO se toca en el bloque del estado. `Alameda` no es
            # un estado, asi que `normalizar_estado` devuelve None sobre ella --
            # y aplicarlo habria borrado la etiqueta de los tres condados, que
            # es lo unico que distingue un bloque de mercado de otro.
            t2 = normalizar_estado(etiq) if nivel == "estado" else etiq
            if nivel == "estado" and etiq and t2 is None:
                t2 = etiq          # no se reconoce: se deja como esta
            marca = ""
            if (e2 and e2 != estado) or (t2 != etiq):
                marca = "  ->  estado=%s etiqueta=%s" % (e2, t2)
                cambios.append((estado, nivel, etiq, e2, t2, n))
            print("   estado=%-12s nivel=%-7s etiqueta=%-14s %3d filas%s"
                  % (estado, nivel or "-", etiq or "-", n, marca))

        # La copia de la etiqueta que vive DENTRO del jsonb se cuenta aparte:
        # corregir solo la columna deja las dos en desacuerdo, y la pantalla lee
        # el jsonb. Va fuera del `if not cambios` porque la desincronizacion
        # sobrevive a que las columnas ya esten bien -- que es exactamente como
        # quedo despues de la primera corrida.
        cur.execute("""
            select count(*) from pacs.capturas_modelmatch
             where geografia_etiqueta is not null
               and parseado->>'etiqueta_geografica'
                   is distinct from geografia_etiqueta
        """)
        desync = cur.fetchone()[0]
        print("\nfilas con el jsonb en desacuerdo con la columna: %d" % desync)

        if not cambios and not desync:
            print("no hay nada que normalizar")
            return 0
        print("%d grupos de columna a corregir, %d filas"
              % (len(cambios), sum(c[5] for c in cambios)))

        # Guarda redundante a proposito: ninguna correccion puede dejar una
        # etiqueta en NULL. Una fila de mercado sin etiqueta es justo la que no
        # se puede distinguir de otra al mirar la tabla.
        for _e, _niv, etiq, _e2, t2, _n in cambios:
            if etiq and not t2:
                print("\nABORTADO: la correccion dejaria en NULL la etiqueta "
                      "%r. No se escribe nada." % etiq)
                return 1

        if not aplicar:
            print("\n(solo muestra; pasar --aplicar para escribir)")
            return 0

        for estado, nivel, etiq, e2, t2, _n in cambios:
            cur.execute("""
                update pacs.capturas_modelmatch
                   set estado = %s, geografia_etiqueta = %s
                 where estado is not distinct from %s
                   and geografia_nivel is not distinct from %s
                   and geografia_etiqueta is not distinct from %s
            """, (e2, t2, estado, nivel, etiq))

        # Y la copia que vive DENTRO del jsonb. Corregir solo la columna deja
        # las dos en desacuerdo, y quien lea `parseado` -- que es lo que muestra
        # la pantalla-- sigue viendo la forma vieja. Una etiqueta guardada en
        # dos sitios se desincroniza en cuanto se corrige uno.
        cur.execute("""
            update pacs.capturas_modelmatch
               set parseado = jsonb_set(parseado, '{etiqueta_geografica}',
                                        to_jsonb(geografia_etiqueta))
             where geografia_etiqueta is not null
               and parseado->>'etiqueta_geografica'
                   is distinct from geografia_etiqueta
        """)
        print("\njsonb sincronizado con la columna: %d filas" % cur.rowcount)
        con.commit()

        cur.execute(consulta)
        print("\nDESPUES, leido de la base")
        for estado, nivel, etiq, n in cur.fetchall():
            print("   estado=%-12s nivel=%-7s etiqueta=%-14s %3d filas"
                  % (estado, nivel or "-", etiq or "-", n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--aplicar" in sys.argv))
