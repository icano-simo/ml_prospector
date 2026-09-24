"""El validador de la ficha redactada. Código puro: `validar(ficha, paquete)`.

Por qué la app valida AL LEER y no solo al escribir
---------------------------------------------------
Cowork corre este mismo validador antes de escribir. Aun así, la app lo vuelve
a correr cada vez que muestra la ficha, y por dos motivos:

1 · **el paquete cambia.** Una ficha válida contra el paquete de ayer puede
    citar una transacción que hoy se re-capturó con otro monto. El `hash` lo
    detecta, pero el validador dice QUÉ frase dejó de sostenerse;
2 · **quien escribe puede saltárselo.** Una validación que solo corre del lado
    del que produce el texto es una promesa, no una guarda.

Si una sección no pasa, esa sección muestra «Pendiente: no pasó la validación
(motivo)» y **las secciones de código se muestran igual**. Nunca se muestra un
texto sin validar, y nunca se pierde lo que sí está comprobado.

Qué NO hace
-----------
No juzga si el texto es bueno. Comprueba que lo que dice se puede sostener con
lo que hay en el paquete: que los ids existen, que los números salen de las
evidencias citadas, que las citas literales están dentro del post que dicen
citar, que el grado corresponde a la fuente, y que no aparece nada de lo
prohibido.

Es decidible, y por eso se puede automatizar. «¿Está bien escrito?» no lo es.
"""
from __future__ import annotations

import json
import re
import unicodedata

#: Longitud máxima del SMS. Por encima se parte en varios mensajes y el
#: segundo llega sin contexto.
MAX_SMS = 320

DATO = "Dato"
LO_CUENTA_ELLA = "Lo cuenta ella"
HIPOTESIS = "Hipótesis"
HIPOTESIS_PORQUE = "Hipótesis el porqué"

#: Prefijo de evidencia -> qué grados puede sostener.
#:
#: `MM-MK-*` (mercado) y `CENSUS` NO sostienen un «Dato», y es la corrección
#: del 2026-09-24: son estadísticas del condado, no de esta persona. De «en
#: Cook el 14 % son FHA» a «sus buyers usan FHA» hay un salto que alguien tiene
#: que validar en la llamada, y llamarlo Dato lo borra.
_GRADO_POR_FUENTE = {
    DATO: ("MM-TX", "MM-OV", "SF-"),
    LO_CUENTA_ELLA: ("IG-",),
}

#: Lo que NO escribe la ficha de un realtor excluido. Ya trabaja con la casa:
#: escribirle es competirle su propia cartera a un colega.
#:
#: `secuencia` entra por el mismo motivo que `mensaje`, y con más razón: la
#: secuencia no es una lectura, es la cola de contacto. `/api/dossier` ya
#: devuelve 409 para un excluido; esto es la segunda vuelta, sobre el texto.
_PROHIBIDO_SI_EXCLUIDO = ("dolores", "mensaje", "secuencia")

#: Y los bloques del dossier que un excluido tampoco lleva.
#:
#: D es la hipótesis principal --el dolor sobre el que se le escribiría-- y E
#: es cómo abrirle. E2 va con ellos porque es la munición de E: un ángulo sin
#: apertura no es una lectura, es la misma apertura en dos trozos.
#:
#: A, B, C y G sí se muestran: son quién es, qué clase de realtor es, su
#: mercado y la pregunta de brecha. Un excluido se sigue pudiendo leer; lo que
#: no existe es el material para escribirle.
_BLOQUES_PROHIBIDOS_SI_EXCLUIDO = ("D", "E", "E2")

#: Vocabulario de lending traducido. El BD tiene que decirlo en inglés en la
#: llamada; traducirlo aquí le obliga a volver a traducirlo.
_TRADUCIDOS = {
    "préstamo hipotecario": "loan", "prestamo hipotecario": "loan",
    "pago inicial": "down payment", "enganche": "down payment",
    "prestamista": "lender", "prestamistas": "lenders",
    "financiadas": "financed", "financiada": "financed",
    "tasa de interés": "rate", "tasa de interes": "rate",
    "precalificación": "pre-approval", "precalificacion": "pre-approval",
    "preaprobación": "pre-approval", "preaprobacion": "pre-approval",
    "cierre": "closing",
}

#: Origen y etnia. Nunca inferidos, y nunca en el mensaje.
#:
#: «hispana» y «latina» pueden aparecer DENTRO de una cita literal suya --ella
#: escribió «my Hispanic community»-- y ahí es su palabra. Fuera de una cita,
#: no.
_ORIGEN = ("hispano", "hispana", "hispanos", "hispanas", "latino", "latina",
           "latinos", "latinas", "mexicano", "mexicana", "hispanic")

#: RESPA §8: que un lender le refiera clientes no es un gancho.
_RESPA = ("lender referral", "referral partner", "nos referimos",
          "intercambiar referidos", "te referimos", "referidos mutuos")

#: «Cash» en Model Match es «sin loan registrado».
_CASH_AFIRMADO = ("pagó en efectivo", "pago en efectivo", "pagaron en efectivo",
                  "compró en efectivo", "compro en efectivo")

#: Números que no hace falta buscar en las evidencias: son del propio texto.
#: Un «2 o 3 líneas» o un «15 min» no es un dato del realtor.
_NUMEROS_LIBRES = {"1", "2", "3", "4", "5", "10", "15", "20", "30"}

