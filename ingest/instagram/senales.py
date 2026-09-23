"""De los posts a los qualifiers, con ancla obligatoria.

Mencion no es verbalizacion
---------------------------
3/E0 solo si el realtor **enuncia el problema o su especializacion con su
propio texto**. Un atributo de listado («Qualifies for 0% down»), una historia
de cierre («Congratulations to my amazing VA buyer») o el texto de terceros
(comentarios) llegan como maximo a 2/E1. Esa distincion es la que separa «sabe
resolver esto» de «le pasó una vez».

Si no hay ancla, no hay qualifier
---------------------------------
Cada señal emitida trae la cita literal con su fecha, que patron disparo, en
cuantos posts DISTINTOS, la fuente y la version del lexico. Un qualifier sin
ancla no se puede discutir con nadie seis meses despues.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ingest.instagram.clase_perfil import CLASES_UTILIZABLES, posts_de
from ingest.instagram.lexico import LEX, VERSION_LEXICO, huella
from ingest.instagram.parseo import hits_distintos

#: Techo de los perfiles con 5 posts o menos.
TECHO_POCA_EVIDENCIA = (2, "E1")

#: La muestra que la matriz exige para acreditar idioma.
MUESTRA_MINIMA_IDIOMA = 10


@dataclass
class Senal:
    qualifier: str
    intensidad: int
    grado: str
    evidencia_ancla: str
    evidencia_regla: str
    posts_distintos: int
    fuente: str = "instagram"
    version_lexico: str = VERSION_LEXICO
    huella_lexico: str = field(default_factory=huella)

    def a_dict(self) -> dict:
        return {"qualifier": self.qualifier, "intensidad": self.intensidad,
                "grado": self.grado, "evidencia_ancla": self.evidencia_ancla,
                "evidencia_regla": self.evidencia_regla,
                "posts_distintos": self.posts_distintos,
                "fuente": self.fuente, "version_lexico": self.version_lexico,
                "huella_lexico": self.huella_lexico}


def _mk(qualifier, intensidad, grado, clave, posts, techo=None) -> Senal | None:
    n_hits, n_distintos, ancla = hits_distintos(posts, LEX[clave])
    if not n_distintos or not ancla:
        return None                       # sin ancla no hay qualifier
    if techo and (intensidad, grado) > techo:
        intensidad, grado = techo
    return Senal(qualifier, intensidad, grado, ancla,
                 "%s en %d posts distintos (%d coincidencias)"
                 % (clave, n_distintos, n_hits), n_distintos)


def senales_de_posts(fila: dict, clase: str) -> list[Senal]:
    """Los qualifiers que salen de Instagram. Vacio si la clase no es utilizable.

    La compuerta va PRIMERO y en esta funcion, no en quien la llame: confiar en
    que cada consumidor consulte la clase antes es exactamente como 36 perfiles
    no utilizables terminaron con dolor primario.
    """
    if clase not in CLASES_UTILIZABLES:
        return []
    # `otro_perfil` entra solo como fuente de referidos (B10): no se le sacan
    # qualifiers de realtor transaccional.
    if clase == "otro_perfil":
        return []

    posts = posts_de(fila.get("captions_texto"))
    if not posts:
        return []
    techo = TECHO_POCA_EVIDENCIA if clase == "poca_evidencia" else None
    fuera: list[Senal] = []

    def agregar(s):
        if s:
            fuera.append(s)

    # ── P-Q01 · el lender le rechaza el caso de nicho ───────────────────────
    # `itin` y `self_emp` son verbalizacion: lo dice el realtor con su texto.
    agregar(_mk("P-Q01", 3, "E0", "itin", posts, techo))
    if not any(s.qualifier == "P-Q01" for s in fuera):
        agregar(_mk("P-Q01", 3, "E0", "self_emp", posts, techo))
    if not any(s.qualifier == "P-Q01" for s in fuera):
        agregar(_mk("P-Q01", 2, "E1", "owner_fin", posts, techo))
    if not any(s.qualifier == "P-Q01" for s in fuera):
        agregar(_mk("P-Q01", 2, "E1", "gob", posts, techo))

    # ── P-Q07 · capital de entrada ──────────────────────────────────────────
    # 3/E0 solo con >=2 posts DISTINTOS de `dpa`: un post es una mencion.
    n_dpa = hits_distintos(posts, LEX["dpa"])[1]
    if n_dpa >= 2:
        agregar(_mk("P-Q07", 3, "E0", "dpa", posts, techo))
    else:
        for clave in ("dpa", "zero_down"):
            if not any(s.qualifier == "P-Q07" for s in fuera):
                agregar(_mk("P-Q07", 2, "E1", clave, posts, techo))
        # `primera` necesita DOS posts distintos, y los otros dos no.
        #
        # La tabla de la spec la dejaba en 1 post, pero medido sobre los 195
        # utilizables con posts dispara en el 37,9% -- por encima de la alarma
        # del 25% de la regla 6. Las citas dicen por que: «Perfect for families,
        # first-time buyers» es un ATRIBUTO DE LISTADO y «el cierre de su
        # primera casa» es una HISTORIA DE CIERRE. Las dos son exactamente lo
        # que la regla 4 llama mencion y no verbalizacion.
        #
        # Con >=2 posts distintos baja a 15,4%. `dpa` (11,3%) y `zero_down`
        # (10,8%) se quedan en 1 porque son especificos del problema de capital
        # y no inflan nada.
        if (not any(s.qualifier == "P-Q07" for s in fuera)
                and hits_distintos(posts, LEX["primera"])[1] >= 2):
            agregar(_mk("P-Q07", 2, "E1", "primera", posts, techo))

    # ── P-Q19 · crédito ─────────────────────────────────────────────────────
    agregar(_mk("P-Q19", 3, "E0", "cred_reing", posts, techo))
    if not any(s.qualifier == "P-Q19" for s in fuera):
        agregar(_mk("P-Q19", 1, "E1", "credito", posts, techo))

    # ── P-Q17 · VA ──────────────────────────────────────────────────────────
    agregar(_mk("P-Q17", 3, "E0", "va_esp", posts, techo))
    if not any(s.qualifier == "P-Q17" for s in fuera):
        # «Congratulations to my amazing VA buyer» es una historia de cierre:
        # 2/E1, nunca 3. Y hacen falta 2 posts distintos, o es una anécdota.
        n_va = hits_distintos(posts, LEX["va_aud"])[1]
        if n_va >= 2:
            agregar(_mk("P-Q17", 2, "E1", "va_aud", posts, techo))

    # ── P-Q12 · preguntas de su audiencia ───────────────────────────────────
    n_pre = hits_distintos(posts, LEX["preaprob"])[1]
    if n_pre >= 2:
        agregar(_mk("P-Q12", 2, "E1", "preaprob", posts, techo))

    return fuera


def idioma_de(fila: dict, clase: str) -> dict:
    """P-Q14, con `pub_es_mayoria` (E1) y `es_declarado` (E0) SEPARADOS.

    La bio no basta para 3: en 47 de los 300 perfiles v3 daba 3/E0 porque la
    bio dice «Bilingual | English & Español» y los 20 posts estan en ingles.
    Declarar que atiende en español es E0; publicar en español es E1; y la
    escala solo llega a 3 cuando pasan las DOS cosas.
    """
    if clase not in CLASES_UTILIZABLES or clase == "otro_perfil":
        return {"intensidad": None, "grado": None, "motivo": "clase %s" % clase}

    posts = posts_de(fila.get("captions_texto"))
    s = fila.get("senales") or {}
    es = _num(s.get("idioma_publica_es"))
    en = _num(s.get("idioma_publica_en"))

    # Portugués ya dejó la clase en `persona_equivocada`, así que aquí no llega.
    if es is None or en is None or (es + en) == 0:
        return {"intensidad": None, "grado": None,
                "motivo": "sin clasificación de idioma de los posts"}

    ratio = es / (es + en)
    n_posts = len(posts)
    pub_es_mayoria = bool(n_posts >= MUESTRA_MINIMA_IDIOMA and ratio >= 0.5)
    _n, declarado, ancla = hits_distintos(posts, LEX["es_decl"])
    es_declarado = bool(declarado)

    base = {"pub_es_mayoria": pub_es_mayoria, "es_declarado": es_declarado,
            "ratio_es": round(ratio, 3), "posts": n_posts,
            "evidencia_ancla": ancla, "version_lexico": VERSION_LEXICO}

    if n_posts >= MUESTRA_MINIMA_IDIOMA and pub_es_mayoria and es_declarado:
        return {**base, "intensidad": 3, "grado": "E0",
                "motivo": "publica mayoritariamente en español Y lo declara"}
    if pub_es_mayoria:
        return {**base, "intensidad": 2, "grado": "E1",
                "motivo": "publica mayoritariamente en español"}
    if 0.10 <= ratio < 0.50:
        return {**base, "intensidad": 1, "grado": "E1",
                "motivo": "entre 10 y 50%% de los posts en español"}

    # Desajuste: le escriben en español y publica en inglés.
    com_es = _num(s.get("idioma_comentarios_es"))
    com_en = _num(s.get("idioma_comentarios_en"))
    if (com_es is not None and com_en is not None
            and (com_es + com_en) >= MUESTRA_MINIMA_IDIOMA
            and com_es / (com_es + com_en) >= 0.50 and ratio < 0.25):
        return {**base, "intensidad": 2, "grado": "E1",
                "motivo": "su audiencia le escribe en español y él publica en "
                          "inglés (desajuste)"}
    return {**base, "intensidad": 0, "grado": "E1", "motivo": "publica en inglés"}


def _num(v):
    if v is None or v != v:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# S6 · las cuentas etiquetadas, por TOKEN y nunca por subcadena
# ══════════════════════════════════════════════════════════════════════════════

#: token -> clase.
_TOKENS = {
    "lender": ("lender", "lenders", "loans", "loan", "mortgage", "mortgages",
               "lending", "prestamos", "hipotecas", "nmls"),
    "title": ("title", "titulo", "titles", "escrow", "titleco"),
    "credit_repair": ("creditrepair", "credit", "credito", "reparacion"),
    "agente": ("realestate", "realtor", "realty", "agent", "agente", "homes",
               "broker"),
}

#: Palabras de relleno que aparecen pegadas en los handles de Instagram. Sirven
#: como DELIMITADOR: lo que va antes de una de ellas es una palabra completa.
_CONECTORES = (
    "company", "co", "group", "team", "services", "service", "solutions",
    "by", "the", "my", "your", "and", "of", "with", "usa", "tx", "fl", "ca",
    "pro", "expert", "official", "real", "ejemplo",
)

_FIN_DE_PALABRA = r"(?:$|[^a-z]|%s)" % "|".join(sorted(_CONECTORES,
                                                       key=len, reverse=True))


def clasificar_cuenta(handle: str) -> tuple[str, str]:
    """(clase, motivo). Lo que el lexico no puede clasificar queda en `verificar`.

    **Prohibido el match por subcadena**, que es lo que marco como lender a un
    nombre propio por contener `lo_` y como title a `@titleist`, que es una
    marca de golf. Pero los handles de Instagram vienen pegados --
    `providencetitlecompany`-- asi que partir por separadores tampoco alcanza:
    deja TODO en `verificar`, que es igual de inutil aunque falle del lado
    seguro.

    La regla: el token tiene que TERMINAR donde termina una palabra -- fin de
    cadena, un caracter que no sea letra, o un conector conocido.

        providencetitlecompany  ->  title + «company»  ->  title
        titleist                ->  title + «ist»      ->  no es palabra
        ejemploloans            ->  loans + fin        ->  lender
        carlo_ejemplo           ->  ningun token       ->  verificar

    NUNCA `lender` por descarte: un lender supuesto es el que termina en el
    dossier como «ya trabaja con alguien» sin que nadie lo haya comprobado.
    """
    h = str(handle or "").strip().lstrip("@").lower()
    if not h:
        return "verificar", "handle vacío"
    for clase, vocab in _TOKENS.items():
        for token in vocab:
            if re.search(re.escape(token) + _FIN_DE_PALABRA, h):
                return clase, "token «%s» completo en el handle" % token
    return "verificar", ("ningún token del léxico coincide: no se supone, "
                         "se verifica")
