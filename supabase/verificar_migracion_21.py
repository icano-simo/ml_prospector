"""La verificación de la migración 21, corrida de verdad.

    python supabase/verificar_migracion_21.py

Las dos mitades siempre: el SELECT que TIENE que funcionar va primero, porque
un INSERT que falla como `authenticated` se ve idéntico haya o no política de
lectura. Esa confusión ya costó una verificación entera en la 15 y volvió a
aparecer en la 18.

Y `security_invoker` se comprueba LEYENDO `reloptions` de la vista, no
suponiendo que el `with (...)` del archivo se aplicó. Una vista creada con
`create or replace` sobre una vista anterior conserva opciones, y el `with` se
puede ignorar sin error.

No deja nada escrito: todo corre en una transacción que se revierte.
"""
from __future__ import annotations

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import psycopg  # noqa: E402

from supabase.config import cargar_env  # noqa: E402

CASOS = [
    ("1 · SELECT como authenticated sobre v_paquete_ficha",
     "set local role authenticated; "
     "select count(*) from pacs.v_paquete_ficha", False, None),
    ("2 · SELECT como authenticated sobre v_ficha_ia_actual",
     "set local role authenticated; "
     "select count(*) from pacs.v_ficha_ia_actual", False, None),
    ("3 · la función pacs.paquete_ficha() como authenticated",
     "set local role authenticated; "
     "select pacs.paquete_ficha(gen_random_uuid())", False, None),
    ("4 · INSERT como authenticated en paquetes_ficha",
     "set local role authenticated; "
     "insert into pacs.paquetes_ficha (realtor_id, version_paquete, "
     "hash_paquete, paquete) select r.id, 'v', 'h', '{}'::jsonb "
     "from pacs.realtors r limit 1",
     True, "permission denied for table paquetes_ficha"),
    ("5 · un paquete con marcadores de origen",
     "insert into pacs.paquetes_ficha (realtor_id, version_paquete, "
     "hash_paquete, paquete) select r.id, 'v', 'v21-ecoa', "
     "'{\"marcadores_culturales\": \"x\"}'::jsonb from pacs.realtors r limit 1",
     True, "paquete_sin_pii"),
    ("6 · un paquete con el nombre del comprador",
     "insert into pacs.paquetes_ficha (realtor_id, version_paquete, "
     "hash_paquete, paquete) select r.id, 'v', 'v21-buyers', "
     "'{\"buyers\": \"X\"}'::jsonb from pacs.realtors r limit 1",
     True, "paquete_sin_pii"),
    ("7 · el MISMO paquete dos veces (mismo realtor, mismo hash)",
     "insert into pacs.paquetes_ficha (realtor_id, version_paquete, "
     "hash_paquete, paquete) select r.id, 'v', h, '{}'::jsonb "
     "from (select id from pacs.realtors limit 1) r, "
     "(values ('v21-dup'), ('v21-dup')) as v(h)",
     True, "paquete_uno_por_contenido"),
    ("8 · un paquete válido SÍ entra (el control)",
     "insert into pacs.paquetes_ficha (realtor_id, version_paquete, "
     "hash_paquete, paquete) select r.id, 'v', 'v21-ok', "
     "'{\"evidencias\": []}'::jsonb from pacs.realtors r limit 1",
     False, None),
    ("9 · una ficha que trae el veredicto (lo decide el código, no la IA)",
     "insert into pacs.fichas_ia (realtor_id, version_prompt, hash_paquete, "
     "json) select r.id, 'p', 'h', '{\"veredicto\": {\"estado\": \"ok\"}}'::jsonb "
     "from pacs.realtors r limit 1",
     True, "ficha_solo_campos_ia"),
    ("10 · una ficha solo con campos de IA SÍ entra",
     "insert into pacs.fichas_ia (realtor_id, version_prompt, hash_paquete, "
     "json) select r.id, 'p', 'h', '{\"dolores\": []}'::jsonb "
     "from pacs.realtors r limit 1",
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
        # ── `security_invoker`, LEÍDO de la base ────────────────────────────
        with con.cursor() as cur:
            cur.execute("""
                select c.relname, c.reloptions
                  from pg_class c join pg_namespace n on n.oid = c.relnamespace
                 where n.nspname = 'pacs' and c.relkind = 'v'
                 order by c.relname""")
            vistas = cur.fetchall()
        nuevas = {"v_paquete_ficha", "v_ficha_ia_actual"}
        print("security_invoker de las vistas de pacs:")
        for nombre, opciones in vistas:
            tiene = any("security_invoker=true" in (o or "").replace(" ", "")
                        for o in (opciones or []))
            marca = "✓" if tiene else ("✕" if nombre in nuevas else "·")
            print("   %s %-34s %s" % (marca, nombre,
                                      "invoker" if tiene else "OWNER"))
            if nombre in nuevas and not tiene:
                fallas += 1
        sin_invoker = [n for n, o in vistas
                       if not any("security_invoker=true" in (x or "").replace(" ", "")
                                  for x in (o or []))]
        print("")
        print("   vistas de pacs que siguen corriendo como OWNER: %d"
              % len(sin_invoker))
        print("   (van en el PR de autenticación, migración 17: hoy no cambia")
        print("    nada porque las políticas son `using (true)`, pero el día")
        print("    que se cierren serían una ventana al lado de la puerta.)")

        with con.cursor() as cur:
            cur.execute("""
                select conname from pg_constraint
                 where conrelid in ('pacs.paquetes_ficha'::regclass,
                                    'pacs.fichas_ia'::regclass,
                                    'pacs.fichas_ia_pendientes'::regclass)
                 order by conname""")
            print("")
            print("constraints: %s" % ", ".join(n for (n,) in cur.fetchall()))
        con.rollback()

        print("")
        print("═" * 68)
        for nombre, sql, debe_fallar, fragmento in CASOS:
            with con.cursor() as cur:
                try:
                    cur.execute(sql)
                    fallo, error = False, None
                except Exception as exc:  # noqa: BLE001
                    fallo, error = True, " ".join(str(exc).split())[:140]
                con.rollback()
            if fallo != debe_fallar:
                estado, fallas = "✕ FALLA LA VERIFICACIÓN", fallas + 1
            elif fragmento and fragmento.lower() not in (error or "").lower():
                estado, fallas = "✕ falló, pero por otro motivo", fallas + 1
            else:
                estado = "✓"
            print("%s %s" % (estado, nombre))
            if error:
                print("     %s" % error)
        print("═" * 68)

    print("")
    print("casos que no pasaron: %d" % fallas)
    print("no quedó nada escrito: todo se revirtió.")
    return 1 if fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())
