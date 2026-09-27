"""El Excel de los realtors con Instagram, con lo que trajo Model Match.

Seis hojas:
  1 Realtors      una fila por realtor, todo lo que se pudo sacar
  2 Lenders       una fila por (realtor, lender) -- formato largo, filtrable
  3 Originadores  idem con los LOs
  4 Companias     idem con las compañias hipotecarias
  5 Revisar       los que NO se encontraron o el match no es seguro
  6 Como leer     que significa cada columna, que costo y que NO esta

La hoja 5 existe por una razon: un match por nombre que nadie reviso se ve
igual que uno confirmado por correo, y actuar sobre el equivocado es peor que
no tener el dato. Todo lo dudoso sale de la hoja 1 y se concentra ahi.
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

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")
SALIDA = os.path.join(RAIZ, "data", "salida")

CABECERA = PatternFill("solid", fgColor="1F3864")
LETRA_CAB = Font(color="FFFFFF", bold=True, size=10)
AVISO = PatternFill("solid", fgColor="FCE4D6")
CAMBIO = PatternFill("solid", fgColor="FFF2CC")

#: (clave en el json, titulo, ancho, de donde sale, que significa).
#:
#: **El diccionario de campos se genera de ESTA tabla**, no se escribe aparte.
#: Un diccionario escrito a mano se desfasa la primera vez que alguien agrega
#: una columna, y entonces miente: dice que el archivo tiene unos campos y el
#: archivo tiene otros. Aqui no puede pasar -- si se agrega una columna sin
#: explicacion, la hoja del diccionario la muestra vacia y se ve.
#:
#: El orden ES la lectura: primero quienes somos nosotros, despues si lo
#: encontramos y con que seguridad, despues lo viejo contra lo nuevo, y al
#: final la produccion.
NUESTRO = "nuestra base (MMI / Salesforce)"
FICHA = "Model Match · ficha del agente"
APARTE = "Model Match · consulta aparte"
CALC = "calculado acá"

COLUMNAS = [
    ("nombre", "Realtor", 26, NUESTRO,
     "El nombre tal como está en nuestra base. Es el que se usó para buscar."),
    ("handle", "Instagram", 20, NUESTRO,
     "La cuenta de Instagram que le encontramos. Es el motivo por el que este "
     "realtor está en esta lista."),
    ("clase_ig", "Clase IG", 15, NUESTRO,
     "Qué tan utilizable es ese perfil de Instagram según la revisión que ya "
     "se hizo (p. ej. poca_evidencia, persona_equivocada)."),
    ("encontrado_txt", "¿En Model Match?", 15, CALC,
     "Si se pudo identificar a esta persona en Model Match. 'NO' significa "
     "que Model Match devolvió candidatos pero ninguno era identificable "
     "como ella, o que no devolvió ninguno."),
    ("match_criterio", "Cómo se identificó", 24, CALC,
     "Con qué dato se decidió que es la misma persona. Ver la hoja «Cómo "
     "leer esto»: email_exacto es la llave más fuerte."),
    ("confianza_final", "Confianza", 26, CALC,
     "Qué tan seguro es el match después de mirar también el teléfono. "
     "'alta' = confirmado por correo; 'alta · confirmada por teléfono' = el "
     "nombre no bastaba pero el teléfono cerró; 'contradicha por el "
     "teléfono' = revisar a mano."),
    ("telefono_coincide", "¿Teléfono coincide?", 16, CALC,
     "Si alguno de los teléfonos que ya teníamos aparece entre los de Model "
     "Match. Se compara sin el +1 ni guiones."),
    ("candidatos_n", "Candidatos vistos", 14, CALC,
     "Cuántos perfiles distintos devolvió Model Match al buscarlo. Un número "
     "alto con confianza baja quiere decir que hay homónimos."),
    ("mm_id", "ID Model Match", 22, FICHA,
     "El identificador estable del agente dentro de Model Match (mma_…). Es "
     "con lo que se vuelve a consultar sin ambigüedad."),

    ("brokerage_mmi", "Brokerage (MMI, viejo)", 30, NUESTRO,
     "La inmobiliaria que figuraba en nuestra base. Puede estar desactualizada."),
    ("mm_brokerage", "Brokerage (Model Match, hoy)", 32, FICHA,
     "La inmobiliaria que Model Match le asigna hoy."),
    ("cambio_de_brokerage", "¿Cambió de casa?", 14, CALC,
     "'si' cuando las dos anteriores no coinciden. Se compara normalizado "
     "(sin mayúsculas ni tildes) y por las primeras palabras, para que "
     "'Realty Concepts Ltd' y 'realty concepts, ltd. - fresno' no cuenten "
     "como cambio."),

    ("emails_mmi_txt", "Emails que ya teníamos", 34, NUESTRO,
     "Los correos de nuestra base, separados por '·'."),
    ("mm_emails_txt", "Emails en Model Match", 40, FICHA,
     "Todos los correos que trae Model Match. Ojo: los mete varios en un "
     "mismo campo separados por punto y coma, y suele conservar el del "
     "brokerage ANTERIOR."),
    ("mm_emails_n", "Nº emails", 9, CALC, "Cuántos correos distintos trae Model Match."),
    ("telefonos_mmi_txt", "Teléfonos que ya teníamos", 22, NUESTRO,
     "Los teléfonos de nuestra base, en formato +1…"),
    ("mm_telefonos_txt", "Teléfonos en Model Match", 34, FICHA,
     "Todos los teléfonos: el de la ficha más los de los perfiles "
     "duplicados. Mezcla celular y oficina sin distinguirlos."),
    ("mm_telefonos_n", "Nº teléfonos", 11, CALC, "Cuántos teléfonos distintos hay."),
    ("mm_perfiles_enlazados", "Perfiles enlazados", 12, FICHA,
     "Cuántos perfiles duplicados considera Model Match que son esta misma "
     "persona. De ahí salen los teléfonos y correos extra."),

    ("estado_mmi", "Estado (MMI)", 10, NUESTRO, "El estado que teníamos."),
    ("mm_ciudad", "Ciudad (MM)", 16, FICHA,
     "Su mercado principal según Model Match, que puede no ser donde tiene "
     "la oficina."),
    ("mm_estado", "Estado (MM)", 10, FICHA, "El estado de su mercado principal."),
    ("mm_zip", "ZIP (MM)", 9, FICHA, "El código postal de su mercado principal."),
    ("mm_licencia", "Licencia (MM)", 14, FICHA,
     "Número de licencia inmobiliaria. Model Match solo lo tiene para la "
     "mitad de los agentes, así que suele venir vacío."),

    ("unidades_mmi", "Unidades/año (MMI)", 14, NUESTRO,
     "Operaciones al año según nuestra base. Otra ventana y otra fecha que "
     "las de Model Match: no son comparables directamente."),
    ("rango_volumen_mmi", "Rango volumen (MMI)", 18, NUESTRO,
     "La banda de volumen que teníamos."),
    ("mm_unidades", "Unidades 12m (MM)", 14, FICHA,
     "Operaciones cerradas en los últimos 12 meses, los dos lados sumados."),
    ("mm_volumen", "Volumen 12m (MM)", 16, FICHA,
     "Dólares cerrados en los últimos 12 meses."),
    ("mm_precio_medio", "Precio medio", 13, FICHA,
     "Precio medio de venta de sus operaciones."),
    ("mm_compras_u", "Compras (u)", 11, FICHA,
     "Operaciones en las que representó al COMPRADOR. Es el lado que nos "
     "interesa: ahí es donde puede presentar un prestamista."),
    ("mm_compras_v", "Compras ($)", 14, FICHA, "Dólares del lado comprador."),
    ("mm_ventas_u", "Ventas (u)", 10, FICHA,
     "Operaciones en las que representó al VENDEDOR (listings)."),
    ("mm_ventas_v", "Ventas ($)", 14, FICHA, "Dólares del lado vendedor."),
    ("mm_dual_u", "Dual (u)", 9, FICHA,
     "Operaciones en las que representó a las dos partes."),

    ("mm_compras_financiadas_u", "Compras FINANCIADAS (u)", 19, FICHA,
     "De sus compras, cuántas se pagaron con hipoteca. **Es la cifra más "
     "precisa de cuántas presentaciones a un prestamista puede hacer al "
     "año.** Este dato no lo teníamos a mano."),
    ("mm_compras_financiadas_v", "Compras financiadas ($)", 19, FICHA,
     "Dólares de esas compras financiadas."),
    ("mm_ventas_financiadas_u", "Ventas financiadas (u)", 18, FICHA,
     "Listings suyos cuyo comprador financió."),
    ("mm_pct_unidades_financiadas", "% unidades financiadas", 18, FICHA,
     "Qué parte de sus operaciones lleva hipoteca. Bajo = libro con mucho "
     "efectivo, y ahí hay menos que hacer."),
    ("mm_pct_volumen_financiado", "% volumen financiado", 17, FICHA,
     "Lo mismo medido en dólares."),
    ("mm_loan_medio", "Loan medio de sus compradores", 22, FICHA,
     "Préstamo promedio de sus operaciones financiadas: en qué banda de "
     "precio piden prestado sus compradores."),

    ("hace_fha", "¿Produce FHA?", 12, APARTE,
     "Tiene al menos una operación FHA en 24 meses. Es un sí/no, NO una "
     "proporción (ver la advertencia en «Cómo leer esto»)."),
    ("hace_convencional", "¿Produce convencional?", 16, APARTE,
     "Tiene al menos una operación convencional en 24 meses."),
    ("hace_va", "¿Produce VA?", 11, APARTE,
     "Tiene al menos una operación VA en 24 meses."),
    ("trabaja_con_la_casa", "¿Ya financia con la casa?", 18, APARTE,
     "'SÍ' = alguna de sus operaciones se financió con Everett Financial "
     "(NMLS 2129, que opera como Supreme Lending), en todo el historial. Es "
     "la exclusión por no-canibalización: ese realtor ya tiene relación con "
     "la casa."),
    ("ops_con_la_casa", "Operaciones con la casa (al menos)", 22, APARTE,
     "Cuántas de sus operaciones financió la casa, medido por tramos: 1, 2, "
     "3, 5, 10 o 20. Un '1' es una relación suelta y un '10' es una "
     "relación de verdad, y hasta ahora los dos se veían igual. Está "
     "comprobado contra Armando Ochoa, que tiene 3 en su tabla cruda de "
     "lenders y cae exactamente en el tramo 3."),
    ("mm_lenders_n", "Nº lenders", 10, FICHA,
     "Con cuántos prestamistas DISTINTOS se financiaron sus operaciones. "
     "Pocos = depende de uno; muchos = reparte."),
    ("mm_originadores_n", "Nº originadores", 13, FICHA,
     "Con cuántos loan officers distintos trabajó. Uno solo es el caso más "
     "interesante para desplazar; muchos, el más fácil de entrar."),
    ("fidelidad", "¿Fidelizado con un LO?", 24, CALC,
     "Lectura del número de loan officers. 'CAUTIVO' = uno solo. En los que "
     "tienen el desglose se comprobó que con 1-3 LOs la concentración media "
     "es del 79 % y con 4 o más baja al 43 %, así que el conteo —que es "
     "gratis— sirve de indicador."),
    ("lo_principal", "Su loan officer principal", 28, APARTE,
     "El nombre del LO por el que pasa la mayor parte de sus préstamos. Solo "
     "está donde se compró el desglose: los de 1-3 LOs, que son los que "
     "importan para desplazar."),
    ("lo_principal_pct", "% por su LO principal", 16, CALC,
     "Qué parte de sus préstamos pasa por ese LO. Se calcula como sus "
     "unidades sobre la SUMA de todos sus LOs. Ojo: NO se usa el 'pctUnits' "
     "que devuelve la API, porque su denominador no son las operaciones del "
     "agente y llega a dar 167 %."),
    ("mm_companias_n", "Nº compañías", 12, FICHA,
     "Con cuántas compañías hipotecarias distintas trató."),
    ("lenders_txt", "Lenders (si cupo en el tope)", 40, APARTE,
     "Los prestamistas por nombre, con sus unidades. Solo se pidió donde "
     "cabía en el tope de 5 créditos: cuesta 1 crédito por prestamista, así "
     "que en la mayoría dice 'no consultado' y queda el conteo de al lado."),
    ("originators_txt", "Originadores (si cupo)", 40, APARTE,
     "Los loan officers por nombre, con la misma limitación."),

    ("creditos_gastados", "Créditos gastados", 13, CALC,
     "Lo que costó este realtor. El tope acordado era 5."),
    ("consultado_en", "Consultado", 20, CALC,
     "Cuándo se pidió el dato a Model Match (UTC)."),
    ("realtor_id", "realtor_id", 36, NUESTRO,
     "Su identificador en nuestra base, para cruzar con el resto del sistema."),
    ("sf_lead_id", "sf_lead_id", 18, NUESTRO, "Su identificador en Salesforce."),
]

#: Los campos de las hojas largas, que no salen de COLUMNAS.
COLUMNAS_LARGAS = [
    ("Realtor", "El realtor de nuestra lista."),
    ("ID Model Match", "Su identificador en Model Match."),
    ("Instagram", "Su cuenta de Instagram."),
    ("Lender / Originador / Compania",
     "El nombre tal como lo escribe la fuente, sin normalizar. Puede venir "
     "con variantes del mismo nombre."),
    ("Unidades", "Cuántas operaciones suyas pasaron por ahí."),
    ("Volumen", "Cuántos dólares."),
    ("% unidades", "Qué parte de sus operaciones. Es la medida de peso real "
                   "de esa relación."),
    ("% volumen", "Qué parte de sus dólares."),
]


#: Los que ya financian con Everett Financial (la casa). Se calcula aparte,
#: con `footprint`, porque preguntarle a cada agente su lista de lenders
#: cuesta 1 por fila y la pregunta inversa solo cobra los que dan positivo.
EVERETT = os.path.join(RAIZ, "data", "trabajo", "everett.json")

#: El mix de tipo de prestamo. SOLO se usan las consultas de umbral 0 --«hace
#: algo de esto»--, que estan validadas contra el conteo real de prestamos de
#: Ana: 3 FHA, 12 convencionales, 0 VA, y las tres banderas coinciden.
#:
#: Las bandas por `shareOfUnits` NO se usan: no miden la proporcion del
#: agente sino la de un bucket de lender, y Ana aparece en «>=50% FHA» cuando
#: su proporcion real es 20%. Estan en el archivo y se ignoran a proposito.
MIX = os.path.join(RAIZ, "data", "trabajo", "mix_prestamos.json")
TIPOS = (("fha", "fha"), ("convencional", "convencional"), ("va", "va"))


def cargar() -> list[dict]:
    con_la_casa = set()
    if os.path.exists(EVERETT):
        with open(EVERETT, encoding="utf-8") as fh:
            con_la_casa = {c.get("mm_id") for c in json.load(fh)}
    peso: dict[str, dict] = {}
    ruta_peso = os.path.join(RAIZ, "data", "trabajo", "everett_peso.json")
    if os.path.exists(ruta_peso):
        with open(ruta_peso, encoding="utf-8") as fh:
            peso = json.load(fh)["peso"]
    mix: dict[str, set] = {}
    if os.path.exists(MIX):
        with open(MIX, encoding="utf-8") as fh:
            crudo = json.load(fh)["resultado"]
        mix = {clave: set(crudo.get(clave) or []) for _, clave in TIPOS}
    filas = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            f = json.load(fh)
        f["trabaja_con_la_casa"] = (
            "sin comprobar" if not f.get("mm_id")
            else ("SÍ" if f["mm_id"] in con_la_casa else "no"))
        f["ops_con_la_casa"] = (peso.get(f.get("mm_id") or "") or {}).get(
            "al_menos") or ("" if f["trabaja_con_la_casa"] != "SÍ" else None)
        for nombre, clave in TIPOS:
            f["hace_%s" % nombre] = (
                "sin comprobar" if not (f.get("mm_id") and mix)
                else ("sí" if f["mm_id"] in mix.get(clave, ()) else "no"))
        filas.append(f)
    return filas


def confianza_final(f: dict) -> str:
    """La confianza DESPUES de mirar el telefono.

    La del extractor se decide con lo que trae instant-search, que no incluye
    telefono. Pero la ficha si lo trae, y un telefono que coincide confirma
    una identificacion hecha solo por nombre tan bien como lo haria el correo:
    dejarla en «media» mandaria a revision manual a gente ya confirmada.

    Y al reves: un telefono que NO coincide baja la confianza aunque el nombre
    y el estado calcen, porque es justo la señal de que son dos personas.
    """
    if not f.get("encontrado"):
        return "no encontrado"
    # El correo es llave DURA: si coincide, un telefono distinto no dice que
    # sea otra persona, dice que Model Match tiene otro numero --el de la
    # oficina, o uno viejo--. Andro Chavez coincide por correo y tiene tres
    # telefonos en Model Match, ninguno el nuestro; sigue siendo el.
    if str(f.get("match_criterio", "")).startswith("email_exacto"):
        return "alta"
    if f.get("telefono_coincide") == "no":
        return "contradicha por el teléfono"
    if f.get("telefono_coincide") == "si":
        return "alta · confirmada por teléfono"
    return f.get("match_confianza") or "ninguna"


def preparar(f: dict) -> dict:
    """Las columnas derivadas: listas a texto y lo que se lee de un vistazo."""
    d = dict(f)
    d["encontrado_txt"] = "sí" if f.get("encontrado") else "NO"
    d["confianza_final"] = confianza_final(f)
    for clave, destino in (("emails_mmi", "emails_mmi_txt"),
                           ("mm_emails", "mm_emails_txt"),
                           ("telefonos_mmi", "telefonos_mmi_txt"),
                           ("mm_telefonos", "mm_telefonos_txt")):
        d[destino] = " · ".join(f.get(clave) or [])
    n = f.get("mm_originadores_n")
    d["fidelidad"] = (
        "" if not isinstance(n, int) else
        "CAUTIVO · 1 solo LO" if n <= 1 else
        "muy concentrado · 2-3 LOs" if n <= 3 else
        "concentrado · 4-6 LOs" if n <= 6 else
        "reparte · 7-12 LOs" if n <= 12 else
        "reparte mucho · 13+ LOs")
    # El LO principal, con el denominador correcto: la suma de SUS LOs.
    orig = f.get("mm_originators")
    d["lo_principal"] = d["lo_principal_pct"] = ""
    if orig:
        total = sum(x.get("unidades") or 0 for x in orig)
        if total:
            top = max(orig, key=lambda x: x.get("unidades") or 0)
            d["lo_principal"] = top.get("nombre")
            d["lo_principal_pct"] = round(
                100.0 * (top.get("unidades") or 0) / total)
    d["mm_emails_n"] = len(f.get("mm_emails") or [])
    d["mm_telefonos_n"] = len(f.get("mm_telefonos") or [])
    for b, destino in (("lenders", "lenders_txt"),
                       ("originators", "originators_txt")):
        v = f.get("mm_%s" % b)
        if v is None:
            d[destino] = "no consultado · %s" % (f.get("mm_%s_motivo" % b) or "")
        else:
            d[destino] = " · ".join(
                "%s (%s u)" % (x.get("nombre"), x.get("unidades")) for x in v)
    for k in ("mm_pct_unidades_financiadas", "mm_pct_volumen_financiado"):
        if isinstance(d.get(k), (int, float)):
            d[k] = round(d[k], 1)
    return d


def escribir_hoja(ws, titulos, anchos, filas):
    ws.append(titulos)
    for c in ws[1]:
        c.fill, c.font = CABECERA, LETRA_CAB
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30
    for i, an in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(i)].width = an
    for fila in filas:
        ws.append(fila)
    ws.freeze_panes = "A2"
    if filas:
        ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(titulos)),
                                          len(filas) + 1)


def main() -> None:
    crudas = cargar()
    if not crudas:
        raise SystemExit("no hay resultados en %s" % DIR)
    filas = [preparar(f) for f in crudas]
    filas.sort(key=lambda f: -(f.get("mm_compras_financiadas_u") or 0))

    # Lo dudoso NO va en la hoja principal: va a Revisar, y se dice por que.
    def dudoso(f):
        if not f.get("encontrado"):
            return "no se encontró en Model Match"
        # Identificado por correo: no se revisa. El correo ya lo confirma.
        if str(f.get("match_criterio", "")).startswith("email_exacto"):
            return None
        if f.get("telefono_coincide") == "no":
            return ("identificado solo por nombre y el teléfono NO coincide: "
                    "puede ser otra persona con el mismo nombre")
        # Una identificacion floja que el telefono confirma NO es dudosa.
        if (f.get("match_confianza") in ("baja", "ninguna")
                and f.get("telefono_coincide") != "si"):
            return "identificado solo por nombre, sin confirmar con correo ni teléfono"
        return None

    buenas = [f for f in filas if not dudoso(f)]
    revisar = [f for f in filas if dudoso(f)]

    wb = Workbook()

    ws = wb.active
    ws.title = "Realtors"
    escribir_hoja(ws, [c[1] for c in COLUMNAS], [c[2] for c in COLUMNAS],
                  [[f.get(c[0]) for c in COLUMNAS] for f in buenas])
    # Pintar el cambio de casa: es el hallazgo que el pedido venia a buscar.
    col_cambio = [c[0] for c in COLUMNAS].index("cambio_de_brokerage") + 1
    for i, f in enumerate(buenas, 2):
        if f.get("cambio_de_brokerage") == "si":
            ws.cell(row=i, column=col_cambio).fill = CAMBIO

    for hoja, clave in (("Lenders", "mm_lenders"),
                        ("Originadores", "mm_originators"),
                        ("Companias", "mm_companies")):
        largo = []
        for f in filas:
            for x in (f.get(clave) or []):
                largo.append([f.get("nombre"), f.get("mm_id"), f.get("handle"),
                              x.get("nombre"), x.get("unidades"),
                              x.get("volumen"),
                              round((x.get("pct_unidades") or 0) * 100, 1),
                              round((x.get("pct_volumen") or 0) * 100, 1)])
        largo.sort(key=lambda r: (r[0] or "", -(r[4] or 0)))
        escribir_hoja(wb.create_sheet(hoja),
                      ["Realtor", "ID Model Match", "Instagram",
                       hoja[:-1] if hoja.endswith("s") else hoja,
                       "Unidades", "Volumen", "% unidades", "% volumen"],
                      [26, 22, 18, 38, 10, 14, 11, 11], largo)

    ws = wb.create_sheet("Revisar")
    escribir_hoja(
        ws,
        ["Realtor", "Instagram", "Por qué hay que revisarlo",
         "Cómo se identificó", "Confianza", "¿Teléfono coincide?",
         "Emails que teníamos", "Emails en Model Match",
         "Candidatos que devolvió Model Match", "realtor_id"],
        [26, 20, 42, 24, 10, 16, 34, 34, 70, 36],
        [[f.get("nombre"), f.get("handle"), dudoso(f), f.get("match_criterio"),
          f.get("match_confianza"), f.get("telefono_coincide"),
          f.get("emails_mmi_txt"), f.get("mm_emails_txt"),
          " || ".join("%s · %s · %s %s · %s" % (
              c.get("nombre"), c.get("office"), c.get("ciudad"),
              c.get("estado"), c.get("email"))
              for c in (f.get("candidatos") or [])[:6]),
          f.get("realtor_id")] for f in revisar])
    for i in range(2, len(revisar) + 2):
        ws.cell(row=i, column=3).fill = AVISO

    # ── el diccionario, generado de COLUMNAS y no escrito aparte ───────────
    ws = wb.create_sheet("Diccionario de campos")
    dicc = [["Hoja", "Campo", "De dónde sale", "Qué significa"]]
    faltan = []
    for clave, titulo, _ancho, fuente, significado in COLUMNAS:
        dicc.append(["Realtors", titulo, fuente, significado])
        if not significado:
            faltan.append(titulo)
    for titulo, significado in COLUMNAS_LARGAS:
        dicc.append(["Lenders / Originadores / Companias", titulo,
                     APARTE, significado])
    for titulo, significado in (
            ("Por qué hay que revisarlo",
             "El motivo concreto por el que este realtor no entró en la hoja "
             "principal."),
            ("Candidatos que devolvió Model Match",
             "Los perfiles que Model Match propuso, con inmobiliaria, ciudad "
             "y correo, para decidir a mano cuál es. Van separados por '||'.")):
        dicc.append(["Revisar", titulo, CALC, significado])

    escribir_hoja(ws, dicc[0], [34, 30, 30, 86], dicc[1:])
    for fila in ws.iter_rows(min_row=2, max_col=4):
        fila[3].alignment = Alignment(wrap_text=True, vertical="top")
        fila[1].font = Font(bold=True, size=10)
    if faltan:
        print("⚠ campos sin explicación: %s" % ", ".join(faltan))
    print("diccionario     : %d campos" % (len(dicc) - 1))

    # ── la hoja que explica, que es la que evita que alguien lea mal ────────
    con_cambio = sum(1 for f in buenas if f.get("cambio_de_brokerage") == "si")
    creditos = sum(f.get("creditos_gastados") or 0 for f in filas)
    notas = [
        ["Qué es esto", ""],
        ["", "Los %d realtors a los que les buscamos Instagram, cruzados "
             "contra Model Match el %s."
         % (len(filas), dt.date.today().isoformat())],
        ["", "%d quedaron con match confiable y %d hay que revisarlos a mano "
             "(hoja Revisar)." % (len(buenas), len(revisar))],
        ["", "%d cambiaron de brokerage desde lo que teníamos de MMI."
         % con_cambio],
        ["", ""],
        ["Cómo se identificó a cada uno", ""],
        ["email_exacto", "Uno de los correos que ya teníamos aparece en la "
                         "ficha de Model Match. Es la llave más fuerte."],
        ["email_exacto_varios_perfiles",
         "El correo coincide en más de un perfil de Model Match (son perfiles "
         "duplicados del mismo agente). Se tomó el de más volumen."],
        ["nombre_exacto_y_estado",
         "El correo no coincidió con ninguno, pero hay un único agente con "
         "ese nombre exacto en ese estado."],
        ["nombre_exacto_sin_estado / ambiguo / sin_candidatos",
         "No alcanza para afirmar que es la misma persona. Va a Revisar, "
         "salvo que el teléfono lo confirme."],
        ["¿Teléfono coincide?",
         "Se comprueba DESPUÉS de identificarlo, contra el teléfono que ya "
         "teníamos, porque la búsqueda no devuelve teléfonos. Un 'sí' "
         "confirma una identificación hecha solo por nombre; un 'no' la "
         "manda a Revisar aunque el nombre y el estado calcen, porque es "
         "justo la señal de que son dos personas distintas."],
        ["", ""],
        ["Qué NO está acá, y por qué", ""],
        ["Las transacciones una por una",
         "La pestaña Transactions de Model Match no existe en la API: los "
         "préstamos no conocen al agente y las ventas solo lo traen como "
         "nombre en búsqueda difusa, con los ids en null. Eso se sigue "
         "pegando a mano."],
        ["Los lenders y originadores de todos",
         "Esos listados cuestan 1 crédito POR FILA. Un agente con 43 lenders "
         "cuesta 43 créditos. Con el tope de 5 créditos por realtor solo se "
         "pidieron donde cabían; en el resto queda el CONTEO, que sí viene "
         "gratis con la ficha. Pedir la tabla de lenders de los 298 costaría "
         "unos 3.500 créditos."],
        ["¿Ya financia con la casa?",
         "Esta sí se pudo contestar para todos, y barata: en vez de "
         "preguntarle a cada agente con quién trabaja (1 crédito por lender), "
         "se le preguntó a Everett Financial (NMLS 2129, que opera como "
         "Supreme Lending) quiénes de esta lista financiaron con ella. Solo "
         "cobra los que dan positivo. Un 'SÍ' significa que ese realtor YA "
         "tiene relación con la casa: es la exclusión por no-canibalización."],
        ["¿Produce FHA / convencional / VA?",
         "Es un SÍ/NO: tiene al menos una operación de ese tipo en los "
         "últimos 24 meses. Está validado contra el conteo real de préstamos "
         "de Ana Osorio (3 FHA, 12 convencionales, 0 VA) y las tres banderas "
         "coinciden."],
        ["⚠ Lo que NO dice: la proporción",
         "No hay forma barata de saber QUÉ PARTE de su producción es FHA. Se "
         "intentó con bandas de porcentaje y no sirven: miden la proporción "
         "dentro de un lender, no la del agente. Ana aparece en la banda "
         "'≥50% FHA' cuando su proporción real es 20%. Por eso esas bandas "
         "no están en esta hoja. La proporción real se saca contando los "
         "préstamos de sus propiedades, y eso cuesta ~30 créditos por "
         "realtor."],
        ["⚠ La ventana cambia la respuesta",
         "Mirando solo los últimos 24 meses dan 28. Mirando TODO el "
         "historial dan 79. Los 51 de diferencia financiaron con la casa "
         "hace más de dos años, y para una exclusión eso sigue contando: la "
         "columna usa el historial completo. Se comprobó que la diferencia "
         "es la ventana y no la lista de nombres de Everett — con la lista "
         "corregida y 24 meses vuelven a salir los mismos 28."],
        ["", ""],
        ["Lo que costó", ""],
        ["Modelo de costo (medido, no estimado)",
         "instant-search 0 · ficha del agente 1 · listados 1 por fila."],
        ["Créditos gastados en total", creditos],
        ["Tope respetado", "5 créditos por realtor, comprobado antes de cada "
                           "pedido y no después."],
        ["", ""],
        ["Ventana de los datos de Model Match", "Últimos 12 meses."],
        ["Advertencia", "Los datos de contacto son de uso comercial interno. "
                        "No se comparten fuera del equipo."],
    ]
    ws = wb.create_sheet("Cómo leer esto")
    escribir_hoja(ws, ["Concepto", "Qué significa"], [38, 112], notas)
    for fila in ws.iter_rows(min_row=2, max_col=2):
        fila[1].alignment = Alignment(wrap_text=True, vertical="top")
        if fila[0].value and not fila[1].value:
            fila[0].font = Font(bold=True, size=11)

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, "realtors_instagram_model_match.xlsx")
    try:
        wb.save(ruta)
    except PermissionError:
        # Windows bloquea el archivo mientras Excel lo tiene abierto. Guardar
        # al lado es mejor que perder la corrida: el usuario decide cual se
        # queda, y se le DICE, en vez de fallar callado o pisar a medias.
        ruta = os.path.join(SALIDA, "realtors_instagram_model_match_%s.xlsx"
                            % dt.datetime.now().strftime("%H%M"))
        wb.save(ruta)
        print("⚠ el archivo principal estaba abierto en Excel; se guardo al lado")
    print("hoja Realtors : %d" % len(buenas))
    print("hoja Revisar  : %d" % len(revisar))
    print("cambios de casa: %d" % con_cambio)
    print("creditos       : %d" % creditos)
    print("guardado en %s" % ruta)


if __name__ == "__main__":
    main()
