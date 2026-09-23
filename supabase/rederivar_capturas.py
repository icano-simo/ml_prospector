"""Re-deriva el `parseado` de las capturas ya guardadas, desde su crudo.

    python supabase/rederivar_capturas.py            # solo reporta
    python supabase/rederivar_capturas.py --aplicar

Es la mitad de la arquitectura que hace que un fallo del parser no cueste una
re-captura: **el crudo es la fuente y la derivacion es libre de repetirse.**
Cada vez que se arregla el parser, esto lo aplica a lo que ya esta guardado.

No toca `texto_crudo` jamas. Solo reescribe `parseado`, y deja constancia de
con que version lo hizo.
"""
from __future__ import annotations

import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)

import psycopg  # noqa: E402

from captura.parser_mm import parsear_mercado, parsear_perfil  # noqa: E402
from supabase.config import cargar_env  # noqa: E402

VERSION = "parser_mm 2026-09-23"

#: Campos que NO salen del texto: los inyecta el guardado porque el dato no
#: viaja en el pegado. Re-derivar desde el crudo los borraria.
#:
#: Paso: la primera corrida de este script dejo `ventana_meses` en NULL sobre
#: una captura que la tenia declarada en 14. El crudo dice `Set Date Range:`
#: sin valor -- por eso hay un campo en la pantalla-- asi que volver a parsear
#: el crudo no puede recuperarlo. **Re-derivar tiene que preservar lo
#: declarado**, o destruye justo lo que no se puede re-derivar.
DECLARADOS_FUERA_DEL_PARSER = ("ventana_meses", "ventana_declarada",
                               "ventana_origen")


def _campos_con_dato(perfil: dict | None) -> int:
    return sum(1 for k, v in (perfil or {}).items()
               if k not in ("capturado_en", "fallos", "wallet_share_base")
               and v not in (None, "", [], {}, False))


def main(aplicar: bool) -> int:
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL")
        return 1

    with psycopg.connect(url) as con:
        cur = con.cursor()
        cur.execute("""
            select id, parseado->>'seccion', alcance, length(texto_crudo),
                   texto_crudo, parseado, version_parser
              from pacs.v_capturas_modelmatch_current
             order by capturado_en, parseado->>'orden'
        """)
        filas = cur.fetchall()

        print("capturas vivas: %d" % len(filas))
        print("")
        print("%-16s %7s  %-14s -> %-14s %s"
              % ("seccion", "chars", "antes", "despues", ""))
        cambios = []
        for (fid, seccion, alcance, n, crudo, p, version) in filas:
            p = dict(p or {})
            if alcance == "mercado":
                nuevo = parsear_mercado(crudo)
                antes = (p.get("metricas") or {}).get("campos")
                despues = nuevo.get("campos")
                p["metricas"] = nuevo
            else:
                nuevo = parsear_perfil(crudo)
                viejo = p.get("perfil") or {}
                # Lo declarado sobrevive al re-derivado.
                for k in DECLARADOS_FUERA_DEL_PARSER:
                    if viejo.get(k) is not None:
                        nuevo[k] = viejo[k]
                # Y si la ventana vuelve, la produccion anualizada tambien.
                if nuevo.get("ventana_meses") and nuevo.get("buyer_units"):
                    nuevo["buyside_anualizado"] = round(
                        nuevo["buyer_units"] / nuevo["ventana_meses"] * 12.0, 1)
                antes = _campos_con_dato(viejo)
                despues = _campos_con_dato(nuevo)
                p["perfil"] = nuevo
            marca = ""
            if (antes or 0) != (despues or 0):
                marca = "   <-- cambia"
                cambios.append((fid, p, seccion, antes, despues))
            print("%-16s %7d  %-14s -> %-14s%s"
                  % (seccion, n, antes, despues, marca))

        print("")
        print("cambian: %d de %d" % (len(cambios), len(filas)))
        if not aplicar:
            print("\n(solo reporta; pasar --aplicar para escribir)")
            return 0
        if not cambios:
            print("nada que re-derivar")
            return 0

        for fid, p, _s, _a, _d in cambios:
            cur.execute("""
                update pacs.capturas_modelmatch
                   set parseado = %s, version_parser = %s
                 where id = %s
            """, (json.dumps(p, ensure_ascii=False), VERSION, fid))
        con.commit()

        cur.execute("""
            select parseado->>'seccion',
                   parseado->'perfil'->>'tpo_pct',
                   jsonb_array_length(coalesce(parseado->'perfil'->'tabla_lenders',
                                               '[]'::jsonb)),
                   parseado->'perfil'->>'ventana_meses'
              from pacs.v_capturas_modelmatch_current
             where alcance = 'perfil' order by parseado->>'orden'
        """)
        print("")
        print("DESPUES, leido de la base")
        print("   %-16s %-8s %-8s %s" % ("seccion", "tpo", "lenders", "ventana"))
        for s, tpo, nl, vm in cur.fetchall():
            print("   %-16s %-8s %-8s %s" % (s, tpo or "-", nl, vm or "-"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--aplicar" in sys.argv))
