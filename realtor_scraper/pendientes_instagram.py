"""Los realtors a los que les falta el scraping de Instagram.

Tres fuentes, y hay que mirar las tres porque cada una sabe algo distinto:

  · **el libro** (`Homesi_Scoring_Realtors_v3_PACS`) define el OBJETIVO: los
    que tienen handle. Son 1.203 de 4.249; el resto no tiene cuenta que
    raspar y no son «pendientes», son «no aplica»;
  · **el checkpoint** del finder dice que raspo el proceso local;
  · **Supabase** (`v_ig_senales_current`) dice que llego a la base.

Los dos ultimos pueden no coincidir: un perfil raspado cuyo parseo nunca se
cargo esta hecho para el checkpoint y ausente para la base. Ese caso se
reporta aparte en vez de decidirlo solo, porque volver a raspar cuesta tiempo
y sesion de Instagram.

Salida: data/salida/instagram_pendientes.csv y .xlsx
"""
from __future__ import annotations

import csv
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))
sys.path.insert(0, os.path.join(RAIZ, "realtor_scraper"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from supabase.config import cargar_env  # noqa: E402

cargar_env()
from _comun import leer  # noqa: E402

SALIDA = os.path.join(RAIZ, "data", "salida")
CHECKPOINT = os.path.join(RAIZ, "realtor_scraper", "output",
                          "ig_checkpoint.json")


def normalizar(h) -> str:
    return str(h or "").strip().lstrip("@").lower()


def objetivo() -> list:
    """La lista objetivo, del MISMO codigo que usa el finder.

    No se reimplementa el filtro (`MQL` o tier A/B): si esta lista y la del
    finder se calcularan por separado, el dia que cambie el criterio el
    archivo de pendientes diria una cosa y el scraper haria otra.
    """
    from instagram.finder import cargar_objetivo  # noqa: PLC0415
    objs, _informe = cargar_objetivo()
    return objs


def main() -> None:
    try:
        objs = objetivo()
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "no pude construir el objetivo con el codigo del finder (%s). "
            "Corre `python -m instagram.finder --objetivo` desde "
            "realtor_scraper/ para ver que pasa." % str(exc)[:200])

    print("objetivo del libro: %d" % len(objs))

    hechos = set()
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, encoding="utf-8") as fh:
            hechos = set(json.load(fh).get("hechos") or [])
    print("checkpoint local  : %d hechos" % len(hechos))

    en_base, desde, paso = set(), 0, 1000
    while True:
        cod, filas, _ = leer("v_ig_senales_current",
                             "?select=handle&limit=%d&offset=%d" % (paso, desde))
        if cod >= 400:
            raise SystemExit("supabase: %s" % str(filas)[:200])
        en_base |= {normalizar(f.get("handle")) for f in (filas or [])}
        if len(filas or []) < paso:
            break
        desde += paso
    en_base.discard("")
    print("en Supabase       : %d handles" % len(en_base))

    pendientes, raspados_sin_cargar = [], []
    for o in objs:
        clave = getattr(o, "clave", None)
        h = normalizar(getattr(o, "handle_del_libro", None))
        fila = {
            "nombre": getattr(o, "nombre", None),
            "handle": h,
            "email": getattr(o, "email", None),
            "estado": getattr(o, "estado", None),
            "tier": getattr(o, "tier", None),
            "nivel": getattr(o, "nivel", None),
        }
        if h and h in en_base:
            continue                      # ya esta el dato bueno
        if clave and clave in hechos:
            raspados_sin_cargar.append(fila)
            continue
        pendientes.append(fila)

    print("")
    print("PENDIENTES de raspar        : %d" % len(pendientes))
    print("raspados pero NO en la base : %d  (no se re-raspan: hay que "
          "parsear y cargar)" % len(raspados_sin_cargar))

    os.makedirs(SALIDA, exist_ok=True)
    cols = ["nombre", "handle", "email", "estado", "tier", "nivel"]
    ruta = os.path.join(SALIDA, "instagram_pendientes.csv")
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(pendientes)
    print("")
    print("guardado en %s" % ruta)

    if raspados_sin_cargar:
        r2 = os.path.join(SALIDA, "instagram_raspados_sin_cargar.csv")
        with open(r2, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(raspados_sin_cargar)
        print("guardado en %s" % r2)


if __name__ == "__main__":
    main()
