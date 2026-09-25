"""Donde viven el saldo y la busqueda instantanea. Deberia costar 0.

El MCP expone `getMeCredits` e `instantSearch`, y la documentacion dice que
las herramientas del MCP se generan desde CADA endpoint de la API. O sea que
las dos existen por REST; lo unico que no sabemos es la ruta.

Los errores no cuestan, y un 400 devuelve la lista entera de claves aceptadas:
es la forma mas barata de documentacion que tiene esta API.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, resumen  # noqa: E402

print("══ 1 · el saldo ══")
for ruta in ("/v1/me/credits", "/v1/credits", "/v1/me/usage", "/v1/usage",
             "/v1/me/balance"):
    d = llamar(ruta, etiqueta="saldo_%s" % ruta.replace("/", "_"))
    if isinstance(d, dict):
        print("      claves: %s" % ", ".join(sorted(d))[:200])
        for k in sorted(d):
            if not isinstance(d[k], (dict, list)):
                print("         %-28s %r" % (k, d[k]))
            else:
                print("         %-28s %s" % (k, str(d[k])[:120]))
        break

print("")
print("══ 2 · instantSearch ══")
for ruta in ("/v1/instant-search", "/v1/search", "/v1/instantsearch"):
    # Primero GET con query, que es lo natural para un typeahead.
    d = llamar(ruta + "?q=ana+osorio", etiqueta="is_get%s" % ruta.replace("/", "_"))
    if d is not None:
        print("      GET funciona · %s" % str(d)[:300])
        break
    d = llamar(ruta, {"query": "ana osorio"},
               etiqueta="is_post%s" % ruta.replace("/", "_"))
    if d is not None:
        print("      POST funciona · %s" % str(d)[:300])
        break

resumen()
