"""¿Que trae un prestamo? Decide si Transactions se puede reconstruir.

`agentRelated{to:loans}` da 48 ids para Ana. Si `getLoan` trae tipo de
prestamo, lender y monto, entonces la pestaña Transactions SI se puede
reconstruir por API y mi conclusion de la fase 1 estaba mal. Si trae solo
identificadores, no.

Una llamada, un prestamo.
"""
import glob
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, saldo  # noqa: E402

# El id sale del crudo ya guardado: no se vuelve a pedir la lista.
ar = sorted(glob.glob(os.path.join(RAIZ, "data", "raw",
                                   "mm_agent_related_*.json")))
ids = [x["id"] for x in json.load(open(ar[-1], encoding="utf-8"))["data"]]
print("prestamos vinculados en el crudo: %d · pruebo el primero" % len(ids))

antes = saldo()
d = llamar("/v1/loans/%s" % ids[0], etiqueta="loan_uno", silencioso=True)
despues = saldo()
print("costo: %s" % ("?" if None in (antes, despues) else antes - despues))

if d:
    a = d.get("data") if isinstance(d.get("data"), dict) else d
    print("")
    print("── campos del prestamo (%d) ──" % len(a))
    for k in sorted(a):
        v = a[k]
        print("   %-30s %s" % (k, str(v)[:64]))
else:
    print("no respondio; pruebo la forma de lista con filtro por id")
    d = llamar("/v1/loans", {"flatFilters": {"id": ids[0]},
                             "pagination": {"size": 1}},
               etiqueta="loan_lista", silencioso=True)
    if d:
        filas = d.get("data") or []
        print("total=%s filas=%d" % (d.get("total"), len(filas)))
        if filas:
            for k in sorted(filas[0]):
                print("   %-30s %s" % (k, str(filas[0][k])[:64]))

print("")
print("saldo: %s" % saldo())
