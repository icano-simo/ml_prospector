"""¿Quien produce FHA, quien convencional, quien VA? Y cuanto.

Ni la ficha ni los breakdowns de agente traen el mix de tipo de prestamo: no
existe `/v1/agents/{id}/breakdowns/loanTypes`. Pero `listAgents` acepta
`footprint.product`, que filtra por el negocio del agente DENTRO de un tipo:

    {"footprint": {"dimension": "lender",
                   "product": {"mix": "loanType", "key": "fha"}}}

La respuesta es la fila normal del agente, asi que dice QUIEN pero no CUANTO.
El «cuanto» sale por bandas: la misma consulta con `shareOfUnits: {gte: N}`
solo devuelve a los que pasan ese umbral, y cruzando dos umbrales queda el
tramo. Cuesta 1 por fila devuelta, o sea que un umbral alto cuesta poco.

Es la via barata. La cara seria agentProperties -> mmPropertyId -> /v1/loans
filtrado por propertyId, que da el tipo de CADA prestamo pero cuesta 1 por
propiedad mas 1 por prestamo.
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
SALIDA = os.path.join(RAIZ, "data", "trabajo", "mix_prestamos.json")
LOTE = 100
PERIODO = "last24Months"

#: (etiqueta, tipo, umbral de % de unidades). El umbral 0 = «hace algo de
#: esto»; los altos dicen cuanto pesa. Se piden de mayor a menor porque los
#: altos devuelven menos filas y cuestan menos: si el presupuesto se corta,
#: se corta por la consulta mas cara y no por la mas informativa.
CONSULTAS = [
    ("fha_50", "fha", 50),
    ("fha_25", "fha", 25),
    ("fha", "fha", 0),
    ("va", "va", 0),
    ("convencional", "conventional", 0),
]


def main() -> None:
    ids = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        f = json.load(open(a, encoding="utf-8"))
        if f.get("mm_id"):
            ids.append(f["mm_id"])
    print("agentes: %d · periodo %s" % (len(ids), PERIODO))

    s0 = saldo()
    print("saldo: %s" % s0)
    print("")

    resultado: dict[str, list[str]] = {}
    for etiqueta, tipo, umbral in CONSULTAS:
        antes = saldo()
        encontrados: list[str] = []
        producto: dict = {"mix": "loanType", "key": tipo}
        if umbral:
            producto["shareOfUnits"] = {"gte": umbral}
        for i in range(0, len(ids), LOTE):
            d = llamar("/v1/agents",
                       {"flatFilters": {"id": ids[i:i + LOTE]},
                        "footprint": {"dimension": "lender",
                                      "product": producto},
                        "period": PERIODO,
                        "pagination": {"size": 100}},
                       etiqueta="mix_%s_%d" % (etiqueta, i // LOTE),
                       silencioso=True)
            encontrados += [f.get("id") for f in ((d or {}).get("data") or [])]
        despues = saldo()
        resultado[etiqueta] = encontrados
        print("%-14s %-13s umbral %3d%%   %3d de %d   costo %s"
              % (etiqueta, tipo, umbral, len(encontrados), len(ids),
                 "?" if None in (antes, despues) else round(antes - despues)))

    with open(SALIDA, "w", encoding="utf-8") as fh:
        json.dump({"periodo": PERIODO, "resultado": resultado}, fh, indent=1)

    s1 = saldo()
    print("")
    print("costo total: %s creditos"
          % ("?" if None in (s0, s1) else round(s0 - s1)))
    print("guardado en %s" % SALIDA)


if __name__ == "__main__":
    main()
