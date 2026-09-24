"""La verificación de la migración 23, corrida de verdad.

    python supabase/verificar_migracion_23.py

Las dos mitades siempre: el SELECT que TIENE que funcionar va primero, porque
un INSERT que falla como `authenticated` se ve idéntico haya o no política de
lectura. Esa confusión ya costó una verificación entera en la 15 y volvió a
aparecer en la 18.

Y dos cosas que ya salieron mal antes y aquí están puestas a propósito:

  · **el unique se prueba con los DOS inserts en la misma sentencia.** En dos
    casos con un rollback en medio no chocan nunca, y la prueba decía que el
    unique no funcionaba cuando lo que no funcionaba era la prueba;
  · **la lectura se comprueba CON DATOS.** Un `count(*)` que da 0 sobre una
    tabla vacía dice exactamente lo mismo que un 0 por permisos.

No deja nada escrito: todo corre en transacciones que se revierten.
"""
from __future__ import annotations

import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import psycopg  # noqa: E402

from supabase.config import cargar_env  # noqa: E402

_FILA = ("insert into pacs.census_reporte_estado "
         "(estado, id_evidencia, texto, fuente) values ")

CASOS = [
    ("1 · SELECT como authenticated sobre la tabla",
     "set local role authenticated; "
     "select count(*) from pacs.census_reporte_estado", False, None),
    ("2 · SELECT como authenticated sobre la vista",
     "set local role authenticated; "
     "select count(*) from pacs.v_census_reporte_actual", False, None),
    ("3 · INSERT como authenticated (tiene que estar prohibido)",
     "set local role authenticated; " + _FILA +
     "('ZZ', 'CENSUS-RPT-ZZ', 'texto de prueba', 'prueba')",
     True, "permission denied for table census_reporte_estado"),
    ("4 · un estado que no son dos letras mayúsculas",
     _FILA + "('Illinois', 'CENSUS-RPT-Illinois', 'texto', 'prueba')",
     True, "census_reporte_estado_estado_check"),
    ("5 · el id que NO coincide con el estado",
     _FILA + "('ZZ', 'CENSUS-RPT-TX', 'texto de prueba', 'prueba')",
     True, "census_rpt_id_coincide"),
    ("6 · un texto con un correo dentro (PII)",
     _FILA + "('ZZ', 'CENSUS-RPT-ZZ', 'escribile a alguien@ejemplo.com', 'p')",
     True, "census_rpt_sin_pii"),
    ("7 · un texto con marcadores de origen",
     _FILA + "('ZZ', 'CENSUS-RPT-ZZ', 'marcadores_culturales: x', 'p')",
     True, "census_rpt_sin_pii"),
    # LOS DOS INSERTS EN LA MISMA SENTENCIA. Ver el docstring.
    ("8 · el MISMO texto dos veces para el mismo estado",
     _FILA + "('ZZ', 'CENSUS-RPT-ZZ', 'el mismo texto', 'p'), "
             "('ZZ', 'CENSUS-RPT-ZZ', 'el mismo texto', 'p')",
     True, "census_rpt_uno_por_texto"),
    ("9 · DOS textos distintos del mismo estado SÍ entran (otra edición)",
     _FILA + "('ZZ', 'CENSUS-RPT-ZZ', 'edicion vieja', 'p'), "
             "('ZZ', 'CENSUS-RPT-ZZ', 'edicion nueva', 'p')",
     False, None),
    ("10 · una fila válida SÍ entra (el control)",
     _FILA + "('ZZ', 'CENSUS-RPT-ZZ', 'ZZ · mercado de prueba', 'prueba')",
     False, None),
]


