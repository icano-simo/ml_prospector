"""¿El volcado pegado es de la persona que está seleccionada en la pantalla?

Por que existe
--------------
Una captura se guarda contra el realtor que la ficha tenia abierta. Nada obliga
a que el texto pegado sea de esa persona: se abre a Fulano, se pega el volcado
de Mengano y la captura queda colgada de Fulano. No falla nada. Los cuatro
mercados entran, el perfil parsea, la confirmacion dice que todo salio bien --
y el diagnostico de Fulano se calcula con la produccion de Mengano.

Es peor que una captura huerfana. Una huerfana no sirve para nada y se nota;
esta sirve para lo que no es, y no se nota nunca.

**El volcado trae con que comprobarlo.** El Overview de Model Match empieza por
el nombre del agente y su email de contacto. No hay que adivinar: hay que
comparar.

Que NO hace
-----------
No bloquea el guardado. El crudo ya se pego y tirarlo obliga a repetir el
trabajo; ademas un nombre puede escribirse de diez formas y un realtor puede
tener un email que el libro no conoce. Lo que hace es **decir en la
confirmacion a quien quedo pegada y si el volcado lo respalda** -- y cuando no
lo respalda, decirlo con las dos versiones al lado.
"""
from __future__ import annotations

import re
import unicodedata

#: Palabras que no distinguen a nadie dentro de un nombre.
_RUIDO = {"de", "del", "la", "las", "los", "y", "jr", "sr", "ii", "iii",
          "mr", "mrs", "ms", "dr"}


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def piezas_del_nombre(nombre: str | None) -> set[str]:
    """Las palabras que de verdad identifican, normalizadas.

    `Armando Perales Crespo` y `ARMANDO CRESPO` comparten dos piezas. El
    segundo apellido aparece en el volcado y no en el libro mas veces de las
    que uno espera, asi que exigir igualdad de cadena no sirve.
    """
    if not nombre:
        return set()
    limpio = _sin_tildes(str(nombre)).lower()
    limpio = re.sub(r"[^a-z\s]", " ", limpio)
    return {p for p in limpio.split() if len(p) > 1 and p not in _RUIDO}


def _emails(valores) -> set[str]:
    if not valores:
        return set()
    if isinstance(valores, str):
        valores = [valores]
    return {v.strip().lower() for v in valores if v and "@" in str(v)}


def comprobar(perfil: dict | None, realtor: dict | None) -> dict:
    """¿El volcado respalda que sea de este realtor?

    Devuelve siempre un veredicto explicito, nunca un silencio:

    ``respalda``   el email coincide, o el nombre comparte dos piezas
    ``discrepa``   hay nombre o email en los dos lados y no se parecen
    ``no_consta``  el volcado no trae con que comprobar

    `no_consta` NO es `respalda`. Es la distincion que hace toda la diferencia:
    una comprobacion que no tuvo nada que comparar no comprobo nada, y decir
    que si es el patron que este proyecto ya pago cinco veces.
    """
    perfil = perfil or {}
    realtor = realtor or {}

    del_volcado = piezas_del_nombre(perfil.get("nombre"))
    del_libro = piezas_del_nombre(realtor.get("nombre_completo"))
    mails_volcado = _emails(perfil.get("emails"))
    mail_libro = _emails(realtor.get("email_principal"))

    comunes = del_volcado & del_libro
    email_coincide = bool(mails_volcado & mail_libro)

    detalle = {
        "nombre_en_el_volcado": perfil.get("nombre"),
        "nombre_en_el_libro": realtor.get("nombre_completo"),
        "email_en_el_libro": (sorted(mail_libro) or [None])[0],
        "emails_en_el_volcado": sorted(mails_volcado),
        "piezas_en_comun": sorted(comunes),
    }

    if email_coincide:
        return {"veredicto": "respalda",
                "por": "el email del volcado es el de su ficha", **detalle}
    # Dos piezas: un solo apellido compartido no alcanza. `Maria Crespo` y
    # `Armando Crespo` son dos personas y las dos son de eXp en Florida.
    if len(comunes) >= 2:
        return {"veredicto": "respalda",
                "por": "el nombre coincide en %s" % ", ".join(sorted(comunes)),
                **detalle}
    if not del_volcado and not mails_volcado:
        return {"veredicto": "no_consta",
                "por": ("el volcado no trae nombre ni email: no se pudo "
                        "comprobar, que no es lo mismo que estar bien"),
                **detalle}
    if not del_libro and not mail_libro:
        return {"veredicto": "no_consta",
                "por": "su ficha no tiene nombre ni email con que comparar",
                **detalle}
    return {"veredicto": "discrepa",
            "por": ("el volcado dice %r y la ficha abierta es %r"
                    % (perfil.get("nombre") or (sorted(mails_volcado) or [""])[0],
                       realtor.get("nombre_completo"))),
            **detalle}
