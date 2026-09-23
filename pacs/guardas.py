"""Las reglas de guardia de la metodologia PACS-H, como codigo que falla.

Estan escritas como funciones y asserts a proposito. Cada una de estas reglas
existe porque ya se violo una vez y el costo no fue el error sino no verlo:

- un porcentaje sin denominador llevo a leer "Top 3 Concentration 100%" como
  concentracion de wallet share, cuando significaba que solo tres de catorce
  operaciones tenian lender identificado;
- un mix de programa calculado sobre 3 operaciones se uso para activar un
  qualifier que la matriz exige sostener con 10;
- una señal ausente rellenada con False convirtio 1.075 perfiles sin datos de
  Instagram en 1.075 perfiles que "no hablaban español";
- un wallet share calculado sobre un agente listside presento como "su lender
  de confianza" a quien financio a los compradores de sus listados.

Las cuatro son silenciosas. Ninguna levanta una excepcion por su cuenta. Por eso
estan aca.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Literal

# ── Umbrales ──────────────────────────────────────────────────────────────────

#: Minimo de operaciones con tipo de prestamo identificado para que el mix de
#: programa pueda activar o desactivar un qualifier.
MIN_OPS_TIPO_IDENTIFICADO = 10

#: Minima fraccion del lado comprador con tipo identificado para lo mismo.
MIN_FRACCION_BUYSIDE_IDENTIFICADO = 0.50

#: Techo de intensidad por grado de evidencia (referencia 05 de la skill).
#: E1 admite 3 solo por excepcion declarada; el techo operativo es 2.
TECHO_POR_GRADO: dict[str, int] = {"E0": 3, "E1": 2, "E2": 2, "E3": 1}

GradoEvidencia = Literal["E0", "E1", "E2", "E3"]
Medicion = Literal["medida", "estimada"]
BaseWallet = Literal["unidades", "volumen"]


class ViolacionDeGuarda(AssertionError):
    """Se violo una regla de guardia. Es un error, no una advertencia."""


# ── 1 · Ningun porcentaje sin su denominador ──────────────────────────────────

def porcentaje(numerador: float, denominador: float, decimales: int = 1) -> str:
    """Formatea un porcentaje SIEMPRE con su denominador.

    No hay forma de obtener de esta funcion un porcentaje pelado. Es deliberado:
    la version con y sin denominador conviviendo es como se cuela la primera.

    >>> porcentaje(3, 14)
    '21.4% (3/14)'
    >>> porcentaje(0, 0)
    '[sin dato: 0/0]'
    """
    if denominador is None or numerador is None:
        return "[sin dato]"
    if denominador == 0:
        return "[sin dato: 0/0]"
    if numerador > denominador:
        raise ViolacionDeGuarda(
            "numerador %s mayor que denominador %s: el grano esta mal. Los dos "
            "proveedores mezclan ventanas de tiempo en el mismo archivo sin "
            "etiquetarlas." % (numerador, denominador)
        )
    pct = numerador / denominador * 100
    return "%.*f%% (%g/%g)" % (decimales, pct, numerador, denominador)


# ── 2 · Toda señal ausente es null, nunca False ───────────────────────────────

@dataclass(frozen=True)
class Senal:
    """Una señal con su mascara de disponibilidad.

    `valor` en None significa "no se midio". No significa False. La diferencia
    la cobra el que lea la salida creyendo que un cero es un cero.
    """

    valor: bool | float | str | None
    disponible: bool
    motivo_si_falta: str | None = None

    def __post_init__(self) -> None:
        if self.disponible and self.valor is None:
            raise ViolacionDeGuarda(
                "señal marcada disponible pero con valor None: elegi una."
            )
        if not self.disponible and self.valor is not None:
            raise ViolacionDeGuarda(
                "señal marcada no disponible pero trae valor %r: si se midio, "
                "esta disponible." % (self.valor,)
            )
        if not self.disponible and not self.motivo_si_falta:
            raise ViolacionDeGuarda(
                "señal ausente sin motivo. 'No se pudo' es un dato: perfil "
                "privado, handle no verificado y no encontrado son tres cosas "
                "distintas y el motor necesita saber cual."
            )

    @classmethod
    def medida(cls, valor: bool | float | str) -> "Senal":
        return cls(valor=valor, disponible=True)

    @classmethod
    def falta(cls, motivo: str) -> "Senal":
        return cls(valor=None, disponible=False, motivo_si_falta=motivo)

    def __bool__(self) -> bool:
        raise ViolacionDeGuarda(
            "no uses una Senal en un if directamente: `if senal:` trata lo "
            "ausente como falso, que es el error que esta clase existe para "
            "impedir. Usa `senal.es_positiva()` o `senal.disponible`."
        )

    def es_positiva(self) -> bool:
        """True solo si se midio Y es verdadera. Ausente no es positiva."""
        return self.disponible and self.valor is True

    def es_negativa(self) -> bool:
        """True solo si se midio Y es falsa. Ausente NO es negativa."""
        return self.disponible and self.valor is False


def mascara_de_disponibilidad(senales: dict[str, Senal]) -> dict[str, bool]:
    """El reporte de lote de una fila: que se pudo acreditar y que no."""
    return {nombre: s.disponible for nombre, s in senales.items()}


# ── 3 · El mix de programa necesita piso de evidencia ─────────────────────────

@dataclass(frozen=True)
class MixDePrograma:
    """Mix FHA/VA/Convencional con su propio juicio sobre si se puede usar."""

    ops_con_tipo: int
    ops_total: int
    buyside_con_tipo: int
    buyside_total: int
    conteos: dict[str, int]

    @property
    def utilizable(self) -> bool:
        """Puede activar o desactivar un qualifier."""
        if self.ops_con_tipo < MIN_OPS_TIPO_IDENTIFICADO:
            return False
        if self.buyside_total <= 0:
            return False
        frac = self.buyside_con_tipo / self.buyside_total
        return frac >= MIN_FRACCION_BUYSIDE_IDENTIFICADO

    @property
    def etiqueta_insuficiencia(self) -> str | None:
        if self.utilizable:
            return None
        return "[insuficiente: %d de %d]" % (self.ops_con_tipo, self.ops_total)

    def pct(self, tipo: str) -> str:
        """Porcentaje de un tipo, con denominador, o la etiqueta de insuficiencia."""
        if not self.utilizable:
            return self.etiqueta_insuficiencia or "[insuficiente]"
        return porcentaje(self.conteos.get(tipo, 0), self.ops_con_tipo)

    def puede_descartar_por_cero_fha(self) -> bool:
        """El caso verificado: cero FHA en 29 operaciones saco a alguien del ICP.

        Con 3 de 14 identificadas, cero FHA no significa nada. Esta funcion es
        la que evita repetir esa lectura.
        """
        return self.utilizable and self.conteos.get("FHA", 0) == 0


# ── 4 · El wallet share solo sobre buyside, y etiquetado ──────────────────────

@dataclass(frozen=True)
class WalletShare:
    """Share del lender principal. Solo tiene sentido sobre el lado comprador.

    En un agente listside, el lender que aparece NO es su socio: es quien
    financio a los compradores de sus listados, que los trajo otro agente. Abrir
    con angulo de complemento sobre ese dato deja en ridiculo a quien lo usa.
    """

    lender: str
    share: float
    base: BaseWallet
    ops_buyside_identificadas: int
    ops_buyside_total: int
    es_libro_buyside: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.share <= 1.0:
            raise ViolacionDeGuarda(
                "share %r fuera de [0,1]: probablemente venga en porcentaje." % self.share
            )
        if self.base not in ("unidades", "volumen"):
            raise ViolacionDeGuarda(
                "el wallet share tiene que declarar su base. Model Match "
                "reporta las dos en el mismo perfil con numeros distintos: "
                "33/33/33 por unidades en Overview contra 40,6/35,3/24,0 por "
                "volumen en la pestaña Originators."
            )

    @property
    def interpretable(self) -> bool:
        return self.es_libro_buyside and self.ops_buyside_identificadas > 0

    def lectura(self) -> str:
        if not self.es_libro_buyside:
            return (
                "NO INTERPRETABLE: libro listside. %s financio a los compradores "
                "de sus listados, no es su socio. No abrir con angulo de "
                "complemento sobre este dato." % self.lender
            )
        if self.ops_buyside_identificadas == 0:
            return "NO INTERPRETABLE: cero operaciones buyside con lender identificado."

        cobertura = porcentaje(self.ops_buyside_identificadas, self.ops_buyside_total)
        detalle = "%s, %.1f%% por %s, sobre %s del lado comprador" % (
            self.lender, self.share * 100, self.base, cobertura,
        )
        if self.share >= 0.60:
            return "LENDER CAUTIVO (%s). Angulo obligado: complemento, jamas sustitucion." % detalle
        if self.share >= 0.35:
            return "RELACION DOMINANTE PERO NO EXCLUSIVA (%s). Complemento con espacio real." % detalle
        return "LIBRO FRAGMENTADO (%s). Sin socio establecido: el premio es grande." % detalle


# ── 5 · Toda cifra lleva fuente, fecha y si es medida o estimada ──────────────

@dataclass(frozen=True)
class Cifra:
    """Un numero que puede responder "¿de donde sale esto?"."""

    valor: float | int | str
    fuente: str
    fecha: _dt.date
    medicion: Medicion
    ventana: str | None = None

    def __post_init__(self) -> None:
        if not self.fuente or not str(self.fuente).strip():
            raise ViolacionDeGuarda(
                "cifra sin fuente. Si no podes decir de donde salio, no va."
            )
        if self.medicion not in ("medida", "estimada"):
            raise ViolacionDeGuarda(
                "cifra sin declarar si es medida o estimada. La caida invernal "
                "esta MODELADA en 23 de 34 estados y DOCUMENTADA en 11: citar "
                "una modelada como dura ya paso una vez."
            )

    def __str__(self) -> str:
        partes = ["%s" % self.valor, "(%s" % self.fuente, self.fecha.isoformat()]
        if self.ventana:
            partes.append("ventana %s" % self.ventana)
        partes.append("%s)" % self.medicion)
        return " · ".join(partes[:2]) + " · " + " · ".join(partes[2:])


# ── 6 · El techo de intensidad por grado de evidencia ─────────────────────────

def intensidad_con_techo(
    intensidad_propuesta: int,
    grado: GradoEvidencia,
    *,
    excepcion_e1_declarada: str | None = None,
) -> tuple[int, str | None]:
    """Aplica el techo. Devuelve (intensidad final, nota si se recorto).

    E3 nunca pasa de 1. E2 nunca pasa de 2. Solo E0 llega a 3. E1 llega a 3
    unicamente con una excepcion escrita, que queda en la nota.
    """
    if grado not in TECHO_POR_GRADO:
        raise ViolacionDeGuarda("grado de evidencia desconocido: %r" % grado)
    if not 0 <= intensidad_propuesta <= 3:
        raise ViolacionDeGuarda(
            "intensidad %r fuera de 0-3" % intensidad_propuesta
        )

    techo = TECHO_POR_GRADO[grado]
    if grado == "E1" and intensidad_propuesta == 3 and excepcion_e1_declarada:
        return 3, "E1 a intensidad 3 por excepcion declarada: %s" % excepcion_e1_declarada

    if intensidad_propuesta <= techo:
        return intensidad_propuesta, None

    return techo, (
        "recortada de %d a %d: evidencia %s no sostiene mas."
        % (intensidad_propuesta, techo, grado)
    )


def acto_de_habla(intensidad: int, grado: GradoEvidencia) -> Literal["AFIRMA", "PREGUNTA"]:
    """Con evidencia fuerte el copy afirma; con evidencia debil pregunta.

    AFIRMA solo con intensidad 3 y evidencia E0, que es texto propio de la
    persona. Todo lo demas pregunta. No se baja el tono: se cambia el verbo.
    """
    return "AFIRMA" if (intensidad == 3 and grado == "E0") else "PREGUNTA"


# ── 7 · Ninguna inferencia desde apellido, etnia u origen ─────────────────────

#: Nombres de campo que no pueden alimentar ninguna inferencia de nicho, idioma
#: o mercado. La lista es para que un revisor pueda hacer grep, y para el
#: assert de abajo.
CAMPOS_PROHIBIDOS_PARA_INFERENCIA = frozenset({
    "apellido", "last_name", "surname",
    "etnia", "ethnicity", "race",
    "origen", "origen_nacional", "national_origin",
    "nombre_de_pila", "first_name", "given_name",
})


#: Trozos que descalifican un nombre de campo aunque no sea exacto.
#: `hispanic_surname_score` no esta en el conjunto de arriba y pasaba entero.
TROZOS_PROHIBIDOS = ("surname", "apellido", "etnia", "ethnic", "race",
                     "national_origin", "origen_nacional")

#: Campos cuya PROCEDENCIA es una base prohibida, se llamen como se llamen.
#:
#: Este registro existe porque el de arriba no alcanza, y se sabe desde un caso
#: concreto: `R7_identidad_hispana` se calcula desde el apellido y el nombre de
#: pila -- base censal de apellidos con >=75% de portadores hispanos, mas una
#: lista de nombres-- y **ninguna** de las dos listas de nombres lo atrapa. No
#: contiene «apellido», ni «surname», ni «etnia». Esta nombrado por lo que dice
#: medir, no por lo que lo calcula.
#:
#: Ahi esta el limite de cualquier guarda sobre la etiqueta: la etiqueta es
#: justamente el unico lugar donde la procedencia prohibida no tiene por que
#: aparecer. Un campo entra aca por lo que se sabe de su ORIGEN, una vez, y deja
#: de depender de que alguien lo haya nombrado con honestidad.
#:
#: Ver `docs/r7-identidad-hispana.md` para el detalle y el alcance medido.
CAMPOS_DE_PROCEDENCIA_PROHIBIDA = {
    "r7_identidad_hispana": (
        "se calcula desde el apellido y el nombre de pila (base censal de "
        "apellidos hispanos + heuristica patronimica -ez/-es/-az/-iz/-oz); "
        "el libro lo define como «probabilidad de que el realtor pertenezca a "
        "la comunidad latina». Ver docs/r7-identidad-hispana.md"),
}


def verificar_entradas_de_inferencia(campos_usados: set[str], qualifier: str) -> None:
    """Falla si una regla de inferencia se apoya en un campo prohibido.

    Inferir nicho desde el origen del agente es discriminacion bajo ECOA
    Regulation B. Aplica al realtor, a sus clientes y a los loan officers.

    Mira TRES cosas, y las tres hacen falta:
      1 · el nombre exacto  (`apellido`, `surname`, …)
      2 · el nombre por trozos  (`hispanic_surname_score` pasaba entero)
      3 · la procedencia declarada  (`R7_identidad_hispana` no se parece a nada
          prohibido, y se calcula desde el apellido)
    """
    prohibidos = {c for c in campos_usados
                  if c.lower() in CAMPOS_PROHIBIDOS_PARA_INFERENCIA}
    prohibidos |= {c for c in campos_usados
                   if any(t in c.lower() for t in TROZOS_PROHIBIDOS)}
    if prohibidos:
        raise ViolacionDeGuarda(
            "el qualifier %s se apoya en %s. Inferir nicho, idioma o mercado "
            "desde apellido, etnia u origen es discriminacion bajo ECOA "
            "Regulation B. La señal legitima es transaccional: FHA, bandas de "
            "precio, geografia, LMI, y el idioma de lo que la persona publica."
            % (qualifier, sorted(prohibidos))
        )

    por_procedencia = {c: CAMPOS_DE_PROCEDENCIA_PROHIBIDA[c.lower()]
                       for c in campos_usados
                       if c.lower() in CAMPOS_DE_PROCEDENCIA_PROHIBIDA}
    if por_procedencia:
        raise ViolacionDeGuarda(
            "el qualifier %s se apoya en %s. El nombre del campo no lo dice, "
            "pero su procedencia si: %s. Que un campo no se llame «apellido» "
            "no cambia de donde sale."
            % (qualifier, sorted(por_procedencia),
               " · ".join(sorted(por_procedencia.values()))))


# ── 8 · Ninguna variable de tract clasifica a una persona ─────────────────────

def verificar_uso_de_tract(proposito: str) -> None:
    """Las variables demograficas de tract describen donde opera, no quien es.

    `proposito` tiene que ser uno de los usos permitidos. Es una barrera
    declarativa: obliga a escribir para que se usa antes de usarlo.
    """
    permitidos = {
        "describir_mercado",       # como es la zona donde opera
        "feature_relativa",        # su ZCTA sobre la mediana de su condado
        "plausibilidad_e3",        # techo de intensidad 1, nunca mas
        "cobertura_de_licencia",   # donde podemos originar
    }
    if proposito not in permitidos:
        raise ViolacionDeGuarda(
            "uso de variable de tract con proposito %r. Permitidos: %s. "
            "Una variable demografica de tract describe donde opera una "
            "persona, no quien es." % (proposito, sorted(permitidos))
        )
