"""¿Se puede pedir SOLO la primera fila de un breakdown? Decide miles de creditos.

El listado de lenders de un agente cuesta 1 credito por fila, y casi todo el
valor esta en la primera: el lender con mas wallet share. Si se pudiera pedir
una sola, saber el lender y el LO principal de 273 agentes pasaria de ~5.500
creditos a ~550.

La guia dice que `agentLenders` no acepta paginacion. Pero la misma guia me
hizo concluir que la pestaña Transactions no se podia reconstruir, y estaba
mal: existian rutas colgadas del agente que no habia probado. Asi que se
mide en vez de creerle.

El peor caso esta acotado a proposito: se elige un agente con POCOS lenders,
asi que si la API ignora el limite se pagan unas pocas filas y no cuarenta.

Tres resultados, y los tres cierran la pregunta:
  · 400            -> gratis, no se puede
  · devuelve 1     -> SE PUEDE
  · devuelve todas -> se pagan esas filas, no se puede
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
#: Pocos lenders: acota el gasto si el limite se ignora. Pero no uno solo, o
#: «devolvio 1» no distinguiria entre que funcione y que solo tenga uno.
MIN, MAX = 4, 7


def elegir() -> tuple[str, int]:
    """Un agente con entre MIN y MAX lenders. Sin nombres en el codigo."""
    mejor = None
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            f = json.load(fh)
        n = f.get("mm_lenders_n")
        if f.get("mm_id") and isinstance(n, int) and MIN <= n <= MAX:
            # Preferir uno cuyo listado YA tengamos: asi se puede comprobar
            # que la primera fila devuelta es de verdad la de mas peso.
            if f.get("mm_lenders"):
                return f["mm_id"], n
            mejor = mejor or (f["mm_id"], n)
    if not mejor:
        raise SystemExit("no hay agente con %d-%d lenders" % (MIN, MAX))
    return mejor


def main() -> None:
    mm, n = elegir()
    print("agente de prueba: %s · tiene %d lenders segun su ficha" % (mm, n))
    print("peor caso de esta prueba: %d creditos" % n)
    print("")

    ruta = "/v1/agents/%s/breakdowns/lenders" % mm

    # 1 · paginacion, que es la forma estandar en esta API.
    antes = saldo()
    d = llamar(ruta, {"pagination": {"size": 1},
                      "sort": [{"field": "units", "order": "desc"}]},
               etiqueta="limite_pagination", silencioso=True)
    despues = saldo()
    costo = None if None in (antes, despues) else round(antes - despues)
    filas = (d or {}).get("data") or []
    print("── intento 1 · pagination.size = 1")
    print("   respondio : %s" % ("sí" if d is not None else "NO (rechazado)"))
    print("   filas     : %d de %d" % (len(filas), n))
    print("   costo     : %s" % costo)
    if filas:
        print("   primera   : %s · %s unidades"
              % (filas[0].get("label"), filas[0].get("units")))

    if d is not None and len(filas) == 1:
        print("")
        print("   ✅ SE PUEDE. Pedir una fila cuesta %s, no %d." % (costo, n))
    elif d is None:
        # 2 · si lo rechazo, el 400 fue gratis: probar `limit` pelado.
        print("")
        print("── intento 2 · limit = 1 (el 400 anterior no costo nada)")
        antes = saldo()
        d2 = llamar(ruta, {"limit": 1}, etiqueta="limite_limit",
                    silencioso=True)
        despues = saldo()
        f2 = (d2 or {}).get("data") or []
        print("   respondio : %s" % ("sí" if d2 is not None else "NO"))
        print("   filas     : %d de %d" % (len(f2), n))
        print("   costo     : %s"
              % (None if None in (antes, despues) else round(antes - despues)))
        if d2 is not None and len(f2) == 1:
            print("   ✅ SE PUEDE con `limit`.")
    else:
        print("")
        print("   ❌ NO se puede: ignoro el limite y cobro las %d filas."
              % len(filas))

    print("")
    print("saldo: %s" % saldo())


if __name__ == "__main__":
    main()
