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


# ── 3-bis · Y para la EXCLUSION se decide por UNIDADES ───────────────────────
#
# Guardar las dos bases no dice cual usar, y la exclusion por no-canibalizacion
# necesita UNA. Se decide por unidades: lo que importa es cuantas operaciones
# pasan por un colega, no cuantos dolares.
#
# El caso que hace que la eleccion cambie el resultado es Chris Ruiz en el
# perfil de prueba: **50,0% por unidades y 30,7% por volumen**. Con un umbral en
# 40% el mismo originador entra o no entra segun que base se use, y las dos
# lecturas salen del mismo perfil sin que nada avise.
#
# Que las dos bases discrepen no es raro: un originador con pocas operaciones
# grandes pesa mas por volumen, y uno con muchas operaciones chicas pesa mas por
# unidades. La relacion con el realtor se construye por operacion.

BASE_PARA_EXCLUSION = "unidades"

#: De donde sale cada base en el perfil parseado.
SECCION_POR_BASE = {
    "unidades": "orig_buyer",   # Buyer Side Relationships, del Overview
    "volumen": "tab_orig",      # la pestaña Originators
}


#: Bases con las que la exclusion puede trabajar. `indistinguible` entra porque
#: con una sola relacion las dos bases dan 100%: la eleccion no cambia nada.
BASES_ACEPTADAS = (BASE_PARA_EXCLUSION, "indistinguible")


def wallet_share_para_exclusion(perfil: dict) -> list[dict]:
    """El reparto que decide la exclusion: el de UNIDADES.

    Lee `orig_buyer` y no `tab_orig`, y **no cae al de volumen** si falta: un
    reparto con la otra base da un numero plausible con la definicion
    equivocada, que es exactamente el error que no se ve.

    Levanta `TrampaDetectada` en los dos casos en que devolver `[]` mentiria:

    1 · el perfil declara un fallo sobre `orig_buyer` -- la seccion estaba en el
        texto y no se parseo. Un `[]` ahi se lee como "no trabaja con nadie", y
        la exclusion no dispararia sobre alguien que si trabaja con la casa.
    2 · la base medida del reparto NO es unidades. Guardar las dos bases no
        sirve de nada si despues se usa la que toco.

    Y avisa cuando el perfil viene de UNA sola fila sin la seccion: `orig_buyer`
    vive en la del Overview, asi que preguntarle a la de Originators da vacio
    sin que nada falle. Para eso esta `parser_mm.unir_perfiles`.
    """
    for f in perfil.get("fallos") or []:
        if f.get("campo") == SECCION_POR_BASE[BASE_PARA_EXCLUSION]:
            raise TrampaDetectada(
                "el perfil declara que `%s` fallo: %s.\n"
                "No se puede decidir la exclusion por no-canibalizacion con "
                "esto. Un reparto vacio se lee como `no trabaja con la casa`, "
                "que es la conclusion contraria a `no lo pudimos leer`."
                % (f.get("campo"), f.get("detalle")))

    reparto = list(perfil.get(SECCION_POR_BASE[BASE_PARA_EXCLUSION]) or [])
    if not reparto:
        return []

    # `base_normalizada` porque las capturas guardadas antes traen un string
    # plano aca. Una etiqueta declarada no cuenta como medicion: entra como
    # `medida = None`, o sea "no se pudo medir", que es lo que era.
    from captura.parser_mm import base_normalizada

    base = base_normalizada(
        (perfil.get("wallet_share_base") or {})
        .get(SECCION_POR_BASE[BASE_PARA_EXCLUSION]))
    medida = base.get("medida")
    if medida is not None and medida not in BASES_ACEPTADAS:
        raise TrampaDetectada(
            "el reparto de `%s` NO reparte por %s: medido contra sus propias "
            "filas da %r.\n"
            "La exclusion se decide por unidades y este reparto no lo es, asi "
            "que usarlo daria un numero plausible con la definicion "
            "equivocada."
            % (SECCION_POR_BASE[BASE_PARA_EXCLUSION], BASE_PARA_EXCLUSION,
               medida))
    return reparto


def share_de_la_casa(perfil: dict) -> dict:
    """Cuanto del negocio comprador del realtor ya pasa por Everett/Supreme.

    Devuelve el share por unidades, las unidades que lo respaldan y **el
    denominador**, porque un porcentaje sobre 3 operaciones y uno sobre 40 se
    leen igual y no valen lo mismo.

    Sin reparto por unidades devuelve `share=None` con su razon: no se rellena
    con cero. Un cero aca dice "no trabaja con la casa", que es la conclusion
    contraria a "no lo pudimos mirar".
    """
    reparto = wallet_share_para_exclusion(perfil)
    if not reparto:
        return {"share": None, "unidades": None, "unidades_totales": None,
                "base": BASE_PARA_EXCLUSION,
                "razon": "este perfil no trajo Buyer Side Relationships, que "
                         "es la seccion que reparte por unidades. Si viene de "
                         "una sola fila de la captura, unir antes con "
                         "`parser_mm.unir_perfiles`: esa seccion vive en la "
                         "fila del Overview y no en la de Originators"}

    de_la_casa = [o for o in reparto if es_de_la_casa(o)]
    total = sum(o.get("unidades") or 0 for o in reparto)
    suyas = sum(o.get("unidades") or 0 for o in de_la_casa)
    return {
        "share": (round(100.0 * suyas / total, 1) if total else None),
        "unidades": suyas,
        "unidades_totales": total,
        "base": BASE_PARA_EXCLUSION,
        "originadores": [o.get("nombre") for o in de_la_casa],
        # El share declarado por la fuente, para contrastar con el calculado.
        "share_declarado": sum(o.get("share") or 0.0 for o in de_la_casa) or None,
    }


def verificar_base_de_exclusion(base: str) -> None:
    """Falla ruidosamente si alguien decide la exclusion por volumen."""
    if base != BASE_PARA_EXCLUSION:
        raise TrampaDetectada(
            "la exclusion por no-canibalizacion se decide por %s, no por %r.\n"
            "Chris Ruiz da 50,0%% por unidades y 30,7%% por volumen sobre el "
            "mismo perfil: la base cambia el resultado."
            % (BASE_PARA_EXCLUSION, base))


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
