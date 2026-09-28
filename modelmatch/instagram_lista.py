"""Todo lo de Instagram por realtor, aplanado. Cero creditos de Model Match.

`v_ig_senales_current` guarda 40 señales dentro de un jsonb. Para que entren
en una sola tabla hay que aplanarlas a columnas `ig_<clave>`, y para que la
tabla no mienta hay que aplanar TODAS -- si se eligen a mano las que parecen
utiles, la proxima vez que alguien busque una que no esta va a concluir que
no se capturo, cuando si.

Salida: data/trabajo/instagram.json (gitignored: trae texto de cuentas
personales y comentarios de terceros).
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from supabase.config import cargar_env  # noqa: E402

cargar_env()
from _comun import leer  # noqa: E402

SALIDA = os.path.join(RAIZ, "data", "trabajo", "instagram.json")


def todas(tabla: str, consulta: str, paso: int = 1000) -> list[dict]:
    """PostgREST corta en ~1000 filas sin avisar. Se pagina siempre."""
    fuera, desde = [], 0
    while True:
        cod, filas, _ = leer(tabla, "%s&limit=%d&offset=%d"
                             % (consulta, paso, desde))
        if cod >= 400:
            raise SystemExit("%s: %s" % (tabla, filas))
        fuera.extend(filas or [])
        if len(filas or []) < paso:
            return fuera
        desde += paso


print("── señales ──")
sen = todas("v_ig_senales_current", "?select=*")
print("   filas: %d" % len(sen))

print("── clase del perfil ──")
clases = {c["realtor_id"]: c for c in todas("v_ig_clase_actual", "?select=*")}
print("   filas: %d" % len(clases))

salida: dict[str, dict] = {}
claves = set()
for f in sen:
    rid = f.get("realtor_id")
    if not rid:
        continue
    fila = {
        "ig_handle": f.get("handle"),
        "ig_estado_perfil": f.get("estado_perfil"),
        "ig_estado_evidencia": f.get("estado_evidencia"),
        "ig_handle_confianza": f.get("handle_confianza"),
        "ig_captions_n": f.get("captions_n"),
        "ig_comentarios_n": f.get("comentarios_n"),
        "ig_paginacion_truncada": f.get("paginacion_truncada"),
        "ig_desajuste_idioma": f.get("desajuste_idioma"),
        "ig_capturado_en": f.get("capturado_en"),
    }
    c = clases.get(rid) or {}
    fila.update({
        "ig_clase": c.get("clase"),
        "ig_clase_motivo": c.get("motivo"),
        "ig_clase_origen": c.get("origen"),
        "ig_clase_revisar": c.get("revisar"),
        "ig_version_lexico": c.get("version_lexico"),
        "ig_auditada_por": c.get("auditada_por"),
    })
    for k, v in (f.get("senales") or {}).items():
        fila["ig_%s" % k] = v
        claves.add("ig_%s" % k)
    salida[rid] = fila

with open(SALIDA, "w", encoding="utf-8") as fh:
    json.dump(salida, fh, ensure_ascii=False, indent=1)

print("")
print("realtors con Instagram: %d" % len(salida))
print("columnas ig_* distintas: %d" % (len(claves) + 15))
print("guardado en %s" % SALIDA)
