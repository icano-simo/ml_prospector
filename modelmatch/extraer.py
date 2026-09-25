"""Los 298 realtors con Instagram, buscados en Model Match.

Reglas que vienen del pedido y que el codigo hace cumplir, no recuerda:

  · **Tope de 5 creditos por realtor.** Se cuenta con el modelo MEDIDO
    (detalle = 1, breakdown = 1 por fila) y se comprueba ANTES de pedir cada
    breakdown, no despues. El detalle trae `totalLendersWorkedWith` y sus
    hermanos, que SON el numero de filas de cada breakdown: por eso el costo
    se sabe antes de gastarlo.
  · **Desambiguar con el correo o el telefono que ya teniamos.** El nombre
    solo no decide: buscando el email de Ana Osorio salen cinco candidatas,
    dos de ellas «ana osorio de vega». El criterio y la confianza quedan
    escritos en la salida, y los candidatos descartados tambien.
  · **Todos los correos y todos los telefonos.** Model Match mete varios en un
    mismo campo separados por `;`, y el detalle trae mas en `linkedProfiles`.
  · **El cambio de compañia se registra.** Lo de MMI es viejo; se guardan el
    brokerage viejo, el de Model Match y si cambiaron.
  · **Reanudable.** Cada realtor se guarda apenas termina. Volver a correr no
    re-paga lo ya hecho: es la unica proteccion real contra un corte a mitad.

Uso:
    python modelmatch/extraer.py            # todos los pendientes
    python modelmatch/extraer.py --limite 5 # una prueba corta
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from modelmatch.cliente import llamar, resumen, saldo  # noqa: E402

TRABAJO = os.path.join(RAIZ, "data", "trabajo")
ENTRADA = os.path.join(TRABAJO, "realtors_con_ig.json")
SALIDA = os.path.join(TRABAJO, "mm_por_realtor")

#: Tope duro por realtor, del pedido. El codigo no lo pasa ni por un credito.
TOPE_POR_REALTOR = 5
#: Orden de valor de los breakdowns: quien lo financia primero, porque es lo
#: que decide la exclusion por no-canibalizacion y lo que se usa en el pitch.
BREAKDOWNS = (("lenders", "totalLendersWorkedWith"),
              ("originators", "totalOriginatorsWorkedWith"),
              ("companies", "totalCompaniesWorkedWith"))


def normalizar(s) -> str:
    """Minusculas, sin tildes, sin puntuacion, espacios colapsados."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


def solo_digitos(s) -> str:
    d = re.sub(r"\D", "", str(s or ""))
    # E.164 de EE.UU.: +1XXXXXXXXXX -> XXXXXXXXXX, para comparar con MM.
    return d[1:] if len(d) == 11 and d.startswith("1") else d


def correos_de(valor) -> list[str]:
    """Model Match mete VARIOS correos en un campo, separados por `;`."""
    return [e.strip().lower() for e in re.split(r"[;,]", str(valor or ""))
            if "@" in e]


def buscar(texto: str) -> list[dict]:
    """instant-search. Cero creditos (medido)."""
    d = llamar("/v1/instant-search", {"query": texto},
               etiqueta="is_%s" % normalizar(texto).replace(" ", "_")[:40],
               silencioso=True)
    return ((d or {}).get("results") or {}).get("agents") or []


def elegir(candidatos: list[dict], r: dict) -> tuple[dict | None, str, str]:
    """El candidato, el criterio y la confianza. Sin adivinar.

    El orden es el del pedido: primero el correo, despues el resto. El
    telefono no se puede usar aqui --instant-search no lo trae-- asi que se
    comprueba DESPUES, contra el detalle, y queda anotado si coincidio.
    """
    mios = {e.lower() for e in (r.get("emails_mmi") or [])}
    unicos: dict[str, dict] = {}
    for c in candidatos:
        if c.get("id"):
            unicos.setdefault(c["id"], c)
    cands = list(unicos.values())

    # 1 · el correo, que es llave dura.
    por_correo = [c for c in cands if mios & set(correos_de(c.get("email")))]
    if len(por_correo) == 1:
        return por_correo[0], "email_exacto", "alta"
    if len(por_correo) > 1:
        # Varios perfiles con el mismo correo: es el caso de perfiles
        # duplicados de MM. Gana el de mas volumen, y queda dicho.
        mejor = max(por_correo, key=lambda c: c.get("volume") or 0)
        return mejor, "email_exacto_varios_perfiles", "alta"

    # 2 · nombre normalizado igual Y estado igual.
    nom, est = normalizar(r.get("nombre")), (r.get("estado_mmi") or "").upper()
    exactos = [c for c in cands if normalizar(c.get("fullName")) == nom]
    con_estado = [c for c in exactos
                  if (c.get("state") or "").upper() == est]
    if len(con_estado) == 1:
        return con_estado[0], "nombre_exacto_y_estado", "media"
    if len(con_estado) > 1:
        mejor = max(con_estado, key=lambda c: c.get("volume") or 0)
        return mejor, "nombre_y_estado_varios", "baja"
    if len(exactos) == 1:
        return exactos[0], "nombre_exacto_sin_estado", "baja"

    return None, ("sin_candidatos" if not cands else "ambiguo"), "ninguna"


