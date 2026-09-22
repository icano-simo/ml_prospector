"""Parser de Model Match, portado del prototipo y calibrado contra dato real.

Procedencia
-----------
Los patrones salen de `parseMercado` y `parseMM` de
`homesi-mesa-de-trabajo.html`, escritos contra los volcados reales de Armando
Ochoa y Lisa Munoz. **No se reescribieron**: se tradujeron. Un parser calibrado
contra el dato real vale mas que uno elegante, y volver a deducir el formato
seria repetir el trabajo con peor informacion.

Lo que si cambia es donde vive: en Python, que es el unico motor. El JavaScript
se elimina y Vercel solo muestra.

Las seis trampas, y donde estan resueltas aca
---------------------------------------------
1 · el grafico rodante no respeta el filtro  -> `total_volume` sale de
    `Total Loan Volume`, que es de Market Overview, nunca del rodante
2 · conforming/jumbo con denominador propio  -> `jumbo` se guarda como su
    porcentaje y `total_units` aparte; no se multiplican
3 · dos wallet shares                        -> `orig_buyer` (por unidades) y
    `tab_orig` (por volumen) se guardan separados
4 · los conteos de cabecera no coinciden     -> `sf_buy`, `buyer_units`,
    `listing_sold` y la suma de condados van cada uno por su lado
5 · la empresa va antes del nombre           -> `_relaciones` lee hacia atras
6 · los condados salen de View Counties      -> `condados`
"""
from __future__ import annotations

import datetime as dt
import re

#: Palabras que delatan que una linea es una EMPRESA y no una persona.
#: Del prototipo, tal cual: es lo que permite separar el nombre del originador
#: de su empresa cuando vienen en lineas seguidas.
COMPANYISH = re.compile(
    r"\b(inc|llc|l\.l\.c|corp|bank|mortgage|lending|financial|credit union|"
    r"fcu|association|company|capital|loans|home loans|savings|n\.a|na)\b|,",
    re.IGNORECASE,
)


def mval(texto: str | None) -> float | None:
    """'$1.2M' -> 1200000. '$613.2K' -> 613200. Del prototipo.

    Devuelve None si no hay numero, nunca 0: un cero inventado se suma.
    """
    if not texto:
        return None
    m = re.search(r"\$?\s*([\d.,]+)\s*([MKB])?", str(texto), re.IGNORECASE)
    if not m:
        return None
    crudo = m.group(1)
    # 1,096,337 es separador de millar; 6.0 es decimal.
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", crudo):
        crudo = crudo.replace(",", "")
    else:
        crudo = crudo.replace(",", "")
    try:
        v = float(crudo)
    except ValueError:
        return None
    sufijo = (m.group(2) or "").upper()
    return v * {"K": 1e3, "M": 1e6, "B": 1e9}.get(sufijo, 1.0)


def _plano(txt: str) -> str:
    return re.sub(r"[ \t]+", " ", txt)


def _g(plano: str, patron: str, grupo: int = 1) -> str | None:
    m = re.search(patron, plano, re.IGNORECASE)
    return m.group(grupo) if m else None


def _n(plano: str, patron: str, grupo: int = 1) -> float | None:
    v = _g(plano, patron, grupo)
    if v is None:
        return None
    try:
        return float(v.replace(",", ""))
    except ValueError:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# MERCADO · Market Signals
# ══════════════════════════════════════════════════════════════════════════════

