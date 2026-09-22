"""Contrastes: el agente contra SU mercado, no contra una constante.

De numero a lectura
-------------------
`FHA 66,7%` no dice nada solo. `FHA 66,7% contra 16,0% del condado donde opera`
es una lectura, y `contra 3,2% en el condado de al lado` es otra distinta sobre
el MISMO agente. Por eso el contraste se calcula por geografia y no una vez.

Las guardias mandan sobre la lectura
------------------------------------
Un contraste se puede CALCULAR y aun asi no poder ACTIVAR nada. El mix de
programa necesita 10 operaciones con tipo identificado y 50% de cobertura del
lado comprador; por debajo de eso el numero existe y no significa.

Devolver el ratio sin su veredicto seria ofrecer un 21x para que alguien lo
cite. `Contraste.activa` es lo que decide, y `motivo` dice por que no.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Las guardias de PACS-H para el mix de programa.
MIN_OPERACIONES_IDENTIFICADAS = 10
MIN_COBERTURA_PCT = 50.0


@dataclass
class Contraste:
    """Un agente contra una geografia, con todo lo que lo hace interpretable."""

    metrica: str
    geografia: str
    nivel: str
    valor_agente: float | None
    valor_mercado: float | None
    #: El denominador del lado del agente. Sin el no hay lectura.
    base_agente: float | None = None
    base_agente_descripcion: str = ""
    activa: bool = False
    motivo: str = ""
    guardias: list[str] = field(default_factory=list)

    @property
    def veces(self) -> float | None:
        if not self.valor_mercado or self.valor_agente is None:
            return None
        return round(self.valor_agente / self.valor_mercado, 1)

    def leer(self) -> str:
        """La lectura en palabras. Nunca el ratio pelado."""
        if self.valor_agente is None or self.valor_mercado is None:
            return "%s · sin dato de un lado: no hay contraste" % self.geografia
        v = self.veces
        relacion = ("%s veces" % _coma(v) if v and v >= 1.1
                    else "%s veces" % _coma(v) if v and v <= 0.9
                    else "en linea con")
        texto = ("%s: %s%% del agente contra %s%% del mercado — %s"
                 % (self.geografia, _coma(self.valor_agente),
                    _coma(self.valor_mercado), relacion))
        if not self.activa:
            texto += "  [NO ACTIVA: %s]" % self.motivo
        return texto


def _coma(v) -> str:
    return ("%g" % round(v, 1)).replace(".", ",")


def mix_de_programa(loan_mix: dict, mercados: list[dict], *,
                    tipo: str = "FHA") -> list[Contraste]:
    """El mix del agente contra el de cada mercado donde opera.

    `loan_mix` es `perfil['loan_mix_buyer']`, que ya trae su denominador:
    `unidades_identificadas` y `cobertura`. Las guardias se evaluan UNA vez --
    son del agente, no de la geografia-- y se copian a cada contraste, para que
    ninguno se pueda leer sin su veredicto.
    """
    mix = loan_mix or {}
    filas = mix.get("filas") or []
    identificadas = mix.get("unidades_identificadas")
    cobertura = mix.get("cobertura")

    fila = next((f for f in filas
                 if (f.get("tipo") or "").upper().startswith(tipo.upper())),
                None)
    valor_agente = fila.get("share") if fila else None

    guardias, motivo = [], ""
    if identificadas is None or identificadas < MIN_OPERACIONES_IDENTIFICADAS:
        guardias.append(
            "operaciones con tipo identificado: %s, hacen falta %d"
            % (identificadas if identificadas is not None else "sin dato",
               MIN_OPERACIONES_IDENTIFICADAS))
    if cobertura is None or cobertura < MIN_COBERTURA_PCT:
        guardias.append(
            "cobertura del lado comprador: %s%%, hace falta %g%%"
            % (_coma(cobertura) if cobertura is not None else "sin dato",
               MIN_COBERTURA_PCT))
    if guardias:
        motivo = "; ".join(guardias)

    clave = "mkt_" + tipo.lower()
    salida = []
    for m in mercados:
        salida.append(Contraste(
            metrica="mix " + tipo.upper(),
            geografia=m.get("etiqueta") or m.get("estado") or "?",
            nivel=m.get("nivel") or "?",
            valor_agente=valor_agente,
            valor_mercado=(m.get("metricas") or {}).get(clave),
            base_agente=identificadas,
            base_agente_descripcion=(
                "%s operaciones con tipo identificado sobre %s del lado "
                "comprador" % (identificadas, mix.get("buyer_units"))),
            activa=not guardias,
            motivo=motivo,
            guardias=list(guardias),
        ))
    return salida
