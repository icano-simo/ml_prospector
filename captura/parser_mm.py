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


def _clave(etiqueta: str) -> str:
    """'Banked - Retail' -> 'banked_retail'."""
    return re.sub(r"[^a-z0-9]+", "_", etiqueta.lower()).strip("_")


def _zona(txt: str, desde: str, hasta: str | None = None) -> str:
    """El trozo entre dos marcadores. '' si no aparece el de apertura.

    Existe para que ningun campo se lea del documento entero. `Avg Loan Size`
    sale dos veces en el mismo perfil con valores distintos ($444K en la
    cabecera del comprador, $361K en la de lenders), y `Not Labeled` sale en
    Transaction Type y otra vez en Loan Channel. Un `re.search` sobre todo el
    texto se lleva el primero y no avisa.
    """
    partes = re.split(desde, txt, flags=re.IGNORECASE)
    if len(partes) < 2:
        return ""
    z = partes[1]
    if hasta:
        z = re.split(hasta, z, flags=re.IGNORECASE)[0]
    return z


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

#: Los canales de originacion, tal como los nombra Model Match.
CANALES = ("Banked - Retail", "Banked - Wholesale", "Correspondent",
           "Brokered", "Not Labeled")


def _loan_channel(txt: str) -> dict:
    """Loan Channel Distribution, la mitad de mercado del contraste de canal.

    La otra mitad es el `TPO %` de la cabecera de Lenders del AGENTE, que se lee
    en `parsear_perfil`. Se guardan las dos crudas y no se calcula un "TPO del
    mercado" sumando canales: **Model Match no dice que canales cuentan como
    TPO**, y elegirlo aca seria inventar el denominador del contraste dentro del
    parser, donde nadie lo vuelve a mirar.

    `Not Labeled` aparece tambien en Transaction Type Distribution con otro
    valor (11,6% contra 0,9%), asi que se lee acotado a esta seccion.
    """
    z = _zona(txt, r"Loan Channel Distribution",
              r"Market Signals|Originators this agent|Total Originators")
    if not z:
        return {}
    salida = {}
    for etiqueta in CANALES:
        m = re.search(r"^[ \t]*%s[ \t]*\r?\n[ \t]*([\d.]+)%%"
                      % re.escape(etiqueta), z, re.MULTILINE | re.IGNORECASE)
        if m:
            salida[_clave(etiqueta)] = float(m.group(1))
    return salida


def _conforming(txt: str, unidades_del_mercado: float | None) -> dict:
    """TRAMPA 2 · conforming/jumbo tiene su PROPIO denominador.

    Medido: el mercado declara 1.096.337 unidades y el bloque conforming/jumbo
    declara 613,2K. El 17,0% de jumbo es sobre 613,2K, no sobre 1.096.337 --
    multiplicarlo por las unidades del mercado da casi el doble de operaciones
    jumbo de las que hay.

    Por eso el denominador se guarda **explicito y al lado del porcentaje**, y
    la suma de los dos conteos se compara contra el: 509.013 + 104.166 = 613.179
    contra 613,2K. Si no cuadran, el bloque se leyo cruzado con otro.
    """
    z = _zona(txt, r"Conforming vs Jumbo",
              r"Borrower Profile|Product & Distribution|Application Performance")
    if not z:
        return {}

    o: dict = {"denominador_propio": mval(
        _g(z, r"Total Units\s*([\d.,]+\s*[MKB]?)")),
        "unidades_del_mercado": unidades_del_mercado}

    for tramo in ("Conforming", "Jumbo"):
        m = re.search(r"^[ \t]*%s[ \t]*\r?\n[ \t]*([\d,]+)[ \t]*loans?[ \t]*"
                      r"\r?\n[ \t]*([\d.]+)%%" % tramo, z,
                      re.MULTILINE | re.IGNORECASE)
        if m:
            o[tramo.lower() + "_loans"] = float(m.group(1).replace(",", ""))
            o[tramo.lower() + "_pct"] = float(m.group(2))

    suma = sum(o.get(k) or 0.0 for k in ("conforming_loans", "jumbo_loans"))
    den = o.get("denominador_propio")
    o["suma_de_tramos"] = suma or None
    # El denominador viene redondeado ("613.2K"), asi que la comparacion
    # tolera el redondeo -- pero no tolera que sea otro numero.
    o["cuadra"] = (None if not (suma and den)
                   else abs(suma - den) / den < 0.01)
    # Y el suyo no puede ser mayor que el del mercado entero: si lo es, el
    # bloque se leyo cruzado con el de otra geografia. La misma comprobacion
    # esta en `MixConforming.verificar`, y esta redundancia es a proposito:
    # la de alla hay que construirla a mano y esta corre sola en cada captura.
    o["mayor_que_el_mercado"] = (
        None if not (den and unidades_del_mercado)
        else den > unidades_del_mercado)
    return o


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
    # Y acotado a lo que va ANTES de Conforming vs Jumbo, que trae su propio
    # `Total Units` (613,2K). Hoy gana el del Market Overview por estar primero,
    # pero en un bloque al que le falte esa seccion el patron se llevaria el
    # 613 del otro denominador: un numero absurdo con formato correcto.
    antes_conf = re.split(r"Conforming vs Jumbo", plano, flags=re.IGNORECASE)[0]
    o["total_units"] = _n(antes_conf, r"Total Units\s*(?:\(i\))?\s*([\d,]+)")

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
    # total_units. Se guarda el porcentaje tal como lo reporta la fuente, y el
    # bloque entero -- con SU denominador y los dos conteos-- al lado.
    o["jumbo"] = _n(plano, r"Jumbo\s*[\d,]*\s*loans?\s*([\d.]+)%")
    o["conforming"] = _conforming(txt, o["total_units"]) or None

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

    # Los cinco canales, acotados a su seccion. `brokered` y `banked_retail`
    # siguen sueltos por compatibilidad con lo ya capturado, pero salen del
    # mismo dict: dos copias del mismo patron es como quedo el bug del alt-text.
    canales = _loan_channel(txt)
    o["loan_channel"] = canales or None
    for k, v in canales.items():
        o["canal_" + k] = v
    o["brokered"] = canales.get("brokered")
    o["banked_retail"] = canales.get("banked_retail")

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


