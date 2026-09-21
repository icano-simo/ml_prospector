"""Valores versionados. Nunca se sobrescribe un campo.

La regla
--------
El brief lo pide asi: *«Nunca sobrescribas un campo: versiona cada valor con
fuente y fecha.»*

No es purismo. Model Match entrega varios emails y telefonos con porcentaje de
confianza, y **el de nuestra lista puede coincidir con uno secundario**. Si el
pipeline se queda con el de mayor confianza y descarta el resto, pierde el
unico cruce que confirmaba identidad.

Y al reves: si un dato nuevo sobrescribe uno viejo, el conflicto desaparece sin
que nadie lo vea. Un telefono que MMI dice que es 512-555-0100 y que el board
de licencias dice que es 512-555-0199 **no es un dato mejor**: es una pregunta
abierta, y una pregunta abierta guardada como un solo valor es una respuesta
inventada.

Como se usa
-----------
    campo = Campo("telefono")
    campo.agregar("+15125550100", fuente="mmi", fecha=hoy, confianza=0.9)
    campo.agregar("+15125550199", fuente="board", fecha=hoy, confianza=0.7)

    campo.preferido()      -> el de mayor confianza, para operar
    campo.en_conflicto     -> True
    campo.conflictos()     -> los pares que no coinciden, para el log
    campo.todos()          -> todos, que es lo que se persiste
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

#: Prioridad de fuente cuando dos traen la misma confianza declarada.
#:
#: La licencia estatal manda porque es un registro de gobierno y es la llave de
#: identidad del sistema. El board de LOs es una aproximacion operativa -- la
#: autoridad sobre quien trabaja aca es HR y sobre quien esta licenciado es
#: NMLS -- asi que va debajo de las fuentes transaccionales.
PRIORIDAD_DE_FUENTE: dict[str, int] = {
    "licencia_estatal": 100,
    "nmls": 95,
    "model_match": 80,
    "mmi": 78,
    "google_places": 60,
    "instagram_bio": 55,
    "board_los": 50,
    "lote_original": 40,
    "instagram_inferido": 20,
    "derivado": 10,
}


@dataclass(frozen=True)
class Valor:
    """Un valor con su procedencia. Inmutable a proposito."""

    valor: Any
    fuente: str
    fecha: dt.date
    #: 0-1. None cuando la fuente no declara confianza.
    confianza: float | None = None
    nota: str | None = None

    def __post_init__(self) -> None:
        if not self.fuente or not str(self.fuente).strip():
            raise ValueError("un valor sin fuente no se guarda")
        if self.confianza is not None and not 0.0 <= self.confianza <= 1.0:
            raise ValueError(
                "confianza %r fuera de [0,1]: Model Match la reporta en "
                "porcentaje, hay que dividirla" % self.confianza
            )

    @property
    def peso(self) -> tuple[float, int, str]:
        """Para ordenar: confianza, luego prioridad de fuente, luego fecha."""
        return (
            self.confianza if self.confianza is not None else 0.5,
            PRIORIDAD_DE_FUENTE.get(self.fuente, 0),
            self.fecha.isoformat(),
        )

    def __str__(self) -> str:
        partes = ["%s" % self.valor, self.fuente, self.fecha.isoformat()]
        if self.confianza is not None:
            partes.append("conf %.0f%%" % (self.confianza * 100))
        if self.nota:
            partes.append(self.nota)
        return " · ".join(partes)


@dataclass
class Campo:
    """Todos los valores conocidos de un campo, con su procedencia.

    No hay setter. `agregar` acumula; nada borra.
    """

    nombre: str
    valores: list[Valor] = field(default_factory=list)

    def agregar(
        self,
        valor: Any,
        *,
        fuente: str,
        fecha: dt.date,
        confianza: float | None = None,
        nota: str | None = None,
    ) -> Valor:
        """Acumula un valor. Si ya existe ese valor de esa fuente, lo actualiza
        solo si la fecha es mas nueva -- eso no es sobrescribir un dato
        distinto, es refrescar el mismo."""
        nuevo = Valor(valor=valor, fuente=fuente, fecha=fecha,
                      confianza=confianza, nota=nota)
        for i, existente in enumerate(self.valores):
            if existente.valor == nuevo.valor and existente.fuente == nuevo.fuente:
                if nuevo.fecha >= existente.fecha:
                    self.valores[i] = nuevo
                return nuevo
        self.valores.append(nuevo)
        return nuevo

    def preferido(self) -> Valor | None:
        """El valor con el que operar. No borra los otros."""
        if not self.valores:
            return None
        return max(self.valores, key=lambda v: v.peso)

    def todos(self) -> list[Valor]:
        return sorted(self.valores, key=lambda v: v.peso, reverse=True)

    def distintos(self) -> list[Any]:
        vistos: list[Any] = []
        for v in self.todos():
            if v.valor not in vistos:
                vistos.append(v.valor)
        return vistos

    @property
    def en_conflicto(self) -> bool:
        return len(self.distintos()) > 1

    def conflictos(self) -> list[str]:
        """Los pares que no coinciden, listos para el log."""
        if not self.en_conflicto:
            return []
        por_valor: dict[Any, list[str]] = {}
        for v in self.todos():
            por_valor.setdefault(v.valor, []).append(
                "%s(%s%s)" % (
                    v.fuente, v.fecha.isoformat(),
                    ", conf %.0f%%" % (v.confianza * 100)
                    if v.confianza is not None else "",
                )
            )
        partes = ["%r desde %s" % (val, ", ".join(fuentes))
                  for val, fuentes in por_valor.items()]
        return ["%s tiene %d valores distintos: %s"
                % (self.nombre, len(por_valor), " | ".join(partes))]

    def a_dict(self) -> dict:
        """Para persistir. Se guardan TODOS los valores, no solo el preferido."""
        pref = self.preferido()
        return {
            "campo": self.nombre,
            "preferido": pref.valor if pref else None,
            "fuente_preferida": pref.fuente if pref else None,
            "en_conflicto": self.en_conflicto,
            "n_valores": len(self.valores),
            "valores": [
                {
                    "valor": v.valor,
                    "fuente": v.fuente,
                    "fecha": v.fecha.isoformat(),
                    "confianza": v.confianza,
                    "nota": v.nota,
                }
                for v in self.todos()
            ],
        }
