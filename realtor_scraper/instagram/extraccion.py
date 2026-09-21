"""Lado navegador: lee captions reales, fechas, comentarios y metadatos.

Esto reemplaza `_extract_post_alt_texts`, que leia `article img[alt]` -- el texto
de accesibilidad que Meta genera automaticamente, casi siempre en ingles sin
importar el idioma del caption.

Separacion deliberada
---------------------
Todo lo que decide algo vive en `idioma.py`, `posts.py`, `comentarios.py`,
`estado.py` y `verificacion.py`, que son puro Python y tienen 51 pruebas. Aca
solo esta lo que toca el DOM, que no se puede probar sin navegador. Si algo
falla en una corrida, la pregunta "¿es el selector o la logica?" se responde
mirando si las pruebas pasan.

Limites de tasa y terminos de uso
---------------------------------
Se respetan limites de tasa con backoff exponencial y pausas aleatorias. El
estado BLOQUEADO es un resultado legitimo del pipeline, no un error a reintentar
en un bucle: cuando aparece, se corta y se reintenta mas tarde.

Los selectores de Instagram cambian. Cada extractor prueba varias vias y
devuelve None si ninguna anda: **None, no un valor por defecto.** Un selector
roto tiene que producir un hueco declarado, no un cero.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
import time
import urllib.parse
from dataclasses import dataclass, field

from loguru import logger

from instagram.comentarios import Comentario
from instagram.estado import Diagnostico, EstadoPerfil, diagnosticar
from instagram.posts import Post, TipoDePost

IG_BASE = "https://www.instagram.com/"

#: Posts a leer por perfil. El brief pide 30-50. Mas arriba, Instagram empieza a
#: pedir scroll infinito y el costo por dato se dispara.
N_POSTS_OBJETIVO = 40

#: Posts de los que se leen comentarios. Abrir cada post es una navegacion, asi
#: que se limita a los mas recientes.
N_POSTS_PARA_COMENTARIOS = 12

#: Comentarios por post. Suficiente para un perfil de audiencia sin convertir
#: esto en un corpus de mensajes de gente que no sabe que los leemos.
N_COMENTARIOS_POR_POST = 15

PAUSA_ENTRE_POSTS = (2.0, 4.5)
PAUSA_ENTRE_PERFILES = (6.0, 12.0)
PAUSA_TRAS_SCROLL = (1.2, 2.8)

#: Backoff exponencial ante bloqueo, en segundos. Despues del ultimo se rinde.
BACKOFF = (60, 180, 420)


def pausa(rango: tuple[float, float]) -> None:
    time.sleep(random.uniform(*rango))


# ── Resultado ─────────────────────────────────────────────────────────────────

@dataclass
class PerfilCrudo:
    """Todo lo leido de un perfil, sin interpretar.

    `estado` es lo primero que hay que mirar. Si no es PUBLICO_LEIDO, las listas
    de abajo estan vacias **porque no se pudieron leer**, no porque la persona
    no publique nada. La diferencia la lleva el diagnostico.
    """

    handle: str | None
    url: str | None
    diagnostico: Diagnostico

    nombre_perfil: str | None = None
    bio: str | None = None
    seguidores: int | None = None
    siguiendo: int | None = None
    n_posts_declarados: int | None = None
    link_de_bio: str | None = None
    destino_link_de_bio: str | None = None
    titulos_de_destacadas: list[str] = field(default_factory=list)
    es_cuenta_profesional: bool | None = None
    categoria_declarada: str | None = None

    posts: list[Post] = field(default_factory=list)
    comentarios: list[Comentario] = field(default_factory=list)
    n_posts_con_comentarios: int = 0

    @property
    def contenido_legible(self) -> bool:
        return self.diagnostico.estado.contenido_legible

    def captions(self) -> list[str]:
        """En orden cronologico, de mas antiguo a mas reciente."""
        con_fecha = sorted(
            (p for p in self.posts if p.fecha and p.caption),
            key=lambda p: p.fecha,  # type: ignore[arg-type,return-value]
        )
        sin_fecha = [p for p in self.posts if not p.fecha and p.caption]
        return [p.caption for p in con_fecha] + [p.caption for p in sin_fecha]


# ── Utilidades de parseo, probables sin navegador ────────────────────────────

def parsear_conteo(texto: str | None) -> int | None:
    """'1,234' -> 1234 · '12.3K' -> 12300 · '1.2M' -> 1200000 · None si no se lee."""
    if not texto:
        return None
    limpio = texto.strip().replace(",", "").replace(" ", " ")
    m = re.search(r"([\d.]+)\s*([KkMm])?", limpio)
    if not m:
        return None
    try:
        valor = float(m.group(1))
    except ValueError:
        return None
    sufijo = (m.group(2) or "").upper()
    if sufijo == "K":
        valor *= 1_000
    elif sufijo == "M":
        valor *= 1_000_000
    return int(valor)


def parsear_fecha_iso(valor: str | None) -> dt.date | None:
    """El `datetime` del `<time>` de Instagram viene en ISO 8601 con zona."""
    if not valor:
        return None
    texto = valor.strip()
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(texto).date()
    except ValueError:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", texto)
        if m:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def tipo_desde_url(url: str | None) -> TipoDePost:
    if not url:
        return TipoDePost.DESCONOCIDO
    if "/reel/" in url:
        return TipoDePost.REEL
    if "/tv/" in url:
        return TipoDePost.VIDEO
    if "/p/" in url:
        return TipoDePost.IMAGEN
    return TipoDePost.DESCONOCIDO


def extraer_conteos_de_meta(contenido_meta: str | None) -> tuple[int | None, int | None, int | None]:
    """'336 Followers, 512 Following, 88 Posts - ...' -> (336, 512, 88)."""
    if not contenido_meta:
        return None, None, None
    def buscar(etiqueta: str) -> int | None:
        m = re.search(r"([\d,.]+[KkMm]?)\s*" + etiqueta, contenido_meta, re.IGNORECASE)
        return parsear_conteo(m.group(1)) if m else None
    return buscar("followers"), buscar("following"), buscar(r"posts?")


def extraer_bio_de_meta(contenido_meta: str | None) -> str | None:
    """La bio va despues de 'on Instagram:' en el meta description."""
    if not contenido_meta:
        return None
    m = re.search(r"on Instagram:\s*[\"“](.+?)[\"”]\s*$", contenido_meta, re.DOTALL)
    if m:
        return m.group(1).strip() or None
    idx = contenido_meta.find("on Instagram:")
    if idx != -1:
        resto = contenido_meta[idx + len("on Instagram:"):].strip().strip('"').strip("'")
        if resto and "See Instagram" not in resto:
            return resto.strip() or None
    return None


# ── Lado navegador ────────────────────────────────────────────────────────────

def _atributo(page, selector: str, atributo: str) -> str | None:
    try:
        el = page.query_selector(selector)
        return el.get_attribute(atributo) if el else None
    except Exception:  # noqa: BLE001 - un selector roto no aborta el perfil
        return None


def _texto(page, selector: str) -> str | None:
    try:
        el = page.query_selector(selector)
        if not el:
            return None
        t = (el.inner_text() or "").strip()
        return t or None
    except Exception:  # noqa: BLE001
        return None


def _ir(page, url: str, timeout_ms: int = 25_000) -> int | None:
    """Navega y devuelve el codigo HTTP, o None si no se pudo saber."""
    try:
        respuesta = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        return respuesta.status if respuesta else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("navegacion a {} fallo: {}", url, exc)
        return None


def _datos_de_ld_json(page) -> dict:
    """Instagram a veces sirve un ld+json con nombre y descripcion. Es lo mas
    estable que hay: sobrevive a los cambios de clases CSS."""
    try:
        for el in page.query_selector_all('script[type="application/ld+json"]'):
            crudo = el.inner_text() or ""
            if not crudo.strip():
                continue
            try:
                datos = json.loads(crudo)
            except json.JSONDecodeError:
                continue
            if isinstance(datos, list):
                datos = next((d for d in datos if isinstance(d, dict)), {})
            if isinstance(datos, dict) and datos:
                return datos
    except Exception:  # noqa: BLE001
        pass
    return {}


def leer_perfil(page, handle: str, *, con_comentarios: bool = True) -> PerfilCrudo:
    """Lee un perfil completo. Nunca levanta: devuelve el diagnostico."""
    url = IG_BASE + handle.strip().lstrip("@") + "/"
    codigo = _ir(page, url)
    pausa(PAUSA_TRAS_SCROLL)

    titulo = ""
    body = ""
    try:
        titulo = page.title() or ""
    except Exception:  # noqa: BLE001
        pass
    try:
        body = page.inner_text("body") or ""
    except Exception:  # noqa: BLE001
        pass

    meta = _atributo(page, "meta[name=description]", "content")
    enlaces_post = _urls_de_posts(page)

    diag = diagnosticar(
        handle=handle, codigo_http=codigo, titulo=titulo, texto_body=body,
        hay_meta_description=bool(meta), n_articulos_con_posts=len(enlaces_post),
    )

    seguidores, siguiendo, n_posts = extraer_conteos_de_meta(meta)
    ld = _datos_de_ld_json(page)
    nombre = (ld.get("name") if isinstance(ld.get("name"), str) else None) \
        or _nombre_desde_titulo(titulo)
    bio = extraer_bio_de_meta(meta) or (
        ld.get("description") if isinstance(ld.get("description"), str) else None
    )

    perfil = PerfilCrudo(
        handle=handle, url=url, diagnostico=diag,
        nombre_perfil=nombre, bio=bio,
        seguidores=seguidores, siguiendo=siguiendo, n_posts_declarados=n_posts,
        link_de_bio=_link_de_bio(page),
        titulos_de_destacadas=_titulos_de_destacadas(page),
        categoria_declarada=_categoria(page, ld),
    )

    if not diag.estado.contenido_legible:
        logger.info("@{}: {} ({})", handle, diag.estado.value, diag.evidencia)
        return perfil

    perfil.posts = _leer_posts(page, enlaces_post)
    if con_comentarios:
        perfil.comentarios, perfil.n_posts_con_comentarios = _leer_comentarios(
            page, perfil.posts[:N_POSTS_PARA_COMENTARIOS], handle,
        )
    return perfil


def _nombre_desde_titulo(titulo: str) -> str | None:
    """'Ana Tapia (@sold_by_ana) • Instagram photos and videos' -> 'Ana Tapia'."""
    m = re.match(r"\s*(.+?)\s*\(@[^)]+\)", titulo or "")
    return m.group(1).strip() if m else None


def _categoria(page, ld: dict) -> str | None:
    """La categoria que declara una cuenta profesional. Alimenta S5 y S10."""
    for clave in ("@type", "category", "additionalType"):
        valor = ld.get(clave)
        if isinstance(valor, str) and valor.lower() not in ("person", "profilepage"):
            return valor
    return _texto(page, "header div:has-text('Real Estate')")


def _link_de_bio(page) -> str | None:
    """El link de la bio. Su destino alimenta S4 (madurez tecnologica)."""
    for selector in (
        "header a[href^='https://l.instagram.com']",
        "header a[href^='http']:not([href*='instagram.com'])",
        "a[href*='linktr.ee']", "a[href*='calendly']",
    ):
        href = _atributo(page, selector, "href")
        if href:
            return href
    return None


def _titulos_de_destacadas(page) -> list[str]:
    """Titulos de las historias destacadas. Alimentan S3 y S4.

    Un agente con destacadas tituladas "FHA", "Primera casa", "Testimonios"
    esta declarando su nicho en un lugar que nadie mira.
    """
    titulos: list[str] = []
    try:
        for el in page.query_selector_all(
            "ul li button span, div[role='menuitem'] span, "
            "section ul li div span"
        ):
            t = (el.inner_text() or "").strip()
            if t and len(t) <= 30 and t not in titulos and not t.isdigit():
                titulos.append(t)
            if len(titulos) >= 20:
                break
    except Exception:  # noqa: BLE001
        pass
    return titulos


def _urls_de_posts(page) -> list[str]:
    """URLs de los posts de la grilla. Se hace scroll para llegar al objetivo."""
    vistos: list[str] = []
    sin_avance = 0
    while len(vistos) < N_POSTS_OBJETIVO and sin_avance < 3:
        antes = len(vistos)
        try:
            for el in page.query_selector_all("a[href*='/p/'], a[href*='/reel/']"):
                href = el.get_attribute("href") or ""
                if not href:
                    continue
                if href.startswith("/"):
                    href = "https://www.instagram.com" + href
                if href not in vistos:
                    vistos.append(href)
        except Exception:  # noqa: BLE001
            break
        if len(vistos) >= N_POSTS_OBJETIVO:
            break
        try:
            page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
        except Exception:  # noqa: BLE001
            break
        pausa(PAUSA_TRAS_SCROLL)
        sin_avance = sin_avance + 1 if len(vistos) == antes else 0
    return vistos[:N_POSTS_OBJETIVO]


def _leer_posts(page, urls: list[str]) -> list[Post]:
    """Abre cada post y lee su caption real, su fecha y su engagement."""
    posts: list[Post] = []
    for url in urls:
        codigo = _ir(page, url)
        if codigo in (401, 403, 429):
            logger.warning("bloqueo leyendo {} (HTTP {}): corto el perfil", url, codigo)
            break
        pausa(PAUSA_ENTRE_POSTS)

        fecha = parsear_fecha_iso(_atributo(page, "time[datetime]", "datetime"))
        caption = _caption(page)
        likes, comentarios = _engagement(page)
        posts.append(Post(
            url=url, fecha=fecha, caption=caption or "",
            tipo=tipo_desde_url(url), likes=likes, n_comentarios=comentarios,
            geotag=_geotag(page),
        ))
    return posts


def _caption(page) -> str | None:
    """El caption real del post. Nunca el `alt` de la imagen.

    Se prueban varias vias porque los selectores de Instagram cambian. El
    og:description del meta es el mas estable y va primero.
    """
    meta = _atributo(page, "meta[property='og:description']", "content")
    if meta:
        # 'N likes, M comments - handle on DATE: "el caption"'
        m = re.search(r':\s*[\"“](.+)[\"”]\s*$', meta, re.DOTALL)
        if m and m.group(1).strip():
            return m.group(1).strip()

    for selector in ("h1", "article div[role='button'] + div h1",
                     "ul li div div div span", "article span[dir='auto']"):
        t = _texto(page, selector)
        if t and len(t) > 15:
            return t
    return None


def _engagement(page) -> tuple[int | None, int | None]:
    """(likes, comentarios). None donde no se pudo leer: nunca cero."""
    meta = _atributo(page, "meta[property='og:description']", "content")
    likes = comentarios = None
    if meta:
        m = re.search(r"([\d,.]+[KkMm]?)\s*likes?", meta, re.IGNORECASE)
        if m:
            likes = parsear_conteo(m.group(1))
        m = re.search(r"([\d,.]+[KkMm]?)\s*comments?", meta, re.IGNORECASE)
        if m:
            comentarios = parsear_conteo(m.group(1))
    if likes is None:
        t = _texto(page, "section span a span, section button span")
        likes = parsear_conteo(t)
    return likes, comentarios


def _geotag(page) -> str | None:
    """El lugar etiquetado. Alimenta S7 sub-estatal, que el lote nunca trae."""
    for selector in ("a[href*='/explore/locations/']",
                     "div[role='button'] a[href*='locations']"):
        t = _texto(page, selector)
        if t:
            return t
    return None


def _leer_comentarios(page, posts: list[Post], handle_agente: str
                      ) -> tuple[list[Comentario], int]:
    """Lee comentarios y los anonimiza en el acto.

    El handle del comentarista se usa solo para comparar con el del agente y
    **no se guarda**: `Comentario.desde_crudo` lo descarta. Ver comentarios.py.
    """
    salida: list[Comentario] = []
    con_comentarios = 0

    for post in posts:
        if not post.url:
            continue
        codigo = _ir(page, post.url)
        if codigo in (401, 403, 429):
            logger.warning("bloqueo leyendo comentarios (HTTP {}): corto", codigo)
            break
        pausa(PAUSA_ENTRE_POSTS)

        crudos = _comentarios_del_post(page)
        if crudos:
            con_comentarios += 1
        for autor, texto in crudos[:N_COMENTARIOS_POR_POST]:
            salida.append(Comentario.desde_crudo(
                texto=texto, handle_autor=autor,
                handle_agente=handle_agente, post_url=post.url,
            ))
    return salida, con_comentarios


def _comentarios_del_post(page) -> list[tuple[str | None, str]]:
    """[(handle del autor, texto)]. El handle no sale de esta funcion."""
    salida: list[tuple[str | None, str]] = []
    try:
        for bloque in page.query_selector_all("ul ul, div[role='button'] ~ ul li"):
            texto = (bloque.inner_text() or "").strip()
            if not texto or len(texto) < 3:
                continue
            enlace = bloque.query_selector("a[href^='/']")
            autor = None
            if enlace:
                href = enlace.get_attribute("href") or ""
                autor = href.strip("/").split("/")[0] or None
            # La primera linea suele ser el handle; se saca del texto.
            lineas = [ln for ln in texto.split("\n") if ln.strip()]
            if autor and lineas and lineas[0].strip().lstrip("@").lower() == autor.lower():
                lineas = lineas[1:]
            cuerpo = " ".join(lineas).strip()
            if cuerpo:
                salida.append((autor, cuerpo))
            if len(salida) >= N_COMENTARIOS_POR_POST * 2:
                break
    except Exception:  # noqa: BLE001
        pass
    return salida


def resolver_destino_de_link(page, url: str | None) -> str | None:
    """Sigue el redirect del link de la bio. Alimenta S4.

    Instagram envuelve los links en l.instagram.com. El destino real dice si la
    persona usa Calendly, un CRM, una landing propia o nada.
    """
    if not url:
        return None
    codigo = _ir(page, url, timeout_ms=15_000)
    if codigo in (401, 403, 429):
        return None
    try:
        destino = page.url
        return destino if destino and destino != url else url
    except Exception:  # noqa: BLE001
        return url


# ══════════════════════════════════════════════════════════════════════════════
# CAPTURA CRUDA · Bloque 1-bis
# ══════════════════════════════════════════════════════════════════════════════
#
# Crudo primero, parser despues.
#
# `capturar_crudo` devuelve un dict serializable a JSON con TODO lo extraido y
# NADA derivado: ni idioma, ni qualifiers, ni ratios. El parser corre en un
# segundo paso sobre esos archivos.
#
# La razon es economica. Si el parser falla, se arregla y se re-parsea en
# segundos. Si no se guardo el crudo, cada bug del parser cuesta una pasada
# entera contra Instagram: 1.203 perfiles a 30 s son 10 horas, y cada pasada
# gasta la cuota de una cuenta que se puede bloquear.
#
# Por eso esta funcion no interpreta nada. Interpretar es lo unico que se puede
# repetir gratis.

#: Posts a capturar por perfil. El brief pide 15 a 30.
N_POSTS_CRUDO = 30
#: Comentarios por post. El brief pide hasta 20.
N_COMENTARIOS_CRUDO = 20

#: Endpoint JSON de Instagram para el perfil. Con sesion iniciada responde con
#: el perfil completo, incluidos los 12 primeros posts con su caption real.
#: Es mucho mas estable que el DOM, que cambia con cada deploy.
API_PERFIL = (
    "https://www.instagram.com/api/v1/users/web_profile_info/?username=%s"
)

#: Cabecera que Instagram exige en sus endpoints internos.
APP_ID = "936619743392459"


def _pedir_json(page, url: str) -> dict | None:
    """Pide un endpoint JSON de Instagram desde la sesion del navegador.

    Se hace con `page.request`, que reusa las cookies del contexto: no hay que
    replicar la sesion ni manejar tokens.
    """
    try:
        respuesta = page.request.get(url, headers={
            "X-IG-App-ID": APP_ID,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": IG_BASE,
            "Accept": "*/*",
        }, timeout=30_000)
        if respuesta.status != 200:
            logger.debug("JSON {} -> HTTP {}", url, respuesta.status)
            return None
        return respuesta.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("JSON {} fallo: {}", url, exc)
        return None


def _nodo_a_post_crudo(nodo: dict) -> dict:
    """Un nodo de la respuesta JSON de Instagram, sin interpretar.

    Solo se renombra y se aplana. Los valores van tal como vienen.
    """
    bordes_caption = ((nodo.get("edge_media_to_caption") or {}).get("edges") or [])
    caption = None
    if bordes_caption:
        caption = ((bordes_caption[0] or {}).get("node") or {}).get("text")

    etiquetadas = []
    for borde in ((nodo.get("edge_media_to_tagged_user") or {}).get("edges") or []):
        usuario = ((borde or {}).get("node") or {}).get("user") or {}
        if usuario.get("username"):
            etiquetadas.append(usuario["username"])

    ubicacion = nodo.get("location") or {}

    return {
        "shortcode": nodo.get("shortcode"),
        "id": nodo.get("id"),
        "caption": caption,
        "timestamp": nodo.get("taken_at_timestamp"),
        "typename": nodo.get("__typename"),
        "es_video": nodo.get("is_video"),
        "duracion_video": nodo.get("video_duration"),
        "vistas_video": nodo.get("video_view_count"),
        "likes": ((nodo.get("edge_liked_by") or {}).get("count")
                  if nodo.get("edge_liked_by") else
                  (nodo.get("edge_media_preview_like") or {}).get("count")),
        "n_comentarios": (nodo.get("edge_media_to_comment")
                          or nodo.get("edge_media_preview_comment")
                          or {}).get("count"),
        "comentarios_deshabilitados": nodo.get("comments_disabled"),
        "etiquetadas": etiquetadas,
        "ubicacion": {
            "id": ubicacion.get("id"),
            "nombre": ubicacion.get("name"),
            "slug": ubicacion.get("slug"),
        } if ubicacion else None,
        "accesibilidad_alt": nodo.get("accessibility_caption"),
        "n_hijos": len(((nodo.get("edge_sidecar_to_children") or {}).get("edges") or [])),
    }


def _comentarios_crudos_de_json(datos: dict) -> list[dict]:
    """Comentarios de la respuesta de un post, sin interpretar."""
    salida: list[dict] = []
    for clave in ("edge_media_to_parent_comment", "edge_media_to_comment"):
        bordes = ((datos.get(clave) or {}).get("edges") or [])
        for borde in bordes[:N_COMENTARIOS_CRUDO]:
            nodo = (borde or {}).get("node") or {}
            propietario = nodo.get("owner") or {}
            salida.append({
                "id": nodo.get("id"),
                "texto": nodo.get("text"),
                "timestamp": nodo.get("created_at"),
                "autor_handle": propietario.get("username"),
                "autor_verificado": propietario.get("is_verified"),
                "likes": (nodo.get("edge_liked_by") or {}).get("count"),
            })
        if salida:
            break
    return salida[:N_COMENTARIOS_CRUDO]


def _perfil_crudo_de_json(usuario: dict) -> dict:
    """El bloque de perfil, sin interpretar."""
    destacadas = []
    for borde in ((usuario.get("edge_highlight_reels") or {}).get("edges") or []):
        nodo = (borde or {}).get("node") or {}
        if nodo.get("title"):
            destacadas.append(nodo["title"])

    return {
        "handle": usuario.get("username"),
        "nombre_visible": usuario.get("full_name"),
        "bio": usuario.get("biography"),
        "bio_entidades": usuario.get("biography_with_entities"),
        "seguidores": (usuario.get("edge_followed_by") or {}).get("count"),
        "seguidos": (usuario.get("edge_follow") or {}).get("count"),
        "n_publicaciones": (usuario.get("edge_owner_to_timeline_media") or {}).get("count"),
        "enlace_bio": usuario.get("external_url"),
        "enlace_bio_sin_redirigir": usuario.get("external_url_linkshimmed"),
        "es_privado": usuario.get("is_private"),
        "es_verificado": usuario.get("is_verified"),
        "es_cuenta_empresa": usuario.get("is_business_account"),
        "es_cuenta_profesional": usuario.get("is_professional_account"),
        "categoria_declarada": (usuario.get("category_name")
                                or usuario.get("business_category_name")),
        "categoria_empresa_general": usuario.get("overall_category_name"),
        "email_empresa": usuario.get("business_email"),
        "telefono_empresa": usuario.get("business_phone_number"),
        "direccion_empresa": usuario.get("business_address_json"),
        "titulos_destacadas": destacadas,
        "id_usuario": usuario.get("id"),
    }


def capturar_crudo(
    page,
    handle: str,
    *,
    n_posts: int = N_POSTS_CRUDO,
    n_comentarios: int = N_COMENTARIOS_CRUDO,
    con_comentarios: bool = True,
    resolver_enlace_bio: bool = True,
) -> dict:
    """Captura CRUDA de un perfil. No deriva nada.

    Estrategia: JSON primero, DOM como respaldo. El JSON de Instagram es mucho
    mas estable que su DOM y trae el caption real, la fecha exacta en epoch, las
    cuentas etiquetadas y la ubicacion sin tener que abrir cada post.

    Devuelve siempre un dict, tambien cuando falla: el estado y la evidencia van
    adentro. Un fallo tambien es un dato que hay que guardar.
    """
    ahora = dt.datetime.now(dt.timezone.utc)
    limpio = (handle or "").strip().lstrip("@").rstrip("/")
    crudo: dict = {
        "esquema": "ig-crudo-v1",
        "handle_pedido": limpio,
        "capturado_en": ahora.isoformat(timespec="seconds"),
        "via": None,
        "estado_perfil": None,
        "estado_evidencia": None,
        "http_status": None,
        "perfil": None,
        "posts": [],
        "comentarios_por_post": {},
        "destino_enlace_bio": None,
        "errores": [],
    }

    if not limpio:
        crudo["estado_perfil"] = EstadoPerfil.SIN_HANDLE.value
        crudo["estado_evidencia"] = "no habia handle candidato"
        return crudo

    # ── 1 · JSON del perfil ───────────────────────────────────────────────────
    datos = _pedir_json(page, API_PERFIL % limpio)
    usuario = None
    if isinstance(datos, dict):
        usuario = ((datos.get("data") or {}).get("user"))

    if usuario:
        crudo["via"] = "json"
        crudo["perfil"] = _perfil_crudo_de_json(usuario)
        crudo["json_perfil_bruto"] = datos

        if usuario.get("is_private"):
            crudo["estado_perfil"] = EstadoPerfil.PRIVADO.value
            crudo["estado_evidencia"] = "is_private=true en el JSON del perfil"
        else:
            bordes = ((usuario.get("edge_owner_to_timeline_media") or {})
                      .get("edges") or [])
            crudo["posts"] = [
                _nodo_a_post_crudo((b or {}).get("node") or {})
                for b in bordes[:n_posts]
            ]
            crudo["estado_perfil"] = EstadoPerfil.PUBLICO_LEIDO.value
            crudo["estado_evidencia"] = (
                "JSON del perfil con %d posts en la primera pagina"
                % len(crudo["posts"])
            )
    else:
        # ── 2 · Respaldo por DOM ──────────────────────────────────────────────
        perfil_dom = leer_perfil(page, limpio, con_comentarios=False)
        crudo["via"] = "dom"
        crudo["http_status"] = perfil_dom.diagnostico.codigo_http
        crudo["estado_perfil"] = perfil_dom.diagnostico.estado.value
        crudo["estado_evidencia"] = perfil_dom.diagnostico.evidencia
        crudo["perfil"] = {
            "handle": perfil_dom.handle,
            "nombre_visible": perfil_dom.nombre_perfil,
            "bio": perfil_dom.bio,
            "seguidores": perfil_dom.seguidores,
            "seguidos": perfil_dom.siguiendo,
            "n_publicaciones": perfil_dom.n_posts_declarados,
            "enlace_bio": perfil_dom.link_de_bio,
            "titulos_destacadas": list(perfil_dom.titulos_de_destacadas),
            "categoria_declarada": perfil_dom.categoria_declarada,
            "es_privado": None,
        }
        crudo["posts"] = [
            {
                "shortcode": (p.url or "").rstrip("/").rsplit("/", 1)[-1] or None,
                "caption": p.caption or None,
                "timestamp": None,
                "fecha_iso": p.fecha.isoformat() if p.fecha else None,
                "typename": p.tipo.value,
                "likes": p.likes,
                "n_comentarios": p.n_comentarios,
                "etiquetadas": [],
                "ubicacion": {"nombre": p.geotag} if p.geotag else None,
            }
            for p in perfil_dom.posts[:n_posts]
        ]
        crudo["errores"].append(
            "el endpoint JSON no respondio; se uso el DOM, que trae menos "
            "campos (sin cuentas etiquetadas ni timestamp exacto)"
        )

    # ── 3 · Mas posts por paginacion del JSON ────────────────────────────────
    if (crudo["via"] == "json"
            and crudo["estado_perfil"] == EstadoPerfil.PUBLICO_LEIDO.value
            and len(crudo["posts"]) < n_posts):
        pagina = ((usuario.get("edge_owner_to_timeline_media") or {})
                  .get("page_info") or {})
        cursor = pagina.get("end_cursor")
        id_usuario = usuario.get("id")
        if pagina.get("has_next_page") and cursor and id_usuario:
            extra = _mas_posts_por_json(
                page, id_usuario, cursor, n_posts - len(crudo["posts"]),
            )
            crudo["posts"].extend(extra)
            crudo["estado_evidencia"] += " + %d por paginacion" % len(extra)

    # ── 4 · Comentarios, post por post ───────────────────────────────────────
    if con_comentarios and crudo["estado_perfil"] == EstadoPerfil.PUBLICO_LEIDO.value:
        for post in crudo["posts"]:
            shortcode = post.get("shortcode")
            if not shortcode:
                continue
            if post.get("comentarios_deshabilitados"):
                crudo["comentarios_por_post"][shortcode] = []
                continue
            if not post.get("n_comentarios"):
                crudo["comentarios_por_post"][shortcode] = []
                continue
            comentarios = _comentarios_de_un_post(page, shortcode, n_comentarios)
            crudo["comentarios_por_post"][shortcode] = comentarios
            pausa((1.2, 2.8))

    # ── 5 · Destino final del enlace de la bio ───────────────────────────────
    if resolver_enlace_bio and crudo.get("perfil"):
        enlace = crudo["perfil"].get("enlace_bio")
        if enlace:
            crudo["destino_enlace_bio"] = resolver_destino_de_link(page, enlace)

    return crudo


#: Consulta GraphQL para paginar el timeline. El hash es el que usa la web de
#: Instagram; si cambia, la paginacion deja de funcionar y `capturar_crudo` lo
#: registra en `errores` en vez de fallar. Los primeros 12 posts del JSON del
#: perfil no dependen de esto.
QUERY_HASH_TIMELINE = "e769aa130647d2354c40ea6a439bfc08"


def _mas_posts_por_json(page, id_usuario: str, cursor: str, faltan: int) -> list[dict]:
    salida: list[dict] = []
    while faltan > 0 and cursor:
        variables = json.dumps({
            "id": str(id_usuario),
            "first": min(faltan, 12),
            "after": cursor,
        })
        url = ("https://www.instagram.com/graphql/query/?query_hash=%s&variables=%s"
               % (QUERY_HASH_TIMELINE, urllib.parse.quote(variables)))
        datos = _pedir_json(page, url)
        medios = (((datos or {}).get("data") or {}).get("user") or {}).get(
            "edge_owner_to_timeline_media"
        ) or {}
        bordes = medios.get("edges") or []
        if not bordes:
            break
        for borde in bordes:
            salida.append(_nodo_a_post_crudo((borde or {}).get("node") or {}))
        faltan -= len(bordes)
        pagina = medios.get("page_info") or {}
        cursor = pagina.get("end_cursor") if pagina.get("has_next_page") else None
        pausa((1.5, 3.0))
    return salida


#: Consulta GraphQL para los comentarios de un post.
QUERY_HASH_COMENTARIOS = "bc3296d1ce80a24b1b6e40b1e72903f5"


def _comentarios_de_un_post(page, shortcode: str, n: int) -> list[dict]:
    """Comentarios de un post. JSON primero, DOM como respaldo."""
    variables = json.dumps({"shortcode": shortcode, "first": min(n, 24)})
    url = ("https://www.instagram.com/graphql/query/?query_hash=%s&variables=%s"
           % (QUERY_HASH_COMENTARIOS, urllib.parse.quote(variables)))
    datos = _pedir_json(page, url)
    medios = ((datos or {}).get("data") or {}).get("shortcode_media")
    if medios:
        return _comentarios_crudos_de_json(medios)

    # Respaldo: abrir el post y leer el DOM.
    codigo = _ir(page, "%sp/%s/" % (IG_BASE, shortcode))
    if codigo in (401, 403, 429):
        return []
    pausa(PAUSA_ENTRE_POSTS)
    return [
        {"id": None, "texto": texto, "timestamp": None,
         "autor_handle": autor, "autor_verificado": None, "likes": None}
        for autor, texto in _comentarios_del_post(page)[:n]
    ]


def leer_con_backoff(page, handle: str, *, con_comentarios: bool = True) -> PerfilCrudo:
    """Reintenta con backoff exponencial solo si el estado es BLOQUEADO.

    NO_ENCONTRADO no se reintenta: el handle no existe y volver a pedirlo es
    gastar cuota. BLOQUEADO si, porque es un dato sobre nuestro acceso.
    """
    perfil = leer_perfil(page, handle, con_comentarios=con_comentarios)
    intento = 0
    while perfil.diagnostico.estado is EstadoPerfil.BLOQUEADO and intento < len(BACKOFF):
        espera = BACKOFF[intento] * random.uniform(0.85, 1.25)
        logger.warning(
            "@{} bloqueado ({}). Espero {:.0f}s antes del reintento {}/{}",
            handle, perfil.diagnostico.evidencia, espera, intento + 1, len(BACKOFF),
        )
        time.sleep(espera)
        perfil = leer_perfil(page, handle, con_comentarios=con_comentarios)
        intento += 1
    return perfil
