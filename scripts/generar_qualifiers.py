"""Genera motor/qualifiers.py desde la hoja 8, literal.

Se GENERA y no se escribe a mano porque son 60 fichas con siete campos cada una:
transcribirlas es 420 oportunidades de cambiar una palabra. Y se versiona el
resultado para que Vercel no necesite el xlsx.
"""
import os
import sys

RAIZ = r"C:\Users\icano.CL-390BQ04\ml_prospector"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd  # noqa: E402

LIBRO = os.path.join(RAIZ, "Data_inputIA", "MATRIZ_PACS-H_v1.xlsx")
DESTINO = os.path.join(RAIZ, "motor", "qualifiers.py")

df = pd.read_excel(LIBRO, sheet_name="8 · Qualifiers v2")
CAMPOS = ["familia", "enunciado", "nivel_o_tipo", "categorias_de_senal",
          "senales_de_deteccion", "escala_de_intensidad", "evidencia_minima",
          "municion_PR_GC", "angulo_que_activa", "ruta_de_copy",
          "confianza_tipica"]

CABECERA = '''"""El banco de qualifiers, literal de la matriz.

GENERADO desde `Data_inputIA/MATRIZ_PACS-H_v1.xlsx`, hoja `8 · Qualifiers v2`,
por `scripts/generar_qualifiers.py`. **No se edita a mano.** Son 60 fichas con
once campos cada una: transcribirlas seria 660 oportunidades de cambiar una
palabra, y el enunciado es lo que el BD lee.

Por que vive aca y no se lee del xlsx
-------------------------------------
Vercel no tiene el libro ni pandas. Y un catalogo que se lee de un archivo que
puede no estar es un catalogo que a veces devuelve vacio -- sin fallar.

Que trae cada uno
-----------------
  enunciado             que se supone que le pasa, en palabras
  escala_de_intensidad  que significa cada nivel de 0 a 3
  evidencia_minima      con que se puede acreditar
  municion_PR_GC        con que se le responde
  angulo_que_activa     el angulo de conversacion
"""
from __future__ import annotations

#: qualifier_id -> sus campos, tal como estan en la hoja 8.
CATALOGO: dict[str, dict] = {
'''

PIE = '''}


def ficha(qualifier: str) -> dict:
    """La ficha de un qualifier, o un dict vacio con su razon.

    No levanta: un qualifier sin ficha es un dato -- significa que el banco no
    lo cubre-- y quien llama tiene que poder decirlo en pantalla en vez de
    romperse.
    """
    return CATALOGO.get(qualifier, {})


def enunciado(qualifier: str) -> str | None:
    """Que se supone que le pasa. `P-Q14` solo no le dice nada a nadie."""
    return ficha(qualifier).get("enunciado")
'''


def lit(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "None"
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return "None"
    return repr(s)


with open(DESTINO, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(CABECERA)
    for _, r in df.iterrows():
        qid = str(r["qualifier_id"]).strip()
        if not qid or qid.lower() == "nan":
            continue
        fh.write("    %r: {\n" % qid)
        for c in CAMPOS:
            if c in df.columns:
                fh.write("        %r: %s,\n" % (c, lit(r[c])))
        fh.write("    },\n")
    fh.write(PIE)

print("escrito %s" % DESTINO)

sys.path.insert(0, RAIZ)
from motor.qualifiers import CATALOGO, enunciado  # noqa: E402

print("qualifiers: %d" % len(CATALOGO))
print("P-Q14: %s" % enunciado("P-Q14"))
print("P-Q14 angulo: %s" % CATALOGO["P-Q14"]["angulo_que_activa"][:60])
faltan = [q for q in ("P-Q06", "P-Q01", "P-Q09", "P-Q11", "P-Q14")
          if q not in CATALOGO]
print("de los cinco principales, faltan: %s" % (faltan or "ninguno"))