_RE_NUMERO = re.compile(r"\d[\d.,]*\s*%|\$\s?[\d.,]+\s*[KMB]?|\d[\d.,]*")
_RE_ESPACIOS = re.compile(r"\s+")


def _plano(s: str) -> str:
    """Minúsculas, sin acentos y con los espacios colapsados.

    Para comparar citas: el scraper y quien redacta pueden diferir en un
    espacio doble o en un salto de línea, y rechazar por eso sería rechazar
    una cita correcta.
    """
    sin = "".join(c for c in unicodedata.normalize("NFD", s or "")
                  if unicodedata.category(c) != "Mn")
    return _RE_ESPACIOS.sub(" ", sin.lower()).strip()


def _numeros(texto: str) -> list[str]:
    """Los números que el texto afirma, normalizados para comparar."""
    salida = []
    for bruto in _RE_NUMERO.findall(texto or ""):
        n = bruto.replace("$", "").replace("%", "").replace(" ", "")
        n = n.rstrip(".,")
        if not n or n in _NUMEROS_LIBRES:
            continue
        salida.append(n.lower())
    return salida


def _texto_de_evidencias(evidencias: list[dict]) -> str:
    return " ".join(json.dumps(e, ensure_ascii=False, default=str)
                    for e in evidencias)


def _numero_esta(n: str, texto_ev: str) -> bool:
    """¿El número aparece en alguna de las evidencias citadas?

    Se compara de varias formas porque el mismo número se escribe distinto: la
    evidencia guarda `286000.0` y la ficha escribe `$286K`; guarda `0.7308` y
    la ficha escribe `73%`. Rechazar por el formato sería rechazar un número
    correcto, y aceptar cualquier cosa sería no comprobar nada.
    """
    plano = texto_ev.lower()
    # Las dos direcciones del decimal: `44.8` contra `44,8` y al revés. Con
    # una sola, la ficha que escribe el decimal con punto contra una evidencia
    # que lo guarda con coma se rechazaba por la coma.
    candidatos = {n, n.replace(".", ""), n.replace(",", ""),
                  n.replace(",", "."), n.replace(".", ",")}
    seco = n.replace(",", "").replace(".", "")
    if seco.isdigit():
        candidatos.add(seco)
    # `286k` -> `286000`; `5,3m` -> `5300000`
    m = re.fullmatch(r"([\d.,]+)([kmb])", n)
    if m:
        try:
            v = float(m.group(1).replace(",", "."))
            factor = {"k": 1e3, "m": 1e6, "b": 1e9}[m.group(2)]
            entero = int(round(v * factor))
            candidatos |= {str(entero), "%.1f" % (v * factor), str(float(entero))}
        except ValueError:
            pass
    # Un porcentaje contra su fracción: `73` contra `0.7308`.
    try:
        f = float(n.replace(",", "."))
        candidatos |= {str(f), "%g" % f, str(int(f)) if f == int(f) else str(f)}
        if 0 < f <= 100:
            candidatos.add("0.%02d" % int(f))
            candidatos.add(str(round(f / 100.0, 2)))
    except ValueError:
        pass
    return any(c and c in plano for c in candidatos)


# ══════════════════════════════════════════════════════════════════════════════
# LAS COMPROBACIONES, UNA POR UNA
# ══════════════════════════════════════════════════════════════════════════════

def _problema(seccion, motivo, detalle=None):
    return {"seccion": seccion, "motivo": motivo, "detalle": detalle}


def _revisar_frase(seccion, frase, indice, *, es_mensaje=False,
                   es_cita=False):
    """Las comprobaciones que no dependen del paquete.

    `es_cita` apaga las reglas de RESPA y de origen. Una cita literal son LAS
    PALABRAS DEL REALTOR: si ella escribió «I met her through a Lender Referral
    partner», eso es contexto y se puede mostrar. Lo que RESPA prohíbe es que
    NOSOTROS lo usemos como gancho, y eso se mira en el mensaje.

    Rechazar la cita era rechazar el hecho por cómo suena, y el efecto es que
    la ficha esconde justo lo que el BD tiene que saber antes de llamar.
    """
    problemas = []
    texto = (frase or {}).get("texto") or (frase or {}).get("texto_literal") or ""
    plano = _plano(texto)

    # El vocabulario NO se le exige a una cita literal. «$0 de enganche … al
    # cierre» es palabra de Julissa: corregirla sería reescribir lo que ella
    # escribió, y entonces deja de ser una cita. La regla existe para que el BD
    # diga «down payment» en la llamada, no para editar a nadie.
    if not es_cita:
        for traducido, en_ingles in _TRADUCIDOS.items():
            if _plano(traducido) in plano:
                problemas.append(_problema(
                    seccion, "vocabulario de lending traducido",
                    "dice «%s»; va «%s»" % (traducido, en_ingles)))

    for frase_cash in _CASH_AFIRMADO:
        if _plano(frase_cash) in plano:
            problemas.append(_problema(
                seccion, "afirma que pagó en efectivo",
                "«Cash» en Model Match es «sin loan registrado». Va «figura "
                "como cash»."))

    # RESPA y origen: SOLO en el mensaje, que es lo que le llega a ella. En una
    # cita literal son sus palabras, y en el resto de la ficha son contexto.
    if es_mensaje and not es_cita:
        for r in _RESPA:
            if _plano(r) in plano:
                problemas.append(_problema(
                    seccion, "usa como gancho que un lender le refiere clientes",
                    "RESPA §8: es contexto, nunca gancho. Dice «%s»" % r))
        for o in _ORIGEN:
            if re.search(r"\b%s\b" % re.escape(o), plano):
                problemas.append(_problema(
                    seccion, "segmenta por origen en el mensaje",
                    "dice «%s»" % o))
                break
    return problemas


