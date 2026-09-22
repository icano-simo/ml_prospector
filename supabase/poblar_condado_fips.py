"""Puebla `condado_fips` en pacs.realtors y pacs.realtor_mercados.

    python supabase/poblar_condado_fips.py            # solo reporta
    python supabase/poblar_condado_fips.py --aplicar

Dos fuentes, y son muy distintas en lo que dan:

  el LIBRO           `mmi: condado_dominante`, un nombre por realtor
  las CAPTURAS       la tabla de condados de Model Match, con unidades

Lo que no se resuelve se REPORTA, no se adivina. `geo.fips.resolver` no hace
fuzzy matching a proposito: un FIPS aproximado es un FIPS equivocado, y un
benchmark atribuido al condado de al lado es peor que no tener benchmark.
"""
from __future__ import annotations

import os
import re
import sys
import uuid
from collections import Counter

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import pandas as pd  # noqa: E402
import psycopg  # noqa: E402

from captura.estados import normalizar_estado  # noqa: E402
from geo.fips import FipsNoResuelto, cargar, resolver  # noqa: E402
from supabase.cargar_libro_v3 import HOJA, LIBRO  # noqa: E402
from supabase.config import cargar_env  # noqa: E402

COL_CONDADO = "mmi: condado_dominante"

#: Lo que el libro pone cuando no hay dato. No es un condado.
SIN_DATO = ("[sin dato mmi]", "[sin dato]", "", "nan", "none")

#: `Travis 103 · Williamson 14 · Hays 7` -> [(Travis, 103), ...]
#: El separador es el punto medio; el numero al final de cada trozo son las
#: unidades. El PRIMERO es el dominante, que es lo que dice el nombre de la
#: columna -- pero se guardan todos, porque la columna trae mas de lo que
#: promete y tirarlo seria perder dato que ya esta.
_RE_TROZO = re.compile(r"^\s*(.+?)\s+(\d+)\s*$")


def condados_del_texto(valor) -> list[tuple[str, int]]:
    texto = str(valor or "").strip()
    if texto.lower() in SIN_DATO:
        return []
    salida = []
    for trozo in re.split(r"[·|;]", texto):
        m = _RE_TROZO.match(trozo)
        if m:
            salida.append((m.group(1).strip(), int(m.group(2))))
        elif trozo.strip():
            salida.append((trozo.strip(), 0))
    return salida


def _del_libro() -> tuple[list[dict], Counter]:
    df = pd.read_excel(LIBRO, sheet_name=HOJA)
    if COL_CONDADO not in df.columns:
        raise SystemExit("el libro no trae %r" % COL_CONDADO)

    tabla = cargar()
    filas, motivos = [], Counter()
    for _, r in df.iterrows():
        estado = normalizar_estado(r.get("Estado"))
        trozos = condados_del_texto(r.get(COL_CONDADO))
        if not trozos:
            motivos["el libro dice [sin dato MMI]"] += 1
            continue
        if not estado:
            motivos["sin estado normalizable"] += 1
            continue
        nombre, unidades = trozos[0]          # el dominante
        try:
            fips, oficial = resolver(estado, nombre, tabla)
        except FipsNoResuelto:
            motivos["no resuelve: %s / %s" % (estado, nombre)] += 1
            continue
        filas.append({"email": r.get("Email"), "nombre": r.get("Nombre"),
                      "estado": estado, "condado": nombre, "fips": fips,
                      "oficial": oficial, "unidades": unidades,
                      "todos": trozos})
    return filas, motivos


