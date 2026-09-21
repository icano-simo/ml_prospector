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


def extraer_nombre_de_meta(contenido_meta: str | None) -> str | None:
    """El nombre visible sale del meta description, no del <title>.

    `1,351 Followers, 1,247 Following, 23 Posts - Javier Hernandez
     (@javierhernandezrealtor) on Instagram: "..."`  ->  `Javier Hernandez`

    El <title> no sirve: en `domcontentloaded` todavia dice solo "Instagram" y
    recien se completa cuando hidrata. Medido: `nombre_visible` salia None en
    todos los perfiles, y eso debilita la verificacion de handle -- que es
    justamente lo que compara el nombre del perfil con el del libro.
    """
    if not contenido_meta:
        return None
    m = re.search(r"-\s*(.+?)\s*\(@[A-Za-z0-9_.]+\)\s*on Instagram", contenido_meta)
    if m:
        nombre = m.group(1).strip()
        return nombre or None
    return None


#: Categorias que Instagram muestra en una cuenta profesional. Se busca la
#: linea exacta dentro del bloque del header, que trae mucho mas que eso.
_CATEGORIAS_CONOCIDAS = (
    "Real Estate Agent", "Real Estate", "Real Estate Service",
    "Entrepreneur", "Public Figure", "Digital Creator", "Personal Blog",
    "Local Service", "Financial Service", "Mortgage Brokers",
    "Agente inmobiliario", "Bienes raices", "Empresario",
    "Figura publica", "Creador digital", "Blog personal",
)


def extraer_categoria(texto_header: str | None) -> str | None:
    """La categoria declarada, de una linea del header.

    El selector del header devuelve el bloque entero -- nombre, conteos, bio y
    enlace, todo junto. Sin este filtro, `categoria_declarada` quedaba con
    doscientos caracteres de texto pegado.
    """
    if not texto_header:
        return None
    lineas = [ln.strip() for ln in str(texto_header).splitlines() if ln.strip()]
    for linea in lineas:
        if len(linea) > 40:
            continue
        for categoria in _CATEGORIAS_CONOCIDAS:
            if linea.lower() == categoria.lower():
                return linea
    return None


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


# ══════════════════════════════════════════════════════════════════════════════
# DOM CON SESION · la via que si funciona
# ══════════════════════════════════════════════════════════════════════════════
#
# Medido el 2026-09-21 con sesion iniciada: el endpoint interno
# /api/v1/users/web_profile_info/ devuelve **HTTP 429** de forma sostenida para
# una cuenta nueva, incluso tras esperar y calentar la sesion. El cuerpo del 429
# es la pagina HTML con `class="logged-in"`, asi que la sesion esta bien: lo que
# esta limitado es el endpoint.
#
# Pero el DOM con sesion **si** da lo que hace falta, y esto tambien es medido
# sobre @javierhernandezrealtor:
#
#   meta[name=description]        seguidores, seguidos, n_posts, nombre, BIO
#   og:description del post       caption completo, likes, n_comentarios, AUTOR
#   time[datetime]                fecha exacta (2023-05-20T14:55:22.000Z)
#   el propio caption             @menciones
#   la pagina del post            geotag ("Chicago, Illinois")
#   ancla en los botones "Reply"  los comentarios con su autor
#
# Lo unico que no se alcanza son las cuentas etiquetadas EN LA FOTO, que
# requieren un clic sobre la imagen. Las @menciones del caption si, y son la via
# principal de S6.

#: Marcador de tiempo relativo que Instagram pone en cada comentario: "45w",
#: "3d", "17h", "2m". Sirve para reconocer un bloque de comentario.
_RE_HACE = re.compile(r"\b\d+\s*[smhdw]\b", re.IGNORECASE)

#: Texto del boton que tiene TODO comentario. Es el ancla, y se usa por texto
#: visible y no por clase CSS: las clases de Instagram son ofuscadas y cambian
#: en cada deploy; "Reply" y "Responder" no.
_TEXTOS_RESPONDER = ("reply", "responder")

#: Enlace que es un perfil y nada mas: /usuario/
_RE_ENLACE_PERFIL = re.compile(r"^/([A-Za-z0-9_.]{2,30})/$")


