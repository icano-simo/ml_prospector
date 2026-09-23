"""Captura por CAJAS: el condado lo define la caja, no la posición.

El problema de la caja única
----------------------------
`etiquetar_por_posicion` exige exactamente `1 + N` bloques de Market Insight,
uno por condado del Overview. Model Match a veces muestra 5 condados en el
Overview y solo 3 en Market Insight -- y entonces la captura se rechazaba
ENTERA. Un dato que falta hacía perder los cuatro que sí estaban.

Y el condado salía de la posición del bloque, así que pegar los bloques en otro
orden etiquetaba mal cada mercado sin que nada fallara. La biblioteca de
geografías guardaba las métricas de Solano bajo Alameda.

Aquí cada caja llega con su etiqueta puesta desde la pantalla. Una caja vacía
es un dato -- «Model Match no muestra este condado»-- y no un error.

Funciones puras, sin IO.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Lo que puede pasarle a una caja. Son TRES estados, no dos: «se pegó y no se
#: pudo leer» no es lo mismo que «no se pegó nada», y ninguno de los dos es
#: «está vacío porque Model Match no lo muestra».
LEIDO = "leido"
VACIO_DECLARADO = "vacio_declarado"
SIN_PEGAR = "sin_pegar"
NO_SE_PUDO_LEER = "no_se_pudo_leer"

ESTADOS_DE_CAJA = (LEIDO, VACIO_DECLARADO, SIN_PEGAR, NO_SE_PUDO_LEER)

#: `Set Location` del bloque, que es como Model Match dice de qué geografía es.
_RE_SET_LOCATION = re.compile(
    r"Set Location[:\s]*([A-Za-zÁÉÍÓÚÑáéíóúñ.\-' ]{2,60}?)"
    r"(?:\s+County|\s+Parish|\s*,|\s*\n|$)", re.I)


@dataclass
class Caja:
    """Una caja de la pantalla, con su etiqueta puesta desde ahí."""

    clave: str
    #: `estado`, `condado`, `overview`, `originators` o `lenders`.
    tipo: str
    etiqueta: str | None = None
    texto: str = ""
    #: La casilla «Model Match no muestra esto para este agente».
    vacio_declarado: bool = False
    estado: str = SIN_PEGAR
    aviso: str | None = None
    metricas: int | None = None
    detalle: dict = field(default_factory=dict)

    def a_dict(self) -> dict:
        return {"clave": self.clave, "tipo": self.tipo,
                "etiqueta": self.etiqueta, "estado": self.estado,
                "vacio_declarado": self.vacio_declarado,
                "aviso": self.aviso, "metricas": self.metricas,
                "caracteres": len(self.texto or "")}


def set_location_de(texto: str) -> str | None:
    """La geografía que el propio bloque declara, si la trae."""
    m = _RE_SET_LOCATION.search(texto or "")
    if not m:
        return None
    v = m.group(1).strip(" .,-'")
    return v or None


def _normalizar(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower()) \
        .replace(" county", "").replace(" parish", "").replace(" borough", "")


def control_suave(etiqueta: str | None, texto: str) -> str | None:
    """¿El texto pegado parece de OTRA geografía? Avisa, no bloquea.

    Model Match no siempre trae `Set Location`, y cuando lo trae el nombre
    puede venir de mil formas. Bloquear con una señal así rechazaría capturas
    buenas -- y la captura que se rechaza es la que no se repite.

    Avisar cuesta nada y atrapa el error que de verdad pasa: pegar el bloque de
    Alameda en la caja de Solano.
    """
    if not etiqueta or not texto:
        return None
    declarado = set_location_de(texto)
    if not declarado:
        return None
    if _normalizar(declarado) == _normalizar(etiqueta):
        return None
    return ("¿Pegaste %s en la caja de %s? El bloque dice «Set Location: %s»."
            % (declarado, etiqueta, declarado))


def cajas_desde(payload: dict) -> list[Caja]:
    """El payload de la pantalla -> las cajas, con su estado resuelto.

    `payload['cajas']` es una lista de dicts con `clave`, `tipo`, `etiqueta`,
    `texto` y `vacio_declarado`. El orden NO significa nada: la etiqueta manda.
    """
    salida: list[Caja] = []
    for i, c in enumerate(payload.get("cajas") or []):
        texto = str(c.get("texto") or "")
        caja = Caja(
            clave=str(c.get("clave") or "caja_%d" % i),
            tipo=str(c.get("tipo") or "condado"),
            etiqueta=(c.get("etiqueta") or None),
            texto=texto,
            vacio_declarado=bool(c.get("vacio_declarado")))

        if texto.strip():
            caja.estado = LEIDO
            caja.aviso = control_suave(caja.etiqueta, texto)
            # Una caja con texto Y la casilla marcada es una contradicción del
            # usuario. Gana el texto -- hay dato-- y se avisa.
            if caja.vacio_declarado:
                caja.vacio_declarado = False
                caja.aviso = ("marcaste «no muestra nada» pero pegaste texto: "
                              "se guarda el texto")
        elif caja.vacio_declarado:
            caja.estado = VACIO_DECLARADO
        else:
            caja.estado = SIN_PEGAR
        salida.append(caja)
    return salida


def condados_sin_market_insight(condados: list[str],
                                cajas: list[Caja]) -> list[str]:
    """Los condados del Overview que no tienen caja con texto.

    Se guardan como «no disponible» y **no bloquean la captura**: que Model
    Match no muestre Market Insight de un condado es un hecho de Model Match,
    no un error de quien captura.
    """
    con_texto = {_normalizar(c.etiqueta) for c in cajas
                 if c.tipo == "condado" and c.estado == LEIDO}
    return [c for c in condados if _normalizar(c) not in con_texto]


def resumen_de_cajas(cajas: list[Caja]) -> dict:
    """Una línea por caja, con uno de los tres estados. Es lo que se muestra."""
    por_estado: dict = {}
    for c in cajas:
        por_estado[c.estado] = por_estado.get(c.estado, 0) + 1
    return {
        "cajas": [c.a_dict() for c in cajas],
        "por_estado": por_estado,
        "avisos": [c.aviso for c in cajas if c.aviso],
        # Lo que hay que volver a mirar: una caja sin pegar y sin casilla es la
        # única que de verdad falta.
        "faltan": [c.etiqueta or c.clave for c in cajas
                   if c.estado == SIN_PEGAR],
    }
