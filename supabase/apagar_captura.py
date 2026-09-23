"""Apaga la captura de un realtor por la via disenada: es_vigente = false.

    python supabase/apagar_captura.py <realtor_id> "la razon"
    python supabase/apagar_captura.py <realtor_id> "la razon" --aplicar

Sin DELETE. El crudo queda como historico y la razon queda en la nota del lote:
`es_vigente = false` dice "no cuenta" y no dice POR QUE, y eso ya costo analizar
payloads de ensayo como si fueran capturas.

Cuando usarlo
-------------
Desde que `capturas_que_mandan` existe, dos capturas vivas NO compiten: manda la
mas reciente y la anterior queda como historico. Asi que esto no hace falta para
re-capturar.

Sirve para lo otro: cuando la captura anterior es MALA -- se pego a medias, se
capturo el realtor equivocado, o le falta algo que la hace enganosa-- y no se
quiere ni como historico vivo.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import psycopg  # noqa: E402

from supabase.config import cargar_env  # noqa: E402


def main(realtor_id: str, razon: str, aplicar: bool) -> int:
    if not razon.strip():
        print("hace falta una razon: `es_vigente=false` sin por que es lo que "
              "hizo analizar ensayos como capturas")
        return 1
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL")
        return 1

    nota = "[APAGADA %s] %s" % (dt.date.today().isoformat(), razon.strip())

    with psycopg.connect(url) as con:
        cur = con.cursor()
        cur.execute("""
            select distinct c.upload_batch_id, b.uploaded_at, b.es_vigente,
                   count(*) over (partition by c.upload_batch_id)
              from pacs.capturas_modelmatch c
              join pacs.upload_batch b on b.id = c.upload_batch_id
             where c.parseado->>'realtor_id' = %s
             order by b.uploaded_at
        """, (realtor_id,))
        lotes = cur.fetchall()
        if not lotes:
            print("ese realtor no tiene capturas")
            return 1

        print("capturas de %s" % realtor_id)
        for lid, cuando, vig, n in lotes:
            print("   %s  %s  vigente=%s  %d filas"
                  % (str(lid)[:8], str(cuando)[:19], vig, n))

        vivos = [l for l in lotes if l[2]]
        print("")
        print("a apagar: %d lote%s" % (len(vivos), "" if len(vivos) == 1 else "s"))
        if not vivos:
            print("no hay ninguno vigente")
            return 0
        if not aplicar:
            print("\n(solo muestra; pasar --aplicar para escribir)")
            return 0

        for lid, _c, _v, _n in vivos:
            cur.execute("""
                update pacs.upload_batch
                   set es_vigente = false,
                       nota = coalesce(nota || ' | ', '') || %s
                 where id = %s
            """, (nota, lid))
        con.commit()

        # El DESPUES, leido de la base.
        cur.execute("""
            select count(*) from pacs.v_capturas_modelmatch_current
             where parseado->>'realtor_id' = %s
        """, (realtor_id,))
        vivas = cur.fetchone()[0]
        cur.execute("""
            select count(*) from pacs.capturas_modelmatch
             where parseado->>'realtor_id' = %s
        """, (realtor_id,))
        hist = cur.fetchone()[0]
        print("")
        print("DESPUES, leido de la base")
        print("   filas vivas    : %d" % vivas)
        print("   en el historico: %d  (el crudo no se toca)" % hist)
        print("   nota: %s" % nota)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2], "--aplicar" in sys.argv))
