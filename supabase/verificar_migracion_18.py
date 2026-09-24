"""La verificación al pie de la migración 18, corrida de verdad.

    python supabase/verificar_migracion_18.py

Por qué es un script y no un bloque de SQL comentado
----------------------------------------------------
Un bloque comentado se lee y se cree. Este imprime, caso por caso, si pasó lo
que tenía que pasar -- y **falla con código distinto de cero** si alguno no.

Y las dos mitades, siempre. Un INSERT que falla como `anon` se ve IDÉNTICO haya
o no política de lectura: Postgres corta por el GRANT antes de mirar RLS. Esa
confusión ya costó una verificación entera en la migración 15, así que aquí el
SELECT que TIENE que funcionar va primero y su resultado se imprime.

No deja nada escrito: todo corre dentro de una transacción que se revierte.
"""
from __future__ import annotations

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import psycopg  # noqa: E402

from supabase.config import cargar_env  # noqa: E402

#: (nombre, sql, tiene_que_fallar, fragmento_esperado_del_error)
CASOS = [
    # Como `authenticated` y no como `anon`: `anon` no tiene USAGE sobre el
    # esquema `pacs`, así que los dos casos fallarían por el ESQUEMA y no por
    # lo que se quiere comprobar. Ver la migración 20.
    ("1 · SELECT como authenticated sobre la vista",
     "set local role authenticated; "
     "select count(*) from pacs.v_transacciones_current",
     False, None),
    ("2 · INSERT como authenticated (no tiene GRANT de insert)",
     "set local role authenticated; "
     "insert into pacs.transacciones (upload_batch_id, realtor_id, hash_fila, "
     "estado_prestamo) select b.id, r.id, 'v18-auth', 'financiada' "
     "from pacs.upload_batch b, pacs.realtors r limit 1",
     True, "permission denied for table transacciones"),
    ("2b · `anon` no llega ni al esquema",
     "set local role anon; select count(*) from pacs.v_transacciones_current",
     True, "permission denied for schema pacs"),
    ("3 · crudo con el nombre del comprador",
     "insert into pacs.transacciones (upload_batch_id, realtor_id, hash_fila, "
     "estado_prestamo, crudo) select b.id, r.id, 'v18-ecoa', 'financiada', "
     "'{\"buyers\": \"X\"}'::jsonb from pacs.upload_batch b, pacs.realtors r "
     "limit 1",
     True, "tx_sin_nombres_de_las_partes"),
    ("4 · tasa en puntos base (762)",
     "insert into pacs.transacciones (upload_batch_id, realtor_id, hash_fila, "
     "estado_prestamo, tasa) select b.id, r.id, 'v18-tasa', 'financiada', 762 "
     "from pacs.upload_batch b, pacs.realtors r limit 1",
     True, "tx_tasa_es_un_porcentaje"),
    ("5 · lado inventado",
     "insert into pacs.transacciones (upload_batch_id, realtor_id, hash_fila, "
     "estado_prestamo, lado) select b.id, r.id, 'v18-lado', 'financiada', "
     "'compraventa' from pacs.upload_batch b, pacs.realtors r limit 1",
     True, "tx_lado_valido"),
    # El CONTROL de los tres anteriores: si nada entrara, «todo falla» no
    # probaría que los checks funcionan -- probaría que la tabla no recibe.
    ("6 · una fila válida CON `no_leido` (el arreglo que pidió la revisión)",
     "insert into pacs.transacciones (upload_batch_id, realtor_id, hash_fila, "
     "estado_prestamo, lado, tasa) select b.id, r.id, 'v18-ok', 'no_leido', "
     "'compra', 6.55 from pacs.upload_batch b, pacs.realtors r limit 1",
     False, None),
    # Las DOS inserciones en la MISMA sentencia. La primera versión las ponía
    # en dos casos, y entre uno y otro hay un rollback -- así que el segundo
    # insertaba la primera fila otra vez y no chocaba con nada. La prueba decía
    # que el unique no funciona, y lo que no funcionaba era la prueba.
    ("7 · la misma fila dos veces en el mismo lote",
     "insert into pacs.transacciones (upload_batch_id, realtor_id, hash_fila, "
     "estado_prestamo) select b.id, r.id, h, 'financiada' "
     "from pacs.upload_batch b, pacs.realtors r, "
     "(values ('v18-dup'), ('v18-dup')) as v(h) limit 2",
     True, "tx_una_vez_por_lote"),
    ("8 · la misma fila en DOS lotes distintos sí entra (es una re-captura)",
     "insert into pacs.transacciones (upload_batch_id, realtor_id, hash_fila, "
     "estado_prestamo) select b.id, r.id, 'v18-recap', 'financiada' "
     "from (select id from pacs.upload_batch limit 2) b, "
     "(select id from pacs.realtors limit 1) r",
     False, None),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL")
        return 1

    fallas = 0
    with psycopg.connect(url, autocommit=False) as con:
        # ── Lo que la migración dejó, leído de la base ──────────────────────
        with con.cursor() as cur:
            cur.execute("""
                select conname from pg_constraint
                 where conrelid = 'pacs.transacciones'::regclass
                 order by conname""")
            print("constraints en pacs.transacciones:")
            for (n,) in cur.fetchall():
                print("   %s" % n)
        with con.cursor() as cur:
            cur.execute("""
                select pg_get_constraintdef(oid) from pg_constraint
                 where conrelid = 'pacs.transacciones'::regclass
                   and conname = 'tx_estado_prestamo_valido'""")
            fila = cur.fetchone()
            print("")
            print("tx_estado_prestamo_valido: %s" % (fila[0] if fila else "NO ESTÁ"))
            if not fila or "no_leido" not in fila[0]:
                print("   ✕ no acepta `no_leido`")
                fallas += 1
        with con.cursor() as cur:
            cur.execute("""
                select polname, polcmd from pg_policy
                 where polrelid = 'pacs.transacciones'::regclass""")
            print("políticas RLS: %r" % (cur.fetchall(),))
        with con.cursor() as cur:
            cur.execute("""
                select grantee, privilege_type
                  from information_schema.role_table_grants
                 where table_schema = 'pacs' and table_name = 'transacciones'
                 order by grantee, privilege_type""")
            print("GRANTs: %r" % (cur.fetchall(),))
        con.rollback()

        print("")
        print("═" * 66)
        for nombre, sql, debe_fallar, fragmento in CASOS:
            with con.cursor() as cur:
                try:
                    cur.execute(sql)
                    resultado = (cur.fetchone() if cur.description else None)
                    fallo, error = False, None
                except Exception as exc:  # noqa: BLE001
                    fallo, error = True, " ".join(str(exc).split())[:150]
                    resultado = None
                con.rollback()

            if fallo != debe_fallar:
                estado = "✕ FALLA LA VERIFICACIÓN"
                fallas += 1
            elif fragmento and fragmento.lower() not in (error or "").lower():
                estado = "✕ falló, pero por otro motivo"
                fallas += 1
            else:
                estado = "✓"
            print("%s %s" % (estado, nombre))
            if error:
                print("     %s" % error)
            elif resultado is not None:
                print("     devolvió %r" % (resultado,))
        print("═" * 66)

    print("")
    print("casos que no pasaron: %d" % fallas)
    print("no quedó nada escrito: todo se revirtió.")
    return 1 if fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())
