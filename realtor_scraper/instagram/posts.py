"""Posts con caption real y fecha, y todo lo que se deriva de ellos.

Reemplaza el analisis sobre `article img[alt]`, que leia el texto de
accesibilidad que genera Meta automaticamente, casi siempre en ingles sin
importar el idioma del caption.

Lo que se guarda y por que
--------------------------
**El caption crudo, no solo los flags.** Los flags cambian cuando cambian las
reglas; el texto no. Un lexico que hoy no busca "203k" lo va a buscar mañana, y
re-scrapear 5.000 perfiles para eso es absurdo cuando se puede re-derivar.

Campos y el qualifier que alimentan
-----------------------------------
| campo | alimenta |
|---|---|
| `caption` + `fecha` | P-Q14 con la evidencia que la matriz exige (>=10 piezas) |
| ratio español/ingles por post y su evolucion | distingue intensidad 1 de 2 |
| `menciones` y `etiquetadas` | S6 gratis: si etiqueta a un loan officer, ahi esta su lender |
| `co_marketing` | S6 + P-Q21 (exposicion RESPA) |
| `programas` | P-Q01, P-Q07, P-Q17, P-Q19 |
| `tipo`, cadencia, huecos | P-Q10, J-Q04 |
| `likes` + `comentarios` / seguidores | R1 verdadero |
| `geotag` | S7 sub-estatal |
"""
from __future__ import annotations

import datetime as dt
import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from enum import Enum


class TipoDePost(str, Enum):
    IMAGEN = "imagen"
    CARRUSEL = "carrusel"
    REEL = "reel"
    VIDEO = "video"
    DESCONOCIDO = "desconocido"


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )


# ── Lexico de programas ───────────────────────────────────────────────────────
#
# Cada entrada declara el qualifier que alimenta. La tabla no es decorativa: es
# lo que permite que el dossier cite de donde salio el diagnostico.
#
# Todos los patrones llevan limite de palabra. La razon esta documentada en la
# referencia 11 de la skill: `\bestates?\b` matchea "real estate" y clasifico
# como perfil de lujo a mas de mil agentes antes de detectarse.

LEXICO_PROGRAMAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "fha": ("P-Q01/P-Q07", (r"\bfha\b", r"\bf\.h\.a\.\b")),
    "va": ("P-Q17", (r"\bva loan\b", r"\bva home\b", r"\bva benefit\b",
                     r"\bpr[eé]stamo va\b", r"\bveteran[oa]?s?\b",
                     r"\bmilitar(?:y|es)?\b", r"\bactive duty\b", r"\bpcs\b")),
    "usda": ("P-Q01", (r"\busda\b", r"\brural development\b")),
    "203k": ("P-Q01", (r"\b203\s?k\b", r"\brenovation loan\b",
                       r"\bpr[eé]stamo de renovaci[oó]n\b")),
    "itin": ("P-Q01", (r"\bitin\b", r"\btax\s?id\b",
                       r"\bsin (?:seguro social|ssn)\b", r"\bno ssn\b")),
    "dpa": ("P-Q07", (r"\bdpa\b", r"\bdown payment assistance\b",
                      r"\bdown\s?payment help\b", r"\bayuda (?:con|para) el enganche\b",
                      r"\bsubvenci[oó]n\b", r"\bgrant\b", r"\bzero down\b",
                      r"\bsin enganche\b", r"\b0% down\b")),
    "credito": ("P-Q19", (r"\bcredit repair\b", r"\bcredit score\b",
                          r"\bbad credit\b", r"\breparaci[oó]n de cr[eé]dito\b",
                          r"\bpuntaje de cr[eé]dito\b", r"\bsubir tu cr[eé]dito\b",
                          r"\bbankruptcy\b", r"\bforeclosure\b", r"\bquiebra\b")),
    "self_employed": ("P-Q01/P-Q20", (r"\bself[\s-]?employed\b", r"\b1099\b",
                                      r"\bbank statement loan\b",
                                      r"\bbusiness owner\b", r"\bnegocio propio\b",
                                      r"\bcuenta propia\b", r"\bindependiente\b")),
    "preaprobacion": ("P-Q12", (r"\bpre[\s-]?approv\w*\b", r"\bpre[\s-]?qual\w*\b",
                                r"\bprecalifi\w*\b", r"\bpre[\s-]?aprobaci[oó]n\b")),
    "primera_compra": ("P-Q07/P-Q12", (r"\bfirst[\s-]?time (?:home\s?)?buyer\b",
                                       r"\bprimera casa\b", r"\bprimer hogar\b",
                                       r"\bstop renting\b", r"\bdeja de rentar\b",
                                       r"\bdejar de rentar\b")),
    "inversion": ("P-Q09", (r"\binvestment propert\w+\b", r"\brental propert\w+\b",
                            r"\bairbnb\b", r"\bmultifamily\b", r"\bportfolio loan\b",
                            r"\bcash flow\b", r"\bpropiedad de inversi[oó]n\b")),
}