def parsear_mercado(crudo: str) -> dict:
    """Un bloque de Market Signals -> metricas.

    `total_volume` sale de `Total Loan Volume`, que es la seccion Market
    Overview. **Nunca del Rolling Monthly Performance**, que muestra el mismo
    numero para las cuatro geografias porque no respeta el filtro.
    """
    txt = (crudo or "").replace("\r", "").replace(" ", " ")
    plano = _plano(txt)
    o: dict = {"capturado_en": dt.datetime.now(dt.timezone.utc).isoformat()}

    loc = re.search(r"Set Location\s*\n?\s*(?:\(i\)\s*)?([A-Za-z .,'-]{2,40})", txt)
    if loc:
        limpio = re.sub(r"\s*(Mortgage activity|Market Status|Refresh).*$", "",
                        loc.group(1).strip()).strip()
        o["location"] = None if re.fullmatch(r"(i|Set|Location)", limpio,
                                             re.IGNORECASE) else limpio
    else:
        o["location"] = None

    o["status"] = _g(plano, r"Market Status:\s*([^\n\U0001F525]+)")
    o["applications"] = _n(plano, r"Applications\s*(?:\(i\))?\s*([+\-]?[\d.]+)%")
    o["approvals"] = _n(plano, r"Approvals\s*(?:\(i\))?\s*([+\-]?[\d.]+)%")
    o["locks"] = _n(plano, r"Locks\s*(?:\(i\))?\s*([+\-]?[\d.]+)%")

    ttc = re.search(r"Avg Time to Close[\s\S]{0,60}?(\d+)\s*days", txt,
                    re.IGNORECASE)
    o["time_to_close"] = int(ttc.group(1)) if ttc else None

    # TRAMPA 1 · de Market Overview, no del grafico rodante.
    o["total_volume"] = mval(
        _g(plano, r"Total Loan Volume\s*(?:\(i\))?\s*(\$[\d.,]+\s*[MKB]?)"))
    o["total_units"] = _n(plano, r"Total Units\s*(?:\(i\))?\s*([\d,]+)")

    o["avg_rate"] = _n(plano, r"Avg Interest Rate\s*(?:\(i\))?\s*([\d.]+)%")
    o["avg_ltv"] = _n(plano, r"Avg LTV\s*([\d.]+)%")
    o["avg_term"] = _n(plano, r"Avg Loan Term\s*(\d+)\s*mo")
    o["avg_score"] = _n(plano, r"Avg Credit Score\s*(?:\(i\))?\s*(\d+)")
    o["avg_income"] = mval(
        _g(plano, r"Avg Household Income\s*(\$[\d.,]+\s*[MKB]?)"))
    o["funded"] = _n(plano, r"Funded\s*(?:\(i\))?\s*([\d.]+)%")
    o["fallout"] = _n(plano, r"Fall\s*Out\s*(?:\(i\))?\s*([\d.]+)%")
    o["adquisicion"] = _n(
        plano, r"Mortgage Acquisition Rate\s*(?:\(i\))?\s*([\d.]+)%")

    o["ftb"] = _n(plano, r"First-Time Buyers\s*([\d.]+)%")
    o["repeat"] = _n(plano, r"Repeat Buyers\s*([\d.]+)%")
    o["veterans"] = _n(plano, r"Veterans\s*([\d.]+)%")
    o["self_emp"] = _n(plano, r"Self-Employed\s*([\d.]+)%")
    o["credit_poor"] = _n(plano, r"Poor \(300-579\)\s*([\d.]+)%")
    o["credit_fair"] = _n(plano, r"Fair \(580-669\)\s*([\d.]+)%")
    o["credit_good"] = _n(plano, r"Good \(670-739\)\s*([\d.]+)%")
    o["millennial"] = _n(plano, r"Millennial\s*([\d.]+)%")
    o["genz"] = _n(plano, r"Gen Z\s*([\d.]+)%")

    # TRAMPA 2 · el jumbo tiene su propio denominador: NO se cruza con
    # total_units. Se guarda el porcentaje tal como lo reporta la fuente.
    o["jumbo"] = _n(plano, r"Jumbo\s*[\d,]*\s*loans?\s*([\d.]+)%")

    pz = re.split(r"Loan Type Distribution", txt, flags=re.IGNORECASE)
    if len(pz) > 1:
        z = re.split(r"Transaction Type Distribution", pz[1],
                     flags=re.IGNORECASE)[0].replace("\n", " ")
        for t in ("Conventional", "FHA", "VA", "HE", "HELOC", "Reverse"):
            m = re.search(r"\b%s\b\s*([\d.]+)%%" % re.escape(t), z,
                          re.IGNORECASE)
            if m:
                o["mkt_" + t.lower()] = float(m.group(1))

    tz = re.split(r"Transaction Type Distribution", txt, flags=re.IGNORECASE)
    if len(tz) > 1:
        z = re.split(r"Lender Type Distribution", tz[1],
                     flags=re.IGNORECASE)[0].replace("\n", " ")
        for t in ("Purchase", "Refinance", "Construction", "Equity"):
            m = re.search(r"\b%s\b\s*([\d.]+)%%" % t, z, re.IGNORECASE)
            if m:
                o["tx_" + t.lower()] = float(m.group(1))

    o["brokered"] = _n(plano, r"Brokered\s*([\d.]+)%")
    o["banked_retail"] = _n(plano, r"Banked\s*-\s*Retail\s*([\d.]+)%")

    o["campos"] = sum(1 for k, v in o.items()
                      if v is not None and k != "capturado_en")
    return o


