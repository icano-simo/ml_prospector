"""Orquestador de la capa de Instagram.

Que cambio respecto de la version anterior
------------------------------------------
La version anterior devolvia catorce booleanos y un `{}` cuando algo fallaba, y
ese `{}` se volvia `False` en las catorce columnas. Esta devuelve un objeto con
**estado del perfil**, **confianza del handle** y una **mascara de
disponibilidad por señal**.

La regla que ordena todo el modulo: *nunca se devuelve False donde corresponde
null.* Una señal ausente lleva su motivo, y el motivo importa -- un perfil
privado es un dato sobre la persona, un handle equivocado es un dato sobre
nuestro scraper.

Y la segunda: *si el handle no verifica, sus señales no se usan.* Un handle
equivocado no producia un error: producia catorce señales sobre la persona
equivocada.
"""
from __future__ import annotations

import random
import re
import time
import urllib.parse
from dataclasses import asdict, dataclass, field

from loguru import logger

from instagram import extraccion
from instagram.comentarios import (
    PerfilDeAudiencia,
    perfilar_audiencia,
    verificar_anonimato,
)
from instagram.estado import EstadoPerfil
from instagram.extraccion import PerfilCrudo
from instagram.idioma import PerfilDeIdioma, declara_acompanamiento, perfilar
from instagram.posts import (
    Cadencia,
    EngagementReal,
    RedDeMenciones,
    calcular_cadencia,
    calcular_engagement,
    construir_red,
    geotags_agregados,
    programas_agregados,
)
from instagram.verificacion import (
    Confianza,
    Verificacion,
    extraer_licencias_de_bio,
    verificar,
)

DDG = "https://duckduckgo.com/"

#: Candidatos a evaluar por realtor. La version anterior tomaba el primero que
#: apareciera en el HTML y por eso "encontraba" el 98,1%.
MAX_CANDIDATOS = 5

PAUSA_BUSQUEDA = (2.5, 5.0)

#: Rutas de Instagram que no son handles de persona.
_NO_SON_HANDLES = {
    "p", "reel", "reels", "explore", "accounts", "stories", "tv", "about",
    "privacy", "legal", "help", "tags", "directory", "developer", "api",
    "instagram", "web", "direct", "challenge", "emails", "session",
    "oauth", "graphql", "static", "images", "ajax", "your_activity",
}


# ── Resultado ─────────────────────────────────────────────────────────────────

@dataclass
class SenalesInstagram:
    """Lo que la capa de Instagram entrega al motor de reglas PACS.

    Cada campo que puede faltar es `None`, y `disponibilidad` dice por que.
    """

    # Identidad y estado
    handle: str | None = None
    url: str | None = None
    estado_perfil: str = EstadoPerfil.SIN_HANDLE.value
    motivo_estado: str = ""
    handle_confidence: str = Confianza.BAJA.value
    razon_confianza: str = ""
    candidatos_evaluados: list[dict] = field(default_factory=list)

    # Huella digital (S1)
    nombre_perfil: str | None = None
    bio: str | None = None
    seguidores: int | None = None
    n_posts_declarados: int | None = None
    categoria_declarada: str | None = None

    # Madurez tecnologica (S4)
    link_de_bio: str | None = None
    destino_link_de_bio: str | None = None
    titulos_de_destacadas: list[str] = field(default_factory=list)

    # Identidad cruzada
    licencias_en_bio: list[str] = field(default_factory=list)

    # Contenido (S3, S9) — CRUDO, no solo flags
    posts_crudos: list[dict] = field(default_factory=list)

    # Idioma (P-Q14)
    idioma: dict | None = None
    intensidad_pq14: int | None = None
    grado_pq14: str | None = None
    regla_pq14: str | None = None
    evidencia_ancla_idioma: str | None = None

    # Programas (P-Q01, P-Q07, P-Q17, P-Q19)
    programas: dict = field(default_factory=dict)

    # Relaciones (S6) y co-marketing (P-Q21)
    red_de_menciones: dict | None = None
    candidatas_a_lender: list[str] = field(default_factory=list)
    n_posts_co_marketing: int = 0

    # Produccion y cadencia (P-Q10, J-Q04)
    cadencia: dict | None = None
    n_posts_con_produccion: int = 0

    # R1 verdadero
    engagement: dict | None = None

    # S7 sub-estatal
    geotags: dict = field(default_factory=dict)

    # S8 (perfil de audiencia, agregado y anonimo)
    audiencia: dict | None = None

    # Anti-ICP
    marcadores_anti_icp: list[str] = field(default_factory=list)

    #: {nombre de señal: disponible}. El reporte de lote de esta fila.
    disponibilidad: dict[str, bool] = field(default_factory=dict)
    #: {nombre de señal: por que falta}
    motivos_de_ausencia: dict[str, str] = field(default_factory=dict)

    @property
    def senales_usables(self) -> bool:
        """False si el handle no verifica o el perfil no se leyo."""
        return (
            self.handle_confidence != Confianza.BAJA.value
            and self.estado_perfil == EstadoPerfil.PUBLICO_LEIDO.value
        )

    def a_fila(self) -> dict:
        """Aplanado para la sabana. Las listas y dicts van como JSON."""
        import json

        fila: dict = {}
        for clave, valor in asdict(self).items():
            if isinstance(valor, (list, dict)):
                fila["ig_" + clave] = json.dumps(valor, ensure_ascii=False, default=str) \
                    if valor else None
            else:
                fila["ig_" + clave] = valor
        return fila