def _revisar_evidencias(seccion, frase, por_id):
    """Los ids existen, y los números salen de ellos."""
    problemas = []
    citados = list((frase or {}).get("evidencias") or [])
    if not citados:
        return [_problema(seccion, "frase sin evidencias",
                          _plano((frase or {}).get("texto") or "")[:80])]

    faltan = [i for i in citados if i not in por_id]
    if faltan:
        problemas.append(_problema(
            seccion, "cita evidencias que no están en el paquete",
            ", ".join(faltan)))
    presentes = [por_id[i] for i in citados if i in por_id]
    if not presentes:
        return problemas

    texto_ev = _texto_de_evidencias(presentes)
    texto = (frase or {}).get("texto") or ""
    for n in _numeros(texto):
        if not _numero_esta(n, texto_ev):
            problemas.append(_problema(
                seccion, "un número del texto no está en las evidencias citadas",
                "«%s» no aparece en %s" % (n, ", ".join(citados))))
    return problemas


def _revisar_cita(seccion, cita, por_id):
    """Una cita literal tiene que estar DENTRO del post que dice citar."""
    problemas = _revisar_frase(seccion, cita, 0, es_cita=True)
    citados = list((cita or {}).get("evidencias") or [])
    if not citados:
        return problemas + [_problema(seccion, "cita sin evidencias")]
    if not (cita or {}).get("fecha"):
        problemas.append(_problema(
            seccion, "cita sin fecha",
            "sin fecha no se puede decir «el 15 de junio dijo», y eso es lo "
            "único que el BD puede usar"))

    literal = _plano((cita or {}).get("texto_literal") or "")
    if not literal:
        return problemas + [_problema(seccion, "cita sin texto literal")]

    fuentes = [por_id[i] for i in citados if i in por_id]
    faltan = [i for i in citados if i not in por_id]
    if faltan:
        problemas.append(_problema(seccion, "cita evidencias que no están en "
                                            "el paquete", ", ".join(faltan)))
    # La cita puede llevar «…» al recortar; se compara por trozos.
    trozos = [t for t in re.split(r"…|\.\.\.", literal) if len(t.strip()) > 12]
    trozos = trozos or [literal]
    texto_fuentes = " ".join(_plano(f.get("texto") or "") for f in fuentes)
    faltantes = [t.strip() for t in trozos if t.strip() not in texto_fuentes]
    if faltantes:
        problemas.append(_problema(
            seccion, "la cita no aparece en la evidencia que cita",
            "no encontré «%s» en %s" % (faltantes[0][:70], ", ".join(citados))))
    return problemas


def _revisar_grado(seccion, grados, citados, por_id):
    """«Dato» solo con MM/SF; «Lo cuenta ella» solo con IG y cita fechada."""
    problemas = []
    for g in grados or []:
        prefijos = _GRADO_POR_FUENTE.get(g)
        if not prefijos:
            continue          # `Hipótesis` y `Hipótesis el porqué` no exigen
        if not any(str(i).startswith(pre) for i in citados for pre in prefijos):
            problemas.append(_problema(
                seccion, "el grado no corresponde a la fuente",
                "«%s» exige citar %s y cita %s"
                % (g, " o ".join(prefijos), ", ".join(citados) or "nada")))
    return problemas


# ══════════════════════════════════════════════════════════════════════════════
# LA ENTRADA
# ══════════════════════════════════════════════════════════════════════════════

