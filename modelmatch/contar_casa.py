"""¿Cuantos agentes del PAIS financiaron con la casa? Cuesta 0 creditos.

`POST /v1/agents/count` devuelve un numero, y lo que devuelve un numero es
gratis: medido contra el ledger. Asi se puede dimensionar el universo entero
ANTES de decidir si vale la pena pagarlo, porque la lista equivalente cobra
1 credito por fila devuelta y no admite pedir menos.

Contesta tres cosas de una, sin gastar:
  · cuantos hay en los ultimos 12 meses, que es lo que se pregunto;
  · cuanto cambia segun la ventana, que en nuestra muestra casi triplicaba;
  · cuanto aportan los tres ids que NO estan comprobados.

Y lo reparte por estado, para poder comprar solo donde operamos si el total
no entra en el presupuesto.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.auditar_casa import CONFIRMADOS, DUDOSOS  # noqa: E402
from modelmatch.cliente import llamar, saldo  # noqa: E402

CASA = CONFIRMADOS + DUDOSOS
VENTANAS = ("last12Months", "last24Months", "allTime")
#: Los estados donde hay realtors nuestros, por volumen de lote.
ESTADOS = ("TX", "CA", "FL", "IL", "AZ", "GA", "NV", "NJ", "NY", "CO", "OK",
           "WA", "NC", "VA", "MD", "PA", "OH", "MI")


def contar(ids, periodo, estado=None, etiqueta=""):
    flat = {}
    if estado:
        flat["state"] = estado
    cuerpo = {"footprint": {"lender": ids}, "period": periodo}
    if flat:
        cuerpo["flatFilters"] = flat
    d = llamar("/v1/agents/count", cuerpo, etiqueta=etiqueta, silencioso=True)
    if not isinstance(d, dict):
        return None
    t = d.get("total")
    return int(t) if isinstance(t, (int, float)) else None


def main() -> None:
    s0 = saldo()
    print("saldo al empezar: %s · esto NO debe gastar nada" % s0)
    print("")

    print("── agentes del PAIS cuyas operaciones financio la casa ──")
    print("%-16s %12s %12s" % ("ventana", "9 ids", "solo los 6"))
    print("-" * 42)
    for v in VENTANAS:
        n9 = contar(CASA, v, etiqueta="cnt_%s_9" % v)
        n6 = contar(CONFIRMADOS, v, etiqueta="cnt_%s_6" % v)
        print("%-16s %12s %12s"
              % (v, "{:,}".format(n9) if n9 is not None else "?",
                 "{:,}".format(n6) if n6 is not None else "?"))

    print("")
    print("── a 12 meses, por estado ──")
    filas = []
    for e in ESTADOS:
        n = contar(CASA, "last12Months", estado=e, etiqueta="cnt_12m_%s" % e)
        if n:
            filas.append((e, n))
    filas.sort(key=lambda x: -x[1])
    acumulado = 0
    for e, n in filas:
        acumulado += n
        print("   %-4s %8s   (acumulado %s)"
              % (e, "{:,}".format(n), "{:,}".format(acumulado)))

    s1 = saldo()
    gasto = None if None in (s0, s1) else round(s0 - s1, 2)
    print("")
    print("saldo al terminar: %s · gasto: %s  %s"
          % (s1, gasto, "OK, fue gratis" if gasto == 0 else "⚠ COBRO — revisar"))
    print("")
    print("Recordatorio: LISTARLOS cuesta 1 credito por fila devuelta.")


if __name__ == "__main__":
    main()