#: Anti-ICP. Dos o mas marcadores -> descartado, sin importar el score.
#: `\bestates?\b` NO esta aca, a proposito. Ver arriba.
LEXICO_ANTI_ICP: tuple[str, ...] = (
    r"\bluxury\b", r"\bluxurious\b", r"\bwaterfront\b", r"\bpenthouse\b",
    r"\bmulti[\s-]?million\b", r"\bmillion dollar\b", r"\bestate homes?\b",
    r"\bluxury estates?\b", r"\bultra[\s-]?luxury\b", r"\bbespoke\b",
    r"\bconcierge\b", r"\byacht\b", r"\bequestrian\b",
)

#: Co-marketing: taller conjunto, evento con otro profesional, seminario.
#: Alimenta S6 y P-Q21 (exposicion RESPA).
LEXICO_CO_MARKETING: tuple[str, ...] = (
    r"\bco[\s-]?host(?:ed|ing)?\b", r"\bjoin(?:t)? (?:me|us) (?:and|with)\b",
    r"\bworkshop\b", r"\btaller\b", r"\bseminar(?:io)?\b", r"\bwebinar\b",
    r"\bcharla\b", r"\bclase gratis\b", r"\bfree class\b",
    r"\bhomebuyer (?:class|workshop|seminar)\b",
    r"\bevento\b", r"\bopen house con\b", r"\bpartnered with\b",
    r"\ben conjunto con\b", r"\bjunto a\b", r"\bcolabora\w* con\b",
)

#: Produccion de contenido propia. Alimenta P-Q10 y J-Q04.
LEXICO_PRODUCCION: tuple[str, ...] = (
    r"\breel\b", r"\bnew video\b", r"\bnuevo video\b", r"\bpodcast\b",
    r"\byoutube\b", r"\btiktok\b", r"\bbehind the scenes\b", r"\bepisodio\b",
)


def _detectar(patrones: tuple[str, ...], texto: str) -> list[str]:
    encontrados = []
    for p in patrones:
        if re.search(p, texto, re.IGNORECASE):
            encontrados.append(p)
    return encontrados


# ── Post ──────────────────────────────────────────────────────────────────────

#: Una @mencion de verdad, no la cola de un email.
#:
#: Medido sobre la captura real del piloto: el patron ingenuo `@([\w.]{2,30})`
#: daba `@gmail.com` diez veces en un solo perfil y `@mpowerrealtors.com`
#: cuatro, porque los captions llevan el email del agente. Eso no es ruido
#: inocuo: inflaba `etiquetadas`, ponia `tiene_socio = True` en casi todo post
#: con firma de contacto —y con eso `posts_comarketing`— y un caption con
#: `maria@titlecompanyx.com` habria producido `menciona_lender =
#: @titlecompanyx.com`, o sea un socio hipotecario inventado.
#:
#: Dos guardas: el `@` no puede venir pegado a una letra, un digito o un punto
#: (que es lo que lo separa de un email), y la cuenta tiene que empezar por
#: letra o digito. El punto final se recorta aparte, porque `@cuenta.` es una
#: mencion al final de una frase.
_RE_MENCION = re.compile(r"(?<![A-Za-z0-9_.])@([A-Za-z0-9_][A-Za-z0-9_.]{1,29})")
_RE_HASHTAG = re.compile(r"#([\wÀ-ɏ]{2,60})", re.UNICODE)


def menciones_de_texto(texto: str | None) -> list[str]:
    """Las @cuentas de un texto, en minuscula, sin repetir y en orden.

    Es la unica via: `finder.py` tenia su propia copia del patron, y arreglar
    una sin la otra es como quedo el bug del alt-text.
    """
    if not texto:
        return []
    crudas = (m.rstrip(".").lower() for m in _RE_MENCION.findall(texto))
    return list(dict.fromkeys(m for m in crudas if len(m) >= 2))