def validar(ficha: dict, paquete: dict) -> list[dict]:
    """Los problemas de la ficha contra su paquete. Lista vacía = pasa.

    Devuelve una lista de `{seccion, motivo, detalle}` y no un booleano: la
    pantalla apaga LA SECCIÓN que falló y muestra el resto, así que necesita
    saber cuál y por qué.
    """
    from motor.paquete import por_id as indice

    problemas: list[dict] = []
    por_id = indice(paquete)
    ficha = ficha or {}

    if (paquete or {}).get("hash_paquete") and ficha.get("hash_paquete"):
        if ficha["hash_paquete"] != paquete["hash_paquete"]:
            problemas.append(_problema(
                "ficha", "la ficha se escribió contra otro paquete",
                "hay datos nuevos: ficha pendiente de actualizar"))

    # ── UN EXCLUIDO NO TIENE DOLORES NI MENSAJE ─────────────────────────────
    #
    # El paquete ya no le manda las activaciones, así que no hay de dónde
    # sacarlos. Esto es la segunda vuelta: si una ficha vieja los trae, o si
    # alguien los escribe igual, la sección no se muestra.
    #
    # Es la única regla del validador que mira el CONTENIDO de una decisión de
    # negocio, y puede porque la decisión ya está tomada: `VEREDICTO` viene
    # calculado y la IA no lo toca.
    excluido = (por_id.get("VEREDICTO") or {}).get("estado") == "excluido"
    if excluido:
        for seccion in _PROHIBIDO_SI_EXCLUIDO:
            if ficha.get(seccion):
                problemas.append(_problema(
                    seccion, "el realtor está excluido y no lleva %s" % seccion,
                    "ya trabaja con la casa: escribirle es competirle su "
                    "propia cartera a un colega"))

    # ── cabecera ────────────────────────────────────────────────────────────
    cab = ficha.get("cabecera") or {}
    if cab.get("bio"):
        problemas += _revisar_frase("cabecera.bio", cab["bio"], 0)
        problemas += _revisar_evidencias("cabecera.bio", cab["bio"], por_id)
    for i, c in enumerate(cab.get("bio_evidencias_visibles") or []):
        problemas += _revisar_cita("cabecera.bio_evidencias[%d]" % i, c, por_id)

    # ── por qué ella ────────────────────────────────────────────────────────
    razones = (ficha.get("por_que_ella") or {}).get("razones") or []
    if razones and len(razones) != 3:
        problemas.append(_problema("por_que_ella", "tienen que ser 3 razones",
                                   "hay %d" % len(razones)))
    for i, r in enumerate(razones):
        s = "por_que_ella.razones[%d]" % i
        problemas += _revisar_frase(s, r, i)
        problemas += _revisar_evidencias(s, r, por_id)
        # `de_donde_sale` es texto de la IA como cualquier otro: si no se
        # valida, la razón queda comprobada y su justificación no -- que es
        # justo donde alguien pondría el número que no se puede sostener.
        dd = r.get("de_donde_sale")
        if isinstance(dd, dict):
            sd = s + ".de_donde_sale"
            problemas += _revisar_frase(sd, dd, i)
            problemas += _revisar_evidencias(sd, dd, por_id)
            for j, c in enumerate(dd.get("citas") or []):
                problemas += _revisar_cita("%s.citas[%d]" % (sd, j), c, por_id)

    # ── dolores ─────────────────────────────────────────────────────────────
    dolores = ficha.get("dolores") or []
    if dolores and not (2 <= len(dolores) <= 5):
        problemas.append(_problema("dolores", "tienen que ser entre 2 y 5",
                                   "hay %d" % len(dolores)))
    for i, d in enumerate(dolores):
        s = "dolores[%d]" % i
        problemas += _revisar_frase(s, {"texto": d.get("dolor")}, i)
        problemas += _revisar_frase(s, {"texto": d.get("evidencia_texto")}, i)
        problemas += _revisar_evidencias(
            s, {"texto": "%s %s" % (d.get("dolor") or "",
                                    d.get("evidencia_texto") or ""),
                "evidencias": d.get("evidencias")}, por_id)
        problemas += _revisar_grado(s, d.get("grado"),
                                    d.get("evidencias") or [], por_id)
        if not (d.get("pregunta") or "").strip().endswith("?"):
            problemas.append(_problema(
                s, "el dolor no trae una pregunta para validarlo",
                "un dolor que no se valida es una suposición que se repite"))

    # ── mensaje ─────────────────────────────────────────────────────────────
    msg = ficha.get("mensaje") or {}
    for clave in ("sms", "largo_es", "largo_en", "canal", "objecion"):
        f = msg.get(clave)
        if not f:
            continue
        s = "mensaje.%s" % clave
        problemas += _revisar_frase(s, f, 0, es_mensaje=True)
        problemas += _revisar_evidencias(s, f, por_id)
    for i, f in enumerate(msg.get("preguntas") or []):
        s = "mensaje.preguntas[%d]" % i
        problemas += _revisar_frase(s, f, i, es_mensaje=True)
        problemas += _revisar_evidencias(s, f, por_id)

    sms = (msg.get("sms") or {}).get("texto") or ""
    if len(sms) > MAX_SMS:
        problemas.append(_problema(
            "mensaje.sms", "el SMS pasa de %d caracteres" % MAX_SMS,
            "tiene %d" % len(sms)))
    if sms:
        problemas += _revisar_sms_sin_transacciones(sms, paquete)
        problemas += _revisar_idioma_del_sms(sms, paquete)

    # ── el resto de las secciones de IA ─────────────────────────────────────
    prod = ficha.get("produccion") or {}
    for clave in ("lede", "nota_loan_mix", "lo_que_significa"):
        if prod.get(clave):
            s = "produccion.%s" % clave
            problemas += _revisar_frase(s, prod[clave], 0)
            problemas += _revisar_evidencias(s, prod[clave], por_id)

    ig = ficha.get("instagram") or {}
    for clave in ("lede", "nota_listings", "idioma"):
        if ig.get(clave):
            s = "instagram.%s" % clave
            problemas += _revisar_frase(s, ig[clave], 0)
            problemas += _revisar_evidencias(s, ig[clave], por_id)
    for i, b in enumerate(ig.get("a_quien_le_habla") or []):
        problemas += _revisar_cita("instagram.a_quien_le_habla[%d]" % i,
                                   b.get("cita"), por_id)
    for i, c in enumerate(ig.get("que_cuenta_de_sus_clientes") or []):
        problemas += _revisar_cita("instagram.que_cuenta[%d]" % i, c, por_id)

    # `encaje` es juicio de la IA y va siempre como Hipótesis. Lo que se
    # comprueba es que las razones citen evidencia existente -- que el juicio
    # se apoye en algo, no que el juicio sea el correcto.
    enc = ficha.get("encaje") or {}
    if enc:
        if enc.get("clase") not in ("Cliente ideal", "Revisar", "Nutrición"):
            problemas.append(_problema(
                "encaje", "la clase de encaje no es una de las tres",
                repr(enc.get("clase"))))
        razones_enc = enc.get("razones") or []
        if not (2 <= len(razones_enc) <= 3):
            problemas.append(_problema("encaje", "tienen que ser 2 o 3 razones",
                                       "hay %d" % len(razones_enc)))
        for i, r in enumerate(razones_enc):
            s = "encaje.razones[%d]" % i
            problemas += _revisar_frase(s, r, i)
            problemas += _revisar_evidencias(s, r, por_id)

    # ── las tres pestañas redactadas ────────────────────────────────────────
    problemas += _revisar_instagram_analisis(ficha, por_id)
    problemas += _revisar_dossier(ficha, por_id, excluido, paquete)
    problemas += _revisar_secuencia(ficha, por_id, paquete)

    ctx = ficha.get("contexto") or {}
    for clave in ("mercado_resumen", "mercado_texto", "census_resumen",
                  "census_texto"):
        if ctx.get(clave):
            s = "contexto.%s" % clave
            problemas += _revisar_frase(s, ctx[clave], 0)
            problemas += _revisar_evidencias(s, ctx[clave], por_id)
    # Los títulos son texto suelto, sin evidencias: no afirman un hecho, lo
    # nombran. Se revisan solo por términos prohibidos.
    for clave in ("mercado_titulo", "census_titulo"):
        if ctx.get(clave):
            problemas += _revisar_frase("contexto.%s" % clave,
                                        {"texto": ctx[clave]}, 0)

    return problemas


