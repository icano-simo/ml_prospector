"""¿CUANTO trabajaron con la casa? No es lo mismo una vez que veinte.

La columna «¿Ya financia con la casa?» dice si/no. Para decidir que se hace
con esos 79 hace falta el peso: una operacion hace tres años no es lo mismo
que veinte el año pasado, y hoy los dos se ven igual.

`footprint` con un lender EXPLICITO si admite umbrales con el significado que
uno espera. La guia lo dice literal: cada entrada nombra UNA relacion de
financiacion y los limites se cumplen DENTRO de ella, o sea
`{lender: CASA, units: {gte: 3}}` = «tres o mas de sus operaciones las
financio esa casa».

Es distinto del caso `product.shareOfUnits`, que mordio: ahi la dimension era
«cualquier lender» y el porcentaje se media dentro de un bucket suelto. Aca el
bucket es la casa, que es justo lo que se quiere medir.

Igual NO se da por bueno: se comprueba contra un testigo elegido solo, uno de
los realtors cuya tabla CRUDA de lenders nombra a la casa. Si tiene tres
unidades ahi, tiene que aparecer en los umbrales 1, 2 y 3 y desaparecer en el
5; si no cuadra, el script lo dice y avisa de no usar el numero.

Cuesta 1 por fila devuelta, y los umbrales altos devuelven pocas filas.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, saldo  # noqa: E402
from modelmatch.everett import CASA  # noqa: E402

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
EVERETT = os.path.join(RAIZ, "data", "trabajo", "everett.json")
SALIDA = os.path.join(RAIZ, "data", "trabajo", "everett_peso.json")

UMBRALES = (1, 2, 3, 5, 10, 20)
LOTE = 100

#: El testigo de la comprobacion NO se escribe a mano: se busca.
#:
#: Antes estaba puesto el nombre de un realtor y sus operaciones con la casa,
#: y este repo es PUBLICO: eso es publicar la relacion comercial de una
#: persona. Ahora se toma de los que tienen la tabla cruda de lenders --que
#: vive en `data/`, fuera de git-- y en el codigo no queda ningun nombre.
#: De paso el test deja de romperse cuando ese realtor cambia.
HUELE_A_CASA = re.compile(r"everett|evertt", re.IGNORECASE)


def buscar_testigo(nombre_de: dict) -> tuple[str, str, int] | None:
    """Un realtor con la casa en su tabla CRUDA, para contrastar el umbral.

    Devuelve (mm_id, nombre, unidades). El nombre solo se usa para imprimir
    en pantalla; no se guarda ni se versiona.
    """
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        f = json.load(open(a, encoding="utf-8"))
        for x in (f.get("mm_lenders") or []):
            if HUELE_A_CASA.search(str(x.get("nombre") or "")):
                return f["mm_id"], f.get("nombre"), x.get("unidades") or 0
    return None


def main() -> None:
    # Solo se preguntan los 79 que ya dieron positivo: preguntarle a los 273
    # pagaria filas de gente que sabemos que no trabaja con la casa.
    ids = [c["mm_id"] for c in json.load(open(EVERETT, encoding="utf-8"))]
    nombre_de = {}
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        f = json.load(open(a, encoding="utf-8"))
        if f.get("mm_id"):
            nombre_de[f["mm_id"]] = f.get("nombre")

    print("agentes con la casa: %d" % len(ids))
    s0 = saldo()
    print("saldo: %s" % s0)
    print("")

    por_umbral: dict[int, list[str]] = {}
    for u in UMBRALES:
        encontrados: list[str] = []
        for i in range(0, len(ids), LOTE):
            d = llamar("/v1/agents",
                       {"flatFilters": {"id": ids[i:i + LOTE]},
                        "footprint": {"lender": CASA, "units": {"gte": u}},
                        "period": "allTime", "pagination": {"size": 100}},
                       etiqueta="peso_%d_%d" % (u, i // LOTE), silencioso=True)
            encontrados += [f.get("id") for f in ((d or {}).get("data") or [])]
        por_umbral[u] = encontrados
        print("   %2d o mas operaciones con la casa: %3d" % (u, len(encontrados)))

    # ── la comprobacion, antes de creerle al numero ─────────────────────────
    testigo = buscar_testigo(nombre_de)
    print("")
    if testigo:
        testigo_id, testigo_nombre, testigo_u = testigo
        print("── testigo: %s, con %d unidades segun su tabla cruda"
              % (testigo_nombre, testigo_u))
        bien = True
        for u in UMBRALES:
            esta = testigo_id in por_umbral[u]
            debe = u <= testigo_u
            ok = esta == debe
            bien = bien and ok
            print("   umbral %-2d  esperado %-3s  medido %-3s  %s"
                  % (u, "si" if debe else "no", "si" if esta else "no",
                     "ok" if ok else "NO CUADRA"))
        print("   => el umbral %s"
              % ("significa lo que dice" if bien
                 else "NO es el numero de operaciones. NO USAR."))
    else:
        print("no se encontro el testigo; el resultado queda sin comprobar")

    # El tramo de cada uno: el umbral mas alto que pasa.
    peso = {}
    for mm_id in ids:
        alto = 0
        for u in UMBRALES:
            if mm_id in por_umbral[u]:
                alto = u
        peso[mm_id] = {"nombre": nombre_de.get(mm_id), "al_menos": alto}

    with open(SALIDA, "w", encoding="utf-8") as fh:
        json.dump({"umbrales": UMBRALES, "peso": peso}, fh,
                  ensure_ascii=False, indent=1)

    print("")
    print("── los de relacion mas fuerte con la casa ──")
    for mm_id, p in sorted(peso.items(), key=lambda kv: -kv[1]["al_menos"])[:15]:
        print("   %-28s al menos %2d operaciones" % (p["nombre"], p["al_menos"]))

    s1 = saldo()
    print("")
    print("costo: %s" % ("?" if None in (s0, s1) else round(s0 - s1)))
    print("guardado en %s" % SALIDA)


if __name__ == "__main__":
    main()
