"""Cliente del data browser de HMDA (CFPB). Gratis, nacional, sin ToS hostil.

Para que
--------
El fallout %, el score medio, el LTV y el ingreso por condado salen del registro
publico de HMDA. **Es literalmente lo que Model Match vende como Market
Signals**, y Model Match caduca con la prueba mientras HMDA no.

Si eso sirve para todos los condados donde opera la division, se construye una
vez y se hereda, igual que la capa geografica. El uso mas rentable de la prueba
de Model Match es usarla como verdad de referencia para validar esta fuente
libre. Ver modelmatch/calibracion.py.

La trampa del denominador, que es TODO el asunto
------------------------------------------------
`action_taken` tiene ocho valores y **uno de ellos no es una solicitud**:

    1  Loan originated
    2  Application approved but not accepted
    3  Application denied
    4  Application withdrawn by applicant
    5  File closed for incompleteness
    6  Purchased loan            <-- NO es una solicitud
    7  Preapproval request denied
    8  Preapproval request approved but not accepted

El 6 es un prestamo comprado en el mercado secundario: la solicitud la tomo
otra institucion y ya esta contada en su propio registro. Meterlo en el
denominador infla el total y baja el fallout. En Harris County 2023 son 17.266
registros de 125.863, o sea 13,7% del archivo.

Medido el 2026-09-21, Harris County TX (48201), año 2023, **sin filtros de
universo**:

    originadas (1)                 55.607
    aprobadas no aceptadas (2)      3.456
    negadas (3)                    24.652
    retiradas (4)                  18.692
    cerradas por incompletas (5)    5.895
    compradas (6)                  17.266   <-- excluidas
    preaprob. negadas (7)             119
    preaprob. no aceptadas (8)        176

    fallout = 52.990 / 108.597 = 48,8%

Ese 48,8% **no** es comparable con el ~22% que muestra Model Match. La
diferencia casi seguro es el universo: MM filtra. El filtro estandar del oficio
es compra de vivienda, 1-4 unidades site-built, una unidad, primer lien. Cual
usa exactamente MM es una pregunta empirica, y responderla es el paso 3 del
Bloque 5.

Por eso `Fallout` lleva su filtro adentro y `__str__` lo imprime: **un fallout
sin su universo declarado no se puede citar a un realtor.**
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://ffiec.cfpb.gov/v2/data-browser-api/view"
CACHE = Path(__file__).resolve().parent / "cache"

USER_AGENT = "ml_prospector/1.0 (prospeccion B2B; +https://github.com/icano-simo)"

#: Pausa minima entre llamadas. El endpoint esta detras de Akamai y devuelve
#: 403 "Access Denied" ante rafagas -- comprobado el 2026-09-21: la segunda
#: llamada consecutiva ya vino bloqueada. No es un problema de permisos.
PAUSA_MINIMA = 2.5
BACKOFF = (15, 60, 180)

# ── Semantica de action_taken ────────────────────────────────────────────────

ORIGINADA = "1"
#: Las seis acciones que cuentan como solicitud caida.
CAIDAS = ("2", "3", "4", "5", "7", "8")
#: Prestamo comprado en el secundario. NO es una solicitud: nunca al denominador.
COMPRADA = "6"

ETIQUETAS_ACCION = {
    "1": "originada",
    "2": "aprobada no aceptada",
    "3": "negada",
    "4": "retirada por el solicitante",
    "5": "cerrada por incompleta",
    "6": "comprada en el secundario (NO es solicitud)",
    "7": "preaprobacion negada",
    "8": "preaprobacion aprobada no aceptada",
}

ETIQUETAS_TIPO = {
    "1": "Conventional",
    "2": "FHA",
    "3": "VA",
    "4": "USDA",
}

#: El filtro de universo estandar del oficio: compra de vivienda, unifamiliar
#: site-built, una unidad, primer lien. Es el que hay que usar para comparar
#: con cualquier proveedor, y el que hay que declarar al citar una cifra.
FILTRO_COMPRA_ESTANDAR: dict[str, str] = {
    "loan_purposes": "1",
    "dwelling_categories": "Single Family (1-4 Units):Site-Built",
    "total_units": "1",
    "lien_statuses": "1",
}

#: Sin filtro. Sirve para ver el archivo completo, no para citar nada.
SIN_FILTRO: dict[str, str] = {}


class HmdaNoDisponible(RuntimeError):
    """No se pudo obtener el dato. No se devuelve un valor plausible."""


# ── Transporte ────────────────────────────────────────────────────────────────

_ultima_llamada = [0.0]


def _clave_cache(ruta: str, params: dict) -> Path:
    firma = urlencode(sorted(params.items()))
    seguro = "".join(c if c.isalnum() or c in "-_=&." else "_" for c in firma)
    return CACHE / ruta.replace("/", "_") / (seguro[:180] + ".json")


def _pedir(ruta: str, params: dict, *, usar_cache: bool = True) -> dict:
    cache = _clave_cache(ruta, params)
    if usar_cache and cache.exists():
        with cache.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    url = "%s/%s?%s" % (BASE, ruta, urlencode(params, doseq=True))

    for intento in range(len(BACKOFF) + 1):
        espera = PAUSA_MINIMA - (time.time() - _ultima_llamada[0])
        if espera > 0:
            time.sleep(espera)
        _ultima_llamada[0] = time.time()

        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=120) as respuesta:  # noqa: S310 - URL fija
                datos = json.loads(respuesta.read().decode("utf-8"))
            cache.parent.mkdir(parents=True, exist_ok=True)
            with cache.open("w", encoding="utf-8") as fh:
                json.dump(datos, fh)
            return datos

        except HTTPError as exc:
            if exc.code in (403, 429, 503) and intento < len(BACKOFF):
                pausa = BACKOFF[intento] * random.uniform(0.9, 1.3)
                time.sleep(pausa)
                continue
            raise HmdaNoDisponible(
                "HMDA devolvio HTTP %d para %s.%s"
                % (exc.code, url,
                   " El 403 detras de Akamai es limite de tasa, no permisos: "
                   "subi PAUSA_MINIMA y reintenta mas tarde."
                   if exc.code == 403 else "")
            ) from exc
        except (URLError, json.JSONDecodeError) as exc:
            if intento < len(BACKOFF):
                time.sleep(BACKOFF[intento])
                continue
            raise HmdaNoDisponible("no pude leer %s: %s" % (url, exc)) from exc

    raise HmdaNoDisponible("agotados los reintentos para %s" % url)


def agregar(
    *,
    anio: int,
    dimension: str,
    valores: str,
    condado: str | None = None,
    estado: str | None = None,
    tract: str | None = None,
    filtro_universo: dict[str, str] | None = None,
    usar_cache: bool = True,
) -> dict[str, dict]:
    """Agregacion de HMDA. Devuelve {valor de la dimension: {count, sum}}.

    `dimension` es el nombre del parametro que se desglosa, por ejemplo
    "actions_taken" o "loan_types". `valores` son los que se piden.
    """
    if not any((condado, estado, tract)):
        raise ValueError("hace falta condado, estado o tract")

    params: dict[str, str] = {"years": str(anio), dimension: valores}
    if condado:
        params["counties"] = condado
    if estado:
        params["states"] = estado
    if tract:
        params["tracts"] = tract
    params.update(filtro_universo or {})

    datos = _pedir("aggregations", params, usar_cache=usar_cache)
    clave = dimension
    salida: dict[str, dict] = {}
    for fila in datos.get("aggregations", []):
        etiqueta = str(fila.get(clave.rstrip("s"), fila.get(clave, "")))
        salida[etiqueta] = {
            "count": int(fila.get("count") or 0),
            "sum": float(fila.get("sum") or 0.0),
        }
    if not salida:
        raise HmdaNoDisponible(
            "HMDA respondio sin agregaciones para %s. Parametros: %s"
            % (condado or estado or tract, params)
        )
    return salida


# ── Fallout ───────────────────────────────────────────────────────────────────

@dataclass
class Fallout:
    """Fallout con su universo declarado. No se puede imprimir sin el.

    `filtro` no es metadato: es lo que hace comparable o incomparable esta
    cifra con la de cualquier proveedor. Un fallout sin universo declarado no
    se cita a un realtor.
    """

    geografia: str
    nivel: str
    anio: int
    filtro: dict[str, str]
    por_accion: dict[str, int] = field(default_factory=dict)

    @property
    def originadas(self) -> int:
        return self.por_accion.get(ORIGINADA, 0)

    @property
    def caidas(self) -> int:
        return sum(self.por_accion.get(k, 0) for k in CAIDAS)

    @property
    def compradas_excluidas(self) -> int:
        """Accion 6. Se reporta para que se vea que se excluyo."""
        return self.por_accion.get(COMPRADA, 0)

    @property
    def denominador(self) -> int:
        """Solicitudes. Sin los prestamos comprados."""
        return self.originadas + self.caidas

    @property
    def pct(self) -> float | None:
        return None if self.denominador == 0 else self.caidas / self.denominador

    def desglose(self) -> dict[str, tuple[int, str]]:
        return {
            k: (v, ETIQUETAS_ACCION.get(k, "?"))
            for k, v in sorted(self.por_accion.items())
        }

    def __str__(self) -> str:
        if self.pct is None:
            return "%s %d: [sin dato: denominador 0]" % (self.geografia, self.anio)
        universo = (
            ", ".join("%s=%s" % kv for kv in sorted(self.filtro.items()))
            if self.filtro else "SIN FILTRO DE UNIVERSO"
        )
        return (
            "%s (%s) %d · fallout %.1f%% (%d/%d) · %d compradas excluidas · "
            "universo: %s"
            % (self.geografia, self.nivel, self.anio, self.pct * 100,
               self.caidas, self.denominador, self.compradas_excluidas, universo)
        )


def fallout(
    *,
    anio: int,
    condado: str | None = None,
    estado: str | None = None,
    tract: str | None = None,
    filtro_universo: dict[str, str] | None = None,
    usar_cache: bool = True,
) -> Fallout:
    """Fallout de un condado, estado o tract.

    Por omision NO aplica filtro de universo, y `__str__` lo dice. Para
    comparar con un proveedor hay que pasar `FILTRO_COMPRA_ESTANDAR`.
    """
    # Se piden las ocho acciones, incluida la 6, para poder reportar cuantas se
    # excluyeron. Ocultar la exclusion seria el mismo error que ocultar un
    # denominador.
    agregado = agregar(
        anio=anio, dimension="actions_taken", valores="1,2,3,4,5,6,7,8",
        condado=condado, estado=estado, tract=tract,
        filtro_universo=filtro_universo, usar_cache=usar_cache,
    )
    geo = condado or estado or tract or "?"
    nivel = "condado" if condado else ("estado" if estado else "tract")
    return Fallout(
        geografia=geo, nivel=nivel, anio=anio,
        filtro=dict(filtro_universo or {}),
        por_accion={k: v["count"] for k, v in agregado.items()},
    )


# ── Mix de programa ───────────────────────────────────────────────────────────

@dataclass
class MixDeMercado:
    """Cuota FHA/VA/USDA/Convencional del MERCADO, no de un agente.

    Es un dato de mercado, no del cliente: no toca ninguna caracteristica
    protegida. Sirve como contexto para leer el mix de un agente y como proxy
    E3 -- techo de intensidad 1, nunca mas -- de exposicion a nicho.
    """

    geografia: str
    nivel: str
    anio: int
    filtro: dict[str, str]
    por_tipo: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.por_tipo.values())

    def pct(self, tipo: str) -> str:
        """Porcentaje con denominador, siempre."""
        if self.total == 0:
            return "[sin dato: 0/0]"
        n = self.por_tipo.get(tipo, 0)
        return "%.1f%% (%d/%d)" % (n / self.total * 100, n, self.total)

    @property
    def fha_pct(self) -> float | None:
        return None if self.total == 0 else self.por_tipo.get("2", 0) / self.total

    def __str__(self) -> str:
        universo = (
            ", ".join("%s=%s" % kv for kv in sorted(self.filtro.items()))
            if self.filtro else "SIN FILTRO DE UNIVERSO"
        )
        partes = ["%s %s" % (ETIQUETAS_TIPO.get(k, k), self.pct(k))
                  for k in sorted(self.por_tipo)]
        return "%s (%s) %d · %s · universo: %s" % (
            self.geografia, self.nivel, self.anio, " · ".join(partes), universo,
        )


def mix_de_mercado(
    *,
    anio: int,
    condado: str | None = None,
    estado: str | None = None,
    tract: str | None = None,
    filtro_universo: dict[str, str] | None = None,
    solo_originadas: bool = True,
    usar_cache: bool = True,
) -> MixDeMercado:
    """Mix de tipo de prestamo del mercado.

    `solo_originadas` en True cuenta solo las operaciones que se cerraron, que
    es lo comparable con el mix de un agente. En False cuenta solicitudes, que
    es otra cosa: mezclarlas es el error de grano de siempre.
    """
    filtro = dict(filtro_universo or {})
    if solo_originadas:
        filtro["actions_taken"] = "1"

    agregado = agregar(
        anio=anio, dimension="loan_types", valores="1,2,3,4",
        condado=condado, estado=estado, tract=tract,
        filtro_universo=filtro, usar_cache=usar_cache,
    )
    geo = condado or estado or tract or "?"
    nivel = "condado" if condado else ("estado" if estado else "tract")
    return MixDeMercado(
        geografia=geo, nivel=nivel, anio=anio,
        filtro=dict(filtro_universo or {}),
        por_tipo={k: v["count"] for k, v in agregado.items()},
    )
