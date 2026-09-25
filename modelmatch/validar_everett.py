"""¿Se le escapo alguien al footprint de Everett? Cero creditos.

De 38 realtors tenemos la tabla CRUDA de lenders, con los nombres tal cual los
escribe la fuente. Eso es un patron: si alguno tiene un lender que dice
Everett o Supreme y el footprint NO lo marco, el footprint tiene un agujero y
la exclusion no sirve.

Es la unica prueba real que se puede hacer sin gastar: comparar dos caminos
distintos al mismo hecho.
"""
import glob
import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
EVERETT = os.path.join(RAIZ, "data", "trabajo", "everett.json")

marcados = {c["mm_id"] for c in json.load(open(EVERETT, encoding="utf-8"))}
print("marcados por el footprint: %d" % len(marcados))

#: Lo que, dicho en un nombre crudo de lender, huele a la casa.
HUELE = re.compile(r"everett|evertt|supreme", re.IGNORECASE)

con_tabla = escapados = 0
for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
    f = json.load(open(a, encoding="utf-8"))
    tabla = f.get("mm_lenders")
    if not tabla:
        continue
    con_tabla += 1
    sospechosos = [x for x in tabla if HUELE.search(str(x.get("nombre") or ""))]
    if not sospechosos:
        continue
    esta = f.get("mm_id") in marcados
    print("")
    print("%-26s footprint=%s" % ((f.get("nombre") or "")[:26],
                                  "SI" if esta else "NO  <<< SE ESCAPO"))
    for x in sospechosos:
        print("      %-44s %s u · %.1f%% de sus unidades"
              % (str(x.get("nombre"))[:44], x.get("unidades"),
                 (x.get("pct_unidades") or 0) * 100))
    if not esta:
        escapados += 1

print("")
print("realtors con tabla de lenders: %d" % con_tabla)
print("con un lender que suena a la casa y el footprint NO marco: %d" % escapados)
if escapados:
    print("   => la lista de ids del footprint tiene un agujero")
else:
    print("   => en esta muestra, el footprint y los nombres crudos coinciden")
