"""Cuanto cuesta cada llamada, leido del ledger antes y despues.

El brief prohibe estimar el gasto, y la skill dice que el costo de
list/breakdowns/analytics no esta documentado: hay que medirlo. Se mide una
sola vez, con Ana, y de ahi sale el presupuesto de las 298.

Tambien fija la FORMA real de cada respuesta, que es lo otro que los esquemas
no dicen: «nunca afirmar un dato de Model Match que no venga de una respuesta».
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import gastado_en_el_ciclo, llamar, saldo  # noqa: E402

ANA = "mma_d776087e62127785"


def medir(etiqueta, ruta, cuerpo=None, metodo=None):
    """Una llamada con el saldo leido antes y despues.

    Se mide contra `balance.total` y NO contra `usage.spent`: el spent va con
    retraso --siete llamadas no lo movieron ni una decima-- asi que el unico
    que contesta «cuanto costo esto» en el acto es el saldo.
    """
    antes = saldo()
    d = llamar(ruta, cuerpo, etiqueta=etiqueta, metodo=metodo, silencioso=True)
    despues = saldo()
    costo = None if (antes is None or despues is None) else round(antes - despues, 3)
    print("%-26s %-44s costo %s" % (etiqueta, ruta[:44],
                                    "?" if costo is None else "%.2f" % costo))
    return d, costo


print("saldo: %s creditos · gastado en el ciclo: %s"
      % (saldo(), gastado_en_el_ciclo()))
print("")
print("%-26s %-44s %s" % ("etiqueta", "ruta", "costo"))
print("-" * 86)

d, _ = medir("instant_search", "/v1/instant-search",
             {"query": "anaosorio.yourrealtor@gmail.com"})
if isinstance(d, dict):
    res = d.get("results") or {}
    print("      secciones: %s" % ", ".join("%s=%d" % (k, len(v or []))
                                            for k, v in res.items()))
    for a in (res.get("agents") or [])[:3]:
        print("      agente: %s" % {k: a[k] for k in list(a)[:12]})

medir("agents_lista", "/v1/agents",
      {"flatFilters": {"id": ANA}, "period": "last12Months",
       "pagination": {"size": 1}})
medir("agent_detalle", "/v1/agents/%s" % ANA)
medir("agent_lenders", "/v1/agents/%s/breakdowns/lenders" % ANA, {})
medir("agent_originators", "/v1/agents/%s/breakdowns/originators" % ANA, {})
medir("agent_companies", "/v1/agents/%s/breakdowns/companies" % ANA, {})
medir("agent_counties", "/v1/agents/%s/breakdowns/counties" % ANA, {})

print("")
print("saldo: %s creditos · gastado en el ciclo: %s"
      % (saldo(), gastado_en_el_ciclo()))