# ── Busqueda de handle ────────────────────────────────────────────────────────

def _candidatos_de_ddg(nombre: str, estado: str, page) -> list[str]:
    """Handles candidatos, en orden de aparicion. **Ninguno esta verificado.**

    Se extraen de los `href` de los resultados, no del HTML completo. El bug
    anterior usaba `re.findall` sobre `page.content()`, que devuelve cualquier
    `instagram.com/...` de la pagina: anuncios, pie de pagina, resultados
    ajenos.
    """
    consultas = [
        'site:instagram.com "%s" realtor %s' % (nombre, estado),
        'site:instagram.com "%s" real estate %s' % (nombre, estado),
        'site:instagram.com %s realtor %s' % (nombre, estado),
    ]
    candidatos: list[str] = []

    for consulta in consultas:
        if len(candidatos) >= MAX_CANDIDATOS:
            break
        url = DDG + "?q=" + urllib.parse.quote_plus(consulta) + "&kl=us-en"
        codigo = extraccion._ir(page, url, timeout_ms=20_000)
        if codigo in (403, 429):
            logger.warning("DuckDuckGo limito la busqueda (HTTP %s)", codigo)
            time.sleep(random.uniform(30, 70))
            continue
        time.sleep(random.uniform(*PAUSA_BUSQUEDA))

        try:
            enlaces = page.query_selector_all("a[href*='instagram.com']")
        except Exception:  # noqa: BLE001
            continue

        for el in enlaces:
            href = el.get_attribute("href") or ""
            # DuckDuckGo envuelve los resultados; el real va en uddg=
            if "uddg=" in href:
                partes = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = (partes.get("uddg") or [href])[0]
            m = re.search(
                r"instagram\.com/([A-Za-z0-9_.]{2,30})(?:/|\?|$)", href
            )
            if not m:
                continue
            handle = m.group(1)
            if handle.lower() in _NO_SON_HANDLES:
                continue
            if handle not in candidatos:
                candidatos.append(handle)
            if len(candidatos) >= MAX_CANDIDATOS:
                break

    return candidatos


# ── Construccion de señales ───────────────────────────────────────────────────

