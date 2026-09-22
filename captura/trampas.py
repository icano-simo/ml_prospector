"""Las trampas verificadas de Model Match, como reglas ejecutables.

Cada una salio de comparar capturas reales, no de leer la interfaz. Viven aca
separadas del parser porque son la parte que NO se puede re-derivar: si el
parser lee del lugar equivocado, el numero sale plausible y nadie lo revisa.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class TrampaDetectada(AssertionError):
    """Un valor salio del lugar equivocado. No se guarda."""


# ══════════════════════════════════════════════════════════════════════════════
# 1 · Rolling Monthly Performance NO respeta el filtro de ubicacion
# ══════════════════════════════════════════════════════════════════════════════
#
# Medido: muestra $578,70B en las CUATRO capturas del caso de prueba, aunque
# Total Loan Volume baje de $578,7B (California) a $6,0B (Solano).
#
# O sea que leer el volumen del grafico rodante da el numero del estado para
# todos los condados, y el error es invisible: el numero existe, tiene formato
# de dolares y es del orden correcto.
#
# La regla: **Total Loan Volume y Total Units se leen de Market Overview, nunca
# del grafico rodante.**

SECCION_VOLUMEN = "Market Overview"
SECCION_PROHIBIDA_VOLUMEN = "Rolling Monthly Performance"


def verificar_volumenes_distintos(volumenes: list[float], geografias: list[str]) -> None:
    """Cuatro capturas de distinta geografia tienen que dar cuatro volumenes.

    Es la prueba obligatoria del brief. Si salen iguales, el parser esta
    leyendo del grafico rodante.
    """
    if len(volumenes) < 2:
        return
    unicos = len({round(v, 4) for v in volumenes})
    if unicos == 1:
        raise TrampaDetectada(
            "Las %d geografias (%s) dieron el MISMO volumen: %s.\n"
            "Eso es Rolling Monthly Performance, que no respeta el filtro de "
            "ubicacion. Total Loan Volume se lee de la seccion '%s'."
            % (len(volumenes), ", ".join(geografias), volumenes[0],
               SECCION_VOLUMEN)
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2 · Conforming vs Jumbo tiene DENOMINADOR PROPIO
# ══════════════════════════════════════════════════════════════════════════════
#
# Medido: 1.096.337 unidades totales, pero 613,2K en conforming/jumbo. El
# porcentaje de jumbo NO es sobre el total del mercado.

@dataclass
class MixConforming:
    """El par conforming/jumbo, con SU denominador y no el del mercado."""

    conforming: float | None
    jumbo: float | None
    denominador_propio: float | None
    unidades_del_mercado: float | None

    def porcentaje_jumbo(self) -> str:
        if self.jumbo is None or not self.denominador_propio:
            return "[sin dato]"
        pct = 100.0 * self.jumbo / self.denominador_propio
        return "%.1f%% (%s de %s en conforming/jumbo)" % (
            pct, _miles(self.jumbo), _miles(self.denominador_propio))

    def verificar(self) -> None:
        if (self.denominador_propio and self.unidades_del_mercado
                and self.denominador_propio > self.unidades_del_mercado):
            raise TrampaDetectada(
                "el denominador de conforming/jumbo (%s) es mayor que las "
                "unidades del mercado (%s): se leyeron cruzados"
                % (self.denominador_propio, self.unidades_del_mercado))


def _miles(v: float) -> str:
    return "{:,.0f}".format(v).replace(",", ".")


# ══════════════════════════════════════════════════════════════════════════════
# 3 · DOS definiciones de wallet share en el mismo perfil
# ══════════════════════════════════════════════════════════════════════════════
#
# Overview reparte por UNIDADES; la pestaña Originators por VOLUMEN. En el
# perfil de prueba: 50/25/25 contra 30,7/35,3/34,0.
#
# No se reconcilian ni se elige una: se guardan las dos, etiquetadas. Un wallet
# share sin decir su base no se puede interpretar.

@dataclass
class WalletShareCapturado:
    base: str          # 'unidades' | 'volumen'
    seccion: str       # de donde salio
    reparto: dict      # originador -> porcentaje

    def __post_init__(self) -> None:
        if self.base not in ("unidades", "volumen"):
            raise TrampaDetectada(
                "wallet share sin base declarada: %r. El Overview reparte por "
                "unidades y la pestaña Originators por volumen, y dan numeros "
                "distintos sobre el mismo perfil." % self.base)


# ══════════════════════════════════════════════════════════════════════════════
# 4 · Los conteos de cabecera NO coinciden entre si
# ══════════════════════════════════════════════════════════════════════════════
#
# Medido en el perfil de prueba: Side Focus dice 3 buy / 0 sell, Buyer Units
# dice 9, Listing Activity dice 3 Sold, y los condados suman 9.
#
# Se guardan los CUATRO por separado. Reconciliarlos inventa un numero que no
# esta en la fuente, y la discrepancia misma es informacion sobre que mide cada
# widget.

CONTEOS_DE_CABECERA = ("side_focus_buy", "side_focus_sell", "buyer_units",
                       "listing_sold", "suma_condados")


def verificar_no_reconciliado(conteos: dict) -> None:
    faltan = [c for c in CONTEOS_DE_CABECERA if c not in conteos]
    if faltan:
        raise TrampaDetectada(
            "faltan conteos de cabecera: %s. Los cuatro se guardan por "
            "separado; no coinciden entre si y esa discrepancia es informacion."
            % faltan)


# ══════════════════════════════════════════════════════════════════════════════
# 5 · La empresa del originador va en la linea ANTERIOR al nombre
# ══════════════════════════════════════════════════════════════════════════════
#
# Con el NMLS entre medias. Sin ese campo no se detecta que Everett Financial
# opera como Supreme Lending, que es la exclusion dura por no-canibalizacion.

_RE_NMLS = re.compile(r"NMLS\s*#?\s*(\d{4,9})", re.IGNORECASE)


def originadores_con_empresa(texto: str) -> list[dict]:
    """(empresa, nmls, nombre) leyendo hacia ATRAS desde el NMLS.

    El orden en el texto es: empresa, NMLS, nombre. Leer solo el nombre pierde
    la empresa, y sin empresa no hay exclusion.
    """
    lineas = [l.strip() for l in (texto or "").splitlines()]
    salida = []
    for i, linea in enumerate(lineas):
        m = _RE_NMLS.search(linea)
        if not m:
            continue
        empresa = lineas[i - 1] if i >= 1 else None
        nombre = lineas[i + 1] if i + 1 < len(lineas) else None
        salida.append({"empresa": empresa or None,
                       "nmls": m.group(1),
                       "nombre": nombre or None})
    return salida


#: Everett Financial opera como Supreme Lending, NMLS 2129.
NMLS_DE_LA_CASA = "2129"
NOMBRES_DE_LA_CASA = ("everett financial", "supreme lending")


def es_de_la_casa(originador: dict) -> bool:
    if originador.get("nmls") == NMLS_DE_LA_CASA:
        return True
    empresa = (originador.get("empresa") or "").lower()
    return any(n in empresa for n in NOMBRES_DE_LA_CASA)


# ══════════════════════════════════════════════════════════════════════════════
# 6 · Produccion: solo el lado comprador, y nunca se pisa el lote
# ══════════════════════════════════════════════════════════════════════════════

def anualizado_buyside(buy_units: float, ventana_meses: float) -> float:
    """buy_units / ventana * 12. **No suma el lado vendedor.**

    El lado vendedor se guarda igual, porque dice si se dedica mas a una cosa
    que a la otra -- pero no entra en la produccion hipotecaria.
    """
    if ventana_meses <= 0:
        raise TrampaDetectada("ventana de %r meses" % ventana_meses)
    return buy_units / ventana_meses * 12.0


def verificar_no_pisa_el_lote(campo_destino: str) -> None:
    """`unidades_ano` del lote NO se sobrescribe con el de Model Match.

    Se guardan los dos, con su fecha y su ventana. Son mediciones distintas de
    cosas parecidas y la diferencia entre ellas es informacion.
    """
    if campo_destino == "unidades_ano":
        raise TrampaDetectada(
            "Model Match no escribe en `unidades_ano`: ese es el del lote. La "
            "produccion de MM va en su propia columna, con su ventana y su "
            "fecha de captura.")