def _autor_de_og(og: str) -> str | None:
    """`154 likes, 29 comments - javierhernandezrealtor on May 20, 2023: "..."`

    El autor es lo que permite descartar los posts que NO son del realtor. La
    grilla del perfil trae enlaces a posts de otras cuentas -- medido: 2 de 23
    en un perfil -- y sin esta comprobacion esos captions entrarian como si
    fueran suyos.
    """
    if not og:
        return None
    m = re.search(r"-\s*([A-Za-z0-9_.]{2,30})\s+on\s+\w+\s+\d{1,2},\s*\d{4}", og)
    return m.group(1).lower() if m else None


def _caption_de_og(og: str) -> str | None:
    """El caption va despues de `: "` y hasta el final."""
    if not og:
        return None
    m = re.search(r':\s*["“](.*)["”]\s*$', og, re.DOTALL)
    if m:
        return m.group(1).strip() or None
    idx = og.find(': "')
    if idx != -1:
        return og[idx + 3:].rstrip('"”').strip() or None
    return None


def _urls_de_posts_propios(page, handle: str, n_posts: int
                           ) -> tuple[list[str], bool]:
    """URLs de los posts DEL PERFIL, con scroll. Devuelve (urls, fin_del_grid).

    Filtra por prefijo de ruta: un post propio es `/p/CODIGO/` o
    `/handle/...`. Los `/otracuenta/reel/...` que Instagram mete al costado
    quedan fuera.
    """
    esperado = handle.strip().lstrip("@").lower()
    vistos: list[str] = []
    ajenos = 0
    sin_avance = 0

    while len(vistos) < n_posts and sin_avance < 3:
        antes = len(vistos)
        try:
            enlaces = page.query_selector_all("a[href*='/p/'], a[href*='/reel/']")
        except Exception:  # noqa: BLE001
            break
        for a in enlaces:
            href = a.get_attribute("href") or ""
            if not href:
                continue
            ruta = href if href.startswith("/") else re.sub(
                r"^https?://[^/]+", "", href
            )
            propio = (
                ruta.startswith("/p/")
                or ruta.startswith("/reel/")
                or ruta.startswith("/%s/" % esperado)
            )
            if not propio:
                ajenos += 1
                continue
            completo = "https://www.instagram.com" + ruta
            if completo not in vistos:
                vistos.append(completo)

        if len(vistos) >= n_posts:
            break
        try:
            page.evaluate("window.scrollBy(0, window.innerHeight * 1.6)")
        except Exception:  # noqa: BLE001
            break
        pausa(PAUSA_TRAS_SCROLL)
        sin_avance = sin_avance + 1 if len(vistos) == antes else 0

    # Si el scroll dejo de traer posts nuevos tres veces, se agoto la grilla.
    fin_del_grid = sin_avance >= 3 and len(vistos) < n_posts
    if ajenos:
        logger.debug("@{}: {} enlaces a posts de otras cuentas descartados",
                     esperado, ajenos)
    return vistos[:n_posts], fin_del_grid


