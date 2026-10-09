"""¿Los manuales de Instagram dicen lo MISMO que el codigo?

La leccion viene del manual de Model Match, donde se desfaso cuatro veces: un
manual que promete columnas que no existen, o que lista nueve valores donde el
codigo emite diez, no es impreciso -- manda a un agente a construir contra algo
que no esta.

Lo que se comprueba, y todo se LEE DEL CODIGO, nunca se reescribe aca:

  1. las 50 columnas del CSV, en orden y con su numero;
  2. los estados del perfil;
  3. los valores de confianza del handle;
  4. las rutas que no son handles;
  5. las constantes de ritmo y volumen;
  6. las tres consultas de busqueda.

Uso:
    python realtor_scraper/verificar_manuales_ig.py
"""
from __future__ import annotations

import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAQUETE = os.path.join(RAIZ, "realtor_scraper")
sys.path.insert(0, PAQUETE)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILLS = os.path.join(RAIZ, ".claude", "skills")
BUSQUEDA = os.path.join(SKILLS, "instagram-busqueda", "SKILL.md")
MINADO = os.path.join(SKILLS, "instagram-minado", "SKILL.md")

FUENTE_FINDER = os.path.join(PAQUETE, "instagram", "finder.py")
FUENTE_EXTRAC = os.path.join(PAQUETE, "instagram", "extraccion.py")
FUENTE_ESTADO = os.path.join(PAQUETE, "instagram", "estado.py")
FUENTE_VERIF = os.path.join(PAQUETE, "instagram", "verificacion.py")
FUENTE_AUDI = os.path.join(PAQUETE, "instagram", "audiencia.py")


def leer(ruta: str) -> str:
    return open(ruta, encoding="utf-8").read()


def lista_literal(fuente: str, nombre: str) -> list[str]:
    """Las cadenas de una lista o set literal, SIN importar el modulo.

    Se parsea el texto en vez de importar porque estos modulos arrastran
    playwright y loguru, y el verificador tiene que correr en una maquina que
    solo quiera revisar la documentacion.
    """
    m = re.search(r"^%s\s*=\s*[\[{(]" % re.escape(nombre), fuente, re.M)
    if not m:
        raise SystemExit("no se encontro %s en la fuente" % nombre)
    i = m.end() - 1
    abre, nivel = fuente[i], 0
    cierra = {"[": "]", "{": "}", "(": ")"}[abre]
    for j in range(i, len(fuente)):
        if fuente[j] == abre:
            nivel += 1
        elif fuente[j] == cierra:
            nivel -= 1
            if nivel == 0:
                cuerpo = fuente[i + 1:j]
                break
    else:
        raise SystemExit("%s no cierra" % nombre)
    # Se quitan los comentarios antes de sacar las cadenas: un `#: "algo"`
    # dentro del bloque no es un valor.
    limpio = "\n".join(l.split("#")[0] for l in cuerpo.splitlines())
    return re.findall(r"[\"']([^\"']+)[\"']", limpio)


def constante(fuente: str, nombre: str) -> str:
    m = re.search(r"^%s\s*=\s*(.+)$" % re.escape(nombre), fuente, re.M)
    if not m:
        raise SystemExit("no se encontro la constante %s" % nombre)
    return m.group(1).split("#")[0].strip()


