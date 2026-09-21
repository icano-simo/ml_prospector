"""Deteccion de idioma con un detector real, sobre texto real.

Historia de este archivo, que importa para no repetirla
------------------------------------------------------
**Version 1** contaba palabras españolas sobre el `alt` de las imagenes, que
Meta genera automaticamente en ingles. Resultado medido sobre 5.620 filas:
`ig_content_language = spanish` en **185 filas, 3,29%**, en un lote
seleccionado por mercado latino.

**Version 2** (Bloque 1) paso a leer captions reales, pero seguia clasificando
con conteo de palabras funcionales. Mejor fuente, mismo metodo fragil.

**Version 3** (Bloque 1-bis, esta) usa un detector de idioma de verdad:
`lingua`, restringido a {español, ingles}.

Por que lingua y no langdetect · medido el 2026-09-21
-----------------------------------------------------
Sobre 17 captions realistas de agentes inmobiliarios -- cortos, con emoji,
hashtags y terminos del oficio en ingles en medio del español:

| detector | aciertos |
|---|---|
| langdetect | 15 / 17 |
| **lingua** | **17 / 17** |

Y los dos fallos de langdetect son exactamente el caso que importa:

    "¡Vendida! 🏡🔑 Felicidades"                      -> pt con confianza 1.00
    "Casa abierta este sabado 🏠 #openhouse #austin"  -> pt con confianza 1.00

Portugues, con confianza maxima, asi que **ningun umbral lo habria filtrado**.
Ademas langdetect levanta excepcion con texto de solo emoji y es no
determinista sin fijar semilla.

La ventaja decisiva de lingua aca es poder restringir el espacio de hipotesis a
español e ingles, que es lo correcto en este dominio y lo que elimina la
confusion con portugues e italiano.

Rendimiento medido: **11.307 detecciones/s**. El lote completo -- 1.203
perfiles x 30 captions x 21 piezas -- son ~758.000 detecciones, o sea **~1
minuto de CPU**. No es un costo a optimizar.

La limpieza previa, que hace la mitad del trabajo
-------------------------------------------------
Antes de preguntarle al detector se sacan URLs, @menciones, #hashtags, emoji y
puntuacion. Sin eso, `#realtor #austin #texas #realestate` se clasifica como
ingles con 0,83 de confianza, y un hashtag no es evidencia de idioma.

Con la limpieza, todo texto sin letras queda en **indeterminado** por
construccion, no por un umbral. En la calibracion, los cuatro casos de basura
(`🔥🔥🔥`, `👏`, `!!!`, `@otro_agente`) dieron los cuatro 0 letras.

Los pisos, calibrados
---------------------
Dos umbrales distintos, porque un caption y un comentario no tienen el mismo
largo:

| pieza | min. letras | min. confianza | por que |
|---|---|---|---|
| caption | 18 | 0,60 | `captions_es_ratio` es el numero que se revisa contra la pantalla: conviene estricto |
| comentario | 10 | 0,60 | "Se puede con ITIN?" son 14 letras y es justo el comentario que importa |

En la calibracion sobre 26 comentarios reales hubo **cero clasificaciones
erroneas en todos los pisos probados**: lo unico que cambia el piso es cuantos
comentarios reales se descartan. Con 10/0,60 se clasifican 15 de 22 y se
pierden 7 por cortos.

Lo que NO se hace
-----------------
No se infiere idioma desde el apellido, el nombre ni el origen de nadie. Se
mide el idioma del texto que la persona escribio.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum

#: Piezas minimas que la matriz exige para sostener P-Q14 con su estandar.
MIN_PIEZAS_MATRIZ = 10
MIN_REVIEWS_MATRIZ = 5

#: Pisos calibrados. Ver la tabla del docstring.
MIN_LETRAS_CAPTION = 18
MIN_LETRAS_COMENTARIO = 10
MIN_CONFIANZA = 0.60

#: Compatibilidad: era el piso de la version 2, en caracteres crudos.
MIN_CARACTERES_PIEZA = 25

#: Escape declarado para entornos sin lingua. Marca la salida, no la esconde.
VAR_HEURISTICA = "ML_PROSPECTOR_IDIOMA_HEURISTICA"


class Idioma(str, Enum):
    ESPANOL = "es"
    INGLES = "en"
    MIXTO = "mixto"
    INDETERMINADO = "indeterminado"


class DetectorNoDisponible(RuntimeError):
    """Falta el detector de idioma. No se degrada en silencio."""


# ── Limpieza previa ───────────────────────────────────────────────────────────

_RE_URL = re.compile(r"https?://\S+|www\.\S+")
_RE_ARROBA = re.compile(r"@[\w.]+")
_RE_HASHTAG = re.compile(r"#[\wÀ-ɏ]+")
_RE_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F"
    "\U0001F1E6-\U0001F1FF←-⇿⬀-⯿]+"
)
_RE_NO_LETRA = re.compile(r"[^\w\s'À-ɏ]+", re.UNICODE)


def limpiar_para_deteccion(texto: str | None) -> str:
    """Saca URLs, @menciones, #hashtags, emoji y puntuacion.

    Un hashtag no es evidencia de idioma. Sin esta limpieza,
    `#realtor #austin #texas #realestate` se clasifica como ingles con 0,83.
    """
    t = _RE_URL.sub(" ", texto or "")
    t = _RE_ARROBA.sub(" ", t)
    t = _RE_HASHTAG.sub(" ", t)
    t = _RE_EMOJI.sub(" ", t)
    t = _RE_NO_LETRA.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def contar_letras(texto: str) -> int:
    return sum(1 for c in texto if c.isalpha())


# ── El detector ───────────────────────────────────────────────────────────────

_detector = None
_motor = None


def _cargar_detector():
    """Singleton perezoso. Falla ruidosamente si no hay detector real."""
    global _detector, _motor
    if _detector is not None or _motor == "heuristica":
        return _detector

    try:
        from lingua import Language, LanguageDetectorBuilder
    except ImportError:
        if os.environ.get(VAR_HEURISTICA) == "1":
            _motor = "heuristica"
            return None
        raise DetectorNoDisponible(
            "Falta el detector de idioma.\n"
            "\n"
            "    pip install lingua-language-detector\n"
            "\n"
            "No hay degradacion automatica a conteo de palabras clave, y es a\n"
            "proposito: ese metodo es el que produjo un 3,29%% de contenido en\n"
            "español sobre un lote seleccionado por mercado latino.\n"
            "\n"
            "Si de verdad hace falta correr sin el detector, hay que pedirlo:\n"
            "    set %s=1\n"
            "y entonces cada pieza sale marcada con motor='heuristica', para\n"
            "que nadie confunda una estimacion con una medicion."
            % VAR_HEURISTICA
        )

    _detector = (
        LanguageDetectorBuilder
        .from_languages(Language.SPANISH, Language.ENGLISH)
        .with_preloaded_language_models()
        .build()
    )
    _motor = "lingua"
    return _detector


def motor_en_uso() -> str:
    """'lingua' o 'heuristica'. Va al manifiesto de la corrida y al JSON crudo."""
    _cargar_detector()
    return _motor or "desconocido"


# ── Heuristica de emergencia, explicitamente marcada ─────────────────────────

_FUNCIONALES_ES = {
    "que", "de", "la", "el", "los", "las", "un", "una", "para", "por", "con",
    "como", "cuando", "donde", "porque", "pero", "si", "no", "es", "son",
    "esta", "estan", "hay", "tiene", "puede", "quiero", "vamos", "estoy",
    "somos", "soy", "tu", "mi", "su", "te", "me", "se", "lo", "le", "ya",
    "muy", "mas", "tambien", "aqui", "ahora", "hoy", "todo", "todos", "mucho",
    "nada", "quien", "cual", "cuanto", "del", "al", "esto", "ese", "otro",
    "asi", "bien", "gracias", "felicidades", "bienvenidos",
}
_FUNCIONALES_EN = {
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "with", "about",
    "from", "and", "or", "but", "because", "if", "not", "is", "are", "was",
    "were", "be", "have", "has", "had", "do", "does", "did", "can", "will",
    "would", "should", "this", "that", "these", "those", "it", "its", "you",
    "your", "my", "our", "their", "we", "they", "there", "now", "today",
    "all", "some", "any", "more", "most", "very", "just", "also", "who",
    "which", "what", "when", "where", "how", "why", "congratulations",
    "welcome", "thanks", "thank",
}
_TERMINOS_DE_OFICIO = {
    "realtor", "realty", "broker", "listing", "listings", "open", "house",
    "closing", "escrow", "mls", "condo", "townhouse", "loan", "mortgage",
    "fha", "va", "usda", "conventional", "preapproval", "under", "contract",
    "sold", "buyer", "seller", "downpayment", "dpa", "itin", "credit",
    "score", "homeready", "refinance", "appraisal",
}


def _heuristica(limpio: str) -> tuple[Idioma, float]:
    """Solo se usa con la variable de entorno puesta. Nunca en automatico."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", limpio)
        if unicodedata.category(c) != "Mn"
    ).lower()
    tokens = [t for t in re.findall(r"[a-z]{2,}", sin_acentos)
              if t not in _TERMINOS_DE_OFICIO]
    n_es = sum(1 for t in tokens if t in _FUNCIONALES_ES)
    n_en = sum(1 for t in tokens if t in _FUNCIONALES_EN)
    n_es += min(sum(1 for c in limpio.lower() if c in "ñáéíóúü"), 3)
    total = n_es + n_en
    if total == 0:
        return Idioma.INDETERMINADO, 0.0
    prop = n_es / total
    if prop >= 0.70:
        return Idioma.ESPANOL, prop
    if prop <= 0.30:
        return Idioma.INGLES, 1 - prop
    return Idioma.MIXTO, 0.5