# ══════════════════════════════════════════════════════════════════════════════
# LAS TRES PESTAÑAS REDACTADAS
# ══════════════════════════════════════════════════════════════════════════════

#: Las nueve frases de la pestaña Instagram. En este orden se leen.
_CAMPOS_IG_ANALISIS = (
    "quien_es", "con_quien_se_relaciona", "que_escribe", "a_quien_le_habla",
    "donde", "cada_cuanto", "que_le_preguntan", "senales_para_el_bd",
    "que_verificar",
)


def _revisar_instagram_analisis(ficha: dict, por_id: dict) -> list[dict]:
    """Nueve frases y un juicio, todas con evidencia de SU cuenta.

    Se revisa campo por campo y no la sección entera: si «cada_cuanto» no se
    sostiene, lo que hay que apagar es esa línea, no las otras ocho.
    """
    ia = ficha.get("instagram_analisis") or {}
    if not ia:
        return []
    problemas = []

    # ── «SU INSTAGRAM NO APORTA» ────────────────────────────────────────────
    #
    # Cinco realtors tienen la cuenta sin datos, no utilizable, o personal. Uno
    # --Claudia-- tiene mapeada la cuenta de OTRA persona. Exigirles las nueve
    # frases es pedir que se escriba sobre lo que no hay, y lo que sale de ahí
    # es relleno con evidencias forzadas.
    #
    # Con `aporta: false` se exige lo contrario: el MOTIVO. La pantalla enseña
    # un sello «IG no aporta» con la razón y lo que habría que verificar, que
    # es información de verdad -- «no miramos su Instagram» y «su Instagram no
    # sirve» son dos cosas distintas, y la segunda le ahorra el viaje al BD.
    if ia.get("aporta") is False:
        pr = ia.get("prioridad_ig") or {}
        if not (pr.get("razones") or []):
            problemas.append(_problema(
                "instagram_analisis.prioridad_ig",
                "dice que no aporta y no dice por qué",
                "un «no aporta» sin motivo no se distingue de un hueco"))
        problemas += _revisar_prioridad_ig(pr, por_id)
        for clave in ("que_verificar",):
            if ia.get(clave):
                s = "instagram_analisis.%s" % clave
                problemas += _revisar_frase(s, ia[clave], 0)
                problemas += _revisar_evidencias(s, ia[clave], por_id)
        return problemas

    for clave in _CAMPOS_IG_ANALISIS:
        s = "instagram_analisis.%s" % clave
        f = ia.get(clave)
        if not f:
            problemas.append(_problema(s, "falta el campo"))
            continue
        problemas += _revisar_frase(s, f, 0)
        problemas += _revisar_evidencias(s, f, por_id)

    # `prioridad_ig` es juicio, y va siempre como Hipótesis: lo que se
    # comprueba no es que la clase sea la correcta --eso no es decidible-- sino
    # que la clase exista y que cada razón se apoye en algo del paquete.
    problemas += _revisar_prioridad_ig(ia.get("prioridad_ig") or {}, por_id)
    return problemas


def _revisar_prioridad_ig(pr: dict, por_id: dict) -> list[dict]:
    """La clase existe y cada razón se apoya en algo. El juicio no se valida.

    `prioridad_ig` va siempre como Hipótesis: lo que se comprueba no es que la
    clase sea la correcta --eso no es decidible-- sino que exista y que las
    razones citen evidencia del paquete.
    """
    if not pr:
        return []
    s = "instagram_analisis.prioridad_ig"
    problemas = []
    if pr.get("clase") not in ("A", "B", "C", "D"):
        problemas.append(_problema(s, "la clase no es A, B, C ni D",
                                   repr(pr.get("clase"))))
    razones = pr.get("razones") or []
    if not razones:
        problemas.append(_problema(s, "la prioridad no trae razones"))
    for i, r in enumerate(razones):
        sr = "%s.razones[%d]" % (s, i)
        problemas += _revisar_frase(sr, r, i)
        problemas += _revisar_evidencias(sr, r, por_id)
    return problemas


