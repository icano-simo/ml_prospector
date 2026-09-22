"""Corre el motor sobre los realtors cargados y escribe pacs.evaluaciones.

Los campos de evidencia viven en el libro v3, no en `pacs.realtors` -- ahi solo
se cargo identidad. El cruce es por email, que es lo unico que une las dos
cosas hoy; las filas sin email quedan sin evaluar y se reportan.

Los contrastes NO corren aca. Necesitan `pacs.mercados`, y hoy esta vacia. La
evaluacion se guarda igual, con `campos_ausentes` diciendo que falto: una
evaluacion sin contrastes es una evaluacion incompleta declarada, no una
evaluacion mala.
"""
from __future__ import annotations

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.confianza import evaluar_confianza  # noqa: E402
from motor.entrada import limpiar_entrada  # noqa: E402
from motor.evaluar import evaluar  # noqa: E402
from supabase.cargar import conectar  # noqa: E402

LIBRO = os.path.join(RAIZ, "Data_inputIA",
                     "Homesi_Scoring_Realtors_v3_PACS (2).xlsx")

#: columna del libro -> campo del motor
MAPA = {
    "ev2: itin": "ev2_itin", "ev2: self_employed": "ev2_self_employed",
    "ev2: va_militar": "ev2_va_militar", "ev2: inversion": "ev2_inversion",
    "ev2: credito": "ev2_credito", "ev2: dpa_enganche": "ev2_dpa_enganche",
    "ev2: fha_gob": "ev2_fha_gob", "ev2: precalificacion": "ev2_precalificacion",
    "ev2: equipo": "ev2_equipo", "ev2: video_contenido": "ev2_video_contenido",
    "ev2: educacion": "ev2_educacion", "ev2: testimonio": "ev2_testimonio",
    "ev2: fe_familia": "ev2_fe_familia", "ev2: espanol_decl": "ev2_espanol_decl",
    "ev2: primera_casa": "ev2_primera_casa", "ev2: comunidad": "ev2_comunidad",
    "ev2: listing_side": "ev2_listing_side", "ev2: buy_side": "ev2_buy_side",
    "ev2: volumen_declarado_bio": "ev2_volumen_declarado_bio",
    "ev: bio legible": "ev_bio_legible",
    "ev: hits lujo/inversion": "ev_hits_lujo_inversion",
    "ev: caracteres espanol": "ev_caracteres_espanol",
    "R4 Comunidad / FHB": "R4_comunidad_fhb", "R5 Espanol": "R5_espanol",
    "R7 Identidad hispana": "R7_identidad_hispana",
    "E6 Asequibilidad": "E6_asequibilidad",
    "E3 Urgencia sept (no pond.)": "E3_urgencia_sept",
    "Unidades/ano": "unidades_ano", "IG seguidores": "ig_seguidores",
}
BOOLEANOS = {c for c in MAPA.values()
             if c.startswith("ev2_") and c != "ev2_volumen_declarado_bio"}
BOOLEANOS.add("ev_bio_legible")

#: Lo que falta hoy y que la evaluacion tiene que declarar, no omitir.
FALTAN_HOY = ("contrastes_de_mercado", "senales_instagram", "modelmatch")


def registro_de(fila, pd):
    reg = {}
    for col, campo in MAPA.items():
        v = fila[col]
        if not pd.isna(v):
            reg[campo] = bool(v) if campo in BOOLEANOS else v
    limpio, sacados = limpiar_entrada(reg)
    return limpio, sacados


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import pandas as pd

    df = pd.read_excel(LIBRO, sheet_name="Realtors PACS")

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("select lower(email_principal), id from pacs.realtors "
                        " where email_principal is not null")
            por_email = {e: str(i) for e, i in cur.fetchall()}
            cur.execute("select count(*) from pacs.realtors")
            total_realtors = cur.fetchone()[0]

    print("realtors: %d · con email para cruzar: %d" % (total_realtors, len(por_email)))

    filas = []
    sin_cruce = 0
    sacados_alguna_vez: set[str] = set()
    for _, r in df.iterrows():
        em = r.get("Email")
        em = str(em).strip().lower() if not pd.isna(em) else None
        rid = por_email.get(em) if em else None
        if not rid:
            sin_cruce += 1
            continue

        reg, sacados = registro_de(r, pd)
        sacados_alguna_vez.update(sacados)
        ev = evaluar(reg, realtor_id=rid)
        conf = evaluar_confianza(
            ev,
            categorias_acreditadas=set(),
            bio_legible=reg.get("ev_bio_legible"),
            modelmatch_capturado=False,
        )
        d = json.loads(ev.a_json())
        filas.append({
            "realtor_id": rid,
            "version_reglas": ev.version_reglas,
            "huella_reglas": ev.huella_reglas,
            "resultado": d,
            "dolor_primario": ev.dolor_primario,
            "dolores_secundarios": list(ev.dolores_secundarios),
            "moduladores": list(ev.moduladores),
            "apertura": ev.apertura,
            "gating_qualifier": ev.gating.qualifier if ev.gating else None,
            "gating_intensidad": ev.gating.intensidad if ev.gating else None,
            "no_evaluadas": d["no_evaluadas"],
            "campos_ausentes": list(ev.campos_ausentes) + list(FALTAN_HOY),
            "confianza": conf.a_dict(),
            "entrada": reg,
        })

    print("evaluaciones a escribir: %d · filas del libro sin cruce: %d"
          % (len(filas), sin_cruce))
    print("campos sacados por ECOA: %s" % (sorted(sacados_alguna_vez) or "ninguno"))
    print("")

    from supabase.cargar import cargar
    res = cargar("evaluaciones", filas, fuente="libro_v3",
                 archivo="motor " + filas[0]["version_reglas"],
                 nota="sin contrastes: pacs.mercados vacia. Sin Instagram ni "
                      "Model Match. Declarado en campos_ausentes de cada fila.")
    print(res)

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from pacs.evaluaciones")
            n = cur.fetchone()[0]
            cur.execute("select count(*) from pacs.evaluaciones "
                        " where dolor_primario is null")
            sin_dolor = cur.fetchone()[0]
            cur.execute("select dolor_primario, count(*) from pacs.evaluaciones "
                        " group by 1 order by 2 desc limit 10")
            top = cur.fetchall()
            cur.execute("select confianza->>'nivel', count(*) "
                        "  from pacs.evaluaciones group by 1 order by 2 desc")
            niveles = cur.fetchall()
            cur.execute("select count(distinct version_reglas), "
                        "       count(distinct huella_reglas) "
                        "  from pacs.evaluaciones")
            n_ver, n_huella = cur.fetchone()

    print("")
    print("=" * 66)
    print("RESULTADO, contado en la base")
    print("=" * 66)
    print("  evaluaciones            : %d" % n)
    print("  SIN dolor primario      : %d (%.1f%%)  <- comparar con 28,9%%"
          % (sin_dolor, 100.0 * sin_dolor / n))
    print("  version_reglas distintas: %d · huellas distintas: %d"
          % (n_ver, n_huella))
    print("")
    print("  dolor primario:")
    for q, c in top:
        print("      %-28s %5d  (%.1f%%)"
              % (q or "(ninguno)", c, 100.0 * c / n))
    print("")
    print("  confianza:")
    for niv, c in niveles:
        print("      %-8s %5d" % (niv, c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
