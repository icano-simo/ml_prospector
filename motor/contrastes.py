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

#: Cuanto tiene que separarse el agente de su mercado para que el contraste
#: ACTIVE algo. Sin esto, `activa` solo miraba las guardias de base: un agente
#: con 16,1% de FHA contra un condado de 16,0% activaba igual que uno con
#: 66,7%, y el copy decia «mas que su zona» sobre una decima.
#:
#: 1,5 y no 1,1: entre 1,1 y 1,5 la diferencia existe pero no sostiene una
#: afirmacion sobre la cartera de alguien, y este motor solo afirma cuando
#: puede. Por debajo de 1/1,5 = 0,67 vale al reves, que es igual de accionable
#: --hace FHA muy por debajo de su zona-- y se lee distinto.
UMBRAL_CONTRASTE = 1.5


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

    @property
    def hay_dos_lados(self) -> bool:
        """Los dos valores presentes y NINGUNO en cero.

        Un 0 no es un dato menor: es el divisor que hace que `veces` no exista,
        y del lado del agente es la ausencia de la practica, no su medida. Con
        un lado en cero no hay contraste que leer, ni a favor ni en contra.
        """
        return bool(self.valor_agente and self.valor_mercado)

    @property
    def direccion(self) -> str:
        """`por_encima`, `por_debajo`, `en_linea` o `sin_contraste`.

        Es lo que elige la plantilla. Antes la direccion se reconstruia en cada
        sitio que queria redactar, y `leer_mix_fha` tenia una sola plantilla que
        decia «mas que su zona» tambien cuando era menos.
        """
        if not self.hay_dos_lados:
            return "sin_contraste"
        v = self.veces
        if v is None:
            return "sin_contraste"
        if v >= UMBRAL_CONTRASTE:
            return "por_encima"
        if v <= 1.0 / UMBRAL_CONTRASTE:
            return "por_debajo"
        return "en_linea"

    def leer(self) -> str:
        """La lectura en palabras. Nunca el ratio pelado."""
        if not self.hay_dos_lados:
            cual = ("del agente" if not self.valor_agente else "del mercado")
            return ("%s · sin dato %s: no hay contraste de un lado"
                    % (self.geografia, cual))
        v = self.veces
        # «en linea con» SOLO cuando hay dos lados de verdad. Antes caia aqui
        # tambien el caso de un lado en 0, que es justo el que no se puede leer.
        relacion = {"por_encima": "%s veces" % _coma(v),
                    "por_debajo": "%s veces" % _coma(v),
                    "en_linea": "en linea con"}[self.direccion]
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
        c = Contraste(
            metrica="mix " + tipo.upper(),
            geografia=m.get("etiqueta") or m.get("estado") or "?",
            nivel=m.get("nivel") or "?",
            valor_agente=valor_agente,
            valor_mercado=(m.get("metricas") or {}).get(clave),
            base_agente=identificadas,
            base_agente_descripcion=(
                "%s operaciones con tipo identificado sobre %s del lado "
                "comprador" % (identificadas, mix.get("buyer_units"))),
            activa=False,
            motivo=motivo,
            guardias=list(guardias),
        )
        # `activa` exige TRES cosas, y las guardias de base eran solo una:
        #   1 · las guardias de PACS-H (10 operaciones, 50% de cobertura)
        #   2 · los dos lados con valor, ninguno en cero
        #   3 · separacion de al menos UMBRAL_CONTRASTE en cualquier direccion
        # Sin la 3, un agente en 16,1% contra un condado en 16,0% activaba, y
        # el copy afirmaba sobre una decima.
        propias = list(guardias)
        if not c.hay_dos_lados:
            propias.append(
                "falta el valor %s: sin los dos lados no hay contraste"
                % ("del agente" if not c.valor_agente else
                   "del mercado en " + c.geografia))
        elif c.direccion == "en_linea":
            propias.append(
                "%s contra %s%% del mercado es %s veces: por debajo de %s no "
                "sostiene una afirmacion"
                % (_coma(c.valor_agente), _coma(c.valor_mercado),
                   _coma(c.veces), _coma(UMBRAL_CONTRASTE)))
        c.activa = not propias
        c.guardias = propias
        c.motivo = "; ".join(propias)
        salida.append(c)
    return salida
