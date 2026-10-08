"""El Excel de los realtors con Instagram, con lo que trajo Model Match.

Ocho hojas:
  1 Realtors                una fila por realtor, todo lo que se pudo sacar
  2 Lenders                 una fila por (realtor, lender) -- formato largo
  3 Originadores            idem con los LOs
  4 Companias               idem con las compañias hipotecarias
  5 Revisar                 los que NO se encontraron o el match no es seguro
  6 Diccionario de campos   columna por columna: que es y que costo
  7 Como interpretar        como se leen juntos, no solo uno a uno
  8 Como leer esto          los limites y las trampas de lectura

Las hojas 2, 3 y 4 son de la corrida vieja, la unica que pago los breakdowns.
El minado de hoy no los pide --cuestan 1 por fila-- asi que no crecen, y la 4
queda siempre vacia. Se dejan porque lo ya pagado sigue siendo valido.

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
    ("revisar_por", "⚠ Revisar porque…", 40, CALC,
     "Vacío = el match es confiable y la fila se puede usar. Con texto = hay "
     "una razón concreta para no fiarse todavía, y está escrita. Estas filas "
     "también están sueltas en la hoja Revisar, con los candidatos."),
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

    ("mm_ultima_operacion", "Última operación", 13, FICHA,
     "Fecha de su última operación cerrada. **Es la única señal de recencia "
     "que hay**: dice si sigue activo o lleva meses sin cerrar. Viene en la "
     "ficha y hasta ahora se tiraba."),
    ("mm_licencias", "Licencias (todas)", 34, FICHA,
     "Todas sus licencias inmobiliarias con su estado y vencimiento. Un "
     "agente puede tener varias, de varios estados. Vacío en buena parte de "
     "la lista: vacío es «no lo sabe», no «no tiene»."),
    ("mm_estados_licencia", "Estados con licencia", 16, FICHA,
     "En qué estados está habilitado para operar. Distinto de dónde produce."),
    ("mm_licencia_vence", "Licencia vence", 13, FICHA,
     "El vencimiento más próximo. Una fecha cercana puede ser señal de que "
     "está por dejar la actividad."),
    ("mm_precio_medio_compras", "Precio medio de sus COMPRAS", 20, CALC,
     "Volumen comprador ÷ unidades compradoras. Distinto de `Precio medio`, "
     "que mezcla los dos lados: éste es el precio de las casas que compran "
     "sus clientes, que es la banda que nos importa."),
    ("mm_precio_medio_compras_fin", "Precio medio de sus compras financiadas",
     22, CALC,
     "Lo mismo, solo sobre las que llevaron hipoteca. Es el precio real de "
     "quien necesita préstamo."),
    ("mm_precio_medio_listings", "Precio medio de sus listings", 20, CALC,
     "Volumen vendedor ÷ unidades vendedoras."),
    ("mm_total_listado", "Suma de precios de listado", 18, FICHA,
     "Lo que pidió por todo lo que listó, sumado."),
    ("mm_venta_vs_listado", "Venta vs listado (%)", 16, CALC,
     "Precio de venta ÷ precio de listado, en porcentaje. Por debajo de 100 "
     "vende con descuento sobre lo que pide; por encima, con competencia. "
     "Dice cómo negocia."),
    ("mm_ventas_financiadas_v", "Ventas financiadas ($)", 18, FICHA,
     "Dólares de sus listings cuyo comprador financió. Completa el par con "
     "las unidades, que ya traíamos."),
    ("mm_dual_v", "Dual ($)", 12, FICHA,
     "Dólares de doble agencia."),
    ("mm_dual_financiadas_u", "Dual financiadas (u)", 16, FICHA,
     "Operaciones de doble agencia que llevaron hipoteca. Suele ser 0."),
    ("mm_dual_financiadas_v", "Dual financiadas ($)", 16, FICHA,
     "Sus dólares. Suele ser 0."),

    ("hace_fha", "¿Produce FHA?", 12, APARTE,
     "Tiene al menos una operación FHA en 24 meses. Es un sí/no, NO una "
     "proporción (ver la advertencia en «Cómo leer esto»)."),
    ("hace_convencional", "¿Produce convencional?", 16, APARTE,
     "Tiene al menos una operación convencional en 24 meses."),
    ("hace_va", "¿Produce VA?", 11, APARTE,
     "Tiene al menos una operación VA en 24 meses."),
    ("everett_historico", "¿Trabajó con Everett · histórico?", 20, APARTE,
     "'SÍ' = alguna de sus operaciones la financió Everett Financial (NMLS "
     "2129, que opera como Supreme Lending), en **todo el historial**. Es la "
     "exclusión por no-canibalización."),
    ("everett_u_historico", "Operaciones con Everett · histórico", 22, APARTE,
     "Cuántas, en todo el historial. Exacto hasta 4 y por bandas arriba. Un "
     "'1' es una relación suelta; un '20-49' es una relación de verdad, y "
     "hasta ahora las dos se veían igual."),
    ("everett_12m", "¿Trabajó con Everett · 12 meses?", 20, APARTE,
     "La misma pregunta, **solo en los últimos 12 meses**. Es la que dice si "
     "la relación está VIVA. De 136 con relación histórica, solo 21 la "
     "tienen en 12 meses: 115 están excluidos hoy por algo que ya no pasa."),
    ("everett_u_12m", "Operaciones con Everett · 12 meses", 22, APARTE,
     "Cuántas en los últimos 12 meses."),
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
    ("mm_companias_n", "Nº compañías", 12, FICHA,
     "Con cuántas compañías hipotecarias distintas trató."),
    ("historical_units_txt", "Historical units · por año", 40, APARTE,
     "Unidades del lado comprador, año por año, desde 2017. Sale de contar, "
     "que no cobra. El año en curso NO se pide como año literal —devuelve "
     "0 aunque haya producción— sino como `yearToDate`."),
    ("primer_anio", "Primer año con producción", 16, CALC,
     "El año más viejo con unidades. Si dice 2017, está topado: es el año "
     "más antiguo que acepta la API y su primera operación puede ser anterior."),
    ("anios_produciendo", "Años con producción", 14, CALC,
     "En cuántos años distintos cerró al menos una operación."),
    ("antiguedad_aprox", "Antigüedad aproximada (años)", 18, CALC,
     "Año en curso − primer año + 1. **Aproximada**: es un piso, no la fecha "
     "en que empezó. Model Match no tiene antigüedad de agentes; esto se "
     "deriva de su producción, que es más exigente porque obliga a que "
     "estuviera cerrando, no solo habilitado."),

    ("creditos_gastados", "Créditos gastados", 13, CALC,
     "Lo que costó este realtor. El tope es 1: la ficha es la única llamada "
     "que cobra. Un 2 acá significa que se le compró la ficha dos veces."),
    ("consultado_en", "Consultado", 20, CALC,
     "Cuándo se pidió el dato a Model Match (UTC)."),
    ("realtor_id", "realtor_id", 36, NUESTRO,
     "Su identificador en nuestra base, para cruzar con el resto del sistema."),
    ("sf_lead_id", "sf_lead_id", 18, NUESTRO, "Su identificador en Salesforce."),
]

IG = "Instagram · scraping propio"

#: Que significa cada señal de Instagram. Las claves sin descripcion salen
#: igual en la tabla --el pedido es que este TODO-- pero el generador avisa,
#: para que no se cuele una columna muda.
DESC_IG = {
    "ig_handle": "La cuenta.",
    "ig_estado_perfil": "Si el perfil se pudo leer (público, privado, no encontrado…).",
    "ig_estado_evidencia": "En qué se basó ese estado.",
    "ig_handle_confianza": "Qué tan seguro es que la cuenta sea de esta persona.",
    "ig_captions_n": "Cuántos textos de publicaciones se leyeron.",
    "ig_comentarios_n": "Cuántos comentarios se leyeron.",
    "ig_paginacion_truncada": "Si el scraping se cortó antes de terminar. En 'True' los conteos son un piso, no un total.",
    "ig_desajuste_idioma": "Si publica en un idioma y le comentan en otro.",
    "ig_capturado_en": "Cuándo se leyó el perfil.",
    "ig_clase": "Clasificación del perfil tras la revisión (utilizable, poca_evidencia, persona_equivocada…).",
    "ig_clase_motivo": "Por qué se le puso esa clase.",
    "ig_clase_origen": "Si la clase la puso el código o una auditoría manual.",
    "ig_clase_revisar": "Si quedó marcada para revisar.",
    "ig_version_lexico": "Versión del léxico con el que se detectaron las señales.",
    "ig_auditada_por": "Quién la auditó y cuándo.",
    "ig_idioma_publica_es": "Cuántas publicaciones suyas están en español. Es la señal más accionable: evidencia directa de que atiende en español.",
    "ig_idioma_publica_en": "Cuántas publicaciones suyas están en inglés.",
    "ig_captions_es_ratio": "Qué proporción de sus textos está en español (0 a 1).",
    "ig_idioma_comentarios_es": "Cuántos comentarios recibe en español. Dice el idioma de su AUDIENCIA, que puede no ser el suyo.",
    "ig_idioma_comentarios_en": "Cuántos comentarios recibe en inglés.",
    "ig_comentarios_es_ratio": "Proporción de comentarios en español (0 a 1).",
    "ig_menciona_primera_casa": "Cuántas veces habla de primera vivienda. Quien escribe 'te ayudo a comprar tu primera casa' ya filtró su audiencia hacia nuestro cliente.",
    "ig_menciona_fha": "Cuántas veces menciona FHA.",
    "ig_menciona_va": "Cuántas veces menciona préstamos VA.",
    "ig_menciona_dpa": "Cuántas veces menciona ayudas para el enganche (down payment assistance).",
    "ig_menciona_itin": "Cuántas veces menciona ITIN, que es el caso del comprador sin número de seguro social.",
    "ig_menciona_credito": "Cuántas veces habla de crédito o puntaje.",
    "ig_programas_mencionados": "Qué programas nombra y cuántas veces.",
    "ig_menciona_lender": "A qué prestamista menciona. Dice con quién ya tiene relación pública.",
    "ig_cuentas_hipotecarias_etiquetadas": "Qué cuentas de hipotecas etiqueta. Es la competencia visible.",
    "ig_posts_comarketing": "Publicaciones hechas junto a otra marca o profesional.",
    "ig_temas": "De qué habla y cuánto.",
    "ig_tema_dominante": "Su tema principal.",
    "ig_audiencia_dominante": "A quién le habla sobre todo. 'lujo' o 'inversion' es señal de que su cliente NO es el nuestro.",
    "ig_audiencia_segmentos": "Todos los segmentos detectados con su conteo.",
    "ig_ratio_educa_vs_anuncia": "Si enseña o solo publica listados. Quien educa construye audiencia de primer comprador.",
    "ig_registro": "Si tutea o trata de usted. Sirve para el tono del mensaje.",
    "ig_marcadores_culturales": "Banderas, modismos y referencias culturales detectadas.",
    "ig_designaciones": "Credenciales profesionales que exhibe (NAHREP y similares).",
    "ig_barrios_mencionados": "Qué zonas nombra y cuántas veces. Es su mercado dicho por él.",
    "ig_geotags_top": "Dónde geoetiqueta sus publicaciones.",
    "ig_precios_mencionados": "Qué precios nombra. Dice en qué banda trabaja.",
    "ig_preguntas_recibidas": "Qué le preguntan en los comentarios. 'calificacion' es una señal fuerte de audiencia compradora.",
    "ig_comentarios_pregunta_calificacion": "Cuántas veces le preguntan si califican para un crédito.",
    "ig_engagement_rate": "Interacciones sobre seguidores. OJO: el conteo de seguidores NO predice producción (correlación 0,086).",
    "ig_tipo_post_reel_pct": "Qué parte de sus publicaciones son reels.",
    "ig_dias_entre_posts_mediana": "Cada cuánto publica.",
    "ig_hueco_max_dias": "El silencio más largo. Un hueco grande puede ser una cuenta abandonada.",
    "ig_destacadas_titulos": "Los títulos de sus historias destacadas.",
    "ig_citas_por_etiqueta": "Las frases exactas que dispararon cada señal. Es la evidencia cruda: cuando un dato no cuadre, la respuesta está acá.",
    "ig_captions_texto": "El texto completo de sus publicaciones, tal cual. Puede llegar a 30.000 caracteres en una celda.",
    "ig_comentarios_texto": "⚠ Comentarios de TERCEROS textuales. No son palabras del realtor sino de quien le comentó.",
    "ig_comentarios_redactados": "Cuántos comentarios se redactaron por traer datos personales.",
    "ig_comentarios_del_agente": "Lo que el propio realtor respondió en comentarios.",
    "ig_texto_truncado": "Si el texto guardado se cortó por tamaño.",
}

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
#: un caso testigo: 3 FHA, 12 convencionales y 0 VA, y las tres coinciden.
#:
#: Las bandas por `shareOfUnits` NO se usan: no miden la proporcion del
#: agente sino la de un bucket de lender: el testigo cae en «>=50% FHA» cuando
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
    ig: dict[str, dict] = {}
    ruta_ig = os.path.join(RAIZ, "data", "trabajo", "instagram.json")
    if os.path.exists(ruta_ig):
        with open(ruta_ig, encoding="utf-8") as fh:
            ig = json.load(fh)
    mix: dict[str, set] = {}
    if os.path.exists(MIX):
        with open(MIX, encoding="utf-8") as fh:
            crudo = json.load(fh)["resultado"]
        mix = {clave: set(crudo.get(clave) or []) for _, clave in TIPOS}
    filas = []
    for a in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        with open(a, encoding="utf-8") as fh:
            f = json.load(fh)
        # El registro del realtor manda sobre los archivos sueltos. `paso4.py`
        # escribe ahi el resultado del conteo, que es el metodo del manual y
        # cuesta 0; los archivos laterales son del metodo viejo, con lista
        # paga. Donde estan los dos, se comprobo que coinciden exacto (79 =
        # 79), asi que preferir el registro no cambia ningun valor: cambia de
        # donde viene, y deja de haber dos fuentes para el mismo dato.
        if not f.get("paso4_en"):
            f["trabaja_con_la_casa"] = (
                "sin comprobar" if not f.get("mm_id")
                else ("SÍ" if f["mm_id"] in con_la_casa else "no"))
            f["ops_con_la_casa"] = (
                (peso.get(f.get("mm_id") or "") or {}).get("al_menos")
                or ("" if f["trabaja_con_la_casa"] != "SÍ" else None))
            for nombre, clave in TIPOS:
                f["hace_%s" % nombre] = (
                    "sin comprobar" if not (f.get("mm_id") and mix)
                    else ("sí" if f["mm_id"] in mix.get(clave, ()) else "no"))
        f.update(ig.get(f.get("realtor_id") or "") or {})
        filas.append(f)
    return filas


def columnas_ig(filas: list[dict]) -> list[tuple]:
    """Las columnas de Instagram, DESCUBIERTAS de los datos y no listadas.

    Si se listaran a mano, una señal nueva del scraper no aparecería nunca y
    nadie se enteraría: el archivo diría, callado, que ese dato no se captura.
    Así aparece sola, y si no tiene descripción el generador avisa.
    """
    vistas: dict[str, None] = {}
    for f in filas:
        for k in f:
            if k.startswith("ig_"):
                vistas.setdefault(k, None)
    # Los bloques de texto largo van al final: si van en medio, empujan todo
    # lo demas fuera de la pantalla y la tabla deja de poder leerse.
    largas = ("ig_citas_por_etiqueta", "ig_captions_texto",
              "ig_comentarios_texto", "ig_comentarios_del_agente")
    orden = [k for k in DESC_IG if k in vistas and k not in largas]
    orden += sorted(k for k in vistas if k not in DESC_IG and k not in largas)
    orden += [k for k in largas if k in vistas]
    return [(k, "IG · " + k[3:].replace("_", " "),
             40 if k in largas else 18, IG, DESC_IG.get(k, ""))
            for k in orden]


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
    # CERO no es CAUTIVO. Cero loan officers significa que Model Match no le
    # atribuye ninguna operacion financiada, no que dependa de uno: es lo
    # contrario de un objetivo de desplazamiento. Seis realtors salian como
    # «CAUTIVO · 1 solo LO» teniendo n=0, y eso manda a un comercial a
    # disputarle un LO a alguien que no tiene ninguno.
    d["fidelidad"] = (
        "" if not isinstance(n, int) else
        "sin operaciones financiadas atribuidas" if n == 0 else
        "CAUTIVO · 1 solo LO" if n == 1 else
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
    # Vacio no es cero. De un realtor que no encontramos NO sabemos cuantos
    # correos tiene Model Match; escribir 0 afirmaria que no tiene ninguno.
    d["mm_emails_n"] = (len(f.get("mm_emails") or [])
                        if f.get("encontrado") else "")
    d["mm_telefonos_n"] = (len(f.get("mm_telefonos") or [])
                           if f.get("encontrado") else "")
    # Historical units: los años con produccion, en una celda legible, y los
    # derivados. `anios` lo escribe el script de conteo, que no cobra.
    anios = f.get("anios_buyside") or {}
    d["historical_units_txt"] = " · ".join(
        "%s: %s" % (a, anios[a]) for a in sorted(anios) if anios[a] != "")
    con_produccion = sorted(a for a in anios
                            if anios[a] != "" and a.isdigit())
    d["primer_anio"] = con_produccion[0] if con_produccion else ""
    d["anios_produciendo"] = len(con_produccion)
    d["antiguedad_aprox"] = (
        dt.date.today().year - int(d["primer_anio"]) + 1
        if d["primer_anio"] else "")
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
    for f in filas:
        f["revisar_por"] = dudoso(f) or ""

    # UNA sola tabla con TODO: Model Match, Instagram y lo nuestro, y las 298
    # filas, no solo las de match confiable. Sacar de la tabla principal a los
    # dudosos los escondia: quien busca a alguien en la hoja Realtors y no lo
    # encuentra concluye que no lo sacamos, cuando lo que pasa es que esta en
    # otra hoja. Van todos, con la columna que dice de cual desconfiar.
    todas_las_columnas = COLUMNAS + columnas_ig(filas)
    sin_desc = [c[1] for c in todas_las_columnas if not c[4]]

    wb = Workbook()

    ws = wb.active
    ws.title = "Realtors"
    escribir_hoja(ws, [c[1] for c in todas_las_columnas],
                  [c[2] for c in todas_las_columnas],
                  [[f.get(c[0]) for c in todas_las_columnas] for f in filas])
    # Pintar el cambio de casa: es el hallazgo que el pedido venia a buscar.
    col_cambio = [c[0] for c in todas_las_columnas].index(
        "cambio_de_brokerage") + 1
    col_rev = [c[0] for c in todas_las_columnas].index("revisar_por") + 1
    for i, f in enumerate(filas, 2):
        if f.get("cambio_de_brokerage") == "si":
            ws.cell(row=i, column=col_cambio).fill = CAMBIO
        if f.get("revisar_por"):
            ws.cell(row=i, column=col_rev).fill = AVISO

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
    for clave, titulo, _ancho, fuente, significado in todas_las_columnas:
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

    # ── como INTERPRETAR, que es distinto de que significa cada campo ──────
    # El diccionario contesta «que es esta columna». Esta hoja contesta «que
    # hago con ella», que es la pregunta que de verdad tiene quien abre el
    # archivo. Las reglas de negocio --las compuertas, la banda de volumen
    # del ICP, los arquetipos-- salen del modelo de prospeccion que ya
    # existe, no de criterio propio; lo que se agrega aca es como se conecta
    # cada dato de Model Match con ellas.
    con_cambio = sum(1 for f in buenas if f.get("cambio_de_brokerage") == "si")
    n_cautivos = sum(1 for f in buenas
                     if str(f.get("fidelidad", "")).startswith("CAUTIVO"))
    n_fha = sum(1 for f in buenas if f.get("hace_fha") == "sí")
    n_casa1 = sum(1 for f in buenas if f.get("ops_con_la_casa") == 1)
    n_produce = sum(1 for f in buenas
                    if (f.get("mm_compras_financiadas_u") or 0) >= 9)

    interpretacion = [
        ["LO PRIMERO: QUÉ CONTESTA ESTE ARCHIVO", ""],
        ["", "Contesta «quién es esta persona hoy y cuánto negocio "
             "hipotecario mueve». NO contesta «a quién llamo primero»: eso "
             "lo decide el modelo de scoring, que mira además el estado, el "
             "idioma y el perfil de Instagram. Esto es el insumo fresco para "
             "ese modelo, no un reemplazo."],
        ["", "Todo lo de Model Match es de los últimos 12 meses salvo la "
             "columna de Everett, que mira todo el historial."],

        ["EL ORDEN DE LECTURA: PRIMERO DESCARTAR, DESPUÉS ORDENAR", ""],
        ["", "El error caro es ordenar por producción y llamar desde arriba. "
             "Primero se descarta, y recién después se ordena lo que queda."],
        ["1 · ¿Está bien identificado?",
         "Si la Confianza dice «contradicha por el teléfono», el resto de la "
         "fila puede ser de otra persona. No se actúa sobre esa fila hasta "
         "resolverla en la hoja Revisar."],
        ["2 · ¿Ya es de la casa?",
         "«¿Ya financia con la casa?» en SÍ es exclusión por "
         "no-canibalización. PERO mirá primero la columna de al lado: %d de "
         "los 79 tienen UNA sola operación con la casa, y una operación "
         "suelta hace años no es una relación. Ahí la exclusión es una "
         "decisión, no un automatismo." % n_casa1],
        ["3 · ¿Produce lo suficiente?",
         "La regla del modelo es 9 operaciones al año. Acá hay una medida "
         "mejor que la de siempre: «Compras FINANCIADAS (u)», que son las "
         "veces reales que puede presentar un prestamista. %d de los %d "
         "llegan a 9 o más." % (n_produce, len(buenas))],
        ["4 · ¿Hay algo que decirle?",
         "Eso no está en este archivo: sale del idioma, el apellido, el "
         "brokerage y el perfil de Instagram. Un realtor que produce mucho "
         "pero no tiene ningún gancho va a campaña masiva, no a llamada."],

        ["REGLA: ANTE DISCREPANCIA, MANDA MODEL MATCH", ""],
        ["", "Los datos de MMI están viejos y esta extracción lo dejó "
             "medido, no opinado. Cuando una columna «(MMI)» y su gemela "
             "«(MM)» no coincidan, **la buena es la de Model Match**, y la "
             "de MMI se queda solo para ver cuánto se había corrido."],
        ["La prueba de que está viejo",
         "%d de los %d realtors cambiaron de inmobiliaria. Los correos "
         "corporativos que trae MMI apuntan en varios casos a la casa "
         "anterior. Y las unidades de MMI son de otra ventana y otra fecha."
         % (con_cambio, len(filas))],
        ["Qué hacer con eso",
         "Para contactar: usar el brokerage, el teléfono y la ciudad de "
         "Model Match. Para el correo, probar los de Model Match Y los "
         "nuestros, porque cada fuente conserva uno distinto y ninguna "
         "tiene los dos. Para puntuar: rehacer con la producción de Model "
         "Match, que es la fresca."],
        ["La excepción",
         "Donde Model Match viene vacío —la licencia, por ejemplo, que solo "
         "tiene para la mitad— vale lo nuestro. Vacío no es 'no tiene': es "
         "'no lo sabe'."],

        ["LOS CINCO NÚMEROS QUE DECIDEN", ""],
        ["Compras FINANCIADAS (u)",
         "El más importante de todos. No es cuánto vende: es cuántas veces "
         "al año tiene delante a un comprador que necesita hipoteca. La "
         "banda dulce del ICP es 15-20: ahí ya es constante pero todavía no "
         "institucionalizó su flujo hipotecario."],
        ["% unidades financiadas",
         "Bajo = libro con mucho efectivo, y ahí hay poco que hacer por más "
         "volumen que tenga. Un realtor de 40 operaciones con 30 % "
         "financiado vale menos que uno de 15 con 90 %."],
        ["Nº originadores",
         "Mide la captividad, que antes solo se podía suponer por el "
         "volumen. Pocos LOs = hay a quién desplazar y cuesta; muchos = "
         "entrar es fácil porque ya reparte. En esta lista hay %d cautivos "
         "de un solo LO y la mediana es 10." % n_cautivos],
        ["Loan medio de sus compradores",
         "En qué banda de precio piden prestado sus clientes. Es la "
         "asequibilidad medida en la persona y no en el estado: un loan "
         "medio bajo dice que sus compradores son exactamente el cliente de "
         "entrada que buscamos."],
        ["¿Produce FHA?",
         "FHA es el producto del comprador de primera vivienda con enganche "
         "chico. %d de los %d producen algo de FHA. Es un sí/no: NO dice qué "
         "parte de su negocio es." % (n_fha, len(buenas))],

        ["CUATRO LECTURAS COMBINADAS", ""],
        ["Muchas financiadas + UN solo LO",
         "El caso más valioso y el más caro. Hay flujo real y hay a quién "
         "desplazar. Requiere una razón concreta para cambiar, no una "
         "presentación. Mirá «Su loan officer principal»: ese es el nombre "
         "contra el que se compite."],
        ["Muchas financiadas + muchos LOs",
         "El más fácil. Ya reparte entre diez o más, así que sumar uno no le "
         "cuesta nada emocionalmente. Es entrada, no desplazamiento, y el "
         "mensaje es otro."],
        ["Mucho volumen + poco % financiado",
         "Trampa. Se ve grande en la lista y no tiene nada que referir. "
         "Ordenar por volumen los pone arriba y hacen perder toques."],
        ["Cambió de brokerage",
         "Momento de apertura: acaba de mudarse y sus relaciones están "
         "sueltas. Pero también significa que lo que sabíamos de su oficina "
         "está viejo — ver la advertencia de abajo."],

        ["LO QUE MODEL MATCH PERMITE DEJAR DE SUPONER", ""],
        ["Antes se suponía la captividad por el volumen",
         "La regla decía que arriba de 60 operaciones el realtor ya tiene "
         "lender cautivo. Ahora no hace falta suponerlo: «Nº originadores» "
         "lo mide. Hay realtors de 100 operaciones que reparten entre 20 "
         "LOs y realtors de 12 que dependen de uno."],
        ["Antes la producción venía de MMI y estaba vieja",
         "Ahora hay dos columnas de producción, la de MMI y la de Model "
         "Match, y se ven una al lado de la otra. No son comparables "
         "directamente (distinta ventana y distinta fecha), pero una "
         "diferencia grande es señal de que el registro hay que refrescarlo."],
        ["⚠ El brokerage con el que se puntuó puede estar viejo",
         "%d de los realtors cambiaron de inmobiliaria desde lo que "
         "teníamos. El criterio de «brokerage con identidad latina» se "
         "calculó sobre el brokerage ANTERIOR en todos esos casos, así que "
         "ese puntaje hay que recalcularlo con la columna nueva."
         % con_cambio],

        ["LAS TRAMPAS DE ESTOS DATOS", ""],
        ["Ningún porcentaje de la API se usa sin comprobar",
         "Van tres que no significaban lo que parecía. El 'pctUnits' del "
         "desglose de originadores llegó a dar 167 % en una fila. Las bandas "
         "de FHA medían la proporción dentro de un prestamista, no la del "
         "agente. Los porcentajes que quedaron en este archivo están "
         "recalculados acá con el denominador correcto o validados contra un "
         "caso conocido."],
        ["La ventana cambia la respuesta",
         "Everett a 24 meses da 28 realtors; a historial completo da 79. "
         "Siempre que un número de acá se cite, tiene que ir con su ventana."],
        ["Los nombres de prestamistas vienen crudos",
         "Sin normalizar: la misma empresa aparece con varias grafías, y una "
         "tiene 'Everett' mal escrito. No se agrupan por texto sin revisar."],
        ["⚠ Las columnas IG con texto crudo",
         "«IG · captions texto» trae sus publicaciones enteras, hasta 30.000 "
         "caracteres en una celda. «IG · comentarios texto» trae comentarios "
         "de TERCEROS textuales: no son palabras del realtor sino de quien "
         "le comentó. Están porque se pidió el dato bruto completo, pero no "
         "se reenvían fuera del equipo."],
        ["Lo que Model Match NO sabe",
         "Las operaciones una por una con su tipo de préstamo y su monto no "
         "salen por esta vía a un costo razonable: eso se sigue pegando a "
         "mano desde la pestaña Transactions."],

        ["CÓMO SE USA ESTO, Y CÓMO NO", ""],
        ["Es para decidir a qué REALTOR se contacta",
         "Es información comercial sobre profesionales inmobiliarios. No se "
         "usa para decidir nada sobre un consumidor ni sobre su crédito."],
        ["El origen del realtor no entra acá",
         "Este archivo no trae ni infiere apellido, etnia ni origen. Esas "
         "señales viven en el modelo de scoring y sirven para elegir el "
         "idioma de la conversación con un profesional — nunca para una "
         "decisión de crédito sobre una persona."],
        ["Que un realtor trabaje con la casa es contexto",
         "Sirve para no pisarle el cliente a un colega. No es un argumento "
         "de venta ni se le menciona al realtor como gancho."],
        ["Datos de contacto",
         "Correos y teléfonos son de uso interno del equipo. No se comparten "
         "fuera ni se cargan en herramientas de terceros sin aprobación."],
    ]
    ws = wb.create_sheet("Cómo interpretar")
    escribir_hoja(ws, ["Tema", "Cómo se lee"], [38, 112], interpretacion)
    for fila in ws.iter_rows(min_row=2, max_col=2):
        fila[1].alignment = Alignment(wrap_text=True, vertical="top")
        if fila[0].value and not fila[1].value:
            fila[0].font = Font(bold=True, size=11, color="1F3864")
            fila[0].fill = PatternFill("solid", fgColor="D9E2F3")
            fila[1].fill = PatternFill("solid", fgColor="D9E2F3")
        else:
            fila[0].alignment = Alignment(wrap_text=True, vertical="top")

    # La guia de lectura va SEGUNDA, pegada a los datos: si queda al final
    # nadie la abre, y este archivo tiene demasiadas formas de leerse mal.
    wb.move_sheet("Cómo interpretar", offset=-(len(wb.sheetnames) - 2))

    # ── la hoja que explica, que es la que evita que alguien lea mal ────────
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
         "de un caso testigo (3 FHA, 12 convencionales y 0 VA sobre sus 38 "
         "propiedades) y las tres banderas coinciden."],
        ["⚠ Lo que NO dice: la proporción",
         "No hay forma barata de saber QUÉ PARTE de su producción es FHA. Se "
         "intentó con bandas de porcentaje y no sirven: miden la proporción "
         "dentro de un lender, no la del agente. El caso testigo aparece en "
         "la banda '≥50% FHA' cuando su proporción real es 20%. Esas bandas "
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
    print("hoja Realtors : %d filas x %d columnas (TODOS, incluidos los "
          "dudosos)" % (len(filas), len(todas_las_columnas)))
    print("   de los cuales hay que revisar: %d" % len(revisar))
    print("cambios de casa: %d" % con_cambio)
    print("creditos       : %d" % creditos)
    print("guardado en %s" % ruta)


if __name__ == "__main__":
    main()