def main() -> None:
    fallos: list[str] = []
    finder = leer(FUENTE_FINDER)
    audi = leer(FUENTE_AUDI)
    man_b = leer(BUSQUEDA)
    man_m = leer(MINADO)

    print("── 1 · las columnas del CSV, en orden y con su numero ──")
    base = lista_literal(finder, "COLUMNAS_CSV")
    de_audiencia = lista_literal(audi, "COLUMNAS_AUDIENCIA")
    columnas = base + de_audiencia
    print("   base %d + audiencia %d = %d columnas"
          % (len(base), len(de_audiencia), len(columnas)))
    for i, col in enumerate(columnas, 1):
        fila = "| %d | `%s` |" % (i, col)
        if fila not in man_m:
            fallos.append("el manual de minado no trae la fila exacta `%s`"
                          % fila)
    # Y al reves: que no prometa columnas que no existen.
    for m in re.finditer(r"^\| (\d+) \| `([a-z_0-9]+)` \|", man_m, re.M):
        n, col = int(m.group(1)), m.group(2)
        if col not in columnas:
            fallos.append("el manual nombra la columna `%s`, que no existe"
                          % col)
        elif columnas[n - 1] != col:
            fallos.append("el manual pone `%s` en la posicion %d y el codigo "
                          "la tiene en la %d"
                          % (col, n, columnas.index(col) + 1))
    if "**50 columnas**" not in man_m and len(columnas) == 50:
        fallos.append("el manual no dice «50 columnas» y deberia")

    print("")
    print("── 2 · los estados del perfil ──")
    estados = re.findall(r'^\s{4}[A-Z_]+ = "([a-z_]+)"',
                         leer(FUENTE_ESTADO), re.M)
    print("   %d estados: %s" % (len(estados), ", ".join(estados)))
    for e in estados:
        if "`%s`" % e not in man_b:
            fallos.append("el manual de busqueda no nombra el estado `%s`" % e)

    print("")
    print("── 3 · la confianza del handle ──")
    conf = re.findall(r'^\s{4}[A-Z]+ = "([a-z]+)"', leer(FUENTE_VERIF), re.M)
    print("   %s" % ", ".join(conf))
    for c in conf:
        if "`%s`" % c not in man_b:
            fallos.append("el manual no nombra la confianza `%s`" % c)

    print("")
    print("── 4 · las rutas que NO son handles ──")
    no_handles = sorted(lista_literal(finder, "_NO_SON_HANDLES"))
    congeladas = []
    # ⚠ El patron acepta el lenguaje de apertura. Sin eso, `^```\n` emparejaba
    # el CIERRE de un bloque ```python con la APERTURA del siguiente y leia la
    # prosa de en medio como si fuera la lista. Es el mismo fallo que ya
    # aparecio en el verificador de Model Match.
    for bloque in re.findall(r"^```[a-z]*\n(.*?)^```", man_b, re.S | re.M):
        lineas = [x.strip() for x in bloque.splitlines() if x.strip()]
        if lineas and lineas[0] == "p":
            congeladas = sorted(lineas)
            break
    print("   codigo %d · manual %d" % (len(no_handles), len(congeladas)))
    if congeladas != no_handles:
        faltan = sorted(set(no_handles) - set(congeladas))
        sobran = sorted(set(congeladas) - set(no_handles))
        if faltan:
            fallos.append("el manual no congela estas rutas: %s" % faltan)
        if sobran:
            fallos.append("el manual congela rutas que no existen: %s" % sobran)

    print("")
    print("── 5 · las constantes de ritmo y volumen ──")
    extrac = leer(FUENTE_EXTRAC)
    comprobaciones = [
        (constante(finder, "MAX_CANDIDATOS"), man_b, "MAX_CANDIDATOS"),
        (constante(extrac, "N_POSTS_CRUDO"), man_m, "N_POSTS_CRUDO"),
    ]
    for valor, manual, nombre in comprobaciones:
        print("   %-18s %s" % (nombre, valor))
        if valor not in manual:
            fallos.append("el manual no dice el valor de %s (%s)"
                          % (nombre, valor))
    for nombre, manual in (("PAUSA_BUSQUEDA", man_b),
                           ("PAUSA_ENTRE_POSTS", man_m),
                           ("PAUSA_ENTRE_PERFILES", man_m)):
        fuente = finder if nombre == "PAUSA_BUSQUEDA" else extrac
        crudo = constante(fuente, nombre)
        nums = re.findall(r"[\d.]+", crudo)
        print("   %-18s %s" % (nombre, crudo))
        # El manual escribe los rangos con coma decimal: 2,5 a 5,0.
        for n in nums:
            con_coma = n.replace(".", ",")
            if n not in manual and con_coma not in manual:
                fallos.append("el manual no trae el %s de %s"
                              % (n, nombre))

    print("")
    print("── 6 · las tres consultas de busqueda ──")
    consultas = re.findall(r"'(site:instagram\.com[^']+)'", finder)
    print("   %d consultas" % len(consultas))
    # El primer %s es el nombre y el segundo el estado, en las tres. Se
    # sustituyen POR POSICION, no por reemplazo de texto: reemplazar dejaba la
    # segunda ranura con el nombre y el chequeo exigia una consulta imposible.
    for c in consultas:
        trozos = c.split("%s")
        patron = trozos[0]
        for valor, resto in zip(("<nombre completo>", "<estado>"), trozos[1:]):
            patron += valor + resto
        if patron not in man_b:
            fallos.append("el manual no trae la consulta `%s`" % patron)

    print("")
    if fallos:
        print("FALLA · %d problemas:" % len(fallos))
        for f in fallos:
            print("   · %s" % f)
        raise SystemExit(1)
    print("OK · los dos manuales y el codigo dicen lo mismo.")


if __name__ == "__main__":
    main()
