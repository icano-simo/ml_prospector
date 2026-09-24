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
from motor.desde_instagram import (  # noqa: E402
    bio_legible,
    categorias_acreditadas,
    combinar_con_el_libro,
    senales_de,
)
from motor.entrada import limpiar_entrada  # noqa: E402
from motor.evaluar import evaluar  # noqa: E402
from motor.exclusion import clasificar  # noqa: E402
from motor.veredicto import puede_contactarse  # noqa: E402
from captura.parser_mm import unir_perfiles  # noqa: E402
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
    # `R7 Identidad hispana` NO se mapea desde el 2026-09-23. Se calculaba desde
    # el apellido y el nombre de pila -- base censal de apellidos con >=75% de
    # portadores hispanos, mas heuristica patronimica -ez/-es/-az/-iz/-oz-- y el
    # libro la define como «probabilidad de que el realtor pertenezca a la
    # comunidad latina». Es inferencia de origen: ECOA Regulation B.
    #
    # `R6 Broker latino` tampoco se mapea, y nunca se mapeo. Suma 2 puntos «si
    # el nombre contiene un apellido hispano», asi que habria que sacarla --
    # pero no hay nada que sacar: jamas llego al motor.
    #
    # Ver docs/r7-identidad-hispana.md.
    "E6 Asequibilidad": "E6_asequibilidad",
    "E3 Urgencia sept (no pond.)": "E3_urgencia_sept",
    "Unidades/ano": "unidades_ano", "IG seguidores": "ig_seguidores",
}
BOOLEANOS = {c for c in MAPA.values()
             if c.startswith("ev2_") and c != "ev2_volumen_declarado_bio"}
BOOLEANOS.add("ev_bio_legible")

#: Lo que falta hoy y que la evaluacion tiene que declarar, no omitir.
#: Lo que el motor TODAVIA no mira. `senales_instagram` salio de esta lista el
#: 2026-09-23, cuando se cargaron los 298 perfiles y se conecto
#: `motor.desde_instagram`. Mientras estuvo aqui, cargar Instagram a la base no
#: movia ni un numero -- el motor no lo leia.
FALTAN_HOY = ("contrastes_de_mercado",)

#: Lo que el motor toma del perfil de Model Match.
#:
#: `mm_buyside_anualizado` lo piden DOS reglas -- P-Q11-2, que es la produccion
#: que manda, y P-Q11-3, que solo aplica cuando NO hay Model Match-- y nunca
#: llegaba: `correr_motor` usaba el perfil para el veredicto y no lo metia al
#: registro. O sea que P-Q11-2 no podia activarse nunca, y todos caian en
#: P-Q11-3 «segun el libro», que no distingue lado ni ventana.
#:
#: Es la misma forma de siempre: el dato existia, la regla existia, y nadie las
#: unia. Nada fallaba.
DEL_PERFIL_MM = {"buyside_anualizado": "mm_buyside_anualizado"}

#: Los `mm_*` que NO se copian de un campo sino que se calculan aqui.
DERIVADOS_MM = ("mm_share_buy",)


def _share_del_grano(perfil: dict | None) -> float | None:
    """El share contando operaciones de la pestaña Transactions, si la hay."""
    from captura.transacciones import resumen, share_buy_de_transacciones

    tx = (perfil or {}).get("transacciones")
    if not isinstance(tx, dict) or not tx.get("filas"):
        return None
    # Con paginas de menos no se calcula: 25 filas de 137 dan un share de una
    # quinta parte del negocio, y sale con la misma cara que el de verdad.
    if tx.get("faltan_paginas"):
        return None
    return share_buy_de_transacciones(resumen(tx))

#: Todos los `mm_*` que este modulo puede producir. `motor.reevaluacion` lo usa
#: para saber que NO heredar de la evaluacion anterior: un campo de Model Match
#: que no este aca se arrastraria para siempre desde la `entrada` vieja, y una
#: captura nueva no lo movería.
CAMPOS_MM = tuple(DEL_PERFIL_MM.values()) + DERIVADOS_MM


def share_del_lado_comprador(perfil: dict | None) -> float | None:
    """Fraccion de operaciones del lado comprador. Del grano si lo hay.

    Dos fuentes, en orden, y el orden es la regla de siempre: **el grano manda
    sobre el resumen.**

    1 · la pestaña Transactions, contando operaciones una por una. El lado sale
        de en que columna aparece su nombre, asi que es un conteo y no una
        lectura de un resumen ajeno;
    2 · `Side Focus` del Overview -- «3 buy / 0 sell».

    Las dos discrepan en las capturas medidas, y no poco: un perfil con Side
    Focus «3 buy / 0 sell» tiene 9 unidades compradoras y 3 listings vendidos.
    Son ventanas distintas del mismo negocio, y por eso hay un orden declarado
    en vez de un promedio.

    `buyer_units` y `listing_sold` NO se usan como tercera fuente: cuentan
    cosas con otro denominador, y una derivacion que da un numero parecido pero
    distinto es peor que no tenerla, porque nadie sabe cual leyo el motor.

    Devuelve `None` --no cero-- cuando no hay ninguna de las dos.
    """
    del_grano = _share_del_grano(perfil)
    if del_grano is not None:
        return del_grano

    buy = (perfil or {}).get("sf_buy")
    sell = (perfil or {}).get("sf_sell")
    if buy is None or sell is None:
        return None
    total = buy + sell
    if total <= 0:
        return None
    return round(buy / float(total), 4)


