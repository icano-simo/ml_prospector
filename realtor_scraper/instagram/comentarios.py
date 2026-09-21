"""Comentarios agregados como perfil de audiencia. Reemplaza S8 sin Zillow.

Para que sirven
---------------
S8 es "friccion declarada" y esta vacia en casi todos los lotes. Es la categoria
que da las aperturas mas potentes, y sin ella cinco de los dolores mejor
documentados del corpus **no se pueden activar nunca**: P-Q02 latencia del
ciclo, P-Q03 caida tardia del contrato, P-Q05 tasacion, P-Q15 cobrador de
documentos, P-Q16 opacidad del estatus.

Un comentario como "¿cuanto necesito de enganche?" o "¿se puede con ITIN?" es
**evidencia directa del dolor del cliente**, en las palabras del cliente. Eso no
lo da ninguna otra fuente gratis.

La regla de privacidad, que no es negociable
--------------------------------------------
**Nunca se perfila individualmente a quien comenta, y no se almacenan sus datos
personales.** Los comentarios entran como agregado: cuantos preguntan por
enganche, en que idioma, si responde el agente. Nunca quien pregunto.

Esto esta implementado, no prometido:

- `Comentario.autor_es_el_agente` es un booleano, no un handle;
- el handle del comentarista **no se guarda**: se descarta en el constructor;
- las @menciones dentro del texto del comentario se **redactan**;
- el texto se guarda solo si pasa el filtro de anonimato, y los emails y
  telefonos que alguien haya dejado en un comentario se redactan siempre.

La diferencia con las menciones del agente
------------------------------------------
Las @cuentas que **el agente** etiqueta en **sus propios captions** si se
guardan (ver `posts.py`): son sus socios comerciales y es informacion de
negocio. Un tercero que comenta en un post no eligio aparecer en nuestro CRM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from instagram.idioma import Idioma, clasificar_pieza

# ── Redaccion de datos personales ─────────────────────────────────────────────

_RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")
_RE_TELEFONO = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"
)
_RE_MENCION = re.compile(r"@[A-Za-z0-9_.]{2,30}")
#: Un numero largo suelto puede ser un telefono sin formato o un DNI.
_RE_NUMERO_LARGO = re.compile(r"(?<!\d)\d{7,}(?!\d)")


def redactar(texto: str) -> tuple[str, list[str]]:
    """Saca datos personales del texto de un comentario.

    Devuelve (texto redactado, que se redacto). Lo segundo va al log de
    auditoria: si un lote redacta mucho, alguien tiene que saber que la gente
    esta dejando su telefono en los comentarios.
    """
    redactado = texto or ""
    encontrados: list[str] = []

    if _RE_EMAIL.search(redactado):
        encontrados.append("email")
        redactado = _RE_EMAIL.sub("[email]", redactado)
    if _RE_TELEFONO.search(redactado):
        encontrados.append("telefono")
        redactado = _RE_TELEFONO.sub("[telefono]", redactado)
    if _RE_MENCION.search(redactado):
        encontrados.append("mencion")
        redactado = _RE_MENCION.sub("[cuenta]", redactado)
    if _RE_NUMERO_LARGO.search(redactado):
        encontrados.append("numero_largo")
        redactado = _RE_NUMERO_LARGO.sub("[numero]", redactado)

    return redactado, encontrados


# ── Comentario ────────────────────────────────────────────────────────────────

@dataclass
class Comentario:
    """Un comentario, ya anonimizado. El autor nunca se guarda.

    Se construye con `desde_crudo`, que es lo unico que ve el handle del autor,
    y solo para compararlo con el del agente. Nunca lo almacena.
    """

    texto: str
    autor_es_el_agente: bool
    idioma: Idioma
    post_url: str | None = None
    redacciones: list[str] = field(default_factory=list)

    @classmethod
    def desde_crudo(
        cls,
        *,
        texto: str,
        handle_autor: str | None,
        handle_agente: str | None,
        post_url: str | None = None,
    ) -> "Comentario":
        """Unico camino de construccion. `handle_autor` se usa y se descarta."""
        es_el_agente = bool(
            handle_autor and handle_agente
            and handle_autor.strip().lstrip("@").lower()
            == handle_agente.strip().lstrip("@").lower()
        )
        redactado, redacciones = redactar(texto)
        pieza = clasificar_pieza(redactado)
        return cls(
            texto=redactado,
            autor_es_el_agente=es_el_agente,
            idioma=pieza.idioma,
            post_url=post_url,
            redacciones=redacciones,
        )


# ── Lexico de friccion del cliente ───────────────────────────────────────────
#
# Cada patron declara el qualifier que alimenta. Estas son las preguntas que la
# gente hace en los comentarios de un agente inmobiliario, y son el dolor del
# CLIENTE, que es exactamente lo que S8 tiene que capturar.

LEXICO_FRICCION: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "enganche": (
        "P-Q07", "pregunta por el capital de entrada",
        (r"\benganch\w*\b", r"\bdown\s?payment\b", r"\bcuanto (?:necesito|hay que)\b",
         r"\bhow much (?:do i need|down)\b", r"\bsin dinero\b", r"\bno tengo (?:para el|el)\b",
         r"\bzero down\b", r"\bayuda con el\b"),
    ),
    "itin_documentos": (
        "P-Q01", "pregunta por documentacion atipica",
        (r"\bitin\b", r"\bsin (?:seguro social|ssn|papeles)\b", r"\bno ssn\b",
         r"\btax\s?id\b", r"\bsin documentos\b", r"\bundocumented\b",
         r"\bwork permit\b", r"\bpermiso de trabajo\b", r"\bdaca\b"),
    ),
    "credito": (
        "P-Q19", "pregunta por puntaje o historial de credito",
        (r"\bcredit(?:o)?\b.{0,20}\b(?:score|puntaje|malo|bad|low|bajo)\b",
         r"\bmi credito\b", r"\bmy credit\b", r"\bno tengo credito\b",
         r"\bno credit\b", r"\bquiebra\b", r"\bbankruptcy\b",
         r"\bforeclosure\b", r"\bcuanto (?:de|necesito de) (?:score|puntaje)\b"),
    ),
    "ingreso_no_w2": (
        "P-Q01/P-Q20", "pregunta por ingreso sin W-2",
        (r"\b1099\b", r"\bself[\s-]?employed\b", r"\bcuenta propia\b",
         r"\bnegocio propio\b", r"\bcash\b.{0,15}\bincome\b", r"\bpago en efectivo\b",
         r"\bbank statement\b", r"\bsin comprobante de ingreso\b"),
    ),
    "cuota_mensual": (
        "P-Q06", "pregunta por el pago mensual",
        (r"\bcuanto (?:seria|es) (?:el|la) (?:pago|cuota|mensual)\b",
         r"\bmonthly payment\b", r"\bcuanto pagaria\b", r"\bhow much (?:a|per) month\b",
         r"\bmensualidad\b"),
    ),
    "precalificacion": (
        "P-Q12", "pregunta como empezar o como precalificar",
        (r"\bcomo (?:empiezo|empezar|califico|calificar)\b",
         r"\bhow do i (?:start|qualify|get started)\b",
         r"\bpre[\s-]?approv\w*\b", r"\bprecalifi\w*\b", r"\bpor donde empiezo\b"),
    ),
    "veterano": (
        "P-Q17", "pregunta por beneficio VA",
        (r"\bva loan\b", r"\bveteran\w*\b", r"\bmilitar\w*\b",
         r"\bfunding fee\b", r"\bsoy veterano\b"),
    ),
    "proceso_opaco": (
        "P-Q16", "pregunta por el estado de su tramite",
        (r"\bcuanto (?:tarda|demora|se tarda)\b", r"\bhow long does it take\b",
         r"\bno me (?:contestan|responden|dicen nada)\b",
         r"\bsigo esperando\b", r"\bstill waiting\b", r"\bno news\b"),
    ),
    "caso_caido": (
        "P-Q03", "menciona un caso que se cayo",
        (r"\bme (?:negaron|rechazaron|lo negaron)\b", r"\bdenied\b",
         r"\bse cayo\b", r"\bfell through\b", r"\bno me aprobaron\b",
         r"\bdidn'?t (?:qualify|get approved)\b"),
    ),
    "idioma": (
        "P-Q14", "pregunta si se atiende en español",
        (r"\bhabla(?:n|s)? espa[nñ]ol\b", r"\bspeak spanish\b",
         r"\ben espa[nñ]ol\b", r"\bsomeone who speaks spanish\b"),
    ),
}


def _detectar(patrones: tuple[str, ...], texto: str) -> bool:
    return any(re.search(p, texto, re.IGNORECASE) for p in patrones)


# ── Perfil de audiencia ───────────────────────────────────────────────────────

@dataclass
class PerfilDeAudiencia:
    """Lo que la audiencia pregunta, agregado. Nunca quien pregunta.

    Este objeto es todo lo que sale del modulo. No hay forma de recuperar un
    comentarista individual desde aca, porque su handle nunca se guardo.
    """

    n_comentarios: int
    n_de_terceros: int
    n_del_agente: int
    tasa_de_respuesta_del_agente: float | None

    #: {clave de friccion: {qualifier, descripcion, n, ejemplos redactados}}
    fricciones: dict[str, dict] = field(default_factory=dict)

    #: Idioma de los comentarios de TERCEROS. Es la señal de idioma de los
    #: clientes, que es distinta de la del agente y vale mas.
    idioma_terceros: dict[str, int] = field(default_factory=dict)

    n_posts_con_comentarios: int = 0
    redacciones_aplicadas: dict[str, int] = field(default_factory=dict)
    nota_de_evidencia: str = ""

    @property
    def ratio_espanol_terceros(self) -> float | None:
        es = self.idioma_terceros.get(Idioma.ESPANOL.value, 0)
        en = self.idioma_terceros.get(Idioma.INGLES.value, 0)
        mx = self.idioma_terceros.get(Idioma.MIXTO.value, 0)
        total = es + en + mx
        return None if total == 0 else (es + 0.5 * mx) / total

    def friccion_dominante(self) -> tuple[str, dict] | None:
        if not self.fricciones:
            return None
        clave = max(self.fricciones, key=lambda k: self.fricciones[k]["n"])
        return clave, self.fricciones[clave]


#: Minimo de comentarios de terceros para que el perfil de audiencia sostenga
#: algo. Por debajo se reporta pero no activa qualifiers: tres comentarios no
#: son un perfil de audiencia.
MIN_COMENTARIOS_TERCEROS = 15

#: Ejemplos guardados por friccion. Se limita a proposito: el ejemplo existe
#: para que el BD entienda el tono, no para construir un corpus de mensajes de
#: gente que no sabe que los estamos leyendo.
MAX_EJEMPLOS_POR_FRICCION = 3


def perfilar_audiencia(
    comentarios: list[Comentario],
    *,
    n_posts_con_comentarios: int = 0,
) -> PerfilDeAudiencia:
    """Agrega los comentarios en un perfil de audiencia anonimo."""
    terceros = [c for c in comentarios if not c.autor_es_el_agente]
    del_agente = [c for c in comentarios if c.autor_es_el_agente]

    fricciones: dict[str, dict] = {}
    for c in terceros:
        for clave, (qualifier, descripcion, patrones) in LEXICO_FRICCION.items():
            if not _detectar(patrones, c.texto):
                continue
            entrada = fricciones.setdefault(clave, {
                "qualifier": qualifier,
                "descripcion": descripcion,
                "n": 0,
                "ejemplos": [],
            })
            entrada["n"] += 1
            if len(entrada["ejemplos"]) < MAX_EJEMPLOS_POR_FRICCION:
                entrada["ejemplos"].append(c.texto[:200])

    idioma_terceros: dict[str, int] = {}
    for c in terceros:
        idioma_terceros[c.idioma.value] = idioma_terceros.get(c.idioma.value, 0) + 1

    redacciones: dict[str, int] = {}
    for c in comentarios:
        for r in c.redacciones:
            redacciones[r] = redacciones.get(r, 0) + 1

    tasa = None
    if n_posts_con_comentarios > 0:
        # Proxy de si responde: posts donde el agente comento sobre el total de
        # posts que tienen comentarios.
        posts_respondidos = len({c.post_url for c in del_agente if c.post_url})
        tasa = round(posts_respondidos / n_posts_con_comentarios, 3)

    if len(terceros) >= MIN_COMENTARIOS_TERCEROS:
        nota = "%d comentarios de terceros: alcanza para un perfil de audiencia" % len(terceros)
    else:
        nota = (
            "solo %d comentarios de terceros (se necesitan %d): se reporta pero "
            "NO activa qualifiers. Tres comentarios no son un perfil de audiencia."
            % (len(terceros), MIN_COMENTARIOS_TERCEROS)
        )

    return PerfilDeAudiencia(
        n_comentarios=len(comentarios),
        n_de_terceros=len(terceros),
        n_del_agente=len(del_agente),
        tasa_de_respuesta_del_agente=tasa,
        fricciones=fricciones,
        idioma_terceros=idioma_terceros,
        n_posts_con_comentarios=n_posts_con_comentarios,
        redacciones_aplicadas=redacciones,
        nota_de_evidencia=nota,
    )


def verificar_anonimato(perfil: PerfilDeAudiencia) -> None:
    """Guarda redundante: falla si se colo un dato personal en el agregado.

    Es redundante a proposito. `Comentario.desde_crudo` ya redacta, pero esto
    revisa el resultado final, que es lo que se guarda en disco.
    """
    sospechosos: list[str] = []
    for clave, datos in perfil.fricciones.items():
        for ejemplo in datos.get("ejemplos", []):
            if _RE_EMAIL.search(ejemplo):
                sospechosos.append("%s: email sin redactar" % clave)
            if _RE_TELEFONO.search(ejemplo):
                sospechosos.append("%s: telefono sin redactar" % clave)
            if _RE_MENCION.search(ejemplo):
                sospechosos.append("%s: @mencion sin redactar" % clave)
    if sospechosos:
        raise AssertionError(
            "el perfil de audiencia trae datos personales de terceros: %s\n"
            "Ningun dato personal de terceros se almacena individualmente. "
            "Revisa redactar() antes de seguir." % sospechosos
        )
