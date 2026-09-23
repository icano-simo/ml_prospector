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


def _produccion(realtor: dict, mm: dict) -> str:
    """Las cifras de produccion, cada una con SU ventana y SU fuente.

    El parrafo anterior decia «cierra 16 operaciones al año» y, dos comas mas
    tarde, «enteramente del lado comprador (3 de 3)». Un BD podia entender que
    de sus 16 solo 3 son del lado comprador, **y no es lo que dice el dato**:

      16   del libro, que es de principios de año
      9    de Model Match, lado comprador, sobre 14 meses
      3    de esas 9, las que tienen tipo de prestamo identificado

    Son tres numeros de tres ventanas distintas. Sin decir cual es cual, el
    lector arma la relacion que le parece -- y la que parece obvia es falsa.

    Y la produccion que MANDA es la anualizada de Model Match: buy_units sobre
    la ventana por doce. Nueve en catorce meses son 7,7 al año, no 16. La del
    libro se conserva y se dice, pero no es la que decide.
    """
    partes = []
    libro = realtor.get("unidades_ano")
    if libro is not None:
        partes.append("según el libro cierra unas %s operaciones al año"
                      % "{:,.0f}".format(libro).replace(",", "."))

    buy = mm.get("buyer_units")
    ventana = mm.get("ventana_meses")
    anual = mm.get("buyside_anualizado")
    if buy and ventana:
        frase = ("en los últimos %d meses Model Match le registra %s del lado "
                 "comprador" % (ventana, "{:,.0f}".format(buy).replace(",", ".")))
        mix = (mm.get("loan_mix_buyer") or {}).get("unidades_identificadas")
        if mix:
            frase += (", de las cuales %s tienen tipo de préstamo identificado"
                      % "{:,.0f}".format(mix).replace(",", "."))
        partes.append(frase)
        if anual:
            partes.append("que anualizado da %s al año, y es el número que "
                          "manda" % ("%g" % anual).replace(".", ","))
    elif buy:
        partes.append("Model Match le registra %s del lado comprador, sin "
                      "ventana declarada, así que no se puede anualizar"
                      % "{:,.0f}".format(buy).replace(",", "."))

    return "; ".join(partes) if partes else ""


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

    texto = partes[0] + ". "

    prod = _produccion(realtor, mm)
    if prod:
        texto += prod[0].upper() + prod[1:] + ". "

    # El lado comprador es lo que decide si nos sirve: un agente de listados no
    # nos trae borrower. `sf_buy/sf_sell` son de la cabecera de Model Match y
    # su ventana es la misma que la de arriba, asi que se dice una sola vez.
    sf_buy, sf_sell = mm.get("sf_buy"), mm.get("sf_sell")
    if sf_buy is not None and sf_sell is not None and (sf_buy or sf_sell):
        if sf_sell == 0:
            texto += "Su actividad reciente es toda del lado comprador. "
        elif sf_sell > sf_buy:
            texto += ("Trabaja más listados que compradores (%d contra %d), "
                      "que es el lado que menos borrower nos trae. "
                      % (sf_sell, sf_buy))
    elif mm.get("side_focus"):
        texto += "Model Match lo clasifica como %s. " % str(
            mm["side_focus"]).lower()

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
