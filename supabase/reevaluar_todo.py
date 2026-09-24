"""Re-evaluar el lote ENTERO, con el mismo `reevaluar` de una captura.

    python supabase/reevaluar_todo.py                 # solo mide, no escribe
    python supabase/reevaluar_todo.py --con-mm        # solo los que tienen MM
    python supabase/reevaluar_todo.py --guardar       # escribe

Por que un lector en memoria y no un segundo camino
---------------------------------------------------
`reevaluar` hace cuatro lecturas por realtor. Sobre 4.186 eso son mas de
16.000 peticiones a PostgREST, que no termina en un rato razonable.

La tentacion es escribir aqui una version «masiva» del calculo. Eso seria medir
el camino paralelo: la corrida de auditoria diria una cosa y el guardado de una
captura haria otra, y la diferencia no aparece hasta que alguien la busca.

Asi que lo que cambia es el LECTOR, no el calculo. `LectorEnMemoria` carga las
cuatro vistas de una vez y responde las mismas consultas desde un diccionario.
`motor.reevaluacion.reevaluar` corre sin enterarse, regla por regla, igual que
cuando se guarda una captura.
"""
from __future__ import annotations

import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))

from _comun import escribir, leer  # noqa: E402
from motor.reevaluacion import NoSePudoReevaluar, reevaluar  # noqa: E402
from supabase.config import cargar_env  # noqa: E402

PAGINA = 1000

#: Las cuatro vistas que `reevaluar` consulta, con las columnas que pide.
VISTAS = {
    "v_evaluacion_actual": ("realtor_id,entrada,dolor_primario,excluido,"
                            "excluido_motivo,veredicto_contacto,apertura,"
                            "gating_intensidad,version_reglas,resultado"),
    "v_ig_senales_current": ("realtor_id,estado_perfil,captions_n,"
                             "comentarios_n,senales"),
    "v_ig_clase_actual": "realtor_id,clase,motivo",
    "v_capturas_modelmatch_current": "realtor_id,parseado,capturado_en",
}

_RE_RID = re.compile(r"realtor_id=eq\.([0-9a-fA-F-]{36})")


class LectorEnMemoria:
    """Responde `leer` desde un cache. La firma es la de `api._comun.leer`."""

    def __init__(self, cache: dict):
        self.cache = cache
        self.escrituras: list = []

    def leer(self, tabla, consulta="", **kw):
        m = _RE_RID.search(consulta or "")
        if not m:
            raise AssertionError(
                "consulta sin realtor_id, no la puedo servir del cache: %r"
                % consulta[:120])
        filas = list(self.cache.get(tabla, {}).get(m.group(1), []))
        if "order=capturado_en.asc" in (consulta or ""):
            filas.sort(key=lambda f: f.get("capturado_en") or "")
        return 200, filas, {}

    def escribir(self, tabla, filas, **kw):
        # En modo medicion nunca se llama. Si se llamara, que se vea.
        self.escrituras.append((tabla, len(filas)))
        return escribir(tabla, filas, **kw)


def cargar_cache() -> dict:
    cache: dict = {}
    for vista, columnas in VISTAS.items():
        por_realtor: dict = {}
        desde = 0
        while True:
            cod, filas, _ = leer(
                vista, "?select=%s&limit=%d&offset=%d"
                % (columnas, PAGINA, desde))
            if cod >= 400:
                raise SystemExit("no se pudo leer %s: %s" % (vista, filas))
            for f in filas or []:
                rid = f.get("realtor_id")
                if rid:
                    por_realtor.setdefault(rid, []).append(f)
            if len(filas or []) < PAGINA:
                break
            desde += PAGINA
        cache[vista] = por_realtor
        print("   %-32s %6d realtors" % (vista, len(por_realtor)))
    return cache


def _afirma_p_q14(activaciones) -> bool:
    for a in activaciones or []:
        if (a.get("qualifier") == "P-Q14" and a.get("acto") == "AFIRMA"
                and a.get("intensidad") == 3 and a.get("grado") == "E0"):
            return True
    return False


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cargar_env()
    guardar = "--guardar" in sys.argv
    solo_mm = "--con-mm" in sys.argv

    print("cargando las cuatro vistas...")
    cache = cargar_cache()
    lector = LectorEnMemoria(cache)

    ids = sorted(cache["v_evaluacion_actual"])
    con_mm = set(cache["v_capturas_modelmatch_current"])
    if solo_mm:
        ids = [i for i in ids if i in con_mm]

    print("")
    print("a re-evaluar: %d%s%s"
          % (len(ids), "  (solo los que tienen Model Match)" if solo_mm else "",
             "" if guardar else "  ·  MIDE, NO ESCRIBE"))
    print("")

    n = cambio_dolor = cambio_ver = fallos = 0
    afirma_antes = afirma_ahora = 0
    sin_dolor_antes = sin_dolor_ahora = 0
    sin_hipoteca = 0
    por_motivo: dict = {}
    for rid in ids:
        try:
            r = reevaluar(rid, lector=lector, guardar=guardar, detalle=True)
        except NoSePudoReevaluar as exc:
            fallos += 1
            por_motivo[str(exc)[:60]] = por_motivo.get(str(exc)[:60], 0) + 1
            continue
        n += 1
        if r["dolor_antes"] != r["dolor_ahora"]:
            cambio_dolor += 1
        if r["veredicto_antes"] != r["veredicto_ahora"]:
            cambio_ver += 1
        afirma_antes += 1 if _afirma_p_q14(r["activaciones_antes"]) else 0
        afirma_ahora += 1 if _afirma_p_q14(r["activaciones_ahora"]) else 0
        sin_dolor_antes += 1 if not r["dolor_antes"] else 0
        sin_dolor_ahora += 1 if not r["dolor_ahora"] else 0
        sin_hipoteca += 1 if r["apertura_ahora"] == "sin_apertura_hipotecaria" else 0
        if n % 500 == 0:
            print("   ... %d" % n)

    print("")
    print("═" * 64)
    print("  re-evaluadas            %6d" % n)
    print("  fallaron                %6d" % fallos)
    for motivo, cuantas in sorted(por_motivo.items(), key=lambda kv: -kv[1]):
        print("      %6d · %s" % (cuantas, motivo))
    print("")
    print("  cambian de dolor        %6d" % cambio_dolor)
    print("  cambian de veredicto    %6d" % cambio_ver)
    print("")
    print("  P-Q14 AFIRMA 3/E0 antes %6d" % afirma_antes)
    print("  P-Q14 AFIRMA 3/E0 ahora %6d" % afirma_ahora)
    print("")
    print("  sin dolor primario antes %5d" % sin_dolor_antes)
    print("  sin dolor primario ahora %5d" % sin_dolor_ahora)
    print("  de esos, «sin apertura hipotecaria» %d" % sin_hipoteca)
    print("═" * 64)
    if guardar:
        print("  ESCRITAS: %d" % len(lector.escrituras))
    else:
        print("  no se escribió nada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