#: Tolerancia al comparar un share declarado contra el que sale de las filas.
#: La fuente redondea a un decimal y a veces a entero ("50%").
_HOLGURA_SHARE = 1.0


def base_del_reparto(filas: list[dict]) -> str | None:
    """Que base usa un reparto: MEDIDO contra sus propias filas.

    `wallet_share_base` era un dict fijo que se copiaba en cada fila dijera lo
    que dijera el dato -- una etiqueta que nunca se comprobaba, y por lo tanto
    que podia mentir sin que nada fallara. Esto la reemplaza por una medicion:
    se recalcula el share desde las unidades y desde el volumen, y gana el que
    reproduce lo que declara la fuente.

    Sobre la captura real de Armando:

        orig_buyer  u=2,1,1 -> 50,0 / 25,0 / 25,0  = lo declarado  -> unidades
        tab_orig    $540K,$520K,$470K -> 35,3 / 34,0 / 30,7        -> volumen

    Devuelve:
      'unidades' | 'volumen'  una de las dos reproduce y la otra no
      'indistinguible'        menos de dos filas: las dos bases dan 100%
      None                    ninguna reproduce, o faltan datos
    """
    filas = [f for f in (filas or []) if f.get("share") is not None]
    if not filas:
        return None
    if len(filas) < 2:
        return "indistinguible"

    def reproduce(clave: str) -> bool:
        total = sum(f.get(clave) or 0 for f in filas)
        if not total:
            return False
        return all(
            abs(100.0 * (f.get(clave) or 0) / total - f["share"]) <= _HOLGURA_SHARE
            for f in filas)

    por_unidades, por_volumen = reproduce("unidades"), reproduce("volumen")
    if por_unidades and not por_volumen:
        return "unidades"
    if por_volumen and not por_unidades:
        return "volumen"
    return None


def base_normalizada(valor, esperada: str | None = None) -> dict:
    """Acepta la forma VIEJA de `wallet_share_base` sin dejarla pasar por medida.

    Hasta hoy el campo era un string plano -- `"unidades"`, `"volumen"`-- que
    declaraba la base sin comprobarla. Las capturas ya guardadas lo tienen asi,
    y quien las lea se encuentra las dos formas.

    La vieja se convierte en `{"esperada": ..., "medida": None}` y NO en
    `{"medida": "unidades"}`: era una etiqueta declarada, y convertirla en
    medicion seria darle una autoridad que nunca tuvo. `heredada` lo dice para
    que se vea en pantalla en vez de parecer una medicion que dio None.
    """
    if isinstance(valor, dict):
        return valor
    if isinstance(valor, str) and valor:
        return {"esperada": esperada or valor, "medida": None,
                "coincide": None, "filas": 0, "heredada": valor}
    return {"esperada": esperada, "medida": None, "coincide": None,
            "filas": 0}


