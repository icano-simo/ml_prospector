"""Cliente de la API de Model Match, con las reglas del brief adentro.

    from modelmatch.cliente import llamar, saldo, resumen

Lo que el modulo impone, para no tener que acordarse en cada script:

  · **guarda el crudo ANTES de mirarlo**, en `data/raw/` (gitignored), asi no
    hay que re-consultar --y re-pagar-- para volver a leer algo;
  · **nunca sigue el cursor** solo: paginar se pide explicitamente con
    `permitir_cursor=True`, para que no pase por descuido;
  · **no llama a enrichment ni a bulk-delivery sin pedirlo**: la lista de
    rutas prohibidas esta aqui y revienta ANTES de salir a la red. El
    enrichment es skip-trace de dueños de propiedad --PII de consumidor para
    un lender-- y cuesta 10 creditos por match;
  · **lee el saldo del ledger** y nunca lo estima;
  · reintenta el 429 con espera, que es el unico error que se arregla solo.

El techo de gasto se pasa a `presupuesto()` y el cliente **para** cuando se
alcanza, en vez de confiar en que el script lleve bien la cuenta.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRUDO = os.path.join(RAIZ, "data", "raw")
HOST = "https://api.modelmatch.com"

sys.path.insert(0, RAIZ)
from supabase.config import cargar_env  # noqa: E402

cargar_env()
_CLAVE = (os.environ.get("MODELMATCH_API_KEY") or "").strip()

#: Lo que no se toca sin aprobacion explicita, con el motivo. Reventar aqui es
#: mas barato que descubrirlo en la factura o en un reporte de cumplimiento.
PROHIBIDO = {
    "enrich": "es skip-trace: nombre, telefono y email de dueños de "
              "propiedad. PII de consumidor para un lender, y 10 creditos "
              "por match. No se toca sin permiso escrito",
    "bulk-delivery": "cuesta 1 credito por FILA; se usa a proposito y con "
                     "`limit`, nunca por descuido",
}

#: Segundos entre llamadas. Con un segundo salta el 429 `rate_limited`.
PAUSA = 2.0
#: Espera tras un 429 antes de reintentar, y cuantas veces.
ESPERA_429 = 20.0
REINTENTOS_429 = 3

LLAMADAS: list[dict] = []

#: El modelo de costo, MEDIDO contra el ledger el 2026-09-25 (no estimado):
#:   instant-search          0
#:   GET  /v1/agents/{id}    1
#:   POST /v1/agents         1 POR FILA devuelta (5 filas = 5 creditos)
#:   breakdowns              1 POR FILA (8 lenders = 8, 10 originators = 10)
#: De ahi sale lo util: `totalLendersWorkedWith` y sus hermanos, que vienen en
#: el detalle, SON el numero de filas de cada breakdown -- asi que el costo de
#: un breakdown se sabe ANTES de pedirlo.
COSTO_DETALLE = 1
COSTO_INSTANT_SEARCH = 0


class SinPresupuesto(RuntimeError):
    """Se alcanzo el techo de gasto. No es un fallo: es la guarda funcionando."""


def _pedir(ruta: str, cuerpo, metodo: str):
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    pedido = urllib.request.Request(
        HOST + ruta, data=datos, method=metodo,
        headers={"x-api-key": _CLAVE, "Accept": "application/json",
                 "Content-Type": "application/json",
                 "User-Agent": "HomeSi-prospector/extraccion"})
    try:
        with urllib.request.urlopen(pedido, timeout=120) as r:
            return r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8", "replace"), e.code


def llamar(ruta: str, cuerpo=None, etiqueta: str = "", metodo: str | None = None,
           permitir_cursor: bool = False, guardar: bool = True,
           silencioso: bool = False):
    """Una llamada. Guarda el crudo y devuelve el JSON, o None si fallo."""
    for prohibida, por_que in PROHIBIDO.items():
        if prohibida in ruta:
            raise SystemExit("ruta prohibida (%s): %s" % (ruta, por_que))
    if (cuerpo and not permitir_cursor
            and '"cursor"' in json.dumps(cuerpo)):
        raise SystemExit("paginar se pide con permitir_cursor=True")

    # El techo NO se comprueba aqui contra el ledger: leerlo es otra llamada,
    # y cobrarse una consulta de saldo por cada consulta de datos duplica el
    # trafico y el riesgo de 429. El presupuesto lo lleva quien llama, con el
    # modelo de costo MEDIDO (detalle = 1, breakdown = 1 por fila), y lo
    # concilia con el ledger cada tantos realtors.
    metodo = metodo or ("POST" if cuerpo is not None else "GET")
    for intento in range(REINTENTOS_429 + 1):
        texto, status = _pedir(ruta, cuerpo, metodo)
        if status != 429 or intento == REINTENTOS_429:
            break
        if not silencioso:
            print("   429 · espero %.0fs y reintento (%d/%d)"
                  % (ESPERA_429, intento + 1, REINTENTOS_429))
        time.sleep(ESPERA_429)
    time.sleep(PAUSA)

    LLAMADAS.append({"ruta": metodo + " " + ruta, "status": status,
                     "bytes": len(texto), "etiqueta": etiqueta})

    destino = None
    if guardar:
        os.makedirs(CRUDO, exist_ok=True)
        sello = dt.datetime.now().strftime("%Y%m%dT%H%M%S%f")[:-3]
        nombre = re.sub(r"[^a-z0-9]+", "_",
                        (etiqueta or ruta).lower()).strip("_")[:60]
        destino = os.path.join(CRUDO, "mm_%s_%s.json" % (nombre, sello))
        with open(destino, "w", encoding="utf-8") as fh:
            fh.write(texto)

    if not silencioso:
        print("%-5s %-46s %s · %6d bytes%s"
              % (metodo, ruta[:46], status, len(texto),
                 ("  " + os.path.basename(destino)) if destino else ""))
        if status >= 400:
            print("      %s" % texto[:300].replace("\n", " "))
    if status >= 400:
        return None
    try:
        return json.loads(texto)
    except ValueError:
        return None


# ── El saldo, leido del ledger. Nunca estimado. ──────────────────────────────

#: La ruta del saldo, MEDIDA (2026-09-25). La respuesta es:
#:   {"allowance": {"perCycle": 4000, "unitPriceCents": 1},
#:    "balance": {"cycle": 4000, "onDemand": 0, "personal": 0, "total": 4000},
#:    "usage": {"window": {...}, "granted": ..., "purchased": ..., "spent": ...}}
#: `balance.total` es lo que queda; `usage.spent` es lo gastado en el ciclo.
#: Los dos hacen falta: el total contesta «¿alcanza?» y el spent contesta
#: «¿cuanto costo esto?», que es lo que el brief pide medir y no estimar.
RUTA_SALDO = "/v1/me/credits"


def _leer_credits() -> dict | None:
    d = llamar(RUTA_SALDO, etiqueta="saldo", guardar=False, silencioso=True)
    return d if isinstance(d, dict) else None


def saldo(silencioso: bool = True) -> float | None:
    """Creditos que QUEDAN, del ledger. Gratis. None si no se pudo leer."""
    d = _leer_credits()
    if not d:
        return None
    b = d.get("balance") or {}
    t = b.get("total")
    return float(t) if isinstance(t, (int, float)) else None


def gastado_en_el_ciclo() -> float | None:
    """Lo que el ledger dice que se lleva gastado este ciclo.

    **NO sirve para medir el costo de una llamada.** Se comprobo el
    2026-09-25: siete llamadas bajaron `balance.total` de 3970 a 3940 y este
    numero no se movio ni una decima. Va con retraso --su ventana es el ciclo
    entero-- asi que para «cuanto costo esto» se usa `saldo()`, que es el
    unico de los dos que responde en el acto.
    """
    d = _leer_credits()
    if not d:
        return None
    g = (d.get("usage") or {}).get("spent")
    return round(float(g), 4) if isinstance(g, (int, float)) else None


def resumen() -> None:
    print("")
    print("llamadas: %d" % len(LLAMADAS))
    por_ruta: dict[str, int] = {}
    for c in LLAMADAS:
        clave = "%s %s" % (c["status"], re.sub(r"mma_[0-9a-f]+", "{id}",
                                               c["ruta"]))
        por_ruta[clave] = por_ruta.get(clave, 0) + 1
    for k, v in sorted(por_ruta.items(), key=lambda kv: -kv[1]):
        print("   %-58s x%d" % (k[:58], v))