def _disponibilidad(crudo: PerfilCrudo, ver: Verificacion) -> tuple[dict, dict]:
    """Que señales se pudieron acreditar y por que las otras no."""
    estado = crudo.diagnostico.estado
    legible = estado.contenido_legible
    confiable = ver.confianza.usable

    motivo_contenido = ""
    if not legible:
        motivo_contenido = estado.motivo()
    elif not confiable:
        motivo_contenido = (
            "el handle no verifico (%s): sus señales no se usan" % ver.razon
        )

    usable = legible and confiable
    disponible = {
        # Estas dos salen del meta y existen incluso en un perfil privado.
        "seguidores": crudo.seguidores is not None,
        "bio": bool(crudo.bio),
        # Estas exigen leer los posts Y que el handle verifique.
        "captions": usable and bool(crudo.posts),
        "idioma_contenido": usable and bool(crudo.captions()),
        "programas": usable and bool(crudo.posts),
        "menciones": usable and bool(crudo.posts),
        "co_marketing": usable and bool(crudo.posts),
        "cadencia": usable and sum(1 for p in crudo.posts if p.fecha) >= 2,
        "engagement": usable and any(
            p.engagement_absoluto() is not None for p in crudo.posts
        ),
        "geotags": usable and any(p.geotag for p in crudo.posts),
        "audiencia": usable and bool(crudo.comentarios),
        "destacadas": bool(crudo.titulos_de_destacadas),
        "link_de_bio": bool(crudo.link_de_bio),
    }

    motivos = {}
    for nombre, hay in disponible.items():
        if hay:
            continue
        if nombre in ("seguidores", "bio", "destacadas", "link_de_bio"):
            motivos[nombre] = motivo_contenido or "no estaba en el perfil"
        else:
            motivos[nombre] = motivo_contenido or (
                "el perfil se leyo pero no habia datos para esta señal"
            )
    return disponible, motivos


