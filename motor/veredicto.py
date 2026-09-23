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

from captura.trampas import TrampaDetectada, es_de_la_casa, share_de_la_casa

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
        return Veredicto(
            estado=PENDIENTE,
            motivo=("hay captura pero sin reparto por unidades: %s"
                    % (reparto.get("razon") or "sin Buyer Side Relationships")),
            evidencia=_evidencia_base(None, capturado_en))

    unidades = reparto.get("unidades") or 0
    evidencia = _evidencia_base(perfil.get("orig_buyer"), capturado_en)
    evidencia.update({
        "originadores_de_la_casa": [
            o.get("nombre") for o in (perfil.get("orig_buyer") or [])
            if es_de_la_casa(o)],
        "unidades_de_la_casa": unidades,
        "unidades_totales": reparto.get("unidades_totales"),
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
