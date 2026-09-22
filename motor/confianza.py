"""La confianza, como lista de terminos. **Sin numero compuesto.**

Por que no hay un porcentaje
----------------------------
El archivo 06 propone `0,15 + 0,07×categorias + 0,06×qualifiers + 0,10 si bio
legible`, con tope 0,95, y dice de sus propios coeficientes que son arbitrarios
y estan escritos ahi para que alguien pueda discutirlos.

Un 72% no se puede discutir: parece medido. La lista dice exactamente lo mismo
y muestra de donde sale:

    tres categorias de señal presentes · dos qualifiers en fuerza 2 o mas ·
    bio legible · Model Match capturado

Lo que no es arbitrario es el principio del archivo 06, y se conserva entero:
**la confianza mide cuantas ventanas distintas tuviste al mismo sujeto**, no que
tan alto salio el numero.

El nivel ALTA/MEDIA/BAJA si se conserva, porque hay que poder ordenar una lista
de prospeccion. Pero sale de contar terminos presentes, no de sumar pesos, y
cada termino queda al lado para que el nivel se pueda auditar.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from motor.evaluar import Evaluacion

#: Las categorias de señal de la metodologia. S1-S10.
CATEGORIAS = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10")

#: Cuantos terminos hacen falta para cada nivel. Son cortes sobre un conteo de
#: cosas presentes, no umbrales sobre una suma ponderada: se pueden discutir
#: mirando la lista.
MIN_TERMINOS_ALTA = 4
MIN_TERMINOS_MEDIA = 2


@dataclass(frozen=True)
class Termino:
    """Una ventana al sujeto. Presente o ausente, con su cuenta."""

    nombre: str
    presente: bool
    detalle: str

    def __str__(self) -> str:
        return self.detalle


@dataclass
class Confianza:
    """La confianza como lista. `nivel` es para ordenar; `terminos` es la razon."""

    terminos: list[Termino] = field(default_factory=list)

    @property
    def presentes(self) -> list[Termino]:
        return [t for t in self.terminos if t.presente]

    @property
    def nivel(self) -> str:
        n = len(self.presentes)
        if n >= MIN_TERMINOS_ALTA:
            return "ALTA"
        if n >= MIN_TERMINOS_MEDIA:
            return "MEDIA"
        return "BAJA"

    def frase(self) -> str:
        """La linea que va al dossier, en español llano."""
        if not self.presentes:
            return "sin ninguna ventana al sujeto"
        return " · ".join(t.detalle for t in self.presentes)

    def a_dict(self) -> dict:
        return {
            "nivel": self.nivel,
            "n_terminos_presentes": len(self.presentes),
            "n_terminos_evaluados": len(self.terminos),
            "terminos": [
                {"nombre": t.nombre, "presente": t.presente, "detalle": t.detalle}
                for t in self.terminos
            ],
            "frase": self.frase(),
        }


def evaluar_confianza(
    evaluacion: Evaluacion,
    *,
    categorias_acreditadas: set[str] | None = None,
    bio_legible: bool | None = None,
    modelmatch_capturado: bool | None = None,
) -> Confianza:
    """Los cuatro terminos, cada uno con su cuenta al lado.

    `categorias_acreditadas` son las S1-S10 con dato real. `None` en cualquiera
    de los tres argumentos significa *no se verifico*, y un termino que no se
    verifico cuenta como ausente **y lo dice**: no se llena por descarte.
    """
    cats = categorias_acreditadas or set()
    desconocidas = {c for c in cats if c not in CATEGORIAS}
    if desconocidas:
        raise ValueError("categorias fuera de S1-S10: %s" % sorted(desconocidas))

    fuertes = [a for a in evaluacion.activaciones if a.intensidad >= 2]

    return Confianza(terminos=[
        Termino(
            "categorias_de_senal",
            presente=len(cats) >= 3,
            detalle=("%d categorías de señal presentes (%s)"
                     % (len(cats), ", ".join(sorted(cats)) or "ninguna")),
        ),
        Termino(
            "qualifiers_fuertes",
            presente=len(fuertes) >= 2,
            detalle=("%d qualifiers en fuerza 2 o más (%s)"
                     % (len(fuertes),
                        ", ".join(a.qualifier for a in fuertes) or "ninguno")),
        ),
        Termino(
            "bio_legible",
            presente=bio_legible is True,
            detalle=("bio legible" if bio_legible is True
                     else "bio no legible" if bio_legible is False
                     else "no se verificó si la bio es legible"),
        ),
        Termino(
            "modelmatch",
            presente=modelmatch_capturado is True,
            detalle=("Model Match capturado" if modelmatch_capturado is True
                     else "sin captura de Model Match" if modelmatch_capturado is False
                     else "no se verificó si hay captura de Model Match"),
        ),
    ])