# ══════════════════════════════════════════════════════════════════════════════
# PERFIL · Overview, Originators, Lenders
# ══════════════════════════════════════════════════════════════════════════════

def _relaciones(txt: str, cabecera: str, corte: str | None) -> list[dict]:
    """TRAMPA 5 · la empresa va en la linea ANTERIOR al nombre.

    Se lee hacia atras desde la fila con el monto. Sin esto no se detecta que
    Everett Financial es Supreme Lending, que es la exclusion dura.
    """
    partes = re.split(cabecera, txt, flags=re.IGNORECASE)
    if len(partes) < 2:
        return []
    zona = partes[1]
    if corte:
        zona = re.split(corte, zona, flags=re.IGNORECASE)[0]
    L = [s.strip() for s in zona.split("\n")]

    def previa(i: int):
        for j in range(i - 1, -1, -1):
            if L[j]:
                return L[j], j
        return None

    salida = []
    for i, linea in enumerate(L):
        m = re.match(r"^(.*?)\$([\d.,]+\s*[MKB]?)\s+(\d+)\s+([\d.]+)%\s*$", linea)
        if not m:
            continue
        empresa = (m.group(1) or "").strip()
        nombre = ""
        if empresa:
            p = previa(i)
            nombre = p[0] if p else ""
        else:
            p = previa(i)
            if not p:
                continue
            if COMPANYISH.search(p[0]):
                empresa = p[0]
                p2 = previa(p[1])
                nombre = p2[0] if p2 else ""
            else:
                nombre = p[0]
        if re.match(r"^NMLS", nombre, re.IGNORECASE):
            nombre = ""
        salida.append({"nombre": nombre, "empresa": empresa,
                       "volumen": mval("$" + m.group(2)),
                       "unidades": int(m.group(3)),
                       "share": float(m.group(4))})
    return salida


def detectar_inversion(originadores: list[dict]) -> list[str]:
    """Avisa si nombre y empresa parecen cambiados de lugar.

    Model Match trae los originadores en dos formas distintas segun la
    seccion, y una tercera forma -- empresa arriba, nombre en la fila del
    monto-- invierte los dos campos sin que se note: los dos son texto, los dos
    se llenan, y "Everett Financial Inc" en el campo `nombre` no rompe nada.

    Lo que si rompe es la exclusion: `es_de_la_casa` mira la EMPRESA, y si ahi
    quedo el nombre de la persona, un originador de Everett pasa el filtro.

    Heuristica barata: si el `nombre` tiene pinta de empresa y la `empresa` no,
    estan al reves.
    """
    sospechosos = []
    for o in originadores:
        nombre = o.get("nombre") or ""
        empresa = o.get("empresa") or ""
        if not nombre or not empresa:
            continue
        if COMPANYISH.search(nombre) and not COMPANYISH.search(empresa):
            sospechosos.append(
                "%r parece una empresa y esta en `nombre`, mientras %r esta en "
                "`empresa`" % (nombre, empresa))
    return sospechosos


def _tabla_originadores(txt: str) -> list[dict]:
    """La pestaña Originators: empresa, NMLS y nombre en lineas separadas."""
    partes = re.split(r"Originators this agent has worked with", txt,
                      flags=re.IGNORECASE)
    if len(partes) < 2:
        return []
    zona = re.split(r"Lenders this agent has worked with|Total Lenders|"
                    r"Title Companies", partes[1], flags=re.IGNORECASE)[0]
    L = [s.strip() for s in zona.split("\n")]
    salida = []
    for i, linea in enumerate(L):
        m = re.match(r"^(.*?)\$([\d.,]+\s*[MKB]?)\s+(\d+)\s+"
                     r"\$([\d.,]+\s*[MKB]?)\s+([\d.]+)%", linea)
        if not m:
            continue
        empresa = (m.group(1) or "").strip()
        nmls, nombre = "", ""
        for j in range(i - 1, max(-1, i - 5), -1):
            if not L[j]:
                continue
            nm = re.match(r"^NMLS:\s*(\d+)", L[j], re.IGNORECASE)
            if nm:
                nmls = nm.group(1)
                continue
            if not nombre and not COMPANYISH.search(L[j]):
                nombre = L[j]
                break
            if not empresa:
                empresa = L[j]
        salida.append({"nombre": nombre, "nmls": nmls, "empresa": empresa,
                       "volumen": mval("$" + m.group(2)),
                       "unidades": int(m.group(3)),
                       "promedio": mval("$" + m.group(4)),
                       "share": float(m.group(5))})
    return salida