def _etiqueta_de_base(filas: list[dict], esperada: str) -> dict:
    medida = base_del_reparto(filas)
    return {
        "esperada": esperada,
        "medida": medida,
        "coincide": (None if medida in (None, "indistinguible")
                     else medida == esperada),
        "filas": len(filas or []),
    }


#: (marcador en el texto, campo que tiene que salir, para que sirve).
#: Si el marcador esta y el campo sale vacio, es un FALLO DECLARADO, no un
#: array vacio -- que es indistinguible de "este perfil no tiene eso".
SECCIONES_ESPERADAS = (
    (r"Buyer Side Relationships", "orig_buyer",
     "el reparto por unidades, que es el que decide la exclusion por "
     "no-canibalizacion"),
    (r"Originators this agent has worked with", "tab_orig",
     "la tabla de originadores con su NMLS"),
    (r"Loan Type Breakdown \(Buyer\)", "loan_mix_buyer",
     "la mitad de agente del contraste FHA"),
    (r"Lenders this agent has worked with", "tabla_lenders",
     "la tabla de lenders"),
    (r"View Counties", "condados",
     "los condados, que son lo que etiqueta cada bloque de mercado"),
)

#: Frases con las que Model Match dice que una seccion esta vacia de verdad.
_VACIO_DECLARADO = re.compile(
    r"No (?:originator relationships|builder data|active or pending listings|"
    r"data|results?)[^\n]*(?:found|available)", re.IGNORECASE)


def fallos_de_seccion(txt: str, salida: dict) -> list[dict]:
    """Secciones que estan en el texto y no llegaron al dict.

    La unica alternativa a esto es un `[]`, y un `[]` dice dos cosas a la vez:
    "este agente no trabaja con nadie" y "el parser no supo leerlo". La primera
    es un dato y la segunda es un error, y se guardan identicas.
    """
    fallos = []
    for marcador, campo, para_que in SECCIONES_ESPERADAS:
        if not re.search(marcador, txt, re.IGNORECASE):
            continue
        if salida.get(campo):
            continue
        # La fuente puede decir explicitamente que no hay nada. Eso es un dato.
        zona = _zona(txt, marcador)
        if zona and _VACIO_DECLARADO.search(zona[:400]):
            continue
        fallos.append({
            "campo": campo,
            "seccion": re.sub(r"\\", "", marcador),
            "por_que_importa": para_que,
            "detalle": ("la seccion esta en el texto y el campo salio vacio: "
                        "es un fallo del parser, no un perfil sin datos"),
        })
    return fallos


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
#: Una fila de View Counties. Cuatro cosas que la version anterior perdia, y
#: las cuatro se midieron contra volcados reales:
#:
#:   · **Espacios ademas de tabuladores.** Al copiar desde el navegador a veces
#:     llegan espacios, y la fila entera no matcheaba -- o sea CERO condados,
#:     que es el peor resultado posible porque no parece un error.
#:   · **Parish, Borough y city.** Luisiana usa Parish, Alaska Borough, y hay
#:     ciudades independientes (`Baltimore city`). Sin esto, un realtor de
#:     Nueva Orleans no tenia ni un condado.
#:   · **Acentos y ñ.** `Doña Ana County` en Nuevo Mexico.
#:   · **Nombres de una sola palabra.** El `{2,40}?` sobre la clase pedia al
#:     menos 3 caracteres, asi que `Lee County` (Florida) pasaba raspando y
#:     `Ada County` tambien -- pero la intencion era otra y conviene que se vea.
_RE_FILA_CONDADO_REAL = re.compile(
    r"^[ \t]*([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ.\-' ]{1,40}?)\s+"
    r"(County|Parish|Borough|city|City and County)\s*,\s*([A-Z]{2})"
    r"[ \t]+\$[\d.,]+\s*[MKB]?[ \t]+(\d+)(?:[ \t]|$)",
    re.MULTILINE,
)

