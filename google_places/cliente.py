"""Google Places API (New): reviews del agente y de la oficina. Prioridad 2 de S8.

Por que Google Places y no scraping
-----------------------------------
Es una **API oficial y de pago**. No hay problema de terminos de uso, no hay
muro anti-bot y no hay que evadir nada. Eso es exactamente lo que fallo con
Zillow, donde toda la ingenieria termino en mas codigo de evasion y cero
columnas.

Lo que da, y para que sirve
---------------------------
| Campo | Alimenta |
|---|---|
| `rating` y `userRatingCount` | S8, friccion declarada, con denominador |
| hasta 5 textos de review | S8 y el dolor del cliente en sus palabras |
| `languageCode` de cada review | **el idioma de los CLIENTES**, que vale mas que el del agente |
| `reviews[].publishTime` | fecha, para la cadena de evidencia |

La matriz acepta para P-Q14 «>=10 piezas **o** >=5 reviews». Cinco reviews es
exactamente el umbral, asi que un perfil con las cinco que devuelve la API
cumple el estandar **sin** necesidad de los captions. Por eso `perfilar()` de
`instagram.idioma` acepta `n_reviews`.

Tres advertencias que hay que tener presentes
---------------------------------------------
1. **La API devuelve como maximo 5 reviews.** No son las 5 mas representativas
   ni una muestra aleatoria: Google elige. Con `userRatingCount = 180` y 5
   textos, cualquier proporcion calculada sobre esos 5 tiene denominador 5, no
   180. `Lugar.pct_reviews_en_espanol()` lo reporta con su denominador.

2. **La politica de Google limita el almacenamiento de contenido de Places.**
   El `place_id` se puede guardar indefinidamente; el resto del contenido, no.
   Por eso este modulo separa `place_id` (llave persistente) de
   `Review` (contenido), y `a_fila_persistible()` devuelve **solo los
   agregados**: conteos, rating, idiomas y los qualifiers activados. El texto
   crudo de la review se usa en memoria y no se escribe en la sabana.
   Es la diferencia con los captions de Instagram, que si se guardan enteros.

3. **No se perfila individualmente a quien escribio la review.** El nombre del
   autor que devuelve la API se descarta en el constructor, igual que en
   `instagram.comentarios`.

Configuracion
-------------
    GOOGLE_PLACES_API_KEY=...

La clave se lee del entorno. **Nunca se pasa por la linea de comandos**: queda
en el historial del shell.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_BUSQUEDA = "https://places.googleapis.com/v1/places:searchText"
BASE_DETALLE = "https://places.googleapis.com/v1/places/%s"

#: Campos que se piden. La API cobra por mascara de campos, asi que pedir de
#: menos es mas barato y pedir de mas es tirar plata.
CAMPOS_BUSQUEDA = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.rating,places.userRatingCount,places.types,places.websiteUri"
)
CAMPOS_DETALLE = (
    "id,displayName,formattedAddress,rating,userRatingCount,types,"
    "websiteUri,nationalPhoneNumber,reviews"
)

#: Maximo de reviews que devuelve la API. No es configurable.
MAX_REVIEWS_API = 5

PAUSA_MINIMA = 0.6
BACKOFF = (2, 8, 30)


class PlacesNoDisponible(RuntimeError):
    """No se pudo consultar. No se devuelve un rating inventado."""


def _clave() -> str:
    clave = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    if not clave:
        raise PlacesNoDisponible(
            "Falta GOOGLE_PLACES_API_KEY en el entorno.\n"
            "\n"
            "Se saca en https://console.cloud.google.com -> APIs -> Places API (New).\n"
            "Es de pago, con cuota gratuita mensual.\n"
            "\n"
            "Ponela en el entorno, NO en la linea de comandos: un argumento "
            "queda en el historial del shell."
        )
    return clave


_ultima = [0.0]


def _pedir(url: str, *, cuerpo: dict | None = None, campos: str) -> dict:
    espera = PAUSA_MINIMA - (time.time() - _ultima[0])
    if espera > 0:
        time.sleep(espera)
    _ultima[0] = time.time()

    cabeceras = {
        "X-Goog-Api-Key": _clave(),
        "X-Goog-FieldMask": campos,
        "Content-Type": "application/json",
    }
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None

    for intento in range(len(BACKOFF) + 1):
        try:
            req = Request(url, data=datos, headers=cabeceras,
                          method="POST" if datos else "GET")
            with urlopen(req, timeout=45) as respuesta:  # noqa: S310 - host fijo
                return json.loads(respuesta.read().decode("utf-8"))
        except HTTPError as exc:
            detalle = ""
            try:
                detalle = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:  # noqa: BLE001
                pass
            if exc.code in (429, 500, 503) and intento < len(BACKOFF):
                time.sleep(BACKOFF[intento])
                continue
            raise PlacesNoDisponible(
                "Places devolvio HTTP %d. %s%s"
                % (exc.code, detalle,
                   "\nUn 403 suele ser que la Places API (New) no esta "
                   "habilitada en el proyecto, o que la clave tiene "
                   "restriccion de referrer." if exc.code == 403 else "")
            ) from exc
        except (URLError, json.JSONDecodeError) as exc:
            if intento < len(BACKOFF):
                time.sleep(BACKOFF[intento])
                continue
            raise PlacesNoDisponible("no pude consultar Places: %s" % exc) from exc

    raise PlacesNoDisponible("agotados los reintentos")


# ── Modelo ────────────────────────────────────────────────────────────────────

_RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")
_RE_TELEFONO = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"
)


@dataclass
class Review:
    """Una review, ya anonimizada. El autor nunca se guarda.

    Se construye con `desde_api`, que es lo unico que ve el nombre del autor, y
    no lo almacena. Es la misma regla que en instagram.comentarios.
    """

    texto: str
    codigo_idioma: str | None
    calificacion: int | None
    publicada: str | None

    @classmethod
    def desde_api(cls, cruda: dict) -> "Review":
        texto_original = (
            (cruda.get("originalText") or {}).get("text")
            or (cruda.get("text") or {}).get("text")
            or ""
        )
        idioma = (
            (cruda.get("originalText") or {}).get("languageCode")
            or (cruda.get("text") or {}).get("languageCode")
        )
        limpio = _RE_TELEFONO.sub("[telefono]", _RE_EMAIL.sub("[email]", texto_original))
        return cls(
            texto=limpio,
            codigo_idioma=idioma,
            calificacion=cruda.get("rating"),
            publicada=cruda.get("publishTime"),
        )

    @property
    def es_espanol(self) -> bool | None:
        """None si la API no declaro idioma. None no es False."""
        if not self.codigo_idioma:
            return None
        return self.codigo_idioma.lower().startswith("es")


@dataclass
class Lugar:
    """Un agente o una oficina en Google Places."""

    place_id: str
    nombre: str | None = None
    direccion: str | None = None
    #: `rating` de Google es None cuando no hay reviews. Nunca es 0.
    rating: float | None = None
    n_reviews_total: int | None = None
    tipos: list[str] = field(default_factory=list)
    web: str | None = None
    telefono: str | None = None
    reviews: list[Review] = field(default_factory=list)

    @property
    def n_reviews_con_texto(self) -> int:
        return sum(1 for r in self.reviews if r.texto.strip())

    def pct_reviews_en_espanol(self) -> str:
        """Con denominador SIEMPRE, y el denominador es 5, no userRatingCount.

        La API devuelve como maximo 5 reviews y las elige ella. Una proporcion
        sobre esas 5 no es una proporcion sobre las 180 que puede tener el
        lugar, y confundirlas es la misma trampa que "Top 3 Concentration 100%".
        """
        con_idioma = [r for r in self.reviews if r.es_espanol is not None]
        if not con_idioma:
            return "[sin dato: ninguna review declara idioma]"
        n_es = sum(1 for r in con_idioma if r.es_espanol)
        base = "%.0f%% (%d/%d de las reviews devueltas" % (
            n_es / len(con_idioma) * 100, n_es, len(con_idioma),
        )
        if self.n_reviews_total and self.n_reviews_total > len(con_idioma):
            base += ", de %d totales que tiene el lugar" % self.n_reviews_total
        return base + ")"

    @property
    def cumple_umbral_matriz(self) -> bool:
        """La matriz acepta >=5 reviews para sostener P-Q14."""
        return self.n_reviews_con_texto >= 5

    def textos(self) -> list[str]:
        """Los textos, para pasarlos a instagram.idioma o al lexico de friccion.

        **En memoria.** No se persisten: ver la advertencia 2 del modulo.
        """
        return [r.texto for r in self.reviews if r.texto.strip()]

    def a_fila_persistible(self) -> dict:
        """Solo lo que se puede guardar: agregados y el place_id.

        El texto crudo de las reviews NO va aca. La politica de Google limita
        el almacenamiento de contenido de Places; el place_id es la excepcion.
        """
        return {
            "places_place_id": self.place_id,
            "places_nombre": self.nombre,
            "places_rating": self.rating,
            "places_n_reviews_total": self.n_reviews_total,
            "places_n_reviews_con_texto": self.n_reviews_con_texto,
            "places_pct_espanol": self.pct_reviews_en_espanol(),
            "places_cumple_umbral_matriz": self.cumple_umbral_matriz,
            "places_telefono": self.telefono,
            "places_web": self.web,
        }


# ── Consultas ─────────────────────────────────────────────────────────────────

def buscar(consulta: str, *, sesgo_region: str = "us") -> list[Lugar]:
    """Busca por texto. Devuelve candidatos SIN verificar.

    Igual que con los handles de Instagram: el primer resultado no es
    necesariamente la persona. La verificacion es de quien llama.
    """
    cuerpo = {
        "textQuery": consulta,
        "regionCode": sesgo_region.upper(),
        "maxResultCount": 5,
    }
    datos = _pedir(BASE_BUSQUEDA, cuerpo=cuerpo, campos=CAMPOS_BUSQUEDA)
    salida = []
    for p in datos.get("places", []):
        salida.append(Lugar(
            place_id=p.get("id", ""),
            nombre=(p.get("displayName") or {}).get("text"),
            direccion=p.get("formattedAddress"),
            rating=p.get("rating"),
            n_reviews_total=p.get("userRatingCount"),
            tipos=list(p.get("types") or []),
            web=p.get("websiteUri"),
        ))
    return salida


def detalle(place_id: str) -> Lugar:
    """Trae el detalle con hasta 5 reviews."""
    url = BASE_DETALLE % urlencode({"": place_id})[1:]
    datos = _pedir(url, campos=CAMPOS_DETALLE)
    return Lugar(
        place_id=datos.get("id", place_id),
        nombre=(datos.get("displayName") or {}).get("text"),
        direccion=datos.get("formattedAddress"),
        rating=datos.get("rating"),
        n_reviews_total=datos.get("userRatingCount"),
        tipos=list(datos.get("types") or []),
        web=datos.get("websiteUri"),
        telefono=datos.get("nationalPhoneNumber"),
        reviews=[Review.desde_api(r) for r in (datos.get("reviews") or [])],
    )


def buscar_agente(nombre: str, brokerage: str | None, ciudad: str | None,
                  estado: str | None) -> list[Lugar]:
    """Busca al agente. El brokerage y la ciudad desambiguan."""
    partes = [nombre]
    if brokerage:
        partes.append(brokerage)
    partes.append("real estate agent")
    if ciudad:
        partes.append(ciudad)
    if estado:
        partes.append(estado)
    return buscar(" ".join(partes))


def buscar_oficina(brokerage: str, ciudad: str | None, estado: str | None
                   ) -> list[Lugar]:
    """La oficina suele tener muchas mas reviews que el agente individual.

    Son reviews de la oficina, no de la persona: sirven para el contexto de
    friccion y para el idioma de los clientes del lugar, **no** para atribuirle
    una queja a un agente concreto.
    """
    partes = [brokerage]
    if ciudad:
        partes.append(ciudad)
    if estado:
        partes.append(estado)
    return buscar(" ".join(partes))
