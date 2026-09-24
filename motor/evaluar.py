"""El motor: aplica las reglas declaradas y devuelve la cadena de evidencia.

Nunca devuelve un valor suelto. Cada qualifier activado sale con la regla que
lo disparo, los campos que leyo, el grado de evidencia, si la intensidad se
recorto por el techo, y el acto de habla que le corresponde al copy.

Y cada evaluacion sale con la lista de reglas que **no se pudieron evaluar**,
con el campo que faltaba. Una regla que no se evaluo no es una regla que no
aplica, y esa distincion es la segunda guardia del proyecto.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field

from motor.reglas import (
    ORDEN_FAMILIA,
    QUALIFIER_GATING,
    REGLAS,
    Regla,
)
from pacs.guardas import (
    GradoEvidencia,
    acto_de_habla,
    intensidad_con_techo,
)

#: Version del catalogo de reglas. Cambia cuando cambian las reglas, y queda
#: guardada en cada evaluacion: sin esto, dentro de tres meses no se sabe con
#: que reglas se produjo un diagnostico viejo.
#: Sube cuando cambia CUALQUIER cosa que el lector vea, no solo la lógica: el
#: `texto` de una regla es lo que el BD lee en la ficha, así que corregirlo es
#: un cambio declarado.
#:
#: `-compuertas` es el 2026-09-23 por la tarde, y cambia dos cosas que un
#: diagnóstico viejo no tiene: J-Q01 sale del registro buy/sell de Model Match
#: y cierra la apertura hipotecaria en <= 1, y P-Q14 sale del idioma medido del
#: muro y deja la bio sola en 1/E1. Una evaluación de antes y una de después no
#: son comparables en esos dos números, y sin la versión nadie podría saberlo.
VERSION_REGLAS = "2026.09.23-compuertas"


def huella_del_catalogo() -> str:
    """Huella de las reglas activas. Detecta un cambio no declarado.

    Si alguien toca una intensidad y no sube `VERSION_REGLAS`, las evaluaciones
    viejas y las nuevas quedan indistinguibles. La huella lo delata.
    """
    partes = [
        "%s|%s|%d|%s|%s|%s" % (r.id, r.qualifier, r.intensidad, r.grado,
                               r.origen, r.texto)
        for r in REGLAS
    ]
    return hashlib.sha256("\n".join(partes).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Activacion:
    """Un qualifier activado, con todo lo que lo sostiene."""

    qualifier: str
    familia: str
    intensidad: int
    grado: GradoEvidencia
    texto: str
    regla_id: str
    origen: str
    referencia: str
    #: Campos del registro que la regla leyo, con su valor. La respuesta a
    #: "de donde sacaste eso".
    campos_leidos: dict
    #: Nota si el techo por grado de evidencia recorto la intensidad.
    nota_techo: str | None = None
    #: Intensidad que la regla proponia antes del techo.
    intensidad_propuesta: int | None = None
    #: AFIRMA solo con intensidad 3 y E0. Todo lo demas PREGUNTA.
    acto: str = "PREGUNTA"
    #: Otras reglas del mismo qualifier que tambien dieron True.
    tambien_activaron: tuple[str, ...] = ()
    discrepancia: str | None = None
    gancho: str | None = None


@dataclass(frozen=True)
class ReglaNoEvaluada:
    """Una regla que no se pudo evaluar. NO es una regla que no aplica."""

    regla_id: str
    qualifier: str
    campos_faltantes: tuple[str, ...]
    motivo: str = "falta el dato de entrada"


@dataclass
class Evaluacion:
    """El resultado completo de una corrida del motor sobre un realtor.

    Se persiste entero, con timestamp, append-only. No es auditoria: es la
    infraestructura de la correlacion futura. Dentro de tres meses la pregunta
    va a ser que diagnostico predijo conversion, y sin el historico no se puede
    responder.
    """

    realtor_id: str
    evaluado_en: str
    version_reglas: str
    huella_reglas: str
    activaciones: list[Activacion] = field(default_factory=list)
    no_evaluadas: list[ReglaNoEvaluada] = field(default_factory=list)
    dolor_primario: str | None = None
    dolores_secundarios: tuple[str, ...] = ()
    gating: Activacion | None = None
    #: Con que abre el primer mensaje cuando no hay ningun dolor de familia P.
    apertura: str | None = None
    #: J-Q y G-Q activados. No son dolores: son moduladores. Elevan un angulo,
    #: dan contexto y aparecen en el toque 5. Nunca abren la conversacion.
    moduladores: tuple[str, ...] = ()
    #: Campos del registro que llegaron vacios. El denominador de todo lo demas.
    campos_ausentes: tuple[str, ...] = ()

    def a_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True,
                          default=str)


def evaluar(
    registro: dict,
    *,
    realtor_id: str,
    reglas: tuple[Regla, ...] = REGLAS,
    ahora: dt.datetime | None = None,
) -> Evaluacion:
    """Aplica todas las reglas a un registro y devuelve la evaluacion completa.

    La resolucion es la del archivo 06: **cuando varias reglas apuntan al mismo
    qualifier, gana la de mayor intensidad**. A igual intensidad gana la que
    esta declarada primero, que es la del grado de evidencia mas fuerte porque
    asi estan ordenadas.

    El prototipo usa `if/elif`, o sea la primera que coincide. Donde las dos
    difieren esta anotado en la regla y medido en el documento de la etapa.
    """
    ahora = ahora or dt.datetime.now(dt.timezone.utc)

    candidatas: dict[str, list[tuple[Regla, dict]]] = {}
    no_evaluadas: list[ReglaNoEvaluada] = []

    for regla in reglas:
        veredicto = regla.condicion(registro)
        leidos = {c: registro.get(c) for c in regla.campos}

        if veredicto is None:
            faltan = tuple(c for c in regla.campos if registro.get(c) is None)
            no_evaluadas.append(ReglaNoEvaluada(
                regla_id=regla.id, qualifier=regla.qualifier,
                campos_faltantes=faltan or regla.campos,
            ))
            continue
        if veredicto:
            candidatas.setdefault(regla.qualifier, []).append((regla, leidos))

    activaciones: list[Activacion] = []
    for qualifier, lista in candidatas.items():
        # Gana la de mayor intensidad. El indice en REGLAS desempata, y como
        # estan declaradas por intensidad descendente eso equivale a preferir
        # el grado de evidencia mas fuerte.
        ganadora, leidos = min(
            lista, key=lambda par: (-par[0].intensidad, reglas.index(par[0]))
        )
        final, nota = intensidad_con_techo(ganadora.intensidad, ganadora.grado)
        activaciones.append(Activacion(
            qualifier=qualifier,
            familia=ganadora.familia,
            intensidad=final,
            grado=ganadora.grado,
            texto=ganadora.texto,
            regla_id=ganadora.id,
            origen=ganadora.origen,
            referencia=ganadora.referencia,
            campos_leidos=leidos,
            nota_techo=nota,
            intensidad_propuesta=ganadora.intensidad,
            acto=acto_de_habla(final, ganadora.grado),
            tambien_activaron=tuple(
                r.id for r, _ in lista if r.id != ganadora.id
            ),
            discrepancia=ganadora.discrepancia,
            gancho=ganadora.gancho,
        ))

    gating = next((a for a in activaciones if a.qualifier == QUALIFIER_GATING),
                  None)
    dolores = _ordenar_dolores(activaciones)

    # ── LA COMPUERTA J-Q01, APLICADA ────────────────────────────────────────
    #
    # J-Q01 mide cuanto depende su negocio del financiamiento del comprador.
    # Con J-Q01 <= 1 --seller heavy-- ningun dolor hipotecario puede ser el
    # primario: el angulo no le aplica, porque su negocio no pasa por ahi.
    #
    # Estaba declarado como compuerta y no se aplicaba. Aaron Gaston cierra 3
    # del lado comprador y 6 del vendedor, J-Q01 = 1, y el motor le ponia P-Q06
    # como dolor primario -- un angulo hipotecario a alguien que vive de
    # listings.
    #
    # Los dolores NO se borran: siguen en `activaciones` y pasan a secundarios.
    # Lo que cambia es que ninguno se presenta como el primario, y la apertura
    # lo dice.
    sin_apertura = bool(gating and gating.intensidad <= UMBRAL_APERTURA)
    if sin_apertura:
        dolores = [q for q in dolores if not q.startswith("P-")]

    campos_declarados = {c for r in reglas for c in r.campos}
    ausentes = tuple(sorted(
        c for c in campos_declarados if registro.get(c) is None
    ))

    return Evaluacion(
        realtor_id=realtor_id,
        evaluado_en=ahora.isoformat(timespec="seconds"),
        version_reglas=VERSION_REGLAS,
        huella_reglas=huella_del_catalogo(),
        activaciones=sorted(
            activaciones,
            key=lambda a: (-a.intensidad, ORDEN_FAMILIA[a.familia], a.qualifier),
        ),
        no_evaluadas=sorted(no_evaluadas, key=lambda n: n.regla_id),
        dolor_primario=dolores[0] if dolores else None,
        dolores_secundarios=tuple(dolores[1:3]),
        gating=gating,
        apertura=(APERTURA_SIN_HIPOTECA if sin_apertura and not dolores
                  else None if dolores else APERTURA_SIN_DOLOR),
        moduladores=tuple(
            a.qualifier for a in sorted(
                (x for x in activaciones
                 if x.familia != "P" and x.qualifier != QUALIFIER_GATING),
                key=lambda a: (-a.intensidad, ORDEN_FAMILIA[a.familia],
                               a.qualifier),
            )
        ),
        campos_ausentes=ausentes,
    )


def _ordenar_dolores(activaciones: list[Activacion]) -> list[str]:
    """Selecciona el dolor primario. **Solo familia P.**

    Decision del 2026-09-22, a favor del prototipo y contra el archivo 06, que
    estaba mal escrito. El motivo importa mas que la regla:

        El dolor primario es lo que ABRE la conversacion. Un J-Q no es un dolor:
        es un trabajo por hacer. Abrir un primer mensaje con «construyes
        audiencia como estrategia deliberada» no le duele a nadie -- le suena a
        halago o a nada.

    Los J-Q y los G-Q son **moduladores**: elevan un angulo, dan contexto,
    aparecen en el toque 5. Nunca son la apertura.

    El caso que lo ilustra: SINDY MATA pasaba de P-Q11 a J-Q03 con la regla del
    archivo 06. «Quiere ser percibida como la que resuelve en su comunidad» no
    es una apertura; «pierde el contacto despues del cierre» si.

    Si ningun P se activo **no hay dolor primario**, y el primer mensaje abre
    con la pregunta de cierre de brecha, que es la del lender.
    """
    elegibles = [
        a for a in activaciones
        if a.familia == "P" and a.qualifier != QUALIFIER_GATING
    ]
    elegibles.sort(key=lambda a: (-a.intensidad, a.qualifier))
    return [a.qualifier for a in elegibles]


#: Cuando no hay ningun dolor de familia P, el primer mensaje abre con esto.
#: No es un dolor diagnosticado: es la pregunta que cierra la brecha.
APERTURA_SIN_DOLOR = "pregunta_de_cierre_de_brecha_lender"

#: Con J-Q01 en esta intensidad o menos, su negocio NO pasa por el
#: financiamiento del comprador y ningun angulo hipotecario le aplica.
UMBRAL_APERTURA = 1

#: Lo que se dice en vez de un dolor primario cuando la compuerta cierra.
#: No es «no lo sabemos»: se sabe, y lo que se sabe es que este angulo no va.
APERTURA_SIN_HIPOTECA = "sin_apertura_hipotecaria"
