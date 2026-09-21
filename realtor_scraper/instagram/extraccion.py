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
        logger.debug("navegacion a %s fallo: %s", url, exc)
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
        logger.info("@%s: %s (%s)", handle, diag.estado.value, diag.evidencia)
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
            logger.warning("bloqueo leyendo %s (HTTP %s): corto el perfil", url, codigo)
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
            logger.warning("bloqueo leyendo comentarios (HTTP %s): corto", codigo)
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
            "@%s bloqueado (%s). Espero %.0fs antes del reintento %d/%d",
            handle, perfil.diagnostico.evidencia, espera, intento + 1, len(BACKOFF),
        )
        time.sleep(espera)
        perfil = leer_perfil(page, handle, con_comentarios=con_comentarios)
        intento += 1
    return perfil
