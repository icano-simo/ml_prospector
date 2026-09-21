"""Esquema versionado de captura de Model Match.

Por que un esquema versionado y no "pega el texto y vemos"
----------------------------------------------------------
La prueba de Model Match caduca. Lo que se capture durante la prueba tiene que
seguir siendo legible despues, cuando ya no se pueda volver a mirar la pantalla
para desambiguar. Un archivo sin esquema declarado es ilegible a los tres meses.

Y hay una razon mas concreta: **los numeros se mueven dentro de la misma
sesion.** En dos pestañas consecutivas del mismo perfil, mismo rango de 14
meses, se leyo "7 buy / 21 sell · 15 total · 28 Sold" contra
"6 buy / 21 sell · 14 total · 27 Sold". Si la captura no lleva timestamp y
pestaña de origen, no hay forma de saber cual de las dos se esta mirando.

Nunca imagenes
--------------
Los numeros no sobreviven al OCR y una captura de pantalla no se puede versionar
ni comparar. Orden de preferencia: export nativo -> volcado del DOM a JSON con
el snippet de DevTools -> texto pegado en .txt con este esquema.

Nomenclatura de archivo
-----------------------
    {licencia}_{apellido}_{YYYYMMDD}.txt      perfil de agente
    condado_{FIPS}_{YYYYMMDD}.txt             benchmark de condado

El FIPS, no el nombre: hay 31 condados llamados Washington.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

ESQUEMA_VERSION = "mm-captura-v1"

#: Pestañas de las que puede venir un dato. Importa porque reportan numeros
#: distintos para la misma cosa.
Pestana = Literal[
    "overview",
    "originators",
    "lenders",
    "title_companies",
    "geography",
    "market_signals",
    "contacts",
    "export_nativo",
]

BaseDeShare = Literal["unidades", "volumen"]
Metodo = Literal["export_nativo", "dom_json", "texto_pegado"]


@dataclass(frozen=True)
class Procedencia:
    """De donde salio exactamente un bloque de numeros.

    `pestana` y `capturado_en` no son metadatos decorativos: son lo unico que
    permite reconciliar dos lecturas distintas del mismo perfil.
    """

    pestana: Pestana
    capturado_en: dt.datetime
    ventana_declarada: str
    metodo: Metodo
    url: str | None = None
    nota: str | None = None

    def clave(self) -> str:
        return "%s@%s" % (self.pestana, self.capturado_en.isoformat(timespec="seconds"))


@dataclass(frozen=True)
class ConteoDeLados:
    """buy / sell / total / sold, tal como los reporta UNA pestaña.

    Los cuatro numeros se guardan crudos y sin reconciliar. La reconciliacion la
    hace el parser y deja el conflicto en un log, porque un conflicto entre dos
    pestañas es informacion sobre la fuente, no ruido a promediar.
    """

    buy: int | None
    sell: int | None
    total: int | None
    sold: int | None
    procedencia: Procedencia

    @property
    def suma_lados(self) -> int | None:
        if self.buy is None or self.sell is None:
            return None
        return self.buy + self.sell

    @property
    def cuadra(self) -> bool | None:
        """`total` deberia ser buy+sell. Casi nunca lo es."""
        s = self.suma_lados
        if s is None or self.total is None:
            return None
        return s == self.total


@dataclass(frozen=True)
class WalletShareCapturado:
    """Un share de lender, con su base declarada y su pestaña de origen.

    Model Match reporta DOS definiciones de wallet share en el mismo perfil:
    la tarjeta de Overview muestra 33/33/33 (por unidades) y la pestaña
    Originators muestra 40,6/35,3/24,0 (por volumen). Las dos se capturan,
    etiquetadas. Ninguna es "la correcta".
    """

    lender: str
    share: float
    base: BaseDeShare
    lado: Literal["buyside", "listside", "ambos", "sin_declarar"]
    ops: int | None
    procedencia: Procedencia


@dataclass
class PerfilAgente:
    """Todo lo capturado de un agente. Caduca con la prueba."""

    esquema: str = ESQUEMA_VERSION
    licencia: str | None = None
    nmls_si_tiene: str | None = None
    apellido: str | None = None
    nombre: str | None = None

    # Los tres clasificadores de cabecera
    producer_tier: str | None = None
    side_focus: str | None = None
    referral_concentration: str | None = None   # es nuestro S6 precomputado

    conteos: list[ConteoDeLados] = field(default_factory=list)
    wallet_shares: list[WalletShareCapturado] = field(default_factory=list)
    originadores: list[dict] = field(default_factory=list)   # nombre + NMLS
    lenders: list[dict] = field(default_factory=list)
    title_companies: list[dict] = field(default_factory=list)
    condados: list[dict] = field(default_factory=list)       # FIPS + % + unidades

    #: Model Match entrega VARIOS emails y telefonos con porcentaje de
    #: confianza. Se guardan TODOS: el de nuestra lista puede coincidir con un
    #: secundario, y descartar los secundarios es perder el unico cruce posible.
    contactos: list[dict] = field(default_factory=list)

    #: Lo que el propio export declara que no trae.
    ausencias_declaradas: list[str] = field(default_factory=list)

    def conflictos_de_conteo(self) -> list[str]:
        """Discrepancias entre pestañas. Se reportan, no se promedian."""
        problemas: list[str] = []
        for campo in ("buy", "sell", "total", "sold"):
            vistos = {
                getattr(c, campo): c.procedencia.clave()
                for c in self.conteos
                if getattr(c, campo) is not None
            }
            if len(vistos) > 1:
                problemas.append(
                    "%s reportado con %d valores distintos: %s"
                    % (campo, len(vistos),
                       ", ".join("%s en %s" % (v, k) for v, k in vistos.items()))
                )
        for c in self.conteos:
            if c.cuadra is False:
                problemas.append(
                    "en %s, buy+sell=%s pero total=%s"
                    % (c.procedencia.clave(), c.suma_lados, c.total)
                )
        return problemas

    def es_prospecto(self) -> tuple[bool, str]:
        """Con NMLS propio origina el mismo: no es prospecto, es colega."""
        if self.nmls_si_tiene:
            return False, (
                "DESCARTADO: tiene NMLS propio (%s). Origina el mismo."
                % self.nmls_si_tiene
            )
        return True, ""


@dataclass
class BenchmarkCondado:
    """Los numeros de mercado de un condado. NO caducan con la prueba.

    Esto es el activo permanente del Bloque 5. Un perfil individual caduca; un
    benchmark de condado no cambia de semana a semana, sirve para todos los
    realtors de ese condado y sobrevive al vencimiento de la prueba.

    Dos de estos numeros resuelven deudas concretas de la metodologia:

    - `fallout_pct` convierte el argumento comercial de HOMESI en dato citable;
    - `dias_medios_al_cierre` elimina la promesa sin respaldo que hoy aparece
      en los borradores de copy.
    """

    esquema: str = ESQUEMA_VERSION
    fips: str | None = None            # 5 digitos: estado(2) + condado(3)
    nombre_condado: str | None = None
    estado: str | None = None

    fallout_pct: float | None = None
    fallout_denominador: int | None = None
    dias_medios_al_cierre: float | None = None

    #: {"FHA": 0.21, "VA": 0.06, "Conventional": 0.68, "USDA": 0.01, ...}
    mix_tipo_prestamo: dict[str, float] = field(default_factory=dict)
    mix_denominador: int | None = None

    #: {"<620": 0.04, "620-679": 0.13, ...}
    distribucion_score: dict[str, float] = field(default_factory=dict)

    #: {"primerizos": 0.38, "veteranos": 0.05, "self_employed": 0.11, ...}
    tipos_de_comprador: dict[str, float] = field(default_factory=dict)
    generacion: dict[str, float] = field(default_factory=dict)

    tasa_media: float | None = None
    ltv_medio: float | None = None
    ingreso_medio_hogar: float | None = None
    canal: dict[str, float] = field(default_factory=dict)
    tipo_de_lender: dict[str, float] = field(default_factory=dict)

    procedencia: Procedencia | None = None

    #: Loan officers nuestros con licencia activa en este condado. Es la razon
    #: por la que este condado esta en la lista de captura.
    los_activos: int | None = None

    def falta(self) -> list[str]:
        """Que campos quedaron vacios. Va al reporte, no se rellena."""
        faltantes = []
        if self.fallout_pct is None:
            faltantes.append("fallout_pct")
        if self.dias_medios_al_cierre is None:
            faltantes.append("dias_medios_al_cierre")
        if not self.mix_tipo_prestamo:
            faltantes.append("mix_tipo_prestamo")
        if self.mix_denominador is None and self.mix_tipo_prestamo:
            faltantes.append("mix_denominador (hay mix sin denominador)")
        return faltantes


# ── Plantilla de captura en texto ─────────────────────────────────────────────

PLANTILLA_PERFIL = """\
# esquema: {version}
# Rellena lo que la pantalla muestre. Lo que no este, se deja en [sin dato].
# NO completes de memoria y NO redondees. Si dos pestañas dicen distinto,
# pon las dos: hay una seccion para cada una.

