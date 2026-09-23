"""De numero a lectura.

El problema
-----------
`FHA 66,7% contra 16,0%, 4,2 veces` obliga al lector a interpretar, y esa
interpretacion es trabajo del sistema. Quien lo lee no sabe si eso es bueno o
malo, ni que hacer con ello.

Cada contraste devuelve TRES campos, no uno:

  que_dice_del_borrower   el agente es el intermediario; lo que importa es
                          quien es su cliente
  bueno_o_malo            explicito, nunca a interpretacion
  que_hacer               la frase que el BD puede usar, o la PREGUNTA que lo
                          confirma

La guardia manda sobre la lectura
---------------------------------
Un contraste que no activa **no afirma**. Su `que_hacer` es la pregunta que lo
confirmaria, y su `bueno_o_malo` es `neutro`. Escribir "es exactamente el
cliente que sabemos cerrar" sobre tres operaciones seria justo lo que las
guardias existen para impedir.

Vocabulario
-----------
El de un loan officer hispano en EE.UU.: español con los terminos tecnicos en
ingles -- down payment, closing costs, pre-approval, score, credit report, DTI.
Traducirlos suena a folleto y delata que no se conoce el oficio.
`PALABRAS_PROHIBIDAS` lo hace comprobable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from motor.contrastes import UMBRAL_CONTRASTE

# ── Los cinco veredictos, explicitos ────────────────────────────────────────
ES_NUESTRO_CLIENTE = "es nuestro cliente"
NO_ES_NUESTRO_CLIENTE = "no es nuestro cliente"
FRICCION_RESOLUBLE = "fricción que podemos resolver"
SENAL_DE_ALERTA = "señal de alerta"
NEUTRO = "neutro"

VEREDICTOS = (ES_NUESTRO_CLIENTE, NO_ES_NUESTRO_CLIENTE, FRICCION_RESOLUBLE,
              SENAL_DE_ALERTA, NEUTRO)

#: Los tecnicos van en ingles. Estos son sus equivalentes de manual, que es lo
#: que hay que no escribir.
#:
#: `enganche` y `banda baja de credito` los nombro el brief. El resto sale de
#: la misma regla -- "traducir terminos tecnicos al español de manual suena a
#: folleto"-- aplicada a los seis terminos que el brief manda dejar en ingles.
PALABRAS_PROHIBIDAS = {
    "enganche": "down payment",
    "pago inicial": "down payment",
    "cuota inicial": "down payment",
    "banda baja de crédito": "score entre 580 y 669",
    "banda baja de credito": "score entre 580 y 669",
    "puntaje de crédito": "score",
    "puntaje crediticio": "score",
    "costos de cierre": "closing costs",
    "gastos de cierre": "closing costs",
    "preaprobación": "pre-approval",
    "pre-aprobación": "pre-approval",
    "precalificación": "pre-approval",
    "informe de crédito": "credit report",
    "reporte de crédito": "credit report",
    "relación deuda-ingreso": "DTI",
    "relación deuda ingreso": "DTI",
}


class VocabularioInvalido(ValueError):
    """Una frase usa una palabra que delata que no se conoce el oficio."""


def verificar_vocabulario(texto: str) -> None:
    bajo = (texto or "").lower()
    for mala, buena in PALABRAS_PROHIBIDAS.items():
        if mala in bajo:
            raise VocabularioInvalido(
                "%r no se usa en el sector en EE.UU. Va %r.\n"
                "  en: %s" % (mala, buena, texto[:160]))


# ── Numeros en lenguaje hablado ─────────────────────────────────────────────

_FRACCIONES = {0.5: "medio", 0.25: "un cuarto", 0.75: "tres cuartos"}
_CARDINALES = {0: "cero", 1: "uno", 2: "dos", 3: "tres", 4: "cuatro",
               5: "cinco", 6: "seis", 7: "siete", 8: "ocho", 9: "nueve",
               10: "diez"}
_FEMENINOS = {**_CARDINALES, 1: "una"}


#: Lo que el redondeo a medios puede desviar, en puntos porcentuales.
#: Es el maximo estructural: medio decimo son 5 puntos, la mitad 2,5.
DESVIO_MAXIMO_PP = 2.5

#: Por debajo de esto el desvio absoluto sigue siendo chico pero el RELATIVO se
#: dispara, y el numero hablado deja de describir el dato.
MINIMO_HABLADO = 5.0


def de_cada_diez(pct: float | None, *, femenino: bool = False) -> str | None:
    """22,2% -> 'dos de cada diez'. 16,0% -> 'una y media de cada diez'.

    `cuatro de cada diez` antes que `40%`: se lee sin traducir.

    Redondea al MEDIO decimo mas cercano, asi que siempre hay forma hablada y
    el desvio no pasa de 2,5 puntos. La primera version dejaba huecos -- 22,2%
    y 66,7% caian entre bandas y devolvian None-- y un hueco en la capa de
    lectura se ve como un dato que falta, no como un redondeo que no se hizo.
    El numero exacto viaja siempre en `evidencia`.

    Por encima de 95% la forma hablada estorba, y **por debajo de 5% miente**:
    3,8% redondea a `medio de cada diez`, que son 5% -- 1,2 puntos de desvio
    absoluto pero un tercio de error relativo. Ahi se devuelve None y quien
    llama usa el porcentaje, que a esa escala es lo que se entiende.
    """
    if pct is None or pct < MINIMO_HABLADO or pct > 95:
        return None
    medios = round(pct / 5.0)          # al medio decimo mas cercano
    entero, mitad = divmod(medios, 2)
    tabla = _FEMENINOS if femenino else _CARDINALES

    if mitad and not entero:
        # `medio de cada diez` se entiende y suena torpe. Es el unico caso en
        # que la forma de veinte se lee mejor, y dice exactamente lo mismo.
        return "uno de cada veinte" if not femenino else "una de cada veinte"
    if mitad:
        media = "media" if femenino else "medio"
        palabra = "%s y %s" % (tabla[entero], media)
    else:
        palabra = tabla[entero]
    return "%s de cada diez" % palabra


# ── La lectura ──────────────────────────────────────────────────────────────

@dataclass
class Lectura:
    """Lo que el sistema interpreta, para que no lo interprete el lector."""

    que_dice_del_borrower: str
    bueno_o_malo: str
    que_hacer: str
    #: La evidencia detras, para `Como se calculo`.
    evidencia: str = ""
    #: True cuando la lectura AFIRMA; False cuando solo pregunta.
    afirma: bool = False
    #: Lo MISMO, dicho EN SEGUNDA PERSONA y para mandarselo a él.
    #:
    #: `que_dice_del_borrower` esta escrito para que lo lea un BD: habla de la
    #: persona en tercera persona y la nombra. El toque 4 lo pegaba tal cual en
    #: el cuerpo del email, asi que a Armando le llegaba «Armando trabaja con
    #: compradores que…». Y `que_hacer` es una instruccion PARA el BD --
    #: «Ofrecerle que el caso se origine…»-- que tampoco se le manda a nadie.
    #:
    #: Vacio significa que esta lectura no tiene forma de decirse a él. El
    #: toque 4 entonces NO la usa; no improvisa una.
    para_el_realtor: str = ""

    def __post_init__(self) -> None:
        if self.bueno_o_malo not in VEREDICTOS:
            raise ValueError(
                "veredicto %r no esta en la lista. Se elige de %s, nunca se "
                "deja a interpretacion." % (self.bueno_o_malo, VEREDICTOS))
        for campo in (self.que_dice_del_borrower, self.que_hacer):
            verificar_vocabulario(campo)
        if self.para_el_realtor:
            verificar_vocabulario(self.para_el_realtor)
        # Una lectura que AFIRMA tiene que poder decirsele. Si no, el toque 4
        # se queda sin material y cae a la pregunta -- que es correcto, pero
        # entonces afirmar no servia de nada.
        if self.afirma and not self.para_el_realtor:
            raise ValueError(
                "la lectura afirma pero no trae `para_el_realtor`: no hay "
                "forma de decirselo sin pegarle el texto interno")


def _hablado(pct, femenino=False):
    """La forma hablada si existe; si no, el porcentaje. Nunca las dos."""
    h = de_cada_diez(pct, femenino=femenino)
    return h or ("%s%%" % ("%g" % round(pct, 1)).replace(".", ","))


def leer_mix_fha(contraste, nombre_agente: str) -> Lectura:
    """El mix FHA del agente contra su mercado, en palabras.

    Habla del BORROWER, no del agente: el agente es el intermediario y lo que
    decide es quien es su cliente.
    """
    agente, mercado = contraste.valor_agente, contraste.valor_mercado
    donde = contraste.geografia

    if agente is None or mercado is None:
        return Lectura(
            que_dice_del_borrower=(
                "No sabemos que tipo de préstamo usan los compradores de %s."
                % nombre_agente),
            bueno_o_malo=NEUTRO,
            que_hacer=("Preguntarle con qué tipo de préstamo cierran la "
                       "mayoría de sus operaciones."),
            evidencia="falta el dato de un lado del contraste")

    suyo = _hablado(agente)
    delmercado = _hablado(mercado, femenino=True)

    # La frase «score entre 580 y 669» salio el 2026-09-23: NINGUN dato la
    # respalda. Del mix FHA se deduce el tipo de programa, no el score del
    # comprador -- que no esta en Model Match ni en ninguna fuente que tengamos.
    # Era una caracterizacion inventada del cliente de otra persona.
    cuerpo = (
        "%s trabaja con compradores que necesitan préstamos de gobierno mucho "
        "más que el resto de su zona. %s de sus operaciones son FHA, cuando en "
        "%s solo lo son %s. Es un comprador que suele entrar con menos down "
        "payment."
        % (nombre_agente, suyo.capitalize(), donde, delmercado))

    # La plantilla depende de la DIRECCION. Antes habia una sola y decia «mucho
    # más que el resto de su zona» tambien cuando el agente estaba por debajo:
    # un agente con 5% de FHA contra un condado con 16% leia igual que uno con
    # 66,7% contra 16%.
    if contraste.direccion == "por_debajo" and contraste.activa:
        return Lectura(
            que_dice_del_borrower=(
                "%s cierra con FHA bastante menos que su zona: %s de sus "
                "operaciones, cuando en %s son %s. Su comprador llega con más "
                "down payment, o no le están ofreciendo el programa."
                % (nombre_agente, suyo, donde, delmercado)),
            bueno_o_malo=NEUTRO,
            que_hacer=("Preguntarle si ve clientes que califican para FHA y "
                       "terminan yéndose. Si es lo segundo, ahí hay operaciones "
                       "que se están perdiendo."),
            evidencia="FHA del agente %s%% contra %s%% de %s · %s veces · base: %s"
                      % (agente, mercado, donde, contraste.veces,
                         contraste.base_agente_descripcion))

    if not contraste.activa:
        # La guardia manda: se describe lo que se ve y se pregunta, no se
        # concluye. Afirmar sobre tres operaciones es lo que las guardias
        # existen para impedir.
        hacia = {"por_encima": "más que la zona",
                 "por_debajo": "menos que la zona",
                 "en_linea": "parecido a la zona",
                 "sin_contraste": "sin con qué compararlo"}[contraste.direccion]
        return Lectura(
            que_dice_del_borrower=(
                "Lo que vemos apunta a compradores que usan préstamos de "
                "gobierno %s, pero no alcanza para afirmarlo: %s."
                % (hacia, contraste.motivo or
                   contraste.base_agente_descripcion)),
            bueno_o_malo=NEUTRO,
            que_hacer=("Preguntarle cuántas de sus operaciones del último año "
                       "cerraron con FHA. Si son varias, es exactamente el "
                       "cliente que sabemos cerrar."),
            evidencia="contraste calculado (%s veces) y NO activo: %s"
                      % (contraste.veces, contraste.motivo))

    return Lectura(
        que_dice_del_borrower=cuerpo + " Es exactamente el cliente que sabemos "
                                       "cerrar.",
        bueno_o_malo=ES_NUESTRO_CLIENTE,
        # «score desde 580» sale el 2026-09-23: es MUNICION --lo que decimos que
        # podemos hacer-- y la municion todavia no tiene version. Una cifra de
        # producto sin version es la que sigue circulando en los mensajes seis
        # meses despues de que el overlay cambio, y nadie se entera.
        que_hacer=("Abrir por el perfil del comprador: decirle que sostenemos "
                   "el pre-approval antes de que escriba la oferta."),
        evidencia="FHA del agente %s%% contra %s%% de %s · %s veces · base: %s"
                  % (agente, mercado, donde, contraste.veces,
                     contraste.base_agente_descripcion),
        afirma=True,
        para_el_realtor=(
            "%s de tus operaciones cierran con FHA, contra %s en %s. Es un "
            "comprador que suele entrar con menos down payment y al que le "
            "sostenemos el pre-approval antes de que escriba la oferta.\n\n"
            "¿Lo ves igual desde tu lado?"
            % (suyo.capitalize(), delmercado, donde)))


def leer_canal_tpo(tpo_agente: float | None, canal_mercado: dict | None,
                   nombre_agente: str, donde: str,
                   fallout_mercado: float | None = None,
                   originadores_de_la_casa: list | None = None) -> Lectura:
    """El canal del agente contra el del mercado.

    Un préstamo que sale de la casa que lo origina suma manos al expediente, y
    cada mano es un punto mas donde el caso se cae. Eso es friccion, no
    descarte: es justo lo que sabemos resolver.

    Tres cosas que esta funcion NO puede hacer, y antes hacia:

    1 · **Afirmar siempre.** Tenia `afirma=True` y `FRICCION_RESOLUBLE` fijos,
        asi que un TPO de 3% contra 45% mayorista --el agente MUY por debajo
        del mercado-- salia diciendo «sus originadores lo pasan a otro» igual
        que uno de 67% contra 12%.
    2 · **Leer sin los dos lados.** Un mayorista de mercado en 0 no es un
        mercado sin canal mayorista: es un dato que falta.
    3 · **Decir «sus originadores lo pasan a otro» cuando esos originadores son
        NUESTROS.** Si trabaja con Everett/Supreme, la fricción que se le
        estaria señalando es la de la casa propia, y el copy quedaria vendiendo
        contra nosotros mismos.
    """
    de_la_casa = [o for o in (originadores_de_la_casa or []) if o]
    if tpo_agente is None or not canal_mercado:
        return Lectura(
            que_dice_del_borrower=(
                "No sabemos por qué canal se fondean las operaciones de %s."
                % nombre_agente),
            bueno_o_malo=NEUTRO,
            que_hacer=("Preguntarle si sus originadores cierran en su propia "
                       "casa o pasan el caso a otro."),
            evidencia="falta el TPO del agente o la distribución del mercado")

    mayorista = (canal_mercado.get("banked_wholesale") or 0) + \
                (canal_mercado.get("brokered") or 0)
    suyo = _hablado(tpo_agente)
    evidencia = ("TPO del agente %s%% contra %s%% mayorista en %s"
                 % (tpo_agente, round(mayorista, 1), donde))

    # ── los dos lados, ninguno en cero ──────────────────────────────────────
    if not tpo_agente or not mayorista:
        cual = "del agente" if not tpo_agente else "del mercado en %s" % donde
        return Lectura(
            que_dice_del_borrower=(
                "No podemos comparar por qué canal se fondean las operaciones "
                "de %s: falta el dato %s." % (nombre_agente, cual)),
            bueno_o_malo=NEUTRO,
            que_hacer=("Preguntarle si sus originadores cierran en su propia "
                       "casa o pasan el caso a otro."),
            evidencia=evidencia + " · un lado en cero: no hay contraste")

    veces = tpo_agente / mayorista

    # ── si sus originadores son de la casa, esta friccion no es argumento ───
    if de_la_casa:
        return Lectura(
            que_dice_del_borrower=(
                "%s ya trabaja con %s. Su canal no es un problema que le "
                "podamos resolver: es el nuestro."
                % (nombre_agente, ", ".join(de_la_casa))),
            bueno_o_malo=NEUTRO,
            que_hacer=("No abrir por el canal. Este realtor está excluido por "
                       "no-canibalización: la conversación que corresponde es "
                       "con el originador que ya lo atiende."),
            evidencia=evidencia + " · originadores de la casa: %s"
                      % ", ".join(de_la_casa))

    # ── el agente POR DEBAJO del mercado ────────────────────────────────────
    if veces <= 1.0 / UMBRAL_CONTRASTE:
        return Lectura(
            que_dice_del_borrower=(
                "%s de las operaciones de %s van por canal mayorista, bastante "
                "menos que su condado — %s del mercado. Sus originadores están "
                "colocando el préstamo en su propia casa."
                % (suyo.capitalize(), nombre_agente, _hablado(mayorista))),
            bueno_o_malo=NEUTRO,
            que_hacer=("No abrir por el canal: no es su problema. Buscar el "
                       "ángulo por el perfil del comprador."),
            evidencia=evidencia + " · %s veces: por debajo del mercado"
                      % ("%g" % round(veces, 1)).replace(".", ","))

    # ── en linea: existe la diferencia pero no sostiene una afirmacion ──────
    if veces < UMBRAL_CONTRASTE:
        return Lectura(
            que_dice_del_borrower=(
                "El canal de %s se parece al de su condado: %s contra %s. No "
                "hay ahí una diferencia que le sirva de nada."
                % (nombre_agente, suyo, _hablado(mayorista))),
            bueno_o_malo=NEUTRO,
            que_hacer=("Preguntarle si los tiempos de cierre le están dando "
                       "problemas, sin dar por hecho que el canal es la causa."),
            evidencia=evidencia + " · %s veces: por debajo del umbral de %s"
                      % (("%g" % round(veces, 1)).replace(".", ","),
                         ("%g" % UMBRAL_CONTRASTE).replace(".", ",")))

    cuerpo = (
        "%s de las operaciones de %s se fondean por un canal mayorista, en un "
        "condado donde eso casi no se usa — %s del mercado. Sus originadores "
        "no colocan el préstamo en su propia casa: lo pasan a otro. Cada mano "
        "extra en el expediente es un punto más donde el caso se cae"
        % (suyo.capitalize(), nombre_agente, _hablado(mayorista)))
    if fallout_mercado:
        cuerpo += ", y en %s ya se cae %s" % (donde,
                                              _hablado(fallout_mercado,
                                                       femenino=True))
    cuerpo += "."

    return Lectura(
        que_dice_del_borrower=cuerpo,
        bueno_o_malo=FRICCION_RESOLUBLE,
        que_hacer=("Ofrecerle que el caso se origine y se cierre en la misma "
                   "casa, y decirle en cuántos días cerramos. La fricción que "
                   "está viendo no es del comprador: es del canal."),
        evidencia=evidencia + " · %s veces"
                  % ("%g" % round(veces, 1)).replace(".", ","),
        afirma=True,
        para_el_realtor=(
            "%s de tus operaciones se fondean por canal mayorista, en un "
            "condado donde eso es %s. Cada mano extra en el expediente es un "
            "punto más donde el caso se cae.\n\n"
            "¿Te está pasando con los tiempos de cierre?"
            % (suyo.capitalize(), _hablado(mayorista))))


def leer_perfil_del_comprador(mercado: dict, censo: dict | None,
                              donde: str) -> str:
    """El perfil de la zona, como PARRAFO.

    Describe a quien le vende el realtor, no al realtor. Es contexto del
    borrower y por eso no lleva veredicto: no dice si el agente sirve.
    """
    m = mercado or {}
    partes = []

    # `_hablado` ya devuelve `dos de cada diez`, asi que la plantilla NO lleva
    # `de los`: quedaba "dos de cada diez de los compradores".
    ftb = m.get("ftb")
    if ftb is not None:
        partes.append("%s compradores de %s son primerizos"
                      % (_hablado(ftb), donde))
    vet = m.get("veterans")
    if vet is not None and vet >= 3:
        partes.append("%s son veteranos" % _hablado(vet))
    cp = (censo or {}).get("cuenta_propia_pct")
    if cp is not None:
        partes.append("%s de quienes trabajan lo hacen por cuenta propia, así "
                      "que el income no siempre entra en un W-2" % _hablado(cp))

    fair = m.get("credit_fair")
    if fair is not None:
        partes.append("%s tienen score entre 580 y 669" % _hablado(fair))
    ingreso = m.get("avg_income")
    if ingreso:
        partes.append("el ingreso medio del hogar ronda los %s dólares"
                      % "{:,.0f}".format(ingreso).replace(",", "."))

    esp = (censo or {}).get("espanol_en_casa_pct")
    if esp is not None:
        partes.append("%s hogares hablan español en casa" % _hablado(esp))
    lim = (censo or {}).get("ingles_limitado_sobre_espanol_pct")
    if lim is not None:
        partes.append("y de esos, %s manejan el inglés con dificultad"
                      % _hablado(lim))

    carga = (censo or {}).get("carga_hipoteca_30mas_pct")
    if carga is not None:
        partes.append("%s de quienes ya tienen mortgage destinan más de un "
                      "tercio del ingreso a la vivienda" % _hablado(carga))

    if not partes:
        return ("No tenemos perfil del comprador de %s todavía." % donde)
    texto = "; ".join(partes) + "."
    verificar_vocabulario(texto)
    return texto[0].upper() + texto[1:]
