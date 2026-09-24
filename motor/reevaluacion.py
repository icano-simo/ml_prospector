"""Volver a evaluar a UN realtor, sin leer el libro y sin conexión directa.

Por qué no lee el libro
-----------------------
La primera versión abría el Excel con pandas. En Vercel eso NUNCA pudo
funcionar: `Data_inputIA/` está en `.gitignore`, así que el libro no viaja al
deploy, y `includeFiles` tampoco lo traería. El error que se vio --«Falta el
driver»-- era el primero de dos, y el segundo habría aparecido justo después.

No hace falta leerlo: los campos del libro YA están en `entrada` de la
evaluación anterior. El libro no cambia entre corridas; lo que cambia es Model
Match e Instagram. Así que se parte de lo guardado y se reponen esas dos capas.

Eso también lo hace más honesto: se re-evalúa con la MISMA evidencia del libro
con la que se evaluó antes, así que cualquier diferencia en el resultado viene
de la captura nueva y no de que alguien tocó el Excel entre medio.

Por qué no abre la conexión
---------------------------
Recibe un `lector` con `leer` y `escribir` -- los de `api/_comun`, que hablan
PostgREST. La consola le pasa un adaptador sobre psycopg. Así el módulo del
motor no sabe de drivers ni de credenciales, y no hay una segunda vía de acceso
a la base que haya que configurar en Vercel.
"""
from __future__ import annotations

import json

from motor.confianza import evaluar_confianza
from motor.desde_instagram import (
    bio_legible,
    categorias_acreditadas,
    combinar_con_el_libro,
    senales_de,
)
from motor.evaluar import VERSION_REGLAS, evaluar
from motor.veredicto import puede_contactarse

#: Lo que NO se hereda de la evaluación anterior porque se recalcula.
#: Todo lo demás --los `ev2_*`, las R y las E del libro-- se conserva tal cual.
#:
#: Solo van aquí los campos que **el libro no produce**. Esta lista tiene que
#: cubrir TODOS los `mm_*` que `campos_de_modelmatch` produce: uno que falte se
#: heredaría de la `entrada` vieja y la captura nueva no lo movería -- el valor
#: viejo ganaría en silencio, que es la peor forma. `test_reevaluacion` lo
#: comprueba contra `CAMPOS_MM`.
SE_RECALCULAN = ("mm_buyside_anualizado", "mm_share_buy",
                 "ig_idioma_es", "ig_idioma_posts")

#: `ig_seguidores` SALIO de esa lista el 2026-09-23, y no para recalcularlo de
#: otra forma sino para dejar de tocarlo.
#:
#: El libro v3 trae la columna `IG seguidores`, y en la corrida completa el
#: libro gana: `combinar_con_el_libro` no pisa un número que ya está. Isabella
#: decidió dejar eso como está. Pero la re-evaluación lo borraba de la base
#: heredada, así que a quien no tiene muro leído se le perdían los seguidores
#: del libro en cada captura, y las reglas que los leen pasaban de activarse a
#: «no evaluada» sin que nadie tocara un dato.
#:
#: Ahora las dos vías dicen lo mismo, que es el punto: una re-evaluación no
#: puede diferir de la corrida completa en algo que nadie decidió.


class NoSePudoReevaluar(RuntimeError):
    """Faltó algo para recalcular. NUNCA tumba el guardado de la captura."""


def base_del_libro(entrada_anterior: dict | None) -> dict:
    """La evidencia del libro, tal como quedó en la evaluación anterior."""
    if not entrada_anterior:
        raise NoSePudoReevaluar(
            "este realtor no tiene una evaluación anterior de la que partir. "
            "Corré el motor completo una vez antes de capturarlo.")
    return {k: v for k, v in entrada_anterior.items()
            if k not in SE_RECALCULAN}