# ── Clasificacion de una pieza ────────────────────────────────────────────────

@dataclass
class IdiomaDePieza:
    """El veredicto sobre una pieza suelta, con lo que lo sostiene."""

    idioma: Idioma
    confianza: float
    letras: int
    texto_limpio: str
    cuenta_para_evidencia: bool
    motor: str = "lingua"
    detalle: str = ""

    @property
    def ratio_es(self) -> float | None:
        """Compatibilidad con la version 2: 1,0 español · 0,0 ingles · None si no.

        Ya no es una proporcion de palabras funcionales: es el veredicto del
        detector expresado en la misma escala, para que las series historicas
        sigan siendo legibles.
        """
        if not self.cuenta_para_evidencia:
            return None
        if self.idioma is Idioma.ESPANOL:
            return 1.0
        if self.idioma is Idioma.INGLES:
            return 0.0
        if self.idioma is Idioma.MIXTO:
            return 0.5
        return None


def clasificar_pieza(
    texto: str,
    *,
    min_letras: int = MIN_LETRAS_CAPTION,
    min_confianza: float = MIN_CONFIANZA,
) -> IdiomaDePieza:
    """Idioma de un caption, un comentario o una review.

    Devuelve INDETERMINADO cuando no hay con que decidir. **Nunca devuelve
    INGLES por defecto**: un caption de tres emoji no es un caption en ingles,
    y tratarlo como tal es como se llego a un 82% de "english" sobre alt-text.
    """
    limpio = limpiar_para_deteccion(texto)
    n = contar_letras(limpio)

    if n < min_letras:
        return IdiomaDePieza(
            idioma=Idioma.INDETERMINADO, confianza=0.0, letras=n,
            texto_limpio=limpio, cuenta_para_evidencia=False,
            motor=motor_en_uso(),
            detalle="solo %d letras utiles, se exigen %d" % (n, min_letras),
        )

    detector = _cargar_detector()
    if detector is None:
        idioma, conf = _heuristica(limpio)
        return IdiomaDePieza(
            idioma=idioma, confianza=conf, letras=n, texto_limpio=limpio,
            cuenta_para_evidencia=(idioma is not Idioma.INDETERMINADO
                                   and conf >= min_confianza),
            motor="heuristica",
            detalle="ESTIMADO con heuristica de palabras clave, no medido",
        )

    valores = detector.compute_language_confidence_values(limpio)
    if not valores:
        return IdiomaDePieza(
            idioma=Idioma.INDETERMINADO, confianza=0.0, letras=n,
            texto_limpio=limpio, cuenta_para_evidencia=False,
            motor="lingua", detalle="el detector no devolvio candidatos",
        )

    mejor = valores[0]
    codigo = {"SPANISH": Idioma.ESPANOL, "ENGLISH": Idioma.INGLES}.get(
        mejor.language.name, Idioma.INDETERMINADO
    )
    conf = float(mejor.value)

    if conf < min_confianza:
        return IdiomaDePieza(
            idioma=Idioma.INDETERMINADO, confianza=conf, letras=n,
            texto_limpio=limpio, cuenta_para_evidencia=False, motor="lingua",
            detalle="confianza %.2f por debajo del piso %.2f" % (conf, min_confianza),
        )

    return IdiomaDePieza(
        idioma=codigo, confianza=conf, letras=n, texto_limpio=limpio,
        cuenta_para_evidencia=True, motor="lingua",
        detalle="%s con confianza %.2f sobre %d letras" % (codigo.value, conf, n),
    )


