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
                                NUESTRO, cargar, columnas_ig, preparar)
from modelmatch.anios_buyside import BANDAS as B_ANIOS  # noqa: E402
from modelmatch.anios_buyside import etiqueta as etq_anios  # noqa: E402
from modelmatch.auditar_casa import CONFIRMADOS, DUDOSOS  # noqa: E402
from modelmatch.everett import CASA  # noqa: E402
from modelmatch.everett_bandas import BANDAS as B_EVERETT  # noqa: E402
from modelmatch.everett_bandas import etiqueta as etq_everett  # noqa: E402
from modelmatch.extraer import TOPE_POR_REALTOR as TOPE  # noqa: E402

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
    "everett_historico": ["SÍ", "no", "sin comprobar"],
    "everett_12m": ["SÍ", "no", "sin comprobar"],
    "regimen_minado": ["tope 1", "minado antes del tope 1"],
}

#: Las bandas TAMBIEN son vocabulario cerrado: el scoring filtra por igualdad
#: sobre ellas igual que sobre `Confianza`. Se arman desde el codigo, no a
#: mano, y se comprueba que el manual las escriba todas (chequeo 7).
VOCABULARIOS_DE_BANDA = ("everett_u_historico", "everett_u_12m")


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
    ("tercera fila de la tabla", "es la SEGUNDA columna de la tabla"),
    # Un conteo tiene TRES respuestas. «si no» mete el fallo de red en la
    # misma bolsa que el 0, y entonces un error escribe «no trabajo con
    # Everett», que es la exclusion al reves. La tabla 4·B lo decia asi
    # mientras la escalera de bandas decia lo contrario.
    ("si no `\"no\"`", "un conteo tiene TRES respuestas: 1, 0 y sin "
                       "respuesta. «si no» mete el fallo con el 0"),
    ("si no `\"NO\"`", "idem"),
    ("si no \"no\"", "idem"),
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
    print("── 1 bis · TODO numero de columnas que el manual cite ──")
    # Los numeros escritos a mano se desfasan SIEMPRE. Ya paso tres veces:
    # decia 34 cuando habia 47, y despues 26, 30, 13 y 5 en distintas tablas
    # cuando los valores reales eran otros. En vez de corregirlos uno por uno,
    # se prohibe citar un numero que no sea uno de los reales.
    import re as _re0
    n_ficha = sum(1 for c in COLUMNAS if c[3] == FICHA)
    n_cont = sum(1 for c in COLUMNAS if c[3] == APARTE)
    n_cal = sum(1 for c in COLUMNAS if c[3] == CALC)
    n_nuestras = sum(1 for c in COLUMNAS if c[3] == NUESTRO)
    n_api = n_ficha + n_cont
    # La hoja entera y el bloque de Instagram tambien son numeros legitimos:
    # el plano del archivo los cita, y los genera el mismo script que la tabla
    # de posiciones, asi que no pueden desfasarse.
    n_ig = len(columnas_ig(filas))
    legitimos = {n_ficha, n_cont, n_cal, n_api, n_cal + n_api, n_nuestras,
                 n_ig, len(COLUMNAS) + n_ig}
    print("   numeros validos: %s" % sorted(legitimos))
    for m in _re0.finditer(r"(\d+)\s+columnas", texto):
        cuanto = int(m.group(1))
        if cuanto in legitimos:
            continue
        linea = texto[:m.start()].count("\n") + 1
        fallos.append("linea %d: dice «%s columnas» y no es ninguno de los "
                      "numeros reales %s" % (linea, cuanto, sorted(legitimos)))
        print("   ⚠ linea %d · «%d columnas»" % (linea, cuanto))
    for frase in ("%d columnas" % (n_api + n_cal), "%d de la API" % n_api,
                  "%d se calculan" % n_cal):
        if frase not in texto:
            fallos.append("el manual no dice «%s» y deberia" % frase)

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
    # ⚠ El patron tiene que anclar la apertura al principio de linea y aceptar
    # el lenguaje. Sin eso, `\n```\n(.*?)\n``` ` emparejaba el CIERRE de un
    # bloque con la APERTURA del siguiente y revisaba la prosa de en medio como
    # si fuera un bloque de valores: tres falsos positivos sobre una cita.
    for bloque in _re2.findall(r"^```[a-z]*\n(.*?)^```", texto,
                               _re2.S | _re2.M):
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
    print("── 5 · el tope, el mismo numero en el codigo y en el manual ──")
    # El tope bajo de 2 a 1 y quedaron CUATRO sitios diciendo 2, uno de ellos
    # un bloque de codigo copiable. Un manual que autoriza el doble de lo que
    # el codigo permite no es impreciso: es permiso escrito.
    if "TOPE_POR_REALTOR = %d" % TOPE not in texto:
        fallos.append("el manual no muestra «TOPE_POR_REALTOR = %d»" % TOPE)
    for m in _re0.finditer(r"TOPE_POR_REALTOR = (\d+)", texto):
        if int(m.group(1)) != TOPE:
            linea = texto[:m.start()].count("\n") + 1
            fallos.append("linea %d: el manual muestra TOPE_POR_REALTOR = %s y "
                          "el codigo dice %d" % (linea, m.group(1), TOPE))
    for m in _re0.finditer(r"tope de (\d+) cr[eé]dito", texto):
        if int(m.group(1)) != TOPE:
            linea = texto[:m.start()].count("\n") + 1
            fallos.append("linea %d: dice «tope de %s creditos» y el tope es %d"
                          % (linea, m.group(1), TOPE))
    for m in _re0.finditer(r"por encima de (\d+) cr[eé]dito", texto):
        if int(m.group(1)) != TOPE:
            linea = texto[:m.start()].count("\n") + 1
            fallos.append("linea %d: el chequeo de corrida permite %s creditos "
                          "y el tope es %d" % (linea, m.group(1), TOPE))
    print("   tope del codigo: %d" % TOPE)

    print("")
    print("── 6 · los ids de Everett: tres copias, una sola lista ──")
    # La lista vive duplicada en el codigo --everett.py y auditar_casa.py-- y
    # una tercera vez en el bloque copiable del manual. Un id que falte en una
    # de las tres deja pasar por prospecto nuevo a alguien que ya es cliente.
    del_manual = []
    for bloque in _re2.findall(r"^```[a-z]*\n(.*?)^```", texto,
                               _re2.S | _re2.M):
        lineas_b = [x.strip() for x in bloque.splitlines() if x.strip()]
        if lineas_b and lineas_b[0] == CASA[0]:
            del_manual = lineas_b
            break
    tres = {"everett.py": list(CASA),
            "auditar_casa.py": CONFIRMADOS + DUDOSOS,
            "el manual": del_manual}
    for nombre, lista in tres.items():
        if lista != list(CASA):
            fallos.append("los ids de Everett de %s no coinciden con los de "
                          "everett.py: sobran %s, faltan %s"
                          % (nombre, sorted(set(lista) - set(CASA)),
                             sorted(set(CASA) - set(lista))))
    print("   %d ids · %s" % (len(CASA),
                              "las tres copias coinciden"
                              if all(v == list(CASA) for v in tres.values())
                              else "⚠ DIFIEREN"))

    print("")
    print("── 5 bis · cada bandera tiene su caso de FALLO escrito ──")
    # No alcanza con prohibir «si no»: hay que exigir que el tercer caso este.
    # Una columna cuyo valor sale de un conteo PUEDE quedar «sin comprobar», y
    # si el manual no lo dice, el agente escribe `no` y el fallo de red se
    # vuelve una afirmacion.
    for col in ("¿Produce FHA?", "¿Produce convencional?", "¿Produce VA?",
                "¿Trabajó con Everett · histórico?",
                "¿Trabajó con Everett · 12 meses?"):
        filas_col = [l for l in texto.splitlines()
                     if "`%s`" % col in l and l.startswith("|")]
        if not any("sin comprobar" in l for l in filas_col):
            fallos.append("la bandera `%s` no tiene ninguna fila de tabla que "
                          "diga que hacer cuando la llamada falla "
                          "(`sin comprobar`)" % col)
    print("   5 banderas comprobadas")

    print("")
    print("── 6 bis · las columnas de Instagram, congeladas ──")
    # El generador las DESCUBRE de los datos, para no perder una señal nueva
    # en silencio. El reverso es que el archivo cambiaria de columnas sin que
    # nadie lo decida, y un scoring que lea por posicion se rompe. Asi que la
    # lista vive congelada en el manual y cualquier divergencia FALLA: la
    # decision --agregarla y cambiar de version, o arreglar el scraper-- la
    # toma una persona, no el generador.
    reales = [c[1] for c in columnas_ig(filas)]
    congeladas = []
    for bloque in _re2.findall(r"^```[a-z]*\n(.*?)^```", texto,
                               _re2.S | _re2.M):
        lineas_b = [x.strip() for x in bloque.splitlines() if x.strip()]
        if lineas_b and reales and lineas_b[0] == reales[0]:
            congeladas = lineas_b
            break
    if congeladas != reales:
        sobran = [x for x in reales if x not in congeladas]
        faltan = [x for x in congeladas if x not in reales]
        if sobran:
            fallos.append("los datos traen columnas de Instagram que el "
                          "manual no congela: %s" % sobran)
        if faltan:
            fallos.append("el manual congela columnas de Instagram que los "
                          "datos ya no traen: %s" % faltan)
        if not sobran and not faltan:
            fallos.append("las columnas de Instagram son las mismas pero en "
                          "otro ORDEN que el congelado en el manual")
    print("   %d columnas · %s" % (len(reales),
                                   "coinciden con las congeladas"
                                   if congeladas == reales else "⚠ DIFIEREN"))

    print("")
    print("── 7 · las bandas del manual son las del codigo ──")
    # Las bandas se escribieron a mano en el manual y ya estaban mal: decia
    # «1 · 2 · 3 · 4 · 5-9» cuando el codigo agrupa 3 y 4 en una sola. Un
    # numero de operaciones con Everett mal leido decide una exclusion.
    # No se comprueban solo los CORTES: se comprueba la ETIQUETA, que es lo
    # que alguien lee. La etiqueta se importa del codigo --`etiqueta()`-- en
    # vez de reescribirla aqui, porque una copia se desfasa igual que la del
    # manual y entonces el verificador avalaria el error.
    for nombre, bandas, fn in (("Everett", B_EVERETT, etq_everett),
                               ("historical units", B_ANIOS, etq_anios)):
        for gte, lt in bandas:
            cota = "%d" % lt if lt is not None else "—"
            # La FILA ENTERA, con su etiqueta dentro. Comprobar por separado
            # que la fila existe y que la etiqueta aparece «en alguna parte»
            # daba verde mientras la tabla que el agente COPIA decia `50` y el
            # `50+` bueno vivia tres secciones mas abajo. Es el mismo fallo de
            # siempre: presencia no es correspondencia.
            fila = "| %d | %s | `%s` |" % (gte, cota, fn(gte, lt))
            if fila not in texto:
                fallos.append("%s: la fila de la banda [%s, %s) no es "
                              "exactamente `%s`" % (nombre, gte, lt, fila))
        print("   %-18s %d bandas · cortes y etiquetas" % (nombre, len(bandas)))
    # Y que el codigo no emita una banda fuera de la escala, como pasaba con
    # el `50` pelado, que afirmaba cincuenta exactas.
    validas = {str(etq_everett(g, l)) for g, l in B_EVERETT} | {""}
    for col in VOCABULARIOS_DE_BANDA:
        raros = sorted({str(f.get(col)) for f in filas} - validas - {"None"})
        if raros:
            fallos.append("%s emite %s, que no es ninguna banda de la escala"
                          % (col, raros))
    print("   escala de Everett: %s" % sorted(validas - {""}))

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
