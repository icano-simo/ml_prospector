"""Una sola compuerta: ¿se le puede escribir a esta persona?

Por que una sola
----------------
Antes la pregunta se contestaba en cuatro sitios y ninguno la contestaba
entera. `/api/dossier` miraba la exclusion del libro, `guardar_texto` no miraba
nada, y la exclusion por no-canibalizacion --el realtor que ya trabaja con
nuestros propios originadores-- no bloqueaba en ningun lado. Cada camino tenia
su propio criterio, asi que el mismo realtor podia salir contactable por uno e
inviable por otro.

Aca hay IO cero. Recibe lo que ya se leyo y devuelve un veredicto; quien lea la
base es el que llama. Eso es lo que permite probarla sin red y llamarla desde la
API, desde el guardado de textos y desde el motor sin tres implementaciones.

Los tres veredictos
-------------------
``excluido``              ya trabaja con la casa. **Umbral > 0: basta una
                          operacion buyside por unidades.** Decision de negocio
                          del 2026-09-23, no un parametro que se afine.
``pendiente_modelmatch``  no hay captura de Model Match, o la hay y no se pudo
                          leer el reparto de originadores. Sin eso no se sabe
                          si lo estariamos canibalizando, y no saberlo no es
                          poder.
``ok``                    hay captura, se leyo el reparto, y no hay operaciones
                          con la casa.

`pendiente_modelmatch` NO es un estado de error: es el estado normal de casi
todo el lote mientras la captura avanza realtor por realtor. La app muestra lo
que ya sabe y lo marca; lo que no hace es producir dolor primario, ganchos,
toques ni textos.

Por que el umbral es > 0 y no un porcentaje
-------------------------------------------
Lo pidio el negocio y tiene sentido operativo: una sola operacion ya significa
que hay una relacion viva con un originador nuestro, y escribirle es competirle
a un colega por su propia cartera. El share se calcula igual y viaja en la
evidencia, porque «1 de 20» y «18 de 20» son la misma decision con conversaciones
muy distintas detras.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from captura.trampas import (
    TrampaDetectada,
    es_de_la_casa,
    lenders_de_la_casa,
    share_de_la_casa,
)

EXCLUIDO = "excluido"
PENDIENTE = "pendiente_modelmatch"
OK = "ok"

#: Una sola operacion basta. Decision de negocio, 2026-09-23.
UNIDADES_MINIMAS_PARA_EXCLUIR = 0


@dataclass(frozen=True)
class Veredicto:
    estado: str
    motivo: str
    #: Lo que sostiene el veredicto: originadores, unidades, base y fecha.
    evidencia: dict = field(default_factory=dict)

    @property
    def puede_escribirsele(self) -> bool:
        """Lo unico que hay que preguntarle para decidir si se genera copy."""
        return self.estado == OK

    def a_dict(self) -> dict:
        return {"estado": self.estado, "motivo": self.motivo,
                "evidencia": dict(self.evidencia)}


def _evidencia_base(reparto, capturado_en) -> dict:
    return {
        "base": "unidades",
        "umbral": "> %d" % UNIDADES_MINIMAS_PARA_EXCLUIR,
        "capturado_en": capturado_en,
        "originadores_de_la_casa": [],
        "unidades_de_la_casa": None,
        "unidades_totales": None,
        "share_de_la_casa": None,
        "originadores_leidos": len(reparto or []),
    }


def puede_contactarse(perfil: dict | None, *,
                      capturado_en: str | None = None,
                      excluido_por_el_libro: str | None = None,
                      motivo_del_libro: str | None = None) -> Veredicto:
    """El veredicto, con su motivo y su evidencia. Sin tocar la base.

    `perfil` es el perfil unido de Model Match (`parser_mm.unir_perfiles`).
    `excluido_por_el_libro` es el nivel de `pacs: nivel_de_calificacion` cuando
    NO es contactable -- lo calcula `motor.exclusion.clasificar`, y aqui entra
    ya resuelto para que este modulo siga sin leer nada.
    """
    # 1 · La exclusion metodologica manda sobre todo lo demas. Es una decision
    #     ya tomada aguas arriba, y Model Match no la revisa.
    if excluido_por_el_libro:
        return Veredicto(
            estado=EXCLUIDO,
            motivo="excluido por metodología: %s" % excluido_por_el_libro,
            evidencia={"origen": "libro v3", "nivel": excluido_por_el_libro,
                       "motivo_del_libro": motivo_del_libro})

    # 2 · Sin captura no hay veredicto. Un perfil vacio y un perfil que no se
    #     pudo parsear llegan igual aca, y los dos significan lo mismo: todavia
    #     no sabemos si lo estariamos canibalizando.
    if not perfil:
        return Veredicto(
            estado=PENDIENTE,
            motivo=("falta la captura de Model Match: sin ella no se sabe con "
                    "qué originadores trabaja, y no saberlo no es poder"),
            evidencia=_evidencia_base(None, capturado_en))

    # 2b · LA PESTAÑA LENDERS. Everett/Supreme ahi es exclusion igual que en
    #      originadores: la casa ya esta en esa operacion.
    #
    #      Se mira ANTES del reparto por unidades porque no depende de el: un
    #      perfil sin `Buyer Side Relationships` pero con Everett en Lenders es
    #      una exclusion que se sabe, y dejarla en `pendiente` seria no usar un
    #      dato que esta a la vista.
    de_la_casa_en_lenders = lenders_de_la_casa(perfil)
    if de_la_casa_en_lenders:
        evidencia = _evidencia_base(perfil.get("orig_buyer"), capturado_en)
        evidencia.update({"lenders_de_la_casa": de_la_casa_en_lenders,
                          "origen": "pestaña Lenders de Model Match"})
        return Veredicto(
            estado=EXCLUIDO,
            motivo="%s aparece como lender en Model Match"
                   % ", ".join(de_la_casa_en_lenders),
            evidencia=evidencia)

    # 3 · «Model Match no muestra originadores para este agente», declarado con
    #     la casilla de la pantalla de captura.
    #
    #     Decision de Isabella del 2026-09-23: no tener originadores esta bien y
    #     NO bloquea. Lo que bloquea es no saber.
    #
    #     La diferencia entre esto y el caso de abajo es toda la diferencia:
    #     una caja vacia SIN la casilla es «falta capturar», y una caja vacia
    #     CON la casilla es «se miro y no hay». Son el mismo `orig_buyer = []`
    #     en el dato, y dos veredictos opuestos -- por eso la casilla existe:
    #     es el unico sitio donde queda constancia de que alguien miro.
    if perfil.get("sin_originadores_declarado"):
        evidencia = _evidencia_base([], capturado_en)
        evidencia.update({"unidades_de_la_casa": 0, "unidades_totales": 0,
                          "share_de_la_casa": 0.0,
                          "vacio_declarado": True,
                          "declarado_por": perfil.get("declarado_por")})
        return Veredicto(
            estado=OK,
            motivo=("Model Match no registra originadores del lado comprador: "
                    "0 operaciones con la casa"),
            evidencia=evidencia)

    try:
        reparto = share_de_la_casa(perfil)
    except TrampaDetectada as exc:
        # `share_de_la_casa` revienta sobre un fallo declarado del parser. Eso
        # es exactamente `pendiente`: hay captura pero no se pudo leer.
        return Veredicto(
            estado=PENDIENTE,
            motivo=("hay captura pero el reparto de originadores no se pudo "
                    "leer: %s" % str(exc).split("\n")[0]),
            evidencia=_evidencia_base(None, capturado_en))

    if reparto.get("share") is None and not reparto.get("unidades"):
        # Dos casos distintos con el mismo sintoma, y el motivo tiene que
        # decir cual es: uno se arregla pegando una seccion, el otro marcando
        # una casilla. Un motivo que no distingue manda a buscar lo que no es.
        if perfil.get("tab_orig"):
            falta = ("está pegada la pestaña Originators, que reparte por "
                     "VOLUMEN, y falta la sección «Buyer Side Relationships», "
                     "que es la que reparte por unidades")
        else:
            falta = ("falta la sección Originators. Si Model Match no le "
                     "muestra originadores a este agente, marcá la casilla "
                     "«Model Match no muestra originadores»")
        return Veredicto(
            estado=PENDIENTE,
            motivo="hay captura pero sin reparto por unidades: %s" % falta,
            evidencia=_evidencia_base(None, capturado_en))

    unidades = reparto.get("unidades") or 0
    evidencia = _evidencia_base(perfil.get("orig_buyer"), capturado_en)
    evidencia.update({
        "originadores_de_la_casa": [
            o.get("nombre") for o in (perfil.get("orig_buyer") or [])
            if es_de_la_casa(o)],
        "unidades_de_la_casa": unidades,
        "unidades_totales": reparto.get("unidades_totales"),
        # Las compras SIN originador identificado NO bloquean (decision de
        # Isabella, 2026-09-23). Abby Grimaldi tiene 7 de 18 identificadas y
        # ninguna de la casa: queda `ok`. Pero el numero viaja, porque «7» y
        # «18» leidos sin el otro dicen cosas distintas.
        "compras_con_originador": reparto.get("unidades_totales"),
        "compras_totales": perfil.get("buyer_units"),
        "share_de_la_casa": reparto.get("share"),
    })

    if unidades > UNIDADES_MINIMAS_PARA_EXCLUIR:
        quienes = ", ".join(evidencia["originadores_de_la_casa"]) or "la casa"
        return Veredicto(
            estado=EXCLUIDO,
            motivo=("ya trabaja con %s: %g de %s operaciones buyside por "
                    "unidades. Escribirle es competirle su propia cartera a un "
                    "colega."
                    % (quienes, unidades,
                       ("%g" % reparto["unidades_totales"])
                       if reparto.get("unidades_totales") else "?")),
            evidencia=evidencia)

    return Veredicto(
        estado=OK,
        motivo=("no tiene operaciones buyside con originadores de la casa "
                "(%d originadores leídos)" % evidencia["originadores_leidos"]),
        evidencia=evidencia)
