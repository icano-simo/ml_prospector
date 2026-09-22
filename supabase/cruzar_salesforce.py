"""Aplica la migracion 01 y cruza el Lead ID de Salesforce por email.

Del archivo toma DOS columnas y nada mas: `Lead ID` y `Email`.

Cuidado con el archivo: trae `Email` y `Email Owner`, y la segunda tiene 14
valores unicos sobre 4.386 filas -- es el correo del DUEÑO del lead, no el del
realtor. Cruzar por esa habria unido a todo el mundo con catorce personas.
"""
from __future__ import annotations

import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from supabase.cargar import conectar  # noqa: E402

ARCH = os.path.join(RAIZ, "Data_inputIA",
                    "Loan officer check-2026-09-18-12-54-09.xlsx")
MIGRACION = os.path.join(RAIZ, "supabase", "migracion_01_sf_lead_id.sql")

COL_LEAD = "Lead ID"
COL_EMAIL = "Email"


def email_limpio(v) -> str | None:
    import pandas as pd
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().lower()
    return s if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", s) else None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import pandas as pd

    df = pd.read_excel(ARCH)
    for c in (COL_LEAD, COL_EMAIL):
        if c not in df.columns:
            raise SystemExit("falta la columna %r en el archivo" % c)

    # email -> lead_id. Si dos leads comparten email, no se elige uno: se
    # descarta el par y se reporta. Un cruce ambiguo resuelto en silencio es
    # peor que un cruce que no ocurre.
    por_email: dict[str, str] = {}
    ambiguos: set[str] = set()
    sin_email = 0
    for _, r in df.iterrows():
        em = email_limpio(r[COL_EMAIL])
        lead = str(r[COL_LEAD]).strip()
        if not em:
            sin_email += 1
            continue
        if em in por_email and por_email[em] != lead:
            ambiguos.add(em)
        por_email[em] = lead
    for em in ambiguos:
        por_email.pop(em, None)

    print("archivo: %d filas · %d emails utilizables · %d sin email · %d ambiguos"
          % (len(df), len(por_email), sin_email, len(ambiguos)))
    print("")

    with conectar() as conn:
        # ── 1 · la migracion ────────────────────────────────────────────────
        with open(MIGRACION, encoding="utf-8") as fh:
            sql = fh.read()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("migracion 01 aplicada")

        with conn.cursor() as cur:
            # ── 2 · el cruce, por lotes ─────────────────────────────────────
            cur.execute("select id, email_principal from pacs.realtors "
                        " where email_principal is not null")
            filas = cur.fetchall()

            pares = [(por_email[em], str(rid))
                     for rid, em in filas if em in por_email]
            print("realtors con email: %d · cruzan: %d" % (len(filas), len(pares)))

            for i in range(0, len(pares), 500):
                cur.executemany(
                    "update pacs.realtors "
                    "   set sf_lead_id = %s, clave_resolucion = 'sf_lead_id', "
                    "       actualizado_en = now() "
                    " where id = %s",
                    pares[i:i + 500],
                )
        conn.commit()

        # ── 3 · contar en la base ───────────────────────────────────────────
        with conn.cursor() as cur:
            cur.execute(
                "select count(*), count(sf_lead_id), "
                "       count(*) filter (where sin_llave_dura) "
                "  from pacs.realtors")
            total, con_lead, sin_llave = cur.fetchone()

            cur.execute(
                "select nombre_completo, estado, email_principal "
                "  from pacs.realtors where sf_lead_id is null "
                " order by estado nulls last, nombre_completo")
            huerfanos = cur.fetchall()

            cur.execute("select clave_resolucion, count(*) from pacs.realtors "
                        " group by 1 order by 2 desc")
            por_clave = cur.fetchall()

    print("")
    print("=" * 74)
    print("RESULTADO, contado en la base")
    print("=" * 74)
    print("  realtors                 : %d" % total)
    print("  con sf_lead_id           : %d (%.1f%%)"
          % (con_lead, 100.0 * con_lead / total))
    print("  sin_llave_dura = true    : %d (%.1f%%)"
          % (sin_llave, 100.0 * sin_llave / total))
    print("")
    print("  clave de resolucion:")
    for clave, n in por_clave:
        print("      %-24s %5d" % (clave, n))

    print("")
    print("=" * 74)
    print("LOS %d QUE NO CRUZAN · cola de revision manual" % len(huerfanos))
    print("=" * 74)
    print("%-32s %-6s %s" % ("nombre", "estado", "email"))
    for nombre, estado, email in huerfanos:
        print("%-32s %-6s %s" % (str(nombre)[:32], estado or "-", email or "SIN EMAIL"))

    salida = os.path.join(RAIZ, "data", "sf_sin_cruce.csv")
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    import csv
    with open(salida, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["nombre", "estado", "email"])
        w.writerows(huerfanos)
    print("")
    print("y en %s" % salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
