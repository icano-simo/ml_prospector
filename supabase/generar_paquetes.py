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


def paquete_de(realtor_id: str) -> dict | None:
    """El paquete de un realtor, leyendo lo mismo que lee la ficha.

    Devuelve `None` si el realtor no existe. Un realtor sin Model Match SÍ
    tiene paquete: lo que le falta entra como `Pendiente` declarado, que es lo
    que permite que la IA escriba «esto no lo sabemos» en vez de callarlo.
    """
    import urllib.parse

    from api.rutas import CAMPOS_LISTA, _mercados_enlazados, capturas_que_mandan
    from api.ficha import contactos_por_canal
    from captura.parser_mm import unir_perfiles
    from captura.transacciones import resumen as resumen_tx
    from motor.paquete import construir
    from motor.veredicto import puede_contactarse

    rid = urllib.parse.quote(realtor_id)
    realtor = _uno("realtors", "?select=%s&id=eq.%s" % (CAMPOS_LISTA, rid))
    if not realtor:
        return None

    ev = _uno("v_evaluacion_actual",
              "?select=resultado,dolor_primario,veredicto_contacto,"
              "version_reglas,evaluado_en&realtor_id=eq.%s" % rid)

    crudas, _cuantas = capturas_que_mandan(realtor_id)
    perfiles, mercados = [], []
    for f in crudas or []:
        p = f.get("parseado") or {}
        if p.get("perfil"):
            perfiles.append(p["perfil"])
        if p.get("metricas"):
            mercados.append({"nivel": f.get("geografia_nivel"),
                             "estado": f.get("estado"),
                             "etiqueta": f.get("geografia_etiqueta"),
                             "metricas": p["metricas"],
                             "capturado_en": f.get("capturado_en")})
    mercados.extend(_mercados_enlazados(crudas))
    perfil = unir_perfiles(perfiles) if perfiles else {}
    tx = perfil.get("transacciones") if isinstance(perfil, dict) else None
    resumen = resumen_tx(tx) if (tx or {}).get("filas") else None

    sen = _uno("v_ig_senales_current",
               "?select=handle,estado_perfil,captions_n,comentarios_n,senales,"
               "capturado_en&realtor_id=eq.%s" % rid)
    cls = _uno("v_ig_clase_actual",
               "?select=clase,motivo,handle&realtor_id=eq.%s" % rid)
    ig = dict(sen) if sen else None
    if ig and cls:
        ig["clase_perfil"] = cls.get("clase")
        from ingest.instagram.clase_perfil import CLASES_UTILIZABLES
        ig["utilizable"] = (cls.get("clase") in CLASES_UTILIZABLES
                            and cls.get("clase") != "otro_perfil")

    _c, cts, _ = leer("contactos",
                      "?select=canal,valor,fuente&realtor_id=eq.%s" % rid)

    ver = (ev or {}).get("veredicto_contacto") or puede_contactarse(
        perfil or None).a_dict()

    return construir(
        realtor=realtor, evaluacion=ev, perfil_mm=perfil or None,
        resumen_tx=resumen, filas_tx=(tx or {}).get("filas"),
        mercados=mercados, ig=ig,
        contactos=contactos_por_canal(cts or []),
        census=None, veredicto=ver, salesforce=None)


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

    print("paquetes a generar: %d%s"
          % (len(ids), "" if guardar else "   ·   MIDE, NO ESCRIBE"))
    print("")
    filas = []
    for rid in ids:
        p = paquete_de(rid)
        if not p:
            print("   %s · no existe" % rid[:8])
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
    if not guardar:
        print("no se escribió nada. Pasá --guardar.")
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