def extraer(r: dict) -> dict:
    """Un realtor. Nunca pasa de TOPE_POR_REALTOR creditos."""
    fila: dict = {
        "realtor_id": r["realtor_id"], "nombre": r["nombre"],
        "handle": r["handle"], "clase_ig": r.get("clase_ig"),
        "emails_mmi": r.get("emails_mmi"), "telefonos_mmi": r.get("telefonos_mmi"),
        "brokerage_mmi": r.get("brokerage_mmi"), "estado_mmi": r.get("estado_mmi"),
        "unidades_mmi": r.get("unidades_mmi"),
        "rango_volumen_mmi": r.get("rango_volumen_mmi"),
        "sf_lead_id": r.get("sf_lead_id"),
        "creditos_gastados": 0, "consultado_en": None,
    }

    # ── nivel 0 · encontrarlo. Cero creditos. ───────────────────────────────
    candidatos: list[dict] = []
    for email in (r.get("emails_mmi") or [])[:2]:
        candidatos += buscar(email)
    elegido, criterio, confianza = elegir(candidatos, r)
    if elegido is None and r.get("nombre"):
        # Solo si el correo no resolvio: cada busqueda es gratis pero lenta.
        candidatos += buscar(r["nombre"])
        elegido, criterio, confianza = elegir(candidatos, r)

    fila["match_criterio"] = criterio
    fila["match_confianza"] = confianza
    fila["candidatos_n"] = len({c.get("id") for c in candidatos if c.get("id")})
    # Los descartados quedan escritos: sin esto, «no encontrado» y «habia tres
    # y ninguno convencia» se leen igual.
    fila["candidatos"] = [
        {"id": c.get("id"), "nombre": c.get("fullName"),
         "email": c.get("email"), "office": c.get("office"),
         "ciudad": c.get("city"), "estado": c.get("state"),
         "volumen": c.get("volume")}
        for c in {c.get("id"): c for c in candidatos if c.get("id")}.values()]

    if elegido is None:
        fila["encontrado"] = False
        return fila

    fila["encontrado"] = True
    fila["mm_id"] = elegido.get("id")

    # ── nivel 1 · el detalle. 1 credito. ────────────────────────────────────
    det = llamar("/v1/agents/%s" % elegido["id"],
                 etiqueta="det_%s" % elegido["id"], silencioso=True)
    if not det or not isinstance(det.get("data"), dict):
        fila["error"] = "el detalle no respondio"
        return fila
    a = det["data"]
    fila["creditos_gastados"] = 1
    s = a.get("scored") or {}

    # Todos los correos y todos los telefonos, de todas partes.
    correos = set(correos_de(a.get("email")))
    telefonos = {solo_digitos(a.get("phone"))} - {""}
    enlazados = a.get("linkedProfiles") or []
    for p in enlazados:
        correos |= set(correos_de(p.get("email")))
        for t in (p.get("phone"), p.get("officePhone")):
            if solo_digitos(t):
                telefonos.add(solo_digitos(t))

    mios_tel = {solo_digitos(t) for t in (r.get("telefonos_mmi") or [])} - {""}
    fila.update({
        "mm_nombre": a.get("fullName"),
        "mm_emails": sorted(correos),
        "mm_telefonos": sorted(telefonos),
        "mm_brokerage": a.get("office"),
        "mm_ciudad": a.get("city"),
        "mm_estado": a.get("state"),
        "mm_zip": a.get("zip"),
        "mm_licencia": a.get("licenseNumber"),
        "mm_lat": (a.get("_geo") or {}).get("lat"),
        "mm_lng": (a.get("_geo") or {}).get("lng"),
        "mm_perfiles_enlazados": a.get("linkedProfileCount") or len(enlazados),
        # Produccion
        "mm_unidades": a.get("units"), "mm_volumen": a.get("volume"),
        "mm_precio_medio": a.get("avgSoldPrice"),
        "mm_compras_u": a.get("buyerUnits"), "mm_compras_v": a.get("buyerVolume"),
        "mm_ventas_u": a.get("sellerUnits"), "mm_ventas_v": a.get("sellerVolume"),
        "mm_dual_u": a.get("dualUnits"), "mm_dual_v": a.get("dualVolume"),
        # El subconjunto FINANCIADO, que a mano no teniamos
        "mm_compras_financiadas_u": s.get("total_mortgaged_buyer_units"),
        "mm_compras_financiadas_v": s.get("total_mortgaged_buyer_volume"),
        "mm_ventas_financiadas_u": s.get("total_mortgaged_listing_units"),
        "mm_pct_unidades_financiadas": s.get("total_percent_units_mortgaged"),
        "mm_pct_volumen_financiado": s.get("total_percent_volume_mortgaged"),
        "mm_loan_medio": s.get("average_mortgaged_loan_amount"),
        # Red
        "mm_lenders_n": a.get("totalLendersWorkedWith"),
        "mm_originadores_n": a.get("totalOriginatorsWorkedWith"),
        "mm_companias_n": a.get("totalCompaniesWorkedWith"),
        # Las dos comprobaciones que pidio el pedido
        "telefono_coincide": (
            "sin_dato" if not (mios_tel and telefonos)
            else ("si" if mios_tel & telefonos else "no")),
        "cambio_de_brokerage": (
            "sin_dato" if not (r.get("brokerage_mmi") and a.get("office"))
            else ("no" if normalizar(r["brokerage_mmi"])[:12]
                  == normalizar(a["office"])[:12] else "si")),
    })

    # ── nivel 2 · los breakdowns que QUEPAN en lo que sobra. ────────────────
    # `totalXWorkedWith` es el numero de filas, y el breakdown cuesta 1 por
    # fila: por eso se puede decidir sin gastar.
    for nombre, clave_n in BREAKDOWNS:
        filas_n = a.get(clave_n) or 0
        resto = TOPE_POR_REALTOR - fila["creditos_gastados"]
        if not filas_n:
            fila["mm_%s" % nombre] = []
            continue
        if filas_n > resto:
            fila["mm_%s" % nombre] = None      # None = no consultado
            fila["mm_%s_motivo" % nombre] = (
                "%d filas y quedaban %d creditos del tope" % (filas_n, resto))
            continue
        d = llamar("/v1/agents/%s/breakdowns/%s" % (elegido["id"], nombre), {},
                   etiqueta="bd_%s_%s" % (nombre, elegido["id"]),
                   silencioso=True)
        obtenidas = (d or {}).get("data") or []
        fila["mm_%s" % nombre] = [
            {"nombre": x.get("label"), "unidades": x.get("units"),
             "volumen": x.get("volume"), "pct_unidades": x.get("pctUnits"),
             "pct_volumen": x.get("pctVolume")} for x in obtenidas]
        fila["creditos_gastados"] += len(obtenidas)

    return fila


