"""Lo que nunca se le dice a un realtor. El bloque F del dossier.

Por que es una regla ejecutable y no una lista en un documento
-------------------------------------------------------------
Los tres son errores que suenan bien al escribirlos. Un BD con prisa escribe
"te consigo la exención de tasación" porque es verdad que la conseguimos -- y
lo que no es verdad es que sea *nuestra*. La lista en un documento no frena esa
frase; una guarda que revienta al construir el texto, si.

Es la misma forma que `PALABRAS_PROHIBIDAS` y `PROMESAS_DE_MATERIAL`.

Los tres
--------
1 · **No sustituir al lender, ampliar la capacidad.** Un realtor con un lender
    que funciona no lo cambia, y pedirselo pone la conversacion en un terreno
    donde perdemos. Lo que se ofrece es el caso que hoy se le cae.

2 · **Las exenciones de tasación, FHA 203k, VA, USDA y las ayudas para el down
    payment NO son ventaja propia.** Son programas publicos, y cualquier
    originador elegible los obtiene igual. Presentarlos como nuestros es una
    ventaja que el realtor puede desmentir con una llamada, y ahi se cae todo
    lo demas que dijimos.

3 · **Nunca prometer pago por referir.** Ademas de falso, RESPA Section 8
    prohibe pagar por la derivacion de un negocio de settlement service. No es
    una preferencia de estilo: es la clase de frase que le cuesta la licencia a
    alguien.
"""
from __future__ import annotations

import re


class NuncaSeDice(ValueError):
    """El texto dice algo que no se le dice a un realtor. Con su razón."""


#: (patrón, qué se dijo, por qué no). El patrón es deliberadamente amplio: un
#: falso positivo se corrige mirando la frase, y un falso negativo sale a la
#: calle.
#: Dos cosas que costaron tres falsos negativos y conviene no repetir:
#:
#: 1 · El acento va en la CLASE, no fuera: `c[aá]mbi` y no `cambi`. Ignorar
#:     mayúsculas no ignora tildes, y `Cámbiate` se escapaba entero.
#: 2 · Ningún `\b` al final de una alternativa que termina en PREFIJO.
#:     `referi\b` no puede coincidir nunca dentro de `referir`: la `r` que sigue
#:     es carácter de palabra, así que no hay límite ahí. El patrón parecía más
#:     estricto y era inerte.
NUNCA = (
    (r"\b(c[aá]mbi(a|ar|á)te?|dej[aá]|sustitu(ye|ir|í)|reemplaz(a|ar|á)|"
     r"bot(a|á)|saca?te)\b"
     r"[^.]{0,40}\b(lender|prestamista|banco)\b",
     "propone sustituir a su lender",
     "Un realtor con un lender que funciona no lo cambia. Lo que se ofrece es "
     "ampliar su capacidad: el caso que hoy se le cae."),

    (r"\b(nuestr[oa]s?|exclusiv[oa]s?|solo nosotros|únicos?|unicos?)\b"
     r"[^.]{0,60}\b(203k|exenci(ó|o)n de tasaci(ó|o)n|appraisal waiver|"
     r"\bVA\b|USDA|DPA|down payment assistance)\b",
     "presenta un programa público como ventaja propia",
     "Las exenciones de tasación, FHA 203k, VA, USDA y las ayudas para el down "
     "payment son programas públicos: cualquier originador elegible los obtiene "
     "igual. Presentarlos como nuestros es una ventaja que el realtor desmiente "
     "con una llamada."),

    (r"\b(203k|exenci(ó|o)n de tasaci(ó|o)n|appraisal waiver|USDA|"
     r"down payment assistance|\bDPA\b)\b[^.]{0,40}"
     r"\b(nuestr[oa]s?|exclusiv[oa]s?|solo (con )?nosotros)\b",
     "presenta un programa público como ventaja propia",
     "Mismo caso, con el orden invertido: el programa primero y la posesión "
     "después."),

    # `refi?er` y no `refer`: el verbo cambia de raíz. `referir`, `referido` y
    # `referencia` traen `refer`, pero `refiera` y `refieren` traen `refier`.
    # Un patrón que solo mira `refer` deja pasar justo la forma en que se
    # escribe la promesa: «a quien nos refiera».
    (r"\b(te pag(o|amos|aremos|an)|"
     r"comisi[oó]n[^.]{0,24}\brefi?er|"
     r"pag(o|amos|ar)[^.]{0,24}\brefi?er|"
     r"te damos [^.]{0,24}por cada (referido|cliente)|"
     r"\brebate\b|\bkickback\b|"
     r"(bono|incentivo)[^.]{0,24}\brefi?er)",
     "promete pago por referir",
     "Además de falso, RESPA Section 8 prohíbe pagar por la derivación de un "
     "negocio de settlement service. Es la clase de frase que le cuesta la "
     "licencia a alguien."),
)

_COMPILADOS = tuple((re.compile(p, re.IGNORECASE), q, por) for p, q, por in NUNCA)


def verificar_nunca(texto: str) -> None:
    """Revienta si el texto dice algo de la lista, con la razón."""
    t = texto or ""
    for patron, que, por_que in _COMPILADOS:
        m = patron.search(t)
        if m:
            raise NuncaSeDice(
                "%s: %r\n%s\n  en: %s"
                % (que, m.group(0)[:70], por_que, t[:160]))


#: El bloque F, para mostrarlo. Es lo que el BD tiene que tener delante cuando
#: escribe a mano, porque la guarda solo cubre lo que genera el sistema.
BLOQUE_F = (
    {"no": "No le propongas cambiar de lender",
     "si": "Ofrécele ampliar su capacidad: el caso que hoy se le cae",
     "por_que": "Un realtor con un lender que funciona no lo cambia, y "
                "pedírselo pone la conversación donde perdemos."},
    {"no": "No presentes como ventaja nuestra las exenciones de tasación, "
           "FHA 203k, VA, USDA ni las ayudas para el down payment",
     "si": "Nómbralos como lo que son y habla de cómo los operamos: tiempos, "
           "documentación y quién sostiene el caso",
     "por_que": "Son programas públicos y cualquier originador elegible los "
                "obtiene igual. Es una ventaja que desmiente con una llamada."},
    {"no": "Nunca prometas pago por referir",
     "si": "El intercambio es de capacidad, no de dinero",
     "por_que": "RESPA Section 8 prohíbe pagar por la derivación de un negocio "
                "de settlement service."},
)
