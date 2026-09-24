"""Re-evaluar realtors desde la CONSOLA. El cálculo vive en `motor.reevaluacion`.

    python supabase/reevaluar.py <realtor_id> [<realtor_id> ...]
    python supabase/reevaluar.py --capturados

Por qué este archivo es tan corto
---------------------------------
La primera versión traía el cálculo entero y usaba psycopg. En Vercel eso no
funciona --no hay driver, y no queremos credenciales de conexión directa en una
función pública-- así que el cálculo se mudó a `motor/reevaluacion.py`, que
recibe un `lector` y no sabe de drivers.

Aquí queda solo el adaptador de consola, que usa el mismo PostgREST que la API.
Usar el mismo camino en los dos sitios es lo que hace que lo que se prueba en
la consola sea lo que corre en producción.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))

from _comun import escribir, leer  # noqa: E402
from motor.reevaluacion import NoSePudoReevaluar, reevaluar  # noqa: E402
from supabase.config import cargar_env  # noqa: E402


class Lector:
    leer = staticmethod(leer)
    escribir = staticmethod(escribir)


def capturados() -> list[tuple[str, str]]:
    """(realtor_id, nombre) de quienes tienen captura de Model Match viva."""
    _c, caps, _ = leer("v_capturas_modelmatch_current",
                       "?select=realtor_id&alcance=eq.perfil&limit=5000")
    ids = sorted({c["realtor_id"] for c in (caps or []) if c.get("realtor_id")})
    if not ids:
        return []
    _c, rs, _ = leer("realtors", "?select=id,nombre_completo&id=in.(%s)"
                     % ",".join(ids))
    return [(r["id"], r["nombre_completo"]) for r in (rs or [])]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cargar_env()

    if "--capturados" in sys.argv:
        objetivos = capturados()
    else:
        ids = [a for a in sys.argv[1:] if not a.startswith("--")]
        if not ids:
            print(__doc__)
            return 2
        objetivos = [(i, i[:8]) for i in ids]

    print("a re-evaluar: %d" % len(objetivos))
    print("")
    print("%-24s %-22s %-22s %s"
          % ("realtor", "dolor", "veredicto", "mm_buyside_anualizado"))
    print("-" * 92)
    fallos = 0
    for rid, nombre in objetivos:
        try:
            r = reevaluar(rid, lector=Lector())
        except NoSePudoReevaluar as exc:
            fallos += 1
            print("%-24s NO SE PUDO: %s" % (nombre[:24], str(exc)[:60]))
            continue
        print("%-24s %-22s %-22s %s"
              % (nombre[:24],
                 "%s → %s" % (r["dolor_antes"] or "—", r["dolor_ahora"] or "—"),
                 "%s → %s" % (r["veredicto_antes"] or "—", r["veredicto_ahora"]),
                 r["mm_buyside_anualizado"] if r["mm_buyside_anualizado"]
                 is not None else "—"))
    print("")
    print("fallos: %d" % fallos)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
