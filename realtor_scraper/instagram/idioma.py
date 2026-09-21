"""Deteccion de idioma sobre texto real, con el umbral de evidencia de la matriz.

Por que existe este modulo
--------------------------
La version anterior contaba palabras españolas sobre el `alt` de las imagenes,
que Meta genera automaticamente en ingles. Resultado medido sobre 5.620 filas:
`ig_content_language = spanish` en **185 filas, 3,29%**, en un lote seleccionado
por mercado latino.

Y la matriz exige, para P-Q14, **deteccion de idioma sobre >=10 piezas o >=5
reviews**. Con una bio de 150 caracteres eso no se cumple, y la referencia 11 de
la skill dice explicitamente que la inferencia es mas debil que lo que la propia
metodologia pide. Este modulo cuenta las piezas y lo declara.

La escala de P-Q14, literal de la matriz
----------------------------------------
    0 = operacion integramente en ingles
    1 = contenido bilingue ocasional
    2 = mayoria del contenido o de las reviews en español
    3 = declara explicitamente que traduce o acompaña a sus clientes

Distinguir 1 de 2 es lo que el alt-text nunca pudo hacer, porque no medía
proporcion: medía presencia de palabras en un texto que ni era del agente.

Metodo
------
Palabras funcionales y diacriticos, no un modelo. Es deliberado:

- funciona sin dependencias y es auditable palabra por palabra;
- un caption inmobiliario mezcla nombres propios, hashtags y emoji, donde los
  clasificadores genericos se equivocan;
- y se puede explicar en un dossier, que es un requisito real: cada eslabon de
  la cadena de inferencia tiene que poder mostrarse.

Lo que NO se hace
-----------------
No se infiere idioma desde el apellido, el nombre ni el origen de nadie. Se mide
el idioma del texto que la persona escribio.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum

#: Piezas minimas que la matriz exige para sostener P-Q14 con su estandar.
MIN_PIEZAS_MATRIZ = 10
MIN_REVIEWS_MATRIZ = 5

#: Caracteres minimos para que una pieza cuente. Un caption de tres emoji y un
#: hashtag no informa sobre el idioma de nadie.
MIN_CARACTERES_PIEZA = 25


class Idioma(str, Enum):
    ESPANOL = "es"
    INGLES = "en"
    MIXTO = "mixto"
    INDETERMINADO = "indeterminado"


# ── Lexicos funcionales ───────────────────────────────────────────────────────
#
# Palabras funcionales, no de contenido. Las de contenido ("casa", "familia")
# aparecen en textos en ingles de agentes latinos y no distinguen idioma: un
# caption que dice "Your new casa awaits" es ingles.

_FUNCIONALES_ES = {
    "que", "de", "la", "el", "los", "las", "un", "una", "unos", "unas",
    "para", "por", "con", "sin", "sobre", "entre", "desde", "hasta",
    "como", "cuando", "donde", "porque", "pero", "aunque", "si", "no",
    "es", "son", "esta", "estan", "fue", "ser", "estar", "hay", "tiene",
    "tienen", "puede", "pueden", "quiero", "quieres", "quiere", "vamos",
    "estoy", "estamos", "somos", "soy", "tu", "tus", "mi", "mis", "su",
    "sus", "nuestro", "nuestra", "te", "me", "se", "lo", "le", "les",
    "ya", "muy", "mas", "tambien", "aqui", "alli", "ahora", "hoy",
    "manana", "siempre", "nunca", "todo", "todos", "toda", "todas",
    "mucho", "muchos", "poco", "algo", "nada", "quien", "cual", "cuanto",
    "del", "al", "esto", "esta", "ese", "esa", "aquel", "otro", "otra",
    "asi", "bien", "gracias", "felicidades", "bienvenidos", "bienvenida",
}

_FUNCIONALES_EN = {
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "with",
    "without", "about", "between", "from", "until", "and", "or", "but",
    "because", "if", "not", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "can", "could",
    "will", "would", "should", "may", "might", "must", "this", "that",
    "these", "those", "it", "its", "you", "your", "yours", "my", "mine",
    "our", "ours", "their", "his", "her", "we", "they", "he", "she",
    "there", "here", "now", "today", "tomorrow", "always", "never",
    "all", "some", "any", "more", "most", "very", "just", "also",
    "who", "which", "what", "when", "where", "how", "why", "who",
    "congratulations", "welcome", "thanks", "thank",
}

#: Palabras en ingles que un agente latino usa en medio de un texto en español
#: porque son terminos del oficio. No cuentan como señal de ingles.
_TERMINOS_DE_OFICIO = {
    "realtor", "realty", "broker", "listing", "listings", "open", "house",
    "closing", "escrow", "mls", "condo", "townhouse", "loan", "mortgage",
    "fha", "va", "usda", "conventional", "preapproval", "under", "contract",
    "sold", "buyer", "seller", "downpayment", "dpa", "itin", "credit",
    "score", "homeready", "homepath", "refinance", "appraisal",
}

_DIACRITICOS_ES = "ñáéíóúü¿¡"

#: `ing` final es el marcador morfologico mas util del ingles en textos cortos.
_RE_GERUNDIO_EN = re.compile(r"\b[a-z]{3,}ing\b")
#: Terminaciones verbales tipicas del español.
_RE_VERBAL_ES = re.compile(r"\b[a-z]{3,}(?:ando|iendo|amos|emos|imos|aste|aron|aran)\b")


def _tokenizar(texto: str) -> list[str]:
    """Palabras comparables. Saca hashtags, menciones, URLs y emoji."""
    t = texto or ""
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[@#][\w.]+", " ", t)
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", t)
        if unicodedata.category(c) != "Mn"
    )
    sin_acentos = sin_acentos.lower()
    return [w for w in re.findall(r"[a-z]{2,}", sin_acentos)]


@dataclass
class IdiomaDePieza:
    """El veredicto sobre una pieza suelta, con lo que lo sostiene."""

    idioma: Idioma
    n_es: int
    n_en: int
    n_tokens: int
    diacriticos: int
    cuenta_para_evidencia: bool
    detalle: str = ""

    @property
    def ratio_es(self) -> float | None:
        """Fraccion de la señal funcional que es española. None si no hay señal."""
        total = self.n_es + self.n_en
        return None if total == 0 else self.n_es / total


def clasificar_pieza(texto: str) -> IdiomaDePieza:
    """Idioma de un caption, un comentario o una review.

    Devuelve INDETERMINADO cuando no hay con que decidir. **Nunca devuelve
    INGLES por defecto**: un caption de tres emoji no es un caption en ingles, y
    tratarlo como tal es como se llego a un 82% de "english" sobre alt-text.
    """
    crudo = texto or ""
    tokens = _tokenizar(crudo)
    diacriticos = sum(1 for c in crudo.lower() if c in _DIACRITICOS_ES)

    utiles = [t for t in tokens if t not in _TERMINOS_DE_OFICIO]
    n_es = sum(1 for t in utiles if t in _FUNCIONALES_ES)
    n_en = sum(1 for t in utiles if t in _FUNCIONALES_EN)

    # Morfologia, que ayuda en textos cortos donde no hay funcionales.
    n_es += len(_RE_VERBAL_ES.findall(" ".join(utiles)))
    n_en += len(_RE_GERUNDIO_EN.findall(" ".join(utiles)))

    # Los diacriticos son señal fuerte pero no infinita: dos tildes no vuelven
    # español a un texto de cuarenta palabras en ingles.
    n_es += min(diacriticos, 3)

    cuenta = len(crudo.strip()) >= MIN_CARACTERES_PIEZA and (n_es + n_en) >= 2

    if n_es + n_en == 0:
        return IdiomaDePieza(
            idioma=Idioma.INDETERMINADO, n_es=0, n_en=0, n_tokens=len(tokens),
            diacriticos=diacriticos, cuenta_para_evidencia=False,
            detalle="sin palabras funcionales de ninguno de los dos idiomas",
        )

    total = n_es + n_en
    prop_es = n_es / total
    if prop_es >= 0.70:
        idioma = Idioma.ESPANOL
    elif prop_es <= 0.30:
        idioma = Idioma.INGLES
    else:
        idioma = Idioma.MIXTO

    return IdiomaDePieza(
        idioma=idioma, n_es=n_es, n_en=n_en, n_tokens=len(tokens),
        diacriticos=diacriticos, cuenta_para_evidencia=cuenta,
        detalle="es=%d en=%d diacriticos=%d" % (n_es, n_en, diacriticos),
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

    @property
    def idioma_dominante(self) -> Idioma:
        if self.n_piezas_validas == 0:
            return Idioma.INDETERMINADO
        if self.ratio_espanol is None:
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
        return intensidad, grado, texto


def perfilar(piezas: list[str], *, n_reviews: int = 0) -> PerfilDeIdioma:
    """Agrega el idioma de varias piezas en orden cronologico.

    `piezas` va de mas antigua a mas reciente, para que `serie_ratio` sirva para
    ver la evolucion: alguien que empezo en ingles y viro a español es un
    prospecto distinto de alguien que siempre escribio en los dos.
    """
    clasificadas = [clasificar_pieza(p) for p in piezas]
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
