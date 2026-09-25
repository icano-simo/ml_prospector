"""¿Existen las rutas de transacciones COLGADAS DEL AGENTE?

En la fase 1 conclui que la pestaña Transactions no se podia reconstruir. Esa
conclusion se apoyo en dos pruebas: `/v1/sales` filtrado (el agente solo
aparece como nombre en busqueda difusa, con los ids en null) y `/v1/related`
(404). **Nunca probe `/v1/agents/{id}/sales`**, que es el mismo patron que si
funciona para los breakdowns -- y la guia del MCP lista agentSales,
agentProperties y agentRelated como herramientas propias del agente.

Si responden, la conclusion estaba mal y hay que decirlo.

Tambien se prueba el mix de tipo de prestamo, que es la otra pregunta:
  · un breakdown por loanType colgado del agente, si existe;
  · y el filtro `footprint.product`, que segun el esquema acepta
    `{mix:'loanType', key:'fha'}`.

Los 404 y 400 no cuestan. Lo que responda se mide contra el ledger.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, saldo  # noqa: E402

ANA = "mma_d776087e62127785"


def medir(etiqueta, ruta, cuerpo=None, metodo=None):
    antes = saldo()
    d = llamar(ruta, cuerpo, etiqueta=etiqueta, metodo=metodo, silencioso=True)
    despues = saldo()
    costo = "?" if None in (antes, despues) else "%.0f" % (antes - despues)
    ok = "200" if d is not None else "falló"
    print("%-22s %-46s %-6s costo %s" % (etiqueta, ruta[:46], ok, costo))
    return d


print("── 1 · las ventas del agente ──")
d = medir("agent_sales", "/v1/agents/%s/sales" % ANA,
          {"period": "last12Months", "pagination": {"size": 3}})
if d:
    filas = d.get("data") or []
    print("      total=%s · filas=%d" % (d.get("total"), len(filas)))
    if filas:
        print("      campos (%d): %s"
              % (len(filas[0]), ", ".join(sorted(filas[0]))))
        for f in filas[:2]:
            print("      %s" % {k: f[k] for k in list(sorted(f))[:10]})

print("")
print("── 2 · los prestamos vinculados ──")
for ruta, cuerpo, met in (
        ("/v1/agents/%s/related?to=loans&limit=5" % ANA, None, "GET"),
        ("/v1/agents/%s/related" % ANA, {"to": "loans", "limit": 5}, None)):
    d = medir("agent_related", ruta, cuerpo, met)
    if d:
        print("      %s" % str(d)[:400])
        break

print("")
print("── 3 · las propiedades del agente ──")
d = medir("agent_properties", "/v1/agents/%s/properties" % ANA,
          {"period": "last12Months", "pagination": {"size": 2}})
if d:
    filas = d.get("data") or []
    print("      total=%s · filas=%d" % (d.get("total"), len(filas)))
    if filas:
        print("      campos: %s" % ", ".join(sorted(filas[0])))

print("")
print("── 4 · un breakdown por tipo de prestamo ──")
for dim in ("loantypes", "loan-types", "loanTypes", "products"):
    d = medir("bd_%s" % dim, "/v1/agents/%s/breakdowns/%s" % (ANA, dim), {})
    if d:
        print("      %s" % str(d)[:300])
        break

print("")
print("── 5 · el filtro footprint.product (mix de loanType) ──")
d = medir("footprint_fha", "/v1/agents",
          {"flatFilters": {"id": ANA},
           "footprint": {"dimension": "lender",
                         "product": {"mix": "loanType", "key": "fha"}},
           "period": "last12Months", "pagination": {"size": 1}})
if d is not None:
    print("      total=%s (1 = hace FHA · 0 = no)" % d.get("total"))

print("")
print("saldo: %s" % saldo())