#: Los bloques del dossier que son una frase suelta. `D` es un objeto y `F` no
#: lo escribe la IA.
_BLOQUES_FRASE = ("A", "B", "C", "E", "E2", "G")

#: Los que se LE DICEN a ella. El resto es para el BD.
_BLOQUES_QUE_SE_ENVIAN = ("E", "G")


def _revisar_lo_que_se_envia(seccion: str, texto, paquete: dict) -> list[dict]:
    """Las dos reglas de lo que sale hacia el realtor, en un solo sitio.

    No nombra sus transacciones --sus lenders, sus ZIPs, ni el principio del
    nombre de un lender-- y no va en español sin evidencia de idioma. Estaban
    solo en el SMS; el toque, el bloque E y el G se envían igual.
    """
    texto = texto or ""
    if not texto.strip() or not paquete:
        return []
    return (_revisar_sms_sin_transacciones(texto, paquete, seccion)
            + [dict(p, seccion=seccion)
               for p in _revisar_idioma_del_sms(texto, paquete)])


def _revisar_dossier(ficha: dict, por_id: dict, excluido: bool,
                     paquete: dict | None = None) -> list[dict]:
    """Los bloques A–G, y la regla del acto de habla en D."""
    dos = ficha.get("dossier") or {}
    if not dos:
        return []
    problemas = []

    # El bloque F es la lista de lo que NUNCA se dice, así que por definición
    # contiene las frases prohibidas: si lo escribiera la IA, el propio
    # validador lo rechazaría por decir lo que está ahí para prohibir. Lo pone
    # el código, literal, desde `motor/nunca.py`.
    if dos.get("F"):
        problemas.append(_problema(
            "dossier.F", "el bloque F no lo escribe la IA",
            "sale literal de motor/nunca.py::BLOQUE_F, que es la misma lista "
            "que revienta la construcción de cualquier texto que la diga"))

    for letra in _BLOQUES_FRASE:
        f = dos.get(letra)
        if not f:
            continue
        s = "dossier.%s" % letra
        # E y G SE ENVÍAN: E es la primera frase, tal cual se dice, y G es la
        # pregunta con la que se cierra. Las dos pasan por las reglas del
        # mensaje --RESPA, origen, sus transacciones, el idioma-- y no por las
        # de la prosa interna. A, B, C y E2 son para el BD.
        se_envia = letra in _BLOQUES_QUE_SE_ENVIAN
        problemas += _revisar_frase(s, f, 0, es_mensaje=se_envia)
        problemas += _revisar_evidencias(s, f, por_id)
        if se_envia:
            problemas += _revisar_lo_que_se_envia(s, (f or {}).get("texto"),
                                                  paquete)

    d = dos.get("D") or {}
    if d:
        problemas += _revisar_frase("dossier.D", d, 0)
        problemas += _revisar_evidencias("dossier.D", d, por_id)
        problemas += _revisar_acto_de_habla(d, por_id)

    if excluido:
        for letra in _BLOQUES_PROHIBIDOS_SI_EXCLUIDO:
            if dos.get(letra):
                problemas.append(_problema(
                    "dossier.%s" % letra,
                    "el realtor está excluido y no lleva el bloque %s" % letra,
                    "ya trabaja con la casa: no hay dolor que afirmarle ni "
                    "apertura que escribirle. A, B, C y G se muestran igual"))
    return problemas


def _revisar_acto_de_habla(d: dict, por_id: dict) -> list[dict]:
    """`AFIRMA` solo con una activación PACS de intensidad 3 y grado E0.

    Es la regla del método, no una preferencia de tono. Un qualifier de fuerza
    2 o con evidencia E1 es una hipótesis: afirmarlo delante del realtor es
    decirle que sabemos algo de su negocio que en realidad dedujimos, y la
    conversación se cae en la primera respuesta.

    `TECHO_POR_GRADO` ya lo impone al calcular; esto lo vuelve a comprobar
    sobre el TEXTO, que es lo que alguien escribe a mano.
    """
    problemas = []
    acto = (d.get("acto") or "").upper()
    if acto not in ("AFIRMA", "PREGUNTA"):
        return [_problema("dossier.D", "el acto de habla no es AFIRMA ni "
                                       "PREGUNTA", repr(d.get("acto")))]

    citadas = [por_id[i] for i in (d.get("evidencias") or []) if i in por_id]
    activaciones = [e for e in citadas if e.get("tipo") == "activacion_pacs"]

    # La activación del MISMO qualifier que dice el bloque. Sin ella, `D` dice
    # un qualifier y cita otra cosa.
    suya = next((a for a in activaciones
                 if a.get("qualifier") == d.get("qualifier")), None)
    if d.get("qualifier") and not suya:
        problemas.append(_problema(
            "dossier.D", "nombra un qualifier que no cita",
            "dice %s y no cita PACS-%s" % (d.get("qualifier"),
                                           d.get("qualifier"))))
    if suya:
        if str(suya.get("intensidad")) != str(d.get("intensidad")):
            problemas.append(_problema(
                "dossier.D", "la intensidad no es la de la activación",
                "%s dice %s y la activación trae %s"
                % (d.get("qualifier"), d.get("intensidad"),
                   suya.get("intensidad"))))
        if (suya.get("grado_evidencia") or "") != (d.get("grado") or ""):
            problemas.append(_problema(
                "dossier.D", "el grado no es el de la activación",
                "%s dice %s y la activación trae %s"
                % (d.get("qualifier"), d.get("grado"),
                   suya.get("grado_evidencia"))))

    if acto == "AFIRMA":
        fuerte = [a for a in activaciones
                  if str(a.get("intensidad")) == "3"
                  and (a.get("grado_evidencia") or "").upper() == "E0"]
        if not fuerte:
            problemas.append(_problema(
                "dossier.D", "AFIRMA sin una activación de intensidad 3 y "
                             "grado E0",
                "con cualquier otra cosa el bloque va como PREGUNTA: es una "
                "hipótesis, y afirmarla delante del realtor la convierte en "
                "un dato que él puede desmentir"))
    return problemas


