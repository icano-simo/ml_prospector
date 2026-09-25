"""Los realtors con Instagram, con TODO lo que sirve para desambiguarlos en MM.

El pedido dice «si hay varios perfiles debes revisar el correo o telefono que
ya teniamos en la fuente inicial de lo que salia de mmi». Asi que la lista de
trabajo no es una lista de nombres: es nombre + emails + telefonos + licencia
+ ciudad/estado + la compañia VIEJA, que es contra la que se compara para
detectar el cambio de casa.

Salida: data/trabajo/realtors_con_ig.json (gitignored), que es lo que come el
extractor. Cero llamadas a Model Match.
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

SALIDA = os.path.join(RAIZ, "data", "trabajo")


def todas(tabla: str, consulta: str, paso: int = 1000) -> list[dict]:
    """PostgREST corta en ~1000 filas y NO avisa. Se pagina siempre.

    Es la trampa que ya nos costo una medicion entera: una consulta que
    devuelve menos de lo que hay no falla, contesta otra cosa.
    """
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


print("── handles de Instagram ──")
ig = todas("v_ig_senales_current",
           "?select=realtor_id,handle,estado_perfil,handle_confianza")
con_handle = {f["realtor_id"]: f for f in ig if (f.get("handle") or "").strip()}
print("   filas en la vista: %d · con handle: %d" % (len(ig), len(con_handle)))

print("── clase del perfil ──")
clases = {f["realtor_id"]: f for f in
          todas("v_ig_clase_actual", "?select=realtor_id,clase,handle")}

print("── realtors ──")
rs = {f["id"]: f for f in todas(
    "realtors",
    "?select=id,nombre_completo,brokerage,estado,condado_fips,licencia_numero,"
    "licencia_estado,email_principal,telefono_e164,unidades_ano,rango_volumen,"
    "sf_lead_id,es_cliente_de_la_casa")}
print("   realtors en la base: %d" % len(rs))

print("── contactos ──")
contactos: dict[str, list[dict]] = {}
for c in todas("contactos", "?select=realtor_id,canal,valor,fuente,vigente"):
    contactos.setdefault(c["realtor_id"], []).append(c)

lista = []
for rid, f in con_handle.items():
    r = rs.get(rid)
    if not r:
        continue
    cts = contactos.get(rid) or []
    # El email principal de la fila VA EN LA LISTA aunque no este en contactos:
    # es el que trajo MMI, y es la llave de desambiguacion mas fuerte.
    correos = {(r.get("email_principal") or "").strip().lower()} | {
        (c["valor"] or "").strip().lower() for c in cts
        if c.get("canal") == "email" and c.get("valor")}
    tels = {(r.get("telefono_e164") or "").strip()} | {
        (c["valor"] or "").strip() for c in cts
        if c.get("canal") in ("telefono", "phone", "celular") and c.get("valor")}
    lista.append({
        "realtor_id": rid,
        "nombre": r.get("nombre_completo"),
        # El brokerage VIEJO: es el patron contra el que se detecta el cambio.
        "brokerage_mmi": r.get("brokerage"),
        "estado_mmi": r.get("estado"),
        "condado_fips_mmi": r.get("condado_fips"),
        "licencia_mmi": r.get("licencia_numero"),
        "licencia_estado_mmi": r.get("licencia_estado"),
        "unidades_mmi": r.get("unidades_ano"),
        "rango_volumen_mmi": r.get("rango_volumen"),
        "sf_lead_id": r.get("sf_lead_id"),
        "emails_mmi": sorted(e for e in correos if e and "@" in e),
        "telefonos_mmi": sorted(t for t in tels if t),
        "handle": f.get("handle"),
        "estado_perfil": f.get("estado_perfil"),
        "clase_ig": (clases.get(rid) or {}).get("clase"),
    })

lista.sort(key=lambda x: (x["nombre"] or "").upper())

os.makedirs(SALIDA, exist_ok=True)
ruta = os.path.join(SALIDA, "realtors_con_ig.json")
with open(ruta, "w", encoding="utf-8") as fh:
    json.dump(lista, fh, ensure_ascii=False, indent=1)

con_email = sum(1 for x in lista if x["emails_mmi"])
con_tel = sum(1 for x in lista if x["telefonos_mmi"])
con_lic = sum(1 for x in lista if x["licencia_mmi"])
con_est = sum(1 for x in lista if x["estado_mmi"])

print("")
print("TOTAL con handle de Instagram: %d" % len(lista))
print("   con email  : %d  (%.0f%%)" % (con_email, 100.0 * con_email / max(1, len(lista))))
print("   con telefono: %d  (%.0f%%)" % (con_tel, 100.0 * con_tel / max(1, len(lista))))
print("   con licencia: %d  (%.0f%%)" % (con_lic, 100.0 * con_lic / max(1, len(lista))))
print("   con estado  : %d  (%.0f%%)" % (con_est, 100.0 * con_est / max(1, len(lista))))
print("")
print("guardado en %s" % ruta)
