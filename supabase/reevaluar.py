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

    # `--simular` hace todo menos escribir. Es para medir el impacto de un
    # cambio de reglas ANTES de desplegarlo: una evaluación escrita con una
    # versión que producción todavía no corre sale en la pantalla marcada como
    # «de una versión anterior», que es justo al revés.
    guardar = "--simular" not in sys.argv

    print("a re-evaluar: %d%s" % (len(objetivos),
                                  "" if guardar else "  (SIMULACIÓN: no escribe)"))
    print("")
    print("%-22s %-24s %-20s %-16s %s"
          % ("realtor", "dolor", "apertura", "J-Q01", "veredicto"))
    print("-" * 104)
    fallos = 0
    cambios = 0
    for rid, nombre in objetivos:
        try:
            r = reevaluar(rid, lector=Lector(), guardar=guardar)
        except NoSePudoReevaluar as exc:
            fallos += 1
            print("%-22s NO SE PUDO: %s" % (nombre[:22], str(exc)[:60]))
            continue
        cambios += 1 if r["cambio"] else 0
        share = r.get("mm_share_buy")
        print("%-22s %-24s %-20s %-16s %s"
              % (nombre[:22],
                 "%s → %s" % (r["dolor_antes"] or "—", r["dolor_ahora"] or "—"),
                 "%s → %s" % (_corto(r["apertura_antes"]),
                              _corto(r["apertura_ahora"])),
                 "%s → %s%s" % (r["gating_antes"] if r["gating_antes"]
                                is not None else "—",
                                r["gating_ahora"] if r["gating_ahora"]
                                is not None else "—",
                                "" if share is None else " (%.0f%% buy)"
                                % (100 * share)),
                 "%s → %s" % (r["veredicto_antes"] or "—",
                              r["veredicto_ahora"])))
    print("")
    print("cambiaron: %d de %d · fallos: %d"
          % (cambios, len(objetivos), fallos))
    if not guardar:
        print("NO se escribió nada: fue una simulación.")
    return 1 if fallos else 0


#: Los códigos de apertura, acortados para que la tabla se lea.
_CORTOS = {"sin_apertura_hipotecaria": "sin hipoteca",
           "pregunta_de_cierre_de_brecha_lender": "preg. lender"}


def _corto(cod) -> str:
    return _CORTOS.get(cod, "dolor") if cod else "dolor"


if __name__ == "__main__":
    sys.exit(main())
