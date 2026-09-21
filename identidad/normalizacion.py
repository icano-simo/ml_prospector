"""Normalizacion de las llaves de cruce: telefono, email, nombre, licencia.

Por que E.164 y no "el telefono tal como vino"
----------------------------------------------
El mismo numero aparece en las fuentes como `+1 (512) 522-0477`, `5125220477`,
`512.522.0477` y `1-512-522-0477`. Cuatro cadenas distintas para una persona.
Un cruce por telefono sin normalizar **no encuentra nada y no falla**: devuelve
cero coincidencias, que se lee como "no esta en la otra fuente".

E.164 es el formato canonico: `+15125220477`. Una sola forma por numero.

Lo que NO se hace aca
---------------------
No se infiere nada de un nombre mas alla de compararlo con otro nombre. Ni
origen, ni etnia, ni idioma, ni nicho. Es la regla 2 de la metodologia y aplica
igual en este modulo que en instagram/verificacion.py.
"""
from __future__ import annotations

import re
import unicodedata

# ── Telefono ──────────────────────────────────────────────────────────────────

#: Prefijos de area que no existen en el NANP. Un numero que empiece asi es
#: basura, y guardarlo como telefono valido produce un cruce fantasma.
_AREA_INVALIDA = re.compile(r"^[01]")


def a_e164(crudo: str | None, *, pais: str = "1") -> tuple[str | None, str]:
    """Normaliza a E.164. Devuelve (numero, motivo si no se pudo).

    Solo NANP (+1). Si aparece un numero internacional, se declara y no se
    fuerza: un numero mexicano metido a la fuerza en el formato de EE.UU. es un
    numero equivocado.
    """
    if not crudo:
        return None, "vacio"

    texto = str(crudo).strip()
    # Extension: se descarta, pero se declara que habia.
    tenia_extension = bool(re.search(r"\b(?:x|ext|extension)\.?\s*\d+", texto, re.I))
    texto = re.sub(r"\b(?:x|ext|extension)\.?\s*\d+", "", texto, flags=re.I)

    digitos = re.sub(r"\D", "", texto)
    if not digitos:
        return None, "sin digitos"

    if len(digitos) == 11 and digitos.startswith(pais):
        digitos = digitos[1:]
    elif len(digitos) > 11:
        return None, "%d digitos: parece internacional o dos numeros pegados" % len(digitos)
    elif len(digitos) < 10:
        return None, "solo %d digitos" % len(digitos)
    elif len(digitos) == 11:
        return None, "11 digitos con prefijo %r, no %r" % (digitos[0], pais)

    if _AREA_INVALIDA.match(digitos):
        return None, "prefijo de area %r no existe en el NANP" % digitos[:3]
    if _AREA_INVALIDA.match(digitos[3:]):
        return None, "prefijo de central %r no existe en el NANP" % digitos[3:6]
    if len(set(digitos)) <= 2:
        return None, "numero de relleno (%s)" % digitos

    nota = " (tenia extension, se descarto)" if tenia_extension else ""
    return "+%s%s" % (pais, digitos), nota.strip()


# ── Email ─────────────────────────────────────────────────────────────────────

_RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

#: Dominios de placeholder que aparecen en los exports y no son emails de nadie.
_DOMINIOS_BASURA = {
    "example.com", "test.com", "email.com", "noemail.com", "none.com",
    "na.com", "nomail.com", "no.com", "domain.com",
}


def normalizar_email(crudo: str | None) -> tuple[str | None, str]:
    """Minusculas y sin espacios. Devuelve (email, motivo si no se pudo).

    **No se quitan los puntos del usuario ni el sufijo `+algo`.** En Gmail son
    equivalentes, en otros proveedores no, y tratar `a.b@x.com` y `ab@x.com`
    como el mismo email en un dominio corporativo une a dos personas distintas.
    """
    if not crudo:
        return None, "vacio"
    texto = str(crudo).strip().strip("<>").strip()
    if not texto:
        return None, "vacio"
    bajo = texto.lower()
    if not _RE_EMAIL.match(bajo):
        return None, "no tiene forma de email: %r" % texto[:60]
    dominio = bajo.rsplit("@", 1)[1]
    if dominio in _DOMINIOS_BASURA:
        return None, "dominio de relleno: %s" % dominio
    return bajo, ""