def clasificar_comentario(texto: str) -> IdiomaDePieza:
    """Igual que clasificar_pieza pero con el piso corto de los comentarios."""
    return clasificar_pieza(
        texto,
        min_letras=MIN_LETRAS_COMENTARIO,
        min_confianza=MIN_CONFIANZA,
    )


# ── Agregado sobre el conjunto de piezas ─────────────────────────────────────

@dataclass
class PerfilDeIdioma:
    """El idioma del contenido de una persona, con su evidencia declarada."""

    n_piezas_totales: int
    n_piezas_validas: int
    n_espanol: int
    n_ingles: int
    n_mixto: int
    n_indeterminado: int
    ratio_espanol: float | None
    cumple_evidencia_matriz: bool
    #: Ratio español por pieza, en orden cronologico, para ver la evolucion.
    serie_ratio: list[float | None] = field(default_factory=list)
    nota_de_evidencia: str = ""
    motor: str = "lingua"

    @property
    def idioma_dominante(self) -> Idioma:
        if self.n_piezas_validas == 0 or self.ratio_espanol is None:
            return Idioma.INDETERMINADO
        if self.ratio_espanol >= 0.60:
            return Idioma.ESPANOL
        if self.ratio_espanol <= 0.15:
            return Idioma.INGLES
        return Idioma.MIXTO

    def intensidad_pq14(self, declara_acompanamiento: bool = False
                        ) -> tuple[int | None, str, str]:
        """(intensidad, grado de evidencia, texto de la regla) para P-Q14.

        Devuelve intensidad None cuando no hay piezas validas. None no es 0:
        0 significa "operacion integramente en ingles", que es una afirmacion.
        """
        if declara_acompanamiento:
            return 3, "E0", (
                "declara explicitamente que traduce o acompaña a sus clientes"
            )

        if self.n_piezas_validas == 0:
            return None, "", (
                "sin piezas de contenido legibles: no se puede afirmar ni negar "
                "el idioma de su operacion"
            )

        ratio = self.ratio_espanol or 0.0
        base = "%d de %d piezas validas" % (
            self.n_espanol + self.n_mixto, self.n_piezas_validas,
        )

        if ratio >= 0.50:
            intensidad, texto = 2, "mayoria del contenido en español (%s)" % base
        elif ratio > 0.0:
            intensidad, texto = 1, "contenido bilingue ocasional (%s)" % base
        else:
            intensidad, texto = 0, "contenido integramente en ingles (%s)" % base

        grado = "E1"
        if not self.cumple_evidencia_matriz:
            texto += (
                ". EVIDENCIA POR DEBAJO DEL ESTANDAR: la matriz exige >=%d piezas "
                "o >=%d reviews y hay %d piezas validas"
                % (MIN_PIEZAS_MATRIZ, MIN_REVIEWS_MATRIZ, self.n_piezas_validas)
            )
            intensidad = min(intensidad, 1)
        if self.motor == "heuristica":
            texto += (
                ". OJO: clasificado con heuristica de palabras clave, no con "
                "detector de idioma"
            )
        return intensidad, grado, texto