#: Los tipos que NO son condado. En cinco estados existe una ciudad
#: independiente con el MISMO nombre que el condado que la rodea, y son FIPS
#: distintos:
#:
#:   Baltimore city (24510) y Baltimore County (24005), MD
#:   St. Louis city (29510) y St. Louis County (29189), MO
#:   Richmond city (51760) y Richmond County (51159), VA
#:   Fairfax city (51600) y Fairfax County (51059), VA
#:   Roanoke city (51770) y Roanoke County (51161), VA
#:
#: Quitar el sufijo los convertia en el mismo mercado: dos filas del Overview
#: con volumenes y unidades distintos colapsaban en «Baltimore», y la
#: biblioteca de geografias promediaba dos sitios que no se parecen -- una
#: ciudad de 570.000 habitantes y el condado suburbano de al lado.
#:
#: Es el mismo error de CA contra California, al reves: alli dos nombres del
#: mismo sitio, aqui un nombre para dos sitios.
TIPOS_QUE_NO_SON_CONDADO = ("city", "City and County")


def _condados(txt: str) -> list[dict]:
    """Los condados de View Counties, EN ORDEN y con sus unidades totales.

    El orden es dato y no presentacion: es lo que etiqueta cada bloque de
    Market Signals.
    """
    salida = []
    for nombre, tipo, estado_fila, unidades in _RE_FILA_CONDADO_REAL.findall(
            txt or ""):
        n = nombre.strip()
        if n.lower() in ("total", "county", "counties", "units"):
            continue
        tipo = tipo.strip()
        # `nombre` conserva el sufijo cuando NO es un condado, porque si no
        # «Baltimore city» y «Baltimore County» son la misma etiqueta y son dos
        # FIPS distintos. Para los condados se quita, que es como se nombran.
        etiqueta = n if tipo == "County" else "%s %s" % (n, tipo)
        salida.append({"nombre": etiqueta, "nombre_base": n, "tipo": tipo,
                       "es_condado": tipo not in TIPOS_QUE_NO_SON_CONDADO,
                       "estado": estado_fila, "unidades": int(unidades)})
    return salida


#: Una fila del desglose por tipo de prestamo del agente:
#:
#:   FHA
#:   $1.1M / 2 Units
#:   66.7%
_RE_FILA_LOAN_MIX = re.compile(
    r"^[ \t]*([A-Za-z][A-Za-z ()/.\-]{1,40}?)[ \t]*\r?\n"
    r"[ \t]*\$([\d.,]+[ \t]*[MKB]?)[ \t]*/[ \t]*([\d,]+)[ \t]*Units?[ \t]*\r?\n"
    r"[ \t]*([\d.]+)%",
    re.MULTILINE,
)


def _loan_mix_buyer(txt: str, buyer_units: float | None) -> dict:
    """Loan Type Breakdown (Buyer): la mitad de agente del contraste FHA.

    **Con su denominador.** En el perfil de prueba el agente declara 9 unidades
    compradoras, y el desglose por tipo solo identifica 3 (FHA 2 + HE 1). El
    66,7% de FHA es sobre esas 3, no sobre las 9: son 2 operaciones, no 6.

    Por eso se devuelve `unidades_identificadas` y `cobertura` al lado de las
    filas. La guardia de PACS-H pide 10 operaciones con tipo identificado y 50%
    de cobertura del lado comprador; sin estos dos campos esa guardia no tiene
    con que correr, y una guardia que no puede correr pasa siempre.

    La misma forma `$x / n Units \\n pct%` aparece en `Buyer vs. Listing Side`
    justo arriba, asi que se lee acotado a esta seccion.
    """
    z = _zona(txt, r"Loan Type Breakdown \(Buyer\)",
              r"Monthly Volume|Buyer Side Relationships|Market Signals")
    if not z:
        return {}

    filas = []
    for tipo, vol, unidades, share in _RE_FILA_LOAN_MIX.findall(z):
        t = tipo.strip()
        # Las dos lineas de cabecera de la tabla tienen la misma forma.
        if t.lower() in ("loan type", "volume", "units", "share", "buyer",
                         "seller", "represented"):
            continue
        filas.append({"tipo": t, "volumen": mval("$" + vol),
                      "unidades": int(unidades.replace(",", "")),
                      "share": float(share)})
    if not filas:
        return {}

    identificadas = float(sum(f["unidades"] for f in filas))
    return {
        "filas": filas,
        "unidades_identificadas": identificadas,
        "buyer_units": buyer_units,
        "cobertura": (None if not buyer_units
                      else round(100.0 * identificadas / buyer_units, 1)),
        "base_del_share": "unidades identificadas, NO buyer_units",
    }


#: `Office: (888) 584-9427`
_RE_TELEFONO_OFICINA = re.compile(r"^[ \t]*Office:[ \t]*([+()\d][\d\s().\-]{6,24})",
                                  re.MULTILINE | re.IGNORECASE)

