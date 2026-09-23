"""`clase_perfil`: la compuerta que decide si un perfil de Instagram sirve.

El problema que resuelve
------------------------
`motor/desde_instagram.py` evaluaba Instagram **sin compuerta de perfil**: 36 de
los 39 perfiles no utilizables tenian un dolor primario vigente. Entre ellos, la
cuenta personal de alguien, un criadero de gallos y la campaña politica de otro
pais.

Funciones puras, sin IO. Se calcula en la INGESTA y se persiste; el motor solo
la lee. Calcularla en el motor la haria depender de que cada consumidor la
recalcule igual.

Las tres reglas de estado
-------------------------
No leido = `None`. `publico_leido` con 0 captions = `sin_datos`. En esta capa
estan prohibidos `bool("0")` y `x or 0`: un cero que en realidad es «no se
pudo mirar» es como 36 perfiles pasaron.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from captura.estados import ESTADOS
from ingest.instagram.lexico import (
    CONFERENCISTA,
    ES_EEUU_SIEMPRE,
    HASHTAG_REGIONAL,
    LISTADO_EXTRANJERO,
    ORIGINADOR,
    OTRA_ACTIVIDAD,
    PAISES_NO_EEUU,
    PORTUGUES,
    RE_DEBIL,
    RE_FUERTE,
    SEP_POST,
    TELEFONO_EXTRANJERO,
    VERSION_LEXICO,
    WHOLESALER,
)

#: Solo estas alimentan `ev2_*`, S1-S10 y los qualifiers.
#: `otro_perfil` entra SOLO como fuente de referidos (correccion B10): no se
#: evalua como realtor transaccional ni genera la secuencia de 7 toques.
CLASES_UTILIZABLES = frozenset({"realtor_activo", "realtor_mixto",
                                "poca_evidencia", "otro_perfil"})

#: Y estas son todas las que existen. Una clase nueva que no este aqui hace
#: fallar la prueba: caer del lado utilizable por omision es como empezo esto.
CLASES = CLASES_UTILIZABLES | frozenset({
    "sin_datos", "persona_equivocada", "re_fuera_eeuu", "inactivo",
    "personal_sin_re"})

DIAS_INACTIVO = 180
POSTS_POCA_EVIDENCIA = 5
SHARE_RE_MIXTO = 0.30
MIN_PORTUGUES = 5
MIN_OTRA_ACTIVIDAD = 3
#: Posts de real estate ubicados en EE. UU. que bastan para quedarse (A2).
MIN_RE_EN_EEUU = 3

#: Nombres y siglas de estado, para el gazetteer de A1.
_NOMBRES_ESTADO = {n.lower() for n in ESTADOS.values()}
_SIGLAS_ESTADO = set(ESTADOS)


@dataclass
class Clase:
    clase: str
    motivo: str
    #: `True` cuando la clase la puso una heuristica que hay que mirar a mano.
    revisar: bool = False
    #: Lo medido, para que el motivo se pueda comprobar sin re-correr nada.
    detalle: dict = field(default_factory=dict)
    version_lexico: str = VERSION_LEXICO

    @property
    def utilizable(self) -> bool:
        return self.clase in CLASES_UTILIZABLES

    def a_dict(self) -> dict:
        return {"clase_perfil": self.clase, "clase_motivo": self.motivo,
                "clase_origen": "auto", "revisar": self.revisar,
                "version_lexico": self.version_lexico,
                "detalle": dict(self.detalle)}


# ══════════════════════════════════════════════════════════════════════════════
# Utilidades de lectura. Ninguna rellena con cero.
# ══════════════════════════════════════════════════════════════════════════════

def posts_de(texto) -> list[str]:
    if texto is None or texto != texto:      # None o NaN
        return []
    return [p for p in str(texto).split(SEP_POST) if p.strip()]


def fecha_de(post: str) -> date | None:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", post or "")
    return date.fromisoformat(m.group(1)) if m else None


def _a_fecha(v) -> date | None:
    """`capturado_en` puede venir como date, datetime o texto ISO."""
    if v is None or v != v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except ValueError:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
        return date.fromisoformat(m.group(1)) if m else None


def es_post_de_real_estate(post: str) -> bool:
    """Correccion A3: un fuerte basta; de los debiles hacen falta DOS distintos.

    «Finally got the keys to our new boat» tiene `keys`. «Closing out summer
    with the family» tiene `closing`. «Pending: my birthday party» tiene
    `pending`. Con un solo debil, los tres contaban como posts del oficio y la
    cuenta salia `realtor_mixto`, o sea utilizable.
    """
    if not post:
        return False
    if RE_FUERTE.search(post):
        return True
    distintos = {m.group(0).lower() for m in RE_DEBIL.finditer(post)}
    return len(distintos) >= 2


def _tiene_estado_de_eeuu(lugar: str) -> bool:
    """El gazetteer de A1, con los 50 estados + DC que ya vivian en el repo.

    «Panama City Beach, Florida» trae Florida, asi que es EE. UU. y la lista de
    paises no se consulta. Lo mismo resuelve Mexico Beach FL, Cuba NM, Peru IN
    y Mexico MO, que era la lista entera de trampas medidas.

    NO se agrego `pycountry` ni GeoNames, que es lo que pedia la correccion al
    pie de la letra: el repo declara «sin dependencias» y las pruebas corren sin
    red. Lo que esto NO cubre queda dicho en el reporte: una ciudad extranjera
    sin estado de EE. UU. en el geotag y que no este en `PAISES_NO_EEUU` se
    queda sin resolver -- y sin resolver significa `None`, no «es de EE. UU.».
    """
    bajo = (lugar or "").lower()
    if any(("," + n) in bajo or bajo.strip() == n for n in _NOMBRES_ESTADO):
        return True
    if any(re.search(r",\s*" + re.escape(n) + r"\b", bajo)
           for n in _NOMBRES_ESTADO):
        return True
    return bool(re.search(r",\s*(%s)\b" % "|".join(_SIGLAS_ESTADO), lugar or ""))


def geotags_extranjeros(geotags) -> tuple[int, int] | None:
    """(extranjeros, total), o `None` si no hay geotags que leer."""
    if geotags is None or geotags != geotags or not str(geotags).strip():
        return None
    partes = re.findall(r"([^,(]+(?:,[^,(]+)*)\s*\((\d+)\)", str(geotags))
    total = ext = 0
    for lugar, n in partes:
        n = int(n)
        total += n
        if _tiene_estado_de_eeuu(lugar) or ES_EEUU_SIEMPRE.search(lugar):
            continue                      # correccion A1
        if PAISES_NO_EEUU.search(lugar):
            ext += n
    return (ext, total) if total else None


def _clase_de_otro_perfil(texto: str, bio: str) -> Clase | None:
    """Correccion A6: `otro_perfil` se DETECTA, no solo se audita.

    Sin esto, un scraping nuevo nunca encuentra a un loan officer ni a un
    wholesaler: una conferencista salia `realtor_mixto` y se evaluaba como
    realtor transaccional.
    """
    todo = "%s %s" % (bio or "", texto or "")

    def _propio(patron):
        """El match, salvo que haya un @handle cerca: eso es de otra persona.

        «our amazing loan officer @jenniferwyattloanofficer» y
        «@speakermatiasrios Empresario, conferencista internacional» son los dos
        casos medidos. Un arroba a menos de 40 caracteres significa que la frase
        le esta dando el credito a alguien mas.
        """
        m = patron.search(todo)
        if not m:
            return None
        cerca = todo[max(0, m.start() - 40):m.end() + 40]
        return None if "@" in cerca else m

    m = _propio(ORIGINADOR)
    if m:
        nmls = re.search(r"\bnmls\s*#?\s*(\d{4,})", todo, re.I)
        return Clase(
            "otro_perfil",
            "origina el mismo (%s): regla 7, descarte. NMLS %s"
            % (m.group(0).strip(), nmls.group(1) if nmls else "sin dato"),
            revisar=True,
            detalle={"es_originador": True,
                     "nmls": nmls.group(1) if nmls else None,
                     "cita": m.group(0).strip()})
    m = _propio(WHOLESALER)
    if m:
        return Clase("otro_perfil",
                     "compra para revender, no representa compradores: «%s»"
                     % m.group(0).strip(),
                     revisar=True, detalle={"wholesaler": True})
    m = _propio(CONFERENCISTA)
    if m:
        return Clase("otro_perfil",
                     "vive de formar agentes, no de transaccionar: «%s»"
                     % m.group(0).strip(),
                     revisar=True, detalle={"conferencista": True})
    return None


# ══════════════════════════════════════════════════════════════════════════════
# El clasificador
# ══════════════════════════════════════════════════════════════════════════════

def clasificar(fila: dict, *, handles_repetidos: frozenset | set = frozenset()
               ) -> Clase:
    """La primera regla que dispara gana. El ORDEN es el de la correccion A5.

        sin_datos -> duplicado -> region -> portugues -> pais -> otra actividad
        -> otro_perfil -> personal_sin_re -> inactivo -> poca_evidencia
        -> realtor_mixto / realtor_activo

    `inactivo` va DESPUES de `personal_sin_re` a proposito: con el orden al
    reves, 5 cuentas personales viejas salian «pedir la cuenta vigente» en vez
    de «tiene otra cuenta de negocio: buscar handle». No cambia la compuerta,
    pero si la accion que se le indica al BD, y esa es la unica salida util de
    un perfil que no sirve.
    """
    estado_perfil = fila.get("estado_perfil")
    posts = posts_de(fila.get("captions_texto"))

    # 1 · sin datos. No leido y leido-vacio son lo mismo para la compuerta, y
    #     los dos son distintos de «se miro y no habia señales».
    if estado_perfil != "publico_leido" or not posts:
        return Clase("sin_datos",
                     "estado_perfil=%s · %d captions (no leído ≠ no existe)"
                     % (estado_perfil, len(posts)),
                     detalle={"estado_perfil": estado_perfil,
                              "captions": len(posts)})

    handle = str(fila.get("handle") or "").lower().lstrip("@")
    if handle and handle in handles_repetidos:
        return Clase("persona_equivocada",
                     "handle asignado a más de un lead: se anula en todos "
                     "hasta verificar",
                     revisar=True, detalle={"handle": handle})

    texto = " ".join(posts)
    bio = str(fila.get("bio") or "")
    estado_lead = fila.get("estado")

    # 3 · hashtag regional fuera de su estado
    for tag, estados_ok in HASHTAG_REGIONAL.items():
        if re.search(r"#" + tag, texto, re.I) and estado_lead not in estados_ok:
            return Clase("persona_equivocada",
                         "#%s en un lead de %s" % (tag, estado_lead),
                         detalle={"hashtag": tag, "estado_lead": estado_lead})

    # 4 · portugues
    n_pt = len(PORTUGUES.findall(texto))
    if n_pt >= MIN_PORTUGUES:
        return Clase("persona_equivocada",
                     "contenido en portugués (%d marcadores)" % n_pt,
                     detalle={"marcadores_pt": n_pt, "idioma": "pt"})

    # ── lo que hace falta para las reglas que siguen ────────────────────────
    re_posts = [p for p in posts if es_post_de_real_estate(p)]
    n_re = len(re_posts)
    share_re = n_re / len(posts)
    geo = geotags_extranjeros(fila.get("geotags_top"))
    tel = bool(TELEFONO_EXTRANJERO.search(texto))

    # 5 · pais extranjero (correcciones A1 y A2)
    #     `re_fuera_eeuu` exige que los POSTS DE REAL ESTATE esten fuera. Un
    #     realtor de TX con 18 de 20 posts de real estate y 2 geotags de Cancun
    #     esta de vacaciones, no opera alla.
    re_afuera = [p for p in re_posts
                 if LISTADO_EXTRANJERO.search(p) or TELEFONO_EXTRANJERO.search(p)
                 or PAISES_NO_EEUU.search(p)]
    geo_mayoria_afuera = bool(geo and geo[1] >= 2 and geo[0] / geo[1] >= 0.5)
    if re_afuera and len(re_afuera) >= max(1, n_re // 2):
        return Clase("re_fuera_eeuu",
                     "%d de %d posts de real estate con listado fuera de "
                     "EE. UU." % (len(re_afuera), n_re),
                     detalle={"re_afuera": len(re_afuera), "re_total": n_re})
    if (geo_mayoria_afuera or tel) and n_re < MIN_RE_EN_EEUU:
        partes = []
        if geo_mayoria_afuera:
            partes.append("%d de %d geotags fuera de EE. UU." % geo)
        if tel:
            partes.append("teléfono extranjero")
        return Clase("persona_equivocada", " · ".join(partes),
                     detalle={"geotags_ext": geo, "telefono_ext": tel,
                              "posts_re": n_re})
    # `opera_tambien_fuera` exige un post DE REAL ESTATE afuera, no un geotag de
    # viaje. Marcarlo desde los geotags decia «también opera en México» de
    # alguien que se fue una semana a Cancún -- que es el mismo error de A2 un
    # escalón más abajo: no excluye, pero miente en la ficha.
    opera_fuera = bool(re_afuera and n_re >= MIN_RE_EN_EEUU)

    # 6 · otra actividad (correccion A7). Va ANTES de `personal_sin_re`: «vive
    #     de otra cosa» y «tiene otra cuenta de negocio» piden acciones
    #     distintas, y con <=1 post de real estate la primera es la correcta.
    n_otra = sum(1 for p in posts if OTRA_ACTIVIDAD.search(p))
    if n_otra >= MIN_OTRA_ACTIVIDAD and n_re <= 1:
        return Clase("persona_equivocada",
                     "%d posts de otra actividad y %d de real estate"
                     % (n_otra, n_re),
                     detalle={"otra_actividad": n_otra, "posts_re": n_re})

    # 7 · otro perfil: loan officer, wholesaler, conferencista
    otro = _clase_de_otro_perfil(texto, bio)
    if otro:
        otro.detalle.update({"posts_re": n_re, "posts": len(posts)})
        return otro

    # 8 · personal sin real estate (ANTES que inactivo, correccion A5)
    if n_re <= 1:
        return Clase("personal_sin_re",
                     "%d de %d posts de real estate: es una cuenta personal, "
                     "buscar su cuenta de negocio" % (n_re, len(posts)),
                     detalle={"posts_re": n_re, "posts": len(posts)})

    # 9 · inactivo, medido contra `capturado_en` (correccion A4)
    #     Con `hoy` el mismo crudo daba otra clase mañana.
    referencia = _a_fecha(fila.get("capturado_en"))
    fechas = [f for f in (fecha_de(p) for p in posts) if f]
    if referencia and fechas:
        dias = (referencia - max(fechas)).days
        if dias > DIAS_INACTIVO:
            return Clase("inactivo",
                         "último post %s, %d días antes de la captura"
                         % (max(fechas), dias),
                         detalle={"ultimo_post": str(max(fechas)),
                                  "dias": dias,
                                  "capturado_en": str(referencia)})

    # 10 · poca evidencia
    if len(posts) <= POSTS_POCA_EVIDENCIA:
        return Clase("poca_evidencia",
                     "solo %d posts: techo 2/E1" % len(posts),
                     detalle={"posts": len(posts), "posts_re": n_re})

    detalle = {"posts_re": n_re, "posts": len(posts),
               "share_re": round(share_re, 3)}
    if opera_fuera:
        detalle["opera_tambien_fuera"] = True
    if share_re < SHARE_RE_MIXTO:
        return Clase("realtor_mixto",
                     "%d de %d posts de real estate" % (n_re, len(posts)),
                     detalle=detalle)
    return Clase("realtor_activo",
                 "%d de %d posts de real estate" % (n_re, len(posts)),
                 detalle=detalle)


def handles_repetidos_en(filas: list[dict]) -> frozenset:
    """Los handles que aparecen en mas de un lead. Es un chequeo de CARGA."""
    vistos: dict[str, set] = {}
    for f in filas:
        h = str(f.get("handle") or "").lower().lstrip("@")
        rid = f.get("realtor_id")
        if h and rid:
            vistos.setdefault(h, set()).add(str(rid))
    return frozenset(h for h, ids in vistos.items() if len(ids) > 1)
