"""Aplica un archivo .sql por conexion directa, y verifica despues.

    python supabase/aplicar_migracion.py supabase/migracion_06_contactos_direccion.sql

Por que existe: una migracion que "corrio sin error" no prueba que quedo
aplicada. Este script imprime el estado DESPUES, leido de la base, para que la
comprobacion tenga algo que comprobar.
"""
from __future__ import annotations

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import psycopg  # noqa: E402

from supabase.config import cargar_env  # noqa: E402


def main(ruta: str) -> int:
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL en .env")
        return 1

    with open(ruta, encoding="utf-8") as fh:
        sql = fh.read()

    with psycopg.connect(url, autocommit=False) as con:
        with con.cursor() as cur:
            cur.execute(sql)
        con.commit()
        print("aplicada: %s" % os.path.basename(ruta))

        # El estado DESPUES, leido de la base y no del archivo.
        with con.cursor() as cur:
            cur.execute("""
                select pg_get_constraintdef(oid)
                from pg_constraint
                where conrelid = 'pacs.contactos'::regclass
                  and conname = 'contactos_canal_check'
            """)
            fila = cur.fetchone()
        print("check de canal ahora: %s" % (fila[0] if fila else "(no existe)"))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