def campos_de_modelmatch(perfil: dict | None) -> dict:
    """Los `mm_*` que el motor entiende. Solo lo que tiene valor."""
    salida = {}
    for origen, campo in DEL_PERFIL_MM.items():
        v = (perfil or {}).get(origen)
        if v is not None:
            salida[campo] = v
    share = share_del_lado_comprador(perfil)
    if share is not None:
        salida["mm_share_buy"] = share
    return salida

#: Las dos columnas del libro que deciden si una persona es contactable. NO
#: entran al registro que evalua el motor -- no son evidencia, son una decision
#: ya tomada aguas arriba. Viajan aparte, a su propia columna de la evaluacion.
COL_NIVEL = "pacs: nivel_de_calificacion"
COL_MOTIVO = "pacs: motivo_si_descartado"


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

    # Sin la columna de nivel el motor NO puede saber a quien no contactar.
    # Seguir sin ella es volver al estado en que Lisa Munoz salia con dolor
    # primario y confianza MEDIA, lista para una cola de envio. Se para aca.
    faltan = [c for c in (COL_NIVEL, COL_MOTIVO) if c not in df.columns]
    if faltan:
        print("el libro no trae %s: sin eso no hay exclusion que aplicar"
              % faltan)
        return 1

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("select lower(email_principal), id from pacs.realtors "
                        " where email_principal is not null")
            por_email = {e: str(i) for e, i in cur.fetchall()}
            cur.execute("select count(*) from pacs.realtors")
            total_realtors = cur.fetchone()[0]

            # Las señales de Instagram, por realtor, CON SU CLASE.
            #
            # La clase viene de `v_ig_clase_actual`, donde la auditoria manual
            # gana sobre la automatica. Sin este join el motor la recalcularia,
            # y recalcularla es ignorar la auditoria: alguien miro 55 perfiles a
            # mano y el motor decidiria por su cuenta igual.
            cur.execute("""
                select s.realtor_id::text, s.estado_perfil, s.captions_n,
                       s.comentarios_n, s.senales,
                       c.clase, c.motivo, c.origen
                  from pacs.v_ig_senales_current s
                  left join pacs.v_ig_clase_actual c
                         on c.realtor_id = s.realtor_id
                 where s.realtor_id is not null
            """)
            ig = {r[0]: {"estado_perfil": r[1], "captions_n": r[2],
                         "comentarios_n": r[3], "senales": r[4],
                         "clase_perfil": r[5], "clase_motivo": r[6],
                         "clase_origen": r[7]}
                  for r in cur.fetchall()}

    print("realtors: %d · con email para cruzar: %d" % (total_realtors, len(por_email)))
    print("con señales de Instagram: %d" % len(ig))

    # Quien tiene captura de Model Match viva: es un termino de la confianza.
    with conectar() as conn:
        with conn.cursor() as cur:
            # No basta con SABER quien tiene captura: hace falta su perfil, que
            # es lo que decide si trabaja con originadores de la casa. Antes
            # solo se leia el id, asi que la exclusion por no-canibalizacion no
            # podia evaluarse aqui de ninguna manera.
            cur.execute("""
                select parseado->>'realtor_id', parseado->'perfil',
                       capturado_en
                  from pacs.v_capturas_modelmatch_current
                 where parseado->>'realtor_id' is not null
                   and parseado->'perfil' is not null
                 order by capturado_en
            """)
            por_realtor: dict = {}
            for rid_mm, perfil_mm, cuando in cur.fetchall():
                por_realtor.setdefault(rid_mm, []).append((perfil_mm, cuando))
    # El perfil de Model Match vive repartido en varias filas -- Overview,
    # Originators, Lenders-- y `orig_buyer` esta solo en una. Sin unir, el
    # reparto por unidades no aparece y todo el lote saldria `pendiente`.
    perfiles_mm = {}
    for rid_mm, trozos in por_realtor.items():
        unido = unir_perfiles([p for p, _c in trozos if isinstance(p, dict)])
        if unido:
            unido["capturado_en"] = str(trozos[-1][1])
        perfiles_mm[rid_mm] = unido
    con_modelmatch = set(perfiles_mm)
    print("con captura de Model Match: %d" % len(con_modelmatch))

    filas = []
    sin_cruce = 0
    con_instagram = 0
    sacados_alguna_vez: set[str] = set()
    excluidos: dict[str, int] = {}
    for _, r in df.iterrows():
        em = r.get("Email")
        em = str(em).strip().lower() if not pd.isna(em) else None
        rid = por_email.get(em) if em else None
        if not rid:
            sin_cruce += 1
            continue

        reg, sacados = registro_de(r, pd)
        sacados_alguna_vez.update(sacados)

        # ── LA EXCLUSION ────────────────────────────────────────────────────
        # Se lee del libro, no se deduce de los qualifiers. Y NO entra a `reg`:
        # no es evidencia que el motor deba pesar, es una decision ya tomada
        # que gobierna la salida. La evaluacion se calcula igual -- el raspado
        # y el diagnostico no estorban -- pero la fila sale marcada.
        excluido = clasificar(r.get(COL_NIVEL))
        motivo = r.get(COL_MOTIVO)
        motivo = (None if motivo is None or pd.isna(motivo)
                  else str(motivo).strip() or None)
        if excluido:
            excluidos[excluido] = excluidos.get(excluido, 0) + 1

        # ── INSTAGRAM ────────────────────────────────────────────────────────
        # El libro no se pisa: Instagram confirma o agrega, nunca borra. Son
        # dos lecturas de momentos distintos, y un True del libro que hoy no se
        # ve no es un False.
        fila_ig = ig.get(rid)
        cats, bio_ig = set(), None
        if fila_ig:
            reg = combinar_con_el_libro(reg, senales_de(fila_ig))
            cats = categorias_acreditadas(fila_ig)
            bio_ig = bio_legible(fila_ig)
            con_instagram += 1

        # ── MODEL MATCH ──────────────────────────────────────────────────────
        # La produccion anualizada del lado comprador, que es la que manda para
        # la compuerta. Sin esto P-Q11-2 no se activaba nunca.
        reg.update(campos_de_modelmatch(perfiles_mm.get(rid)))

        ev = evaluar(reg, realtor_id=rid)
        conf = evaluar_confianza(
            ev,
            categorias_acreditadas=cats,
            # `None` cuando no se pudo mirar: no se llena por descarte.
            bio_legible=(bio_ig if bio_ig is not None
                         else reg.get("ev_bio_legible")),
            modelmatch_capturado=rid in con_modelmatch,
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
            "excluido": excluido,
            "excluido_motivo": motivo if excluido else None,
            # El veredicto de contacto, con la MISMA compuerta que usan
            # /api/dossier, /api/extracto y guardar_texto. Sin captura de Model
            # Match es `pendiente_modelmatch`, que es el estado normal de casi
            # todo el lote: la evaluacion se guarda igual y dice que le falta.
            "veredicto_contacto": puede_contactarse(
                perfiles_mm.get(rid),
                capturado_en=(perfiles_mm.get(rid) or {}).get("capturado_en"),
                excluido_por_el_libro=excluido,
                motivo_del_libro=motivo).a_dict(),
        })

    print("evaluaciones a escribir: %d · filas del libro sin cruce: %d"
          % (len(filas), sin_cruce))
    print("campos sacados por ECOA: %s" % (sorted(sacados_alguna_vez) or "ninguno"))
    print("")

    from supabase.cargar import cargar
    res = cargar("evaluaciones", filas, fuente="libro_v3",
                 archivo="motor " + filas[0]["version_reglas"],
                 nota="con señales de Instagram (%d perfiles) y exclusion del "
                      "libro aplicada. Sin contrastes de mercado. Declarado en "
                      "campos_ausentes de cada fila." % con_instagram)
    print(res)

    # Se lee de la VISTA, no de la tabla. `evaluaciones` es append-only, asi que
    # contarla cuenta CORRIDAS y no personas -- y eso ya produjo un reporte con
    # 8.374 evaluaciones y un 34,8% que mezclaba dos pasadas. El numero real era
    # 40,4%.
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from pacs.v_evaluacion_actual")
            n = cur.fetchone()[0]
            cur.execute("select count(*) from pacs.v_evaluacion_actual "
                        " where dolor_primario is null")
            sin_dolor = cur.fetchone()[0]
            cur.execute("select dolor_primario, count(*) "
                        "  from pacs.v_evaluacion_actual "
                        " group by 1 order by 2 desc limit 12")
            top = cur.fetchall()
            cur.execute("select confianza->>'nivel', count(*) "
                        "  from pacs.v_evaluacion_actual "
                        " group by 1 order by 2 desc")
            niveles = cur.fetchall()
            cur.execute("select count(distinct version_reglas), "
                        "       count(distinct huella_reglas) "
                        "  from pacs.v_evaluacion_actual")
            n_ver, n_huella = cur.fetchone()
            cur.execute("select excluido, count(*), "
                        "       count(*) filter (where dolor_primario is not null) "
                        "  from pacs.v_evaluacion_actual "
                        " where excluido is not null group by 1 order by 2 desc")
            exc = cur.fetchall()
            cur.execute("select count(*) from pacs.v_evaluacion_actual "
                        " where excluido is null")
            contactables = cur.fetchone()[0]

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
    print("")
    print("  excluidos por metodologia (NO entran a ninguna cola):")
    for motivo, c, con_dolor in exc:
        # `con_dolor` no es un problema: el diagnostico se calcula igual. Es el
        # numero que antes los metia a la cola, y ahora solo queda de registro.
        print("      %-28s %5d   (con dolor primario: %d)"
              % (motivo, c, con_dolor))
    print("      %-28s %5d" % ("contactables", contactables))
    return 0


if __name__ == "__main__":
    sys.exit(main())