def dominio_de(email: str | None) -> str | None:
    """El dominio, que sirve para agrupar por brokerage sin usar el nombre."""
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1].lower()


# ── Nombre ────────────────────────────────────────────────────────────────────

_SUFIJOS = {"jr", "sr", "ii", "iii", "iv", "v"}
_TITULOS = {"mr", "mrs", "ms", "miss", "dr", "prof"}
_RUIDO_DE_OFICIO = {
    "realtor", "realtors", "realty", "broker", "brokerage", "agent",
    "agente", "abr", "gri", "crs", "sres", "mrp", "epro", "cips", "nahrep",
    "pa", "llc", "inc", "pllc", "team", "group",
}


def sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )


def tokens_de_nombre(crudo: str | None) -> list[str]:
    """Tokens comparables de un nombre. Sin acentos, titulos ni ruido de oficio.

    Se usa **solo para comparar un nombre con otro**. Ninguna otra inferencia
    sale de aca.
    """
    if not crudo:
        return []
    texto = sin_acentos(str(crudo)).lower()
    texto = re.sub(r"[^a-z0-9\s'-]", " ", texto)
    brutos = [t.strip("'-") for t in texto.split() if t.strip("'-")]
    return [
        t for t in brutos
        if len(t) > 1 and t not in _SUFIJOS
        and t not in _TITULOS and t not in _RUIDO_DE_OFICIO
    ]


def clave_de_nombre(crudo: str | None) -> str | None:
    """Los tokens ordenados alfabeticamente, unidos.

    Ordenar resuelve el problema de "Apellido, Nombre" contra
    "Nombre Apellido", que es como vienen las dos mitades de casi todo export
    de gobierno. `"TAPIA, ANA"` y `"Ana Tapia"` dan los dos `ana|tapia`.
    """
    tokens = tokens_de_nombre(crudo)
    return "|".join(sorted(tokens)) if tokens else None


# ── Licencia ──────────────────────────────────────────────────────────────────

#: Formato de licencia por estado, para validar antes de cruzar. Cada patron se
#: escribio mirando el formato que publica el propio board; donde no se
#: verifico, la entrada NO esta, y `normalizar_licencia` lo declara.
FORMATO_POR_ESTADO: dict[str, re.Pattern] = {
    "TX": re.compile(r"^\d{5,7}$"),        # TREC
    "FL": re.compile(r"^(?:BK|SL|BO|CQ)?\d{6,9}$"),  # DBPR
}


def normalizar_licencia(crudo: str | None, estado: str | None = None
                        ) -> tuple[str | None, str]:
    """Quita separadores y mayusculiza. Devuelve (licencia, aviso).

    **No se quitan los ceros a la izquierda.** En California `01998877` y
    `1998877` son cadenas distintas y el board publica la primera; normalizar
    de mas destruye la llave.
    """
    if not crudo:
        return None, "vacio"
    texto = re.sub(r"[\s\-./#]", "", str(crudo).strip().upper())
    if not texto:
        return None, "vacio"
    if not re.search(r"\d", texto):
        return None, "sin digitos: %r" % texto[:30]

    est = (estado or "").strip().upper()[:2]
    patron = FORMATO_POR_ESTADO.get(est)
    if patron is None:
        return texto, (
            "no hay formato verificado para %r: la licencia se guarda pero el "
            "cruce por licencia en ese estado no esta validado" % (est or "?")
        )
    if not patron.match(texto):
        return texto, (
            "%r no coincide con el formato conocido de %s: se guarda pero el "
            "cruce es sospechoso" % (texto, est)
        )
    return texto, ""


def clave_de_licencia(licencia: str | None, estado: str | None) -> str | None:
    """`TX:654321`. El estado va adentro porque los numeros se repiten entre
    estados: hay una licencia 654321 en Texas y otra en Florida."""
    norm, _ = normalizar_licencia(licencia, estado)
    if not norm:
        return None
    est = (estado or "").strip().upper()[:2]
    return "%s:%s" % (est or "??", norm)
