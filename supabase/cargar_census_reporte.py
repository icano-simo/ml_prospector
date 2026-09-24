"""Carga el reporte de mercado latino por estado en `pacs.census_reporte_estado`.

    python supabase/cargar_census_reporte.py <anexo.json>            # mide
    python supabase/cargar_census_reporte.py <anexo.json> --guardar

El anexo es el JSON que manda Cowork: `{"evidencias": [{id, tipo, texto,
fuente}, ...]}` con un id `CENSUS-RPT-<ST>` por estado.

El texto se carga EXACTO
------------------------
Ni se recorta, ni se normaliza, ni se le quitan los espacios. Las fichas citan
estos ids y el validador comprueba que los NÚMEROS del texto de la ficha estén
en la evidencia: cualquier retoque aquí --un punto por una coma, un guion
largo por uno corto-- convierte una cita correcta en un rechazo, y el rechazo
apunta a la ficha, no a este script.

**No escribe nada sin `--guardar`.**
"""
from __future__ import annotations

import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))

from _comun import escribir, leer  # noqa: E402
from supabase.config import cargar_env  # noqa: E402

_RE_ID = re.compile(r"^CENSUS-RPT-([A-Z]{2})$")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cargar_env()
    rutas = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not rutas:
        print(__doc__)
        return 2
    guardar = "--guardar" in sys.argv

    with open(rutas[0], encoding="utf-8") as fh:
        anexo = json.load(fh)

    filas, problemas = [], []
    for e in anexo.get("evidencias") or []:
        m = _RE_ID.match(str(e.get("id") or ""))
        if not m:
            problemas.append("id con forma inesperada: %r" % e.get("id"))
            continue
        if not (e.get("texto") or "").strip():
            problemas.append("%s viene sin texto" % e["id"])
            continue
        filas.append({"estado": m.group(1), "id_evidencia": e["id"],
                      "texto": e["texto"], "fuente": e.get("fuente") or ""})

    for p in problemas:
        print("✕ %s" % p)
    if problemas:
        print("")
        print("no cargo nada: el anexo tiene que venir entero.")
        return 1

    # Lo que YA está, para no volver a escribir lo mismo. El unique lo
    # rechazaría igual, pero un 409 se lee como un error y esto es un estado
    # normal: el anexo se vuelve a cargar cada vez que crece.
    _c, hay, _ = leer("census_reporte_estado",
                      "?select=estado,texto&limit=500")
    ya = {(f["estado"], f["texto"]) for f in (hay or [])}

    nuevas = [f for f in filas if (f["estado"], f["texto"]) not in ya]
    print("estados en el anexo: %d" % len(filas))
    for f in filas:
        marca = "nuevo" if (f["estado"], f["texto"]) not in ya else "ya estaba"
        print("   %-3s %-9s %5d caracteres · %s"
              % (f["estado"], marca, len(f["texto"]), f["fuente"][:60]))

    if not guardar:
        print("")
        print("no se escribió nada. Pasá --guardar. (entrarían %d)"
              % len(nuevas))
        return 0
    if not nuevas:
        print("")
        print("nada nuevo que cargar.")
        return 0

    cod, resp, _ = escribir("census_reporte_estado", nuevas, devolver=False)
    if cod >= 400:
        print("no se pudo escribir (%s): %s" % (cod, str(resp)[:300]))
        return 1

    # Se relee de la base: un 2xx no prueba que la fila quedó como uno cree.
    _c, ahora, _ = leer("v_census_reporte_actual",
                        "?select=estado,id_evidencia,cargado_en&limit=500")
    print("")
    print("escritas: %d · estados vigentes ahora: %d"
          % (len(nuevas), len(ahora or [])))
    for f in sorted(ahora or [], key=lambda x: x["estado"]):
        print("   %-3s %s · %s" % (f["estado"], f["id_evidencia"],
                                   str(f["cargado_en"])[:19]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
