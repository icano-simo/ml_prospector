"""Las señales de Instagram -> la entrada del motor, CON COMPUERTA DE PERFIL.

Las dos cosas que cambiaron el 2026-09-23
-----------------------------------------
**1 · La compuerta.** Antes este modulo evaluaba Instagram sin mirar de quien
era la cuenta: 36 de los 39 perfiles no utilizables tenian un dolor primario
vigente, incluyendo una cuenta personal, un criadero de gallos y una campaña
politica de otro pais. Ahora ninguna señal entra sin una `clase_perfil`
utilizable, y la compuerta esta EN ESTE MODULO -- no en quien lo llame.

**2 · `marcadores_culturales` sale del motor.** Banderas, «latina», fe, familia
y Hispanic Heritage no alimentan ningun `ev2_*`, ni S8, ni `bio_legible`, ni la
confianza. Es la misma regla por la que R7 salio el mismo dia: inferir nicho
desde identidad u origen es ECOA Regulation B.

Se implementa con **lista blanca**, no con lista negra. Una lista negra deja
pasar lo que nadie penso en prohibir, y el campo siguiente que describa
identidad entraria solo.

Las tres guardias que ya estaban, y siguen
------------------------------------------
1 · **La muestra de 10.** Por debajo, el idioma NO se acredita.
2 · **Ausencia no es negacion.** Lo que no se pudo leer queda en `None`.
3 · **El libro no se pisa.** Instagram confirma o agrega, nunca borra.
"""
from __future__ import annotations

from ingest.instagram.clase_perfil import CLASES_UTILIZABLES, clasificar

#: Lo minimo para acreditar idioma, segun la matriz.
MUESTRA_MINIMA_IDIOMA = 10

#: Los estados en que SI se leyo el muro.
SE_PUDO_LEER = ("publico_leido",)

#: ─────────────────────────────────────────────────────────────────────────────
#: LISTA BLANCA de campos de `senales` que el motor puede mirar.
#:
#: Todo lo que no este aqui es invisible para el motor, aunque exista en el
#: jsonb. `marcadores_culturales` es el caso que la motiva, pero la lista vale
#: para el proximo campo de identidad que alguien agregue al scraper: no hay
#: que acordarse de prohibirlo, hay que acordarse de permitirlo.
CAMPOS_PERMITIDOS = frozenset({
    "menciona_itin", "menciona_dpa", "menciona_credito", "menciona_va",
    "menciona_fha", "menciona_primera_casa", "menciona_lender",
    "idioma_publica_es", "idioma_publica_en",
    "idioma_comentarios_es", "idioma_comentarios_en",
    "audiencia_dominante", "tema_dominante", "tipo_post_reel_pct",
    "seguidores", "engagement_rate", "geotags_top", "destacadas_titulos",
    "captions_texto", "comentarios_texto", "preguntas_recibidas",
    "ratio_educa_vs_anuncia", "programas_mencionados", "precios_mencionados",
    "hueco_max_dias", "dias_entre_posts_mediana",
    "cuentas_hipotecarias_etiquetadas", "designaciones",
})

#: Campos que NO entran NUNCA, y por que. Esta lista no gobierna nada -- la
#: lista blanca es la que gobierna-- pero deja escrito el motivo, y hay una
#: prueba que falla si alguno aparece en `CAMPOS_PERMITIDOS`.
PROHIBIDOS_POR_ECOA = {
    "marcadores_culturales": "banderas, «latina», fe, familia, Hispanic "
                             "Heritage: identidad, no conducta (ECOA Reg. B)",
    "barrios_mencionados": "describe dónde vive la gente a la que le habla, "
                           "no qué hace el realtor",
}

#: columna del CSV -> campo del motor.
DE_MENCION = {
    "menciona_itin": "ev2_itin",
    "menciona_dpa": "ev2_dpa_enganche",
    "menciona_credito": "ev2_credito",
    "menciona_va": "ev2_va_militar",
    "menciona_fha": "ev2_fha_gob",
    "menciona_primera_casa": "ev2_primera_casa",
}

