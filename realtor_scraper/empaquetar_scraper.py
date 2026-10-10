"""Empaqueta el scraper de Instagram para correrlo en otro servidor.

Por que un script y no un documento con el codigo pegado: 9.000 lineas
copiadas a un markdown quedan viejas al dia siguiente, y nadie se entera.
Este script LEE el codigo de verdad cada vez que corre, asi que el paquete
siempre es el que esta en produccion. Es la misma razon por la que la tabla
de columnas del manual se genera y no se escribe.

Produce `data/salida/scraper_instagram_portable/` con:

    instagram/        los seis modulos de señales + el orquestador
    navegador.py      el contexto de Chromium y la sesion
    requirements.txt  solo lo que ESTE paquete necesita
    MANUAL.md         el manual operativo, copiado de la skill
    LEEME.md          como arrancar de cero en la maquina nueva
    verificar.py      comprueba que el paquete esta completo y corre

Uso:
    python realtor_scraper/empaquetar_scraper.py
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAQUETE = os.path.join(RAIZ, "realtor_scraper")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DESTINO = os.path.join(RAIZ, "data", "salida", "scraper_instagram_portable")
MANUAL = os.path.join(RAIZ, ".claude", "skills", "instagram-scraping",
                      "SKILL.md")

#: Lo que el scraper de Instagram necesita, y NADA mas.
#:
#: `main.py`, `state_licenses/`, `realtor_com/` y `mmi_enricher.py` son otras
#: capas del repo --licencias estatales, enriquecimiento-- y no entran: un
#: paquete que arrastra lo que no usa obliga a instalar dependencias que no
#: hacen falta y a explicar codigo que nadie va a correr.
MODULOS = [
    ("instagram/__init__.py", "el mapa de los modulos, en orden de dependencia"),
    ("instagram/estado.py", "los diez estados del perfil"),
    ("instagram/verificacion.py", "¿el handle es de esta persona?"),
    ("instagram/idioma.py", "deteccion de idioma con lingua"),
    ("instagram/posts.py", "caption crudo, programas, cadencia, engagement"),
    ("instagram/comentarios.py", "audiencia agregada y anonima"),
    ("instagram/audiencia.py", "las 17 columnas del perfil de audiencia"),
    ("instagram/extraccion.py", "lo UNICO que toca el DOM"),
    ("instagram/finder.py", "el orquestador y la CLI"),
    # `config.py` no es del scraper de Instagram, pero `navegador.py` lo
    # importa para OUTPUT_DIR. Sin el, el paquete importa ocho modulos y
    # revienta en el noveno. Lo caza `verificar.py`, que es para lo que esta.
    ("config.py", "OUTPUT_DIR y constantes compartidas del scraper"),
    ("navegador.py", "contexto de Chromium, sesion y pausas"),
    ("exportar_ig_excel.py", "del CSV al Excel"),
    ("verificar_manuales_ig.py", "el manual contra el codigo"),
]

REQUISITOS = """\
# Lo que necesita el scraper de Instagram, y nada mas.
#
# patchright es un Playwright parcheado para no anunciarse como automatizado.
# El codigo lo intenta primero y cae a playwright si no esta, asi que los dos
# estan listados: con cualquiera de los dos arranca.
patchright>=1.0.0
playwright>=1.44.0
loguru>=0.7.0
openpyxl>=3.1.0
lingua-language-detector>=2.0.0
"""

LEEME = """\
# Scraper de Instagram de realtors — arranque en una maquina nueva

Este paquete lo genero `empaquetar_scraper.py` el %(fecha)s. El codigo se
copio del repositorio tal cual: no hay nada reescrito a mano.

**Lee `MANUAL.md` antes de correr nada.** Este archivo solo dice como arrancar;
el manual dice que hace cada cosa, por que, y como se lee el resultado.

## 1 · Instalar

    python -m venv .venv
    .venv/Scripts/activate        # Windows
    source .venv/bin/activate     # Linux / macOS
    pip install -r requirements.txt
    python -m playwright install chromium

