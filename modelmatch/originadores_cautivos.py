"""El desglose de LOs de los que dependen de pocos. Barato y dirigido.

Comprar el desglose de originadores de los 257 que faltan cuesta 3.044
creditos. Pero el desglose solo dice algo NUEVO donde hay concentracion: si
alguien reparte entre catorce LOs, saber los catorce nombres no cambia
ninguna decision, y cuesta catorce creditos.

Donde si cambia la decision es en los que dependen de uno o dos: ahi el
desglose da el NOMBRE del LO a desplazar, que es la unica accion concreta que
sale de todo esto. Y cuesta 1 credito por LO, o sea casi nada.

Se compra solo ese grupo, y el tope por realtor sigue siendo 5.
"""
from __future__ import annotations

import glob
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, saldo  # noqa: E402

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
MAX_LOS = 3


def main() -> None:
    objetivo = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        f = json.load(open(a, encoding="utf-8"))
        n = f.get("mm_originadores_n")
        if (f.get("mm_id") and f.get("mm_originators") is None
                and isinstance(n, int) and 0 < n <= MAX_LOS):
            objetivo.append((a, f))

    coste = sum(f["mm_originadores_n"] for _, f in objetivo)
    print("realtors con 1-%d LOs y sin desglose: %d · costaran %d creditos"
          % (MAX_LOS, len(objetivo), coste))
    s0 = saldo()
    print("saldo: %s" % s0)
    print("")

    for ruta, f in objetivo:
        d = llamar("/v1/agents/%s/breakdowns/originators" % f["mm_id"], {},
                   etiqueta="orig_%s" % f["mm_id"], silencioso=True)
        filas = (d or {}).get("data") or []
        f["mm_originators"] = [
            {"nombre": x.get("label"), "unidades": x.get("units"),
             "volumen": x.get("volume"), "pct_unidades": x.get("pctUnits"),
             "pct_volumen": x.get("pctVolume")} for x in filas]
        f["mm_originators_motivo"] = None
        f["creditos_gastados"] = (f.get("creditos_gastados") or 0) + len(filas)
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(f, fh, ensure_ascii=False, indent=1)
        total = sum(x.get("unidades") or 0 for x in f["mm_originators"]) or 1
        top = max(f["mm_originators"], key=lambda x: x.get("unidades") or 0,
                  default={})
        print("   %-26s %d LO(s) · principal: %-28s %.0f%% de sus prestamos"
              % ((f.get("nombre") or "")[:26], len(filas),
                 str(top.get("nombre"))[:28],
                 100.0 * (top.get("unidades") or 0) / total))

    s1 = saldo()
    print("")
    print("costo: %s" % ("?" if None in (s0, s1) else round(s0 - s1)))


if __name__ == "__main__":
    main()