def _revisar_secuencia(ficha: dict, por_id: dict,
                       paquete: dict | None = None) -> list[dict]:
    """Los 7 toques: días de PACS, canal, el toque 1, y las reglas del copy."""
    from motor.nunca import NuncaSeDice, verificar_nunca
    from motor.secuencia import (
        DIAS_PACS,
        CopyInvalido,
        verificar_cierra_con_pregunta_u_oferta,
        verificar_sin_folleto,
        verificar_sin_promesas,
        verificar_una_sola_idea,
    )

    seq = ficha.get("secuencia") or {}
    if not seq:
        return []
    problemas = []
    toques = seq.get("toques") or []
    if len(toques) != len(DIAS_PACS):
        problemas.append(_problema(
            "secuencia", "tienen que ser %d toques" % len(DIAS_PACS),
            "hay %d" % len(toques)))

    # Las cuatro reglas de `motor/secuencia.py`, más el bloque F. Las cuatro
    # revientan al construir un toque del código; aquí se recogen como
    # problemas, porque un texto escrito fuera del código no pasa por el
    # constructor y llegaría igual a la pantalla.
    reglas = (
        (verificar_sin_promesas, "promete material"),
        (verificar_sin_folleto, "usa adjetivos de folleto"),
        (verificar_cierra_con_pregunta_u_oferta,
         "no cierra con pregunta ni oferta"),
        (verificar_una_sola_idea, "dice más de una cosa"),
        (verificar_nunca, "dice algo que nunca se le dice a un realtor"),
    )

    for i, t in enumerate(toques):
        s = "secuencia.toques[%d]" % i
        texto = (t or {}).get("texto") or ""
        n = t.get("n")
        if n != i + 1:
            problemas.append(_problema(
                s, "el número del toque no es el de su posición",
                "dice n=%s y va en el lugar %d" % (n, i + 1)))
        esperado = DIAS_PACS[i] if i < len(DIAS_PACS) else None
        if esperado is not None and t.get("dia") != esperado:
            problemas.append(_problema(
                s, "el día no es el de PACS",
                "el toque %d va el día %d y dice %s"
                % (i + 1, esperado, t.get("dia"))))
        if t.get("canal") not in ("sms", "email", "llamada", "dm_ig"):
            problemas.append(_problema(s, "el canal no es uno de los cuatro",
                                       repr(t.get("canal"))))
        if not (t.get("objetivo") or "").strip():
            problemas.append(_problema(s, "el toque no dice qué busca"))
        if not (t.get("si_responde") or "").strip():
            problemas.append(_problema(
                s, "el toque no dice qué hacer si responde",
                "una secuencia sin eso deja al BD con la respuesta en la mano "
                "y sin el siguiente paso"))

        # Es texto que se ENVÍA: las reglas del mensaje valen enteras. RESPA y
        # origen, y también las dos que hasta ahora solo miraban el SMS -- no
        # nombrarle sus transacciones y no escribirle en español sin evidencia
        # de idioma. Un toque se envía igual que el SMS.
        problemas += _revisar_frase(s, t, i, es_mensaje=True)
        problemas += _revisar_evidencias(s, t, por_id)
        problemas += _revisar_lo_que_se_envia(s, texto, paquete)

        for regla, motivo in reglas:
            try:
                regla(texto)
            except (CopyInvalido, NuncaSeDice) as e:
                problemas.append(_problema(s, motivo, str(e).split("\n")[0]))

    # ── EL TOQUE 1 ES EL SMS DE LA FICHA ────────────────────────────────────
    #
    # No «parecido»: el mismo. Si fueran dos textos, la ficha diría uno y la
    # secuencia enviaría otro, y el BD no tiene por qué saber cuál manda.
    sms = ((ficha.get("mensaje") or {}).get("sms") or {}).get("texto") or ""
    if toques and sms:
        primero = (toques[0] or {}).get("texto") or ""
        if _plano(primero) != _plano(sms):
            problemas.append(_problema(
                "secuencia.toques[0]", "el toque 1 no es el SMS de la ficha",
                "la ficha muestra un texto y la secuencia enviaría otro"))
    return problemas