#: Que categoria de señal acredita cada cosa. S1-S10 de la matriz.
#: **S8 ya no existe aqui**: la alimentaba `marcadores_culturales`.
CATEGORIAS_POR_SEÑAL = {
    "captions_n": "S3",              # contenido propio
    "comentarios_n": "S4",           # interaccion
    "menciona_lender": "S6",         # relacion con un lender
    "audiencia_dominante": "S1",     # a quien le habla
    "tema_dominante": "S2",          # de que habla
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


def senales_visibles(fila: dict) -> dict:
    """`senales`, filtrado por la lista blanca. Es la unica via de lectura."""
    s = fila.get("senales") or {}
    return {k: v for k, v in s.items() if k in CAMPOS_PERMITIDOS}


def clase_de(fila: dict, *, handles_repetidos=frozenset()):
    """La clase del perfil. Se lee de la fila si la ingesta ya la calculó.

    Recalcularla aqui cuando ya viene es como dos capas empiezan a discrepar,
    asi que lo persistido MANDA -- incluida la auditoria manual, que es
    `clase_origen='auditoria'` y gana sobre la automatica.
    """
    if fila.get("clase_perfil"):
        return str(fila["clase_perfil"]), str(fila.get("clase_motivo") or "")
    c = clasificar(_para_clasificar(fila), handles_repetidos=handles_repetidos)
    return c.clase, c.motivo


def _para_clasificar(fila: dict) -> dict:
    """La fila aplanada que espera el clasificador.

    `captions_texto` y `geotags_top` viven dentro de `senales`; el resto son
    columnas. Se pasan por la lista blanca igual que todo lo demas.
    """
    s = senales_visibles(fila)
    return {
        "estado_perfil": fila.get("estado_perfil"),
        "handle": fila.get("handle"),
        "estado": fila.get("estado"),
        "capturado_en": fila.get("capturado_en"),
        "realtor_id": fila.get("realtor_id"),
        "bio": fila.get("bio"),
        "captions_texto": s.get("captions_texto"),
        "geotags_top": s.get("geotags_top"),
    }


def senales_de(fila: dict, *, handles_repetidos=frozenset()) -> dict:
    """Una fila de `pacs.ig_senales` -> los campos que el motor entiende.

    **Devuelve `{}` cuando la clase no es utilizable.** No ceros: un diccionario
    vacio deja todos los campos en `None` y sus reglas sin evaluar, que es lo
    que corresponde a «esta cuenta no es de quien creiamos».
    """
    clase, _motivo = clase_de(fila, handles_repetidos=handles_repetidos)
    if clase not in CLASES_UTILIZABLES:
        return {}
    # `otro_perfil` entra solo como fuente de referidos (B10): no se le sacan
    # señales de realtor transaccional.
    if clase == "otro_perfil":
        return {}

    s = senales_visibles(fila)
    estado = fila.get("estado_perfil")
    leido = estado in SE_PUDO_LEER
    salida: dict = {}

    for col, campo in DE_MENCION.items():
        v = _positivo(s.get(col))
        if v:
            salida[campo] = True
        elif v is False and leido:
            salida[campo] = False

    captions = _num(fila.get("captions_n"))
    if leido and captions is not None and captions >= MUESTRA_MINIMA_IDIOMA:
        es = _num(s.get("idioma_publica_es")) or 0
        en = _num(s.get("idioma_publica_en")) or 0
        if es + en > 0:
            salida["ev2_espanol_decl"] = es > en

    if leido:
        if s.get("audiencia_dominante"):
            salida["ev2_inversion"] = s["audiencia_dominante"] == "inversion"
        if s.get("tema_dominante"):
            salida["ev2_educacion"] = s["tema_dominante"] in (
                "educacion", "proceso_compra", "programas_gobierno")
            salida["ev2_testimonio"] = s["tema_dominante"] == "celebracion_cierre"
        if _num(s.get("tipo_post_reel_pct")) is not None:
            salida["ev2_video_contenido"] = _num(s["tipo_post_reel_pct"]) >= 30
        # `ev2_fe_familia` y `ev2_comunidad` ya NO se derivan de Instagram: los
        # alimentaba `marcadores_culturales`. Si el libro los trae, se respetan;
        # lo que no pasa es que Instagram los invente desde una bandera.

    seguidores = _num(s.get("seguidores"))
    if seguidores is not None:
        salida["ig_seguidores"] = seguidores

    return salida


def categorias_acreditadas(fila: dict, *,
                           handles_repetidos=frozenset()) -> set[str]:
    """Las S1-S10 con DATO REAL. Vacio si la clase no es utilizable."""
    clase, _m = clase_de(fila, handles_repetidos=handles_repetidos)
    if clase not in CLASES_UTILIZABLES or clase == "otro_perfil":
        return set()
    if fila.get("estado_perfil") not in SE_PUDO_LEER:
        return set()
    s = senales_visibles(fila)
    cats = set()
    for col, cat in CATEGORIAS_POR_SEÑAL.items():
        v = fila.get(col) if col in fila else s.get(col)
        if v not in (None, "", 0, "0"):
            cats.add(cat)
    return cats


def bio_legible(fila: dict, *, handles_repetidos=frozenset()) -> bool | None:
    """¿Se leyó su bio? `None` cuando no se pudo mirar.

    Ya NO mira `marcadores_culturales`: que alguien ponga una bandera en la bio
    no es evidencia de nada que el motor pueda usar, y era una de las tres vias
    por las que la identidad entraba a la confianza.
    """
    clase, _m = clase_de(fila, handles_repetidos=handles_repetidos)
    if clase not in CLASES_UTILIZABLES:
        return None
    if fila.get("estado_perfil") not in SE_PUDO_LEER:
        return None
    s = senales_visibles(fila)
    return bool(s.get("destacadas_titulos") or fila.get("captions_n"))


def combinar_con_el_libro(del_libro: dict, de_instagram: dict) -> dict:
    """El libro no se pisa: Instagram confirma o agrega, nunca borra."""
    salida = dict(del_libro)
    for campo, valor in de_instagram.items():
        if valor is True:
            salida[campo] = True
        elif campo not in salida or salida.get(campo) is None:
            salida[campo] = valor
    return salida