def reevaluar(realtor_id: str, *, lector, guardar: bool = True) -> dict:
    """Recalcula y escribe UNA evaluación. Devuelve qué cambió.

    `lector` expone `leer(tabla, consulta)` y `escribir(tabla, filas)`.

    Con `guardar=False` hace todo menos la escritura: lee los mismos datos,
    aplica las mismas reglas y devuelve el mismo dict. Existe para medir el
    impacto de un cambio de reglas ANTES de que ese cambio esté desplegado --
    escribir una evaluación con una versión que producción todavía no corre
    deja el diagnóstico más nuevo marcado como «de una versión anterior» en la
    pantalla, que es peor que no tenerlo.

    Es el mismo camino, no una copia: una medición por un camino paralelo mide
    el camino paralelo.
    """
    from captura.parser_mm import unir_perfiles
    from supabase.correr_motor import campos_de_modelmatch

    _c, evs, _ = lector.leer(
        "v_evaluacion_actual",
        "?select=entrada,dolor_primario,excluido,excluido_motivo,"
        "veredicto_contacto,apertura,gating_intensidad,version_reglas"
        "&realtor_id=eq.%s" % realtor_id)
    anterior = (evs or [None])[0]
    if not anterior:
        # El MISMO mensaje que `base_del_libro`: son la misma causa, y dos
        # textos para una causa mandan a buscar dos cosas distintas.
        raise NoSePudoReevaluar(
            "este realtor no tiene una evaluación anterior de la que partir. "
            "Corré el motor completo una vez antes de capturarlo.")

    reg = base_del_libro(anterior.get("entrada"))
    excluido = anterior.get("excluido")
    motivo_libro = anterior.get("excluido_motivo")

    # ── Instagram, con su compuerta de perfil ───────────────────────────────
    _c, sen, _ = lector.leer(
        "v_ig_senales_current",
        "?select=estado_perfil,captions_n,comentarios_n,senales"
        "&realtor_id=eq.%s" % realtor_id)
    _c, cls, _ = lector.leer(
        "v_ig_clase_actual", "?select=clase,motivo&realtor_id=eq.%s" % realtor_id)
    cats, bio_ig = set(), None
    if sen:
        fila_ig = dict(sen[0])
        if cls:
            fila_ig["clase_perfil"] = cls[0].get("clase")
            fila_ig["clase_motivo"] = cls[0].get("motivo")
        reg = combinar_con_el_libro(reg, senales_de(fila_ig))
        cats = categorias_acreditadas(fila_ig)
        bio_ig = bio_legible(fila_ig)

    # ── Model Match: el perfil unido de la captura VIGENTE ──────────────────
    _c, caps, _ = lector.leer(
        "v_capturas_modelmatch_current",
        "?select=parseado,capturado_en&realtor_id=eq.%s"
        "&order=capturado_en.asc" % realtor_id)
    trozos = [(f.get("parseado") or {}).get("perfil") for f in (caps or [])]
    perfil_mm = unir_perfiles([p for p in trozos if isinstance(p, dict)])
    if perfil_mm and caps:
        perfil_mm["capturado_en"] = caps[-1].get("capturado_en")
    reg.update(campos_de_modelmatch(perfil_mm))

    ev = evaluar(reg, realtor_id=realtor_id)
    conf = evaluar_confianza(
        ev, categorias_acreditadas=cats,
        bio_legible=(bio_ig if bio_ig is not None
                     else reg.get("ev_bio_legible")),
        modelmatch_capturado=bool(perfil_mm))
    ver = puede_contactarse(
        perfil_mm or None,
        capturado_en=(perfil_mm or {}).get("capturado_en"),
        excluido_por_el_libro=excluido, motivo_del_libro=motivo_libro)

    d = json.loads(ev.a_json())
    fila = {
        "realtor_id": realtor_id,
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
        "campos_ausentes": list(ev.campos_ausentes) + ["contrastes_de_mercado"],
        "confianza": conf.a_dict(),
        "entrada": reg,
        "excluido": excluido,
        "excluido_motivo": motivo_libro if excluido else None,
        "veredicto_contacto": ver.a_dict(),
    }
    if guardar:
        cod, resp, _ = lector.escribir("evaluaciones", [fila], devolver=False)
        if cod >= 400:
            raise NoSePudoReevaluar("no se pudo escribir: %s" % str(resp)[:150])

    antes_ver = (anterior.get("veredicto_contacto") or {}).get("estado")
    return {
        "guardado": guardar,
        "dolor_antes": anterior.get("dolor_primario"),
        "dolor_ahora": ev.dolor_primario,
        "apertura_antes": anterior.get("apertura"),
        "apertura_ahora": ev.apertura,
        "gating_antes": anterior.get("gating_intensidad"),
        "gating_ahora": (ev.gating.intensidad if ev.gating else None),
        "gating_regla": (ev.gating.regla_id if ev.gating else None),
        "version_antes": anterior.get("version_reglas"),
        "mm_share_buy": reg.get("mm_share_buy"),
        "veredicto_antes": antes_ver,
        "veredicto_ahora": ver.estado,
        "version_reglas": VERSION_REGLAS,
        "cambio": (anterior.get("dolor_primario") != ev.dolor_primario
                   or antes_ver != ver.estado),
        "mm_buyside_anualizado": reg.get("mm_buyside_anualizado"),
    }
