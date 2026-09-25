"""Todos los ids de lender que son Everett Financial. Cero creditos.

La exclusion por no-canibalizacion se apoya en una lista de ids. Si a esa
lista le falta una variante, el agente que financio por esa variante NO sale
en el footprint y lo tratamos como prospecto nuevo: le escribimos a alguien
que ya es cliente de la casa. El falso negativo es el error caro, y por eso
la lista se COMPRUEBA en vez de copiarse.

`instant-search` trae una seccion `lenders` y no cuesta nada, asi que se le
pregunta por las dos palabras y se mira lo que devuelve.

Ojo con el homonimo: «Supreme Mortgage Lending Inc.» (NMLS 2371076) NO es la
casa. Confundirlas excluiria gente con la que si se puede trabajar.
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, saldo  # noqa: E402

SALIDA = os.path.join(RAIZ, "data", "trabajo", "lenders_casa.json")

print("saldo antes: %s" % saldo())

vistos: dict[str, dict] = {}
for termino in ("everett", "everett financial", "supreme lending", "supreme"):
    d = llamar("/v1/instant-search", {"query": termino},
               etiqueta="lend_%s" % termino.replace(" ", "_"), silencioso=True)
    res = ((d or {}).get("results") or {})
    for seccion in ("lenders", "companies"):
        for x in (res.get(seccion) or []):
            clave = "%s|%s" % (seccion, x.get("id"))
            if clave not in vistos:
                x["_seccion"] = seccion
                x["_termino"] = termino
                vistos[clave] = x

print("")
print("%-9s %-44s %-34s %s" % ("seccion", "id", "nombre", "nmls"))
print("-" * 104)
for x in sorted(vistos.values(), key=lambda v: (v["_seccion"], str(v.get("id")))):
    print("%-9s %-44s %-34s %s"
          % (x["_seccion"], str(x.get("id"))[:44],
             str(x.get("name") or x.get("label"))[:34],
             x.get("nmlsId") or x.get("nmls") or ""))

# La casa es Everett Financial, NMLS 2129. Se marca lo que lo diga.
de_la_casa = [x for x in vistos.values()
              if "everett" in str(x.get("name") or x.get("label") or "").lower()
              or str(x.get("nmlsId") or "") == "2129"]
print("")
print("── los que dicen Everett (la casa) ──")
for x in de_la_casa:
    print("   %-9s %-44s %s" % (x["_seccion"], x.get("id"),
                                x.get("name") or x.get("label")))

sospechosos = [x for x in vistos.values()
               if x not in de_la_casa
               and "supreme" in str(x.get("name") or x.get("label") or "").lower()]
print("")
print("── dicen «supreme» y NO son la casa (no excluir por estos) ──")
for x in sospechosos:
    print("   %-9s %-44s %-34s nmls=%s"
          % (x["_seccion"], x.get("id"),
             str(x.get("name") or x.get("label"))[:34],
             x.get("nmlsId") or ""))

with open(SALIDA, "w", encoding="utf-8") as fh:
    json.dump({"de_la_casa": de_la_casa, "homonimos": sospechosos,
               "todo": list(vistos.values())}, fh, ensure_ascii=False, indent=1)
print("")
print("saldo despues: %s" % saldo())
print("guardado en %s" % SALIDA)
