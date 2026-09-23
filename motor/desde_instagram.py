"""Las señales de Instagram -> la entrada del motor.

Por que hace falta este modulo
------------------------------
`correr_motor.py` leia SOLO el libro, y tenia escrito
`FALTAN_HOY = (..., "senales_instagram", ...)` con `categorias_acreditadas=set()`
y `modelmatch_capturado=False` fijos. O sea que cargar Instagram a la base no
movia ni un numero: el motor no lo miraba.

Las tres guardias que gobiernan esto
------------------------------------
1 · **La muestra de 10.** La matriz exige >=10 piezas para acreditar idioma.
    Por debajo, el idioma NO se acredita -- ni a favor ni en contra.
2 · **Ausencia no es negacion.** Un perfil que no se pudo leer deja los campos
    en `None`, no en `False`. `publico_leido` es la unica lectura que permite
    concluir desde una ausencia, porque ahi SI se miro.
3 · **El libro no se pisa.** Si el libro ya trae un `ev2_*` en True, Instagram
    puede confirmarlo pero no borrarlo: son dos lecturas de momentos distintos.
"""
from __future__ import annotations

#: Lo minimo para acreditar idioma, segun la matriz.
MUESTRA_MINIMA_IDIOMA = 10

#: Los estados en que SI se leyo el muro. En el resto, la ausencia de una señal
#: no significa que no este: significa que no se miro.
SE_PUDO_LEER = ("publico_leido",)

#: columna del CSV -> campo del motor. Solo las que el motor ya conoce.
DE_MENCION = {
    "menciona_itin": "ev2_itin",
    "menciona_dpa": "ev2_dpa_enganche",
    "menciona_credito": "ev2_credito",
    "menciona_va": "ev2_va_militar",
    "menciona_fha": "ev2_fha_gob",
    "menciona_primera_casa": "ev2_primera_casa",
}

#: Que categoria de señal acredita cada cosa. S1-S10 de la matriz.
CATEGORIAS_POR_SEÑAL = {
    "captions_n": "S3",              # contenido propio
    "comentarios_n": "S4",           # interaccion
    "menciona_lender": "S6",         # relacion con un lender
    "audiencia_dominante": "S1",     # a quien le habla
    "tema_dominante": "S2",          # de que habla
    "marcadores_culturales": "S8",   # identidad declarada
    "geotags_top": "S7",             # donde opera
    "destacadas_titulos": "S9",      # como se presenta
    "engagement_rate": "S5",         # respuesta de su audiencia
}


def _num(v):
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _positivo(v) -> bool | None:
    n = _num(v)
    return None if n is None else n > 0


def senales_de(fila: dict) -> dict:
    """Una fila de `pacs.ig_senales` -> los campos que el motor entiende.

    Devuelve solo lo que se puede afirmar. Lo que no se pudo leer NO aparece,
    para que el motor lo vea como `None` y sus reglas queden sin evaluar en vez
    de evaluarse en falso.
    """
    s = fila.get("senales") or {}
    estado = fila.get("estado_perfil")
    leido = estado in SE_PUDO_LEER
    salida: dict = {}

    # ── Las menciones ───────────────────────────────────────────────────────
    for col, campo in DE_MENCION.items():
        v = _positivo(s.get(col))
        if v:
            salida[campo] = True          # afirmativo: se vio
        elif v is False and leido:
            salida[campo] = False         # se miro y no esta
        # si no se leyo, no se escribe: queda None

    # ── El idioma, con su muestra ───────────────────────────────────────────
    captions = _num(fila.get("captions_n"))
    if leido and captions is not None and captions >= MUESTRA_MINIMA_IDIOMA:
        es = _num(s.get("idioma_publica_es")) or 0
        en = _num(s.get("idioma_publica_en")) or 0
        if es + en > 0:
            salida["ev2_espanol_decl"] = es > en
    # Por debajo de la muestra el idioma NO se acredita, ni a favor ni en
    # contra: es la guardia de la matriz y no se negocia.

    # ── Lo demas que el motor ya conoce ─────────────────────────────────────
    if leido:
        if s.get("audiencia_dominante"):
            salida["ev2_inversion"] = s["audiencia_dominante"] == "inversion"
        if s.get("tema_dominante"):
            salida["ev2_educacion"] = s["tema_dominante"] in (
                "educacion", "proceso_compra", "programas_gobierno")
            salida["ev2_testimonio"] = s["tema_dominante"] == "celebracion_cierre"
        if _num(s.get("tipo_post_reel_pct")) is not None:
            salida["ev2_video_contenido"] = _num(s["tipo_post_reel_pct"]) >= 30
        if s.get("marcadores_culturales"):
            salida["ev2_fe_familia"] = any(
                m in s["marcadores_culturales"]
                for m in ("familia", "fe", "cultura"))
            salida["ev2_comunidad"] = "comunidad" in s["marcadores_culturales"]

    seguidores = _num(s.get("seguidores"))
    if seguidores is not None:
        salida["ig_seguidores"] = seguidores

    return salida


def categorias_acreditadas(fila: dict) -> set[str]:
    """Las S1-S10 con DATO REAL en este perfil.

    Solo cuentan si el muro se pudo leer: una categoria "acreditada" sobre un
    perfil que no se vio es la confianza subiendo por no haber mirado.
    """
    if fila.get("estado_perfil") not in SE_PUDO_LEER:
        return set()
    s = fila.get("senales") or {}
    cats = set()
    for col, cat in CATEGORIAS_POR_SEÑAL.items():
        v = fila.get(col) if col in fila else s.get(col)
        if v not in (None, "", 0, "0"):
            cats.add(cat)
    return cats


def bio_legible(fila: dict) -> bool | None:
    """¿Se leyó su bio? `None` cuando no se pudo mirar el perfil."""
    if fila.get("estado_perfil") not in SE_PUDO_LEER:
        return None
    return bool((fila.get("senales") or {}).get("marcadores_culturales")
                or (fila.get("senales") or {}).get("destacadas_titulos")
                or fila.get("captions_n"))


def combinar_con_el_libro(del_libro: dict, de_instagram: dict) -> dict:
    """El libro no se pisa: Instagram confirma o agrega, nunca borra.

    Son dos lecturas de momentos distintos. Un `True` del libro que hoy no se
    ve en Instagram no es un `False`: es que el realtor dejo de publicarlo, o
    que el raspado no lo alcanzo.
    """
    salida = dict(del_libro)
    for campo, valor in de_instagram.items():
        if valor is True:
            salida[campo] = True
        elif campo not in salida or salida.get(campo) is None:
            salida[campo] = valor
    return salida