#: Una fila de la tabla de condados, en el formato REAL de Model Match:
#:
#:   Solano County, CA\t$2.3M\t5\t$2.3M\t5\t$0\t0
#:
#: Siete columnas: nombre, volumen total, UNIDADES TOTALES, volumen comprador,
#: unidades comprador, volumen vendedor, unidades vendedor.
#:
#: La version anterior esperaba `nombre \t numero` al final de la linea y
#: devolvia CERO condados contra el volcado real. Sin condados no hay
#: etiquetado por posicion, o sea que la validacion de conteo habria dejado
#: pasar cualquier cantidad de bloques como si fuera solo el estado.
_RE_FILA_CONDADO_REAL = re.compile(
    r"^\s*([A-Z][A-Za-z.\-' ]{2,40}?)\s+County\s*,\s*([A-Z]{2})\s*\t"
    r"\s*\$[\d.,]+\s*[MKB]?\s*\t\s*(\d+)\s*\t",
    re.MULTILINE,
)


def _condados(txt: str) -> list[dict]:
    """Los condados de View Counties, EN ORDEN y con sus unidades totales.

    El orden es dato y no presentacion: es lo que etiqueta cada bloque de
    Market Signals.
    """
    salida = []
    for nombre, estado_fila, unidades in _RE_FILA_CONDADO_REAL.findall(txt or ""):
        n = nombre.strip()
        if n.lower() in ("total", "county", "counties", "units"):
            continue
        salida.append({"nombre": n, "estado": estado_fila,
                       "unidades": int(unidades)})
    return salida


def parsear_perfil(crudo: str) -> dict:
    """El Overview + Originators + Lenders de un perfil."""
    txt = (crudo or "").replace("\r", "").replace(" ", " ")
    plano = _plano(txt)
    lineas = [s.strip() for s in txt.split("\n") if s.strip()]

    def despues(etiqueta: str, n: int = 1) -> str | None:
        for i, l in enumerate(lineas):
            if l.lower() == etiqueta.lower():
                return lineas[i + n] if i + n < len(lineas) else None
        return None

    o: dict = {"capturado_en": dt.datetime.now(dt.timezone.utc).isoformat()}

    # El nombre va DESPUES de `Agents`, que es el ultimo item del menu de
    # navegacion. La primera linea del volcado es "Model Match" -- el nombre de
    # la aplicacion-- porque Ctrl+A copia el cromo entero.
    #
    # Tomar lineas[0] daba "Model Match" como nombre del agente en TODOS los
    # perfiles: un campo que se llena siempre, con el mismo valor, y que nadie
    # mira porque el nombre ya viene de la fila del realtor.
    o["nombre"] = despues("Agents") or (lineas[0] if lineas else None)
    if o["nombre"] and o["nombre"].lower() in ("model match", "search"):
        o["nombre"] = None
    o["licencia"] = _g(plano, r"(?:DRE|TREC|License)\s*#?\s*([A-Z0-9-]+)")
    o["emails"] = sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", txt)))
    o["rango_fechas"] = _g(plano, r"Last\s+(\d+)\s+Months")

    o["producer_tier"] = despues("Producer Tier")
    o["side_focus"] = despues("Side Focus")
    o["referral_concentration"] = despues("Referral Concentration")

    # TRAMPA 4 · los cuatro conteos, cada uno por su lado. NO se reconcilian.
    sf = re.search(r"(\d+)\s*buy\s*/\s*(\d+)\s*sell", plano, re.IGNORECASE)
    if sf:
        o["sf_buy"], o["sf_sell"] = int(sf.group(1)), int(sf.group(2))
    o["buyer_units"] = _n(plano, r"Buyer Units\s*(?:\(i\))?\s*(\d+)")
    o["listing_sold"] = _n(plano, r"(\d+)\s+Sold")
    o["buyer_volume"] = mval(
        _g(plano, r"Buyer Volume\s*(?:\(i\))?\s*(\$[\d.,]+\s*[MKB]?)"))

    o["condados"] = _condados(txt)

    # TRAMPA 3 · los dos wallet shares, separados y etiquetados.
    o["orig_buyer"] = _relaciones(
        txt, r"Buyer Side Relationships",
        r"Seller Side Relationships|Geography|Market Signals")
    o["orig_seller"] = _relaciones(
        txt, r"Seller Side Relationships",
        r"Geography|Top Builders|Market Signals")
    o["tab_orig"] = _tabla_originadores(txt)
    o["wallet_share_base"] = {
        "orig_buyer": "unidades",
        "tab_orig": "volumen",
    }
    return o
