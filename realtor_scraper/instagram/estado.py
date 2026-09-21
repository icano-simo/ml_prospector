"""Estado del perfil de Instagram. El arreglo numero uno del Bloque 1.

El bug que esto reemplaza
-------------------------
`_fetch_ig_profile` devolvia `{}` ante cualquier fallo, y aguas abajo eso se
volvia `False` en cada señal de contenido. Medido sobre las 5.620 filas del
dataset archivado:

    ig_is_private     0 positivos · 5.620 negativos · 0 nulos

Cero cuentas privadas en 5.620 perfiles inmobiliarios es imposible. La señal no
se medía: se rellenaba. Y `ig_is_private` termino con importancia **exactamente
0,000** en el modelo, porque una columna constante no aporta nada y nadie se
da cuenta, ya que un clasificador no se queja de una columna muerta.

Ademas 1.075 perfiles tenian handle y ninguna bio, y 4.557 tenian handle y
ninguna señal de contenido positiva. Todos entraron como afirmaciones negativas
que nadie midio.

La regla
--------
Nunca se devuelve False donde corresponde null. Cada estado de abajo dice algo
distinto sobre POR QUE falta un dato, y el motor de reglas necesita esa
diferencia: un perfil privado es un dato sobre la persona, un handle
equivocado es un dato sobre nuestro scraper.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class EstadoPerfil(str, Enum):
    """Los cinco estados posibles, explicitos.

    No hay un sexto que signifique "algo paso". Si aparece un caso nuevo, se
    agrega aca y se decide que hacer con el, en vez de caer en un `else` que
    lo trate como si el perfil estuviera vacio.
    """

    #: Se cargo el perfil y se pudieron leer los posts.
    PUBLICO_LEIDO = "publico_leido"

    #: El perfil existe, la bio y los contadores se leen del meta, pero los
    #: posts no. Las señales de contenido quedan en null, NO en False.
    PRIVADO = "privado"

    #: 404 o pagina de "Sorry, this page isn't available".
    NO_ENCONTRADO = "no_encontrado"

    #: Instagram devolvio un muro de login, un checkpoint o un 429. Es un dato
    #: sobre nuestro acceso, no sobre la persona: se reintenta.
    BLOQUEADO = "bloqueado"

    #: El perfil cargo pero no es de esta persona. Ver verificacion.py.
    HANDLE_EQUIVOCADO = "handle_equivocado"

    #: No se llego a intentar (sin handle candidato).
    SIN_HANDLE = "sin_handle"

    @property
    def contenido_legible(self) -> bool:
        """Solo en PUBLICO_LEIDO tiene sentido medir señales de contenido."""
        return self is EstadoPerfil.PUBLICO_LEIDO

    @property
    def perfil_existe(self) -> bool:
        return self in (
            EstadoPerfil.PUBLICO_LEIDO,
            EstadoPerfil.PRIVADO,
            EstadoPerfil.HANDLE_EQUIVOCADO,
        )

    @property
    def conviene_reintentar(self) -> bool:
        """BLOQUEADO es transitorio; NO_ENCONTRADO no lo es."""
        return self is EstadoPerfil.BLOQUEADO

    def motivo(self) -> str:
        return {
            EstadoPerfil.PUBLICO_LEIDO: "perfil publico leido",
            EstadoPerfil.PRIVADO: (
                "cuenta privada: la bio y los contadores se leen, los posts no"
            ),
            EstadoPerfil.NO_ENCONTRADO: "el handle no existe en Instagram",
            EstadoPerfil.BLOQUEADO: (
                "Instagram bloqueo el acceso (muro de login, checkpoint o limite "
                "de tasa): es un dato sobre nuestro acceso, no sobre la persona"
            ),
            EstadoPerfil.HANDLE_EQUIVOCADO: (
                "el perfil cargo pero no se pudo verificar que sea de esta persona"
            ),
            EstadoPerfil.SIN_HANDLE: "no se encontro ningun handle candidato",
        }[self]


# ── Deteccion ─────────────────────────────────────────────────────────────────

#: Frases de Instagram para cuenta privada, en las variantes que renderiza.
#: Se comparan sin distinguir mayusculas porque la plataforma alterna entre
#: "This account is private" y "This Account is Private" segun el render.
_PATRONES_PRIVADO = (
    r"this account is private",
    r"esta cuenta es privada",
    r"already follow.*to see their photos and videos",
    r"sigue a .* para ver sus fotos y videos",
)

_PATRONES_NO_ENCONTRADO = (
    r"sorry,?\s*this page\s*isn'?t available",
    r"page not found",
    r"la p[aá]gina no est[aá] disponible",
    r"esta p[aá]gina no est[aá] disponible",
)

_PATRONES_BLOQUEADO = (
    r"log in to see",
    r"inicia sesi[oó]n para ver",
    r"please wait a few minutes before you try again",
    r"espera unos minutos antes de volver a intentarlo",
    r"suspicious login attempt",
    r"challenge_required",
    r"help us confirm",
    r"confirm your identity",
    r"try again later",
)


def _alguno(patrones: tuple[str, ...], texto: str) -> str | None:
    for p in patrones:
        if re.search(p, texto, re.IGNORECASE):
            return p
    return None


@dataclass
class Diagnostico:
    """El estado del perfil y la evidencia de por que se decidio asi."""

    estado: EstadoPerfil
    evidencia: str
    codigo_http: int | None = None
    senales_detectadas: list[str] = field(default_factory=list)


def diagnosticar(
    *,
    handle: str | None,
    codigo_http: int | None,
    titulo: str,
    texto_body: str,
    hay_meta_description: bool,
    n_articulos_con_posts: int,
) -> Diagnostico:
    """Decide el estado del perfil. Es la unica puerta a las señales.

    El orden de las comprobaciones importa: bloqueado se evalua ANTES que
    privado, porque un muro de login tambien dice "log in to see" y no
    significa que la cuenta sea privada.
    """
    if not handle:
        return Diagnostico(
            estado=EstadoPerfil.SIN_HANDLE,
            evidencia="no habia handle candidato",
        )

    texto = "%s\n%s" % (titulo or "", texto_body or "")

    if codigo_http is not None and codigo_http in (401, 403, 429, 500, 502, 503):
        return Diagnostico(
            estado=EstadoPerfil.BLOQUEADO,
            evidencia="HTTP %d" % codigo_http,
            codigo_http=codigo_http,
        )

    encontrado = _alguno(_PATRONES_BLOQUEADO, texto)
    if encontrado:
        return Diagnostico(
            estado=EstadoPerfil.BLOQUEADO,
            evidencia="texto de bloqueo: %r" % encontrado,
            codigo_http=codigo_http,
            senales_detectadas=[encontrado],
        )

    if codigo_http == 404:
        return Diagnostico(
            estado=EstadoPerfil.NO_ENCONTRADO,
            evidencia="HTTP 404",
            codigo_http=404,
        )

    encontrado = _alguno(_PATRONES_NO_ENCONTRADO, texto)
    if encontrado:
        return Diagnostico(
            estado=EstadoPerfil.NO_ENCONTRADO,
            evidencia="texto de pagina inexistente: %r" % encontrado,
            codigo_http=codigo_http,
            senales_detectadas=[encontrado],
        )

    encontrado = _alguno(_PATRONES_PRIVADO, texto)
    if encontrado:
        return Diagnostico(
            estado=EstadoPerfil.PRIVADO,
            evidencia="texto de cuenta privada: %r" % encontrado,
            codigo_http=codigo_http,
            senales_detectadas=[encontrado],
        )

    if not hay_meta_description and n_articulos_con_posts == 0:
        # Ni meta ni posts: no se leyo nada. La version anterior devolvia {} aca
        # y eso terminaba en False en catorce columnas.
        return Diagnostico(
            estado=EstadoPerfil.BLOQUEADO,
            evidencia=(
                "la pagina cargo pero no trae meta description ni posts: no se "
                "leyo nada, asi que no se afirma nada"
            ),
            codigo_http=codigo_http,
        )

    if n_articulos_con_posts == 0 and hay_meta_description:
        # Meta si, posts no, y sin texto de privado. Puede ser una cuenta sin
        # publicaciones o un render parcial. No se asume: se declara privado a
        # efectos de disponibilidad, que es el estado conservador.
        return Diagnostico(
            estado=EstadoPerfil.PRIVADO,
            evidencia=(
                "se leyo el meta pero cero posts y sin aviso de cuenta privada: "
                "puede ser cuenta sin publicaciones o render parcial. Se trata "
                "como privado para que las señales de contenido queden en null"
            ),
            codigo_http=codigo_http,
        )

    return Diagnostico(
        estado=EstadoPerfil.PUBLICO_LEIDO,
        evidencia="%d contenedores de post leidos" % n_articulos_con_posts,
        codigo_http=codigo_http,
    )