@dataclass
class Post:
    """Un post con su caption crudo y su fecha.

    `caption` se guarda entero y sin procesar. Es la fuente; todo lo demas se
    re-deriva.
    """

    url: str | None = None
    fecha: dt.date | None = None
    caption: str = ""
    tipo: TipoDePost = TipoDePost.DESCONOCIDO
    likes: int | None = None
    n_comentarios: int | None = None
    geotag: str | None = None

    @property
    def menciones(self) -> list[str]:
        """@cuentas en el caption. S6 gratis: si etiqueta a un loan officer o a
        una hipotecaria, ahi esta su lender."""
        return menciones_de_texto(self.caption)

    @property
    def hashtags(self) -> list[str]:
        return list(dict.fromkeys(h.lower() for h in _RE_HASHTAG.findall(self.caption)))

    @property
    def programas(self) -> dict[str, str]:
        """{programa: qualifier que alimenta} detectados en el caption."""
        texto = _sin_acentos(self.caption)
        salida: dict[str, str] = {}
        for nombre, (qualifier, patrones) in LEXICO_PROGRAMAS.items():
            if _detectar(patrones, texto):
                salida[nombre] = qualifier
        return salida

    @property
    def marcadores_anti_icp(self) -> list[str]:
        return _detectar(LEXICO_ANTI_ICP, _sin_acentos(self.caption))

    @property
    def es_co_marketing(self) -> bool:
        """Taller conjunto o evento con otro profesional. S6 + P-Q21."""
        texto = _sin_acentos(self.caption)
        return bool(_detectar(LEXICO_CO_MARKETING, texto)) and bool(self.menciones)

    @property
    def senal_de_produccion(self) -> bool:
        return bool(_detectar(LEXICO_PRODUCCION, _sin_acentos(self.caption))) or \
            self.tipo in (TipoDePost.REEL, TipoDePost.VIDEO)

    def engagement_absoluto(self) -> int | None:
        """likes + comentarios. None si falta alguno: no se suma con un cero
        inventado."""
        if self.likes is None or self.n_comentarios is None:
            return None
        return self.likes + self.n_comentarios


# ── Agregados sobre el conjunto de posts ─────────────────────────────────────

@dataclass
class Cadencia:
    """Ritmo de publicacion y sus huecos. Alimenta P-Q10 y J-Q04.

    Un hueco de tres semanas seguido de un pico es la firma del "lo produzco yo
    el domingo": nadie sostiene una maquina de contenido con ese patron, asi que
    el costo de produccion es propio y ese es el angulo A8.
    """

    n_posts: int
    dias_cubiertos: int | None
    posts_por_semana: float | None
    mediana_dias_entre_posts: float | None
    hueco_maximo_dias: int | None
    n_huecos_mayores_a_21d: int
    pico_tras_hueco: bool
    nota: str = ""


def calcular_cadencia(posts: list[Post]) -> Cadencia:
    fechados = sorted((p for p in posts if p.fecha), key=lambda p: p.fecha)  # type: ignore[arg-type,return-value]
    if len(fechados) < 2:
        return Cadencia(
            n_posts=len(posts), dias_cubiertos=None, posts_por_semana=None,
            mediana_dias_entre_posts=None, hueco_maximo_dias=None,
            n_huecos_mayores_a_21d=0, pico_tras_hueco=False,
            nota="menos de 2 posts con fecha: no se puede hablar de cadencia",
        )

    fechas = [p.fecha for p in fechados]
    deltas = [(fechas[i + 1] - fechas[i]).days for i in range(len(fechas) - 1)]
    cubiertos = (fechas[-1] - fechas[0]).days or 1
    huecos_grandes = [d for d in deltas if d > 21]

    # Pico tras hueco: tres o mas posts en los 7 dias siguientes a un hueco >21d.
    pico = False
    for i, d in enumerate(deltas):
        if d <= 21:
            continue
        inicio = fechas[i + 1]
        cercanos = sum(1 for f in fechas if 0 <= (f - inicio).days <= 7)
        if cercanos >= 3:
            pico = True
            break

    return Cadencia(
        n_posts=len(fechados),
        dias_cubiertos=cubiertos,
        posts_por_semana=round(len(fechados) / (cubiertos / 7.0), 2),
        mediana_dias_entre_posts=float(statistics.median(deltas)),
        hueco_maximo_dias=max(deltas),
        n_huecos_mayores_a_21d=len(huecos_grandes),
        pico_tras_hueco=pico,
        nota=(
            "hueco de %d dias seguido de un pico: la firma de la produccion "
            "propia sin equipo" % max(deltas)
        ) if pico else "",
    )


@dataclass
class EngagementReal:
    """(likes + comentarios) / seguidores. Es R1 de verdad.

    El proxy anterior era seguidores, o seguidores/posts. Medido sobre el
    dataset archivado, `ig_followers` correlaciona con `units_sold`:
    Pearson crudo **+0,0014**, log1p **+0,078**, Spearman **+0,075** (n=3.234).
    Es decir: nada.
    """

    n_posts_con_datos: int
    n_posts_totales: int
    seguidores: int | None
    engagement_medio: float | None
    engagement_mediano: float | None
    tasa_media: float | None
    tasa_mediana: float | None
    nota: str = ""

    @property
    def suficiente(self) -> bool:
        return self.n_posts_con_datos >= 5 and bool(self.seguidores)


