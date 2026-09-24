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
#: Ni prestamo ni `Cash`: la celda no se pudo leer. **Es el estado que faltaba**
#: y el que causaba el falso `ok`: un loan que no se leyo entraba como cash, y
#: con eso un realtor con operaciones de Supreme salia contactable.
NO_LEIDO = "no_leido"

#: Sufijos societarios que se quitan para agrupar lenders. «Guaranteed Rate
#: Inc», «Guaranteed Rate, Inc.» y «Guaranteed Rate» son el mismo lender en tres
#: columnas del mismo volcado, y contarlos aparte parte el reparto en tres.
_SUFIJOS_SOCIETARIOS = (
    "incorporated", "corporation", "company", "inc", "llc", "l.l.c", "corp",
    "co", "ltd", "lp", "llp", "na", "n.a")

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
_RE_NMLS = re.compile(r"NMLS\s*[:#]?\s*(\d{4,9})", re.I)
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
    """`$286,000` -> 286000.0. `$300K` -> 300000.0. `Cash` y los vacios -> None.

    El sufijo K/M NO es opcional de leer: el volcado real trae **todos** los
    importes abreviados --`$151K`, `$300K`-- y sin el sufijo «$300K» entraba
    como 300 dolares. Un precio de vivienda de tres cifras no revienta nada:
    se guarda, se promedia y sale en la ficha.

    NO devuelve 0 para `Cash`: un cero se suma en un promedio y desaparece.
    """
    if _vacia(v):
        return None
    s = str(v)
    if "cash" in s.lower():
        return None
    m = re.search(r"(-?[\d,]+(?:\.\d+)?)\s*([KMB])?", s.replace("$", ""),
                  re.IGNORECASE)
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return n * {"K": 1e3, "M": 1e6, "B": 1e9}.get((m.group(2) or "").upper(),
                                                  1.0)


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

    Se corta por COMAS y no con una expresion regular sobre el texto entero.
    La version con regex dejaba que el nombre de ciudad se comiera las palabras
    de la calle --«Calle Ficticia Chicago»-- porque la clase de caracteres
    incluye el espacio y no hay nada que le diga donde empieza la ciudad. Las
    comas si lo dicen.

    Y si el candidato a ciudad trae un numero o mas de cuatro palabras, la
    ciudad queda en `None`: significa que la coma que separa la calle no estaba,
    y una ciudad adivinada se guarda igual de bien que una correcta. El ZIP y el
    estado si salen, que son los que sostienen «donde trabaja».
    """
    if _vacia(direccion):
        return None, None, None
    partes = [p.strip() for p in str(direccion).split(",")]
    if len(partes) < 3:
        return None, None, None
    mz = re.fullmatch(r"(\d{5})(?:-\d{4})?", partes[-1])
    me = re.fullmatch(r"[A-Z]{2}", partes[-2])
    if not (mz and me):
        return None, None, None
    candidata = " ".join(partes[-3].split())
    if re.search(r"\d", candidata) or len(candidata.split()) > 4:
        candidata = ""
    return (candidata or None), partes[-2], mz.group(1)


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

#: Donde termina la tabla y empieza el pie. Lo que sigue a esta etiqueta trae
#: el selector de filas por pagina, el «1 - 25 of 25» y --medido en el pegado
#: real-- un «$200K» suelto que NO es una celda de ninguna fila.
_FIN_DE_LA_TABLA = "Rows per page"

#: Una fila nueva empieza aqui. Es la columna 1 y la unica con forma
#: inconfundible en todo el volcado.
_RE_CELDA_FECHA = re.compile(
    r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+"
    r"\d{1,2},\s*\d{4}$")

#: `NMLS: 900001`. Va pegado a la celda anterior -- el LO o el Employer.
_RE_CELDA_NMLS = re.compile(r"^NMLS\s*[:#]", re.I)

#: `Chicago, IL, 60633`. Va pegada a la anterior, que es la calle, para que la
#: direccion entera ocupe UNA celda y las 21 columnas cuadren.
_RE_CELDA_CIUDAD = re.compile(
    r"^[A-Za-zÁÉÍÓÚÑáéíóúñ.'\- ]{2,40},\s*[A-Z]{2},?\s*\d{5}(?:-\d{4})?$")


def _celdas_por_fila(texto: str) -> list[list[str]]:
    """Las filas crudas, en celdas. Del pegado REAL, no de uno construido.

    Model Match entrega una MEZCLA de tabuladores y saltos de linea, y no una
    cosa o la otra: la misma fila trae la fecha con tabulador, la calle y la
    ciudad en dos lineas, cuatro columnas con tabuladores y los tres agentes en
    tres lineas. La primera version partia por tabuladores o por lineas segun
    cual viera primero, y sobre el volcado real daba 25 filas de una celda y
    304 lineas descartadas -- con todos los campos en null y las 25 filas
    contadas como cash.

    El algoritmo, medido contra el volcado real:

      1 · cortar en «Rows per page». Lo que sigue es el pie;
      2 · partir por tabulador Y por salto de linea, recortar, y tirar las
          celdas vacias. «—» NO es vacia: es una columna que Model Match
          muestra sin dato, y tirarla correria todas las demas;
      3 · fila nueva donde hay una fecha;
      4 · unir a la celda anterior las que empiezan por `NMLS:` y las de la
          forma `Ciudad, ST, 99999`;
      5 · 21 celdas exactas. Lo que no, se cuenta como `no_leida`.

    Se conserva el camino de «una fila por linea con tabuladores», que es como
    lo entrega un pegado desde una hoja de calculo.
    """
    crudo = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    cuerpo = crudo.split(_FIN_DE_LA_TABLA)[0]

    # Camino rapido: filas enteras con tabuladores. Se exige que la linea
    # EMPIECE por una fecha, porque si no la cabecera de la tabla --que
    # tambien trae tabuladores-- lo activaria sobre el volcado real.
    lineas = cuerpo.split("\n")
    if any(l.count("\t") >= 15 and _RE_CELDA_FECHA.match(l.split("\t")[0].strip())
           for l in lineas):
        return [l.split("\t") for l in lineas if l.strip()]

    celdas = [c.strip() for l in lineas for c in l.split("\t")]
    celdas = [c for c in celdas if c]

    filas: list[list[str]] = []
    actual: list[str] = []
    for c in celdas:
        if _RE_CELDA_FECHA.match(c):
            if actual:
                filas.append(actual)
            actual = [c]
            continue
        if not actual:
            # Todo lo de antes de la primera fecha es la cabecera de la tabla.
            continue
        if _RE_CELDA_NMLS.match(c):
            actual[-1] = "%s %s" % (actual[-1], c)
            continue
        if _RE_CELDA_CIUDAD.match(c):
            # Con COMA y no con espacio. Unirlas con un espacio daba
            # «101 Calle Ficticia Chicago, IL, 60633», y de ahi la ciudad salia
            # como «Calle Ficticia Chicago»: la calle entera dentro de un campo
            # que existe justamente para no guardarla.
            actual[-1] = "%s, %s" % (actual[-1], c)
            continue
        actual.append(c)
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


def nombre_de_lender(v: str | None) -> str | None:
    """`Guaranteed Rate, Inc.` -> `Guaranteed Rate`. Para AGRUPAR, no para mostrar.

    Quita los sufijos societarios del final y la puntuacion que los acompaña.
    No toca el resto: «Peoples Bank» se queda entero, porque `bank` no es un
    sufijo societario sino parte del nombre.
    """
    s = " ".join((v or "").split())
    if not s:
        return None
    cambio = True
    while cambio:
        cambio = False
        s = s.rstrip(" .,")
        for suf in _SUFIJOS_SOCIETARIOS:
            if s.lower().endswith(" " + suf):
                s = s[: -len(suf) - 1].rstrip(" .,")
                cambio = True
                break
    return s or None


def _estado_prestamo(celda_prestamo, prestamo, fecha,
                     capturado_en) -> tuple[str, int | None]:
    """financiada / cash_* / no_leido, y los dias transcurridos.

    **`cash_*` solo si la celda dice literalmente `Cash`.** Si esta vacia, trae
    un guion o no se pudo leer, el estado es `no_leido` -- nunca cash. Era el
    agujero: una celda que el troceado no supo leer salia como «pago en
    efectivo», y una compra financiada por la casa desaparecia del conteo que
    decide la exclusion.
    """
    if prestamo is not None and prestamo > 0:
        return FINANCIADA, _dias(fecha, capturado_en)
    if "cash" not in str(celda_prestamo or "").lower():
        return NO_LEIDO, _dias(fecha, capturado_en)
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
    d["lender_agrupado"] = nombre_de_lender(d["lender"])
    d["estado_prestamo"], d["dias_desde_cierre"] = _estado_prestamo(
        bruto.get("prestamo"), prestamo, fecha, capturado_en)
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

#: Las columnas que NO se guardan en el crudo. Indices sobre `COLUMNAS`.
#: 2 es la calle, 4 los compradores, 5 los vendedores.
_A_REDACTAR = ("_compradores", "_vendedores")

REDACTADO = "[redactado]"


def crudo_redactado(texto: str) -> str:
    """El pegado, reconstruido sin calle ni nombres de las partes.

    LA EXCEPCION A «EL CRUDO SE GUARDA SIEMPRE», Y POR QUE
    -------------------------------------------------------
    En todo el resto del proyecto el crudo se guarda tal cual, y es lo que
    permite arreglar el parser y re-derivar sin volver a capturar. Aqui no se
    puede: el pegado de Transactions trae el nombre del comprador, el del
    vendedor y la calle de la vivienda de cada operacion, y `texto_crudo` es
    una columna que se lee, se exporta y se mira.

    De nada sirve que la tabla `pacs.transacciones` no tenga esas columnas si
    el texto entero queda al lado en otra tabla. La guarda tiene que estar en
    la ENTRADA, no solo en el destino.

    Que se conserva, y por que se puede re-derivar igual:
      · todas las demas celdas, en su posicion;
      · de la direccion, la ciudad, el estado y el ZIP -- se redacta SOLO la
        calle. Sin ellos un re-parseo perderia el ZIP, que es la respuesta a
        «donde trabaja» y que la tabla guarda igualmente por decision tomada;
      · el pie de paginacion, que es lo que dice si estan todas.

    Lo que se pierde de verdad es la capacidad de auditar a mano un nombre
    contra el volcado. Es el precio, y se paga a proposito: ECOA Regulation B.
    """
    filas = _celdas_por_fila(texto or "")
    salida = []
    for celdas in filas:
        if len(celdas) != len(COLUMNAS):
            # Una fila que no se leyo se redacta ENTERA: no se sabe que celda
            # es cual, asi que no se sabe cual lleva un nombre.
            salida.append("\t".join(REDACTADO for _ in celdas))
            continue
        c = list(celdas)
        pos = COLUMNAS.index("direccion")
        ciudad, estado, zip_ = _ciudad_zip(c[pos])
        c[pos] = ("%s, %s, %s, %s" % (REDACTADO, ciudad, estado, zip_)
                  if zip_ else REDACTADO)
        for campo in _A_REDACTAR:
            c[COLUMNAS.index(campo)] = REDACTADO
        salida.append("\t".join(c))

    pag = paginacion(texto or "")
    if pag.get("pie"):
        salida.append(_FIN_DE_LA_TABLA)
        salida.append(pag["pie"])
    return "\n".join(salida) + "\n"


def nombre_que_manda(celdas_por_fila, *, propuesto: str | None = None,
                     umbral: float = 0.9) -> tuple[str | None, str]:
    """Qué nombre se usa para decidir el lado, y por qué.

    El lado sale de en qué columna de agente aparece su nombre, así que un
    nombre que no calza deja TODAS las operaciones sin lado. Pasó: la base dice
    «XOCHIL ESCOBAR» y Model Match «Xochil Wendy Escobar», y sus 37 operaciones
    quedaron sin lado -- sin que nada fallara, porque «sin lado» es un estado
    legítimo.

    El que manda es el de la CAPTURA (`parseado.perfil.nombre` del Overview),
    porque al capturar se confirmó que es la misma persona. El del libro no se
    usa para esto nunca: es un volcado, viene en mayúsculas y sin el segundo
    nombre.

    Respaldo si ni ese calza: el nombre que aparece como Buyer o Listing Agent
    en el 90 % o más de las filas. Es él: en su propia tabla de transacciones,
    el agente que sale en casi todas es el dueño de la tabla.

    Devuelve `(nombre, motivo)`. El motivo se muestra: si el respaldo eligió,
    hay que poder ver cuál eligió y con qué respaldo.
    """
    filas = [f for f in celdas_por_fila if len(f) == len(COLUMNAS)]
    if not filas:
        return propuesto, "no hay filas completas de las que deducirlo"

    def _cuantas_con(nombre):
        n = 0
        for f in filas:
            d = dict(zip(COLUMNAS, f))
            if (_nombre_igual(_texto(d.get("agente_comprador")), nombre)
                    or _nombre_igual(_texto(d.get("agente_listing")), nombre)
                    or _nombre_igual(_texto(d.get("agente_colisting")), nombre)):
                n += 1
        return n

    if propuesto and _cuantas_con(propuesto) > 0:
        return propuesto, "el nombre de la captura de Model Match"

    # El respaldo: el agente que sale en casi todas las filas.
    cuenta: dict = {}
    for f in filas:
        d = dict(zip(COLUMNAS, f))
        for campo in ("agente_comprador", "agente_listing"):
            v = _texto(d.get(campo))
            if v:
                cuenta[v] = cuenta.get(v, 0) + 1
    if not cuenta:
        return propuesto, "las columnas de agente vienen vacías"
    nombre, n = max(cuenta.items(), key=lambda kv: kv[1])
    if n / float(len(filas)) >= umbral:
        return nombre, ("«%s» no aparece en ninguna fila; se usó «%s», que "
                        "sale como agente en %d de %d operaciones"
                        % (propuesto or "—", nombre, n, len(filas)))
    return propuesto, ("«%s» no aparece en ninguna fila y ningún agente sale "
                       "en el %d %% de ellas (el que más, «%s», en %d de %d)"
                       % (propuesto or "—", int(umbral * 100), nombre, n,
                          len(filas)))


def parsear_transacciones(crudo: str, *, realtor: str | None = None,
                          capturado_en: str | None = None) -> dict:
    """La pestaña pegada -> las operaciones, con su control de completitud.

    `realtor` es el nombre del agente: sin el, el LADO de cada fila queda en
    None y se declara, porque el lado sale de en que columna aparece su nombre
    y no hay otra forma de saberlo.
    """
    crudas = _celdas_por_fila(crudo or "")
    # QUÉ NOMBRE decide el lado. Ver `nombre_que_manda`: el de la base no se
    # usa nunca para esto, y si el de la captura no calza hay un respaldo que
    # se declara en el aviso.
    realtor, motivo_del_nombre = nombre_que_manda(crudas, propuesto=realtor)

    filas: list[dict] = []
    descartadas = 0
    no_leidas: list[dict] = []
    for celdas in crudas:
        if not _fecha(celdas[0] if celdas else ""):
            # El pie de paginacion no es una fila descartada: es el pie. Si se
            # contara, `lineas_descartadas` --que existe para avisar de que
            # algo no se leyo-- nunca bajaria de 1 y dejaria de significar algo.
            unido = " ".join(c for c in celdas if c).strip()
            if not unido or _RE_PIE.fullmatch(unido):
                continue
            descartadas += 1
            continue
        # 21 CELDAS EXACTAS O NO SE LEE. Rellenar una fila corta corre todas
        # las columnas desde donde falta: la tasa entra en el plazo, el lender
        # en el Sold Amount, y el resultado sale plausible.
        if len(celdas) != len(COLUMNAS):
            no_leidas.append({"fecha": _fecha(celdas[0]),
                              "celdas": len(celdas),
                              "esperadas": len(COLUMNAS)})
            continue
        filas.append(_fila(celdas, realtor=realtor, capturado_en=capturado_en))

    pag = paginacion(crudo or "")
    total = pag.get("total")
    leidas_y_no = len(filas) + len(no_leidas)
    faltan = bool(total) and leidas_y_no < total

    sin_lado = sum(1 for f in filas if not f.get("lado"))
    sin_estado = [f for f in filas if f["estado_prestamo"] == NO_LEIDO]
    financiadas_sin_lender = [
        f for f in filas
        if f["estado_prestamo"] == FINANCIADA
        and not (f.get("lender") or f.get("empleador"))]

    # ── LAS CONDICIONES DE «COMPLETA» ───────────────────────────────────────
    #
    # Antes miraba solo el pie, y el pie cuadraba: 25 filas de una celda cada
    # una son 25 filas. Con eso `completa` decia True sobre un parseo en el que
    # no se habia leido un solo campo.
    #
    # Una lectura completa es la que se puede USAR para el veredicto, y para
    # eso hacen falta estas: el pie cuadra, no hay filas sin leer, y toda fila
    # tiene lado. Nada mas.
    #
    # LO QUE YA NO BLOQUEA: que una compra financiada no traiga lender.
    # Decision de Isabella del 2026-09-24. Model Match no siempre trae el
    # originador, y bloquear por eso dejaba en `pendiente_modelmatch` a
    # catorce realtors cuya pestaña se habia leido ENTERA -- una fila sin
    # originador no impide decir si alguna operacion paso por la casa: si
    # pasara, el lender estaria ahi. La ausencia se cuenta y se muestra como
    # cobertura («27 de 28 con lender»), que es un dato para leer, no una
    # compuerta.
    razones: list[str] = []
    if faltan:
        razones.append("el pie dice %d operaciones y se leyeron %d"
                       % (total, leidas_y_no))
    if no_leidas:
        razones.append("%d filas sin leer" % len(no_leidas))
    if sin_estado:
        razones.append("%d filas sin poder decir si son loan o cash"
                       % len(sin_estado))
    if sin_lado:
        razones.append("%d operaciones sin lado" % sin_lado)

    if total is None:
        # Sin pie no se puede AFIRMAR que estan todas, aunque todo lo demas
        # cuadre. `None` no es `False`: no es que falten, es que no se sabe.
        completa = None
        razones.insert(0, "no se encontró el pie «1 - 25 of 25»")
    else:
        completa = not razones

    return {
        "version_parser": VERSION_PARSER_TX,
        "nombre_usado": realtor,
        "por_que_ese_nombre": motivo_del_nombre,
        "filas": filas,
        "leidas": len(filas),
        "no_leidas": no_leidas,
        "lineas_descartadas": descartadas,
        "paginacion": pag,
        "completa": completa,
        "faltan_paginas": faltan,
        "por_que_no_completa": razones,
        "aviso": (None if completa is True else
                  "no se pudo dar por completa la lectura de Transactions: %s"
                  % "; ".join(razones)),
        "sin_lado": sin_lado,
        "sin_estado_de_prestamo": len(sin_estado),
        # Ya no bloquea, y por eso mismo hay que poder verlo: el conteo y la
        # cobertura viajan, para que la ficha diga «27 de 28 con lender» en vez
        # de callarlo.
        "financiadas_sin_lender": len(financiadas_sin_lender),
        "cobertura_lender": _cobertura_lender(filas),
    }


def _cobertura_lender(filas: list[dict]) -> dict:
    """«27 de 28 con lender», sobre las FINANCIADAS.

    Sobre las financiadas y no sobre todas: una compra cash no tiene lender
    que falte, y meterla en el denominador convertiria una cartera con nueve
    cash en una cobertura del 60 % que no significa nada.
    """
    fin = [f for f in filas if f["estado_prestamo"] == FINANCIADA]
    con = [f for f in fin if (f.get("lender") or f.get("empleador"))]
    return {
        "financiadas": len(fin),
        "con_lender": len(con),
        "sin_lender_identificado": len(fin) - len(con),
        "texto": ("%d de %d con lender" % (len(con), len(fin))) if fin else "",
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
            NO_LEIDO: sum(1 for f in grupo
                          if f["estado_prestamo"] == NO_LEIDO),
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
        # Cuántas de esas financiadas traen originador. No bloquea la lectura
        # --decisión del 2026-09-24-- pero se cuenta y se muestra: «9 de 10 con
        # lender» y «1 sin lender identificado» dicen dos cosas distintas de
        # «9 buys con lender», y la segunda se lee como que hay nueve.
        "compras_sin_lender_identificado": sum(
            1 for f in financiadas_compra
            if not (f.get("lender") or f.get("empleador"))),
        "cobertura_lender_compra": _cobertura_lender(compras),
        "pendientes_de_prestamo": [
            {"fecha": f["fecha"], "lado": f["lado"],
             "dias": f["dias_desde_cierre"],
             "recapturar_despues_de": f["recapturar_despues_de"]}
            for f in pendientes],
        "zips_de_compra": _cuenta(f.get("zip") for f in compras),
        "tasas": sorted(f["tasa"] for f in financiadas_compra
                        if f.get("tasa") is not None),
        "avisos_de_suma": [f["aviso_suma"] for f in filas if f.get("aviso_suma")],
        # Precio y volumen sobre las que TIENEN precio, con su denominador al
        # lado: una mediana de 12 de 18 compras es una mediana de 12.
        "precio_mediano_compra": _mediana(f.get("precio") for f in compras),
        "volumen_compra": _suma(f.get("precio") for f in compras),
        "volumen_venta": _suma(f.get("precio") for f in ventas),
        "compras_con_precio": sum(1 for f in compras if f.get("precio")),
        # Las que no se pudieron clasificar. Nunca se reparten entre las otras.
        "sin_estado_de_prestamo": sum(1 for f in filas
                                      if f["estado_prestamo"] == NO_LEIDO),
    }


def _mediana(valores) -> float | None:
    v = sorted(x for x in valores if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def _suma(valores) -> float | None:
    v = [x for x in valores if x is not None]
    return sum(v) if v else None


def _por_lender(grupo: list[dict]) -> dict:
    """Los lenders del lado, AGRUPADOS por nombre sin sufijo societario.

    «Guaranteed Rate Inc» y «Guaranteed Rate, Inc.» son el mismo lender en dos
    columnas del mismo volcado. Contarlos aparte parte el reparto y hace que
    tres operaciones con el mismo lender parezcan tres lenders distintos.
    """
    return _cuenta(f.get("lender_agrupado") or f.get("lender")
                   for f in grupo if f["estado_prestamo"] == FINANCIADA)


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
