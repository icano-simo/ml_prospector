"""Verificacion de handle de Instagram. El arreglo numero dos del Bloque 1.

El problema
-----------
**5.516 de 5.620 handles "encontrados" (98,1%)** por busqueda de nombre en
DuckDuckGo. Un 98% de acierto buscando handles por nombre no es creible.

La causa esta en una linea:

    handles = re.findall(r"instagram\\.com/([A-Za-z0-9_.]{3,30})", content)
    for h in handles:
        if h.lower() not in _SKIP_HANDLES and not h.startswith("_"):
            return h

`content` es el HTML **completo** de la pagina de resultados. Devuelve el primer
`instagram.com/...` que aparezca en cualquier parte: un anuncio, un resultado
ajeno, un enlace del pie de DuckDuckGo, el perfil de otra persona con nombre
parecido. Nunca se comprobo que el perfil fuera de esa persona.

Y como no habia verificacion, un handle equivocado no producia un error:
producia catorce señales de contenido sobre la persona equivocada.

La regla
--------
Dos condiciones, las dos necesarias:

1. **el nombre del perfil se parece al del realtor**, y
2. **la bio o los posts traen señal inmobiliaria**.

Si no, `handle_confidence = BAJA` y **sus señales no se usan**. No se descarta
el handle: se guarda con su confianza, porque un handle de confianza baja sigue
siendo un punto de partida para una verificacion manual.

Lo que NO se hace
-----------------
No se compara apellido con origen, etnia ni nada parecido. La comparacion de
nombre es **comparacion de cadenas** entre el nombre que nos dio la fuente y el
nombre que la persona puso en su propio perfil. Eso es identidad, no inferencia
de nicho.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum

# ── Confianza ─────────────────────────────────────────────────────────────────


class Confianza(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"

    @property
    def usable(self) -> bool:
        """Solo ALTA y MEDIA alimentan señales del motor de reglas."""
        return self is not Confianza.BAJA


# ── Normalizacion de nombres ──────────────────────────────────────────────────

#: Palabras que aparecen en los nombres de perfil de agentes inmobiliarios y no
#: son parte del nombre de la persona. Se sacan antes de comparar, si no
#: "Ana Tapia | Realtor" no matchea "Ana Tapia".
_RUIDO_EN_NOMBRE = {
    "realtor", "realtors", "realty", "real", "estate", "broker", "brokerage",
    "agent", "agente", "homes", "home", "properties", "property", "group",
    "team", "equipo", "the", "your", "tu", "sold", "by", "with", "con",
    "llc", "inc", "co", "pa", "pllc",
}

#: Sufijos y titulos que tampoco cuentan.
_TITULOS = {"jr", "sr", "ii", "iii", "iv", "mr", "mrs", "ms", "dr"}


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def tokens_de_nombre(texto: str) -> list[str]:
    """Nombre -> lista de tokens comparables, sin acentos ni ruido de oficio."""
    limpio = _sin_acentos(texto or "").lower()
    # los handles vienen pegados o con separadores: sold_by_ana, ana.tapia
    limpio = re.sub(r"[._\-|/+]+", " ", limpio)
    limpio = re.sub(r"[^a-z0-9 ]+", " ", limpio)
    brutos = [t for t in limpio.split() if t]
    return [
        t for t in brutos
        if len(t) > 1 and t not in _RUIDO_EN_NOMBRE and t not in _TITULOS
    ]


def _separar_camel_y_digitos(handle: str) -> str:
    """`AnaTapiaRealtor` -> `Ana Tapia Realtor`, `anatapia01` -> `anatapia 01`."""
    con_espacios = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", handle)
    return re.sub(r"(?<=[A-Za-z])(?=\d)", " ", con_espacios)


def _subcadena_de_algun_token(aguja: str, tokens: list[str]) -> bool:
    """Para handles pegados: 'anatapia' contiene 'ana' y 'tapia'."""
    return any(aguja and aguja in t for t in tokens)


@dataclass
class CoincidenciaDeNombre:
    coincide: bool
    tokens_realtor: list[str]
    tokens_perfil: list[str]
    comunes: list[str] = field(default_factory=list)
    detalle: str = ""


def comparar_nombre(
    nombre_realtor: str,
    nombre_perfil: str | None,
    handle: str | None = None,
) -> CoincidenciaDeNombre:
    """El nombre del perfil (o el handle) tiene que parecerse al del realtor.

    Se exige que coincidan **al menos dos tokens**, o **uno si ese token es el
    apellido y tiene 5 letras o mas**. Un solo token corto coincidiendo — "Ana"
    contra "Ana Gomez" — no alcanza: hay demasiadas Anas.
    """
    t_realtor = tokens_de_nombre(nombre_realtor)
    if not t_realtor:
        return CoincidenciaDeNombre(
            coincide=False, tokens_realtor=[], tokens_perfil=[],
            detalle="el nombre del realtor quedo sin tokens comparables",
        )

    candidatos: list[str] = []
    if nombre_perfil:
        candidatos.extend(tokens_de_nombre(nombre_perfil))
    if handle:
        candidatos.extend(tokens_de_nombre(_separar_camel_y_digitos(handle)))
    t_perfil = list(dict.fromkeys(candidatos))

    if not t_perfil:
        return CoincidenciaDeNombre(
            coincide=False, tokens_realtor=t_realtor, tokens_perfil=[],
            detalle="ni el nombre del perfil ni el handle dieron tokens",
        )

    exactos = [t for t in t_realtor if t in t_perfil]
    pegados = [
        t for t in t_realtor
        if t not in exactos and len(t) >= 4 and _subcadena_de_algun_token(t, t_perfil)
    ]
    comunes = exactos + pegados

    # El ultimo token del nombre del realtor se trata como apellido.
    apellido = t_realtor[-1]
    apellido_coincide = apellido in comunes and len(apellido) >= 5

    coincide = len(comunes) >= 2 or apellido_coincide
    if coincide:
        detalle = "coinciden %s%s" % (
            comunes, " (apellido largo)" if apellido_coincide and len(comunes) < 2 else "",
        )
    elif comunes:
        detalle = (
            "coincide solo %s: un token corto o un nombre de pila suelto no "
            "alcanza para afirmar identidad" % comunes
        )
    else:
        detalle = "ningun token en comun"

    return CoincidenciaDeNombre(
        coincide=coincide, tokens_realtor=t_realtor, tokens_perfil=t_perfil,
        comunes=comunes, detalle=detalle,
    )


# ── Señal inmobiliaria ────────────────────────────────────────────────────────

#: Se busca con limite de palabra. `\bestates?\b` matchea "real estate" y por
#: eso NO esta aca: ese patron inflo el sub-nicho de lujo de ~126 a mas de
#: 1.000 filas en una corrida real antes de detectarse.
_PATRONES_INMOBILIARIA = (
    r"\brealtor\b", r"\brealtors\b", r"\brealty\b",
    r"\breal estate\b", r"\bbienes ra[ií]ces\b",
    r"\bbroker\b", r"\bbrokerage\b",
    r"\blisting[s]?\b", r"\blistado[s]?\b",
    r"\bfor sale\b", r"\bse vende\b", r"\ben venta\b",
    r"\bhomebuyer[s]?\b", r"\bhome buyer[s]?\b",
    r"\bfirst time buyer\b", r"\bprimera casa\b",
    r"\bmls\b", r"\bopen house\b", r"\bcasa abierta\b",
    r"\bclosing day\b", r"\bd[ií]a de cierre\b",
    r"\bunder contract\b", r"\bjust sold\b", r"\bvendida?\b",
    r"\bhomes? for sale\b", r"\bcompra tu casa\b",
    r"\bnar\b", r"\bnahrep\b",
    r"\blic(?:ense|encia)?\s*#?\s*\d", r"\bdre\s*#?\s*\d", r"\btrec\b",
)


@dataclass
class SenalInmobiliaria:
    hay: bool
    patrones: list[str] = field(default_factory=list)
    donde: str = ""


def detectar_senal_inmobiliaria(bio: str | None, captions: list[str] | None = None
                                ) -> SenalInmobiliaria:
    """Busca señal de oficio en la bio y en los captions. No en el alt-text."""
    encontrados: list[str] = []
    donde: list[str] = []

    if bio:
        texto_bio = _sin_acentos(bio).lower()
        for p in _PATRONES_INMOBILIARIA:
            if re.search(p, texto_bio, re.IGNORECASE):
                encontrados.append(p)
                if "bio" not in donde:
                    donde.append("bio")

    if captions:
        texto_caps = _sin_acentos(" \n ".join(captions)).lower()
        for p in _PATRONES_INMOBILIARIA:
            if re.search(p, texto_caps, re.IGNORECASE):
                if p not in encontrados:
                    encontrados.append(p)
                if "captions" not in donde:
                    donde.append("captions")

    return SenalInmobiliaria(
        hay=bool(encontrados),
        patrones=encontrados,
        donde=" + ".join(donde),
    )


# ── Veredicto ─────────────────────────────────────────────────────────────────

@dataclass
class Verificacion:
    """El veredicto sobre si este perfil es de esta persona."""

    confianza: Confianza
    nombre: CoincidenciaDeNombre
    inmobiliaria: SenalInmobiliaria
    razon: str

    @property
    def senales_usables(self) -> bool:
        return self.confianza.usable


def verificar(
    *,
    nombre_realtor: str,
    handle: str | None,
    nombre_perfil: str | None,
    bio: str | None,
    captions: list[str] | None = None,
    licencia_en_bio: str | None = None,
) -> Verificacion:
    """Las dos condiciones, y la confianza que sale de combinarlas.

    | nombre | inmobiliaria | confianza |
    |---|---|---|
    | coincide | si | ALTA |
    | coincide | no | MEDIA |
    | no       | si | BAJA |
    | no       | no | BAJA |

    Mas una excepcion: si la bio trae un numero de licencia que coincide con el
    que tenemos, es ALTA sin importar el nombre. La licencia es la llave de
    identidad del sistema entero; un nombre es una cadena.
    """
    nombre = comparar_nombre(nombre_realtor, nombre_perfil, handle)
    inmo = detectar_senal_inmobiliaria(bio, captions)

    if licencia_en_bio:
        return Verificacion(
            confianza=Confianza.ALTA,
            nombre=nombre,
            inmobiliaria=inmo,
            razon=(
                "la bio declara la licencia %s y coincide con la nuestra: la "
                "licencia manda sobre la comparacion de nombre"
                % licencia_en_bio
            ),
        )

    if nombre.coincide and inmo.hay:
        return Verificacion(
            confianza=Confianza.ALTA, nombre=nombre, inmobiliaria=inmo,
            razon="%s, y hay señal inmobiliaria en %s" % (nombre.detalle, inmo.donde),
        )

    if nombre.coincide and not inmo.hay:
        return Verificacion(
            confianza=Confianza.MEDIA, nombre=nombre, inmobiliaria=inmo,
            razon=(
                "%s, pero no hay señal inmobiliaria en la bio ni en los "
                "captions: puede ser su cuenta personal" % nombre.detalle
            ),
        )

    return Verificacion(
        confianza=Confianza.BAJA, nombre=nombre, inmobiliaria=inmo,
        razon=(
            "el nombre no verifica (%s)%s. Sus señales NO se usan: un handle "
            "equivocado no produce un error, produce catorce señales sobre la "
            "persona equivocada."
            % (nombre.detalle,
               "" if not inmo.hay else " aunque hay señal inmobiliaria")
        ),
    )


# ── Licencia en la bio ────────────────────────────────────────────────────────

#: Los agentes suelen poner su licencia en la bio. Es el cruce mas barato que
#: existe y nadie lo estaba mirando.
_PATRONES_LICENCIA = (
    # TREC (Texas), DRE (California), BK/SL (Florida), generico
    r"\btrec\s*#?\s*(\d{4,8})\b",
    r"\bdre\s*#?\s*(\d{6,9})\b",
    r"\b(?:bk|sl|bkbk)\s*#?\s*(\d{6,9})\b",
    r"\blic(?:ense|encia)?\.?\s*#?\s*(\d{4,10})\b",
    r"\b(?:re|realtor)\s*lic(?:ense)?\.?\s*#?\s*(\d{4,10})\b",
)


def extraer_licencias_de_bio(bio: str | None) -> list[str]:
    """Numeros de licencia que la persona publico ella misma. Evidencia E0."""
    if not bio:
        return []
    texto = _sin_acentos(bio)
    salida: list[str] = []
    for p in _PATRONES_LICENCIA:
        for m in re.finditer(p, texto, re.IGNORECASE):
            valor = m.group(1)
            if valor not in salida:
                salida.append(valor)
    return salida