#: `San Ramon CA 94583` -- la linea que ancla la direccion postal.
_RE_CIUDAD_ESTADO_CP = re.compile(
    r"^[ \t]*([A-Z][A-Za-z.'\- ]{1,40}?)[ \t]+([A-Z]{2})[ \t]+(\d{5})(?:-\d{4})?[ \t]*$",
    re.MULTILINE,
)

#: Lineas que son etiqueta de la interfaz y nunca nombre de oficina.
_NO_ES_OFICINA = ("set date range:", "view more", "agents", "model match",
                  "search", "overview")


def _contacto(txt: str, lineas: list[str]) -> dict:
    """Oficina, direccion y telefono de la cabecera del perfil.

    Se ancla en la linea `Ciudad ST 99999`, que es la unica con forma
    inconfundible, y se lee hacia arriba: calle y despues nombre de la oficina.
    Si esa linea no aparece, **todo queda en None**: una direccion adivinada se
    guarda igual de bien que una correcta y no hay como distinguirlas despues.
    """
    o: dict = {"oficina": None, "calle": None, "ciudad": None,
               "estado_postal": None, "cp": None, "direccion": None,
               "telefono_oficina": None, "telefono_oficina_e164": None}

    m = _RE_TELEFONO_OFICINA.search(txt)
    if m:
        crudo = m.group(1).strip()
        o["telefono_oficina"] = crudo
        digitos = re.sub(r"\D", "", crudo)
        if len(digitos) == 10:
            o["telefono_oficina_e164"] = "+1" + digitos
        elif len(digitos) == 11 and digitos.startswith("1"):
            o["telefono_oficina_e164"] = "+" + digitos

    m = _RE_CIUDAD_ESTADO_CP.search(txt)
    if not m:
        return o
    linea_cp = m.group(0).strip()
    try:
        i = lineas.index(linea_cp)
    except ValueError:
        return o

    o["ciudad"], o["estado_postal"], o["cp"] = (m.group(1).strip(), m.group(2),
                                                m.group(3))
    if i >= 1:
        o["calle"] = lineas[i - 1]
    if i >= 2 and lineas[i - 2].lower().rstrip(":") not in (
            s.rstrip(":") for s in _NO_ES_OFICINA):
        o["oficina"] = lineas[i - 2]

    partes = [p for p in (o["calle"], "%s %s %s" % (o["ciudad"],
                                                    o["estado_postal"],
                                                    o["cp"])) if p]
    o["direccion"] = ", ".join(partes)
    return o


def _cabecera_lenders(txt: str) -> dict:
    """`Total Lenders / Top 5 Concentration / TPO % / Avg Loan Size`.

    Acotada: `Avg Loan Size` sale tambien en la cabecera del comprador con otro
    valor ($444K contra $361K), y un `re.search` sobre el texto entero se lleva
    el primero.
    """
    z = _zona(txt, r"(?m)^[ \t]*Total Lenders[ \t]*$",
              r"Lenders this agent has worked with")
    if not z:
        return {}
    return {
        "total_lenders": _n(z, r"^\s*(\d+)"),
        "top5_concentracion": _n(z, r"Top 5 Concentration\s*([\d.]+)%"),
        "tpo_pct": _n(z, r"TPO\s*%\s*([\d.]+)%"),
        "avg_loan_size": mval(_g(z, r"Avg Loan Size\s*(\$[\d.,]+\s*[MKB]?)")),
    }


