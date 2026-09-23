"""Genera motor/ganchos.py desde el corpus, literal.

Las fichas viven en dos hojas del libro -- `1 · Dolores` (100) y
`4 · Nicho latino v2` (22)-- y la columna es `Gancho conversacional`.

Se GENERA y no se transcribe por lo mismo que el catalogo de qualifiers: el
gancho es la frase con la que el BD abre la conversacion, y una palabra cambiada
al copiar es una frase que ya no es la calibrada. Y se versiona para que Vercel
no dependa del xlsx.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd  # noqa: E402

LIBRO = os.path.join(RAIZ, "Data_inputIA", "MATRIZ_PACS-H_v1.xlsx")
DESTINO = os.path.join(RAIZ, "motor", "ganchos.py")
HOJAS = ("1 · Dolores", "4 · Nicho latino v2")

CABECERA = '''"""Los ganchos conversacionales del corpus, literales.

GENERADO por `scripts/generar_ganchos.py` desde las hojas `1 · Dolores` y
`4 · Nicho latino v2` del libro, columna `Gancho conversacional`. **No se
edita a mano.**

El gancho es la frase con la que el BD abre la conversacion. Una palabra
cambiada al copiar es una frase que ya no es la calibrada, y por eso no se
transcribe.

El enrutado
-----------
`MAPA` va de qualifier a ficha. Es una DECISION, no una derivacion: la matriz
no liga las dos cosas, y este mapa es el que venia del prototipo.

`P-Q01` tiene dos variantes segun la señal que lo activo -- ITIN o cuenta
propia-- porque el mismo dolor se abre distinto en cada caso.

Lo derivado va MARCADO
----------------------
`J-Q05` y `J-Q06` no tienen ficha con gancho propio. Su gancho es derivado y
`gancho_de()` lo devuelve con `derivado=True`, para que la pantalla no lo
presente como si viniera del corpus. Un gancho inventado que parece calibrado
es peor que uno que se declara inventado.
"""
from __future__ import annotations

from dataclasses import dataclass

#: ficha -> su gancho literal y de que hoja salio.
CORPUS: dict[str, dict] = {
'''

PIE = '''}

#: qualifier -> ficha. La DECISION de enrutado, del prototipo.
MAPA: dict[str, str] = {
    "P-Q01": "P-082",
    "P-Q06": "P-074",
    "P-Q07": "P-023",
    "P-Q09": "P-062",
    "P-Q10": "P-091",
    "P-Q11": "P-095",
    "P-Q12": "P-013",
    "P-Q13": "P-N10",
    "P-Q14": "P-N06",
    "P-Q17": "P-083",
    "P-Q19": "P-089",
    "P-Q20": "P-086",
    "P-Q21": "P-097",
}

#: `P-Q01` se abre distinto segun que señal lo activo. El mismo dolor -- el
#: lender rechaza el caso de nicho-- no se conversa igual con quien declara
#: ITIN que con quien declara cuenta propia.
VARIANTES: dict[str, list[tuple[str, str]]] = {
    "P-Q01": [("ev2_itin", "P-N01"), ("ev2_self_employed", "P-081")],
}

#: Los que NO tienen ficha con gancho propio. Su texto es derivado y se dice.
DERIVADOS: dict[str, str] = {
    "J-Q05": "¿Qué parte del proceso te toca explicar tú, que debería explicar "
             "el lender?",
    "J-Q06": "¿Cuántas veces al mes te enteras del avance de un préstamo por "
             "el cliente y no por el originador?",
}

#: `J-Q01` es compuerta: no se conversa.
NO_SE_CONVERSA = ("J-Q01",)


@dataclass
class Gancho:
    texto: str
    ficha: str | None
    fuente: str
    derivado: bool = False


def gancho_de(qualifier: str, señales: dict | None = None) -> Gancho | None:
    """El gancho de un qualifier, con su procedencia declarada.

    Devuelve None cuando el qualifier no se conversa (las compuertas) o cuando
    no hay ni ficha ni derivado -- que es un dato, no un error: significa que
    el enrutado no lo cubre y la pantalla tiene que poder decirlo.
    """
    if qualifier in NO_SE_CONVERSA:
        return None

    ficha = MAPA.get(qualifier)
    for campo, alterna in VARIANTES.get(qualifier, []):
        if (señales or {}).get(campo):
            ficha = alterna
            break

    if ficha and ficha in CORPUS:
        c = CORPUS[ficha]
        return Gancho(texto=c["gancho"], ficha=ficha,
                      fuente="ficha %s del corpus · %s" % (ficha, c["hoja"]),
                      derivado=False)

    if qualifier in DERIVADOS:
        return Gancho(
            texto=DERIVADOS[qualifier], ficha=None,
            fuente="DERIVADO: %s no tiene ficha con gancho propio en el corpus"
                   % qualifier,
            derivado=True)
    return None
'''


def lit(v) -> str:
    s = str(v or "").strip()
    return repr(s)


filas = {}
for hoja in HOJAS:
    df = pd.read_excel(LIBRO, sheet_name=hoja)
    col_id, col_tit = df.columns[0], "Título"
    col_gan = next(c for c in df.columns if "ancho" in c)
    for _, r in df.iterrows():
        fid = str(r[col_id]).strip()
        gan = str(r[col_gan] or "").strip()
        if not fid or fid.lower() == "nan" or not gan or gan.lower() == "nan":
            continue
        filas[fid] = {"gancho": gan.strip('"“”'),
                      "titulo": str(r.get(col_tit) or "").strip(),
                      "hoja": hoja}

with open(DESTINO, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(CABECERA)
    for fid in sorted(filas):
        d = filas[fid]
        fh.write("    %r: {\n" % fid)
        fh.write("        'gancho': %s,\n" % lit(d["gancho"]))
        fh.write("        'titulo': %s,\n" % lit(d["titulo"]))
        fh.write("        'hoja': %s,\n" % lit(d["hoja"]))
        fh.write("    },\n")
    fh.write(PIE)

print("escrito %s con %d fichas" % (DESTINO, len(filas)))

from motor.ganchos import CORPUS, DERIVADOS, MAPA, gancho_de  # noqa: E402

print("corpus: %d · mapa: %d · derivados: %d"
      % (len(CORPUS), len(MAPA), len(DERIVADOS)))
faltan = sorted(f for f in MAPA.values() if f not in CORPUS)
print("fichas del mapa que NO estan en el corpus: %s" % (faltan or "ninguna"))

g = gancho_de("P-Q14")
print("")
print("P-Q14 -> %s" % g.ficha)
print("   %s" % g.texto)
g1 = gancho_de("P-Q01")
g2 = gancho_de("P-Q01", {"ev2_itin": True})
g3 = gancho_de("P-Q01", {"ev2_self_employed": True})
print("")
print("P-Q01 sin señal      -> %s" % g1.ficha)
print("P-Q01 con ITIN       -> %s" % g2.ficha)
print("P-Q01 cuenta propia  -> %s" % g3.ficha)
print("")
print("J-Q05 -> derivado=%s · %s" % (gancho_de("J-Q05").derivado,
                                     gancho_de("J-Q05").texto[:60]))
print("J-Q01 (compuerta) -> %r" % gancho_de("J-Q01"))
