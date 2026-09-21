"""Guarda redundante: falla el commit si hay PII en el indice de git.

Por que existe
--------------
Este repo estuvo PUBLICO en GitHub con cinco archivos que traian nombre, email,
telefono y disposiciones de CRM de unas 33.000 personas. El historial se purgo
el 2026-09-21 y los archivos se movieron a ../ml_prospector_datos_privados/.

El .gitignore no alcanza. Un `git add -f`, un `.gitignore` editado sin pensar o
un archivo nuevo con otro nombre lo pasan por encima sin ruido. Esta guarda
mira el indice, no el disco, y falla ruidosamente.

Es redundante a proposito.

Uso
---
    python scripts/verificacion/sin_pii_versionada.py

Codigo de salida 1 si encuentra algo. Instalada como pre-commit por
scripts/verificacion/instalar_hooks.py.
"""
from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import sys
import zipfile

# Nombres de archivo que ya filtraron una vez. Coincidencia exacta de basename.
NOMBRES_QUEMADOS = {
    "calls.xlsx",
    "historico realtors.xlsx",
    "mmi data.xlsx",
    "historico_scored.csv",
    "realtors.csv",
}

# Extensiones que se inspeccionan por contenido.
EXT_TABULARES = {".csv", ".tsv", ".xlsx", ".xlsm"}

# Encabezados de columna que delatan datos de contacto de una persona.
# Se buscan como token completo para no disparar con, por ejemplo,
# "company_email_domain".
COLUMNAS_PII = [
    r"e[-_ ]?mail",
    r"email_mmi",
    r"phone",
    r"telefono",
    r"tel[eé]fono",
    r"mobile",
    r"cell",
    r"first[_ ]?name",
    r"last[_ ]?name",
    r"full[_ ]?name",
    r"nombre",
    r"apellido",
    r"street",
    r"address",
    r"direccion",
]
RE_COLUMNAS_PII = re.compile(r"^(%s)$" % "|".join(COLUMNAS_PII), re.IGNORECASE)

# Columnas de CRM: no son PII por si mismas, pero unidas a un nombre describen
# el comportamiento de una persona identificada frente a nuestro equipo.
COLUMNAS_CRM = [
    r"converted",
    r"was_called",
    r"call_duration.*",
    r"calls_answered",
    r"total_calls",
    r"answer_rate",
    r"lead[_ ]?status",
    r"disposition",
]
RE_COLUMNAS_CRM = re.compile(r"^(%s)$" % "|".join(COLUMNAS_CRM), re.IGNORECASE)

MAX_BYTES_INSPECCION = 2_000_000


def archivos_en_indice() -> list[str]:
    """Rutas que git tiene en el indice, listas para commitear."""
    salida = subprocess.run(
        ["git", "ls-files", "--cached", "-z"],
        capture_output=True,
        check=True,
    ).stdout
    return [p.decode("utf-8") for p in salida.split(b"\0") if p]


def leer_del_indice(ruta: str) -> bytes | None:
    """Contenido de la version que esta en el indice, no la del disco."""
    res = subprocess.run(
        ["git", "show", ":%s" % ruta],
        capture_output=True,
    )
    if res.returncode != 0:
        return None
    return res.stdout


def encabezado_csv(datos: bytes) -> list[str]:
    texto = datos[:65536].decode("utf-8", errors="replace")
    primera = texto.splitlines()[0] if texto.splitlines() else ""
    try:
        return next(csv.reader(io.StringIO(primera)))
    except (StopIteration, csv.Error):
        return []


def encabezados_xlsx(datos: bytes) -> list[str]:
    """Primera fila de cada hoja, sin openpyxl: se lee el XML del zip."""
    encabezados: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(datos))
    except zipfile.BadZipFile:
        return encabezados
    with zf:
        compartidas: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            xml = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
            compartidas = re.findall(r"<t[^>]*>(.*?)</t>", xml, re.DOTALL)
        for nombre in zf.namelist():
            if not nombre.startswith("xl/worksheets/sheet"):
                continue
            xml = zf.read(nombre).decode("utf-8", errors="replace")
            m = re.search(r'<row[^>]*r="1"[^>]*>(.*?)</row>', xml, re.DOTALL)
            if not m:
                continue
            for celda in re.findall(r"<c[^>]*?(?:\s|>)(.*?)</c>", m.group(1), re.DOTALL):
                inline = re.search(r"<t[^>]*>(.*?)</t>", celda, re.DOTALL)
                if inline:
                    encabezados.append(inline.group(1))
                    continue
                val = re.search(r"<v>(\d+)</v>", celda)
                if val and compartidas:
                    idx = int(val.group(1))
                    if idx < len(compartidas):
                        encabezados.append(compartidas[idx])
    return encabezados


def revisar() -> list[str]:
    hallazgos: list[str] = []

    for ruta in archivos_en_indice():
        base = os.path.basename(ruta).lower()
        ext = os.path.splitext(base)[1]

        if base in NOMBRES_QUEMADOS:
            hallazgos.append(
                "%s -- nombre de archivo que ya filtro PII una vez" % ruta
            )
            continue

        if ext not in EXT_TABULARES:
            continue

        datos = leer_del_indice(ruta)
        if datos is None:
            continue
        if len(datos) > MAX_BYTES_INSPECCION and ext in (".xlsx", ".xlsm"):
            hallazgos.append(
                "%s -- hoja de calculo de %d bytes en el indice, demasiado "
                "grande para ser una plantilla" % (ruta, len(datos))
            )
            continue

        if ext in (".csv", ".tsv"):
            cols = encabezado_csv(datos)
        else:
            cols = encabezados_xlsx(datos)

        pii = sorted({c for c in cols if RE_COLUMNAS_PII.match(c.strip())})
        crm = sorted({c for c in cols if RE_COLUMNAS_CRM.match(c.strip())})

        if pii:
            hallazgos.append(
                "%s -- columnas de contacto: %s" % (ruta, ", ".join(pii))
            )
        elif crm:
            hallazgos.append(
                "%s -- columnas de CRM: %s" % (ruta, ", ".join(crm))
            )

    return hallazgos


def main() -> int:
    try:
        hallazgos = revisar()
    except subprocess.CalledProcessError as exc:
        print("sin_pii_versionada: no pude leer el indice de git: %s" % exc)
        return 1

    if not hallazgos:
        print("sin_pii_versionada: OK, el indice no trae PII.")
        return 0

    print("")
    print("=" * 74)
    print("COMMIT BLOQUEADO -- hay datos personales en el indice de git")
    print("=" * 74)
    for h in hallazgos:
        print("  * %s" % h)
    print("")
    print("Este repo ya filtro los datos de contacto de ~33.000 personas por")
    print("estar publico. Los datos van en ../ml_prospector_datos_privados/,")
    print("nunca en el repo.")
    print("")
    print("Si es un falso positivo, no le busques la vuelta con `git add -f`:")
    print("corrige la lista en scripts/verificacion/sin_pii_versionada.py y")
    print("deja constancia de por que ese archivo es seguro.")
    print("")
    return 1


if __name__ == "__main__":
    sys.exit(main())
