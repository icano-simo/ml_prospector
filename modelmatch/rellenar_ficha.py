"""Saca de la ficha YA PAGADA los campos que estabamos tirando. 0 llamadas.

La pasada campo por campo mostro que la ficha trae mas de lo que llevabamos al
Excel. Nada de esto necesita una llamada nueva: el crudo esta en `data/raw/`
desde que se compro, y se vuelve a leer de ahi.

Dos familias:

  · lo que la ficha trae y no usabamos: la fecha de la ultima operacion, las
    licencias multi-estado con su vencimiento, la suma de precios de listado
    y los volumenes de dual y de ventas financiadas;
  · lo que es ARITMETICA de lo que ya traiamos: los precios medios por lado.
    Se comprobo numero a numero contra `scored` que el cociente coincide, asi
    que se calculan en vez de guardarse dos veces.

Uso:
    python modelmatch/rellenar_ficha.py
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
CRUDO = os.path.join(RAIZ, "data", "raw")


def cruda(mm: str) -> dict:
    """La ficha guardada de ese agente. None si no esta."""
    for a in sorted(glob.glob(os.path.join(CRUDO, "mm_det_%s_*.json" % mm)),
                    reverse=True):
        try:
            with open(a, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(d.get("data"), dict):
            return d["data"]
    # La de la fase 1 no lleva el id en el nombre.
    for a in sorted(glob.glob(os.path.join(CRUDO, "mm_agent_detalle_*.json")),
                    reverse=True):
        with open(a, encoding="utf-8") as fh:
            d = json.load(fh)
        if (d.get("data") or {}).get("id") == mm:
            return d["data"]
    return {}


def fecha(ms) -> str:
    """Epoch en milisegundos -> fecha ISO. '' si no hay.

    La API da un INSTANTE, no una fecha, asi que pasarlo a dia obliga a elegir
    zona. Se elige UTC a proposito: los sellos vienen a las 06:00 UTC --la
    medianoche del centro de EEUU-- asi que en UTC sale el dia calendario que
    la fuente quiso decir, y sale el MISMO en cualquier maquina. Con la hora
    local, una maquina al este de Greenwich daria el dia siguiente.
    """
    if not isinstance(ms, (int, float)) or ms <= 0:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date().isoformat()


def fecha_licencia(s) -> str:
    """`MM/DD/AAAA` -> `AAAA-MM-DD`. '' si no se puede leer.

    Las licencias NO vienen en ISO, vienen en el formato de EEUU, y eso rompia
    el orden en silencio: `sorted()` sobre texto pone `03/31/2027` antes que
    `09/30/2025`, asi que «el vencimiento mas proximo» daba el mas LEJANO.
    Pasa en pocas fichas --las que tienen dos licencias con meses cruzados--
    y por eso nadie lo veia.
    """
    if not isinstance(s, str):
        return ""
    partes = s.strip().split("/")
    if len(partes) != 3:
        return ""
    try:
        return dt.date(int(partes[2]), int(partes[0]),
                       int(partes[1])).isoformat()
    except ValueError:
        return ""


def cociente(a, b):
    """a/b redondeado, o '' si falta alguno o el divisor es 0.

    Vacio y cero no son lo mismo: sin unidades no hay precio medio, y escribir
    0 afirmaria que las casas valian cero.
    """
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return ""
    return round(a / b) if b else ""


def main() -> None:
    tocados = 0
    sin_crudo = []
    for ruta in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(ruta, encoding="utf-8") as fh:
            f = json.load(fh)
        mm = f.get("mm_id")
        if not mm:
            continue
        det = cruda(mm)
        if not det:
            sin_crudo.append(f.get("nombre"))
            continue
        s = det.get("scored") or {}

        # ── lo que la ficha trae y no usabamos ─────────────────────────────
        f["mm_ultima_operacion"] = fecha(s.get("LastTransactionDate"))
        lic = det.get("licenses") or []
        # Todas las fechas en ISO, tambien dentro del texto largo: dos
        # formatos en la misma columna es como se lee mal un dia por un mes.
        f["mm_licencias"] = " · ".join(
            "%s (%s%s)" % (x.get("number"), x.get("state"),
                           ", vence %s" % fecha_licencia(x["expirationDate"])
                           if fecha_licencia(x.get("expirationDate")) else "")
            for x in sorted(lic, key=lambda y: str(y.get("number") or ""))
            if x.get("number"))
        vences = sorted(v for v in (fecha_licencia(x.get("expirationDate"))
                                    for x in lic) if v)
        # El MAS LEJANO, no el mas proximo: la pregunta util es «hasta cuando
        # consta habilitado». Con 182 de 288 fichas enteramente vencidas, el
        # minimo devolvia la fecha mas vieja, que no responde nada. Quien
        # necesite el detalle lo tiene en `Licencias (todas)`.
        f["mm_licencia_vence"] = vences[-1] if vences else ""
        f["mm_estados_licencia"] = " · ".join(
            sorted({x.get("state") for x in lic if x.get("state")}))
        f["mm_dual_v"] = det.get("dualVolume")
        f["mm_ventas_financiadas_v"] = s.get("total_mortgaged_listing_volume")
        f["mm_dual_financiadas_u"] = s.get("total_mortgaged_dual_units")
        f["mm_dual_financiadas_v"] = s.get("total_mortgaged_dual_volume")
        f["mm_total_listado"] = s.get("total_list_price")

        # ── aritmetica de lo que ya traiamos ───────────────────────────────
        f["mm_precio_medio_compras"] = cociente(
            det.get("buyerVolume"), det.get("buyerUnits"))
        f["mm_precio_medio_compras_fin"] = cociente(
            s.get("total_mortgaged_buyer_volume"),
            s.get("total_mortgaged_buyer_units"))
        f["mm_precio_medio_listings"] = cociente(
            det.get("sellerVolume"), det.get("sellerUnits"))
        venta, listado = s.get("total_sale_price"), s.get("total_list_price")
        f["mm_venta_vs_listado"] = (
            round(100.0 * venta / listado, 1)
            if isinstance(venta, (int, float))
            and isinstance(listado, (int, float)) and listado else "")

        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(f, fh, ensure_ascii=False, indent=1)
        tocados += 1

    print("registros rellenados: %d" % tocados)
    if sin_crudo:
        print("sin ficha cruda en disco: %d" % len(sin_crudo))
        print("   (son los que se extrajeron antes de guardar el crudo con "
              "el id en el nombre; su ficha habria que volver a comprarla)")


if __name__ == "__main__":
    main()
