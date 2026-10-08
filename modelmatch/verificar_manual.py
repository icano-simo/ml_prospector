"""¿El manual dice los MISMOS textos exactos que produce el código?

Un manual que escribe «alta, confirmada por teléfono» cuando el código emite
«alta · confirmada por teléfono» no es un manual impreciso: es un manual que
rompe el scoring, porque el scoring filtra por igualdad exacta. Con la coma,
51 realtors perderian su identificacion valida.

Por eso los vocabularios no se escriben a mano en el manual y se cruzan los
dedos: se comprueban. Este script recorre los valores que el codigo PUEDE
emitir en cada columna de vocabulario cerrado, los busca en el texto del
manual, y falla nombrando el que falte.

Uso:
    python modelmatch/verificar_manual.py
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.a_excel import (APARTE, CALC, COLUMNAS, FICHA,  # noqa: E402
                                NUESTRO, cargar, preparar)

MANUAL = os.path.join(RAIZ, ".claude", "skills", "modelmatch-minado",
                      "SKILL.md")

#: Columnas de vocabulario CERRADO: solo pueden tomar estos valores. Si el
#: codigo emite uno que no esta aqui, el manual tampoco lo tendra y este
#: script lo caza.
VOCABULARIOS = {
    "confianza_final": [
        "alta",
        "alta · confirmada por teléfono",
        "contradicha por el teléfono",
        "media",
        "baja",
        "ninguna",
        "no encontrado",
    ],
    "match_criterio": [
        "email_exacto",
        "email_exacto_varios_perfiles",
        "nombre_exacto_y_estado",
        "nombre_y_estado_varios",
        "nombre_exacto_sin_estado",
        "ambiguo",
        "sin_candidatos",
    ],
    "fidelidad": [
        "sin operaciones financiadas atribuidas",
        "CAUTIVO · 1 solo LO",
        "muy concentrado · 2-3 LOs",
        "concentrado · 4-6 LOs",
        "reparte · 7-12 LOs",
        "reparte mucho · 13+ LOs",
    ],
    "revisar_por": [
        "no se encontró en Model Match",
        "identificado solo por nombre y el teléfono NO coincide: puede ser "
        "otra persona con el mismo nombre",
        "identificado solo por nombre, sin confirmar con correo ni teléfono",
    ],
    "telefono_coincide": ["si", "no", "sin_dato"],
    "cambio_de_brokerage": ["si", "no", "sin_dato"],
    "encontrado_txt": ["sí", "NO"],
    "hace_fha": ["sí", "no", "sin comprobar"],
    "trabaja_con_la_casa": ["SÍ", "no", "sin comprobar"],
}


#: Variantes PROHIBIDAS: textos que se parecen a los buenos y no lo son.
#:
#: Esta lista existe por un fallo concreto de este mismo script: paso en
#: verde mientras el manual seguia diciendo «alta, confirmada por telefono»
#: con coma en el paso 3. Comprobar que los valores BUENOS esten presentes no
#: detecta que haya valores MALOS en otra parte del archivo, y el agente que
#: lee el paso 3 antes que la seccion E copia el equivocado.
#:
#: (patron a buscar, por que esta mal)
PROHIBIDAS = [
    ("alta, confirmada", "lleva separador `·`, no coma"),
    ("alta confirmada por", "falta el separador `·`"),
    ("«a revisión»", "el valor es `contradicha por el teléfono`"),
    ("quedaban M créditos", "el centinela dice `creditos` sin acento y "
                            "termina en `del tope`"),
    ("quedaban <M> créditos", "idem"),
    ("creditos del tope\"", "idem: revisar comillas y formato"),
    ("34 columnas aprobadas", "son 47: 34 de la API y 13 calculadas"),
    ("tercera fila de la tabla", "es la SEGUNDA columna de la tabla"),
    ("= `muy concentrado`;", "el texto completo es `muy concentrado · 2-3 LOs`"),
    ("1 = `CAUTIVO · 1 solo LO`;", "n=0 tambien hay que cubrirlo y no es "
                                   "cautivo"),
]


def main() -> None:
    texto = open(MANUAL, encoding="utf-8").read()
    fallos = []

    print("── 0 · variantes PROHIBIDAS en cualquier parte del manual ──")
    for patron, porque in PROHIBIDAS:
        if patron in texto:
            # La linea, para poder ir derecho.
            linea = next((i for i, l in enumerate(texto.splitlines(), 1)
                          if patron in l), "?")
            print("   ⚠ linea %s · %r → %s" % (linea, patron, porque))
            fallos.append("variante prohibida en linea %s: %r (%s)"
                          % (linea, patron, porque))
    if not fallos:
        print("   ninguna")
    print("")

    print("── 1 · vocabularios cerrados ──")
    for col, valores in VOCABULARIOS.items():
        faltan = [v for v in valores if v not in texto]
        print("   %-22s %d valores · faltan %d" % (col, len(valores),
                                                   len(faltan)))
        for v in faltan:
            fallos.append("vocabulario %s: falta %r" % (col, v))

    print("")
    print("── 2 · el codigo no emite valores fuera del vocabulario ──")
    filas = [preparar(f) for f in cargar()]
    for col, valores in VOCABULARIOS.items():
        emitidos = {f.get(col) for f in filas}
        raros = sorted(x for x in emitidos
                       if x not in valores and x not in (None, ""))
        if raros:
            print("   %-22s ⚠ emite %s" % (col, raros))
            for x in raros:
                fallos.append("%s emite %r y no esta en VOCABULARIOS" % (col, x))
        else:
            print("   %-22s ok" % col)

    print("")
    print("── 3 · toda columna esta nombrada Y con su posicion ──")
    for i, (clave, titulo, _an, fuente, _sig) in enumerate(COLUMNAS, 1):
        if fuente == NUESTRO:
            continue
        if "`%s`" % titulo not in texto:
            fallos.append("columna sin nombrar en el manual: %s" % titulo)
        # La tabla de posiciones: la fila «| <n> | `<titulo>` |».
        if "| %d | `%s` |" % (i, titulo) not in texto:
            fallos.append("columna sin su numero de posicion (%d): %s"
                          % (i, titulo))
    n_mm = sum(1 for c in COLUMNAS if c[3] in (FICHA, APARTE))
    n_calc = sum(1 for c in COLUMNAS if c[3] == CALC)
    print("   de Model Match %d · calculadas %d · total a documentar %d"
          % (n_mm, n_calc, n_mm + n_calc))

    print("")
    print("── 1 bis · el manual dice el numero REAL de columnas ──")
    # El numero sale citado en el texto y en la descripcion. Si alguien agrega
    # una columna y no toca el texto, el manual promete una cosa y el codigo
    # entrega otra. Ya paso: decia 34 y habia 47.
    n_api = sum(1 for c in COLUMNAS if c[3] in (FICHA, APARTE))
    n_cal = sum(1 for c in COLUMNAS if c[3] == CALC)
    for frase, cuanto in (("%d columnas" % (n_api + n_cal), n_api + n_cal),
                          ("%d de la API" % n_api, n_api),
                          ("%d se calculan" % n_cal, n_cal)):
        if frase not in texto:
            fallos.append("el manual no dice «%s» y deberia" % frase)
        else:
            print("   dice «%s» · ok" % frase)

    print("")
    print("── 3 bis bis · columnas RETIRADAS que el manual sigue nombrando ──")
    # La direccion que faltaba. El chequeo 3 mira que cada columna del codigo
    # este en el manual; este mira lo contrario: que el manual no prometa
    # columnas que ya no existen. Fallo de verdad -- se retiraron cuatro
    # columnas y el manual siguio explicandolas durante toda una version,
    # mientras el verificador daba verde.
    titulos = {c[1] for c in COLUMNAS}
    for retirada in ("Su loan officer principal", "% por su LO principal",
                     "Lenders (si cupo en el tope)", "Originadores (si cupo)",
                     "¿Ya financia con la casa?",
                     "Operaciones con la casa (al menos)"):
        if retirada in titulos:
            continue                      # sigue viva: no hay nada que mirar
        if "`%s`" % retirada in texto:
            linea = next((i for i, l in enumerate(texto.splitlines(), 1)
                          if "`%s`" % retirada in l), "?")
            fallos.append("linea %s: el manual nombra `%s`, que ya no es una "
                          "columna" % (linea, retirada))
            print("   ⚠ linea %s · %s" % (linea, retirada))
    print("   revisadas las retiradas conocidas")

    print("")
    print("── 3 bis · tablas partidas ──")
    # Una tabla markdown se corta con la primera linea que no empieza por `|`.
    # Si despues de ese corte vuelven filas `|`, la tabla quedo en dos y las
    # de abajo son invisibles para quien la lea entera. Paso de verdad: un
    # aviso insertado en medio de la tabla D dejo cuatro columnas sueltas.
    lineas = texto.splitlines()
    en_tabla = False
    corte = None
    for i, l in enumerate(lineas, 1):
        es_fila = l.startswith("|")
        if es_fila and not en_tabla:
            en_tabla, corte = True, None
        elif not es_fila and en_tabla:
            if l.strip() == "":
                en_tabla = False          # fin normal de la tabla
            else:
                corte = i                 # texto pegado: sospechoso
        elif es_fila and corte:
            fallos.append("tabla partida: la linea %d corta una tabla y en la "
                          "%d vuelven las filas" % (corte, i))
            corte = None
    print("   revisadas %d lineas" % len(lineas))

    print("")
    print("── 3 quater · bloques copiables sin anotaciones ──")
    # Un bloque ``` cuyas lineas son valores para copiar NO puede llevar
    # comentarios al margen: quien copia se lleva el comentario dentro del
    # valor. Paso dos veces --en los ids de la casa y en los textos de
    # fidelidad-- asi que deja de ser un descuido y pasa a comprobarse.
    #
    # Se revisan solo los bloques SIN lenguaje (``` pelado), que son los de
    # valores; los de JSON y los de rutas llevan llaves y barras a proposito.
    import re as _re2
    for bloque in _re2.findall(r"\n```\n(.*?)\n```", texto, _re2.S):
        for linea in bloque.splitlines():
            if not linea.strip() or linea.lstrip().startswith(("/", "{", "}")):
                continue
            # Dos o mas espacios seguidos de algo, o un parentesis, o una
            # flecha: todo eso es anotacion, no valor.
            if _re2.search(r"\S {2,}\S", linea) or "←" in linea \
                    or _re2.search(r"\(\s*n\s*=", linea):
                fallos.append("bloque copiable con anotacion al margen: %r"
                              % linea.strip()[:70])
    print("   revisados los bloques de valores")

    print("")
    print("── 3 ter · referencias internas que apunten a algo ──")
    import re as _re
    secciones = set(_re.findall(r"^#{2,4} ([^\n]+)$", texto, _re.M))
    pasos = set(_re.findall(r"^### Paso (\d+)", texto, _re.M))
    for ref in sorted(set(_re.findall(r"(?:secci[óo]n|tabla) (\d+·[A-Z]|[A-Z] bis|[A-Z] ter)", texto))):
        if not any(ref.split("·")[-1] in s for s in secciones):
            fallos.append("referencia a una seccion que no existe: %s" % ref)
    for ref in sorted(set(_re.findall(r"paso (\d+)", texto))):
        if ref not in pasos:
            fallos.append("referencia al paso %s, que no existe" % ref)
    print("   %d secciones y %d pasos reales" % (len(secciones), len(pasos)))

    print("")
    print("── 4 · cada caso de identificacion tiene sus tres textos ──")
    # Cada criterio tiene que aparecer en una fila de la tabla E bis, o sea
    # en la misma linea que una Confianza valida.
    for criterio in VOCABULARIOS["match_criterio"]:
        lineas = [l for l in texto.splitlines()
                  if "`%s`" % criterio in l and l.startswith("|")]
        if not lineas:
            fallos.append("criterio sin fila en la tabla de casos: %s"
                          % criterio)
            continue
        if not any(any("`%s`" % c in l for c in VOCABULARIOS["confianza_final"])
                   for l in lineas):
            fallos.append("criterio %s aparece sin su Confianza al lado"
                          % criterio)
    print("   %d criterios comprobados" % len(VOCABULARIOS["match_criterio"]))

    print("")
    if fallos:
        print("FALLA · %d problemas:" % len(fallos))
        for f in fallos:
            print("   · %s" % f)
        raise SystemExit(1)
    print("OK · el manual y el codigo dicen lo mismo, carácter a carácter.")


if __name__ == "__main__":
    main()
