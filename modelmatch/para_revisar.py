"""Los realtors que Model Match no resolvio, listos para decidir a mano.

CERO llamadas y CERO creditos: solo lee los registros ya guardados.

Por que existe aparte de la hoja «Revisar» del Excel grande: esa hoja vive
dentro de un archivo de 130 columnas y 900 filas, y el trabajo de desambiguar
es otro --se mira un realtor, se miran sus candidatos, se elige uno--. Un
archivo de dos hojas y una columna para escribir es lo que hace que ese
trabajo se pueda hacer sin perderse.

La columna que hay que llenar es `ID Model Match elegido`. Lo que se escriba
ahi lo lee `aplicar_revision.py`, que compra la ficha del elegido --1 credito,
el mismo tope de siempre-- y completa la fila.

Uso:
    python modelmatch/para_revisar.py
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sys
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
SALIDA = os.path.join(RAIZ, "data", "salida")
ARCHIVO = os.path.join(SALIDA, "revisar_model_match.xlsx")


def normal(s) -> str:
    """Minusculas, sin tildes, sin puntuacion, espacios colapsados."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s.lower())).strip()


def parecido(f: dict, c: dict) -> str:
    """En que se parece ESTE candidato a NUESTRO realtor.

    Es lo que el paso 1 miro para descartarlo, dicho en una celda. Sin esto
    hay que comparar siete candidatos a ojo, campo por campo.
    """
    marcas = []
    if normal(c.get("nombre")) == normal(f.get("nombre")):
        marcas.append("mismo nombre")
    elif normal(c.get("nombre")).split()[:1] == normal(
            f.get("nombre")).split()[:1]:
        marcas.append("mismo nombre de pila")
    if (c.get("estado") or "").upper() == (f.get("estado_mmi") or "").upper():
        marcas.append("mismo estado")
    nuestros = {x.strip().lower() for x in (f.get("emails_mmi") or []) if x}
    suyos = {x.strip().lower()
             for x in re.split(r"[;,]", str(c.get("email") or "")) if x.strip()}
    if nuestros & suyos:
        marcas.append("⚠ CORREO COINCIDE")
    if normal(c.get("office"))[:12] and \
            normal(c.get("office"))[:12] == normal(f.get("brokerage_mmi"))[:12]:
        marcas.append("mismo brokerage")
    return " · ".join(marcas) if marcas else "nada en comun"


def cargar() -> list[dict]:
    fuera = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            f = json.load(fh)
        if not f.get("mm_id") and (f.get("candidatos") or []):
            fuera.append(f)
    return fuera


