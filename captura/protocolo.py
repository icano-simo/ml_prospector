"""El protocolo de captura de Model Match: orden, etiquetado y validacion.

La decision que hace esto util HOY
----------------------------------
La prueba de Model Match vence el 1 de octubre. **El crudo se guarda siempre y
el parser viene despues.** Es la misma arquitectura que probamos con Instagram:
si el parser falla se arregla y se re-parsea gratis; si no se capturo, no hay
nada que arreglar y la prueba ya venció.

Asi que esta pantalla no necesita un parser que funcione para servir. Necesita:

  1 · guardar el texto pegado, integro
  2 · etiquetarlo bien -- que bloque es que geografia
  3 · validar el conteo antes de guardar nada

Lo tercero es lo unico que no se puede arreglar despues: **etiquetar mal un
condado contamina la biblioteca y el error es invisible.** Un volumen de Alameda
guardado como Solano no se ve raro en ninguna consulta.

El problema del desplegable, y por que el orden lo resuelve
----------------------------------------------------------
El valor de `Set Location` vive en un `<select>` y Ctrl+A no lo copia, asi que
el texto pegado NO dice de que geografia es. No hace falta que lo diga: el orden
de captura es fijo y la posicion lo determina.

  bloque 1 de Market Signals  -> el estado
  bloque 2 en adelante        -> los condados, en el orden de la tabla del
                                 Overview

De ahi sale la validacion obligatoria: **los bloques de Market Signals tienen
que ser 1 + numero de condados.** Si no cuadra, no se guarda nada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Las secciones del protocolo, en el orden en que se pegan.
SECCIONES = ("overview", "market_signals", "originators", "lenders")


class ProtocoloInvalido(ValueError):
    """El conteo no cuadra. No se guarda nada."""


@dataclass
class Bloque:
    """Un pegado, con la geografia que le asigna su POSICION."""

    seccion: str
    orden: int
    texto: str
    nivel: str | None = None          # 'estado' | 'condado' | None
    etiqueta: str | None = None       # el nombre, del Overview


@dataclass
class Captura:
    """Una sesion de captura completa, ya etiquetada y validada."""

    realtor: str | None
    estado: str | None
    condados: list[str] = field(default_factory=list)
    bloques: list[Bloque] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    @property
    def market_signals(self) -> list[Bloque]:
        return [b for b in self.bloques if b.seccion == "market_signals"]


# ── Los condados del Overview ────────────────────────────────────────────────
#
# La tabla de condados aparece con "View Counties" activado. Cada fila trae el
# nombre y las unidades. El orden de esa tabla es el orden de captura.

_RE_FILA_CONDADO = re.compile(
    r"^\s*([A-Z][A-Za-z.\-' ]{2,40}?)\s*(?:County)?\s*[,\t|]?\s*([A-Z]{2})?\s*[\t|]\s*(\d+)\s*$",
    re.MULTILINE,
)


def condados_del_overview(texto: str) -> list[tuple[str, int]]:
    """(nombre, unidades) en el ORDEN de la tabla. No se ordena ni se agrupa.

    El orden es dato, no presentacion: es lo que despues etiqueta cada bloque
    de Market Signals.
    """
    salida: list[tuple[str, int]] = []
    for m in _RE_FILA_CONDADO.finditer(texto or ""):
        nombre = m.group(1).strip()
        if nombre.lower() in ("total", "county", "counties", "units"):
            continue
        salida.append((nombre, int(m.group(3))))
    return salida


def etiquetar_por_posicion(
    bloques_ms: list[str], condados: list[str]
) -> list[Bloque]:
    """El bloque 1 es el estado; del 2 en adelante, los condados en orden.

    Falla ANTES de tocar nada si el conteo no cuadra.
    """
    esperados = 1 + len(condados)
    if len(bloques_ms) != esperados:
        raise ProtocoloInvalido(
            "Se esperaban %d bloques de Market Signals (1 del estado + %d "
            "condados del Overview) y llegaron %d.\n"
            "\n"
            "No se guarda nada. Etiquetar mal un condado contamina la "
            "biblioteca de mercados y el error es invisible despues: un volumen "
            "de un condado guardado como otro no se ve raro en ninguna "
            "consulta.\n"
            "\n"
            "Condados del Overview, en orden: %s"
            % (esperados, len(condados), len(bloques_ms),
               ", ".join(condados) or "(ninguno)")
        )

    salida = [Bloque("market_signals", 0, bloques_ms[0], nivel="estado")]
    for i, (texto, nombre) in enumerate(zip(bloques_ms[1:], condados), start=1):
        salida.append(Bloque("market_signals", i, texto,
                             nivel="condado", etiqueta=nombre))
    return salida


def armar_captura(
    *,
    overview: str,
    market_signals: list[str],
    originators: str | None = None,
    lenders: str | None = None,
    realtor: str | None = None,
    estado: str | None = None,
) -> Captura:
    """Valida el protocolo y devuelve la captura etiquetada.

    Levanta `ProtocoloInvalido` antes de que nada llegue a la base.
    """
    filas = condados_del_overview(overview)
    nombres = [n for n, _ in filas]

    cap = Captura(realtor=realtor, estado=estado, condados=nombres)
    cap.bloques.append(Bloque("overview", 0, overview))
    cap.bloques.extend(etiquetar_por_posicion(market_signals, nombres))

    if originators:
        cap.bloques.append(Bloque("originators", 0, originators))
    else:
        cap.advertencias.append(
            "sin bloque de Originators: no se va a poder detectar si sus "
            "originadores son de Everett Financial, que es la exclusion dura"
        )
    if lenders:
        cap.bloques.append(Bloque("lenders", 0, lenders))
    else:
        cap.advertencias.append("sin bloque de Lenders")

    if not nombres:
        cap.advertencias.append(
            "el Overview no trajo tabla de condados: revisar que 'View "
            "Counties' estuviera activado"
        )
    return cap
