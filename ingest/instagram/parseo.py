"""Parseo y conteo de la capa de Instagram. Funciones puras.

`parsear_conteo` acepta formato ES y EN porque el scraper lee la interfaz en el
idioma del perfil: «1.234» y «1,234» son el mismo numero escrito por dos
locales, y quedarse con uno solo pierde la mitad del lote.

`hits_distintos` deduplica ANTES de contar: una firma copiada en 12 posts es
una sola señal, y contarla 12 veces convertia una firma en una especializacion.
"""
from __future__ import annotations

import re

#: Si el engagement da mayor que 1 el dato esta mal y no se usa.
ENGAGEMENT_MAXIMO = 1.0


def parsear_conteo(v) -> int | None:
    """«1.234» → 1234 · «12,5K» → 12500 · «1,2 M» → 1200000. Otra cosa → None.

    Devolver `None` y no `0` es la regla de los tres estados: un seguidor que no
    se pudo leer no es una cuenta sin seguidores.
    """
    if v is None or v != v:
        return None
    s = str(v).strip()
    if not s:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)

    m = re.fullmatch(r"([\d.,]+)\s*([KkMm])?", s)
    if not m:
        return None
    numero, sufijo = m.group(1), (m.group(2) or "").upper()

    # Con sufijo, el separador es decimal en las dos locales: `12,5K` y `12.5K`
    # son 12.500. Sin sufijo, es separador de miles: `1.234` y `1,234` son 1234.
    if sufijo:
        cuerpo = numero.replace(",", ".")
        if cuerpo.count(".") > 1:
            return None
        try:
            valor = float(cuerpo)
        except ValueError:
            return None
        return int(round(valor * (1000 if sufijo == "K" else 1_000_000)))

    solo_digitos = re.sub(r"[.,]", "", numero)
    if not solo_digitos.isdigit():
        return None
    # `1.5` sin sufijo no es un conteo de seguidores: seria 15, que es inventar.
    grupos = re.split(r"[.,]", numero)
    if len(grupos) > 1 and any(len(g) != 3 for g in grupos[1:]):
        return None
    return int(solo_digitos)


def engagement_utilizable(valor) -> tuple[float | None, bool]:
    """(valor, sospechoso). Mayor que 1 no se usa: el denominador esta mal."""
    if valor is None or valor != valor:
        return None, False
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None, False
    if v > ENGAGEMENT_MAXIMO:
        return None, True
    return v, False


def hits_distintos(posts: list[str], patron) -> tuple[int, int, str | None]:
    """(posts_con_match, fragmentos_distintos, ancla).

    El segundo numero es el que manda: una firma repetida cuenta 1. El primero
    se conserva porque la diferencia entre los dos ES el dato -- 12 contra 1
    dice que es una firma, y eso vale para el motivo.
    """
    frags: list[str] = []
    claves: set[str] = set()
    for p in posts or []:
        m = patron.search(p or "")
        if not m:
            continue
        cuerpo = re.sub(r"^\d{4}-\d{2}-\d{2} \| ", "", p)
        m2 = patron.search(cuerpo) or m
        clave = re.sub(r"\W+", "",
                       cuerpo[max(0, m2.start() - 40):m2.end() + 40].lower())
        claves.add(clave)
        frags.append("%s · «%s»"
                     % (p[:10],
                        cuerpo[max(0, m2.start() - 70):m2.end() + 90].strip()))
    return len(frags), len(claves), (frags[0] if frags else None)