def perfilar(
    piezas: list[str],
    *,
    n_reviews: int = 0,
    min_letras: int = MIN_LETRAS_CAPTION,
) -> PerfilDeIdioma:
    """Agrega el idioma de varias piezas en orden cronologico.

    `piezas` va de mas antigua a mas reciente, para que `serie_ratio` sirva para
    ver la evolucion: alguien que empezo en ingles y viro a español es un
    prospecto distinto de alguien que siempre escribio en los dos.
    """
    clasificadas = [clasificar_pieza(p, min_letras=min_letras) for p in piezas]
    validas = [c for c in clasificadas if c.cuenta_para_evidencia]

    n_es = sum(1 for c in validas if c.idioma is Idioma.ESPANOL)
    n_en = sum(1 for c in validas if c.idioma is Idioma.INGLES)
    n_mx = sum(1 for c in validas if c.idioma is Idioma.MIXTO)
    n_ind = len(clasificadas) - len(validas)

    ratio = None
    if validas:
        # El mixto cuenta medio: es bilingue, no español.
        ratio = (n_es + 0.5 * n_mx) / len(validas)

    cumple = len(validas) >= MIN_PIEZAS_MATRIZ or n_reviews >= MIN_REVIEWS_MATRIZ
    nota = (
        "cumple el estandar de la matriz (%d piezas validas, %d reviews)"
        % (len(validas), n_reviews)
        if cumple else
        "POR DEBAJO del estandar de la matriz: %d piezas validas y %d reviews, "
        "se exigen %d o %d" % (len(validas), n_reviews,
                               MIN_PIEZAS_MATRIZ, MIN_REVIEWS_MATRIZ)
    )

    return PerfilDeIdioma(
        n_piezas_totales=len(clasificadas),
        n_piezas_validas=len(validas),
        n_espanol=n_es, n_ingles=n_en, n_mixto=n_mx, n_indeterminado=n_ind,
        ratio_espanol=ratio,
        cumple_evidencia_matriz=cumple,
        serie_ratio=[c.ratio_es for c in clasificadas],
        nota_de_evidencia=nota,
        motor=clasificadas[0].motor if clasificadas else motor_en_uso(),
    )


