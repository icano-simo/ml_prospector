"""¿Los `count` cobran por fila o por llamada? Cambia toda la economia.

Todo lo caro de este trabajo sale de que la API cobra 1 por FILA DEVUELTA.
Pero `countAgents` y `countLoans` no devuelven filas: devuelven un numero. Si
cuestan 1 por llamada --o 0-- entonces:

  · el mix de tipo de prestamo por agente sale contando, no listando;
  · y contar es exactamente lo que necesitamos: «¿cuantas de sus operaciones
    fueron FHA?» es un numero, no una lista.

Si en cambio cobran el total contado, no sirven para nada y hay que saberlo
antes de lanzarlo sobre 273 agentes.
"""
import glob
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, saldo  # noqa: E402

ANA = "mma_d776087e62127785"


def medir(etiqueta, ruta, cuerpo=None, metodo=None):
    antes = saldo()
    d = llamar(ruta, cuerpo, etiqueta=etiqueta, metodo=metodo, silencioso=True)
    despues = saldo()
    costo = "?" if None in (antes, despues) else "%.0f" % (antes - despues)
    print("%-20s %-40s %-6s costo %-4s %s"
          % (etiqueta, ruta[:40], "ok" if d is not None else "falló", costo,
             (str(d)[:70] if d is not None else "")))
    return d


print("── contar agentes (deberia dar un numero grande por poco) ──")
for ruta in ("/v1/agents/count", "/v1/count/agents"):
    d = medir("count_agents", ruta, {"flatFilters": {"state": "IL"},
                                     "period": "last12Months"})
    if d is not None:
        break

print("")
print("── contar prestamos ──")
for ruta in ("/v1/loans/count", "/v1/count/loans"):
    d = medir("count_loans", ruta, {"flatFilters": {"state": "IL",
                                                    "loanType": "fha"},
                                    "period": "last12Months"})
    if d is not None:
        break

print("")
print("── las propiedades de Ana, para cruzarlas con loans ──")
d = medir("props_ana", "/v1/agents/%s/properties" % ANA,
          {"period": "last24Months", "pagination": {"size": 100}})
props = [x.get("mmPropertyId") for x in ((d or {}).get("data") or [])
         if x.get("mmPropertyId")]
print("      propiedades con id: %d" % len(props))

if props:
    print("")
    print("── contar SUS prestamos por tipo (la pregunta real) ──")
    for tipo in ("fha", "conventional", "va"):
        medir("cuenta_%s" % tipo, "/v1/loans/count",
              {"flatFilters": {"propertyId": props[:50], "loanType": tipo},
               "period": "last24Months"})

print("")
print("saldo: %s" % saldo())
