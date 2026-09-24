"""La pestaña Transactions de Model Match: una fila por cierre.

Por que esta pestaña cambia el grano de todo
--------------------------------------------
El Overview es un resumen, y un resumen no se puede desarmar. Las «9 compras
sin originador» de una captura real no eran un dato que faltara: eran compras
cash. Con el resumen no habia forma de saberlo, y el veredicto quedaba
incompleto sobre una ausencia que no existia.

Con el grano de transaccion las tres cosas que importan se DERIVAN en vez de
estimarse: cash contra financiadas, el loan mix, y la compuerta de exclusion
por lender. **Cuando hay Transactions, manda Transactions**; el Overview queda
como lo que es, un resumen. Es la misma regla que J-Q01 y P-Q14: cuando hay una
medicion, el resumen no manda.

Lo que NO se guarda, y no es un olvido
--------------------------------------
Las columnas `Buyers` y `Sellers` se leen para ubicar las demas y se tiran en
el acto. No llegan al dict que sale de aqui, asi que no pueden llegar a la
base. Inferir el origen de los compradores por sus apellidos es ECOA
Regulation B, y la unica forma de no hacerlo por accidente es no tener el dato.

La direccion se reduce a ZIP y ciudad por lo mismo: la calle identifica una
vivienda y una persona, y para lo que el motor hace --saber donde trabaja-- el
ZIP alcanza y sobra.

«Cash» no quiere decir efectivo
-------------------------------
Model Match lo dice el mismo: «Considered Cash until mortgage details are
received. Mortgage details are typically received within 3 to 5 weeks and
update automatically.»

Asi que `Cash` son DOS cosas segun cuanto haga que cerro:

    cash_provisional   cerro hace menos de 35 dias. Todavia no hay datos de
                       prestamo. La ficha NO dice «pago en efectivo».
    cash_segun_mm      cerro hace mas de 35 dias y Model Match sigue sin
                       datos. Ahi si es lo mas parecido a un hecho que hay.

La diferencia importa para el veredicto: una compra provisional puede terminar
financiada por la casa, y entonces ese realtor deja de ser contactable.

Funciones puras, sin IO.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from captura.trampas import NMLS_DE_LA_CASA, NOMBRES_DE_LA_CASA

#: Version del parser de esta pestaña. Viaja en la captura: re-derivar es
#: gratis y volver a capturar no.
VERSION_PARSER_TX = "tx-2026.09.23-v1"

#: Las 21 columnas, en orden. Los encabezados se PIERDEN al copiar y pegar, asi
#: que el parser no depende de ellos: depende del orden y valida cada fila.
COLUMNAS = (
    "fecha",            # 1  Date
    "direccion",        # 2  Property Address -- se reduce a ciudad + ZIP
    "constructor",      # 3  Home Builder
    "_compradores",     # 4  Buyers   · SE TIRA
    "_vendedores",      # 5  Sellers  · SE TIRA
    "title",            # 6  Title Company
    "prestamo",         # 7  Mortgage Amount («Cash» si no hay datos)
    "enganche",         # 8  Down Payment
    "proposito",        # 9  Transaction Type
    "tipo",             # 10 Loan Type
    "tasa",             # 11 Interest Rate
    "plazo",            # 12 Loan Term
    "lo",               # 13 Loan Officer (+ NMLS)
    "empleador",        # 14 Employer (+ NMLS)
    "broker",           # 15 Broker
    "lender",           # 16 Lender
    "precio",           # 17 Sold Amount
    "lista",            # 18 List Amount
    "agente_comprador", # 19 Buyer Agent
    "agente_listing",   # 20 Listing Agent
    "agente_colisting", # 21 Co-Listing Agent
)

#: Las dos que se leen y no se devuelven. La prueba comprueba que no salen.
NUNCA_SE_GUARDAN = ("_compradores", "_vendedores")

#: Model Match tarda de 3 a 5 semanas en recibir los datos del prestamo. 35
#: dias es el borde de arriba de esa ventana, que es el lado seguro: por debajo
#: se dice «pendiente», y decir «pendiente» de una compra que si era cash
#: cuesta una re-captura. Al reves cuesta un veredicto equivocado.
DIAS_CASH_PROVISIONAL = 35

FINANCIADA = "financiada"
CASH_PROVISIONAL = "cash_provisional"
CASH_SEGUN_MM = "cash_segun_mm"

COMPRA = "compra"
VENTA = "venta"
AMBOS = "ambos"

#: `Mortgage + Down ~= Sold`. En FHA la diferencia es el UFMIP del 1,75%, que
#: va DENTRO del prestamo, asi que la suma se pasa por arriba.
TOLERANCIA_SUMA = 0.02

#: El vacio de Model Match en una celda.
_VACIO = ("", "-", "--", "—", "–", "n/a", "na", "none", "null")

_RE_FECHA = re.compile(
    r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\s*$")
_RE_FECHA_LARGA = re.compile(
    r"^\s*([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\s*$")
#: `Chicago, IL, 60638` al final de la direccion. El ZIP ancla.
_RE_CIUDAD_ZIP = re.compile(
    r"([A-Za-zÁÉÍÓÚÑáéíóúñ.'\- ]{2,40}),\s*([A-Z]{2}),?\s*(\d{5})(?:-\d{4})?\s*$")
_RE_NMLS = re.compile(r"NMLS\s*#?\s*(\d{4,9})", re.I)
#: `1 - 25 of 25`, `1-25 of 137`, `Showing 1 to 25 of 25`.
_RE_PIE = re.compile(
    r"(\d[\d,]*)\s*(?:-|–|to)\s*(\d[\d,]*)\s*of\s*(\d[\d,]*)", re.I)

_MESES = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


# ══════════════════════════════════════════════════════════════════════════════
# LECTURAS DE CELDA
# ══════════════════════════════════════════════════════════════════════════════

def _vacia(v) -> bool:
    return str(v or "").strip().lower() in _VACIO


def _texto(v) -> str | None:
    if _vacia(v):
        return None
    return " ".join(str(v).split())


def _fecha(v) -> str | None:
    """`09/14/2026` o `Sep 14, 2026` -> `2026-09-14`. None si no es fecha."""
    s = " ".join(str(v or "").split())
    m = _RE_FECHA.match(s)
    if m:
        mes, dia, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if ano < 100:
            ano += 2000
    else:
        m = _RE_FECHA_LARGA.match(s)
        if not m:
            return None
        mes = _MESES.get(m.group(1).lower())
        if not mes:
            return None
        dia, ano = int(m.group(2)), int(m.group(3))
    try:
        return dt.date(ano, mes, dia).isoformat()
    except ValueError:
        return None


def _dinero(v) -> float | None:
    """`$286,000` -> 286000.0. `Cash` y los vacios -> None.

    NO devuelve 0 para `Cash`: un cero se suma en un promedio y desaparece.
    """
    if _vacia(v):
        return None
    s = str(v)
    if "cash" in s.lower():
        return None
    s = s.replace("$", "").replace(",", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def normalizar_tasa(v) -> float | None:
    """`762.00%` -> 7.62. `6.625%` -> 6.625. Los vacios -> None.

    Model Match a veces manda la tasa en puntos base sin decir que lo hace, y
    762 pasa por un float perfectamente valido. Se divide cuando pasa de 20:
    no existe una hipoteca residencial al 25% y si existe una a 7,62.

    El corte no es un umbral que se afine -- es la distancia entre dos ordenes
    de magnitud.
    """
    if _vacia(v):
        return None
    s = str(v).replace("%", "").replace(",", "").strip()
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        t = float(m.group(0))
    except ValueError:
        return None
    if t <= 0:
        return None
    return round(t / 100.0, 4) if t > 20 else t


def _ciudad_zip(direccion) -> tuple[str | None, str | None, str | None]:
    """`123 Main St, Chicago, IL, 60638` -> (Chicago, IL, 60638).

    La calle se descarta aqui y no se devuelve: identifica una vivienda.
    """
    if _vacia(direccion):
        return None, None, None
    m = _RE_CIUDAD_ZIP.search(" ".join(str(direccion).split()))
    if not m:
        return None, None, None
    return m.group(1).strip(" ,"), m.group(2), m.group(3)


def _persona_con_nmls(v) -> tuple[str | None, str | None]:
    """`Fabian Viera NMLS #123456` -> (Fabian Viera, 123456)."""
    s = _texto(v)
    if not s:
        return None, None
    m = _RE_NMLS.search(s)
    if not m:
        return s, None
    nombre = s[:m.start()].strip(" ,#-")
    return (nombre or None), m.group(1)


def _nombre_igual(a: str | None, b: str | None) -> bool:
    """Compara dos nombres de persona sin puntuacion ni orden de mayusculas.

    No intenta ser listo: `LAST, FIRST` se normaliza a sus palabras ordenadas,
    porque Model Match usa las dos formas en columnas distintas de la misma
    fila.
    """
    def _n(s):
        p = re.sub(r"[^a-z\s]", " ", (s or "").lower()).split()
        return tuple(sorted(p))
    na, nb = _n(a), _n(b)
    return bool(na) and na == nb


# ══════════════════════════════════════════════════════════════════════════════
# EL TROCEADO EN FILAS
# ══════════════════════════════════════════════════════════════════════════════

def _celdas_por_fila(texto: str) -> list[list[str]]:
    """Las filas crudas, en celdas. Dos formas de pegado, las dos reales.

    Al copiar una tabla web, el portapapeles a veces trae la fila entera con
    tabuladores y a veces trae **una celda por linea**. Distinguirlo por la
    presencia de tabuladores y no preguntarselo a quien captura es lo que hace
    que la caja funcione con cualquiera de los dos.

    En la forma «una celda por linea» la fila nueva empieza donde hay una
    FECHA, que es la columna 1 y la unica con forma inconfundible.
    """
    # Sin `rstrip()`: las celdas vacias del final de una fila son tabuladores,
    # y recortarlas dejaba una fila de 21 columnas con dos tabuladores. La
    # deteccion del pegado por tabuladores se caia justo en las filas cash, que
    # son las que traen las columnas 9 a 16 vacias.
    lineas = (texto or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    if any(l.count("\t") >= 8 for l in lineas):
        return [l.split("\t") for l in lineas if l.strip()]

    filas: list[list[str]] = []
    actual: list[str] = []
    for l in lineas:
        s = l.strip()
        if _fecha(s) and actual:
            filas.append(actual)
            actual = [s]
        elif _fecha(s):
            actual = [s]
        elif actual or s:
            if actual:
                actual.append(s)
    if actual:
        filas.append(actual)
    return filas


def paginacion(texto: str) -> dict:
    """El pie `1 - 25 of 25`. Sin el no se sabe si falta media tabla.

    Devuelve `total=None` cuando el pie no esta, que NO es lo mismo que cero:
    sin el pie no se puede afirmar que estan todas, y la ficha lo dice.
    """
    ultimo = None
    for m in _RE_PIE.finditer(texto or ""):
        ultimo = m
    if not ultimo:
        return {"desde": None, "hasta": None, "total": None, "pie": None}
    n = lambda s: int(str(s).replace(",", ""))  # noqa: E731
    return {"desde": n(ultimo.group(1)), "hasta": n(ultimo.group(2)),
            "total": n(ultimo.group(3)), "pie": ultimo.group(0)}


# ══════════════════════════════════════════════════════════════════════════════
# UNA FILA
# ══════════════════════════════════════════════════════════════════════════════

def _hash_fila(d: dict) -> str:
    """Huella de la operacion, para no duplicarla al re-pegar la pestaña.

    Sobre los campos que identifican el cierre y que no cambian al re-capturar.
    `prestamo` NO entra: una compra cash provisional que despues aparece
    financiada tiene que reconocerse como LA MISMA operacion actualizada, y si
    el monto entrara en la huella entraria como una fila nueva.
    """
    partes = [str(d.get(k) or "") for k in
              ("fecha", "zip", "precio", "lado", "agente_contraparte")]
    return hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()[:32]


def _estado_prestamo(prestamo, fecha, capturado_en) -> tuple[str, int | None]:
    """financiada / cash_provisional / cash_segun_mm, y los dias transcurridos."""
    if prestamo is not None and prestamo > 0:
        return FINANCIADA, _dias(fecha, capturado_en)
    dias = _dias(fecha, capturado_en)
    if dias is not None and dias < DIAS_CASH_PROVISIONAL:
        return CASH_PROVISIONAL, dias
    # Sin fecha legible NO se afirma «cash segun Model Match»: se queda en
    # provisional, que es el estado que no afirma nada.
    if dias is None:
        return CASH_PROVISIONAL, None
    return CASH_SEGUN_MM, dias


def _dias(fecha_iso: str | None, capturado_en: str | None) -> int | None:
    if not fecha_iso or not capturado_en:
        return None
    try:
        f = dt.date.fromisoformat(fecha_iso)
        c = dt.date.fromisoformat(str(capturado_en)[:10])
    except ValueError:
        return None
    return (c - f).days


def _lado(fila: dict, realtor: str | None) -> str | None:
    """El lado sale de EN QUE COLUMNA aparece el nombre del realtor.

    Buyer Agent -> compra. Listing Agent (o Co-Listing) -> venta. En las dos,
    doble punta. Sin nombre del realtor no se adivina: devuelve None y la fila
    queda sin lado, declarado.
    """
    if not realtor:
        return None
    compra = _nombre_igual(fila.get("agente_comprador"), realtor)
    venta = (_nombre_igual(fila.get("agente_listing"), realtor)
             or _nombre_igual(fila.get("agente_colisting"), realtor))
    if compra and venta:
        return AMBOS
    if compra:
        return COMPRA
    if venta:
        return VENTA
    return None


def _contraparte(fila: dict, lado: str | None) -> str | None:
    if lado == COMPRA:
        return fila.get("agente_listing")
    if lado == VENTA:
        return fila.get("agente_comprador")
    return None


def _verificar_suma(prestamo, enganche, precio) -> str | None:
    """`Mortgage + Down ~= Sold`, con 2% de tolerancia. Avisa, no descarta.

    En FHA la suma se pasa por arriba porque el UFMIP del 1,75% va DENTRO del
    prestamo: es la senal de que el enganche aparente del 1,8% es en realidad
    el minimo del 3,5%, no un DPA. Por eso el aviso dice cuanto y hacia donde,
    en vez de solo que no cuadra.
    """
    if prestamo is None or enganche is None or not precio:
        return None
    suma = prestamo + enganche
    dif = suma - precio
    if abs(dif) <= abs(precio) * TOLERANCIA_SUMA:
        return None
    return ("préstamo + enganche = %s contra %s de precio (%+.1f%%)"
            % (_m(suma), _m(precio), 100.0 * dif / precio))


def _m(v) -> str:
    return "$%s" % "{:,.0f}".format(v).replace(",", ".")


def _fila(celdas: list[str], *, realtor: str | None,
          capturado_en: str | None) -> dict:
    """Una fila cruda -> la operacion, sin nombres de comprador ni vendedor."""
    # Se rellena hasta 21: el portapapeles recorta las celdas vacias del final.
    c = list(celdas) + [""] * (len(COLUMNAS) - len(celdas))
    bruto = dict(zip(COLUMNAS, c))

    ciudad, estado, zip_ = _ciudad_zip(bruto.get("direccion"))
    lo_nombre, lo_nmls = _persona_con_nmls(bruto.get("lo"))
    empleador, empleador_nmls = _persona_con_nmls(bruto.get("empleador"))

    prestamo = _dinero(bruto.get("prestamo"))
    enganche = _dinero(bruto.get("enganche"))
    precio = _dinero(bruto.get("precio"))
    fecha = _fecha(bruto.get("fecha"))

    d: dict = {
        "fecha": fecha,
        "ciudad": ciudad,
        "estado": estado,
        "zip": zip_,
        "constructor": _texto(bruto.get("constructor")),
        "title": _texto(bruto.get("title")),
        "precio": precio,
        "lista": _dinero(bruto.get("lista")),
        "prestamo": prestamo,
        "enganche": enganche,
        "proposito": _texto(bruto.get("proposito")),
        "tipo": _texto(bruto.get("tipo")),
        "tasa": normalizar_tasa(bruto.get("tasa")),
        "plazo": _texto(bruto.get("plazo")),
        "lo_nombre": lo_nombre,
        "lo_nmls": lo_nmls,
        "empleador": empleador,
        # El NMLS de la empresa vive en la columna `Employer`, no en `Lender`.
        # Se expone como `lender_nmls` porque es el que decide la exclusion, y
        # se deja `empleador` al lado para que se pueda comprobar de donde sale.
        "lender_nmls": empleador_nmls,
        "broker": _texto(bruto.get("broker")),
        "lender": _texto(bruto.get("lender")) or empleador,
        "agente_comprador": _texto(bruto.get("agente_comprador")),
        "agente_listing": _texto(bruto.get("agente_listing")),
        "agente_colisting": _texto(bruto.get("agente_colisting")),
    }

    d["lado"] = _lado(d, realtor)
    d["agente_contraparte"] = _contraparte(d, d["lado"])
    d["estado_prestamo"], d["dias_desde_cierre"] = _estado_prestamo(
        prestamo, fecha, capturado_en)
    d["recapturar_despues_de"] = (
        _sumar_dias(fecha, DIAS_CASH_PROVISIONAL)
        if d["estado_prestamo"] == CASH_PROVISIONAL else None)
    d["aviso_suma"] = _verificar_suma(prestamo, enganche, precio)
    d["de_la_casa"] = _fila_es_de_la_casa(d)

    # Los tres agentes se guardan porque el lado se deriva de ellos y hay que
    # poder rehacer esa derivacion. Los compradores y los vendedores NO.
    for k in NUNCA_SE_GUARDAN:
        d.pop(k, None)
    d["hash_fila"] = _hash_fila(d)
    return d


def _sumar_dias(fecha_iso: str | None, dias: int) -> str | None:
    if not fecha_iso:
        return None
    try:
        return (dt.date.fromisoformat(fecha_iso)
                + dt.timedelta(days=dias)).isoformat()
    except ValueError:
        return None


def _fila_es_de_la_casa(d: dict) -> bool:
    """El NMLS 2129 cuando esta, y el nombre COMPLETO cuando no.

    Nunca una subcadena suelta: «Supreme Mortgage» no es Supreme Lending. Es la
    misma regla que `trampas.lender_es_de_la_casa`, aplicada a las tres
    columnas donde la casa puede aparecer en una transaccion.
    """
    if (d.get("lender_nmls") or "").strip() == NMLS_DE_LA_CASA:
        return True
    if (d.get("lo_nmls") or "").strip() == NMLS_DE_LA_CASA:
        return True
    for campo in ("lender", "empleador", "broker"):
        v = " ".join((d.get(campo) or "").lower().split())
        if any(n in v for n in NOMBRES_DE_LA_CASA):
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# LA PESTAÑA ENTERA
# ══════════════════════════════════════════════════════════════════════════════

def parsear_transacciones(crudo: str, *, realtor: str | None = None,
                          capturado_en: str | None = None) -> dict:
    """La pestaña pegada -> las operaciones, con su control de completitud.

    `realtor` es el nombre del agente: sin el, el LADO de cada fila queda en
    None y se declara, porque el lado sale de en que columna aparece su nombre
    y no hay otra forma de saberlo.
    """
    filas: list[dict] = []
    descartadas = 0
    for celdas in _celdas_por_fila(crudo or ""):
        if not _fecha(celdas[0] if celdas else ""):
            # El pie de paginacion no es una fila descartada: es el pie. Si se
            # contara, `lineas_descartadas` --que existe para avisar de que
            # algo no se leyo-- nunca bajaria de 1 y dejaria de significar algo.
            unido = " ".join(c for c in celdas if c).strip()
            if not unido or _RE_PIE.fullmatch(unido):
                continue
            descartadas += 1
            continue
        filas.append(_fila(celdas, realtor=realtor, capturado_en=capturado_en))

    pag = paginacion(crudo or "")
    total = pag.get("total")
    faltan = bool(total) and len(filas) < total

    return {
        "version_parser": VERSION_PARSER_TX,
        "filas": filas,
        "leidas": len(filas),
        "lineas_descartadas": descartadas,
        "paginacion": pag,
        # `None` cuando no hay pie: no se puede afirmar que estan todas.
        "completa": (None if total is None else len(filas) >= total),
        "faltan_paginas": faltan,
        "aviso": (("faltan páginas: el pie dice %d operaciones y se leyeron %d. "
                   "Pegá las páginas que faltan antes de calcular nada."
                   % (total, len(filas))) if faltan else
                  (None if total is not None else
                   "no se encontró el pie «1 - 25 of 25»: no se puede "
                   "confirmar que estén todas las operaciones")),
        "sin_lado": sum(1 for f in filas if not f.get("lado")),
    }


# ══════════════════════════════════════════════════════════════════════════════
# LO QUE SE DERIVA DEL GRANO
# ══════════════════════════════════════════════════════════════════════════════

def resumen(parseado: dict) -> dict:
    """Cash contra financiadas, loan mix y lenders por lado. Todo derivado.

    **Nada se calcula por diferencia.** Si una compra no se puede clasificar,
    queda sin clasificar y se cuenta aparte; restar del total convierte
    cualquier fila mal leida en una categoria inventada que nadie revisa.
    """
    filas = list(parseado.get("filas") or [])
    compras = [f for f in filas if f.get("lado") in (COMPRA, AMBOS)]
    ventas = [f for f in filas if f.get("lado") in (VENTA, AMBOS)]

    def _reparto(grupo):
        return {
            "total": len(grupo),
            FINANCIADA: sum(1 for f in grupo
                            if f["estado_prestamo"] == FINANCIADA),
            CASH_SEGUN_MM: sum(1 for f in grupo
                               if f["estado_prestamo"] == CASH_SEGUN_MM),
            CASH_PROVISIONAL: sum(1 for f in grupo
                                  if f["estado_prestamo"] == CASH_PROVISIONAL),
        }

    mix: dict = {}
    for f in compras:
        if f["estado_prestamo"] != FINANCIADA:
            continue
        mix[f.get("tipo") or "sin tipo"] = mix.get(f.get("tipo")
                                                   or "sin tipo", 0) + 1

    lenders_compra = _por_lender(compras)
    pendientes = [f for f in filas
                  if f["estado_prestamo"] == CASH_PROVISIONAL]

    financiadas_compra = [f for f in compras
                          if f["estado_prestamo"] == FINANCIADA]
    de_la_casa = [f for f in compras if f.get("de_la_casa")]

    return {
        "compras": _reparto(compras),
        "ventas": _reparto(ventas),
        "sin_lado": sum(1 for f in filas if not f.get("lado")),
        "loan_mix_compra": mix,
        "lenders_compra": lenders_compra,
        "lenders_venta": _por_lender(ventas),
        "unidades_de_la_casa": len(de_la_casa),
        "lenders_de_la_casa": sorted({f.get("lender") or f.get("empleador")
                                      for f in de_la_casa if f.get("lender")
                                      or f.get("empleador")}),
        "compras_financiadas": len(financiadas_compra),
        "pendientes_de_prestamo": [
            {"fecha": f["fecha"], "lado": f["lado"],
             "dias": f["dias_desde_cierre"],
             "recapturar_despues_de": f["recapturar_despues_de"]}
            for f in pendientes],
        "zips_de_compra": _cuenta(f.get("zip") for f in compras),
        "tasas": sorted(f["tasa"] for f in financiadas_compra
                        if f.get("tasa") is not None),
        "avisos_de_suma": [f["aviso_suma"] for f in filas if f.get("aviso_suma")],
    }


def _por_lender(grupo: list[dict]) -> dict:
    return _cuenta(f.get("lender") for f in grupo
                   if f["estado_prestamo"] == FINANCIADA)


def _cuenta(valores) -> dict:
    salida: dict = {}
    for v in valores:
        if v:
            salida[v] = salida.get(v, 0) + 1
    return dict(sorted(salida.items(), key=lambda kv: (-kv[1], kv[0])))


def share_buy_de_transacciones(resumen_tx: dict | None) -> float | None:
    """La fraccion del lado comprador con el GRANO de la transaccion.

    Es la mejor version de `mm_share_buy` que hay: cuenta operaciones reales en
    vez de leer el resumen de Side Focus, que en las capturas medidas discrepa
    del conteo por unidades. Devuelve None --no cero-- si no hay operaciones
    con lado.
    """
    if not resumen_tx:
        return None
    c = (resumen_tx.get("compras") or {}).get("total") or 0
    v = (resumen_tx.get("ventas") or {}).get("total") or 0
    if c + v <= 0:
        return None
    return round(c / float(c + v), 4)