def _tabla_lenders(txt: str) -> list[dict]:
    """La tabla de lenders: nombre, volumen, unidades, promedio y share.

    Mismas cinco columnas que la de originadores, pero el nombre va en la
    MISMA fila -- no hay que leer hacia atras.
    """
    z = _zona(txt, r"Lenders this agent has worked with",
              r"Rows per page|Title Companies")
    if not z:
        return []
    salida = []
    for linea in z.split("\n"):
        m = re.match(r"^\s*(.+?)\s*\t\s*\$([\d.,]+\s*[MKB]?)\s*\t\s*([\d,]+)"
                     r"\s*\t\s*\$([\d.,]+\s*[MKB]?)\s*\t\s*([\d.]+)%",
                     linea)
        if not m:
            continue
        salida.append({"nombre": m.group(1).strip(),
                       "volumen": mval("$" + m.group(2)),
                       "unidades": int(m.group(3).replace(",", "")),
                       "promedio": mval("$" + m.group(4)),
                       "share": float(m.group(5))})
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

    # ── LA PRODUCCION QUE MANDA · solo lado comprador, anualizada ───────────
    # `Last 14 Months` es la ventana de Model Match. Nueve unidades compradoras
    # en catorce meses son 7,7 al año, NO nueve y NO las 16 del libro.
    #
    # Va en su propio campo: `unidades_ano` es del lote y no se sobrescribe --
    # son dos mediciones distintas de cosas parecidas, con distinta ventana y
    # distinta fecha, y la diferencia entre ellas es informacion.
    ventana = None
    if o.get("rango_fechas"):
        try:
            ventana = int(o["rango_fechas"])
        except (TypeError, ValueError):
            ventana = None
    o["ventana_meses"] = ventana
    o["buyside_anualizado"] = (
        round(o["buyer_units"] / ventana * 12.0, 1)
        if (o.get("buyer_units") and ventana) else None)

    # La mitad de agente del contraste FHA, con su denominador al lado.
    o["loan_mix_buyer"] = _loan_mix_buyer(txt, o.get("buyer_units")) or None

    # La mitad de agente del contraste de canal. La de mercado es
    # `loan_channel` de `parsear_mercado`.
    o["cabecera_lenders"] = _cabecera_lenders(txt) or None
    o["tpo_pct"] = (o["cabecera_lenders"] or {}).get("tpo_pct")
    o["tabla_lenders"] = _tabla_lenders(txt)

    # Oficina, direccion y telefono. Van a `pacs.contactos` con fuente Model
    # Match, y se ACUMULAN: la unique key incluye la fuente, asi que el
    # telefono de MM convive con el del lote en vez de pisarlo.
    o["contacto"] = _contacto(txt, lineas)

    # TRAMPA 3 · los dos wallet shares, separados y etiquetados.
    o["orig_buyer"] = _relaciones(
        txt, r"Buyer Side Relationships",
        r"Seller Side Relationships|Geography|Market Signals")
    o["orig_seller"] = _relaciones(
        txt, r"Seller Side Relationships",
        r"Geography|Top Builders|Market Signals")
    o["tab_orig"] = _tabla_originadores(txt)
    # MEDIDA, no declarada: el dict fijo de antes decia "volumen" sobre
    # porcentajes de unidades y nada fallaba.
    o["wallet_share_base"] = {
        "orig_buyer": _etiqueta_de_base(o["orig_buyer"], "unidades"),
        "tab_orig": _etiqueta_de_base(o["tab_orig"], "volumen"),
    }

    # Lo que estaba en el texto y no llego al dict.
    o["fallos"] = fallos_de_seccion(txt, o)
    return o


#: Los campos que son listas y se completan desde la seccion que los trae.
_CAMPOS_LISTA = ("orig_buyer", "orig_seller", "tab_orig", "tabla_lenders",
                 "condados", "emails")


def unir_perfiles(perfiles: list[dict]) -> dict:
    """Las filas de perfil de UNA captura, en un solo dict.

    **`orig_buyer` vive en la fila del Overview y `tab_orig` en la de
    Originators.** Preguntarle a una sola fila devuelve la mitad del perfil sin
    que nada avise: la fila de Originators -- que es justo la que parece traer
    los originadores-- da `orig_buyer = []`, y con eso la exclusion por
    no-canibalizacion no dispara sobre alguien que si trabaja con la casa.

    Se une por seccion y no se promedia nada: cada campo se toma de la primera
    fila que lo trae con dato.
    """
    unido: dict = {}
    fallos: list[dict] = []
    for p in perfiles or []:
        if not isinstance(p, dict):
            continue
        fallos.extend(p.get("fallos") or [])
        for clave, valor in p.items():
            if clave == "fallos":
                continue
            if clave == "wallet_share_base":
                base = unido.setdefault("wallet_share_base", {})
                for k, v in (valor or {}).items():
                    # Las capturas guardadas antes traen un string aca.
                    v = base_normalizada(v)
                    if v.get("filas"):
                        base[k] = v
                    else:
                        base.setdefault(k, v)
                continue
            if clave in _CAMPOS_LISTA:
                if valor and not unido.get(clave):
                    unido[clave] = valor
                else:
                    unido.setdefault(clave, valor)
                continue
            if valor is not None and unido.get(clave) is None:
                unido[clave] = valor
            else:
                unido.setdefault(clave, valor)
    unido["fallos"] = fallos
    unido["filas_unidas"] = len([p for p in (perfiles or [])
                                 if isinstance(p, dict)])
    return unido
