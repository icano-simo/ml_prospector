"""Genera el paquete de evidencia y lo guarda, para que Cowork lo lea por SQL.

    python supabase/generar_paquetes.py --con-mm          # solo mide
    python supabase/generar_paquetes.py --con-mm --guardar
    python supabase/generar_paquetes.py <realtor_id> --guardar

Por qué se guarda y no se calcula al vuelo
------------------------------------------
Cowork lee por SQL --`pacs.paquete_ficha(realtor_id)`-- y no puede llamar a
Python. Si el paquete se calculara al vuelo dentro de una vista, habría que
reimplementar en SQL la lista blanca de campos, el troceado de los posts y las
activaciones PACS-H. Serían dos versiones de la misma regla, y el día que
difieran Cowork leería una cosa y el validador de la app comprobaría contra
otra.

Así que lo calcula `motor/paquete.py` --que tiene pruebas-- y aquí solo se
guarda. Un paquete guardado es además lo que hace que el `hash` signifique
algo: la ficha se escribió contra ESE paquete, y está ahí para comprobarlo.

**No escribe nada sin `--guardar`.**
"""
from __future__ import annotations

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))

from _comun import escribir, leer  # noqa: E402
from supabase.config import cargar_env  # noqa: E402


def _uno(tabla, consulta):
    _c, filas, _ = leer(tabla, consulta)
    return (filas or [None])[0]


#: El armador vive en `api/rutas.py` y NO aquí, aunque este sea el script que
#: lo usa. Lo llaman los dos --el guardado de una captura, que corre en Vercel
#: donde `supabase/` no viaja, y esto-- y dos implementaciones serían dos
#: paquetes distintos para el mismo realtor según quién lo pidiera. El `hash`
#: dejaría de significar nada, que es lo único que sostiene «esta ficha se
#: escribió contra este paquete».
from api.rutas import paquete_de_realtor as paquete_de  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cargar_env()
    guardar = "--guardar" in sys.argv

    if "--con-mm" in sys.argv:
        _c, caps, _ = leer("v_capturas_modelmatch_current",
                           "?select=realtor_id&alcance=eq.perfil&limit=5000")
        ids = sorted({c["realtor_id"] for c in (caps or [])
                      if c.get("realtor_id")})
    else:
        ids = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not ids:
        print(__doc__)
        return 2

    # Lo que YA está guardado, por realtor. Un paquete cuyo hash no cambió es
    # la misma evidencia otra vez: la tabla es append-only, y «append-only» no
    # quiere decir «guardar lo mismo de nuevo». Con duplicados, la ficha dice
    # contra qué paquete se escribió y no se sabe cuál de los dos.
    #
    # La tabla lo impide igual con un unique. Esto es para poder DECIR «sin
    # cambios» en vez de devolver un 409 que hay que ir a interpretar.
    _c, ya, _ = leer("v_paquete_ficha",
                     "?select=realtor_id,hash_paquete&limit=5000")
    hash_actual = {f["realtor_id"]: f["hash_paquete"] for f in (ya or [])}

    print("paquetes a generar: %d%s"
          % (len(ids), "" if guardar else "   ·   MIDE, NO ESCRIBE"))
    print("")
    filas = []
    sin_cambios = 0
    for rid in ids:
        p = paquete_de(rid)
        if not p:
            print("   %s · no existe" % rid[:8])
            continue
        if hash_actual.get(rid) == p["hash_paquete"]:
            sin_cambios += 1
            print("   %-8s %-26s sin cambios (%s)"
                  % (rid[:8], (p.get("nombre") or "")[:26],
                     p["hash_paquete"][:12]))
            continue
        por_tipo: dict = {}
        for e in p["evidencias"]:
            por_tipo[e["tipo"]] = por_tipo.get(e["tipo"], 0) + 1
        print("   %-8s %-26s %3d evidencias   %s"
              % (rid[:8], (p.get("nombre") or "")[:26], len(p["evidencias"]),
                 p["hash_paquete"][:12]))
        print("            %s" % ", ".join(
            "%s %d" % (t, n) for t, n in sorted(por_tipo.items())))
        filas.append({"realtor_id": rid, "version_paquete": p["version_paquete"],
                      "hash_paquete": p["hash_paquete"], "paquete": p})

    print("")
    print("nuevos o cambiados: %d · sin cambios: %d" % (len(filas), sin_cambios))
    if not guardar:
        print("no se escribió nada. Pasá --guardar.")
        return 0
    if not filas:
        print("nada que guardar: ningún paquete cambió.")
        return 0
    cod, det, _ = escribir("paquetes_ficha", filas, devolver=False)
    if cod >= 400:
        print("NO se pudieron guardar: %s" % str(det)[:300])
        return 1
    print("guardados: %d" % len(filas))
    print("")
    print("Cowork los lee con:  select pacs.paquete_ficha('<realtor_id>');")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