def _revisar_sms_sin_transacciones(sms: str, paquete: dict,
                                   seccion: str = "mensaje.sms") -> list[dict]:
    """Lo que se ENVÍA no menciona las transacciones del realtor.

    Se comprueba contra los lenders y los ZIPs que están en SU paquete, no
    contra una lista de palabras: lo prohibido no es hablar de lenders en
    abstracto, es nombrarle los suyos -- que es decirle que le miramos las
    operaciones antes de escribirle.

    **Y también por las dos primeras palabras del lender.** «Angel Oak» se
    escapaba de «Angel Oak Mortgage Solutions»: nadie escribe la razón social
    entera en un SMS, así que la comprobación por el nombre completo caza justo
    lo que nadie iba a escribir. Dos palabras y al menos siete caracteres, para
    no disparar con «Bank of» o «First».

    `seccion` viaja porque la misma regla vale para los toques de la secuencia,
    para el bloque E y para el G: los tres son texto que se le envía.
    """
    from motor.paquete import por_id as indice

    resumen = indice(paquete).get("MM-TX-RESUMEN") or {}
    plano = _plano(sms)
    lenders = (list(resumen.get("lenders_compra") or {})
               + list(resumen.get("lenders_venta") or {}))
    zips = list(resumen.get("zips_de_compra") or {})

    for cosa in lenders + zips:
        if cosa and _plano(str(cosa)) in plano:
            return [_problema(
                seccion, "menciona sus transacciones",
                "nombra «%s», que sale de su Transactions" % cosa)]
    for nombre in lenders:
        corto = " ".join(_plano(str(nombre)).split()[:2])
        if len(corto) >= 7 and corto in plano:
            return [_problema(
                seccion, "menciona sus transacciones",
                "nombra «%s», que es el principio de «%s»" % (corto, nombre))]
    return []


#: Palabras que solo existen en español. Detectan el idioma del SMS sin
#: adivinar: no hay que clasificar el texto, basta con que aparezca una.
_MARCAS_DE_ESPANOL = (
    "hola", "gracias", "cómo", "como estás", "café", "cafecito", "tienes",
    "tus", "tu ", "quieres", "podemos", "conocernos", "ayudamos", "sirve",
    "semana", "llamada", "mensaje", "escríbeme", "cuéntame", "vi tu",
)


def _revisar_idioma_del_sms(sms: str, paquete: dict) -> list[dict]:
    """El SMS va en español solo si hay EVIDENCIA de idioma. Nunca por el nombre.

    Es la regla de compliance más fácil de romper sin darse cuenta: un apellido
    hispano y un SMS en español parecen una cortesía. No lo son -- es inferir
    origen y decidir el trato a partir de él, que es exactamente lo que ECOA
    Regulation B prohíbe, y además sale mal: hay realtors de apellido hispano
    que no hablan español y se ofenden.

    Lo que SÍ vale como evidencia:
      · `PACS-P-Q14` activado --el motor midió el idioma--;
      · posts en español contados en `IG-RESUMEN`;
      · que ella lo declare en un post (`IG-*` con «hablo español» o similar).
    """
    from motor.paquete import por_id as indice

    # Lo que va entre corchetes NO cuenta para el idioma: `[tu nombre]` y
    # `[Confirmar con producto]` son marcas para el BD, no texto que se envía
    # tal cual. Un mensaje entero en inglés con un `[tu nombre]` dentro salía
    # como español por la palabra «nombre».
    plano = _plano(re.sub(r"\[[^\]]*\]", " ", sms or ""))
    if not any(re.search(r"\b%s" % re.escape(_plano(m)), plano)
               for m in _MARCAS_DE_ESPANOL):
        return []          # no está en español: no hay nada que justificar

    ev = indice(paquete)
    if "PACS-P-Q14" in ev:
        return []
    resumen = ev.get("IG-RESUMEN") or {}
    try:
        if float(resumen.get("idioma_publica_es") or 0) > 0:
            return []
    except (TypeError, ValueError):
        pass
    for e in ev.values():
        if e.get("tipo") != "post_instagram":
            continue
        t = _plano(e.get("texto") or "")
        if ("hablo espanol" in t or "habla espanol" in t
                or "speak spanish" in t or "en espanol" in t):
            return []
    return [_problema(
        "mensaje.sms", "el SMS está en español y no hay evidencia de idioma",
        "hace falta P-Q14, posts en español contados en IG-RESUMEN, o que "
        "ella lo declare en un post. Nunca por el nombre (ECOA Reg. B).")]


def secciones_con_problema(problemas: list[dict]) -> dict:
    """`{sección raíz: [motivos]}`. Es lo que la pantalla apaga."""
    salida: dict = {}
    for p in problemas or []:
        raiz = (p.get("seccion") or "").split(".")[0].split("[")[0]
        salida.setdefault(raiz, []).append(p.get("motivo"))
    return salida


def partes_con_problema(problemas: list[dict]) -> dict:
    """`{raíz: {parte: [motivos]}}`, un nivel más fino que la sección.

    La ficha apaga secciones enteras y está bien: son ocho y cada una se lee
    de un tirón. El dossier son siete bloques y la secuencia siete toques, y
    apagar los siete porque el toque 4 promete material esconde seis textos
    que sí se sostienen -- y deja al BD sin secuencia por un párrafo.

    La parte es el segundo nivel del nombre, con su índice si lo tiene:
    `secuencia.toques[3].texto` -> `{'secuencia': {'toques[3]': [...]}}`.
    Un problema de la raíz a secas (`secuencia`) va con la parte vacía, y eso
    la pantalla lo lee como «la sección entera».
    """
    salida: dict = {}
    for p in problemas or []:
        nombre = p.get("seccion") or ""
        trozos = nombre.split(".")
        raiz = trozos[0].split("[")[0]
        parte = trozos[1] if len(trozos) > 1 else ""
        salida.setdefault(raiz, {}).setdefault(parte, []).append(
            p.get("motivo"))
    return salida
