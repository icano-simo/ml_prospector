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

#: (clave en el json, titulo de la columna, ancho). El orden ES la lectura:
#: primero quienes somos nosotros, despues si lo encontramos y con que
#: seguridad, despues lo viejo, despues lo nuevo, y al final la produccion.
COLUMNAS = [
    ("nombre", "Realtor", 26),
    ("handle", "Instagram", 20),
    ("clase_ig", "Clase IG", 15),
    ("encontrado_txt", "¿En Model Match?", 15),
    ("match_criterio", "Cómo se identificó", 24),
    ("confianza_final", "Confianza", 26),
    ("telefono_coincide", "¿Teléfono coincide?", 16),
    ("candidatos_n", "Candidatos vistos", 14),
    ("mm_id", "ID Model Match", 22),

    ("brokerage_mmi", "Brokerage (MMI, viejo)", 30),
    ("mm_brokerage", "Brokerage (Model Match, hoy)", 32),
    ("cambio_de_brokerage", "¿Cambió de casa?", 14),

    ("emails_mmi_txt", "Emails que ya teníamos", 34),
    ("mm_emails_txt", "Emails en Model Match", 40),
    ("mm_emails_n", "Nº emails", 9),
    ("telefonos_mmi_txt", "Teléfonos que ya teníamos", 22),
    ("mm_telefonos_txt", "Teléfonos en Model Match", 34),
    ("mm_telefonos_n", "Nº teléfonos", 11),
    ("mm_perfiles_enlazados", "Perfiles enlazados", 12),

    ("estado_mmi", "Estado (MMI)", 10),
    ("mm_ciudad", "Ciudad (MM)", 16),
    ("mm_estado", "Estado (MM)", 10),
    ("mm_zip", "ZIP (MM)", 9),
    ("mm_licencia", "Licencia (MM)", 14),

    ("unidades_mmi", "Unidades/año (MMI)", 14),
    ("rango_volumen_mmi", "Rango volumen (MMI)", 18),
    ("mm_unidades", "Unidades 12m (MM)", 14),
    ("mm_volumen", "Volumen 12m (MM)", 16),
    ("mm_precio_medio", "Precio medio", 13),
    ("mm_compras_u", "Compras (u)", 11),
    ("mm_compras_v", "Compras ($)", 14),
    ("mm_ventas_u", "Ventas (u)", 10),
    ("mm_ventas_v", "Ventas ($)", 14),
    ("mm_dual_u", "Dual (u)", 9),

    ("mm_compras_financiadas_u", "Compras FINANCIADAS (u)", 19),
    ("mm_compras_financiadas_v", "Compras financiadas ($)", 19),
    ("mm_ventas_financiadas_u", "Ventas financiadas (u)", 18),
    ("mm_pct_unidades_financiadas", "% unidades financiadas", 18),
    ("mm_pct_volumen_financiado", "% volumen financiado", 17),
    ("mm_loan_medio", "Loan medio de sus compradores", 22),

    ("mm_lenders_n", "Nº lenders", 10),
    ("mm_originadores_n", "Nº originadores", 13),
    ("mm_companias_n", "Nº compañías", 12),
    ("lenders_txt", "Lenders (si cupo en el tope)", 40),
    ("originators_txt", "Originadores (si cupo)", 40),

    ("creditos_gastados", "Créditos gastados", 13),
    ("consultado_en", "Consultado", 20),
    ("realtor_id", "realtor_id", 36),
    ("sf_lead_id", "sf_lead_id", 18),
]


def cargar() -> list[dict]:
    filas = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            filas.append(json.load(fh))
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
    escribir_hoja(ws, [t for _, t, _ in COLUMNAS], [a for _, _, a in COLUMNAS],
                  [[f.get(k) for k, _, _ in COLUMNAS] for f in buenas])
    # Pintar el cambio de casa: es el hallazgo que el pedido venia a buscar.
    col_cambio = [k for k, _, _ in COLUMNAS].index("cambio_de_brokerage") + 1
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
         "gratis con la ficha."],
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
    wb.save(ruta)
    print("hoja Realtors : %d" % len(buenas))
    print("hoja Revisar  : %d" % len(revisar))
    print("cambios de casa: %d" % con_cambio)
    print("creditos       : %d" % creditos)
    print("guardado en %s" % ruta)


if __name__ == "__main__":
    main()
