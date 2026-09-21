"""La cascada de cruce de identidad, con match_confidence y log de conflictos.

El orden, del brief
-------------------
    licencia estatal -> telefono E.164 -> email -> nombre + condado + rango de volumen

No es arbitrario. Cada escalon es mas debil que el anterior, y el ultimo es tan
debil que **no alcanza para operar solo**: un nombre mas un condado une a dos
personas distintas con la misma frecuencia con la que une a la misma persona.

Por que un modulo y no un merge por nombre
------------------------------------------
El brief lo pide explicito: *«Modulo propio, no un merge por nombre.»*

Un merge por nombre parece funcionar porque produce filas. Lo que no produce es
la informacion de cuanto confiar en cada fila, y esa es la unica cosa que hace
la diferencia entre un registro unificado y un registro inventado.

Media solucion ya existia: `trec.py` y `dbpr.py` devuelven numero de licencia.
Este modulo es lo que faltaba encima.

match_confidence
----------------
| Nivel | Cruce | Vale para |
|---|---|---|
| **CIERTO** | licencia estatal | todo, incluido escribirle |
| **ALTO** | telefono E.164, o email, con nombre compatible | todo |
| **MEDIO** | email solo, o telefono solo sin nombre compatible | enriquecer, no contactar |
| **BAJO** | nombre + condado + rango de volumen | cola de revision manual |
| **NINGUNO** | no hubo cruce | nada |

El corte esta en MEDIO: por debajo, el registro va a revision y **no se le
escribe**. Un toque humano sobre un registro mal unido se pierde dos veces --
gasta el toque y ensucia el dato.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum

from identidad.normalizacion import (
    a_e164,
    clave_de_licencia,
    clave_de_nombre,
    normalizar_email,
    tokens_de_nombre,
)


class Confianza(str, Enum):
    CIERTO = "cierto"
    ALTO = "alto"
    MEDIO = "medio"
    BAJO = "bajo"
    NINGUNO = "ninguno"

    @property
    def orden(self) -> int:
        return {"cierto": 4, "alto": 3, "medio": 2, "bajo": 1, "ninguno": 0}[self.value]

    @property
    def se_puede_contactar(self) -> bool:
        """El corte esta en MEDIO: por debajo va a revision manual."""
        return self.orden >= Confianza.MEDIO.orden

    @property
    def se_puede_afirmar_identidad(self) -> bool:
        """Solo con licencia o con dos señales fuertes."""
        return self.orden >= Confianza.ALTO.orden


@dataclass
class Candidato:
    """Un registro de otra fuente que podria ser la misma persona."""

    id_fuente: str
    fuente: str
    nombre: str | None = None
    licencia: str | None = None
    estado: str | None = None
    condado: str | None = None
    telefonos: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    unidades: float | None = None


@dataclass
class Cruce:
    """El resultado de comparar dos registros. Incluye por que."""

    confianza: Confianza
    escalon: str
    evidencia: str
    #: Campos que no coinciden entre las dos fuentes. Van al log, no se pisan.
    conflictos: list[str] = field(default_factory=list)

    @property
    def se_puede_contactar(self) -> bool:
        return self.confianza.se_puede_contactar


#: Tolerancia del rango de volumen en el escalon mas debil. Las unidades/año
#: vienen apelmazadas de la fuente -- en un lote de 4.249 filas, 689 marcaban
#: exactamente 9 y 679 marcaban 10, que no es distribucion natural sino un
#: bucket. Por eso se compara como RANGO y no como cifra.
TOLERANCIA_UNIDADES = 0.35

#: Minimo de tokens de nombre en comun para que el nombre sea "compatible".
MIN_TOKENS_NOMBRE = 2


def _nombre_compatible(a: str | None, b: str | None) -> tuple[bool, str]:
    ta, tb = tokens_de_nombre(a), tokens_de_nombre(b)
    if not ta or not tb:
        return False, "una de las dos fuentes no trae nombre comparable"
    comunes = [t for t in ta if t in tb]
    if len(comunes) >= MIN_TOKENS_NOMBRE:
        return True, "coinciden %d tokens de nombre: %s" % (len(comunes), comunes)
    # Un apellido largo solo, si es largo de verdad.
    if comunes and len(comunes[-1]) >= 6 and comunes[-1] == ta[-1] == tb[-1]:
        return True, "coincide el apellido %r, de %d letras" % (
            comunes[-1], len(comunes[-1]))
    if comunes:
        return False, "coincide solo %s: no alcanza" % comunes
    return False, "ningun token de nombre en comun"


def _volumen_compatible(a: float | None, b: float | None) -> tuple[bool, str]:
    if a is None or b is None:
        return False, "falta el volumen en una de las dos fuentes"
    if a <= 0 or b <= 0:
        return False, "volumen no positivo"
    mayor, menor = max(a, b), min(a, b)
    diferencia = (mayor - menor) / mayor
    if diferencia <= TOLERANCIA_UNIDADES:
        return True, "volumen %g vs %g, dentro del %.0f%%" % (
            a, b, TOLERANCIA_UNIDADES * 100)
    return False, "volumen %g vs %g, difiere %.0f%%" % (a, b, diferencia * 100)


def cruzar(nuestro: Candidato, otro: Candidato) -> Cruce:
    """Aplica la cascada. Devuelve el primer escalon que resuelve.

    Los conflictos se acumulan **siempre**, tambien cuando el cruce es CIERTO:
    dos fuentes que coinciden en licencia y difieren en telefono son la misma
    persona con un telefono en disputa, y eso hay que saberlo.
    """
    conflictos = _detectar_conflictos(nuestro, otro)

    # 1 · Licencia estatal. Es la llave de identidad del sistema.
    clave_a = clave_de_licencia(nuestro.licencia, nuestro.estado)
    clave_b = clave_de_licencia(otro.licencia, otro.estado)
    if clave_a and clave_b:
        if clave_a == clave_b:
            return Cruce(
                confianza=Confianza.CIERTO, escalon="licencia_estatal",
                evidencia="misma licencia %s" % clave_a,
                conflictos=conflictos,
            )
        # Dos licencias distintas del mismo estado: NO es la misma persona.
        if clave_a.split(":")[0] == clave_b.split(":")[0]:
            return Cruce(
                confianza=Confianza.NINGUNO, escalon="licencia_estatal",
                evidencia=(
                    "licencias distintas en el mismo estado: %s vs %s. No es la "
                    "misma persona, aunque el nombre coincida."
                    % (clave_a, clave_b)
                ),
                conflictos=conflictos,
            )

    compatible, razon_nombre = _nombre_compatible(nuestro.nombre, otro.nombre)

    # 2 · Telefono en E.164.
    tel_a = {n for n in (a_e164(t)[0] for t in nuestro.telefonos) if n}
    tel_b = {n for n in (a_e164(t)[0] for t in otro.telefonos) if n}
    comunes_tel = tel_a & tel_b
    if comunes_tel:
        if compatible:
            return Cruce(
                confianza=Confianza.ALTO, escalon="telefono_e164",
                evidencia="mismo telefono %s, y %s"
                          % (sorted(comunes_tel)[0], razon_nombre),
                conflictos=conflictos,
            )
        return Cruce(
            confianza=Confianza.MEDIO, escalon="telefono_e164",
            evidencia=(
                "mismo telefono %s pero el nombre no verifica (%s). Puede ser "
                "un telefono de oficina compartido: sirve para enriquecer, no "
                "para contactar como si fuera esa persona."
                % (sorted(comunes_tel)[0], razon_nombre)
            ),
            conflictos=conflictos,
        )

    # 3 · Email.
    mail_a = {e for e in (normalizar_email(m)[0] for m in nuestro.emails) if e}
    mail_b = {e for e in (normalizar_email(m)[0] for m in otro.emails) if e}
    comunes_mail = mail_a & mail_b
    if comunes_mail:
        if compatible:
            return Cruce(
                confianza=Confianza.ALTO, escalon="email",
                evidencia="mismo email %s, y %s"
                          % (sorted(comunes_mail)[0], razon_nombre),
                conflictos=conflictos,
            )
        return Cruce(
            confianza=Confianza.MEDIO, escalon="email",
            evidencia="mismo email %s pero el nombre no verifica (%s)"
                      % (sorted(comunes_mail)[0], razon_nombre),
            conflictos=conflictos,
        )

    # 4 · Nombre + condado + rango de volumen. El escalon debil.
    mismo_condado = (
        nuestro.condado and otro.condado
        and nuestro.condado.strip().lower() == otro.condado.strip().lower()
    )
    vol_ok, razon_vol = _volumen_compatible(nuestro.unidades, otro.unidades)
    if compatible and mismo_condado and vol_ok:
        return Cruce(
            confianza=Confianza.BAJO, escalon="nombre_condado_volumen",
            evidencia=(
                "%s, mismo condado %s, y %s. Es el escalon mas debil de la "
                "cascada: va a revision manual, no se contacta."
                % (razon_nombre, nuestro.condado, razon_vol)
            ),
            conflictos=conflictos,
        )

    faltantes = []
    if not compatible:
        faltantes.append("nombre (%s)" % razon_nombre)
    if not mismo_condado:
        faltantes.append("condado")
    if not vol_ok:
        faltantes.append("volumen (%s)" % razon_vol)
    return Cruce(
        confianza=Confianza.NINGUNO, escalon="ninguno",
        evidencia="no cruza por: %s" % "; ".join(faltantes),
        conflictos=conflictos,
    )


def _detectar_conflictos(a: Candidato, b: Candidato) -> list[str]:
    """Campos donde las dos fuentes dicen cosas distintas.

    Un conflicto no invalida el cruce ni se resuelve promediando. Se registra.
    """
    salida: list[str] = []

    tel_a = {n for n in (a_e164(t)[0] for t in a.telefonos) if n}
    tel_b = {n for n in (a_e164(t)[0] for t in b.telefonos) if n}
    if tel_a and tel_b and not (tel_a & tel_b):
        salida.append(
            "telefono: %s dice %s, %s dice %s"
            % (a.fuente, sorted(tel_a), b.fuente, sorted(tel_b))
        )

    mail_a = {e for e in (normalizar_email(m)[0] for m in a.emails) if e}
    mail_b = {e for e in (normalizar_email(m)[0] for m in b.emails) if e}
    if mail_a and mail_b and not (mail_a & mail_b):
        salida.append(
            "email: %s dice %s, %s dice %s"
            % (a.fuente, sorted(mail_a), b.fuente, sorted(mail_b))
        )

    if a.estado and b.estado and a.estado.strip().upper()[:2] != b.estado.strip().upper()[:2]:
        salida.append(
            "estado: %s dice %r, %s dice %r"
            % (a.fuente, a.estado, b.fuente, b.estado)
        )

    if a.unidades is not None and b.unidades is not None:
        ok, razon = _volumen_compatible(a.unidades, b.unidades)
        if not ok and "falta" not in razon:
            salida.append("volumen: %s" % razon)

    clave_a = clave_de_nombre(a.nombre)
    clave_b = clave_de_nombre(b.nombre)
    if clave_a and clave_b and clave_a != clave_b:
        compatible, razon = _nombre_compatible(a.nombre, b.nombre)
        if not compatible:
            salida.append(
                "nombre: %s dice %r, %s dice %r (%s)"
                % (a.fuente, a.nombre, b.fuente, b.nombre, razon)
            )

    return salida


def mejor_cruce(nuestro: Candidato, candidatos: list[Candidato]
                ) -> tuple[Candidato | None, Cruce]:
    """El candidato que cruza con mas confianza, y su cruce.

    Si dos candidatos cruzan con la MISMA confianza y no es CIERTO, devuelve
    NINGUNO: dos personas que cruzan igual de bien significa que el cruce no
    distingue, y elegir una por orden de aparicion es inventar.
    """
    if not candidatos:
        return None, Cruce(
            confianza=Confianza.NINGUNO, escalon="ninguno",
            evidencia="no habia candidatos",
        )

    cruces = [(c, cruzar(nuestro, c)) for c in candidatos]
    cruces.sort(key=lambda par: par[1].confianza.orden, reverse=True)
    mejor_cand, mejor = cruces[0]

    if mejor.confianza is Confianza.NINGUNO:
        return None, mejor

    empatados = [
        c for c, x in cruces
        if x.confianza.orden == mejor.confianza.orden
    ]
    if len(empatados) > 1 and mejor.confianza is not Confianza.CIERTO:
        return None, Cruce(
            confianza=Confianza.NINGUNO, escalon="ambiguo",
            evidencia=(
                "%d candidatos cruzan con confianza %s: %s. El cruce no "
                "distingue, y elegir uno por orden de aparicion es inventar."
                % (len(empatados), mejor.confianza.value,
                   [c.id_fuente for c in empatados])
            ),
            conflictos=mejor.conflictos,
        )
    return mejor_cand, mejor


@dataclass
class LogDeConflictos:
    """Los conflictos de todo el lote. Es un entregable, no un log de debug."""

    entradas: list[dict] = field(default_factory=list)

    def registrar(self, id_nuestro: str, otro: Candidato, cruce: Cruce,
                  *, fecha: dt.date | None = None) -> None:
        if not cruce.conflictos:
            return
        self.entradas.append({
            "id": id_nuestro,
            "fuente_contraria": otro.fuente,
            "id_contrario": otro.id_fuente,
            "confianza_del_cruce": cruce.confianza.value,
            "escalon": cruce.escalon,
            "conflictos": list(cruce.conflictos),
            "fecha": (fecha or dt.date.today()).isoformat(),
        })

    def resumen(self) -> dict:
        por_campo: dict[str, int] = {}
        for e in self.entradas:
            for c in e["conflictos"]:
                campo = c.split(":", 1)[0]
                por_campo[campo] = por_campo.get(campo, 0) + 1
        return {
            "registros_con_conflicto": len(self.entradas),
            "conflictos_por_campo": dict(
                sorted(por_campo.items(), key=lambda kv: -kv[1])
            ),
            "nota": (
                "un conflicto no se resuelve promediando ni quedandose con el "
                "de mayor confianza: es una pregunta abierta. Si el telefono de "
                "MMI y el del board difieren, alguien tiene que decidir cual "
                "es, y hasta entonces se guardan los dos."
            ),
        }
