"""Verificación mecánica de lo que escribe un modelo.

No confiamos en que el modelo se porte bien: comprobamos lo que escribió.

Las cinco guardas
-----------------
1 · `nunca.py`          las tres cosas que no se le dicen a un realtor
2 · vocabulario         los términos del oficio en inglés, no traducidos
3 · promesas            ningún material prometido mientras nada esté verificado
4 · acto de habla       si el contraste no activa, el texto NO puede afirmar
5 · **las cifras**      toda cifra del texto tiene que estar en los insumos

La quinta es la que importa
---------------------------
Es la única que atrapa una cifra inventada, y ese es el modo de fallo que más
duele: un número equivocado con formato correcto no se ve. `4,2 veces` y
`7,1 veces` se leen igual de bien, y solo uno es el de este realtor.

Y su denominador se reporta siempre. **Cero cifras comprobadas no es un
aprobado**: un texto sin números pasa esta guarda sin que ella haya mirado
nada, y quien lea el veredicto tiene que poder distinguir las dos cosas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from motor.lectura import DESVIO_MAXIMO_PP, verificar_vocabulario
from motor.nunca import verificar_nunca
from motor.secuencia import verificar_sin_folleto, verificar_sin_promesas


class TextoRechazado(ValueError):
    """El texto no entra en la base. Con el motivo y, si es cifra, con cuál."""


# ── Las cifras del oficio ───────────────────────────────────────────────────
#
# Son parte del vocabulario, no afirmaciones sobre este realtor: el rango de
# score que trabajamos, el nombre de un programa. Un texto que las use no está
# inventando un dato suyo.
#
# La lista es CORTA a propósito. Cada número que se agrega es una cifra que la
# guarda deja de mirar, así que agregar uno es una decisión y no un atajo.
CIFRAS_DE_OFICIO: dict[float, str] = {
    580.0: "piso de score del FHA que trabajamos",
    620.0: "piso de score convencional habitual",
    640.0: "piso de score del Tax ID MAX",
    669.0: "techo de la banda de score que se nombra con el 580",
    203.0: "el 203k del FHA, que es el nombre del programa",
    8.0: "la Section 8 de RESPA, que es el nombre de la norma",
}

#: `de cada diez` y `de cada veinte` son la forma hablada de un porcentaje: el
#: denominador no es una cifra del texto, es parte de la construcción.
_RE_HABLADO = re.compile(
    r"\b(cero|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|"
    r"medi[oa])(?:\s+y\s+(medi[oa]))?\s+de\s+cada\s+(diez|veinte)\b",
    re.IGNORECASE)

_PALABRA_A_N = {"cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3,
                "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
                "nueve": 9, "diez": 10, "medio": 0.5, "media": 0.5}

#: Un número escrito con dígitos, en formato español o inglés.
_RE_CIFRA = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+)")


def _a_float(bruto: str) -> float | None:
    """`168.000` -> 168000. `7,7` -> 7.7. `35.6` -> 35.6.

    El separador de millar y el decimal se distinguen por la FORMA, no por
    adivinanza: tres dígitos exactos detrás del punto es millar.
    """
    s = bruto.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
        if s.count(".") > 1:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def cifras_habladas(texto: str) -> list[float]:
    """Las formas habladas, como porcentaje. `tres y medio de cada diez` -> 35."""
    salida = []
    for entero, mitad, base in _RE_HABLADO.findall(texto or ""):
        n = _PALABRA_A_N.get(entero.lower())
        if n is None:
            continue
        if mitad:
            n += 0.5
        divisor = 10.0 if base.lower() == "diez" else 20.0
        salida.append(round(100.0 * n / divisor, 1))
    return salida


def cifras_con_origen(texto: str) -> list[tuple[float, str]]:
    """(valor, origen) de cada cifra. El origen decide con qué tolerancia.

    Quita antes las formas habladas, para que el `diez` de `cuatro de cada
    diez` no cuente como una cifra suelta -- y agrega en su lugar el
    porcentaje que esa forma significa.
    """
    t = texto or ""
    salida: list[tuple[float, str]] = [(c, "hablado") for c in cifras_habladas(t)]
    t = _RE_HABLADO.sub(" ", t)
    for bruto in _RE_CIFRA.findall(t):
        v = _a_float(bruto)
        if v is not None:
            salida.append((v, "digito"))
    return salida


def cifras_del_texto(texto: str) -> list[float]:
    """Solo los valores. `cifras_con_origen` es la que usa la guarda."""
    return [v for v, _o in cifras_con_origen(texto)]


def cifras_de_los_insumos(insumos) -> set[float]:
    """Todas las cifras que hay en el extracto, mire donde mire.

    Recorre el jsonb entero: si el dato está en los insumos, da igual en qué
    campo -- lo que se comprueba es que el número exista, no dónde.
    """
    salida: set[float] = set()

    def recorrer(v):
        if isinstance(v, dict):
            for x in v.values():
                recorrer(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                recorrer(x)
        elif isinstance(v, bool):
            return
        elif isinstance(v, (int, float)):
            salida.add(round(float(v), 4))
        elif isinstance(v, str):
            for c in cifras_del_texto(v):
                salida.add(round(c, 4))

    recorrer(insumos)
    return salida


#: Lo que se admite de diferencia en una cifra escrita con DÍGITOS. Es de
#: redondeo, no de aproximación: `168.000` contra `168.123`.
_RELATIVA_DIGITO = 0.005
_ABSOLUTA_DIGITO = 0.05


def _coincide(cifra: float, origen: str, disponibles: set[float]) -> bool:
    """¿Está esta cifra entre las de los insumos?

    La tolerancia depende del ORIGEN, y esto costó tres falsos aprobados:
    aplicar el desvío de la forma hablada (±2,5 puntos) también a los dígitos
    dejaba pasar `7,1 veces` contra un 9 de los insumos, `17 operaciones`
    contra 16 y `10 del lado comprador` contra 9. Todas plausibles, todas
    falsas, y ninguna se ve.

      dígito   coincide casi exacto: 0,05 absoluto o 0,5% relativo
      hablado  ±2,5 puntos, porque la forma hablada REDONDEA a medios y ese
               desvío está declarado en `lectura.DESVIO_MAXIMO_PP`
    """
    if cifra in disponibles:
        return True
    for d in disponibles:
        if abs(d - cifra) <= _ABSOLUTA_DIGITO:
            return True
        if d and cifra and abs(d - cifra) / max(abs(d), abs(cifra)) <= _RELATIVA_DIGITO:
            return True
        if (origen == "hablado" and cifra <= 100 and d <= 100
                and abs(d - cifra) <= DESVIO_MAXIMO_PP):
            return True
    return False


@dataclass
class Veredicto:
    ok: bool
    guardas: dict = field(default_factory=dict)
    #: Cuántas cifras se comprobaron. Cero NO es un aprobado.
    cifras_comprobadas: int = 0
    cifras_sobrantes: list = field(default_factory=list)
    motivo: str = ""


def verificar_cifras(texto: str, insumos) -> Veredicto:
    """Toda cifra del texto tiene que aparecer en los insumos."""
    disponibles = cifras_de_los_insumos(insumos)
    todas = cifras_con_origen(texto)
    delta = [c for c, origen in todas
             if c not in CIFRAS_DE_OFICIO
             and not _coincide(c, origen, disponibles)]
    total = len(todas)
    return Veredicto(
        ok=not delta, cifras_comprobadas=total,
        cifras_sobrantes=sorted(set(delta)),
        motivo=("" if not delta else
                "estas cifras del texto NO están en los insumos: %s. "
                "Si un número no salió del dato, se inventó."
                % ", ".join(("%g" % d).replace(".", ",") for d in
                            sorted(set(delta)))))


def verificar_texto_generado(texto: str, insumos, *,
                             afirma: bool = True) -> Veredicto:
    """Las cinco guardas. Devuelve el veredicto con su denominador.

    `afirma=False` cuando el contraste que lo origina no activa: ahí el texto
    no puede afirmar, solo preguntar.
    """
    guardas: dict = {}

    for nombre, fn in (("nunca", verificar_nunca),
                       ("vocabulario", verificar_vocabulario),
                       ("promesas_de_material", verificar_sin_promesas),
                       ("folleto", verificar_sin_folleto)):
        try:
            fn(texto)
            guardas[nombre] = {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return Veredicto(ok=False, guardas={**guardas, nombre: {
                "ok": False, "detalle": str(exc)[:300]}},
                motivo=str(exc).split("\n")[0])

    # ── El acto de habla ────────────────────────────────────────────────────
    if not afirma:
        problema = _afirma_sin_poder(texto)
        guardas["acto_de_habla"] = {"ok": not problema, "detalle": problema}
        if problema:
            return Veredicto(ok=False, guardas=guardas, motivo=problema)
    else:
        guardas["acto_de_habla"] = {"ok": True, "detalle": "el contraste activa"}

    v = verificar_cifras(texto, insumos)
    guardas["cifras"] = {"ok": v.ok, "comprobadas": v.cifras_comprobadas,
                         "sobrantes": v.cifras_sobrantes}
    if v.cifras_comprobadas == 0:
        guardas["cifras"]["aviso"] = (
            "cero cifras en el texto: esta guarda no comprobó nada. No es lo "
            "mismo que haber pasado.")
    v.guardas = guardas
    return v


#: Formas que AFIRMAN. Cuando el contraste no activa, el texto pregunta.
_RE_AFIRMA = re.compile(
    r"\b(es (exactamente |justo )?(el|la|un|una) (cliente|perfil|caso)|"
    r"trabaja con compradores que|"
    r"sus clientes (necesitan|son|tienen)|"
    r"su cliente típico (es|tiene|necesita))\b", re.IGNORECASE)


def _afirma_sin_poder(texto: str) -> str:
    m = _RE_AFIRMA.search(texto or "")
    if not m:
        return ""
    return ("el contraste NO activa y el texto afirma: %r. Con la base corta "
            "el texto describe lo que se ve y PREGUNTA; afirmar es lo que las "
            "guardias existen para impedir." % m.group(0)[:60])