def _la_vista_da_una_por_estado(con) -> int:
    """Con dos cargas del mismo estado, la vista devuelve LA MÁS RECIENTE.

    Es lo que hace que el paquete no tenga que elegir. Se prueba escribiendo
    las dos y revirtiendo: sin datos, `distinct on` no se puede comprobar.
    """
    print("")
    print("la vista devuelve una fila por estado, la más reciente:")
    fallas = 0
    with con.cursor() as cur:
        try:
            cur.execute(
                _FILA + "('ZZ', 'CENSUS-RPT-ZZ', 'vieja', 'p'), "
                        "('ZZ', 'CENSUS-RPT-ZZ', 'nueva', 'p')")
            # `cargado_en` es el mismo por defecto en las dos, así que se
            # separa a mano: si no, `distinct on` elegiría cualquiera y la
            # prueba pasaría por azar la mitad de las veces.
            cur.execute("update pacs.census_reporte_estado "
                        "set cargado_en = now() - interval '1 day' "
                        "where estado = 'ZZ' and texto = 'vieja'")
            cur.execute("select texto from pacs.v_census_reporte_actual "
                        "where estado = 'ZZ'")
            filas = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            print("   ✕ no se pudo: %s" % " ".join(str(exc).split())[:120])
            con.rollback()
            return 1
        con.rollback()
    if len(filas) != 1 or filas[0][0] != "nueva":
        print("   ✕ devolvió %r y tenía que devolver [('nueva',)]" % (filas,))
        fallas += 1
    else:
        print("   ✓ una fila, y es la nueva")
    return fallas


def _lectura_con_datos(con) -> int:
    """Que la lectura devuelve LAS FILAS QUE HAY, no que no revienta."""
    fallas = 0
    print("")
    print("lectura CON DATOS:")
    with con.cursor() as cur:
        cur.execute("select count(*) from pacs.census_reporte_estado")
        total = cur.fetchone()[0]
        con.rollback()
    if not total:
        print("   ✕ `pacs.census_reporte_estado` está VACÍA: no hay nada que "
              "verificar. Corré `cargar_census_reporte.py --guardar`.")
        return 1

    for etiqueta, rol in (("como owner", None),
                          ("como authenticated SIN claim", "authenticated")):
        with con.cursor() as cur:
            try:
                if rol:
                    cur.execute("set local role %s" % rol)
                cur.execute("select count(*) from pacs.v_census_reporte_actual")
                n = cur.fetchone()[0]
            except Exception as exc:  # noqa: BLE001
                n = "ERROR %s" % str(exc)[:60]
            con.rollback()
        print("   %-32s %s de %s estados" % (etiqueta, n, total))
        if etiqueta == "como owner" and n != total:
            print("      ✕ la vista no devuelve una fila por estado cargado")
            fallas += 1
    return fallas


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL")
        return 1

    fallas = 0
    with psycopg.connect(url, autocommit=False) as con:
        with con.cursor() as cur:
            cur.execute("""
                select c.relname, c.reloptions
                  from pg_class c join pg_namespace n on n.oid = c.relnamespace
                 where n.nspname = 'pacs' and c.relkind = 'v'
                   and c.relname = 'v_census_reporte_actual'""")
            vistas = cur.fetchall()
        print("security_invoker de la vista nueva:")
        if not vistas:
            print("   ✕ `v_census_reporte_actual` no existe")
            fallas += 1
        for nombre, opciones in vistas:
            tiene = any("security_invoker=true" in (o or "").replace(" ", "")
                        for o in (opciones or []))
            print("   %s %-32s %s" % ("✓" if tiene else "✕", nombre,
                                      "invoker" if tiene else "OWNER"))
            if not tiene:
                fallas += 1

        with con.cursor() as cur:
            cur.execute("""
                select conname from pg_constraint
                 where conrelid = 'pacs.census_reporte_estado'::regclass
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
        fallas += _la_vista_da_una_por_estado(con)
        fallas += _lectura_con_datos(con)

    print("")
    print("casos que no pasaron: %d" % fallas)
    print("no quedó nada escrito: todo se revirtió.")
    return 1 if fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())