def _armar_senales(
    crudo: PerfilCrudo,
    ver: Verificacion,
    candidatos: list[dict],
    *,
    licencia_conocida: str | None = None,
) -> SenalesInstagram:
    s = SenalesInstagram(
        handle=crudo.handle,
        url=crudo.url,
        estado_perfil=crudo.diagnostico.estado.value,
        motivo_estado=crudo.diagnostico.evidencia,
        handle_confidence=ver.confianza.value,
        razon_confianza=ver.razon,
        candidatos_evaluados=candidatos,
        nombre_perfil=crudo.nombre_perfil,
        bio=crudo.bio,
        seguidores=crudo.seguidores,
        n_posts_declarados=crudo.n_posts_declarados,
        categoria_declarada=crudo.categoria_declarada,
        link_de_bio=crudo.link_de_bio,
        destino_link_de_bio=crudo.destino_link_de_bio,
        titulos_de_destacadas=list(crudo.titulos_de_destacadas),
        licencias_en_bio=extraer_licencias_de_bio(crudo.bio),
    )

    disponible, motivos = _disponibilidad(crudo, ver)
    s.disponibilidad = disponible
    s.motivos_de_ausencia = motivos

    if not (crudo.diagnostico.estado.contenido_legible and ver.confianza.usable):
        return s

    # Captions crudos: la fuente, no los flags.
    s.posts_crudos = [
        {
            "url": p.url,
            "fecha": p.fecha.isoformat() if p.fecha else None,
            "caption": p.caption,
            "tipo": p.tipo.value,
            "likes": p.likes,
            "n_comentarios": p.n_comentarios,
            "geotag": p.geotag,
        }
        for p in crudo.posts
    ]

    captions = crudo.captions()
    perfil_idioma: PerfilDeIdioma = perfilar(captions)
    s.idioma = {
        "n_piezas_totales": perfil_idioma.n_piezas_totales,
        "n_piezas_validas": perfil_idioma.n_piezas_validas,
        "n_espanol": perfil_idioma.n_espanol,
        "n_ingles": perfil_idioma.n_ingles,
        "n_mixto": perfil_idioma.n_mixto,
        "n_indeterminado": perfil_idioma.n_indeterminado,
        "ratio_espanol": perfil_idioma.ratio_espanol,
        "idioma_dominante": perfil_idioma.idioma_dominante.value,
        "cumple_evidencia_matriz": perfil_idioma.cumple_evidencia_matriz,
        "nota_de_evidencia": perfil_idioma.nota_de_evidencia,
        "serie_ratio": perfil_idioma.serie_ratio,
    }

    declara, fragmento = declara_acompanamiento(crudo.bio, captions)
    s.evidencia_ancla_idioma = fragmento
    intensidad, grado, regla = perfil_idioma.intensidad_pq14(
        declara_acompanamiento=declara
    )
    s.intensidad_pq14 = intensidad
    s.grado_pq14 = grado or None
    s.regla_pq14 = regla

    s.programas = {
        nombre: {
            "qualifier": datos["qualifier"],
            "n_posts": datos["n_posts"],
            "primer_post": datos["primer_post"].isoformat() if datos["primer_post"] else None,
            "ultimo_post": datos["ultimo_post"].isoformat() if datos["ultimo_post"] else None,
            "ejemplo": datos["ejemplo"],
        }
        for nombre, datos in programas_agregados(crudo.posts).items()
    }

    red: RedDeMenciones = construir_red(crudo.posts)
    s.red_de_menciones = {
        "top": red.top(10),
        "en_co_marketing": red.en_co_marketing,
        "n_posts_con_menciones": red.n_posts_con_menciones,
    }
    s.candidatas_a_lender = red.candidatas_a_lender
    s.n_posts_co_marketing = sum(1 for p in crudo.posts if p.es_co_marketing)
    s.n_posts_con_produccion = sum(1 for p in crudo.posts if p.senal_de_produccion)

    cad: Cadencia = calcular_cadencia(crudo.posts)
    s.cadencia = {
        "n_posts": cad.n_posts,
        "dias_cubiertos": cad.dias_cubiertos,
        "posts_por_semana": cad.posts_por_semana,
        "mediana_dias_entre_posts": cad.mediana_dias_entre_posts,
        "hueco_maximo_dias": cad.hueco_maximo_dias,
        "n_huecos_mayores_a_21d": cad.n_huecos_mayores_a_21d,
        "pico_tras_hueco": cad.pico_tras_hueco,
        "nota": cad.nota,
    }

    eng: EngagementReal = calcular_engagement(crudo.posts, crudo.seguidores)
    s.engagement = {
        "n_posts_con_datos": eng.n_posts_con_datos,
        "n_posts_totales": eng.n_posts_totales,
        "seguidores": eng.seguidores,
        "engagement_medio": eng.engagement_medio,
        "engagement_mediano": eng.engagement_mediano,
        "tasa_media": eng.tasa_media,
        "tasa_mediana": eng.tasa_mediana,
        "suficiente": eng.suficiente,
        "nota": eng.nota,
    }

    s.geotags = geotags_agregados(crudo.posts)

    if crudo.comentarios:
        audiencia: PerfilDeAudiencia = perfilar_audiencia(
            crudo.comentarios,
            n_posts_con_comentarios=crudo.n_posts_con_comentarios,
        )
        # Guarda redundante antes de guardar nada en disco.
        verificar_anonimato(audiencia)
        s.audiencia = {
            "n_comentarios": audiencia.n_comentarios,
            "n_de_terceros": audiencia.n_de_terceros,
            "n_del_agente": audiencia.n_del_agente,
            "tasa_de_respuesta_del_agente": audiencia.tasa_de_respuesta_del_agente,
            "fricciones": audiencia.fricciones,
            "idioma_terceros": audiencia.idioma_terceros,
            "ratio_espanol_terceros": audiencia.ratio_espanol_terceros,
            "redacciones_aplicadas": audiencia.redacciones_aplicadas,
            "nota_de_evidencia": audiencia.nota_de_evidencia,
        }

    marcadores: list[str] = []
    for p in crudo.posts:
        for m in p.marcadores_anti_icp:
            if m not in marcadores:
                marcadores.append(m)
    s.marcadores_anti_icp = marcadores

    return s


# ── Punto de entrada ──────────────────────────────────────────────────────────

