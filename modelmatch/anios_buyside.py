"""Historical units: unidades del lado comprador, año por año. Cuesta 0.

`buyerUnits` es filtro con rango y `period` acepta años sueltos, asi que
`/v1/agents/count` contesta «¿tuvo entre 3 y 5 compras en 2024?» sin cobrar.
Acorralando con bandas sale el numero.

⛔ **El año EN CURSO no se pide como año literal.** Esta medido: para un
agente con mas de cinco operaciones en `yearToDate`, `period: "2026"` devuelve
0. El bucket del año corriente no esta poblado, y pedirlo asi hace creer que
el realtor dejo de producir -- un cero que parece un dato. El año en curso va
por `yearToDate`.

De los años sale el primer año con produccion, y de ahi la antiguedad
aproximada. Es un PISO: 2017 es el año mas viejo del enum, asi que quien
empezo antes sale subestimado y su fila lo dice.

Uso:
    python modelmatch/anios_buyside.py          # los que les falta
    python modelmatch/anios_buyside.py --todos
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, saldo  # noqa: E402

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
ANIO = dt.date.today().year
#: Años COMPLETOS. El actual se pide como `yearToDate`, no como año.
PERIODOS = [str(a) for a in range(2017, ANIO)] + ["yearToDate", "last3Months"]
#: Finas abajo, gruesas arriba: la diferencia entre 2 y 3 decide, la de 60 a
#: 70 no.
BANDAS = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 7), (7, 10), (10, 15),
          (15, 20), (20, 30), (30, 50), (50, 100), (100, None)]


def cuenta(mm: str, periodo: str, gte: int, lt) -> int | None:
    rango: dict = {"gte": gte}
    if lt is not None:
        rango["lt"] = lt
    d = llamar("/v1/agents/count",
               {"flatFilters": {"id": mm, "buyerUnits": rango},
                "period": periodo},
               etiqueta="ab_%s_%s_%s" % (mm, periodo, gte), silencioso=True)
    if not isinstance(d, dict) or not isinstance(d.get("total"), (int, float)):
        return None
    return int(d["total"])


def etiqueta(gte: int, lt) -> int | str:
    """Lo que se escribe para la banda [gte, lt).

    Aparte para que el verificador del manual la importe en vez de copiarla.
    Ojo: la banda sin tope se escribe `100+`, no como en Everett, donde la
    ultima se escribe pelada. Son dos escalas distintas y no se unifican.
    """
    if lt is None:
        return "%d+" % gte
    if lt == gte + 1:
        return gte
    return "%d-%d" % (gte, lt - 1)


#: Lo que devuelve `unidades()` cuando alguna llamada fallo. NO es "", que
#: significa «no produjo nada ese periodo».
FALLO = object()


def unidades(mm: str, periodo: str):
    """El numero, `FALLO` si alguna llamada no contesto, '' si no produjo.

    ⚠ Un fallo NO cuenta como «no es esta banda». Si falla justo la correcta,
    el recorrido sigue y escribe la ultima --100+--, un numero que nunca
    existio; y un fallo en la llamada base escribiria «no produjo», que
    adelanta el primer año y por tanto achica la antiguedad. Cualquier fallo
    deja el periodo pendiente.
    """
    base = cuenta(mm, periodo, 1, None)
    if base is None:
        return FALLO
    if base < 1:
        return ""
    for gte, lt in BANDAS:
        t = cuenta(mm, periodo, gte, lt)
        if t is None:
            return FALLO
        if t == 1:
            return etiqueta(gte, lt)
    return FALLO


#: Cuantos realtors se sondean para ver si el ultimo año cerrado esta poblado,
#: y cuantos de ellos tienen que dar positivo.
MUESTRA = 20
#: 15 de 20, no 1 de 20. Con el umbral en 1, un año poblado A MEDIAS --que es
#: justo el caso de enero-- pasa el sondeo y despues escribe «no produjo» sobre
#: la mayoria. En la corrida de referencia, 461 de 471 tenian produccion en el
#: año anterior: el sondeo deberia dar unos 19.
MINIMO = 15


def probar_el_ultimo_año_cerrado(ids: list[str]) -> bool:
    """¿El bucket del año recien cerrado ya tiene datos?

    Esta medido que el año EN CURSO devuelve 0 aunque haya produccion. Nada
    garantiza cuando se puebla el anterior: en enero, `ANIO - 1` puede estar
    tan vacio como lo estaba `ANIO`. Y un año vacio no se ve como un fallo --se
    ve como un realtor que dejo de producir-- y ademas adelanta el primer año
    y achica la antiguedad de TODO el lote a la vez.

    La muestra son los 20 PRIMEROS ids en orden alfabetico, no 20 cualquiera:
    dos corridas sobre el mismo lote tienen que sondear a los mismos y dar la
    misma respuesta.
    """
    ultimo = str(ANIO - 1)
    muestra = sorted(ids)[:MUESTRA]
    positivos = 0
    for mm in muestra:
        if (cuenta(mm, ultimo, 1, None) or 0) >= 1:
            positivos += 1
    print("   %s: %d de %d sondeados tienen produccion (hacen falta %d)"
          % (ultimo, positivos, len(muestra), MINIMO))
    # Con una muestra mas chica que el umbral se exige que produzcan todos:
    # un lote de 3 realtors no puede dar 15 positivos.
    return positivos >= min(MINIMO, len(muestra))


def main() -> None:
    todos = "--todos" in sys.argv
    pendientes = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            f = json.load(fh)
        if f.get("mm_id") and (todos or not f.get("anios_buyside")):
            pendientes.append((a, f))

    print("── 1 · ¿el ultimo año cerrado esta poblado? ──")
    if not probar_el_ultimo_año_cerrado([f["mm_id"] for _r, f in pendientes]):
        raise SystemExit(
            "\nEl sondeo de %d no llego al minimo. O el bucket de ese año "
            "todavia no esta poblado --pasa con el año en curso, esta medido-- "
            "o esta poblado a medias. En cualquiera de los dos casos, correr "
            "este paso escribiria «no produjo» sobre gente que si produjo, y "
            "eso achica la antiguedad de todo el lote a la vez.\n"
            "NO se corre la produccion por año. Los otros dos pasos --tipo de "
            "prestamo y Everett-- no dependen de esto y pueden correrse."
            % (ANIO - 1))
    print("")

    s0 = saldo()
    print("realtors a los que les falta la produccion por año: %d"
          % len(pendientes))
    print("periodos por realtor: %d · saldo %s · esto NO debe gastar nada"
          % (len(PERIODOS), s0))
    print("")

    fallaron = 0
    for i, (ruta, f) in enumerate(pendientes, 1):
        mm = f["mm_id"]
        anios, fallo = {}, False
        for p in PERIODOS:
            v = unidades(mm, p)
            if v is FALLO:
                # Se omite el periodo entero. Vacio y ausente no son lo mismo:
                # un periodo ausente es «no se pregunto», uno vacio es «no
                # produjo», y el derivado solo mira los que estan.
                fallo = True
                continue
            anios[p] = v
        f["anios_buyside"] = anios
        if fallo:
            f.pop("anios_buyside_en", None)   # sin sello: se reintenta
            fallaron += 1
        else:
            f["anios_buyside_en"] = dt.datetime.now(
                dt.timezone.utc).isoformat()
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(f, fh, ensure_ascii=False, indent=1)
        if i % 20 == 0 or i == len(pendientes):
            con = sum(1 for v in anios.values() if v != "")
            print("   %4d/%d · ultimo: %d periodos con produccion · "
                  "incompletos %d · saldo %s"
                  % (i, len(pendientes), con, fallaron, saldo()))

    s1 = saldo()
    gasto = None if None in (s0, s1) else round(s0 - s1, 2)
    print("")
    print("gasto: %s  %s" % (gasto, "OK, fue gratis" if gasto == 0
                             else "⚠ COBRO — revisar"))


if __name__ == "__main__":
    main()
