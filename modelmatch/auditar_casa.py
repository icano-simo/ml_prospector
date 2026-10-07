"""¿Los ids dudosos de «la casa» cambian a alguien? Cuesta 0 creditos.

De los nueve ids con los que excluimos, seis devolvieron un nombre que dice
Everett, uno tiene el nombre ambiguo --«Supreme Financial Lending», con
«evertt» solo en el id-- y dos nunca aparecieron en ninguna respuesta: salieron
de una guia.

El riesgo va en la direccion cara: si uno de los tres NO es Everett Financial,
estamos marcando como «ya trabaja con la casa» a un realtor que no lo hace, y
eso lo saca de la cola de contacto sin motivo.

La pregunta se contesta sin gastar: se vuelve a preguntar por los marcados,
esta vez con los SEIS confirmados. Los que sigan dando 1 estan sostenidos por
evidencia; los que caigan dependian de un id dudoso.
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

#: Los seis cuyo nombre, en una respuesta real, dice «Everett».
CONFIRMADOS = [
    "everett_financial",
    "everett_financial_texas",
    "everett_financial_incdba_lending_supreme",
    "dba_everett_financial_financial_supr",
    "dba_everett_financial_lending_spureme",
    "dba_everett_finance_lending_supreme",
]
#: Los tres que sostienen una exclusion sin que lo hayamos comprobado.
DUDOSOS = [
    "dba_evertt_financial_lending_supreme",   # nombre: «Supreme Financial Lending»
    "dba_everett_financial_superme",          # nunca visto
    "dba_dupreme_everett_financial_lending",  # nunca visto
]


def marcado(mm: str, ids: list[str], etiqueta: str) -> bool | None:
    d = llamar("/v1/agents/count",
               {"flatFilters": {"id": mm},
                "footprint": {"lender": ids},
                "period": "allTime"},
               etiqueta=etiqueta, silencioso=True)
    if not isinstance(d, dict) or not isinstance(d.get("total"), (int, float)):
        return None
    return d["total"] >= 1


def main() -> None:
    marcados = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            f = json.load(fh)
        if f.get("trabaja_con_la_casa") == "SÍ" and f.get("mm_id"):
            marcados.append((f["mm_id"], f.get("nombre")))

    s0 = saldo()
    print("marcados hoy como «ya financia con la casa»: %d" % len(marcados))
    print("saldo: %s · esto NO debe gastar nada" % s0)
    print("")

    siguen = caen = fallo = 0
    los_que_caen = []
    for i, (mm, nombre) in enumerate(marcados, 1):
        r = marcado(mm, CONFIRMADOS, "casa6_%s" % mm)
        if r is None:
            fallo += 1
        elif r:
            siguen += 1
        else:
            caen += 1
            los_que_caen.append(nombre)
        if i % 25 == 0 or i == len(marcados):
            print("   %3d/%d · sostenidos %d · dependen de un id dudoso %d"
                  % (i, len(marcados), siguen, caen))

    s1 = saldo()
    print("")
    print("sostenidos por los SEIS confirmados : %d" % siguen)
    print("dependen de un id DUDOSO            : %d" % caen)
    if fallo:
        print("llamadas que fallaron               : %d" % fallo)
    for n in los_que_caen[:15]:
        print("   depende de un id dudoso: %s" % n)
    print("")
    print("gasto: %s" % ("?" if None in (s0, s1) else round(s0 - s1, 2)))
    if caen == 0:
        print("=> los tres ids dudosos NO cambian a nadie: la exclusion se "
              "sostiene solo con lo comprobado.")
    else:
        print("=> %d realtors estan excluidos por un id que no comprobamos. "
              "Hay que resolverlo antes de usarlos." % caen)


if __name__ == "__main__":
    main()