def main() -> None:
    limite = None
    if "--limite" in sys.argv:
        limite = int(sys.argv[sys.argv.index("--limite") + 1])

    with open(ENTRADA, encoding="utf-8") as fh:
        lista = json.load(fh)
    os.makedirs(SALIDA, exist_ok=True)

    hechos = {a[:-5] for a in os.listdir(SALIDA) if a.endswith(".json")}
    pendientes = [r for r in lista if r["realtor_id"] not in hechos]
    if limite:
        pendientes = pendientes[:limite]

    s0 = saldo()
    print("realtors con Instagram: %d · ya hechos: %d · a consultar: %d"
          % (len(lista), len(hechos), len(pendientes)))
    print("saldo al empezar: %s creditos · tope %d por realtor"
          % (s0, TOPE_POR_REALTOR))
    print("")

    gasto_previsto = 0
    for i, r in enumerate(pendientes, 1):
        try:
            fila = extraer(r)
        except Exception as exc:  # noqa: BLE001
            print("%4d/%d  %-30s ERROR %s"
                  % (i, len(pendientes), (r["nombre"] or "")[:30], str(exc)[:60]))
            continue
        import datetime as dt
        fila["consultado_en"] = dt.datetime.now(dt.timezone.utc).isoformat()
        with open(os.path.join(SALIDA, "%s.json" % r["realtor_id"]), "w",
                  encoding="utf-8") as fh:
            json.dump(fila, fh, ensure_ascii=False, indent=1)
        gasto_previsto += fila["creditos_gastados"]

        marca = ("ok " if fila.get("encontrado") else "NO ")
        print("%4d/%d  %s %-28s %-22s %-5s %2dc  %s"
              % (i, len(pendientes), marca, (r["nombre"] or "")[:28],
                 fila.get("match_criterio", ""), fila.get("match_confianza", ""),
                 fila["creditos_gastados"],
                 ("cambio de casa" if fila.get("cambio_de_brokerage") == "si"
                  else "")))

        # Conciliar con el ledger cada 25, no cada llamada.
        if i % 25 == 0:
            real = saldo()
            print("      ── ledger: saldo %s · previsto gastado %d · real %s"
                  % (real, gasto_previsto,
                     "?" if None in (s0, real) else round(s0 - real, 2)))

    s1 = saldo()
    resumen()
    print("")
    print("gasto previsto por el modelo: %d creditos" % gasto_previsto)
    print("gasto REAL segun el ledger  : %s"
          % ("?" if None in (s0, s1) else round(s0 - s1, 2)))
    print("saldo: %s  (era %s)" % (s1, s0))


if __name__ == "__main__":
    main()