def calcular_engagement(posts: list[Post], seguidores: int | None) -> EngagementReal:
    valores = [p.engagement_absoluto() for p in posts]
    validos = [v for v in valores if v is not None]

    if not validos:
        return EngagementReal(
            n_posts_con_datos=0, n_posts_totales=len(posts), seguidores=seguidores,
            engagement_medio=None, engagement_mediano=None,
            tasa_media=None, tasa_mediana=None,
            nota="ningun post trae likes y comentarios a la vez",
        )

    medio = statistics.fmean(validos)
    mediano = float(statistics.median(validos))
    tasa_media = tasa_mediana = None
    nota = ""
    if seguidores and seguidores > 0:
        tasa_media = medio / seguidores
        tasa_mediana = mediano / seguidores
    else:
        nota = "sin numero de seguidores: solo hay engagement absoluto, no tasa"

    if len(validos) < 5:
        nota = (nota + " · " if nota else "") + (
            "solo %d posts con engagement: la tasa es inestable" % len(validos)
        )

    return EngagementReal(
        n_posts_con_datos=len(validos), n_posts_totales=len(posts),
        seguidores=seguidores,
        engagement_medio=round(medio, 2), engagement_mediano=mediano,
        tasa_media=round(tasa_media, 5) if tasa_media is not None else None,
        tasa_mediana=round(tasa_mediana, 5) if tasa_mediana is not None else None,
        nota=nota,
    )


@dataclass
class RedDeMenciones:
    """A quien etiqueta y cuantas veces. Es la via mas barata a S6.

    S6 (relaciones con lenders) esta vacia en casi todos los lotes y es la
    categoria que mas decidiria el discurso. Si el agente etiqueta a un loan
    officer o a una hipotecaria en sus posts, esta diciendo con quien trabaja.
    """

    conteo: dict[str, int] = field(default_factory=dict)
    en_co_marketing: dict[str, int] = field(default_factory=dict)
    n_posts_con_menciones: int = 0

    def top(self, n: int = 10) -> list[tuple[str, int]]:
        return sorted(self.conteo.items(), key=lambda kv: (-kv[1], kv[0]))[:n]

    @property
    def candidatas_a_lender(self) -> list[str]:
        """Cuentas cuyo handle sugiere financiamiento. **Es una pista, no un
        hecho**: hay que confirmarla contra NMLS antes de escribirla en un
        dossier. El handle de alguien no prueba su oficio."""
        pistas = (
            "loan", "lend", "mortgage", "hipotec", "prestamo", "nmls",
            "financ", "credito", "credit", "escrow", "title",
        )
        return sorted(
            h for h in self.conteo
            if any(p in h for p in pistas)
        )


def construir_red(posts: list[Post]) -> RedDeMenciones:
    red = RedDeMenciones()
    for p in posts:
        menciones = p.menciones
        if menciones:
            red.n_posts_con_menciones += 1
        for m in menciones:
            red.conteo[m] = red.conteo.get(m, 0) + 1
            if p.es_co_marketing:
                red.en_co_marketing[m] = red.en_co_marketing.get(m, 0) + 1
    return red


def programas_agregados(posts: list[Post]) -> dict[str, dict]:
    """{programa: {qualifier, n_posts, primer_post, ultimo_post, ejemplo}}.

    `ejemplo` guarda el fragmento literal del caption, porque es lo que va al
    dossier como `evidencia_ancla`: el texto que la persona escribio.
    """
    salida: dict[str, dict] = {}
    for p in posts:
        for nombre, qualifier in p.programas.items():
            entrada = salida.setdefault(nombre, {
                "qualifier": qualifier, "n_posts": 0,
                "primer_post": None, "ultimo_post": None, "ejemplo": None,
            })
            entrada["n_posts"] += 1
            if p.fecha:
                if entrada["primer_post"] is None or p.fecha < entrada["primer_post"]:
                    entrada["primer_post"] = p.fecha
                if entrada["ultimo_post"] is None or p.fecha > entrada["ultimo_post"]:
                    entrada["ultimo_post"] = p.fecha
            if entrada["ejemplo"] is None and p.caption:
                entrada["ejemplo"] = p.caption[:280]
    return salida


def geotags_agregados(posts: list[Post]) -> dict[str, int]:
    """Lugares etiquetados. S7 sub-estatal, que el lote nunca trae."""
    conteo: dict[str, int] = {}
    for p in posts:
        if p.geotag:
            clave = p.geotag.strip()
            if clave:
                conteo[clave] = conteo.get(clave, 0) + 1
    return dict(sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0])))
