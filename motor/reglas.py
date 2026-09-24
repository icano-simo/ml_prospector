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


def _tiene(r: dict, campo: str) -> bool:
    """¿Hay dato en este campo? Devuelve bool, NO tri-estado, a proposito.

    Es la unica lectura que puede decir `False` sobre una ausencia, porque su
    pregunta ES la ausencia. Se usa para las reglas que eligen entre dos
    fuentes -- "usa la del libro solo si no hay Model Match"-- donde `None`
    dejaria la regla sin evaluar justamente cuando el respaldo aplica.
    """
    return _n(r, campo) is not None


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


def _igual(r: dict, campo: str, valor: str) -> bool | None:
    """Comparacion exacta contra un valor. None si el campo falta.

    Existe para las reglas que necesitan EVIDENCIA AFIRMATIVA de un estado, no
    la ausencia de su contrario. Ver P-Q10-2.
    """
    v = r.get(campo)
    return None if v is None else str(v) == valor


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
        texto="su bio menciona un programa de gobierno o down payment assistance",
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
        texto="publica en español sin nicho documental declarado",
        # R7 salio el 2026-09-23: se calculaba desde el apellido y el nombre de
        # pila. Era la otra rama de este OR, asi que la regla queda MAS
        # ESTRECHA -- 987 activaciones pasan a 329-- y eso es lo correcto: las
        # 658 que se caen se activaban por como se llama la persona.
        # El enunciado tambien cambia: decia «afinidad latina», que era lo que
        # R7 pretendia medir. Lo que queda medido es que publica en español.
        campos=("R5_espanol",),
        condicion=lambda r: _ge(r, "R5_espanol", 6),
        gancho="P-082",
    ),

    # ── P-Q14 · Sus clientes chocan con la barrera de idioma ────────────────
    #
    # CUANDO INSTAGRAM MIDIO, MANDA INSTAGRAM. Un muro utilizable con 10 posts
    # o mas es una medicion del idioma en que publica de verdad; la bio es una
    # frase sobre si mismo. Ochoa publica 0 de 20 en español y su bio declara
    # atencion en español: el motor le ponia P-Q14 = 3 y AFIRMA.
    #
    # `combinar_con_el_libro` no podia arreglarlo -- no pisa un True del libro
    # con un False-- y esta bien que no lo haga: la correccion va aca, en la
    # regla, donde queda escrito cual gano y por que.
    #
    # Sin medicion, la bio sola llega a 1/E1 y no mas. Es una declaracion de
    # intencion sin muro que la sostenga, y 3/E0 la convertia en AFIRMA.
    Regla(
        id="P-Q14-IG", qualifier="P-Q14", familia="P", intensidad=3, grado="E0",
        texto="publica en español en su propio muro",
        campos=("ig_idioma_es", "ig_idioma_posts"),
        condicion=lambda r: _b(r, "ig_idioma_es"),
    ),
    Regla(
        id="P-Q14-1", qualifier="P-Q14", familia="P", intensidad=1, grado="E1",
        texto="declara atención en español en su bio",
        campos=("ev2_espanol_decl", "ev_caracteres_espanol", "ig_idioma_es"),
        condicion=lambda r: _y(_no(_tiene(r, "ig_idioma_es")),
                               _y(_b(r, "ev2_espanol_decl"),
                                  _ge(r, "ev_caracteres_espanol", 1))),
    ),
    Regla(
        id="P-Q14-2", qualifier="P-Q14", familia="P", intensidad=1, grado="E1",
        texto="contenido publicado en español",
        campos=("R5_espanol", "ig_idioma_es"),
        condicion=lambda r: _y(_no(_tiene(r, "ig_idioma_es")),
                               _ge(r, "R5_espanol", 6)),
    ),
    # P-Q14-3 ELIMINADA el 2026-09-23. Decia «identidad hispana sin evidencia
    # de contenido en español» y se activaba SOLO con `R7 >= 8`, o sea solo por
    # el apellido y el nombre de pila. Su propio enunciado admitia que no habia
    # evidencia de idioma: la unica señal era como se llama la persona.
    # 722 activaciones. Ver docs/r7-identidad-hispana.md.

    # ── P-Q13 · Costo reputacional comunitario ──────────────────────────────
    Regla(
        id="P-Q13-1", qualifier="P-Q13", familia="P", intensidad=2, grado="E1",
        texto="lenguaje de comunidad en su propio contenido",
        # R7 salio el 2026-09-23. Era la otra rama del OR interior, asi que la
        # regla queda MAS ESTRECHA: 50 activaciones pasan a 18.
        campos=("ev2_comunidad", "R5_espanol"),
        condicion=lambda r: _y(
            _b(r, "ev2_comunidad"),
            _ge(r, "R5_espanol", 6),
        ),
    ),
    # P-Q13-2 ELIMINADA el 2026-09-23, y por una razon distinta de la de
    # P-Q14-3. Aqui R7 no era una rama de un OR sino un CONJUNTO de un AND:
    # `ev2_fe_familia Y R7 >= 8`. Quitarle R7 no la depura, la ensancha --
    # medido: de 144 activaciones a 523-- porque lo que la acotaba era
    # justamente el apellido.
    #
    # Una regla que despues de sacarle el campo prohibido se activa sobre 3,6
    # veces mas gente ya no es la misma regla con menos ruido: es otra regla,
    # que nadie escribio ni valido. Marcadores de fe o familia en una bio son
    # comunes en cualquier poblacion y no dicen nada del costo reputacional
    # comunitario que P-Q13 pretende detectar.

    # ── P-Q07 · Capital de entrada ──────────────────────────────────────────
    Regla(
        id="P-Q07-1", qualifier="P-Q07", familia="P", intensidad=3, grado="E0",
        texto="su bio menciona down payment o DPA",
        campos=("ev2_dpa_enganche",),
        condicion=lambda r: _b(r, "ev2_dpa_enganche"),
    ),
    Regla(
        id="P-Q07-2", qualifier="P-Q07", familia="P", intensidad=2, grado="E1",
        texto="el down payment es el cuello de botella típico de ese perfil",
        campos=("ev2_primera_casa",),
        condicion=lambda r: _b(r, "ev2_primera_casa"),
        discrepancia=(
            "RESUELTO 2026-09-22 · gana la documentacion. El prototipo evalua "
            "la regla de intensidad 1 (P-Q07-3) ANTES que esta, con `elif`, "
            "asi que un agente que cumple las dos se quedaba con 1. El `elif` "
            "era un bug, no una decision: el archivo 06 dice que gana la de "
            "mayor intensidad. Son 23 filas del libro v3 que pasan de 1 a 2."
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
        texto="su bio menciona pre-approval",
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
            "ABIERTA · el prototipo le da 3 a inversion CON marcadores de lujo "
            "y 2 a inversion SIN ellos, pero el propio archivo 06 advierte que "
            "«inversión + lujo suele ser anti-ICP, no oportunidad». O sea que "
            "la combinacion que el texto marca como señal de alarma recibe la "
            "intensidad mas alta. Medido: 0 filas de diferencia, porque las dos "
            "condiciones son mutuamente excluyentes y da igual cual se evalue "
            "primero. Lo que queda abierto no es la resolucion sino si la "
            "intensidad esta al reves. Es decision de metodologia."
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
        campos=("estado_perfil", "ig_seguidores", "ev2_video_contenido",
                "ev2_educacion"),
        # **Exige haber LEIDO el perfil.** Es la unica regla del catalogo que
        # concluye desde una AUSENCIA -- "no le vimos señal de produccion"-- y
        # una ausencia solo significa algo si se miro.
        #
        # Sin esta condicion la regla disparaba sobre perfiles privados, donde
        # "no vimos" se convertia en diagnostico. Es exactamente lo que la
        # guardia de "nada se llena por descarte" prohibe, y es el mismo error
        # que costo siete perfiles marcados como privados.
        #
        # Si `estado_perfil` falta, la condicion da None: no se evalua y queda
        # declarada. No leimos su Instagram, asi que no sabemos.
        condicion=lambda r: _y(
            _igual(r, "estado_perfil", "publico_leido"),
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
    # La produccion que MANDA es la anualizada de Model Match: solo lado
    # comprador, `buy_units / ventana * 12`. El `unidades_ano` del libro es de
    # principios de año y no distingue lado, asi que solo se usa cuando no hay
    # Model Match -- y entonces el grado baja, porque es peor evidencia.
    Regla(
        id="P-Q11-2", qualifier="P-Q11", familia="P", intensidad=1, grado="E3",
        texto="base que se enfría sin sistema de retención",
        campos=("mm_buyside_anualizado",),
        condicion=lambda r: _ge(r, "mm_buyside_anualizado", 20),
    ),
    Regla(
        id="P-Q11-3", qualifier="P-Q11", familia="P", intensidad=1, grado="E3",
        texto="volumen del libro alto, sin producción de Model Match que lo confirme",
        campos=("unidades_ano", "mm_buyside_anualizado"),
        condicion=lambda r: _y(
            _ge(r, "unidades_ano", 20),
            _no(_tiene(r, "mm_buyside_anualizado")),
        ),
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
    #
    # Cuando hay Model Match, MANDA su registro: `mm_share_buy` es la fracción
    # de operaciones del lado comprador sobre el total, contada por unidades.
    # La bio dice a qué se dedica; Model Match dice qué cerró.
    #
    # Gaston: 3 buy / 6 sell -> 0,33 -> J-Q01 = 1.  Ochoa: 9 / 3 -> 0,75 -> 3.
    #
    # Grado E1 y no E0: es un registro de un tercero, no su propio texto. La
    # bio daba 3/E0 AFIRMA sobre «buyside sí, listing no», que es menos dato y
    # más fuerza -- exactamente al revés de lo que corresponde.
    # SON DOS BANDAS, NO TRES, y el motivo es el techo de E1.
    #
    # La version de tres --0,60 / 0,40 / resto, con intensidades 3, 2 y 1--
    # declaraba un 3 que el techo de E1 recorta a 2, asi que las dos primeras
    # bandas terminaban en el mismo numero y solo cambiaba el texto. Model
    # Match es el registro de un tercero, no el texto propio de la persona:
    # por definicion no es E0, y E1 no llega a 3 sin una excepcion declarada
    # en el archivo 05 -- que es justo lo que el 2026-09-22 se decidio no abrir
    # para J-Q04.
    #
    # Para lo que J-Q01 hace --abrir o cerrar la compuerta en <= 1-- las dos
    # bandas dicen lo mismo que las tres. El unico corte que cambia algo es
    # 0,40. Gaston: 3 buy / 6 sell -> 0,33 -> 1, compuerta cerrada. Ochoa:
    # 9 / 3 -> 0,75 -> 2, compuerta abierta.
    Regla(
        id="J-Q01-MM1", qualifier="J-Q01", familia="J", intensidad=2,
        grado="E1",
        texto="su registro de Model Match incluye el lado comprador",
        campos=("mm_share_buy",),
        condicion=lambda r: _ge(r, "mm_share_buy", 0.40),
    ),
    Regla(
        id="J-Q01-MM2", qualifier="J-Q01", familia="J", intensidad=1,
        grado="E1",
        texto="su registro de Model Match es mayoritariamente del lado vendedor",
        campos=("mm_share_buy",),
        # Sin `_tiene`: `_ge` ya devuelve None cuando el campo falta, y `_no`
        # lo propaga. Con `_tiene` la regla daria False sobre un registro vacio
        # -- «no aplica» en vez de «no se pudo evaluar», que es la distincion
        # que sostiene todo lo demas.
        condicion=lambda r: _no(_ge(r, "mm_share_buy", 0.40)),
    ),

    # Las tres de la BIO ceden cuando hay Model Match: sin esto, la bio de
    # Ochoa daba 3/E0 y el registro 3/E1, y ganaba la bio por grado -- o sea
    # que el dato mas fuerte perdia contra la declaracion. En Gaston era peor:
    # la bio lo habria puesto por encima de su propio registro de 3 buy / 6
    # sell, que es justo lo que la compuerta existe para leer.
    Regla(
        id="J-Q01-1", qualifier="J-Q01", familia="J", intensidad=3, grado="E0",
        texto="se declara agente de compradores",
        campos=("ev2_buy_side", "ev2_listing_side", "mm_share_buy"),
        condicion=lambda r: _y(_no(_tiene(r, "mm_share_buy")),
                               _y(_b(r, "ev2_buy_side"),
                                  _no(_b(r, "ev2_listing_side")))),
    ),
    Regla(
        id="J-Q01-2", qualifier="J-Q01", familia="J", intensidad=2, grado="E1",
        texto="libro predominantemente buyside",
        campos=("ev2_primera_casa", "mm_share_buy"),
        condicion=lambda r: _y(_no(_tiene(r, "mm_share_buy")),
                               _b(r, "ev2_primera_casa")),
    ),
    Regla(
        id="J-Q01-3", qualifier="J-Q01", familia="J", intensidad=1, grado="E1",
        texto="menor dependencia del financiamiento del comprador",
        campos=("ev2_listing_side", "ev2_buy_side", "mm_share_buy"),
        condicion=lambda r: _y(_no(_tiene(r, "mm_share_buy")),
                               _y(_b(r, "ev2_listing_side"),
                                  _no(_b(r, "ev2_buy_side")))),
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
        id="J-Q04-1", qualifier="J-Q04", familia="J", intensidad=2, grado="E1",
        texto="audiencia propia grande",
        campos=("ig_seguidores", "ev_bio_legible"),
        condicion=lambda r: _y(_ge(r, "ig_seguidores", 10000),
                               _b(r, "ev_bio_legible")),
        discrepancia=(
            "RESUELTO 2026-09-22 · baja de 3 a 2. El archivo 06 la declaraba en "
            "3 con grado E1 y el techo del 05 dice que E1 no pasa de 2. Se "
            "decidio NO abrir la excepcion E1->3: intensidad 3 con E0 es lo "
            "unico que autoriza al copy a afirmar, y una excepcion que permita "
            "afirmar sobre evidencia de registro hace la segunda excepcion mas "
            "facil. Ademas J-Q04 nunca puede ser primario (es familia J), asi "
            "que la excepcion no compraba nada y costaba la disciplina. El "
            "archivo 05 queda como esta; se corrigio el 06."
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
