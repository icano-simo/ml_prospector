"""¿La lista cobra por LLAMADA o por FILA? Decide el presupuesto entero.

Los breakdowns cobran 1 por fila (medido: 8 lenders = 8, 10 originators = 10).
Si `/v1/agents` hace lo mismo, traer 298 agentes cuesta 298 sin importar como
se agrupen. Si cobra por llamada, cuesta 3.

Se mide pidiendo CINCO agentes en una sola llamada: si el saldo baja 1, es por
llamada; si baja 5, es por fila.

Y de paso compara los campos de la fila de lista contra los del detalle, que
es lo que dice si hace falta pagar el detalle aparte.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, saldo  # noqa: E402

ANA = "mma_d776087e62127785"

print("saldo antes: %s" % saldo())

antes = saldo()
d = llamar("/v1/agents",
           {"flatFilters": {"state": "IL"}, "period": "last12Months",
            "pagination": {"size": 5}},
           etiqueta="lote_cinco", silencioso=True)
despues = saldo()
filas = (d or {}).get("data") or []
print("")
print("CINCO en una llamada · filas devueltas: %d · costo: %.2f"
      % (len(filas), (antes - despues) if None not in (antes, despues) else -1))
print("   %s" % ("cobra por FILA" if (antes - despues) >= len(filas)
                 else "cobra por LLAMADA"))

if filas:
    fila = filas[0]
    print("")
    print("── campos de la FILA DE LISTA (%d) ──" % len(fila))
    for k in sorted(fila):
        print("   %-30s %r" % (k, str(fila[k])[:52]))

# El detalle de Ana ya esta guardado de la medicion anterior: se compara
# contra el crudo, sin volver a pagarlo.
import glob  # noqa: E402
import json  # noqa: E402

ar = sorted(glob.glob(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "raw", "mm_agent_detalle_*.json")))
if ar and filas:
    with open(ar[-1], encoding="utf-8") as fh:
        det = json.load(fh).get("data") or {}
    solo_detalle = sorted(set(det) - set(filas[0]))
    solo_lista = sorted(set(filas[0]) - set(det))
    print("")
    print("── el DETALLE trae y la lista no: %s" % (solo_detalle or "nada"))
    print("── la LISTA trae y el detalle no: %s" % (solo_lista or "nada"))

print("")
print("saldo despues: %s" % saldo())