# ── Declaracion explicita de acompañamiento (intensidad 3, E0) ───────────────

_PATRONES_ACOMPANAMIENTO = (
    r"\bse habla espa[nñ]ol\b",
    r"\bhablo espa[nñ]ol\b",
    r"\bhablamos espa[nñ]ol\b",
    r"\bbiling[uü]e\b", r"\bbilingual\b",
    r"\bte acompa[nñ]o\b", r"\blos acompa[nñ]o\b",
    r"\bte traduzco\b", r"\btraduzco\b",
    r"\bte explico (?:todo|el proceso)\b",
    r"\bspanish speaking\b",
    r"\bi speak spanish\b",
    r"\bin your language\b", r"\ben tu idioma\b",
)


def declara_acompanamiento(bio: str | None, captions: list[str] | None = None
                           ) -> tuple[bool, str | None]:
    """Intensidad 3 de P-Q14 con evidencia E0: lo dice ella o el, con su texto.

    Devuelve (si, el fragmento literal) porque el fragmento va al dossier como
    `evidencia_ancla`: el texto que la persona escribio, no nuestra parafrasis.

    Esto **si** es busqueda de patron y no deteccion de idioma, a proposito: una
    declaracion explicita es una cadena concreta, no una estadistica.
    """
    fuentes = [("bio", bio or "")]
    if captions:
        fuentes.extend(("caption", c) for c in captions)

    for origen, texto in fuentes:
        sin_acentos = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        for patron in _PATRONES_ACOMPANAMIENTO:
            m = re.search(patron, sin_acentos, re.IGNORECASE)
            if m:
                inicio = max(0, m.start() - 40)
                fin = min(len(texto), m.end() + 40)
                return True, "%s: ...%s..." % (origen, texto[inicio:fin].strip())
    return False, None