## 2 · Comprobar que el paquete esta completo

    python verificar.py

Comprueba que estan los %(n_modulos)d modulos, que importan, y que el manual
y el codigo dicen lo mismo. **Si esto falla, no sigas.**

## 3 · La sesion de Instagram, una sola vez

    python -m instagram.finder --iniciar-sesion

Abre un navegador con ventana. Se inicia sesion a mano y las cookies quedan en
`output/browser_profile_instagram/`.

⚠ Usa una cuenta DEDICADA. Esa sesion va a leer cientos de perfiles seguidos.

## 4 · El flujo

    python -m instagram.finder --objetivo              # que se va a raspar
    python -m instagram.finder --piloto 20 --con-ventana
    python -m instagram.finder --revisar-piloto        # revision a mano
    python -m instagram.finder --lote                  # pasada 1: el crudo
    python -m instagram.finder --parsear               # pasada 2: el CSV
    python exportar_ig_excel.py                        # el Excel

El piloto con ventana y su revision van ANTES del lote grande. No es
burocracia: es la unica forma de ver que los selectores siguen funcionando
antes de gastar diez horas.

## 5 · Lo que tenes que traer vos

El paquete trae el CODIGO. Los INSUMOS son tuyos:

- **la lista de objetivo**, en `insumos/objetivo.xlsx`, hoja `Realtors PACS`.
  Esa ruta la fijo el empaquetador; en el repo original el libro vive en otro
  lado. Si preferis otra fuente --una base, un CSV-- sustitui
  `cargar_objetivo()` en `instagram/finder.py`: lo unico que tiene que
  devolver es una lista de `Objetivo` con nombre, estado y, si lo tenes,
  handle y licencia.
- **una cuenta de Instagram** para la sesion.

### Las cuatro lineas que NO son copia literal

El codigo del repo asume que hay un repo alrededor. Para que el paquete sea
autocontenido se reescribieron cuatro rutas, y cada una lleva su comentario en
el archivo:

| archivo | antes apuntaba a | ahora |
|---|---|---|
| `verificar_manuales_ig.py` | `.claude/skills/...` | `MANUAL.md`, al lado |
| `exportar_ig_excel.py` | `../data/salida/` **fuera del paquete** | `output/` |
| `config.py` | `latino_re_engine/` | se quito: no viaja |
| `instagram/finder.py` | `../Data_inputIA/Homesi_...xlsx` | `insumos/objetivo.xlsx` |

Todo lo demas es copia byte a byte del codigo de produccion.

## 6 · Donde queda cada cosa

    output/ig_raw/<clave>.json      un crudo por perfil
    output/ig_checkpoint.json       el progreso, para reanudar
    output/ig_signals.csv           LA SALIDA: 50 columnas
    output/ig_audiencia.json        las citas completas

⛔ Nada de esto se versiona: lleva texto de cuentas personales y comentarios
de terceros.

## 7 · Lo que mas facil se rompe

1. **Los selectores del DOM.** Instagram cambia su HTML. Si un lote empieza a
   devolver `sin_grid` en masa, es eso. Los cinco modulos de logica tienen
   pruebas; que pasen dice que el problema es el selector.
2. **Un solo proceso a la vez.** Chromium bloquea el directorio de perfil y el
   checkpoint no tiene bloqueo. Dos lotes en paralelo se pisan.
3. **El codigo de salida miente** si corres con `| tee`. Para saber si termino,
   conta los crudos.