def _comentarios_dom(page, handle_agente: str, n: int) -> list[dict]:
    """Comentarios del post, anclados en los botones "Reply"/"Responder".

    Cada comentario de Instagram tiene ese boton. Se sube desde ahi hasta el
    bloque que contiene el handle del autor y su texto, que es la unica forma
    estable de identificarlo sin depender de clases ofuscadas.
    """
    try:
        crudos = page.evaluate(
            """(textos) => {
              const esResponder = (e) => {
                const t = (e.innerText || '').trim().toLowerCase();
                return textos.includes(t);
              };
              const anclas = Array.from(
                document.querySelectorAll("div[role='button'],button,span")
              ).filter(esResponder);

              const salida = [];
              const vistos = new Set();
              for (const a of anclas) {
                let n = a, bloque = null;
                for (let i = 0; i < 6 && n; i++) {
                  n = n.parentElement;
                  if (!n) break;
                  const enlaces = Array.from(n.querySelectorAll("a[href^='/']"))
                    .map(x => x.getAttribute('href') || '')
                    .filter(h => /^\\/[A-Za-z0-9_.]{2,30}\\/$/.test(h));
                  const t = (n.innerText || '').replace(/\\s+/g, ' ').trim();
                  if (enlaces.length && t.length > 12) {
                    bloque = {handle: enlaces[0], texto: t};
                    break;
                  }
                }
                if (!bloque) continue;
                const clave = bloque.handle + '|' + bloque.texto.slice(0, 60);
                if (vistos.has(clave)) continue;
                vistos.add(clave);
                salida.push(bloque);
              }
              return salida;
            }""",
            list(_TEXTOS_RESPONDER),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("no se pudieron leer comentarios por DOM: {}", exc)
        return []

    salida: list[dict] = []
    for bruto in crudos:
        autor = (bruto.get("handle") or "").strip("/").lower()
        texto = bruto.get("texto") or ""
        # El bloque viene como "autor 45w el texto 1 like Reply ...". Se quita
        # el handle del principio, el marcador de tiempo y la cola de botones.
        limpio = texto
        if autor and limpio.lower().startswith(autor):
            limpio = limpio[len(autor):]
        limpio = _RE_HACE.sub(" ", limpio, count=1)
        limpio = re.sub(
            r"\b\d+\s*(?:likes?|me gusta)\b", " ", limpio, flags=re.IGNORECASE
        )
        for cola in ("View all", "Ver todas", "Ver las", "Reply", "Responder",
                     "Hide replies", "Ocultar"):
            idx = limpio.find(cola)
            if idx > 0:
                limpio = limpio[:idx]
        limpio = re.sub(r"\s+", " ", limpio).strip(" ·-–—")
        if not limpio:
            continue
        salida.append({
            "id": None,
            "texto": limpio,
            "timestamp": None,
            "autor_handle": autor or None,
            "autor_verificado": None,
            "likes": None,
        })
        if len(salida) >= n:
            break
    return salida


def _leer_post_dom(page, url: str, handle_esperado: str) -> dict | None:
    """Un post por DOM con sesion. None si no es del perfil esperado."""
    codigo = _ir(page, url)
    if codigo in (401, 403, 429):
        logger.warning("bloqueo leyendo {} (HTTP {}): corto", url, codigo)
        return {"__bloqueado__": True, "http": codigo}
    pausa(PAUSA_ENTRE_POSTS)

    og = _atributo(page, "meta[property='og:description']", "content") or ""
    autor = _autor_de_og(og)
    esperado = handle_esperado.strip().lstrip("@").lower()

    if autor and autor != esperado:
        # La grilla trae posts de otras cuentas. Este es el filtro que evita
        # meter el caption de otra persona en la fila de nuestro realtor.
        logger.debug("descarto {}: el autor es @{} y no @{}", url, autor, esperado)
        return None

    fecha_iso = _atributo(page, "time[datetime]", "datetime")
    likes = comentarios = None
    m = re.search(r"([\d,.]+[KkMm]?)\s*likes?", og, re.IGNORECASE)
    if m:
        likes = parsear_conteo(m.group(1))
    m = re.search(r"([\d,.]+[KkMm]?)\s*comments?", og, re.IGNORECASE)
    if m:
        comentarios = parsear_conteo(m.group(1))

    return {
        "shortcode": url.rstrip("/").rsplit("/", 1)[-1] or None,
        "id": None,
        "caption": _caption_de_og(og),
        "timestamp": None,
        "fecha_iso": fecha_iso,
        "typename": "GraphVideo" if "/reel/" in url else "GraphImage",
        "es_video": "/reel/" in url,
        "likes": likes,
        "n_comentarios": comentarios,
        "comentarios_deshabilitados": None,
        "etiquetadas": [],
        "ubicacion": {"nombre": _geotag(page)} if _geotag(page) else None,
        "accesibilidad_alt": None,
        "n_hijos": 0,
        "autor_confirmado": autor,
        "og_description": og,
    }


def capturar_por_dom_con_sesion(
    page,
    handle: str,
    *,
    n_posts: int = N_POSTS_CRUDO,
    n_comentarios: int = N_COMENTARIOS_CRUDO,
    con_comentarios: bool = True,
) -> dict:
    """Captura cruda por DOM, con sesion iniciada. La via que funciona hoy.

    Cuesta una navegacion por post -- mas otra si se leen comentarios -- asi que
    es mucho mas lenta que el JSON. Pero da caption real, fecha exacta, likes,
    conteo de comentarios, autor verificado, @menciones, geotag y comentarios.
    """
    limpio = handle.strip().lstrip("@").rstrip("/")
    crudo: dict = {
        "esquema": "ig-crudo-v1",
        "handle_pedido": limpio,
        "capturado_en": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "via": "dom_con_sesion",
        "estado_perfil": None,
        "estado_evidencia": None,
        "http_status": None,
        "perfil": None,
        "posts": [],
        "comentarios_por_post": {},
        "destino_enlace_bio": None,
        "errores": [],
        "posts_solicitados": n_posts,
        "posts_recuperados": 0,
        "fin_de_paginacion": None,
        "paginacion_truncada": None,
        "motivo_truncamiento": None,
        "posts_ajenos_descartados": 0,
    }

    url_perfil = IG_BASE + limpio + "/"
    codigo = _ir(page, url_perfil)
    crudo["http_status"] = codigo
    pausa(PAUSA_TRAS_SCROLL)

    titulo = ""
    cuerpo = ""
    try:
        titulo = page.title() or ""
    except Exception:  # noqa: BLE001
        pass
    try:
        cuerpo = page.inner_text("body") or ""
    except Exception:  # noqa: BLE001
        pass

    meta = _atributo(page, "meta[name=description]", "content")
    seguidores, siguiendo, n_declarados = extraer_conteos_de_meta(meta)

    diag = diagnosticar(
        handle=limpio, codigo_http=codigo, titulo=titulo, texto_body=cuerpo,
        hay_meta_description=bool(meta),
        n_articulos_con_posts=len(
            page.query_selector_all("a[href*='/p/'], a[href*='/reel/']")
            if codigo not in (401, 403, 429, 404) else []
        ),
    )
    crudo["estado_perfil"] = diag.estado.value
    crudo["estado_evidencia"] = diag.evidencia

    crudo["perfil"] = {
        "handle": limpio,
        # El nombre sale del meta, no del <title>: en domcontentloaded el
        # titulo todavia dice solo "Instagram".
        "nombre_visible": (extraer_nombre_de_meta(meta)
                           or _nombre_desde_titulo(titulo)),
        "bio": extraer_bio_de_meta(meta),
        "seguidores": seguidores,
        "seguidos": siguiendo,
        "n_publicaciones": n_declarados,
        "enlace_bio": _link_de_bio(page),
        "es_privado": diag.estado is EstadoPerfil.PRIVADO,
        "es_cuenta_empresa": None,
        "categoria_declarada": extraer_categoria(_texto(page, "header section")
                                                 or _texto(page, "header")),
        "titulos_destacadas": _titulos_de_destacadas(page),
    }

    if diag.estado is not EstadoPerfil.PUBLICO_LEIDO:
        _evaluar_truncamiento(crudo, n_posts)
        return crudo

    urls, fin_del_grid = _urls_de_posts_propios(page, limpio, n_posts)
    crudo["fin_de_paginacion"] = fin_del_grid

    for url in urls:
        post = _leer_post_dom(page, url, limpio)
        if post is None:
            crudo["posts_ajenos_descartados"] += 1
            continue
        if post.get("__bloqueado__"):
            crudo["estado_perfil"] = EstadoPerfil.BLOQUEADO.value
            crudo["estado_evidencia"] = (
                "HTTP %s leyendo un post: se corta el perfil" % post.get("http")
            )
            crudo["errores"].append(
                "bloqueo a mitad del perfil: los posts leidos hasta aca quedan, "
                "pero la muestra esta incompleta"
            )
            break
        crudo["posts"].append(post)

        if con_comentarios and (post.get("n_comentarios") or 0) > 0:
            shortcode = post.get("shortcode")
            if shortcode:
                crudo["comentarios_por_post"][shortcode] = _comentarios_dom(
                    page, limpio, n_comentarios,
                )
        pausa(PAUSA_ENTRE_POSTS)

    _evaluar_truncamiento(crudo, n_posts)
    return crudo


def capturar_crudo(
    page,
    handle: str,
    *,
    n_posts: int = N_POSTS_CRUDO,
    n_comentarios: int = N_COMENTARIOS_CRUDO,
    con_comentarios: bool = True,
    resolver_enlace_bio: bool = True,
    forzar_dom: bool = False,
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
        # ── Contabilidad de la paginacion ────────────────────────────────────
        #
        # Estos cuatro campos son HECHOS de la captura, no derivaciones, y por
        # eso viven en el crudo. El parser los usa para decidir si el ratio de
        # idioma se puede reportar.
        "posts_solicitados": n_posts,
        "posts_recuperados": 0,
        "fin_de_paginacion": None,
        "paginacion_truncada": None,
        "motivo_truncamiento": None,
    }

    if not limpio:
        crudo["estado_perfil"] = EstadoPerfil.SIN_HANDLE.value
        crudo["estado_evidencia"] = "no habia handle candidato"
        return crudo

    if forzar_dom:
        return capturar_por_dom_con_sesion(
            page, limpio, n_posts=n_posts, n_comentarios=n_comentarios,
            con_comentarios=con_comentarios,
        )

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
        # ── 2 · El JSON no respondio: se va por DOM con sesion ────────────────
        #
        # No es un "respaldo pobre": medido, el DOM con sesion da caption real,
        # fecha exacta, likes, autor verificado, geotag y comentarios. Lo unico
        # que pierde son las cuentas etiquetadas EN LA FOTO.
        logger.info("@{}: el endpoint JSON no respondio, voy por DOM con sesion",
                    limpio)
        return capturar_por_dom_con_sesion(
            page, limpio, n_posts=n_posts, n_comentarios=n_comentarios,
            con_comentarios=con_comentarios,
        )

    # ── 3 · Mas posts por paginacion del JSON ────────────────────────────────
    if (crudo["via"] == "json"
            and crudo["estado_perfil"] == EstadoPerfil.PUBLICO_LEIDO.value):
        pagina = ((usuario.get("edge_owner_to_timeline_media") or {})
                  .get("page_info") or {})
        hay_mas = bool(pagina.get("has_next_page"))
        cursor = pagina.get("end_cursor")
        id_usuario = usuario.get("id")

        if not hay_mas:
            # El timeline se agoto en la primera pagina: no hay truncamiento
            # posible, la persona publico eso y nada mas.
            crudo["fin_de_paginacion"] = True
        elif len(crudo["posts"]) >= n_posts:
            # Ya alcanzamos lo pedido; quedan mas pero no los queriamos.
            crudo["fin_de_paginacion"] = False
        elif cursor and id_usuario:
            extra, fin, fallo = _mas_posts_por_json(
                page, id_usuario, cursor, n_posts - len(crudo["posts"]),
            )
            crudo["posts"].extend(extra)
            crudo["fin_de_paginacion"] = fin
            crudo["estado_evidencia"] += " + %d por paginacion" % len(extra)
            if fallo:
                crudo["errores"].append(fallo)
        else:
            crudo["fin_de_paginacion"] = False
            crudo["errores"].append(
                "hay mas posts pero el JSON no trajo cursor ni id de usuario: "
                "no se pudo paginar"
            )

    _evaluar_truncamiento(crudo, n_posts)

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


#: Fraccion minima de lo solicitado que hay que recuperar para que la muestra
#: sea utilizable. Por debajo, y si la paginacion NO llego al final, la muestra
#: esta truncada y el ratio de idioma se reporta como null.
#:
#: Un ratio calculado sobre una muestra truncada no es una medicion peor: es
#: otra cosa. Y la distincion entre "no habla español" y "no lo leimos" ya
#: costo 1.075 perfiles una vez.
FRACCION_MINIMA_PAGINACION = 0.60


def _evaluar_truncamiento(crudo: dict, n_solicitados: int) -> None:
    """Decide `paginacion_truncada` y lo escribe en el crudo.

    Truncada = no se llego al fin de la paginacion **y** se recuperaron menos
    del 60% de lo que se podia esperar.

    "Lo que se podia esperar" es el minimo entre lo solicitado y lo que el
    perfil declara publicar: pedirle 30 posts a quien tiene 8 no es un
    truncamiento, es un perfil chico.
    """
    recuperados = len(crudo.get("posts") or [])
    crudo["posts_recuperados"] = recuperados

    if crudo.get("estado_perfil") != EstadoPerfil.PUBLICO_LEIDO.value:
        # Privado, bloqueado o no encontrado: no se leyo el timeline, asi que
        # no hay muestra que truncar. El estado ya lo dice.
        crudo["paginacion_truncada"] = None
        crudo["motivo_truncamiento"] = None
        return

    declarado = (crudo.get("perfil") or {}).get("n_publicaciones")
    try:
        declarado = int(declarado) if declarado is not None else None
    except (TypeError, ValueError):
        declarado = None

    esperados = n_solicitados if declarado is None else min(n_solicitados, declarado)
    crudo["posts_esperados"] = esperados
    crudo["n_publicaciones_declaradas"] = declarado

    if crudo.get("fin_de_paginacion"):
        crudo["paginacion_truncada"] = False
        crudo["motivo_truncamiento"] = None
        return

    if esperados <= 0:
        crudo["paginacion_truncada"] = False
        crudo["motivo_truncamiento"] = None
        return

    umbral = FRACCION_MINIMA_PAGINACION * esperados
    if recuperados < umbral:
        crudo["paginacion_truncada"] = True
        crudo["motivo_truncamiento"] = (
            "se recuperaron %d de %d esperados (%.0f%%, umbral %.0f%%) y la "
            "paginacion no llego al final%s"
            % (recuperados, esperados, recuperados / esperados * 100,
               FRACCION_MINIMA_PAGINACION * 100,
               ". El perfil declara %d publicaciones." % declarado
               if declarado is not None else "")
        )
    else:
        crudo["paginacion_truncada"] = False
        crudo["motivo_truncamiento"] = None


#: Consulta GraphQL para paginar el timeline. El hash es el que usa la web de
#: Instagram; si cambia, la paginacion deja de funcionar y `capturar_crudo` lo
#: registra en `errores` en vez de fallar. Los primeros 12 posts del JSON del
#: perfil no dependen de esto.
#:
#: **Si este hash caduca, todos los perfiles vuelven con exactamente 12 posts.**
#: Es la primera cosa que hay que mirar en el piloto.
QUERY_HASH_TIMELINE = "e769aa130647d2354c40ea6a439bfc08"


def _mas_posts_por_json(
    page, id_usuario: str, cursor: str, faltan: int,
) -> tuple[list[dict], bool, str | None]:
    """Pagina el timeline.

    Devuelve (posts, llego_al_final, fallo). `llego_al_final` distingue "no hay
    mas posts" de "no pudimos seguir pidiendo", que es la diferencia entre una
    muestra completa y una truncada.
    """
    salida: list[dict] = []
    fallo: str | None = None

    while faltan > 0 and cursor:
        variables = json.dumps({
            "id": str(id_usuario),
            "first": min(faltan, 12),
            "after": cursor,
        })
        url = ("https://www.instagram.com/graphql/query/?query_hash=%s&variables=%s"
               % (QUERY_HASH_TIMELINE, urllib.parse.quote(variables)))
        datos = _pedir_json(page, url)

        if datos is None:
            # El endpoint no respondio. Casi siempre es el query_hash caducado.
            return salida, False, (
                "la paginacion del timeline fallo: el endpoint GraphQL no "
                "respondio. Si pasa en todos los perfiles, el query_hash "
                "%s caduco y hay que actualizarlo." % QUERY_HASH_TIMELINE[:12]
            )

        medios = (((datos or {}).get("data") or {}).get("user") or {}).get(
            "edge_owner_to_timeline_media"
        ) or {}
        bordes = medios.get("edges") or []
        if not bordes:
            # Respondio pero sin posts: se asume que no hay mas.
            return salida, True, fallo

        for borde in bordes:
            salida.append(_nodo_a_post_crudo((borde or {}).get("node") or {}))
        faltan -= len(bordes)

        pagina = medios.get("page_info") or {}
        if not pagina.get("has_next_page"):
            return salida, True, fallo
        cursor = pagina.get("end_cursor")
        if not cursor:
            return salida, False, (
                "has_next_page es true pero no vino end_cursor: no se pudo "
                "seguir paginando"
            )
        pausa((1.5, 3.0))

    # Se salio porque se alcanzo lo pedido, no porque se agoto el timeline.
    return salida, False, fallo


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
