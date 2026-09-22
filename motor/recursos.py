"""Los recursos que promete el copy, y si alguien confirmo que existen.

El archivo 11 de la skill, alucinacion 5
----------------------------------------
    El copy generado ofrece "el desglose de que documentacion acepta cada
    programa", "el mapa de DPA de tu condado", "los tiempos de cierre reales
    por tipo de expediente". **Nadie verifico que esos materiales existan.**

    La regla de que cada toque trae valor real deja de cumplirse si el valor es
    imaginario.

Mientras el equipo confirma que material existe de verdad, ningun toque que
prometa un recurso puede salir por descuido. Por eso el flag no es un aviso: es
el default. Un recurso arranca `verificado = False` y solo cambia cuando alguien
lo marca, con su nombre y su fecha.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class Recurso:
    """Un material que el copy promete entregar."""

    clave: str
    descripcion: str
    #: **Arranca en False y se queda ahi hasta que alguien lo confirme.**
    verificado: bool = False
    confirmado_por: str | None = None
    confirmado_en: dt.date | None = None

    def __post_init__(self) -> None:
        if self.verificado and not (self.confirmado_por and self.confirmado_en):
            raise ValueError(
                "%s se declara verificado sin decir quien y cuando. Un "
                "verificado sin firma es lo mismo que un no verificado, pero "
                "parece lo contrario." % self.clave
            )


#: El catalogo. Todos en False hasta que el equipo confirme, que es el estado
#: real hoy: 2026-09-22, ninguno confirmado.
CATALOGO: dict[str, Recurso] = {
    r.clave: r for r in (
        Recurso("mapa_dpa_condado",
                "mapa de programas de ayuda de enganche del condado"),
        Recurso("desglose_documentacion",
                "qué documentación acepta cada programa"),
        Recurso("tiempos_de_cierre",
                "tiempos de cierre reales por tipo de expediente"),
        Recurso("guia_itin",
                "guía de compra con ITIN"),
        Recurso("comparativa_bank_statement",
                "comparativa de programas bank statement"),
        Recurso("checklist_self_employed",
                "checklist de documentos para trabajador por cuenta propia"),
    )
}


@dataclass
class ToqueConRecursos:
    """Un toque de la secuencia y lo que promete."""

    numero: int
    recursos: tuple[str, ...]

    @property
    def recurso_sin_verificar(self) -> bool:
        """True si promete algo que nadie confirmo que exista.

        Es el flag que el brief pide. Un toque con esto en True **no se envia**.
        """
        return any(not CATALOGO[c].verificado
                   for c in self.recursos if c in CATALOGO)

    @property
    def sin_verificar(self) -> tuple[str, ...]:
        return tuple(c for c in self.recursos
                     if c in CATALOGO and not CATALOGO[c].verificado)

    @property
    def desconocidos(self) -> tuple[str, ...]:
        """Recursos que ni siquiera estan en el catalogo.

        Es el caso mas grave: el copy promete algo que nadie catalogo, o sea
        que nadie puede ni empezar a verificar.
        """
        return tuple(c for c in self.recursos if c not in CATALOGO)


def verificar_secuencia(toques: list[ToqueConRecursos]) -> list[str]:
    """Los motivos por los que una secuencia no puede salir. Vacia = puede.

    Devuelve motivos en vez de levantar: quien llama decide si bloquea o
    advierte, y en los dos casos el motivo esta escrito.
    """
    motivos = []
    for t in toques:
        if t.desconocidos:
            motivos.append(
                "toque %d promete recursos que no están en el catálogo: %s"
                % (t.numero, ", ".join(t.desconocidos))
            )
        if t.sin_verificar:
            motivos.append(
                "toque %d promete %s, que nadie confirmó que exista"
                % (t.numero, ", ".join(
                    CATALOGO[c].descripcion for c in t.sin_verificar))
            )
    return motivos
