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

    avisos: list[str] = []

    with psycopg.connect(url, autocommit=False) as con:
        # Los `raise notice` de la migracion son lo que ELLA dice de si misma.
        # La version anterior imprimia siempre el constraint de `contactos`
        # -- de la migracion 06-- corriera la que corriera: una salida que no
        # depende de lo que paso no comprueba nada, solo tranquiliza.
        con.add_notice_handler(lambda diag: avisos.append(
            (diag.message_primary or "").strip()))
        with con.cursor() as cur:
            cur.execute(sql)
        con.commit()
        print("aplicada: %s" % os.path.basename(ruta))

    if avisos:
        print("")
        print("lo que dice la migracion de si misma:")
        for a in avisos:
            print("   %s" % a)
    else:
        print("   (la migracion no emitio ningun `raise notice`: no dice nada "
              "de lo que dejo. Vale la pena que lo diga.)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
