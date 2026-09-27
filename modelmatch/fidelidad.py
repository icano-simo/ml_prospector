"""¿Estan fidelizados con un loan officer? Cero creditos.

Hay dos preguntas distintas y solo una esta contestada para todos:

  1 · CUANTOS LOs distintos financiaron sus operaciones. Viene en la ficha
      (`totalOriginatorsWorkedWith`), o sea que la tenemos para los 273 sin
      pagar nada. Uno solo = cautivo.

  2 · CUANTO se concentra en el primero. Un agente con diez LOs y el 80% del
      negocio por uno tambien esta fidelizado, y el conteo no lo ve. Eso
      necesita el desglose, que cuesta 1 credito por LO.

De 38 realtors SI tenemos el desglose. Con eso se puede medir si el conteo
--que es gratis-- predice la concentracion --que es cara--. Si la predice, no
hace falta comprar el desglose de los demas.
"""
from __future__ import annotations

import glob
import json
import os
import statistics
import sys
from collections import Counter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

fs = [json.load(open(a, encoding="utf-8"))
      for a in sorted(glob.glob(os.path.join(DIR, "*.json")))]
con = [f for f in fs if f.get("encontrado")]

# ── 1 · lo que sabemos de TODOS, gratis ─────────────────────────────────────
print("── cuantos loan officers distintos (los 273, ya capturado) ──")
tramos = Counter()
for f in con:
    n = f.get("mm_originadores_n")
    if n is None:
        tramos["sin dato"] += 1
    elif n <= 1:
        tramos["1 solo LO · CAUTIVO"] += 1
    elif n <= 3:
        tramos["2 a 3"] += 1
    elif n <= 6:
        tramos["4 a 6"] += 1
    elif n <= 12:
        tramos["7 a 12"] += 1
    else:
        tramos["13 o mas · reparte mucho"] += 1
for k in ("1 solo LO · CAUTIVO", "2 a 3", "4 a 6", "7 a 12",
          "13 o mas · reparte mucho", "sin dato"):
    if tramos[k]:
        print("   %-26s %3d" % (k, tramos[k]))

ns = [f["mm_originadores_n"] for f in con
      if isinstance(f.get("mm_originadores_n"), int)]
print("   mediana %.0f · media %.1f · max %d"
      % (statistics.median(ns), statistics.mean(ns), max(ns)))

# ── 2 · la concentracion real, en los 38 que la tienen ──────────────────────
print("")
print("── concentracion real, en los que SI tienen el desglose ──")
# El `pct_unidades` que devuelve la API NO sirve para esto: Ana Pena da 167%,
# o sea que su denominador no son las operaciones del agente. Tiene sentido --
# la guia avisa que las unidades hipotecarias se miden aparte de las de venta
# y pueden ser MAS-- pero convierte el campo en inutilizable como «parte de
# su negocio». La concentracion se calcula con el denominador correcto: las
# unidades del LO principal sobre la suma de las de TODOS sus LOs.
filas = []
for f in con:
    t = f.get("mm_originators")
    if not t:
        continue
    total = sum(x.get("unidades") or 0 for x in t)
    if not total:
        continue
    top = max(t, key=lambda x: x.get("unidades") or 0)
    filas.append((f.get("nombre"), f.get("mm_originadores_n"),
                  100.0 * (top.get("unidades") or 0) / total,
                  top.get("nombre")))

if not filas:
    print("   ninguno (el tope de 5 creditos no dejo pedirlo)")
else:
    filas.sort(key=lambda r: -r[2])
    print("   %-24s %-4s %-7s %s" % ("realtor", "LOs", "top %", "su LO principal"))
    for nombre, n, pct, lo in filas:
        print("   %-24s %-4s %5.0f%%  %s" % ((nombre or "")[:24], n, pct,
                                             (lo or "")[:34]))
    # ¿El conteo predice la concentracion?
    print("")
    pocos = [p for _, n, p, _ in filas if (n or 99) <= 3]
    muchos = [p for _, n, p, _ in filas if (n or 0) > 3]
    if pocos:
        print("   con 1-3 LOs: concentracion media %.0f%% (n=%d)"
              % (statistics.mean(pocos), len(pocos)))
    if muchos:
        print("   con 4+ LOs : concentracion media %.0f%% (n=%d)"
              % (statistics.mean(muchos), len(muchos)))

# ── 3 · lo que costaria saberlo de todos ────────────────────────────────────
falta = [f for f in con if f.get("mm_originators") is None]
coste = sum(f.get("mm_originadores_n") or 0 for f in falta)
print("")
print("comprar el desglose de los %d que faltan: %d creditos" % (len(falta), coste))
cautivos = [f for f in falta if (f.get("mm_originadores_n") or 99) <= 3]
print("   solo los de 1-3 LOs (%d realtors): %d creditos"
      % (len(cautivos), sum(f.get("mm_originadores_n") or 0 for f in cautivos)))
