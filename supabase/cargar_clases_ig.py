"""Carga las clases de perfil de Instagram a `pacs.ig_clase_perfil`.

Dos origenes, y el orden importa:

  1 · `auto` -- las 298 que calcula `ingest.instagram.clase_perfil`;
  2 · `auditoria` -- las que una persona decidio a mano, firmadas.

La tabla es append-only y `v_ig_clase_actual` resuelve la prioridad: la
auditoria manual gana sobre la automatica SIEMPRE, y entre dos auditorias gana
la mas nueva. Por eso este script puede correrse de nuevo sin borrar nada: cada
corrida agrega filas `auto`, y la auditoria sigue arriba.

    python supabase/cargar_clases_ig.py --auto
    python supabase/cargar_clases_ig.py --auditoria <ruta.json> --firma "Nombre"

El JSON de la auditoria vive FUERA de git (trae handles). El script lo recibe
por ruta y no lo busca solo, para que no haya una ruta por defecto que alguien
versione sin querer.
"""
from __future__ import annotations

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from ingest.instagram.clase_perfil import (  # noqa: E402
    CLASES,
    clasificar,
    handles_repetidos_en,
)
from ingest.instagram.lexico import VERSION_LEXICO  # noqa: E402
from supabase.cargar import conectar  # noqa: E402


def filas_de_ig(cur) -> list[dict]:
    cur.execute("""
        select s.realtor_id::text, s.handle, s.estado_perfil, s.captions_n,
               s.senales, s.capturado_en, r.estado
          from pacs.v_ig_senales_current s
          join pacs.realtors r on r.id = s.realtor_id
         where s.realtor_id is not null
    """)
    return [{"realtor_id": f[0], "handle": f[1], "estado_perfil": f[2],
             "captions_n": f[3], "senales": f[4], "capturado_en": f[5],
             "estado": f[6]} for f in cur.fetchall()]


def cargar_auto() -> int:
    with conectar() as con:
        cur = con.cursor()
        filas = filas_de_ig(cur)
        reps = handles_repetidos_en(filas)
        print("perfiles con Instagram: %d · handles repetidos: %d"
              % (len(filas), len(reps)))

        n = 0
        for f in filas:
            s = f["senales"] or {}
            c = clasificar({"estado_perfil": f["estado_perfil"],
                            "handle": f["handle"], "estado": f["estado"],
                            "capturado_en": f["capturado_en"],
                            "captions_texto": s.get("captions_texto"),
                            "geotags_top": s.get("geotags_top")},
                           handles_repetidos=reps)
            cur.execute("""
                insert into pacs.ig_clase_perfil
                    (realtor_id, handle, clase, motivo, origen, revisar,
                     version_lexico, detalle)
                values (%s,%s,%s,%s,'auto',%s,%s,%s)
            """, (f["realtor_id"], f["handle"], c.clase, c.motivo, c.revisar,
                  VERSION_LEXICO, json.dumps(c.detalle, ensure_ascii=False,
                                             default=str)))
            n += 1
        con.commit()
    print("clases `auto` escritas: %d" % n)
    return n


def cargar_auditoria(ruta: str, firma: str) -> int:
    with open(ruta, encoding="utf-8") as fh:
        aud = json.load(fh)

    # handle -> clase. Se compara en minusculas y sin arroba, como pidio la
    # revision: el mismo handle viene escrito de tres formas segun la fuente.
    esperado = {}
    for clase, handles in (aud.get("clases") or {}).items():
        if clase not in CLASES:
            raise SystemExit("clase %r del JSON no esta en las 9 validas" % clase)
        for h in handles:
            esperado[str(h).strip().lstrip("@").lower()] = clase
    print("auditoria: %d handles en %d clases" % (len(esperado),
                                                  len(aud.get("clases") or {})))

    with conectar() as con:
        cur = con.cursor()
        filas = filas_de_ig(cur)
        por_handle: dict = {}
        for f in filas:
            h = str(f["handle"] or "").strip().lstrip("@").lower()
            if h:
                por_handle.setdefault(h, []).append(f)

        n = sin_cruce = 0
        for h, clase in esperado.items():
            objetivo = por_handle.get(h)
            if not objetivo:
                sin_cruce += 1
                continue
            # Un handle en dos leads se audita en LOS DOS: es la politica que
            # el propio JSON declara para el duplicado.
            for f in objetivo:
                cur.execute("""
                    insert into pacs.ig_clase_perfil
                        (realtor_id, handle, clase, motivo, origen, revisar,
                         auditada_por, version_lexico, detalle)
                    values (%s,%s,%s,%s,'auditoria',false,%s,%s,%s)
                """, (f["realtor_id"], f["handle"], clase,
                      "auditoría manual del %s" % aud.get("_fecha", "2026-09-23"),
                      firma, VERSION_LEXICO,
                      json.dumps({"fuente": aud.get("fuente", "")[:120]},
                                 ensure_ascii=False)))
                n += 1
        con.commit()
    print("clases `auditoria` escritas: %d · handles del JSON sin cruce: %d"
          % (n, sin_cruce))
    return n


def resumen() -> None:
    with conectar() as con:
        cur = con.cursor()
        cur.execute("""
            select clase, origen, count(*) from pacs.ig_clase_perfil
             group by 1,2 order by 1,2
        """)
        print("")
        print("EN LA TABLA (append-only, todas las filas)")
        for clase, origen, n in cur.fetchall():
            print("   %-20s %-10s %4d" % (clase, origen, n))

        cur.execute("""
            select clase, origen, count(*) from pacs.v_ig_clase_actual
             group by 1,2 order by 3 desc, 1
        """)
        print("")
        print("EN v_ig_clase_actual (la que manda)")
        total = 0
        for clase, origen, n in cur.fetchall():
            print("   %-20s %-10s %4d" % (clase, origen, n))
            total += n
        print("   %-31s %4d" % ("TOTAL", total))

        cur.execute("""
            select count(*), count(distinct realtor_id)
              from pacs.v_ig_clase_actual
        """)
        filas, realtors = cur.fetchone()
        if filas != realtors:
            raise SystemExit(
                "la vista devuelve %d filas para %d realtors" % (filas, realtors))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--auto" in sys.argv:
        cargar_auto()
    if "--auditoria" in sys.argv:
        i = sys.argv.index("--auditoria")
        ruta = sys.argv[i + 1]
        firma = sys.argv[sys.argv.index("--firma") + 1] \
            if "--firma" in sys.argv else None
        if not firma:
            raise SystemExit("la auditoria necesita --firma: sin firma no se "
                             "puede discutir con nadie")
        cargar_auditoria(ruta, firma)
    resumen()
    return 0


if __name__ == "__main__":
    sys.exit(main())
