"""Trae los condados del ACS de los estados del lote y los carga en pacs.

    python supabase/cargar_census.py            # solo muestra
    python supabase/cargar_census.py --aplicar

Los estados NO van escritos a mano: salen de `pacs.realtors`, que es quien sabe
donde opera el lote. Escribirlos a mano es como se queda corta una lista: hoy
son 34 y el plan hablaba de 22.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import psycopg  # noqa: E402

from captura.estados import ESTADOS, normalizar_estado  # noqa: E402
from geo import census  # noqa: E402
from supabase.config import cargar_env  # noqa: E402

#: codigo de estado -> FIPS. De la lista oficial del Census.
FIPS_DE_ESTADO = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56", "PR": "72",
}

#: Los condados prioritarios, para poder decir si entraron.
PRIORITARIOS = [
    ("Cook", "IL"), ("Harris", "TX"), ("Dallas", "TX"), ("Bexar", "TX"),
    ("Travis", "TX"), ("Los Angeles", "CA"), ("Riverside", "CA"),
    ("Maricopa", "AZ"), ("Clark", "NV"), ("Miami-Dade", "FL"),
]


def estados_del_lote(cur) -> list[tuple[str, str, int]]:
    """(codigo, nombre, realtors) de lo que hay en el libro, no de una lista."""
    cur.execute("""
        select estado, count(*) from pacs.realtors
         where estado is not null group by 1 order by 2 desc
    """)
    salida, sin_codigo = [], []
    for nombre, n in cur.fetchall():
        cod = normalizar_estado(nombre)
        if cod and cod in FIPS_DE_ESTADO:
            salida.append((cod, nombre, n))
        else:
            sin_codigo.append((nombre, n))
    if sin_codigo:
        print("   OJO · sin FIPS y por lo tanto SIN Census: %s" % sin_codigo)
    return salida


def main(aplicar: bool) -> int:
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL")
        return 1

    # La clave se comprueba ANTES de la primera peticion: un error de forma se
    # ve aca y no como un HTML de rechazo treinta consultas despues.
    clave = census.clave_del_entorno()
    print("clave del Census: %d caracteres, %s…%s"
          % (len(clave), clave[:4], clave[-4:]))

    with psycopg.connect(url) as con:
        cur = con.cursor()
        estados = estados_del_lote(cur)
        print("estados del lote: %d · %d realtors"
              % (len(estados), sum(n for _c, _n, n in estados)))

        cur.execute("select count(*) from pacs.census_condados")
        print("condados ya cargados: %d" % cur.fetchone()[0])

        if not aplicar:
            print("\n(solo muestra; pasar --aplicar para bajar y cargar)")
            print("se pedirian %d consultas, una por estado" % len(estados))
            return 0

        todos: list[dict] = []
        for cod, nombre, n in estados:
            fips = FIPS_DE_ESTADO[cod]
            try:
                condados = census.condados_de_estado(fips, clave=clave)
            except census.CensusRechazo as exc:
                print("   %-4s %-22s RECHAZO: %s"
                      % (cod, nombre, str(exc).split("\n")[0]))
                return 1
            todos.extend(condados)
            print("   %-4s %-22s %4d condados  (%d realtors)"
                  % (cod, nombre, len(condados), n))

        print("\ntotal: %d condados" % len(todos))

        # Una guarda con denominador: si el ingreso medio vino nulo en todos,
        # el centinela se comio la columna y es mejor no cargar nada.
        con_ingreso = sum(1 for c in todos
                          if c["variables"].get("ingreso_medio_hogar"))
        print("con ingreso medio: %d de %d (%.0f%%)"
              % (con_ingreso, len(todos), 100.0 * con_ingreso / len(todos)))
        if con_ingreso < len(todos) * 0.9:
            print("ABORTADO: menos del 90%% trae ingreso. Algo se leyo mal.")
            return 1

        lote = str(uuid.uuid4())
        cur.execute("""
            insert into pacs.upload_batch
                (id, fuente, archivo, es_vigente, filas_esperadas, nota)
            values (%s, 'census', 'acs5 %s county', true, %s, %s)
        """, (lote, census.ANIO, len(todos),
              "condados de los %d estados del lote, variables de mercado"
              % len(estados)))

        for c in todos:
            cur.execute("""
                insert into pacs.census_condados
                    (condado_fips, estado, nombre, variables, anio_acs,
                     upload_batch_id)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (condado_fips) do update
                   set variables = excluded.variables,
                       anio_acs = excluded.anio_acs,
                       upload_batch_id = excluded.upload_batch_id,
                       uploaded_at = now()
            """, (c["condado_fips"],
                  {v: k for k, v in FIPS_DE_ESTADO.items()}.get(
                      c["estado_fips"], c["estado_fips"]),
                  c["nombre"],
                  json.dumps({**c["variables"], "_derivadas": c["derivadas"]}),
                  c["anio_acs"], lote))
        con.commit()

        # El DESPUES, leido de la base.
        cur.execute("select count(*), count(distinct estado) "
                    "from pacs.census_condados")
        n, e = cur.fetchone()
        print("\nDESPUES, leido de la base: %d condados en %d estados" % (n, e))

        print("\nLOS PRIORITARIOS")
        for nombre, cod in PRIORITARIOS:
            cur.execute("""
                select condado_fips, nombre,
                       variables->>'ingreso_medio_hogar',
                       variables->'_derivadas'->>'espanol_en_casa_pct'
                  from pacs.census_condados
                 where estado = %s and nombre ilike %s
            """, (cod, nombre + " %"))
            fila = cur.fetchone()
            if fila:
                print("   %-14s %-4s fips=%s  ingreso=%s  español=%s%%"
                      % (nombre, cod, fila[0], fila[2], fila[3]))
            else:
                print("   %-14s %-4s NO ENTRO" % (nombre, cod))
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--aplicar" in sys.argv))