def main(aplicar: bool) -> int:
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL")
        return 1

    # ── 1 · EL LIBRO ────────────────────────────────────────────────────────
    print("1 · DESDE EL LIBRO · %r" % COL_CONDADO)
    filas, motivos = _del_libro()
    total = sum(motivos.values()) + len(filas)
    print("   resueltos: %d de %d" % (len(filas), total))
    for motivo, n in motivos.most_common(6):
        print("      %-44s %d" % (motivo[:44], n))
    for f in filas:
        print("      %s · %s -> %s (%s), %d unidades"
              % (f["nombre"], f["condado"], f["fips"], f["oficial"],
                 f["unidades"]))
        if len(f["todos"]) > 1:
            print("         y ademas: %s" % f["todos"][1:])

    # ── 2 · LAS CAPTURAS ────────────────────────────────────────────────────
    print("")
    print("2 · DESDE LAS CAPTURAS DE MODEL MATCH")
    tabla = cargar()
    con_captura: list[dict] = []
    no_resueltos: list[str] = []
    with psycopg.connect(url) as con:
        cur = con.cursor()
        cur.execute("""
            select parseado->>'realtor_id', estado, parseado->'perfil'->'condados'
              from pacs.v_capturas_modelmatch_current
             where parseado->>'seccion' = 'overview'
        """)
        for realtor_id, estado, condados in cur.fetchall():
            for c in (condados or []):
                nombre = c.get("nombre")
                est = normalizar_estado(c.get("estado")) or estado
                try:
                    fips, oficial = resolver(est, nombre, tabla)
                except FipsNoResuelto:
                    no_resueltos.append("%s / %s" % (est, nombre))
                    continue
                con_captura.append({"realtor_id": realtor_id,
                                    "condado_fips": fips, "oficial": oficial,
                                    "unidades": c.get("unidades")})
    print("   resueltos: %d · sin resolver: %s"
          % (len(con_captura), no_resueltos or "ninguno"))
    for c in con_captura:
        print("      %s -> %s (%s), %s unidades"
              % (c["oficial"], c["condado_fips"], c["realtor_id"][:8],
                 c["unidades"]))

    if not aplicar:
        print("")
        print("(solo reporta; pasar --aplicar para escribir)")
        return 0

    # ── 3 · ESCRIBIR ────────────────────────────────────────────────────────
    with psycopg.connect(url) as con:
        cur = con.cursor()
        lote = str(uuid.uuid4())
        cur.execute("""
            insert into pacs.upload_batch
                (id, fuente, archivo, es_vigente, filas_esperadas, nota)
            values (%s, 'libro_v3', 'crosswalk de condados', true, %s, %s)
        """, (lote, len(filas),
              "condado_fips desde `mmi: condado_dominante`, resuelto por "
              "geo.fips. La columna trae TODOS los condados, no solo el "
              "dominante: se guardan todos."))

        escritos = 0
        for f in filas:
            cur.execute("""
                update pacs.realtors set condado_fips = %s, actualizado_en = now()
                 where email_principal = %s and condado_fips is null
                returning id
            """, (f["fips"], f["email"]))
            fila = cur.fetchone()
            escritos += 1 if fila else 0
            if not fila:
                cur.execute("select id from pacs.realtors "
                            "where email_principal = %s", (f["email"],))
                fila = cur.fetchone()
            if not fila:
                continue
            rid = fila[0]
            # TODOS los condados de la columna, no solo el dominante: el dato
            # ya esta ahi y tirarlo es perderlo.
            tabla_local = cargar()
            for nombre, unidades in f["todos"]:
                try:
                    fips, _oficial = resolver(f["estado"], nombre, tabla_local)
                except FipsNoResuelto:
                    no_resueltos.append("%s / %s (libro)" % (f["estado"], nombre))
                    continue
                cur.execute("""
                    insert into pacs.realtor_mercados
                        (realtor_id, condado_fips, unidades, fuente,
                         upload_batch_id)
                    values (%s, %s, %s, 'libro_v3', %s)
                """, (rid, fips, unidades, lote))

        lote = str(uuid.uuid4())
        if con_captura:
            cur.execute("""
                insert into pacs.upload_batch
                    (id, fuente, archivo, es_vigente, filas_esperadas, nota)
                values (%s, 'modelmatch', 'crosswalk de condados', true, %s, %s)
            """, (lote, len(con_captura),
                  "condado_fips resuelto desde la tabla de condados de las "
                  "capturas, por geo.fips"))
            for c in con_captura:
                cur.execute("""
                    insert into pacs.realtor_mercados
                        (realtor_id, condado_fips, unidades, fuente,
                         upload_batch_id)
                    values (%s, %s, %s, 'modelmatch', %s)
                """, (c["realtor_id"], c["condado_fips"], c["unidades"], lote))
            # Y el condado dominante del realtor, si no lo tenia.
            mayor: dict = {}
            for c in con_captura:
                p = mayor.get(c["realtor_id"])
                if p is None or (c["unidades"] or 0) > (p["unidades"] or 0):
                    mayor[c["realtor_id"]] = c
            for rid, c in mayor.items():
                cur.execute("""
                    update pacs.realtors
                       set condado_fips = %s, actualizado_en = now()
                     where id = %s and condado_fips is null
                """, (c["condado_fips"], rid))
                escritos += cur.rowcount
        con.commit()

        # El DESPUES, leido de la base.
        cur.execute("""
            select count(*) filter (where condado_fips is not null), count(*)
              from pacs.realtors
        """)
        con_fips, tot = cur.fetchone()
        cur.execute("select count(*) from pacs.realtor_mercados")
        merc = cur.fetchone()[0]
        cur.execute("""
            select count(*) from pacs.realtors r
             join pacs.census_condados c on c.condado_fips = r.condado_fips
        """)
        cruzan = cur.fetchone()[0]

    print("")
    print("DESPUES, leido de la base")
    print("   realtors con condado_fips : %d de %d" % (con_fips, tot))
    print("   de esos, cruzan con Census: %d" % cruzan)
    print("   pacs.realtor_mercados     : %d filas" % merc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--aplicar" in sys.argv))