def buscar_instagram(
    *,
    nombre: str,
    apellido: str,
    estado: str,
    page,
    licencia_conocida: str | None = None,
    con_comentarios: bool = True,
) -> SenalesInstagram:
    """Busca, verifica y lee el perfil de Instagram de un realtor.

    Evalua hasta `MAX_CANDIDATOS` handles y **se queda con el primero que
    verifique**, no con el primero que aparezca. Si ninguno verifica, devuelve
    el mejor con `handle_confidence = baja` y sus señales sin usar: un handle de
    confianza baja sigue siendo un punto de partida para revision manual.
    """
    nombre_completo = ("%s %s" % (nombre or "", apellido or "")).strip()
    if not nombre_completo:
        s = SenalesInstagram()
        s.motivo_estado = "sin nombre de realtor"
        return s

    candidatos = _candidatos_de_ddg(nombre_completo, estado or "", page)
    if not candidatos:
        s = SenalesInstagram(estado_perfil=EstadoPerfil.SIN_HANDLE.value)
        s.motivo_estado = "la busqueda no devolvio ningun handle candidato"
        s.disponibilidad = {k: False for k in (
            "seguidores", "bio", "captions", "idioma_contenido", "programas",
            "menciones", "co_marketing", "cadencia", "engagement", "geotags",
            "audiencia", "destacadas", "link_de_bio",
        )}
        s.motivos_de_ausencia = {
            k: "no se encontro handle" for k in s.disponibilidad
        }
        return s

    evaluados: list[dict] = []
    mejor: tuple[PerfilCrudo, Verificacion] | None = None

    for handle in candidatos:
        crudo = extraccion.leer_con_backoff(
            page, handle, con_comentarios=False,
        )
        licencias = extraer_licencias_de_bio(crudo.bio)
        coincide_licencia = (
            licencia_conocida
            and any(l.lstrip("0") == licencia_conocida.lstrip("0") for l in licencias)
        )
        ver = verificar(
            nombre_realtor=nombre_completo,
            handle=handle,
            nombre_perfil=crudo.nombre_perfil,
            bio=crudo.bio,
            captions=crudo.captions() or None,
            licencia_en_bio=licencia_conocida if coincide_licencia else None,
        )
        evaluados.append({
            "handle": handle,
            "estado": crudo.diagnostico.estado.value,
            "confianza": ver.confianza.value,
            "razon": ver.razon,
        })
        logger.info(
            "@%s -> %s / confianza %s", handle,
            crudo.diagnostico.estado.value, ver.confianza.value,
        )

        if mejor is None or _mejor_que(ver, mejor[1]):
            mejor = (crudo, ver)
        if ver.confianza is Confianza.ALTA:
            break
        time.sleep(random.uniform(*PAUSA_BUSQUEDA))

    assert mejor is not None
    crudo, ver = mejor

    # Recien ahora, con el handle elegido y verificado, se paga el costo de
    # leer posts y comentarios. Hacerlo por cada candidato multiplicaria por
    # cinco las peticiones a Instagram.
    if ver.confianza.usable and crudo.handle:
        crudo = extraccion.leer_con_backoff(
            page, crudo.handle, con_comentarios=con_comentarios,
        )
        if crudo.link_de_bio:
            crudo.destino_link_de_bio = extraccion.resolver_destino_de_link(
                page, crudo.link_de_bio,
            )
        ver = verificar(
            nombre_realtor=nombre_completo,
            handle=crudo.handle,
            nombre_perfil=crudo.nombre_perfil,
            bio=crudo.bio,
            captions=crudo.captions() or None,
            licencia_en_bio=licencia_conocida if any(
                l.lstrip("0") == (licencia_conocida or "x").lstrip("0")
                for l in extraer_licencias_de_bio(crudo.bio)
            ) else None,
        )

    return _armar_senales(crudo, ver, evaluados, licencia_conocida=licencia_conocida)


def _mejor_que(nueva: Verificacion, actual: Verificacion) -> bool:
    orden = {Confianza.ALTA: 3, Confianza.MEDIA: 2, Confianza.BAJA: 1}
    return orden[nueva.confianza] > orden[actual.confianza]
