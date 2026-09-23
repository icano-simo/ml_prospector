"""Vuelve a evaluar a UN realtor y escribe la evaluación nueva.

Por que existe
--------------
Al guardar una captura de Model Match el diagnostico no se movia. La captura
entraba, los mercados se promovian, el veredicto cambiaba -- y `dolor_primario`
seguia siendo el de la corrida anterior, calculado sin Model Match. La pantalla
mostraba el perfil nuevo al lado del diagnostico viejo y nada decia que no se
correspondian.

Correr `correr_motor.py` entero para eso son 4.187 evaluaciones y varios
minutos. Esto corre UNA.

Que NO hace
-----------
No pisa nada. `pacs.evaluaciones` es append-only y la vista se queda con la mas
reciente: la anterior sigue ahi como historico. Y usa la MISMA
`VERSION_REGLAS`, asi que la fila nueva no queda marcada «pendiente de
re-evaluar» -- que es lo que pasaria si se escribiera con otra version.

Si algo falla, NO tumba el guardado. El crudo ya esta en la base y se puede
re-evaluar despues; perder la captura por un error al recalcular seria cambiar
un problema chico por uno caro.
"""
from __future__ import annotations

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from captura.parser_mm import unir_perfiles  # noqa: E402
from motor.confianza import evaluar_confianza  # noqa: E402
from motor.desde_instagram import (  # noqa: E402
    bio_legible,
    categorias_acreditadas,
    combinar_con_el_libro,
    senales_de,
)
from motor.evaluar import VERSION_REGLAS, evaluar  # noqa: E402
from motor.exclusion import clasificar  # noqa: E402
from motor.veredicto import puede_contactarse  # noqa: E402
from supabase.correr_motor import (  # noqa: E402
    COL_MOTIVO,
    COL_NIVEL,
    FALTAN_HOY,
    LIBRO,
    campos_de_modelmatch,
    registro_de,
)


class NoSePudoReevaluar(RuntimeError):
    """Algo falto para recalcular. NUNCA tumba el guardado."""


def _fila_del_libro(email: str):
    """La fila del libro v3 de este realtor, por email.

    Se lee el Excel entero, que tarda unos segundos. Es el precio de que el
    libro sea la fuente de la evidencia y viva en un archivo; cuando esas
    columnas esten en la base, esto es una consulta.
    """
    import pandas as pd

    df = pd.read_excel(LIBRO, sheet_name="Realtors PACS")
    em = (email or "").strip().lower()
    for _, r in df.iterrows():
        v = r.get("Email")
        if not pd.isna(v) and str(v).strip().lower() == em:
            return r, pd
    return None, pd


def reevaluar(realtor_id: str, *, conexion) -> dict:
    """Recalcula y escribe UNA evaluación. Devuelve lo que cambió."""
    cur = conexion.cursor()
    cur.execute("select email_principal from pacs.realtors where id = %s",
                (realtor_id,))
    f = cur.fetchone()
    if not f or not f[0]:
        raise NoSePudoReevaluar(
            "el realtor no tiene email, que es lo unico que lo une al libro v3")
    email = f[0]

    fila, pd = _fila_del_libro(email)
    if fila is None:
        raise NoSePudoReevaluar("no esta en el libro v3 (cruce por email)")

    reg, _sacados = registro_de(fila, pd)

    # Instagram, con su compuerta de perfil.
    cur.execute("""
        select s.estado_perfil, s.captions_n, s.comentarios_n, s.senales,
               c.clase, c.motivo
          from pacs.v_ig_senales_current s
          left join pacs.v_ig_clase_actual c on c.realtor_id = s.realtor_id
         where s.realtor_id = %s
    """, (realtor_id,))
    r_ig = cur.fetchone()
    cats, bio_ig = set(), None
    if r_ig:
        fila_ig = {"estado_perfil": r_ig[0], "captions_n": r_ig[1],
                   "comentarios_n": r_ig[2], "senales": r_ig[3],
                   "clase_perfil": r_ig[4], "clase_motivo": r_ig[5]}
        reg = combinar_con_el_libro(reg, senales_de(fila_ig))
        cats = categorias_acreditadas(fila_ig)
        bio_ig = bio_legible(fila_ig)

    # Model Match: el perfil unido de la captura VIGENTE.
    cur.execute("""
        select parseado->'perfil', capturado_en
          from pacs.v_capturas_modelmatch_current
         where realtor_id = %s and parseado->'perfil' is not null
         order by capturado_en
    """, (realtor_id,))
    trozos = cur.fetchall()
    perfil_mm = unir_perfiles([p for p, _c in trozos if isinstance(p, dict)])
    if perfil_mm and trozos:
        perfil_mm["capturado_en"] = str(trozos[-1][1])
    reg.update(campos_de_modelmatch(perfil_mm))

    # La exclusion del libro.
    excluido = clasificar(fila.get(COL_NIVEL))
    motivo = fila.get(COL_MOTIVO)
    motivo = (None if motivo is None or pd.isna(motivo)
              else str(motivo).strip() or None)

    ev = evaluar(reg, realtor_id=realtor_id)
    conf = evaluar_confianza(
        ev, categorias_acreditadas=cats,
        bio_legible=(bio_ig if bio_ig is not None else reg.get("ev_bio_legible")),
        modelmatch_capturado=bool(perfil_mm))
    ver = puede_contactarse(
        perfil_mm or None,
        capturado_en=(perfil_mm or {}).get("capturado_en"),
        excluido_por_el_libro=excluido, motivo_del_libro=motivo)

    cur.execute("""
        select dolor_primario, veredicto_contacto->>'estado', version_reglas
          from pacs.v_evaluacion_actual where realtor_id = %s
    """, (realtor_id,))
    antes = cur.fetchone() or (None, None, None)

    d = json.loads(ev.a_json())
    cur.execute("""
        insert into pacs.evaluaciones
            (realtor_id, version_reglas, huella_reglas, resultado,
             dolor_primario, dolores_secundarios, moduladores, apertura,
             gating_qualifier, gating_intensidad, no_evaluadas,
             campos_ausentes, confianza, entrada, excluido, excluido_motivo,
             veredicto_contacto)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (realtor_id, ev.version_reglas, ev.huella_reglas, json.dumps(d),
          ev.dolor_primario, list(ev.dolores_secundarios),
          list(ev.moduladores), ev.apertura,
          ev.gating.qualifier if ev.gating else None,
          ev.gating.intensidad if ev.gating else None,
          json.dumps(d["no_evaluadas"]),
          list(ev.campos_ausentes) + list(FALTAN_HOY),
          json.dumps(conf.a_dict()), json.dumps(reg, default=str),
          excluido, motivo if excluido else None,
          json.dumps(ver.a_dict(), default=str)))
    conexion.commit()

    return {
        "dolor_antes": antes[0], "dolor_ahora": ev.dolor_primario,
        "veredicto_antes": antes[1], "veredicto_ahora": ver.estado,
        "version_reglas": VERSION_REGLAS,
        "cambio": (antes[0] != ev.dolor_primario or antes[1] != ver.estado),
        "mm_buyside_anualizado": reg.get("mm_buyside_anualizado"),
    }