"""

VERIFICAR = '''\
"""¿El paquete esta completo y corre? Esto se corre ANTES del primer lote."""
import importlib
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

# La consola de Windows viene en cp1252 y revienta con los recuadros y las
# tildes. Es LO PRIMERO que hace falta: sin esto el verificador se cae en la
# primera linea que imprime, en la maquina nueva, antes de comprobar nada.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

MODULOS = %(modulos)r

print("── 1 · estan los archivos ──")
faltan = [m for m, _ in MODULOS if not os.path.exists(os.path.join(AQUI, m))]
for m, que in MODULOS:
    hay = os.path.exists(os.path.join(AQUI, m))
    print("   %%-34s %%s  %%s" %% (m, "ok" if hay else "FALTA", que))
if faltan:
    raise SystemExit("\\nfaltan %%d archivos: el paquete esta incompleto"
                     %% len(faltan))

print("")
print("── 2 · importan ──")
for m, _ in MODULOS:
    if not m.endswith(".py") or m.endswith("__init__.py"):
        continue
    nombre = m[:-3].replace("/", ".")
    try:
        importlib.import_module(nombre)
        print("   %%-34s ok" %% nombre)
    except Exception as exc:  # noqa: BLE001
        print("   %%-34s FALLA: %%s" %% (nombre, exc))
        print("")
        print("   Si dice «No module named», falta instalar:")
        print("       pip install -r requirements.txt")
        print("       python -m playwright install chromium")
        raise SystemExit(1)

print("")
print("── 3 · ninguna ruta apunta fuera del paquete ──")
# El codigo original vivia dentro de un repo y daba por hecho lo que tenia
# alrededor: el manual en .claude/skills, la salida en ../data/salida, el
# libro de objetivo en ../Data_inputIA. En un servidor nuevo nada de eso
# existe. El empaquetador las reescribio; esto comprueba que no volvieron.
import re as _re
# `parent.parent` NO esta en la lista: desde `instagram/finder.py` apunta a la
# raiz del paquete, que es correcto. Buscarlo daba un falso positivo, y un
# chequeo que grita por lo que esta bien deja de leerse.
FUERA = [
    (r'"data",\\s*"salida"', "escribe en ../data/salida"),
    (r"Data_inputIA", "busca el libro fuera del paquete"),
    (r"latino_re_engine", "capa que no viaja"),
    (r"\\.claude", "las skills del repo"),
]
escapes = []
for raiz, dirs, archivos in os.walk(AQUI):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for a in archivos:
        # Este archivo LLEVA los patrones, asi que se encontraria a si mismo.
        if not a.endswith(".py") or a == os.path.basename(__file__):
            continue
        ruta = os.path.join(raiz, a)
        for i, linea in enumerate(open(ruta, encoding="utf-8",
                                       errors="replace"), 1):
            if linea.lstrip().startswith("#"):
                continue
            for patron, que in FUERA:
                if _re.search(patron, linea):
                    escapes.append((os.path.relpath(ruta, AQUI), i, que,
                                    linea.strip()[:70]))
for rel, i, que, l in escapes:
    print("   RUTA FUERA  %%s:%%d  %%s" %% (rel, i, que))
    print("               %%s" %% l)
if escapes:
    raise SystemExit("\\n%%d rutas apuntan fuera del paquete: no es portable"
                     %% len(escapes))
print("   ninguna: el paquete es autocontenido")

print("")
print("── 4 · el manual dice lo mismo que el codigo ──")
r = subprocess.run([sys.executable,
                    os.path.join(AQUI, "verificar_manuales_ig.py")],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
print((r.stdout or "").strip()[-600:])
if r.returncode != 0:
    raise SystemExit("el manual y el codigo NO coinciden")

print("")
print("OK · el paquete esta completo. Siguiente paso: --iniciar-sesion")
'''


def main() -> None:
    # Se VACIA en vez de borrarse. En Windows, `rmtree` sobre el directorio
    # falla con WinError 32 si cualquier proceso lo tiene como directorio de
    # trabajo --una consola abierta ahi basta-- y entonces el empaquetado se
    # cae por algo que no tiene que ver con el paquete. Vaciar el contenido
    # consigue lo mismo y no necesita soltar el directorio.
    if os.path.exists(DESTINO):
        for nombre in os.listdir(DESTINO):
            ruta = os.path.join(DESTINO, nombre)
            if os.path.isdir(ruta):
                shutil.rmtree(ruta, ignore_errors=True)
            else:
                try:
                    os.remove(ruta)
                except OSError:
                    pass
    os.makedirs(os.path.join(DESTINO, "instagram"), exist_ok=True)

    print("── copiando el codigo, tal cual esta en el repo ──")
    lineas = 0
    for rel, que in MODULOS:
        origen = os.path.join(PAQUETE, rel)
        if not os.path.exists(origen):
            raise SystemExit("falta en el repo: %s" % rel)
        destino = os.path.join(DESTINO, rel)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.copy2(origen, destino)
        n = sum(1 for _ in open(origen, encoding="utf-8", errors="replace"))
        lineas += n
        print("   %-34s %5d lineas · %s" % (rel, n, que))
    print("   %-34s %5d lineas" % ("TOTAL", lineas))

    # ── Las rutas que apuntan FUERA del paquete ───────────────────────────
    #
    # El codigo del repo asume que hay un repo alrededor: el manual en
    # `.claude/skills/`, la salida en `../data/salida/`, el libro de objetivo
    # en `../Data_inputIA/`. En un servidor nuevo nada de eso existe, y el
    # paquete fallaria escribiendo fuera de si mismo o buscando un xlsx que
    # no esta.
    #
    # Se reescriben, y CADA reescritura se declara en el propio archivo con
    # un comentario y en el LEEME. Son las unicas lineas del paquete que no
    # son copia literal.
    reescrituras = [
        ("verificar_manuales_ig.py", [
            ('BUSQUEDA = os.path.join(SKILLS, "instagram-scraping", '
             '"SKILL.md")',
             'BUSQUEDA = os.path.join(os.path.dirname(os.path.abspath('
             '__file__)),\n                        "MANUAL.md")'
             '  # reescrito por el empaquetador'),
            ('PAQUETE = os.path.join(RAIZ, "realtor_scraper")',
             'PAQUETE = os.path.dirname(os.path.abspath(__file__))'
             '  # reescrito por el empaquetador'),
            # Queda muerta al reescribir BUSQUEDA, y seguia nombrando
            # `.claude/skills`, que en el paquete no existe.
            ('SKILLS = os.path.join(RAIZ, ".claude", "skills")',
             '# SKILLS se quito al empaquetar: el manual vive al lado.'),
        ]),
        ("exportar_ig_excel.py", [
            # Escribia en ../data/salida, o sea FUERA del paquete.
            ('SALIDA = os.path.join(RAIZ, "data", "salida")',
             'SALIDA = os.path.join(os.path.dirname(os.path.abspath('
             '__file__)), "output")  # reescrito: dentro del paquete'),
        ]),
        ("config.py", [
            # Apuntaba a latino_re_engine/, una capa que no viaja. El scraper
            # de Instagram no la usa: se quita para que nadie la busque.
            ('CENSUS_OUTPUT = Path(__file__).parent.parent / "latino_re_engine"'
             ' / "data" / "output" / "latino_market_zip_2024.csv"',
             '# CENSUS_OUTPUT se quito al empaquetar: era de la capa de\n'
             '# licencias estatales, que no viaja con el scraper de Instagram.'),
        ]),
        ("instagram/finder.py", [
            # El libro de objetivo vivia en ../Data_inputIA con un nombre
            # fijo. En el paquete se espera en insumos/, y el LEEME lo dice.
            ('RAIZ_SCRAPER.parent / "Data_inputIA" / '
             '"Homesi_Scoring_Realtors_v3_PACS (2).xlsx"',
             'RAIZ_SCRAPER / "insumos" / "objetivo.xlsx"'
             '  # reescrito por el empaquetador'),
            # El mensaje de error seguia mandando a Data_inputIA, que en el
            # paquete no existe: diria al usuario que mire donde no hay nada.
            ('"Es el insumo de la lista de objetivo. Vive en Data_inputIA/, '
             'que "\n            "esta fuera del control de versiones." % ruta',
             '"Es el insumo de la lista de objetivo. Ponelo ahi, con la hoja "\n'
             '            "\'Realtors PACS\', o sustitui cargar_objetivo() por '
             'tu fuente." % ruta'),
        ]),
    ]
    print("")
    print("── rutas reescritas para que el paquete sea autocontenido ──")
    for rel, cambios in reescrituras:
        destino = os.path.join(DESTINO, rel)
        with open(destino, encoding="utf-8") as fh:
            texto = fh.read()
        for viejo, nuevo in cambios:
            if viejo not in texto:
                raise SystemExit(
                    "no encuentro en %s el texto a reescribir:\n  %s\n\n"
                    "El codigo cambio y el empaquetador no se entero. Mejor "
                    "fallar que entregar un paquete con rutas rotas."
                    % (rel, viejo[:90]))
            texto = texto.replace(viejo, nuevo)
            print("   %-28s %s" % (rel, viejo.split("=")[0].strip()))
        with open(destino, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)

    print("")
    print("── el manual y los textos de arranque ──")
    shutil.copy2(MANUAL, os.path.join(DESTINO, "MANUAL.md"))
    n_man = sum(1 for _ in open(MANUAL, encoding="utf-8"))
    print("   MANUAL.md                      %5d lineas" % n_man)

    for nombre, texto in (
        ("requirements.txt", REQUISITOS),
        ("LEEME.md", LEEME % {"fecha": dt.date.today().isoformat(),
                              "n_modulos": len(MODULOS)}),
        ("verificar.py", VERIFICAR % {"modulos": MODULOS}),
    ):
        with open(os.path.join(DESTINO, nombre), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(texto)
        print("   %-30s generado" % nombre)

    for carpeta, nota in (
        ("output", "Acá escribe el scraper: crudos, checkpoint y CSV.\n"
                   "NADA de esto se versiona ni se comparte: lleva texto de\n"
                   "cuentas personales y comentarios de terceros.\n"),
        ("insumos", "Poné acá `objetivo.xlsx`, con la hoja 'Realtors PACS'.\n"
                    "Es la lista de a quién raspar. No viene con el paquete:\n"
                    "lleva nombres, correos y teléfonos de personas reales.\n"),
    ):
        os.makedirs(os.path.join(DESTINO, carpeta), exist_ok=True)
        with open(os.path.join(DESTINO, carpeta, ".gitignore"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write("*\n!.gitignore\n!LEEME.txt\n")
        with open(os.path.join(DESTINO, carpeta, "LEEME.txt"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(nota)

    # ── El paquete sale VACIO de datos, y se comprueba ───────────────────
    #
    # Probarlo deja dentro lo que uno le puso: un objetivo.xlsx con 4.249
    # realtors, unos crudos, el CSV derivado. Si despues se comprime y se
    # manda, eso es una fuga -- y es facil que pase, porque probarlo es
    # justo lo que hay que hacer antes de mandarlo.
    datos = []
    for carpeta in ("output", "insumos"):
        for raiz, _d, archivos in os.walk(os.path.join(DESTINO, carpeta)):
            for a in archivos:
                if a in (".gitignore", "LEEME.txt"):
                    continue
                datos.append(os.path.relpath(os.path.join(raiz, a), DESTINO))
    if datos:
        raise SystemExit(
            "⛔ el paquete tiene %d archivos de DATOS dentro:\n    %s\n\n"
            "Se regenera vaciandolo, asi que esto no deberia pasar. Si pasa, "
            "revisalo antes de comprimir nada." % (len(datos),
                                                   "\n    ".join(datos[:8])))

    print("")
    print("paquete en %s" % DESTINO)
    print("%d archivos de codigo · %d lineas" % (len(MODULOS), lineas))
    print("")
    print("Para probarlo en la maquina nueva:")
    print("    pip install -r requirements.txt")
    print("    python -m playwright install chromium")
    print("    python verificar.py")


if __name__ == "__main__":
    main()
