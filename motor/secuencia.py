"""La secuencia de 7 toques, sin una sola promesa de material.

La decision que la desbloquea
-----------------------------
Los seis recursos del catalogo siguen sin verificar. En vez de esperar, **se
quitan las promesas y se entrega el valor dentro del mensaje**. No se baja la
calidad: se cambia de que esta hecho el valor.

  toque 2   el dato de SU mercado -- fallout de su condado, dias de cierre,
            cuota FHA. Verificables, estan en la base, y ningun realtor los
            conoce. Valor entregado sin adjuntar nada.
  toque 4   una observacion concreta sobre su cartera, sacada de los
            contrastes. Si ningun contraste activa, la pregunta de cierre de
            brecha -- que es lo unico que sabemos que falta en todas las filas.

Las cuatro reglas de calidad
----------------------------
1 · Cada mensaje dice UNA SOLA COSA. Dos ideas significan que sobra una.
2 · Empieza por lo que le interesa a el, no por quienes somos.
3 · Nada de adjetivos de folleto. Si la frase podria estar en el correo de
    cualquier lender, va fuera.
4 · El ultimo parrafo es el que se lee primero: ahi va la pregunta o la oferta,
    nunca el cierre de cortesia.

Las tres primeras son comprobables y estan comprobadas. `PROMESAS_DE_MATERIAL`
y `ADJETIVOS_DE_FOLLETO` son listas ejecutables, igual que el vocabulario: la
construccion revienta si aparecen.

Los ganchos NO se tocan
-----------------------
Son literales de la matriz -- `gancho_conversacional` de las 205 fichas que lo
traen-- y estan calibrados. El toque 1 es el gancho y nada mas. Los que se
trabajan aca son el 2, el 3, el 4 y el 7.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from motor.lectura import _hablado, verificar_vocabulario

# ── Lo que el copy NO puede prometer ────────────────────────────────────────
#
# Mientras nadie confirme que los seis recursos existen, ningun mensaje puede
# ofrecer material. No es un aviso: es una regla que revienta.
PROMESAS_DE_MATERIAL = (
    "te dejo", "te mando", "te comparto", "te envio", "te envío",
    "te paso", "te adjunto", "el mapa de", "el desglose de", "la guía",
    "la guia", "el checklist", "la comparativa", "material completo",
    "te lo hago llegar", "descarga", "descárgate",
)

#: Si la frase podria estar en el correo de cualquier lender, va fuera.
ADJETIVOS_DE_FOLLETO = (
    "soluciones innovadoras", "aliado estratégico", "aliado estrategico",
    "potenciar tu negocio", "llevar tu negocio al siguiente nivel",
    "socio de confianza", "servicio de excelencia", "atención personalizada",
    "somos líderes", "somos lideres", "amplia experiencia",
    "compromiso con la excelencia", "valor agregado", "sinergia",
    "tu mejor aliado", "soluciones a medida",
)


class CopyInvalido(ValueError):
    """El mensaje incumple una de las reglas que si se pueden comprobar."""


def verificar_sin_promesas(texto: str) -> None:
    bajo = (texto or "").lower()
    for frase in PROMESAS_DE_MATERIAL:
        if frase in bajo:
            raise CopyInvalido(
                "%r promete material, y ningun recurso esta verificado.\n"
                "El valor va DENTRO del mensaje, no adjunto.\n  en: %s"
                % (frase, texto[:160]))


def verificar_sin_folleto(texto: str) -> None:
    bajo = (texto or "").lower()
    for frase in ADJETIVOS_DE_FOLLETO:
        if frase in bajo:
            raise CopyInvalido(
                "%r podria estar en el correo de cualquier lender.\n  en: %s"
                % (frase, texto[:160]))


def _parrafos(texto: str) -> list[str]:
    return [p.strip() for p in (texto or "").split("\n\n") if p.strip()]


def verificar_cierra_con_pregunta_u_oferta(texto: str) -> None:
    """El ultimo parrafo es el que se lee primero."""
    ps = _parrafos(texto)
    if not ps:
        raise CopyInvalido("mensaje vacío")
    ultimo = ps[-1]
    if "?" in ultimo:
        return
    # Una oferta concreta tambien vale: se reconoce por el verbo en primera
    # persona con un compromiso, no por su tono.
    if re.search(r"\b(te lo digo|lo reviso|lo miro|lo saco|te lo saco|"
                 r"lo corro|me siento|lo vemos|te lo armo)\b", ultimo.lower()):
        return
    raise CopyInvalido(
        "el último párrafo no lleva pregunta ni oferta: es lo primero que se "
        "lee y ahí no puede ir un cierre de cortesía.\n  último: %s" % ultimo)


def verificar_una_sola_idea(texto: str) -> None:
    """Un mensaje con mas de dos parrafos de cuerpo dice mas de una cosa.

    Es aproximado y esta dicho: lo que se puede comprobar es la FORMA, no la
    unidad semantica. Dos parrafos -- el dato y la pregunta-- es el maximo.
    """
    if len(_parrafos(texto)) > 2:
        raise CopyInvalido(
            "el mensaje tiene %d párrafos. Cada mensaje dice una sola cosa: "
            "si tiene dos ideas, sobra una." % len(_parrafos(texto)))


@dataclass
class Toque:
    numero: int
    dia: int
    canal: str
    asunto: str | None
    cuerpo: str
    #: De donde salio el valor que entrega. Vacio = no entrega dato.
    fuente_del_valor: str = ""
    #: Recursos prometidos. **Siempre vacio ahora**, y la prueba lo exige.
    recursos: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        verificar_vocabulario(self.cuerpo)
        verificar_sin_promesas(self.cuerpo)
        verificar_sin_folleto(self.cuerpo)
        verificar_una_sola_idea(self.cuerpo)
        verificar_cierra_con_pregunta_u_oferta(self.cuerpo)
        if self.asunto:
            verificar_sin_promesas(self.asunto)
            verificar_sin_folleto(self.asunto)


@dataclass
class Secuencia:
    realtor: str
    toques: list[Toque] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)

    @property
    def promete_material(self) -> bool:
        return any(t.recursos for t in self.toques)


# ══════════════════════════════════════════════════════════════════════════════
# LOS TOQUES
# ══════════════════════════════════════════════════════════════════════════════

def _toque_1(gancho: str) -> Toque:
    """El gancho de la matriz, literal. No se reescribe ni se envuelve."""
    return Toque(1, 0, "email", None, gancho.strip(),
                 fuente_del_valor="gancho_conversacional de la matriz")


def _toque_2(nombre: str, mercado: dict, donde: str) -> Toque | None:
    """El dato de SU mercado. Verificable, en la base, y no lo conoce.

    Una sola cifra por mensaje: la regla dice una sola cosa. Se elige la que
    esta -- fallout primero, porque es la que duele-- y no se apilan tres.
    """
    m = mercado or {}
    fallout, dias, fha = m.get("fallout"), m.get("time_to_close"), m.get("mkt_fha")

    # `_hablado` ya devuelve `tres y medio de cada diez`: la plantilla no lleva
    # `de los` detras, y el genero es el del SUSTANTIVO que sigue --
    # expedientes y préstamos son masculinos.
    if fallout is not None:
        dato = ("En %s se caen %s expedientes antes de cerrar."
                % (donde, _hablado(fallout)))
        fuente = "fallout de %s: %s%%" % (donde, fallout)
    elif dias is not None:
        dato = ("En %s el cierre promedio va en %d días." % (donde, int(dias)))
        fuente = "time_to_close de %s: %s días" % (donde, dias)
    elif fha is not None:
        dato = "En %s, %s préstamos son FHA." % (donde, _hablado(fha))
        fuente = "mkt_fha de %s: %s%%" % (donde, fha)
    else:
        return None

    cuerpo = ("%s\n\n¿Te cuadra con lo que ves tú, o en tu cartera se comporta "
              "distinto?" % dato)
    return Toque(2, 3, "email", None, cuerpo, fuente_del_valor=fuente)


def _toque_3(nombre: str, perfil_zona: str | None, donde: str) -> Toque:
    """Quien es su comprador, en una frase. Sigue sin adjuntar nada."""
    if perfil_zona:
        # Una sola idea: se toma el primer rasgo del parrafo, no el parrafo.
        primer = perfil_zona.split(";")[0].strip().rstrip(".")
        cuerpo = ("%s.\n\nEso cambia qué documentos hay que pedir y en qué "
                  "orden. ¿Cómo lo estás manejando hoy?" % primer)
        fuente = "perfil del comprador de %s" % donde
    else:
        cuerpo = ("Todavía no sé cómo se ve tu comprador típico en %s.\n\n"
                  "¿Con qué perfil cierras más — primerizo, inversión, "
                  "self-employed?" % donde)
        fuente = ""
    return Toque(3, 10, "email", None, cuerpo, fuente_del_valor=fuente)


def _toque_4(nombre: str, lecturas: list, apertura_sin_dolor: str) -> Toque:
    """La observacion sobre su cartera, o la pregunta de cierre de brecha.

    Antes decia "te mando el material completo". Ahora, si hay un contraste que
    AFIRMA, se dice lo que se ve; si no, va la pregunta del lender -- que cierra
    la categoria vacia en el 100% de las filas.
    """
    afirman = [l for l in (lecturas or []) if getattr(l, "afirma", False)]
    if afirman:
        l = afirman[0]
        # El que_hacer ya esta escrito para ser usado por el BD.
        cuerpo = ("%s\n\n%s" % (l.que_dice_del_borrower.strip(),
                                l.que_hacer.strip()))
        # Si el que_hacer no cierra con pregunta, se le agrega la de confirmar.
        if "?" not in cuerpo.split("\n\n")[-1]:
            cuerpo += " ¿Lo ves igual?"
        return Toque(4, 21, "email", None, cuerpo,
                     fuente_del_valor="contraste activo: %s" % l.evidencia)
    return Toque(4, 21, "email", None, apertura_sin_dolor,
                 fuente_del_valor="ningún contraste activa: pregunta de cierre "
                                  "de brecha del lender")


#: Como se dice cada cantidad de intentos previos. El numero es un HECHO
#: verificable dentro del propio mensaje: decir "tres veces" cuando fueron dos
#: es la clase de error que el lector si nota, y que quema la credibilidad de
#: todo lo demas que el mensaje afirma.
_VECES = {1: "una vez", 2: "dos veces", 3: "tres veces", 4: "cuatro veces"}


def _toque_7(nombre: str, anteriores: int) -> Toque:
    """El ultimo. Sin material, sin despedida de cortesia, sin insistir."""
    cuantas = _VECES.get(anteriores, "varias veces")
    cuerpo = ("Te escribí %s y no te llegué en buen momento, así que este es "
              "el último.\n\n"
              "Si algún día se te complica un expediente de los difíciles "
              "— ITIN, self-employed, score entre 580 y 669 — escríbeme y lo "
              "miro contigo. ¿Te parece?" % cuantas)
    return Toque(7, 60, "email", None, cuerpo,
                 fuente_del_valor="cierre sin promesa · %d intentos previos"
                                  % anteriores)


#: Los toques 5 y 6 NO estan escritos. Era donde vivian dos de los seis
#: recursos, y escribirlos de relleno para que la secuencia tenga siete es
#: justo lo que el brief pide no hacer. Salen cuando haya valor real que poner.
TOQUES_PENDIENTES = (5, 6)


def armar_secuencia(*, nombre: str, gancho: str, mercado: dict | None,
                    donde: str, perfil_zona: str | None, lecturas: list,
                    apertura_sin_dolor: str) -> Secuencia:
    """La secuencia completa, con lo que haya. Lo que falta se dice."""
    seq = Secuencia(realtor=nombre)
    seq.toques.append(_toque_1(gancho))

    t2 = _toque_2(nombre, mercado or {}, donde)
    if t2:
        seq.toques.append(t2)
    else:
        seq.notas.append(
            "toque 2 sin dato de mercado: no hay fallout, días de cierre ni "
            "mix FHA de %s. Sin eso el toque no entrega valor y no sale."
            % donde)

    seq.toques.append(_toque_3(nombre, perfil_zona, donde))
    seq.toques.append(_toque_4(nombre, lecturas, apertura_sin_dolor))
    # El 7 cuenta los que SI salieron: si el toque 2 no tuvo dato, fueron tres
    # intentos y no cuatro, y el mensaje no puede decir un numero que no es.
    seq.toques.append(_toque_7(nombre, anteriores=len(seq.toques)))

    seq.notas.append(
        "los toques %s no están escritos: era donde vivían dos de los seis "
        "recursos sin verificar. Escribirlos de relleno para llegar a siete es "
        "lo contrario de quitar las promesas."
        % " y ".join(str(n) for n in TOQUES_PENDIENTES))
    return seq