licencia:
nmls_si_tiene:
apellido:
nombre:

producer_tier:
side_focus:
referral_concentration:

## overview  capturado_en: {ahora}  ventana:
buy:
sell:
total:
sold:
# wallet share de la tarjeta de Overview. Base: unidades.
ws_overview_1:
ws_overview_2:
ws_overview_3:

## originators  capturado_en:  ventana:
buy:
sell:
total:
sold:
# wallet share de la pestaña Originators. Base: volumen.
# Estos numeros NO coinciden con los de Overview y esta bien.
ws_originators_1:
ws_originators_2:
ws_originators_3:
# nombre|NMLS|ops|share  una por linea
originador:
originador:
originador:

## lenders  capturado_en:
# nombre|ops|share
lender:
lender:

## title_companies  capturado_en:
title:

## geography  capturado_en:
# FIPS|nombre|unidades|pct
condado:
condado:

## contacts  capturado_en:
# tipo|valor|confianza_pct     tipo = email | telefono
# GUARDA TODOS, tambien los de baja confianza: el de nuestra lista puede
# coincidir con un secundario.
contacto:
contacto:
contacto:

## ausencias_declaradas
# Lo que el propio export dice que no trae. Ej: "mix de programa de prestamo
# no existe a nivel de agente en Model Match".
ausencia:
"""

PLANTILLA_CONDADO = """\
# esquema: {version}
# Market Signals con Set Location bajado a CONDADO, no a estado.
# Este archivo NO caduca con la prueba. Es el activo permanente.

fips:
nombre_condado:
estado:
los_activos:

capturado_en: {ahora}
ventana_declarada:

fallout_pct:
fallout_denominador:
dias_medios_al_cierre:

# tipo|pct   una por linea
mix: FHA|
mix: VA|
mix: Conventional|
mix: USDA|
mix: Otro|
mix_denominador:

# rango|pct
score: <620|
score: 620-679|
score: 680-739|
score: 740+|

# tipo|pct
comprador: primerizos|
comprador: veteranos|
comprador: self_employed|

# generacion|pct
generacion:

tasa_media:
ltv_medio:
ingreso_medio_hogar:

# canal|pct  (retail, broker, correspondent...)
canal:
# tipo|pct  (bank, credit_union, independent...)
tipo_de_lender:
"""
