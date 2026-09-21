"""Genera la lista de condados a capturar en Market Signals.

Que resuelve
------------
El Bloque 5 pide capturar "los 15-25 condados donde tenemos loan officers con
licencia activa". Las licencias NMLS son por ESTADO, no por condado, asi que la
lista no sale de un solo archivo: hay que cruzar dos.

    Loan_Officers_Licencias.xlsx    ->  que estados podemos originar
    census_latinos_estados_counties ->  donde esta el mercado latino

Y hay una distincion que cambia la lista entera: **la licencia multiestado no es
capacidad.** Un loan officer licenciado en 35 estados da cobertura para no
rechazar un caso, no capacidad para sostener una plaza. Siguiendo la referencia
09 de la skill, un LO cuenta como "local" solo si esta licenciado en 5 estados o
menos, y un estado cuya unica cobertura viene de multiestado se marca
COBERTURA NOMINAL, no "cubierto".

Uso
---
    python -m modelmatch.lista_de_captura --top 25
    python -m modelmatch.lista_de_captura --top 25 --salida docs/condados.csv

Despues hay que adjuntar los FIPS, que el parser exige:

    python -m geo.fips --adjuntar docs/condados.csv --salida docs/condados_fips.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

#: Umbral de la referencia 09: licenciado en 5 estados o menos = capacidad local.
MAX_ESTADOS_PARA_SER_LOCAL = 5

NOMBRE_A_COD = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT",
    "Delaware": "DE", "District of Columbia": "DC", "Florida": "FL",
    "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY",
    "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH",
    "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Puerto Rico": "PR", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


def _num(valor) -> float | None:
    if valor is None:
        return None
    try:
        return float(str(valor).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _hoja_a_dicts(ws, fila_encabezado: int) -> list[dict]:
    todas = list(ws.iter_rows(values_only=True))
    if len(todas) < fila_encabezado:
        return []
    enc = ["" if c is None else str(c).strip() for c in todas[fila_encabezado - 1]]
    salida = []
    for fila in todas[fila_encabezado:]:
        if all(c is None or str(c).strip() == "" for c in fila):
            continue
        salida.append({
            enc[i]: fila[i]
            for i in range(min(len(enc), len(fila)))
            if enc[i]
        })
    return salida


def cobertura_por_estado(ruta_los: Path) -> dict[str, dict]:
    """{estado: {activos, locales, etiqueta, multiestado}} desde el board.

    La autoridad sobre quien trabaja aca es HR y sobre quien esta licenciado es
    NMLS. Este board es una aproximacion operativa: sirve para dimensionar, no
    para afirmar.
    """
    import openpyxl

    wb = openpyxl.load_workbook(ruta_los, read_only=True, data_only=True)
    if "Licencias (largo)" not in wb.sheetnames:
        raise SystemExit(
            "%s no tiene la hoja 'Licencias (largo)'. Hojas: %s"
            % (ruta_los, wb.sheetnames)
        )
    registros = _hoja_a_dicts(wb["Licencias (largo)"], fila_encabezado=3)
    wb.close()

    estados_por_persona: dict[str, set[str]] = {}
    status: dict[str, str] = {}
    defectuosos: list[str] = []

    for r in registros:
        if str(r.get("Es Loan Officer") or "").strip().lower() != "true":
            continue
        codigo = r.get("person_code")
        estado = r.get("Estado (cod)")
        if not codigo:
            continue
        if not estado or not str(estado).strip():
            defectuosos.append(str(codigo))
            continue
        estados_por_persona.setdefault(str(codigo), set()).add(str(estado).strip().upper())
        status[str(codigo)] = str(r.get("Status (board)") or "").strip()

    salida: dict[str, dict] = {}
    for codigo, estados in estados_por_persona.items():
        if status.get(codigo, "").lower() != "active":
            continue
        es_local = len(estados) <= MAX_ESTADOS_PARA_SER_LOCAL
        for e in estados:
            entrada = salida.setdefault(e, {"activos": 0, "locales": 0, "personas": []})
            entrada["activos"] += 1
            entrada["personas"].append(codigo)
            if es_local:
                entrada["locales"] += 1

    for e, d in salida.items():
        d["etiqueta"] = _etiqueta_cobertura(d["activos"], d["locales"])

    if defectuosos:
        # Los registros con licencia defectuosa no suman en ninguna columna.
        # La referencia 09 pide declararlos: si dos personas desaparecen del
        # conteo, alguien tiene que saberlo.
        salida["__defectuosos__"] = {  # type: ignore[assignment]
            "activos": 0, "locales": 0, "etiqueta": "N/A",
            "personas": sorted(set(defectuosos)),
        }
    return salida


def _etiqueta_cobertura(activos: int, locales: int) -> str:
    if activos == 0:
        return "SIN COBERTURA ACTIVA"
    if locales == 0:
        return "COBERTURA NOMINAL"
    if activos <= 2:
        return "COBERTURA DELGADA"
    if activos <= 5:
        return "COBERTURA MEDIA"
    return "COBERTURA SUFICIENTE"


def condados_latinos(ruta_censo: Path) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(ruta_censo, read_only=True, data_only=True)
    if "Counties" not in wb.sheetnames:
        raise SystemExit(
            "%s no tiene la hoja 'Counties'. Hojas: %s" % (ruta_censo, wb.sheetnames)
        )
    registros = _hoja_a_dicts(wb["Counties"], fila_encabezado=1)
    wb.close()

    sin_mapear: set[str] = set()
    filas = []
    for r in registros:
        nombre_estado = str(r.get("Estado") or "").strip()
        cod = NOMBRE_A_COD.get(nombre_estado)
        if cod is None:
            if nombre_estado:
                sin_mapear.add(nombre_estado)
            continue
        latinos = _num(r.get("Poblacion latina 2024"))
        filas.append({
            "estado": cod,
            "condado": str(r.get("County") or "").strip(),
            "poblacion_total": _num(r.get("Poblacion total 2024")),
            "latinos": latinos,
            "pct_latino": _num(r.get("% latino 2024")),
            "crecimiento_2010_2024": _num(r.get("Cambio %")),
        })
    if sin_mapear:
        print("AVISO: nombres de estado sin mapear, excluidos: %s"
              % sorted(sin_mapear), file=sys.stderr)
    return filas


def _es_region_de_planificacion(nombre: str) -> bool:
    """Connecticut reemplazo sus condados por regiones de planificacion en 2022."""
    return "planning region" in unicodedata.normalize("NFKD", nombre).lower()


def construir(
    ruta_los: Path,
    ruta_censo: Path,
    *,
    top: int = 25,
    incluir_nominales: bool = False,
) -> tuple[list[dict], dict[str, dict]]:
    cobertura = cobertura_por_estado(ruta_los)
    condados = condados_latinos(ruta_censo)

    con_capacidad = {
        e: d for e, d in cobertura.items()
        if e != "__defectuosos__" and (d["locales"] > 0 or incluir_nominales)
    }

    filas = []
    for c in condados:
        cob = con_capacidad.get(c["estado"])
        if cob is None:
            continue
        filas.append({
            **c,
            "los_activos": cob["activos"],
            "los_locales": cob["locales"],
            "etiqueta_cobertura": cob["etiqueta"],
            "nota": ("region de planificacion, no condado"
                     if _es_region_de_planificacion(c["condado"]) else ""),
        })

    # Prioridad: poblacion latina absoluta. No es el unico criterio posible,
    # pero es el unico defendible con los datos que hay hoy: no tenemos el
    # condado de operacion de nuestros realtors hasta que Model Match lo de.
    filas.sort(key=lambda d: -(d["latinos"] or 0))
    return filas[:top], cobertura


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--salida", type=Path, default=None)
    ap.add_argument("--incluir-nominales", action="store_true",
                    help="incluye estados con cobertura solo nominal (0 LOs locales)")
    ap.add_argument("--entrada-los", type=Path,
                    default=RAIZ / "Data_inputIA" / "Loan_Officers_Licencias.xlsx")
    ap.add_argument("--entrada-censo", type=Path,
                    default=RAIZ / "Data_inputIA" / "census_latinos_estados_counties.xlsx")
    args = ap.parse_args(argv)

    for ruta in (args.entrada_los, args.entrada_censo):
        if not ruta.exists():
            print("No encuentro %s" % ruta, file=sys.stderr)
            return 1

    filas, cobertura = construir(
        args.entrada_los, args.entrada_censo,
        top=args.top, incluir_nominales=args.incluir_nominales,
    )

    print("COBERTURA DE LOAN OFFICERS POR ESTADO")
    print("%-5s %8s %8s  %s" % ("est", "activos", "locales", "etiqueta"))
    for e in sorted((k for k in cobertura if k != "__defectuosos__"),
                    key=lambda k: (-cobertura[k]["activos"], k)):
        d = cobertura[e]
        print("%-5s %8d %8d  %s" % (e, d["activos"], d["locales"], d["etiqueta"]))

    defect = cobertura.get("__defectuosos__")
    if defect and defect["personas"]:
        print("")
        print("REGISTROS CON LICENCIA DEFECTUOSA (no suman en ninguna columna):")
        print("   %s" % ", ".join(defect["personas"]))

    nominales = sorted(e for e, d in cobertura.items()
                       if e != "__defectuosos__" and d["locales"] == 0)
    if nominales:
        print("")
        print("SOLO COBERTURA NOMINAL (0 LOs licenciados en <=5 estados): %s"
              % ", ".join(nominales))
        print("Un estado cubierto solo por un LO multiestado esta vacio en la")
        print("practica. No se capturan sus condados salvo con --incluir-nominales.")

    print("")
    print("LISTA DE CAPTURA · top %d" % args.top)
    print("%-5s %-32s %12s %7s %5s %5s" % ("est", "condado", "latinos", "%lat", "act", "loc"))
    for d in filas:
        print("%-5s %-32s %12s %6s%% %5d %5d" % (
            d["estado"], d["condado"][:32],
            format(int(d["latinos"]), ",") if d["latinos"] else "?",
            ("%.1f" % (d["pct_latino"] * 100)) if d["pct_latino"] else "?",
            d["los_activos"], d["los_locales"],
        ))

    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        campos = ["estado", "condado", "poblacion_total", "latinos", "pct_latino",
                  "crecimiento_2010_2024", "los_activos", "los_locales",
                  "etiqueta_cobertura", "nota"]
        with args.salida.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=campos)
            w.writeheader()
            for d in filas:
                w.writerow({k: d.get(k) for k in campos})
        print("")
        print("Escrito: %s" % args.salida)
        print("")
        print("FALTA EL FIPS, y el parser de capturas lo exige:")
        print("   python -m geo.fips --adjuntar %s --salida %s"
              % (args.salida, args.salida.with_name(args.salida.stem + "_fips.csv")))

    return 0


if __name__ == "__main__":
    sys.exit(_main())
