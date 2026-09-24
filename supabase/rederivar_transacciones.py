"""Vuelve a derivar el LADO de las operaciones ya guardadas, desde su crudo.

    python supabase/rederivar_transacciones.py            # solo mide
    python supabase/rederivar_transacciones.py --aplicar

Por qué se puede, y por qué esto es la mitad que importa
--------------------------------------------------------
El crudo redactado conserva las columnas de agente: se redactan la calle y los
nombres de compradores y vendedores, no los agentes. Así que el lado se puede
volver a calcular sin pedirle a nadie que vuelva a pegar nada.

Es la arquitectura que el proyecto tiene desde el principio --el crudo es la
fuente y la derivación es libre de repetirse-- ejerciéndose. Cuando el parser
se equivocó con el nombre, el costo fue correr esto, no 37 capturas.

Lo que arregla: el lado se buscaba con el nombre de `pacs.realtors` y no con el
de la captura. «XOCHIL ESCOBAR» contra «Xochil Wendy Escobar»: 37 operaciones
sin lado, y sin que nada fallara, porque «sin lado» es un estado legítimo.
"""
from __future__ import annotations

import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "api"))

from _comun import actualizar, leer  # noqa: E402
from supabase.config import cargar_env  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cargar_env()
    from captura.transacciones import parsear_transacciones

    aplicar = "--aplicar" in sys.argv

    cod, caps, _ = leer(
        "v_capturas_modelmatch_current",
        "?select=id,realtor_id,texto_crudo,parseado,capturado_en"
        "&parseado->>seccion=eq.transacciones&limit=500")
    if cod >= 400:
        print("no se pudieron leer las capturas: %s" % str(caps)[:200])
        return 1
    print("capturas de Transactions vivas: %d" % len(caps or []))

    ids = sorted({c["realtor_id"] for c in (caps or []) if c.get("realtor_id")})
    nombres = {}
    if ids:
        _c, rs, _ = leer("realtors", "?select=id,nombre_completo&id=in.(%s)"
                         % ",".join(ids))
        nombres = {r["id"]: r["nombre_completo"] for r in (rs or [])}

    # El nombre de la CAPTURA, que es el que manda. Sale del Overview del mismo
    # realtor, no del libro.
    _c, ovs, _ = leer(
        "v_capturas_modelmatch_current",
        "?select=realtor_id,parseado&parseado->>seccion=eq.overview&limit=500")
    nombre_mm = {}
    for o in ovs or []:
        n = ((o.get("parseado") or {}).get("perfil") or {}).get("nombre")
        if n and o.get("realtor_id"):
            nombre_mm.setdefault(o["realtor_id"], n)

    print("")
    cambios = []
    for c in caps or []:
        rid = c.get("realtor_id")
        antes = ((c.get("parseado") or {}).get("perfil") or {}
                 ).get("transacciones") or {}
        p = parsear_transacciones(c.get("texto_crudo") or "",
                                  realtor=nombre_mm.get(rid),
                                  capturado_en=c.get("capturado_en"))
        con_lado_antes = (antes.get("leidas") or 0) - (antes.get("sin_lado") or 0)
        con_lado = p["leidas"] - p["sin_lado"]
        marca = "=" if con_lado == con_lado_antes else "→"
        print("   %-26s %2d de %2d con lado  %s  %2d de %2d   %s"
              % ((nombres.get(rid) or "?")[:26], con_lado_antes,
                 antes.get("leidas") or 0, marca, con_lado, p["leidas"],
                 p.get("por_que_ese_nombre", "")[:46]))
        if con_lado != con_lado_antes or p["completa"] != antes.get("completa"):
            nuevo = dict(c.get("parseado") or {})
            perfil = dict(nuevo.get("perfil") or {})
            perfil["transacciones"] = p
            nuevo["perfil"] = perfil
            nuevo["rederivado_en"] = "lado desde el nombre de la captura"
            cambios.append({"id": c["id"], "parseado": nuevo})

    print("")
    print("capturas a rederivar: %d" % len(cambios))
    if not aplicar:
        print("(solo mide; pasar --aplicar para escribir)")
        return 0
    if not cambios:
        print("nada que cambiar.")
        return 0

    # Se actualiza el `parseado`, NUNCA el `texto_crudo`. El crudo es la fuente
    # y no se toca jamás: si esta derivación también sale mal, se vuelve a
    # correr sobre lo mismo.
    # PATCH y no POST. `escribir` hace INSERT, así que la primera versión
    # intentaba crear filas nuevas con solo `id` y `parseado` y chocaba contra
    # los NOT NULL -- que es el error correcto de la base ante una petición
    # equivocada, no un problema de la base.
    escritas = 0
    for ch in cambios:
        cod, det, _ = actualizar("capturas_modelmatch",
                                 "?id=eq.%s" % ch["id"],
                                 {"parseado": ch["parseado"]})
        if cod >= 400:
            print("   no se pudo actualizar %s: %s" % (ch["id"][:8],
                                                       str(det)[:120]))
            continue
        escritas += 1
    print("actualizadas: %d de %d" % (escritas, len(cambios)))
    print("")
    print("Ahora hay que regenerar los paquetes:")
    print("   python supabase/generar_paquetes.py --con-mm --guardar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
