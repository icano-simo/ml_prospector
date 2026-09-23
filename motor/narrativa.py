"""El párrafo que un BD lee primero: quién es esta persona.

Antes de cualquier contraste
----------------------------
La lectura del prototipo abría con prosa y no con una tabla, y tenía razón: un
BD que abre una ficha necesita saber a quién va a escribirle antes de saber en
qué se diferencia de su condado.

Lo que entra: brokerage, estado, volumen, si es del lado comprador, cómo es su
mercado y si podemos originarle. Nada que no esté en la base.

Lo que NO entra
---------------
Ninguna inferencia desde el apellido. Lo que cuenta es lo que publica, dónde
trabaja y qué opera -- es ECOA Regulation B, no una preferencia de estilo.
"""
from __future__ import annotations

from motor.lectura import _hablado, verificar_vocabulario


def _volumen_en_palabras(unidades: float | None) -> str | None:
    if unidades is None:
        return None
    n = "{:,.0f}".format(unidades).replace(",", ".")
    if unidades >= 24:
        return "cierra %s operaciones al año, que es volumen de agente de tiempo completo" % n
    if unidades >= 8:
        return "cierra %s operaciones al año" % n
    return "cierra %s operaciones al año, poco para vivir solo de esto" % n


def narrativa(realtor: dict, *, estado_nombre: str | None = None,
              perfil_mm: dict | None = None, mercado: dict | None = None,
              donde: str | None = None, cobertura: dict | None = None) -> str:
    """Quién es, en prosa, en un párrafo."""
    nombre = (realtor.get("nombre_completo") or "").strip() or "Este realtor"
    if nombre.isupper():
        nombre = nombre.title()
    estado = estado_nombre or realtor.get("estado") or "un estado que no tenemos"
    brokerage = (realtor.get("brokerage") or "").strip()
    mm = perfil_mm or {}

    partes = []
    if brokerage:
        partes.append("%s trabaja en %s, en %s" % (nombre, brokerage, estado))
    else:
        partes.append("%s opera en %s" % (nombre, estado))

    vol = _volumen_en_palabras(realtor.get("unidades_ano"))
    if vol:
        partes.append(vol)

    # El lado comprador es lo que decide si nos sirve: un agente de listados no
    # nos trae borrower.
    sf_buy, sf_sell = mm.get("sf_buy"), mm.get("sf_sell")
    if sf_buy is not None and sf_sell is not None:
        if sf_sell == 0 and sf_buy:
            partes.append("y lo que vemos de su actividad es enteramente del "
                          "lado comprador (%d de %d)" % (sf_buy, sf_buy))
        elif sf_buy > sf_sell:
            partes.append("y trabaja más el lado comprador que el vendedor "
                          "(%d contra %d)" % (sf_buy, sf_sell))
        elif sf_sell > sf_buy:
            partes.append("y trabaja más listados que compradores (%d contra "
                          "%d), que es el lado que menos borrower nos trae"
                          % (sf_sell, sf_buy))
    elif mm.get("side_focus"):
        partes.append("y Model Match lo clasifica como %s"
                      % str(mm["side_focus"]).lower())

    texto = ", ".join(partes[:1]) + (". " if len(partes) == 1 else ", ")
    if len(partes) > 1:
        texto = partes[0] + ", " + ", ".join(partes[1:]) + ". "

    # El mercado donde opera, en una frase.
    m = mercado or {}
    if donde and m.get("fallout") is not None:
        texto += ("En %s, donde concentra su operación, se caen %s "
                  "expedientes antes de cerrar" % (donde,
                                                   _hablado(m["fallout"])))
        if m.get("mkt_fha") is not None:
            texto += " y %s préstamos son FHA" % _hablado(m["mkt_fha"])
        texto += ". "
    elif donde:
        texto += ("Todavía no tenemos las métricas de %s, así que las "
                  "comparaciones con su mercado no pueden correr. " % donde)
    else:
        texto += ("No sabemos en qué condado concentra su operación: sin eso "
                  "no hay contra qué compararlo. ")

    # Y lo único que puede hacer irrelevante todo lo anterior.
    cov = cobertura or {}
    if cov.get("activos") == 0:
        texto += ("No tenemos licencia en %s: califica comercialmente y hoy no "
                  "podemos originarle." % estado)
    elif cov.get("activos"):
        texto += ("Podemos originarle: %d loan officer%s con licencia en %s."
                  % (cov["activos"], "" if cov["activos"] == 1 else "s",
                     estado))
    else:
        texto += ("No sabemos si tenemos licencia en %s, así que no se puede "
                  "decir todavía si podemos originarle." % estado)

    verificar_vocabulario(texto)
    return texto
