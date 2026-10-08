"""Operaciones con la casa, por bandas y por ventana. Cuesta 0 creditos.

Reemplaza a la tabla de lenders --que cobra 1 por fila-- para la unica
pregunta que de verdad usamos de ella: la relacion con la casa. El conteo no
cobra, asi que se puede preguntar todo lo que haga falta.

Cuatro columnas, dos ventanas:

    ¿trabajo con la casa alguna vez?      ·  cuantas operaciones
    ¿trabajo en los ultimos 12 meses?     ·  cuantas operaciones

La banda se pide con las dos cotas en la misma llamada:

    "footprint": {"lender": CASA, "units": {"gte": 1, "lt": 10}}

**`lt` no estaba medido.** `gte` si --es lo que ya usaba la columna de
tramos--, pero la cota superior solo estaba documentada. Si se ignorara en
silencio, TODAS las bandas darian positivo y el numero saldria siempre el de
la primera: por eso lo primero que hace este script es probarlo contra un
realtor cuya cifra conocemos por su tabla cruda de lenders, y se niega a
seguir si no cuadra.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.auditar_casa import CONFIRMADOS, DUDOSOS  # noqa: E402
from modelmatch.cliente import llamar, saldo  # noqa: E402

CASA = CONFIRMADOS + DUDOSOS
DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
HUELE = re.compile(r"everett|evertt", re.IGNORECASE)

#: Las bandas, excluyentes y en orden. La ultima no lleva tope.
BANDAS = [(1, 2), (2, 3), (3, 5), (5, 10), (10, 20), (20, 50), (50, None)]
VENTANAS = (("allTime", "historico"), ("last12Months", "12m"))


def cuenta(mm: str, periodo: str, gte=None, lt=None, etq="") -> int | None:
    pie: dict = {"lender": CASA}
    if gte is not None:
        rango: dict = {"gte": gte}
        if lt is not None:
            rango["lt"] = lt
        pie["units"] = rango
    d = llamar("/v1/agents/count",
               {"flatFilters": {"id": mm}, "footprint": pie,
                "period": periodo},
               etiqueta=etq, silencioso=True)
    if not isinstance(d, dict) or not isinstance(d.get("total"), (int, float)):
        return None
    return int(d["total"])


def testigo():
    """Un realtor con la casa en su tabla CRUDA, y sus unidades reales."""
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            f = json.load(fh)
        for x in (f.get("mm_lenders") or []):
            if HUELE.search(str(x.get("nombre") or "")):
                return f["mm_id"], f.get("nombre"), int(x.get("unidades") or 0)
    return None


def probar_la_cota_superior() -> bool:
    """¿`lt` recorta de verdad, o lo ignora?"""
    t = testigo()
    if not t:
        print("   sin testigo con tabla cruda: no se puede comprobar `lt`")
        return False
    mm, nombre, reales = t
    print("   testigo: %s · %d operaciones con la casa segun su tabla cruda"
          % (nombre, reales))
    dentro = cuenta(mm, "allTime", reales, reales + 1, "lt_dentro")
    fuera = cuenta(mm, "allTime", reales + 1, reales + 2, "lt_fuera")
    print("      banda [%d, %d) -> %s   (esperado 1)"
          % (reales, reales + 1, dentro))
    print("      banda [%d, %d) -> %s   (esperado 0)"
          % (reales + 1, reales + 2, fuera))
    ok = dentro == 1 and fuera == 0
    print("      => `lt` %s" % ("recorta bien" if ok else "NO funciona"))
    return ok


def etiqueta(gte: int, lt) -> int | str:
    """Lo que se escribe en la celda para la banda [gte, lt).

    Esta aparte para que el verificador del manual la importe en vez de
    copiarla: la tabla de bandas del manual YA estuvo mal --decia «3 · 4»
    donde el codigo agrupa `3-4`-- y un numero de operaciones con Everett mal
    leido decide una exclusion.
    """
    if lt is None:
        return gte
    if lt == gte + 1:
        return gte
    return "%d-%d" % (gte, lt - 1)


def unidades(mm: str, periodo: str) -> int | str:
    """El numero exacto, o «50+». Vacio si no trabajo con la casa."""
    if (cuenta(mm, periodo, 1, None, "base_%s" % periodo) or 0) < 1:
        return ""
    for gte, lt in BANDAS:
        if cuenta(mm, periodo, gte, lt, "b%s_%s" % (gte, periodo)) == 1:
            return etiqueta(gte, lt)
    return "50+"


def main() -> None:
    print("── 1 · comprobar que la cota superior recorta ──")
    if not probar_la_cota_superior():
        raise SystemExit(
            "\nLa banda no se puede usar: `lt` no recorta. Sin eso, todas "
            "las bandas darian positivo y el numero seria siempre el de la "
            "primera. NO se corre el lote.")

    objetivo = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            f = json.load(fh)
        if f.get("mm_id"):
            objetivo.append((a, f))

    s0 = saldo()
    print("")
    print("── 2 · el lote: %d realtors identificados ──" % len(objetivo))
    print("saldo: %s · esto NO debe gastar nada" % s0)
    print("")

    vivos = historicos = 0
    for i, (ruta, f) in enumerate(objetivo, 1):
        mm = f["mm_id"]
        for periodo, sufijo in VENTANAS:
            n = unidades(mm, periodo)
            f["everett_%s" % sufijo] = "SÍ" if n != "" else "no"
            f["everett_u_%s" % sufijo] = n
        f["everett_bandas_en"] = dt.datetime.now(dt.timezone.utc).isoformat()
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(f, fh, ensure_ascii=False, indent=1)
        historicos += f["everett_historico"] == "SÍ"
        vivos += f["everett_12m"] == "SÍ"
        if i % 25 == 0 or i == len(objetivo):
            print("   %3d/%d · con la casa alguna vez %d · en 12 meses %d"
                  % (i, len(objetivo), historicos, vivos))

    s1 = saldo()
    gasto = None if None in (s0, s1) else round(s0 - s1, 2)
    print("")
    print("con la casa alguna vez  : %d de %d" % (historicos, len(objetivo)))
    print("con la casa en 12 meses : %d" % vivos)
    print("relaciones VIEJAS       : %d  (excluidos hoy por algo que ya no "
          "pasa)" % (historicos - vivos))
    print("gasto: %s  %s" % (gasto, "OK, fue gratis" if gasto == 0
                             else "⚠ COBRO — revisar"))


if __name__ == "__main__":
    main()