def escribir(ws, titulos, anchos, filas):
    ws.append(titulos)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(vertical="top", wrap_text=True)
    for f in filas:
        ws.append(f)
    for i, an in enumerate(anchos, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = an
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def main() -> None:
    sin_resolver = cargar()
    print("realtors sin resolver, con candidatos: %d" % len(sin_resolver))
    if not sin_resolver:
        print("no hay nada que revisar")
        return

    wb = Workbook()

    # ── Hoja 1: uno por realtor, con su columna para escribir ─────────────
    ws = wb.active
    ws.title = "Para decidir"
    filas = []
    for f in sin_resolver:
        cands = sorted(f.get("candidatos") or [],
                       key=lambda c: -(c.get("volumen") or 0))
        resumen = "\n".join(
            "%d) %s — %s — %s, %s — vol %s — id %s"
            % (i, c.get("nombre"), c.get("office") or "sin brokerage",
               c.get("ciudad") or "?", c.get("estado") or "?",
               "{:,.0f}".format(c["volumen"]) if c.get("volumen") else "?",
               c.get("id"))
            for i, c in enumerate(cands, 1))
        filas.append([
            "", f.get("nombre"), f.get("handle"),
            " · ".join(f.get("emails_mmi") or []),
            " · ".join(f.get("telefonos_mmi") or []),
            f.get("estado_mmi"), f.get("brokerage_mmi"),
            f.get("unidades_mmi"), len(cands), resumen, f.get("realtor_id")])
    escribir(ws,
             ["ID Model Match elegido", "Realtor", "Instagram",
              "Correos que tenemos", "Teléfonos que tenemos", "Estado",
              "Brokerage (MMI, viejo)", "Unidades/año (MMI)",
              "Nº candidatos", "Los candidatos, de mayor a menor volumen",
              "realtor_id"],
             [26, 26, 20, 34, 24, 8, 30, 12, 11, 96, 36], filas)
    amarillo = PatternFill("solid", fgColor="FFF3CD")
    for fila in ws.iter_rows(min_row=2):
        fila[0].fill = amarillo
        fila[9].alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 26

    # ── Hoja 2: uno por candidato, para escanear y filtrar ────────────────
    ws2 = wb.create_sheet("Candidatos, uno por fila")
    filas2 = []
    for f in sin_resolver:
        for i, c in enumerate(sorted(f.get("candidatos") or [],
                                     key=lambda c: -(c.get("volumen") or 0)),
                              1):
            filas2.append([
                f.get("nombre"), f.get("handle"), i, c.get("nombre"),
                c.get("office"), c.get("ciudad"), c.get("estado"),
                c.get("email"), c.get("volumen"), parecido(f, c),
                c.get("id"), f.get("realtor_id")])
    escribir(ws2,
             ["Realtor nuestro", "Instagram", "#", "Candidato en Model Match",
              "Su brokerage", "Ciudad", "Estado", "Sus correos", "Volumen",
              "En qué se parece", "ID Model Match", "realtor_id"],
             [26, 20, 4, 26, 30, 18, 8, 34, 14, 34, 26, 36], filas2)

    # ── Hoja 3: como se usa ───────────────────────────────────────────────
    ws3 = wb.create_sheet("Cómo se usa")
    notas = [
        ["Qué es esto", ""],
        ["", "Los %d realtors que Model Match NO resolvió solo: la búsqueda "
             "devolvió candidatos, pero ninguno cumplió la regla de "
             "identificación, así que NO se eligió a nadie y NO se gastó "
             "ningún crédito en ellos." % len(sin_resolver)],
        ["", "Se paran acá a propósito. Elegir al candidato equivocado es "
             "peor que no elegir: la fila entera —producción, lenders, "
             "Everett— quedaría atribuida a otra persona, y se vería igual "
             "de confiable que las demás."],
        ["Qué hay que hacer", ""],
        ["", "En la hoja «Para decidir», columna A, escribir el ID Model "
             "Match del candidato correcto. Los IDs están al final de cada "
             "línea de la columna «Los candidatos»."],
        ["", "Si ninguno es la persona, escribir NINGUNO. Eso también es una "
             "respuesta y hace que no se le vuelva a preguntar."],
        ["", "Si hace falta ver los candidatos con más calma, la hoja "
             "«Candidatos, uno por fila» trae uno por renglón y se puede "
             "filtrar y ordenar."],
        ["Por qué quedaron sin resolver", ""],
        ["", "La regla es: se identifica por correo, o por nombre completo "
             "idéntico MÁS el mismo estado. Estos no cumplieron ninguna de "
             "las dos. La columna «En qué se parece» dice, candidato por "
             "candidato, qué coincidía y qué no."],
        ["", "Si alguno dice «⚠ CORREO COINCIDE», avisá: eso debería haberlo "
             "resuelto solo, y significa que hay algo que la regla no está "
             "viendo."],
        ["Qué pasa después", ""],
        ["", "Con la columna A llena, se corre el paso que compra la ficha "
             "del elegido: 1 crédito por realtor, el mismo tope de siempre. "
             "Los marcados NINGUNO no cuestan nada."],
        ["", "Después se les corren los tres pasos gratis —tipo de préstamo, "
             "Everett y producción por año— y entran al archivo grande como "
             "cualquier otro."],
        ["Cuidado con este archivo", ""],
        ["", "Lleva nombres, correos y teléfonos de personas reales. No se "
             "versiona, no se sube a ningún lado y no se comparte fuera del "
             "equipo."],
    ]
    escribir(ws3, ["Concepto", "Qué significa"], [26, 112], notas)
    for fila in ws3.iter_rows(min_row=2, max_col=2):
        fila[1].alignment = Alignment(wrap_text=True, vertical="top")
        if fila[0].value and not fila[1].value:
            fila[0].font = Font(bold=True, size=11)

    os.makedirs(SALIDA, exist_ok=True)
    wb.save(ARCHIVO)
    n_cand = sum(len(f.get("candidatos") or []) for f in sin_resolver)
    print("realtors a decidir : %d" % len(sin_resolver))
    print("candidatos en total: %d  (mediana %d por realtor)"
          % (n_cand, sorted(len(f.get("candidatos") or [])
                            for f in sin_resolver)[len(sin_resolver) // 2]))
    con_correo = sum(
        1 for f in sin_resolver
        for c in (f.get("candidatos") or [])
        if "⚠ CORREO COINCIDE" in parecido(f, c))
    if con_correo:
        print("⚠ %d candidatos tienen un correo que coincide con el nuestro: "
              "eso deberia haberse resuelto solo" % con_correo)
    print("")
    print("generado el %s" % dt.date.today().isoformat())
    print("guardado en %s" % ARCHIVO)


if __name__ == "__main__":
    main()
