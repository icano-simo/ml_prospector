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
    #: La llave. Sin alguna, la captura de perfil no se puede pegar a nadie
    #: despues -- y la restriccion de la base lo impide.
    mmi_agent_id: str | None = None
    sf_lead_id: str | None = None
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

def condados_del_overview(texto: str) -> list[tuple[str, int]]:
    """(nombre, unidades) en el ORDEN de la tabla. No se ordena ni se agrupa.

    El orden es dato, no presentacion: es lo que despues etiqueta cada bloque
    de Market Signals.

    Delega en `parser_mm._condados`, que tiene el patron calibrado contra el
    volcado real. Habia dos patrones -- uno aca y otro alla-- y el de aca
    devolvia cero condados contra el texto de verdad. Dos copias del mismo
    patron es como quedo el bug del alt-text.
    """
    from captura.parser_mm import _condados

    return [(c["nombre"], c["unidades"]) for c in _condados(texto or "")]


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


# ══════════════════════════════════════════════════════════════════════════════
# UNA SOLA CAJA · el texto ya trae los cortes
# ══════════════════════════════════════════════════════════════════════════════
#
# Siete pegados por realtor son siete oportunidades de poner algo en la caja
# equivocada, y sobre 25 capturas son 175. El volcado trae marcadores que
# delimitan cada seccion, asi que los cortes los encuentra el parser.
#
# Los marcadores, verificados contra el volcado real de Armando Ochoa:
#
#   `Market Signals` seguido de `Set Location`   abre cada bloque de mercado
#   `Originators this agent has worked with`     cierra la serie y abre orig.
#   `Lenders this agent has worked with`         abre lenders
#
# Lo que va antes del primer `Market Signals` + `Set Location` es el Overview.

#: `Market Signals` solo no sirve: aparece tambien en la barra de pestañas de
#: TODAS las secciones. Lo que abre un bloque de verdad es la pareja con
#: `Set Location`, que solo esta en la pestaña de mercado.
_RE_ABRE_MERCADO = re.compile(
    r"^[ \t]*Market Signals[ \t]*\r?\n[ \t]*Set Location[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)
_RE_ABRE_ORIGINADORES = re.compile(
    r"^[ \t]*Originators this agent has worked with", re.MULTILINE | re.IGNORECASE)
_RE_ABRE_LENDERS = re.compile(
    r"^[ \t]*Lenders this agent has worked with", re.MULTILINE | re.IGNORECASE)


def separar_volcado(texto: str) -> dict:
    """Un volcado completo -> sus secciones. Sin pegar nada a mano.

    Devuelve {overview, market_signals: [...], originators, lenders}.

    Levanta `ProtocoloInvalido` si falta el cierre de la serie de mercados: sin
    `Originators this agent has worked with` no se sabe donde termina el ultimo
    bloque, y un ultimo bloque que se come el resto del texto es un error que
    nadie ve -- las metricas salen, solo que del sitio equivocado.
    """
    txt = (texto or "").replace("\r\n", "\n").replace("\r", "\n")

    aperturas = [m.start() for m in _RE_ABRE_MERCADO.finditer(txt)]
    if not aperturas:
        raise ProtocoloInvalido(
            "No encontre ningun bloque de Market Signals.\n"
            "\n"
            "Cada uno empieza con la linea `Market Signals` seguida de "
            "`Set Location`. Si copiaste solo el Overview, falta pegar los "
            "mercados; si copiaste con otra herramienta, puede que se hayan "
            "perdido los saltos de linea."
        )

    cierre = _RE_ABRE_ORIGINADORES.search(txt)
    if not cierre:
        raise ProtocoloInvalido(
            "Falta la seccion `Originators this agent has worked with`.\n"
            "\n"
            "Sin ella la serie de mercados no tiene cierre y no se puede saber "
            "donde termina el ultimo bloque: se comeria todo el texto que "
            "viene despues, y las metricas saldrian igual pero del sitio "
            "equivocado.\n"
            "\n"
            "No se guarda nada. Pega tambien la pestaña Originators, con el "
            "filtro Buyer."
        )
    if cierre.start() < aperturas[0]:
        raise ProtocoloInvalido(
            "La seccion de Originators aparece ANTES del primer bloque de "
            "Market Signals. El orden de captura es Overview, mercados, "
            "Originators, Lenders."
        )

    lenders = _RE_ABRE_LENDERS.search(txt, cierre.end())

    bloques: list[str] = []
    for i, inicio in enumerate(aperturas):
        fin = aperturas[i + 1] if i + 1 < len(aperturas) else cierre.start()
        bloques.append(txt[inicio:fin].strip())

    fin_orig = lenders.start() if lenders else len(txt)
    return {
        "overview": txt[:aperturas[0]].strip(),
        "market_signals": bloques,
        "originators": txt[cierre.start():fin_orig].strip(),
        "lenders": txt[lenders.start():].strip() if lenders else "",
    }


def armar_captura(
    *,
    overview: str,
    market_signals: list[str],
    originators: str | None = None,
    lenders: str | None = None,
    realtor: str | None = None,
    estado: str | None = None,
    mmi_agent_id: str | None = None,
    sf_lead_id: str | None = None,
) -> Captura:
    """Valida el protocolo y devuelve la captura etiquetada.

    Levanta `ProtocoloInvalido` antes de que nada llegue a la base.
    """
    if not (mmi_agent_id or sf_lead_id):
        raise ProtocoloInvalido(
            "Falta la llave: hace falta el MMI Agent ID o el Lead ID de "
            "Salesforce.\n"
            "\n"
            "Sin una llave, esta captura no se puede pegar a ningun realtor "
            "despues. El nombre no es llave: hay dos ANDREA SAAVEDRA en el "
            "libro y el cruce por nombre ya nos dio 301 filas sobre 300.\n"
            "\n"
            "El MMI Agent ID esta en el propio perfil de Model Match."
        )

    filas = condados_del_overview(overview)
    nombres = [n for n, _ in filas]

    cap = Captura(realtor=realtor, estado=estado, condados=nombres,
                  mmi_agent_id=mmi_agent_id, sf_lead_id=sf_lead_id)
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
