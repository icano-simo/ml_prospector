"""Las reglas de activacion, declaradas como datos.

Portadas **tal cual** desde el prototipo (`pacs_engine.py`, funcion
`qualifiers_de`) y desde el archivo 06 de la skill, que es su documentacion.
No se inventa ninguna y no se mejora ninguna: si se reescribe y se mejora a la
vez, despues no se sabe que se rompio.

Que cambia respecto del prototipo
---------------------------------
La forma, no el contenido. El prototipo es una cadena de `if/elif` dentro de una
funcion de 120 lineas; aca cada regla es un registro con condicion, qualifier,
intensidad, grado de evidencia y texto. Eso permite auditarlas, versionarlas y
discutirlas sin tocar codigo, y permite **una prueba por regla** en vez de una
por modulo.

La semantica de resolucion es la del archivo 06, que dice literalmente:

    Cuando varias reglas apuntan al mismo qualifier, **gana la de mayor
    intensidad**.

El prototipo usa `if/elif`, o sea **la primera que coincide**, que no es lo
mismo. Donde las dos difieren esta anotado en la regla con `DISCREPANCIA`, y el
efecto esta medido en `docs/etapa-1-esquema-y-motor.md`. No se elige una por
gusto: se declara la documentada, se mide la diferencia y se reporta.

El campo `origen`
-----------------
`propia` son estas: escritas a mano para operar con los nueve campos que da un
lote de Instagram. `matriz` seran las 124 reglas de inferencia de la matriz
PACS-H, que necesitan 88 campos del diccionario canonico. A medida que aparezcan
campos, las propias se reemplazan por las de la matriz, que son mejores. El
esquema y el motor ya distinguen las dos para que ese reemplazo sea un cambio de
datos y no una reescritura.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from pacs.guardas import GradoEvidencia

#: De donde sale la regla. Ver la nota de arriba.
Origen = Literal["propia", "matriz"]

#: Familia del qualifier. Decide el desempate al elegir el dolor primario.
Familia = Literal["P", "J", "G"]


@dataclass(frozen=True)
class Regla:
    """Una regla de activacion. Es un dato, no codigo.

    `condicion` recibe el registro del realtor ya normalizado y devuelve
    `True`, `False` o **`None`**. `None` significa *no se pudo evaluar porque
    falta el dato*, y es distinto de `False`: una regla que no se pudo evaluar
    no activa nada y **lo declara**, en vez de contarse como que no aplica.

    Es la segunda guardia del proyecto puesta donde se decide: nada se llena
    por descarte. La leccion de `estado_perfil = privado` fue exactamente esta:
    el codigo infirio privacidad de la ausencia de publicaciones, lo documento
    en un comentario, y afirmo igual. Los siete perfiles eran publicos.
    """

    id: str
    qualifier: str
    familia: Familia
    intensidad: int
    grado: GradoEvidencia
    texto: str
    condicion: Callable[[dict], bool | None]
    #: Campos del registro que la condicion lee. Se verifican contra ECOA antes
    #: de evaluar: ninguna regla puede apoyarse en apellido, etnia u origen.
    campos: tuple[str, ...]
    origen: Origen = "propia"
    #: Donde esta escrita y documentada.
    referencia: str = "skill/references/06-reglas-de-activacion.md"
    #: Nota cuando el prototipo hace otra cosa que la documentacion.
    discrepancia: str | None = None
    #: Gancho conversacional, cuando la regla lo determina.
    gancho: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.intensidad <= 3:
            raise ValueError("intensidad %r fuera de 0-3 en %s"
                             % (self.intensidad, self.id))
        if self.familia not in ("P", "J", "G"):
            raise ValueError("familia %r en %s" % (self.familia, self.id))
        if not self.campos:
            raise ValueError(
                "la regla %s no declara sus campos. Sin eso no se puede "
                "verificar contra ECOA ni saber por que no se evaluo." % self.id
            )


# ══════════════════════════════════════════════════════════════════════════════
# LECTORES DE CAMPO
# ══════════════════════════════════════════════════════════════════════════════
#
# Devuelven None cuando el dato falta, y las condiciones propagan ese None.
# Es lo que hace que "no se pudo evaluar" llegue distinto de "no aplica".

def _b(r: dict, campo: str) -> bool | None:
    """Un booleano del registro. None si el campo no esta o vale None."""
    v = r.get(campo)
    return None if v is None else bool(v)


def _n(r: dict, campo: str) -> float | None:
    """Un numero del registro. None si falta o no es numero.

    Los NaN de pandas entran aca como None a proposito: un NaN que se compara
    con `>=` devuelve False en silencio, que es justo la clase de falso
    negativo que este modulo existe para no tener.
    """
    v = r.get(campo)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _ge(r: dict, campo: str, umbral: float) -> bool | None:
    v = _n(r, campo)
    return None if v is None else v >= umbral


def _le(r: dict, campo: str, umbral: float) -> bool | None:
    v = _n(r, campo)
    return None if v is None else v <= umbral


def _y(*valores: bool | None) -> bool | None:
    """AND que propaga el desconocido.

    False gana sobre None: si una parte ya es falsa, el resultado es falso
    aunque falte la otra. None solo sobrevive si nada lo decidio.
    """
    if any(v is False for v in valores):
        return False
    if any(v is None for v in valores):
        return None
    return True


def _o(*valores: bool | None) -> bool | None:
    """OR que propaga el desconocido. True gana sobre None."""
    if any(v is True for v in valores):
        return True
    if any(v is None for v in valores):
        return None
    return False


def _no(v: bool | None) -> bool | None:
    return None if v is None else not v


# ══════════════════════════════════════════════════════════════════════════════
# LAS REGLAS
# ══════════════════════════════════════════════════════════════════════════════
#
# El id es `<QUALIFIER>-<n>`, numeradas por intensidad descendente igual que la
# tabla del archivo 06, para que la fila del doc y la fila del codigo se puedan
# poner una al lado de la otra.

REGLAS: tuple[Regla, ...] = (

    # ── P-Q01 · Pierde casos de nicho porque su lender los rechaza ───────────
    Regla(
        id="P-Q01-1", qualifier="P-Q01", familia="P", intensidad=3, grado="E0",
        texto="su bio menciona ITIN o trabajo por cuenta propia",
        campos=("ev2_itin", "ev2_self_employed"),
        condicion=lambda r: _o(_b(r, "ev2_itin"), _b(r, "ev2_self_employed")),
        gancho="P-N01 si es ITIN · P-081 si es self-employed",
    ),
    Regla(
        id="P-Q01-2", qualifier="P-Q01", familia="P", intensidad=2, grado="E1",
        texto="su bio menciona un programa de gobierno o ayuda de enganche",
        campos=("ev2_fha_gob", "ev2_dpa_enganche"),
        condicion=lambda r: _o(_b(r, "ev2_fha_gob"), _b(r, "ev2_dpa_enganche")),
        gancho="P-082",
    ),
    Regla(
        id="P-Q01-3", qualifier="P-Q01", familia="P", intensidad=2, grado="E1",
        texto="se posiciona en español hacia el primer comprador",
        campos=("R5_espanol", "R4_comunidad_fhb"),
        condicion=lambda r: _y(_ge(r, "R5_espanol", 8),
                               _ge(r, "R4_comunidad_fhb", 7)),
        gancho="P-082",
    ),
    Regla(
        id="P-Q01-4", qualifier="P-Q01", familia="P", intensidad=1, grado="E3",
        texto="señal de afinidad latina sin nicho documental declarado",
        campos=("R5_espanol", "R7_identidad_hispana"),
        condicion=lambda r: _o(_ge(r, "R5_espanol", 6),
                               _ge(r, "R7_identidad_hispana", 8)),
        gancho="P-082",
    ),

    # ── P-Q14 · Sus clientes chocan con la barrera de idioma ────────────────
    Regla(
        id="P-Q14-1", qualifier="P-Q14", familia="P", intensidad=3, grado="E0",
        texto="declara atención en español y además escribe en español",
        campos=("ev2_espanol_decl", "ev_caracteres_espanol"),
        condicion=lambda r: _y(_b(r, "ev2_espanol_decl"),
                               _ge(r, "ev_caracteres_espanol", 1)),
    ),
    Regla(
        id="P-Q14-2", qualifier="P-Q14", familia="P", intensidad=2, grado="E1",
        texto="contenido publicado en español",
        campos=("R5_espanol",),
        condicion=lambda r: _ge(r, "R5_espanol", 6),
    ),
    Regla(
        id="P-Q14-3", qualifier="P-Q14", familia="P", intensidad=1, grado="E3",
        texto="identidad hispana sin evidencia de contenido en español",
        campos=("R7_identidad_hispana",),
        condicion=lambda r: _ge(r, "R7_identidad_hispana", 8),
    ),

    # ── P-Q13 · Costo reputacional comunitario ──────────────────────────────
    Regla(
        id="P-Q13-1", qualifier="P-Q13", familia="P", intensidad=2, grado="E1",
        texto="lenguaje de comunidad en su propio contenido",
        campos=("ev2_comunidad", "R5_espanol", "R7_identidad_hispana"),
        condicion=lambda r: _y(
            _b(r, "ev2_comunidad"),
            _o(_ge(r, "R5_espanol", 6), _ge(r, "R7_identidad_hispana", 8)),
        ),
    ),
    Regla(
        id="P-Q13-2", qualifier="P-Q13", familia="P", intensidad=1, grado="E3",
        texto="marcadores de familia o fe sin narrativa comunitaria explícita",
        campos=("ev2_fe_familia", "R7_identidad_hispana"),
        condicion=lambda r: _y(_b(r, "ev2_fe_familia"),
                               _ge(r, "R7_identidad_hispana", 8)),
    ),

    # ── P-Q07 · Capital de entrada ──────────────────────────────────────────
    Regla(
        id="P-Q07-1", qualifier="P-Q07", familia="P", intensidad=3, grado="E0",
        texto="su bio menciona down payment, DPA o enganche",
        campos=("ev2_dpa_enganche",),
        condicion=lambda r: _b(r, "ev2_dpa_enganche"),
    ),
    Regla(
        id="P-Q07-2", qualifier="P-Q07", familia="P", intensidad=2, grado="E1",
        texto="el enganche es el cuello de botella típico de ese perfil",
        campos=("ev2_primera_casa",),
        condicion=lambda r: _b(r, "ev2_primera_casa"),
        discrepancia=(
            "El prototipo evalua la regla de intensidad 1 (P-Q07-3) ANTES que "
            "esta, con `elif`, asi que un agente que cumple las dos se queda "
            "con 1. El archivo 06 dice que gana la de mayor intensidad, o sea "
            "2. Aca gana 2. Efecto medido en docs/etapa-1-esquema-y-motor.md."
        ),
    ),
    Regla(
        id="P-Q07-3", qualifier="P-Q07", familia="P", intensidad=1, grado="E3",
        texto="estado caro más posicionamiento a primer comprador",
        campos=("E6_asequibilidad", "R4_comunidad_fhb"),
        condicion=lambda r: _y(_le(r, "E6_asequibilidad", 3),
                               _ge(r, "R4_comunidad_fhb", 7)),
    ),

    # ── P-Q06 · La cuota que enfría al cliente ──────────────────────────────
    Regla(
        id="P-Q06-1", qualifier="P-Q06", familia="P", intensidad=2, grado="E1",
        texto="primera compra en un mercado poco asequible",
        campos=("ev2_primera_casa", "E6_asequibilidad"),
        condicion=lambda r: _y(_b(r, "ev2_primera_casa"),
                               _le(r, "E6_asequibilidad", 5)),
    ),
    Regla(
        id="P-Q06-2", qualifier="P-Q06", familia="P", intensidad=1, grado="E3",
        texto="estado con asequibilidad crítica",
        campos=("E6_asequibilidad",),
        condicion=lambda r: _le(r, "E6_asequibilidad", 3),
    ),

    # ── P-Q12 · Precalificación ─────────────────────────────────────────────
    Regla(
        id="P-Q12-1", qualifier="P-Q12", familia="P", intensidad=3, grado="E0",
        texto="su bio menciona pre-aprobación o precalificación",
        campos=("ev2_precalificacion",),
        condicion=lambda r: _b(r, "ev2_precalificacion"),
    ),
    Regla(
        id="P-Q12-2", qualifier="P-Q12", familia="P", intensidad=2, grado="E1",
        texto="educa a compradores primerizos: hoy filtra leads a mano",
        campos=("ev2_educacion", "ev2_primera_casa"),
        condicion=lambda r: _y(_b(r, "ev2_educacion"),
                               _b(r, "ev2_primera_casa")),
    ),

    # ── P-Q17 · Militar y veterano ──────────────────────────────────────────
    Regla(
        id="P-Q17-1", qualifier="P-Q17", familia="P", intensidad=3, grado="E0",
        texto="su bio menciona VA, veterano o militar",
        campos=("ev2_va_militar",),
        condicion=lambda r: _b(r, "ev2_va_militar"),
    ),

    # ── P-Q09 · Inversionista ───────────────────────────────────────────────
    Regla(
        id="P-Q09-1", qualifier="P-Q09", familia="P", intensidad=3, grado="E0",
        texto="inversión declarada como línea de negocio",
        campos=("ev2_inversion", "ev_hits_lujo_inversion"),
        condicion=lambda r: _y(_b(r, "ev2_inversion"),
                               _ge(r, "ev_hits_lujo_inversion", 1)),
        discrepancia=(
            "El prototipo le da 3 a inversion CON marcadores de lujo y 2 a "
            "inversion SIN ellos, pero el propio archivo 06 advierte que "
            "«inversión + lujo suele ser anti-ICP, no oportunidad». O sea que "
            "la combinacion que el texto marca como señal de alarma es la que "
            "recibe la intensidad mas alta. Se porta tal cual y se deja "
            "anotado: cambiarlo es una decision de metodologia, no de codigo."
        ),
    ),
    Regla(
        id="P-Q09-2", qualifier="P-Q09", familia="P", intensidad=2, grado="E1",
        texto="menciona inversión o renta sin marcadores de lujo",
        campos=("ev2_inversion", "ev_hits_lujo_inversion"),
        condicion=lambda r: _y(
            _b(r, "ev2_inversion"),
            _no(_ge(r, "ev_hits_lujo_inversion", 1)),
        ),
    ),

    # ── P-Q19 · Reingreso tras evento de crédito ────────────────────────────
    Regla(
        id="P-Q19-1", qualifier="P-Q19", familia="P", intensidad=3, grado="E0",
        texto="su bio menciona crédito o reparación de crédito",
        campos=("ev2_credito",),
        condicion=lambda r: _b(r, "ev2_credito"),
    ),

    # ── P-Q20 · Ingreso alto sin W-2 ────────────────────────────────────────
    Regla(
        id="P-Q20-1", qualifier="P-Q20", familia="P", intensidad=2, grado="E1",
        texto="cuenta propia más segmento de valor alto",
        campos=("ev2_self_employed", "ev_hits_lujo_inversion"),
        condicion=lambda r: _y(_b(r, "ev2_self_employed"),
                               _ge(r, "ev_hits_lujo_inversion", 1)),
    ),

    # ── P-Q10 · Producción de contenido ─────────────────────────────────────
    Regla(
        id="P-Q10-1", qualifier="P-Q10", familia="P", intensidad=2, grado="E1",
        texto="el costo de producción es propio",
        campos=("ev2_video_contenido",),
        condicion=lambda r: _b(r, "ev2_video_contenido"),
    ),
    Regla(
        id="P-Q10-2", qualifier="P-Q10", familia="P", intensidad=2, grado="E2",
        texto=("audiencia construida sin señal de producción sostenida: "
               "la carga la lleva él o ella"),
        campos=("ig_seguidores", "ev2_video_contenido", "ev2_educacion"),
        condicion=lambda r: _y(
            _ge(r, "ig_seguidores", 1000),
            _no(_o(_b(r, "ev2_video_contenido"), _b(r, "ev2_educacion"))),
        ),
    ),

    # ── P-Q11 · Retención post-cierre ───────────────────────────────────────
    Regla(
        id="P-Q11-1", qualifier="P-Q11", familia="P", intensidad=2, grado="E1",
        texto="base instalada sin sistema de retención visible",
        campos=("ev2_volumen_declarado_bio",),
        condicion=lambda r: _ge(r, "ev2_volumen_declarado_bio", 50),
    ),
    Regla(
        id="P-Q11-2", qualifier="P-Q11", familia="P", intensidad=1, grado="E3",
        texto="base que se enfría sin sistema de retención",
        campos=("unidades_ano",),
        condicion=lambda r: _ge(r, "unidades_ano", 20),
    ),

    # ── P-Q21 · Co-marketing y RESPA ────────────────────────────────────────
    Regla(
        id="P-Q21-1", qualifier="P-Q21", familia="P", intensidad=1, grado="E3",
        texto="co-marketing informal probable, riesgo RESPA sin verificar",
        campos=("ev2_equipo", "ig_seguidores"),
        condicion=lambda r: _y(_b(r, "ev2_equipo"),
                               _ge(r, "ig_seguidores", 3000)),
    ),

    # ── J-Q01 · Dependencia del financiamiento · GATING ─────────────────────
    Regla(
        id="J-Q01-1", qualifier="J-Q01", familia="J", intensidad=3, grado="E0",
        texto="se declara agente de compradores",
        campos=("ev2_buy_side", "ev2_listing_side"),
        condicion=lambda r: _y(_b(r, "ev2_buy_side"),
                               _no(_b(r, "ev2_listing_side"))),
    ),
    Regla(
        id="J-Q01-2", qualifier="J-Q01", familia="J", intensidad=2, grado="E1",
        texto="libro predominantemente buyside",
        campos=("ev2_primera_casa",),
        condicion=lambda r: _b(r, "ev2_primera_casa"),
    ),
    Regla(
        id="J-Q01-3", qualifier="J-Q01", familia="J", intensidad=1, grado="E1",
        texto="menor dependencia del financiamiento del comprador",
        campos=("ev2_listing_side", "ev2_buy_side"),
        condicion=lambda r: _y(_b(r, "ev2_listing_side"),
                               _no(_b(r, "ev2_buy_side"))),
    ),

    # ── J-Q03 · Percepción dentro de su comunidad ───────────────────────────
    Regla(
        id="J-Q03-1", qualifier="J-Q03", familia="J", intensidad=3, grado="E0",
        texto="construye su marca sobre resolver dentro de su comunidad",
        campos=("ev2_comunidad", "ev2_testimonio"),
        condicion=lambda r: _y(_b(r, "ev2_comunidad"), _b(r, "ev2_testimonio")),
    ),
    Regla(
        id="J-Q03-2", qualifier="J-Q03", familia="J", intensidad=2, grado="E1",
        texto="lenguaje de comunidad recurrente",
        campos=("ev2_comunidad",),
        condicion=lambda r: _b(r, "ev2_comunidad"),
    ),

    # ── J-Q04 · Audiencia propia como estrategia ────────────────────────────
    Regla(
        id="J-Q04-1", qualifier="J-Q04", familia="J", intensidad=3, grado="E1",
        texto="audiencia propia grande",
        campos=("ig_seguidores", "ev_bio_legible"),
        condicion=lambda r: _y(_ge(r, "ig_seguidores", 10000),
                               _b(r, "ev_bio_legible")),
        discrepancia=(
            "CONFLICTO ENTRE DOS DOCUMENTOS DE LA METODOLOGIA, no una decision "
            "mia. El archivo 06 declara esta regla con intensidad 3 y grado E1, "
            "y el techo del archivo 05 dice que E1 no pasa de 2. El prototipo "
            "emite 3 porque no aplica ningun techo: la funcion no existe ahi. "
            "Aca se declara 3 -- que es lo que dice la regla-- y el techo la "
            "recorta a 2, dejando la nota en `nota_techo` de la activacion. "
            "Resolverlo es una decision de metodologia: o la regla baja a 2, o "
            "el archivo 05 declara la excepcion E1->3 por escrito, que es el "
            "mecanismo que `intensidad_con_techo` ya soporta."
        ),
    ),
    Regla(
        id="J-Q04-2", qualifier="J-Q04", familia="J", intensidad=2, grado="E1",
        texto="audiencia propia construida",
        campos=("ig_seguidores", "ev_bio_legible"),
        condicion=lambda r: _y(_ge(r, "ig_seguidores", 3000),
                               _b(r, "ev_bio_legible")),
    ),
    Regla(
        id="J-Q04-3", qualifier="J-Q04", familia="J", intensidad=2, grado="E1",
        texto="producción declarada",
        campos=("ev2_video_contenido", "ev2_educacion"),
        condicion=lambda r: _o(_b(r, "ev2_video_contenido"),
                               _b(r, "ev2_educacion")),
    ),

    # ── J-Q05 · Estacionalidad ──────────────────────────────────────────────
    Regla(
        id="J-Q05-1", qualifier="J-Q05", familia="J", intensidad=1, grado="E3",
        texto="estado con caída invernal declarada",
        campos=("E3_urgencia_sept",),
        condicion=lambda r: _ge(r, "E3_urgencia_sept", 6.5),
    ),

    # ── J-Q06 · Equipo ──────────────────────────────────────────────────────
    Regla(
        id="J-Q06-1", qualifier="J-Q06", familia="J", intensidad=2, grado="E1",
        texto="menciona equipo o team en su perfil",
        campos=("ev2_equipo",),
        condicion=lambda r: _b(r, "ev2_equipo"),
    ),

    # ── G-Q04 · Autoridad de nicho ──────────────────────────────────────────
    Regla(
        id="G-Q04-1", qualifier="G-Q04", familia="G", intensidad=2, grado="E1",
        texto="activo de autoridad ya construido",
        campos=("ig_seguidores",),
        condicion=lambda r: _ge(r, "ig_seguidores", 10000),
    ),
)


#: J-Q01 nunca puede ser el dolor primario: es la compuerta que decide si algun
#: angulo hipotecario tiene sentido. Archivo 06, seleccion del dolor primario.
QUALIFIER_GATING = "J-Q01"

#: Orden de familia para desempatar a igual intensidad: P sobre J sobre G.
ORDEN_FAMILIA = {"P": 0, "J": 1, "G": 2}


def por_qualifier() -> dict[str, list[Regla]]:
    """Las reglas agrupadas, en el orden en que estan declaradas."""
    salida: dict[str, list[Regla]] = {}
    for regla in REGLAS:
        salida.setdefault(regla.qualifier, []).append(regla)
    return salida


def verificar_catalogo() -> None:
    """Invariantes del catalogo. Corre en el import de las pruebas.

    No valida que las reglas sean buenas -- eso no lo puede hacer el codigo.
    Valida que sean auditables: ids unicos, campos declarados, intensidades en
    rango y ninguna apoyada en un campo prohibido por ECOA.
    """
    from pacs.guardas import verificar_entradas_de_inferencia

    vistos: set[str] = set()
    for regla in REGLAS:
        if regla.id in vistos:
            raise ValueError("id de regla repetido: %s" % regla.id)
        vistos.add(regla.id)
        if not regla.id.startswith(regla.qualifier):
            raise ValueError(
                "el id %s no empieza con su qualifier %s: el id es lo que "
                "permite poner la fila del doc al lado de la del codigo"
                % (regla.id, regla.qualifier)
            )
        if regla.familia != regla.qualifier[0]:
            raise ValueError(
                "familia %s no coincide con el prefijo de %s"
                % (regla.familia, regla.qualifier)
            )
        verificar_entradas_de_inferencia(set(regla.campos), regla.qualifier)
