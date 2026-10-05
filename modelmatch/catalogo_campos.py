"""Catalogo de TODOS los campos de Model Match: los que sacamos y los que no.

Dos fuentes, y se distinguen a proposito:

  · **lo que sacamos** sale de las respuestas crudas en `data/raw/`. Es
    verdad de terreno: ese campo llego, con ese nombre, en una respuesta real;
  · **lo que se puede sacar** sale de la guia del MCP. Eso es documentacion,
    no observacion, y va marcado como tal.

La distincion importa porque la guia misma avisa que los esquemas casi no
describen las respuestas: un campo «documentado» puede no venir, o venir con
otro nombre. Nunca afirmar un dato de Model Match que no venga de una
respuesta.

Cero llamadas a la API: lee del disco.

Uso:
    python modelmatch/catalogo_campos.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRUDO = os.path.join(RAIZ, "data", "raw")
SALIDA = os.path.join(RAIZ, "data", "salida")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

# ── el modelo de costo, MEDIDO contra el ledger ─────────────────────────────
GRATIS = "GRATIS · 0 créditos"
FILA = "1 crédito POR FILA devuelta"
UNO = "1 crédito"
NO_MEDIDO = "no medido"
PROHIBIDO = "10 por match · PROHIBIDO (skip-trace)"

SI_EXCEL = "SÍ · está en el Excel de realtors"
SI_CRUDO = "SÍ · está en data/raw, no en el Excel"
NO = "no"

#: (dominio, campo, extraido, significado, de donde sale, costo, nota)
CAMPOS: list[tuple] = []


def add(dom, campos, extraido, fuente, costo, sig_por_campo, nota=""):
    for c in campos:
        CAMPOS.append((dom, c, extraido, sig_por_campo.get(c, ""), fuente,
                       costo, nota))


# ══ 1 · BÚSQUEDA (instant-search) — todo gratis ════════════════════════════
add("1 · Búsqueda de agente", [
    "id / modelMatchId", "fullName", "firstName", "lastName", "email",
    "office", "officeKey", "city", "state", "zip", "volume", "units",
    "avgSoldPrice", "_geo.lat", "_geo.lng",
], SI_EXCEL, "POST /v1/instant-search", GRATIS, {
    "id / modelMatchId": "El identificador estable del agente (mma_…). Es la llave para todo lo demás.",
    "fullName": "Nombre completo, en minúsculas.",
    "firstName": "Nombre de pila.",
    "lastName": "Apellido.",
    "email": "Uno o VARIOS correos separados por punto y coma. Suele conservar el del brokerage anterior.",
    "office": "El brokerage al que Model Match lo asigna hoy.",
    "officeKey": "Id de la oficina (base64 de calle‖ciudad‖estado‖zip). Suele venir vacío.",
    "city": "Ciudad de su mercado principal, que puede no ser donde tiene la oficina.",
    "state": "Estado del mercado principal.",
    "zip": "Código postal del mercado principal.",
    "volume": "Dólares cerrados en la ventana.",
    "units": "Operaciones cerradas en la ventana, los dos lados sumados.",
    "avgSoldPrice": "Precio medio de venta.",
    "_geo.lat": "Latitud de su oficina.",
    "_geo.lng": "Longitud de su oficina.",
}, "La búsqueda es DIFUSA: con el nombre devuelve homónimos de otros estados. "
   "Hay que desambiguar con el correo.")

add("1 · Búsqueda · otras entidades", [
    "originators[] (id/nmlsId, name, company, city, state, volume, units)",
    "companies[] (id/nmlsId, name, companyType, tradeNames, loCount, teamSize…)",
    "lenders[] (id, name, canonicalName, aliases, brandAliases, totalDocuments)",
    "offices[] (id, company, street, city, state, zip, agentCount)",
    "branches[] (id, name, company, companyNmlsId, teamSize, volume, units)",
    "locations[] (id, name, type, state, lat, lon, totalCount)",
], SI_CRUDO, "POST /v1/instant-search", GRATIS, {
    "originators[] (id/nmlsId, name, company, city, state, volume, units)":
        "Loan officers. El id ES el NMLS. Así se resuelve un nombre de LO a su NMLS sin gastar.",
    "companies[] (id/nmlsId, name, companyType, tradeNames, loCount, teamSize…)":
        "Compañías hipotecarias. `tradeNames` trae los nombres comerciales: así se encontró que Everett opera como Supreme Lending.",
    "lenders[] (id, name, canonicalName, aliases, brandAliases, totalDocuments)":
        "El diccionario de lenders. El `id` es lo que exigen los filtros de footprint; el nombre tecleado NO matchea.",
    "offices[] (id, company, street, city, state, zip, agentCount)":
        "Oficinas de brokerage inmobiliario, con cuántos agentes tienen.",
    "branches[] (id, name, company, companyNmlsId, teamSize, volume, units)":
        "Sucursales de compañías hipotecarias (NMLS de branch).",
    "locations[] (id, name, type, state, lat, lon, totalCount)":
        "Ciudades, condados y ZIPs. Así se resuelve un nombre de condado a su FIPS, que es lo único que aceptan los filtros.",
}, "Lo usamos solo para agentes. Las otras seis secciones vienen en la misma "
   "respuesta y no cuestan nada extra.")

# ══ 2 · FICHA DEL AGENTE ═══════════════════════════════════════════════════
add("2 · Ficha del agente", [
    "phone", "licenseNumber", "licenses[].number", "licenses[].state",
    "licenses[].type", "licenses[].expirationDate", "linkedProfileCount",
    "linkedProfiles[].name", "linkedProfiles[].email",
    "linkedProfiles[].phone", "linkedProfiles[].officePhone",
    "linkedProfiles[].transactions",
    "linkedProfiles[].firstTransactionDate",
    "linkedProfiles[].lastTransactionDate",
    "buyerUnits", "buyerVolume", "sellerUnits", "sellerVolume",
    "dualUnits", "dualVolume",
    "totalLendersWorkedWith", "totalOriginatorsWorkedWith",
    "totalCompaniesWorkedWith",
], SI_EXCEL, "GET /v1/agents/{id}", UNO, {
    "phone": "Teléfono del agente. La documentación decía que no existía; sí viene.",
    "licenseNumber": "Licencia inmobiliaria. Viene vacía para la mitad de los agentes.",
    "licenses[].number": "Número de cada licencia (puede tener varias, de varios estados).",
    "licenses[].state": "Estado que emitió esa licencia.",
    "licenses[].type": "Tipo (Salesperson, Broker…).",
    "licenses[].expirationDate": "Cuándo vence. Sirve para saber si sigue activo.",
    "linkedProfileCount": "Cuántos perfiles duplicados considera Model Match que son la misma persona.",
    "linkedProfiles[].name": "Nombre en cada perfil duplicado.",
    "linkedProfiles[].email": "Correos de los duplicados: de acá salen correos que la ficha principal no trae.",
    "linkedProfiles[].phone": "Teléfonos extra. Es la fuente de los 188 realtors con más de un número.",
    "linkedProfiles[].officePhone": "Teléfono de oficina del duplicado.",
    "linkedProfiles[].transactions": "Cuántas operaciones tiene ese perfil duplicado.",
    "linkedProfiles[].firstTransactionDate": "Primera operación del duplicado. Vino siempre vacía.",
    "linkedProfiles[].lastTransactionDate": "Última operación del duplicado. Vino siempre vacía.",
    "buyerUnits": "Operaciones representando al COMPRADOR. Es el lado que nos interesa.",
    "buyerVolume": "Dólares del lado comprador.",
    "sellerUnits": "Operaciones representando al VENDEDOR (listings).",
    "sellerVolume": "Dólares del lado vendedor.",
    "dualUnits": "Operaciones representando a las dos partes.",
    "dualVolume": "Dólares de doble agencia.",
    "totalLendersWorkedWith": "Cuántos prestamistas DISTINTOS financiaron sus deals. ES el nº de filas del breakdown de lenders.",
    "totalOriginatorsWorkedWith": "Cuántos loan officers distintos. ≤1 = cautivo. ES el nº de filas de ese breakdown.",
    "totalCompaniesWorkedWith": "Cuántas compañías hipotecarias distintas.",
}, "Los tres `total…WorkedWith` dicen el costo exacto de cada breakdown ANTES "
   "de pedirlo. Es lo que permite respetar un tope por realtor.")

add("2 · Ficha · bloque `scored` (financiado)", [
    "scored.total_mortgaged_buyer_units",
    "scored.total_mortgaged_buyer_volume",
    "scored.total_mortgaged_listing_units",
    "scored.total_mortgaged_listing_volume",
    "scored.total_mortgaged_dual_units",
    "scored.total_mortgaged_dual_volume",
    "scored.total_percent_units_mortgaged",
    "scored.total_percent_volume_mortgaged",
    "scored.average_mortgaged_loan_amount",
    "scored.average_mortgaged_buyer_volume",
    "scored.average_mortgaged_listing_volume",
    "scored.average_mortgaged_dual_volume",
    "scored.average_buyer_side_volume",
    "scored.average_seller_side_volume",
    "scored.average_dual_side_volume",
    "scored.average_listing_amount", "scored.average_sold_price",
    "scored.total_buyer_side_units", "scored.total_buyer_side_volume",
    "scored.total_seller_side_units", "scored.total_seller_side_volume",
    "scored.total_dual_side_units", "scored.total_dual_side_volume",
    "scored.total_sold_units", "scored.total_sale_units",
    "scored.total_sale_price", "scored.total_list_price",
    "scored.total_builders", "scored.LastTransactionDate",
    "scored.breakdownsHint", "scored.total_lenders_worked_with",
    "scored.total_originators_worked_with",
    "scored.total_companies_worked_with",
], SI_EXCEL, "GET /v1/agents/{id} · bloque `scored`", UNO, {
    "scored.total_lenders_worked_with": "Copia dentro de `scored` del nº de prestamistas. Mismo valor que `totalLendersWorkedWith`.",
    "scored.total_originators_worked_with": "Copia dentro de `scored` del nº de loan officers.",
    "scored.total_companies_worked_with": "Copia dentro de `scored` del nº de compañías.",
    "scored.total_mortgaged_buyer_units": "**El número más importante**: cuántas de sus compras se pagaron con hipoteca. Son las veces reales que puede presentar un prestamista.",
    "scored.total_mortgaged_buyer_volume": "Dólares de esas compras financiadas.",
    "scored.total_mortgaged_listing_units": "Listings suyos cuyo comprador financió.",
    "scored.total_mortgaged_listing_volume": "Dólares de esos listings financiados.",
    "scored.total_mortgaged_dual_units": "Operaciones de doble agencia financiadas.",
    "scored.total_mortgaged_dual_volume": "Dólares de doble agencia financiada.",
    "scored.total_percent_units_mortgaged": "Qué parte de sus operaciones lleva hipoteca. Bajo = libro con mucho efectivo.",
    "scored.total_percent_volume_mortgaged": "Lo mismo medido en dólares.",
    "scored.average_mortgaged_loan_amount": "Préstamo promedio de sus operaciones financiadas: en qué banda piden prestado sus compradores.",
    "scored.average_mortgaged_buyer_volume": "Valor medio de sus compras financiadas.",
    "scored.average_mortgaged_listing_volume": "Valor medio de sus listings financiados.",
    "scored.average_mortgaged_dual_volume": "Valor medio de su doble agencia financiada.",
    "scored.average_buyer_side_volume": "Valor medio de sus compras (financiadas o no).",
    "scored.average_seller_side_volume": "Valor medio de sus ventas.",
    "scored.average_dual_side_volume": "Valor medio de su doble agencia.",
    "scored.average_listing_amount": "Precio medio de listado.",
    "scored.average_sold_price": "Precio medio de venta.",
    "scored.total_buyer_side_units": "Unidades lado comprador (duplica `buyerUnits`).",
    "scored.total_buyer_side_volume": "Volumen lado comprador.",
    "scored.total_seller_side_units": "Unidades lado vendedor.",
    "scored.total_seller_side_volume": "Volumen lado vendedor.",
    "scored.total_dual_side_units": "Unidades de doble agencia.",
    "scored.total_dual_side_volume": "Volumen de doble agencia.",
    "scored.total_sold_units": "Total de unidades vendidas. Es el denominador de los pct de los breakdowns.",
    "scored.total_sale_units": "Unidades de venta. Vino en 0 incluso con operaciones; no usar.",
    "scored.total_sale_price": "Suma de precios de venta.",
    "scored.total_list_price": "Suma de precios de listado. Comparado con el de venta da si vende sobre o bajo pedido.",
    "scored.total_builders": "Cuántas constructoras hay entre sus contrapartes. 0 en todos los que vimos.",
    "scored.LastTransactionDate": "Fecha de su última operación, en milisegundos epoch. Dice si sigue activo.",
    "scored.breakdownsHint": "Un aviso de la propia API: dice que los listados por relación se piden aparte. Así descubrimos los breakdowns.",
}, "Este bloque NO está en la fila de lista: es exclusivo del detalle, y "
   "cuesta lo mismo. Por eso conviene siempre el detalle sobre la lista.")

# ══ 3 · BREAKDOWNS ═════════════════════════════════════════════════════════
add("3 · Breakdowns del agente", [
    "lenders[].label", "lenders[].units", "lenders[].volume",
    "lenders[].pctUnits", "lenders[].pctVolume",
    "originators[].label", "originators[].units", "originators[].volume",
    "companies[].label", "companies[].units", "companies[].volume",
    "counties[].id", "counties[].label", "counties[].units",
    "counties[].volume",
], SI_EXCEL, "POST /v1/agents/{id}/breakdowns/{lenders|originators|companies|counties}",
    FILA, {
    "lenders[].label": "Nombre CRUDO del prestamista, sin normalizar. Varias grafías de la misma empresa, y una con 'Everett' mal escrito.",
    "lenders[].units": "Cuántas de sus operaciones financió ese prestamista.",
    "lenders[].volume": "Dólares por ese prestamista.",
    "lenders[].pctUnits": "⚠ NO es la parte de su negocio: el denominador no son sus operaciones y llega a dar 167 %.",
    "lenders[].pctVolume": "⚠ Mismo problema que pctUnits.",
    "originators[].label": "Nombre del loan officer. A veces viene basura tipo 'NMLS #3'.",
    "originators[].units": "Operaciones suyas que pasaron por ese LO. Con esto se calcula la concentración REAL.",
    "originators[].volume": "Dólares por ese LO.",
    "companies[].label": "Nombre de la compañía hipotecaria.",
    "companies[].units": "Operaciones por esa compañía.",
    "companies[].volume": "Dólares por esa compañía.",
    "counties[].id": "FIPS de 5 dígitos del condado. Es la llave para cruzar con el Census.",
    "counties[].label": "Nombre legible del condado.",
    "counties[].units": "Operaciones suyas en ese condado.",
    "counties[].volume": "Dólares en ese condado.",
}, "Cuestan 1 por fila: un agente con 43 lenders cuesta 43 créditos. Por eso "
   "solo se pidieron donde cabían en el tope.")

add("3 · Breakdowns NO pedidos", [
    "agentCities", "agentStates", "agentZipCodes", "agentOffices",
    "agentMarkets",
], NO, "POST /v1/agents/{id}/… (documentado en la guía)", FILA, {
    "agentCities": "Su volumen repartido por ciudad.",
    "agentStates": "Su volumen repartido por estado. Útil para cruzar con las licencias de nuestros LOs.",
    "agentZipCodes": "Su volumen repartido por código postal.",
    "agentOffices": "Las oficinas de listado con las que cerró: sus contrapartes habituales.",
    "agentMarkets": "Lo más rico: ZIPs con volumen, transacciones, precio medio, shareOfScope y el mix de Community Lending del tract.",
}, "No se pidieron por presupuesto. `agentMarkets` trae variables censales "
   "del tract — ojo con usarlas para segmentar: es exposición de fair lending.")

# ══ 4 · VENTAS ═════════════════════════════════════════════════════════════
add("4 · Ventas del agente", [
    "id", "address", "streetAddress", "city", "state", "zip", "zipCode",
    "fips", "apn", "coordinates.lat", "coordinates.lon", "date",
    "transactionDate", "recordingDate", "price", "listPrice",
    "originalListPrice", "salePrice", "soldPrice", "mlsStatus",
    "propertyType", "beds", "baths", "sqft", "yearBuilt", "daysOnMarket",
    "listAgentName", "listingAgentName", "listingAgentId", "soldAgentName",
    "soldAgentId", "buyerName", "sellerName", "txType",
], SI_CRUDO, "POST /v1/agents/{id}/sales", FILA, {
    "id": "Id del documento de venta.",
    "address": "Dirección de la propiedad.",
    "streetAddress": "Calle, en otro formato.",
    "city": "Ciudad.", "state": "Estado.", "zip": "Código postal.",
    "zipCode": "Alias de zip; a veces traen valores distintos.",
    "fips": "FIPS del condado.", "apn": "Número de parcela del condado.",
    "coordinates.lat": "Latitud de la propiedad.",
    "coordinates.lon": "Longitud de la propiedad.",
    "date": "Fecha de la operación.",
    "transactionDate": "Fecha de transacción; no siempre coincide con `date`.",
    "recordingDate": "Fecha de registro en el condado. Vino vacía.",
    "price": "Precio. **Vino vacío en las que pedimos.**",
    "listPrice": "Precio de listado. Vino vacío.",
    "originalListPrice": "Precio de listado original. Vino vacío.",
    "salePrice": "Precio de venta. Vino vacío.",
    "soldPrice": "Precio vendido. Vino vacío.",
    "mlsStatus": "Estado en el MLS: SLD vendida, ACT activa, PND pendiente.",
    "propertyType": "Tipo de propiedad. Ojo: incluye 'Residential Lease', o sea alquileres.",
    "beds": "Dormitorios.", "baths": "Baños.", "sqft": "Pies cuadrados.",
    "yearBuilt": "Año de construcción.",
    "daysOnMarket": "Días en mercado. Vino vacío.",
    "listAgentName": "Nombre del agente de listado.",
    "listingAgentName": "Otro campo con el agente de listado; **puede traer un nombre distinto al anterior**.",
    "listingAgentId": "Id del agente de listado. **Siempre null.**",
    "soldAgentName": "Agente del comprador. Vino vacío.",
    "soldAgentId": "Id del agente del comprador. **Siempre null.**",
    "buyerName": "Nombre del comprador. Siempre null (no lo exponen).",
    "sellerName": "Nombre del vendedor. Siempre null.",
    "txType": "Tipo de transacción. Vino vacío.",
}, "Es lo más parecido a la pestaña Transactions, pero los precios, el tipo "
   "y los ids de agente vinieron vacíos. No reemplaza el pegado a mano.")

# ══ 5 · PROPIEDADES Y PRÉSTAMOS ════════════════════════════════════════════
add("5 · Propiedades del agente", [
    "id", "mmPropertyId", "address", "city", "state", "zip", "date",
    "price", "propertyType",
], SI_CRUDO, "POST /v1/agents/{id}/properties", FILA, {
    "id": "Id del documento.",
    "mmPropertyId": "**La llave de oro**: con ella se filtran los préstamos de esa parcela, y contar préstamos es GRATIS.",
    "address": "Dirección.", "city": "Ciudad.", "state": "Estado.",
    "zip": "Código postal.", "date": "Fecha.",
    "price": "Precio. Vino vacío.",
    "propertyType": "Tipo de propiedad. Vino vacío.",
}, "Es el puente al mix REAL de tipo de préstamo: propiedades (1 por fila) → "
   "contar préstamos por loanType (gratis).")

add("5 · Préstamos vinculados", [
    "related.id (loan_mm_…)", "related.total", "related.linkQuality",
], SI_CRUDO, "GET /v1/agents/{id}/related?to=loans", FILA, {
    "related.id (loan_mm_…)": "Id del préstamo. Lleva dentro el id de parcela, el MONTO y la FECHA, separados por ||.",
    "related.total": "Cuántos préstamos tiene vinculados en total.",
    "related.linkQuality": "Qué tan fuerte es el vínculo: `primary` canónico o `secondary` más débil.",
}, "Da los ids pero NO el detalle: /v1/loans no acepta filtrar por id. El "
   "detalle se alcanza por propertyId.")

add("5 · Préstamo · campos que NO sacamos", [
    "transactionType", "loanType", "mortgageAmount", "mortgageDate",
    "interestRate", "conforming", "ltvAtOrigination", "currentBalance",
    "homeValue", "equity", "borrowerStatus", "originator", "lender",
    "lenderName", "loanCompany", "broker", "employer", "buyerEntityType",
], NO, "POST /v1/loans (documentado en la guía)", FILA, {
    "transactionType": "PROPÓSITO: purchase, refinance, construction, equity, reo.",
    "loanType": "PRODUCTO: conventional, fha, va, usda, heloc… No confundir con el propósito.",
    "mortgageAmount": "Monto del préstamo.",
    "mortgageDate": "Fecha del préstamo; probablemente la de REGISTRO, que llega semanas después del cierre.",
    "interestRate": "Tasa de interés.",
    "conforming": "Si es conforming o jumbo.",
    "ltvAtOrigination": "LTV al originar. Poco poblado; no hay LTV actual.",
    "currentBalance": "Saldo restante estimado. ~19 % poblado.",
    "homeValue": "Valor estimado (AVM) de la propiedad. ~26 % poblado.",
    "equity": "Equity registrado en el préstamo. Histórico, ~10 %.",
    "borrowerStatus": "**Si el prestatario sigue siendo dueño, y si refinanció con el MISMO LO o con otro.** Es la señal de retención o fuga. Solo ~69 % lo tiene.",
    "originator": "NMLS del loan officer que originó.",
    "lender": "Id normalizado del prestamista.",
    "lenderName": "Nombre del prestamista como figura en el documento.",
    "loanCompany": "NMLS de la compañía que fondea.",
    "broker": "NMLS de la empresa broker.",
    "employer": "NMLS del empleador del LO.",
    "buyerEntityType": "Si el comprador es persona jurídica (LLC, trust).",
}, "**countLoans es GRATIS**: se puede contar por tipo sin pagar. Listarlos "
   "cuesta 1 por fila.")

# ══ 6 · MERCADO HMDA ═══════════════════════════════════════════════════════
add("6 · Mercado (HMDA)", [
    "loanType", "loanPurpose", "loanAmount", "purchasePrice",
    "appraisedValue", "ltv", "combinedLtv", "noteRate", "loanTerm",
    "amortizationType", "channel", "creditScore", "income", "dti",
    "dtifront", "firstTimeHomebuyer", "currentHomeOwner", "selfEmployed",
    "veteranIndicator", "borrowerGeneration", "occupancyType",
    "propertyType", "zip", "county", "state", "loanApplicationDate",
    "closingDate", "fundingDate", "hmdaActionTaken", "id",
], SI_CRUDO, "POST /v1/market", FILA, {
    "loanType": "Producto: conventional, fha, va…",
    "loanPurpose": "Propósito: purchase, refinance…",
    "loanAmount": "Monto del préstamo.",
    "purchasePrice": "Precio de compra.",
    "appraisedValue": "Valor de tasación.",
    "ltv": "Loan to value.", "combinedLtv": "LTV combinado (con segundas).",
    "noteRate": "Tasa de la nota.", "loanTerm": "Plazo en meses.",
    "amortizationType": "Fija o variable.",
    "channel": "Canal: retail, correspondent, broker.",
    "creditScore": "Puntaje de crédito del solicitante.",
    "income": "Ingreso del solicitante.",
    "dti": "Deuda sobre ingreso.", "dtifront": "DTI de vivienda solamente.",
    "firstTimeHomebuyer": "Si es comprador de primera vivienda. **Es nuestro cliente objetivo.**",
    "currentHomeOwner": "Si ya es propietario.",
    "selfEmployed": "Si trabaja por cuenta propia.",
    "veteranIndicator": "Si es veterano.",
    "borrowerGeneration": "Generación del prestatario (gen x, millennial…).",
    "occupancyType": "Vivienda principal, segunda o inversión.",
    "propertyType": "Tipo de propiedad.",
    "zip": "Código postal.", "county": "Código de condado de 3 dígitos (NO el FIPS de 5).",
    "state": "Estado.",
    "loanApplicationDate": "Fecha de solicitud.",
    "closingDate": "**Fecha de cierre REAL.** Con la de solicitud da el time-to-close por préstamo.",
    "fundingDate": "Fecha de fondeo. Vino vacía.",
    "hmdaActionTaken": "Qué pasó con la solicitud (aprobada, negada, retirada). **Vino vacía** — es lo que daría el fallout calculado.",
    "id": "Id del registro.",
}, "Es desidentificado y a nivel de solicitud: 88.195 registros solo en Cook. "
   "Permitiría recalcular todo el panel de Market Signals con denominador.")

add("6 · Mercado · filtros de tract (NO usar para segmentar)", [
    "minorityTractPct", "majorityMinorityTract", "lowModIncomeTract",
    "communityIncomeLevel", "craEligible", "tractIncomeVsMetroPct",
], NO, "POST /v1/market (filtros aceptados)", FILA, {
    "minorityTractPct": "Porcentaje de minorías del tract censal.",
    "majorityMinorityTract": "Si el tract es de mayoría minoritaria.",
    "lowModIncomeTract": "Si el tract es de ingreso bajo o moderado.",
    "communityIncomeLevel": "Nivel de ingreso de la comunidad.",
    "craEligible": "Si califica para CRA (Community Reinvestment Act).",
    "tractIncomeVsMetroPct": "Ingreso del tract contra el del área metropolitana.",
}, "⚠ RIESGO DE FAIR LENDING. Que el dato exista no significa que se pueda "
   "usar: segmentar prospectos por el porcentaje de minoría del tract es "
   "redlining. Sirven para MEDIR nuestra cobertura, nunca para ELEGIR.")

# ══ 7 · CUENTA Y CONTEOS — gratis ══════════════════════════════════════════
add("7 · Cuenta y saldo", [
    "balance.total", "balance.cycle", "balance.onDemand", "balance.personal",
    "allowance.perCycle", "allowance.unitPriceCents", "usage.spent",
    "usage.granted", "usage.purchased", "usage.spentByCategory.api",
    "usage.spentByCategory.ai_agent", "usage.spentByCategory.ai_chat",
    "usage.spentByCategory.enrichment", "usage.window.startDate",
    "usage.window.endDate", "organizationId",
], SI_CRUDO, "GET /v1/me/credits", GRATIS, {
    "balance.total": "**Los créditos que quedan.** Es el único que responde al instante; con esto se mide el costo de una llamada.",
    "balance.cycle": "Créditos de la asignación mensual, que se vencen.",
    "balance.onDemand": "Créditos comprados aparte, que se acumulan.",
    "balance.personal": "Bolsa personal.",
    "allowance.perCycle": "Cuántos créditos trae el plan por ciclo (4.000).",
    "allowance.unitPriceCents": "Cuánto vale un crédito en centavos (1 → un centavo).",
    "usage.spent": "⚠ Gastado del ciclo, PERO va con retraso: no se movió mientras el saldo bajaba 30.",
    "usage.granted": "Créditos concedidos en la ventana.",
    "usage.purchased": "Créditos comprados en la ventana.",
    "usage.spentByCategory.api": "Gastado por la API — nuestro consumo.",
    "usage.spentByCategory.ai_agent": "Gastado por el chat de la app. Los 1.959 del ciclo eran de ahí, no nuestros.",
    "usage.spentByCategory.ai_chat": "Gastado por el chat.",
    "usage.spentByCategory.enrichment": "Gastado en skip-trace.",
    "usage.window.startDate": "Inicio de la ventana del ciclo.",
    "usage.window.endDate": "Fin de la ventana.",
    "organizationId": "Id de la organización.",
}, "El desglose por categoría separa lo que gastamos nosotros de lo que gasta "
   "la app. Sin eso, el consumo del chat parece nuestro.")

add("7 · Conteos", [
    "total (countAgents)", "total (countLoans)",
    "locationNormalizations[].field",
    "locationNormalizations[].original",
    "locationNormalizations[].normalized",
    "locationNormalizations[].displayName",
    "locationNormalizations[].confidence",
], SI_CRUDO, "POST /v1/agents/count · /v1/loans/count", GRATIS, {
    "total (countAgents)": "Cuántos agentes cumplen el filtro. Contó 74.103 sin cobrar.",
    "total (countLoans)": "Cuántos préstamos cumplen el filtro. Contó 22.085 sin cobrar.",
    "locationNormalizations[].field": "Qué filtro de ubicación se normalizó (state, county, city…).",
    "locationNormalizations[].original": "Lo que mandamos nosotros.",
    "locationNormalizations[].normalized": "A qué lo convirtió el servidor.",
    "locationNormalizations[].displayName": "Cómo lo muestra.",
    "locationNormalizations[].confidence": "Qué tan seguro está de la conversión (`exact` o aproximada). Si no es exacta, el filtro puede estar midiendo otro sitio.",
}, "**EL HALLAZGO MÁS IMPORTANTE.** Lo que devuelve un número es gratis; lo "
   "que devuelve filas cuesta. Con un id y un footprint, el conteo da 1 o 0 "
   "— o sea un sí/no por agente, gratis.")

# ══ 7 bis · NUESTRA PROPIA CUENTA (no es dato de realtors) ═════════════════
add("7 bis · Nuestra cuenta (GET /v1/me)", [
    "user.id", "user.name", "user.email", "user.emailVerified",
    "user.createdAt", "user.nmlsId", "user.reLicenseNumber",
    "user.reLicenseState", "user.jobRole", "user.theme",
    "user.contactPhone", "user.contactCardType", "user.addressLine1",
    "user.city", "user.state", "user.postalCode", "user.headline",
    "user.tagline", "user.image", "user.agentPhotoUrl",
    "user.signatureImage", "user.qrBaseUrl", "user.sendNewLoginEmail",
    "organization.id", "organization.role",
    "auth.method", "auth.role", "auth.clientId", "auth.scopes",
    "auth.profileResolved",
], SI_CRUDO, "GET /v1/me", GRATIS, {
    "user.id": "Id de nuestro usuario en Model Match.",
    "user.name": "Nombre del titular de la cuenta.",
    "user.email": "Correo del titular.",
    "user.emailVerified": "Si verificó el correo.",
    "user.createdAt": "Cuándo se creó la cuenta.",
    "user.nmlsId": "NMLS del titular. Vacío — y por eso dos alertas (borrower_listed, epo_risk) no se pueden configurar.",
    "user.reLicenseNumber": "Licencia inmobiliaria del titular. Vacío.",
    "user.reLicenseState": "Estado de esa licencia. Vacío.",
    "user.jobRole": "Rol declarado en la cuenta.",
    "user.theme": "Tema claro u oscuro de la app.",
    "user.contactPhone": "Teléfono de contacto del titular.",
    "user.contactCardType": "Tipo de tarjeta de contacto.",
    "user.addressLine1": "Dirección del titular.",
    "user.city": "Ciudad del titular.",
    "user.state": "Estado del titular.",
    "user.postalCode": "Código postal del titular.",
    "user.headline": "Titular del perfil público.",
    "user.tagline": "Lema del perfil público.",
    "user.image": "Foto de perfil.",
    "user.agentPhotoUrl": "Foto para tarjetas compartibles.",
    "user.signatureImage": "Firma para documentos.",
    "user.qrBaseUrl": "URL base del QR de su tarjeta.",
    "user.sendNewLoginEmail": "Si avisa por correo en cada nuevo inicio de sesión.",
    "organization.id": "Id de la organización: es la que paga los créditos.",
    "organization.role": "Nuestro rol en ella (owner).",
    "auth.method": "Cómo nos autenticamos (api-key).",
    "auth.role": "Rol del token.",
    "auth.clientId": "Id del cliente OAuth, si lo hubiera.",
    "auth.scopes": "Permisos del token.",
    "auth.profileResolved": "Si resolvió el perfil del titular.",
}, "Es información de NUESTRA cuenta, no de realtors. Va en el catálogo "
   "porque llegó en una respuesta y nada debe quedar sin nombrar.")

# ══ 8 · LO QUE NO TOCAMOS ══════════════════════════════════════════════════
add("8 · Analítica del agente (no usada)", [
    "agentAnalyticsSummary", "agentAnalyticsTimeSeries",
    "agentAnalyticsChart",
], NO, "documentado en la guía", NO_MEDIDO, {
    "agentAnalyticsSummary": "Producción del período actual CONTRA el anterior. Es el momentum: quién está creciendo.",
    "agentAnalyticsTimeSeries": "Serie temporal por semana, mes, trimestre o año. Da estacionalidad y el último pico.",
    "agentAnalyticsChart": "Gráfico configurable por ciudad, condado, estado o zip.",
}, "El momentum es justo lo que falta para priorizar: hoy sabemos cuánto "
   "produce, no si está subiendo.")

add("8 · Otros dominios (no usados)", [
    "listOriginators / getOriginator", "originatorAgents",
    "listCompanies / getCompany", "companyAgents", "companyTalentFlow",
    "listBranches / branchRoster", "listOffices / officeAgents",
    "listLenders / getLender", "marketMovement*", "listProperties (completo)",
    "enrichProperty / enrichPropertiesBatch",
], NO, "documentado en la guía", NO_MEDIDO, {
    "listOriginators / getOriginator": "Loan officers con licencias, historial de carrera, disciplina y CONTACTO (celular, email personal, LinkedIn).",
    "originatorAgents": "Los realtors que alimentan a un LO. Con el NMLS del LO dominante de un realtor, dice a quién más le da negocio.",
    "listCompanies / getCompany": "Compañías hipotecarias con volumen, tipo y nombres comerciales.",
    "companyAgents": "**Todos los realtors que financiaron con una compañía.** Es la vía barata de la exclusión por Everett.",
    "companyTalentFlow": "Entradas y salidas de personal de una compañía: reclutamiento.",
    "listBranches / branchRoster": "Sucursales y su plantilla.",
    "listOffices / officeAgents": "Brokerages inmobiliarios y sus agentes. Para atacar una oficina entera.",
    "listLenders / getLender": "El diccionario de prestamistas.",
    "marketMovement*": "Movimiento de LOs entre empresas a nivel industria.",
    "listProperties (completo)": "Parcelas con AVM, equity, propensión a vender, estado de ejecución y variables del tract.",
    "enrichProperty / enrichPropertiesBatch": "⛔ Skip-trace del DUEÑO: nombre, teléfono y correo. PII de consumidor, 10 créditos por match. El cliente revienta antes de salir a la red.",
}, "")


def main() -> None:
    # Cuántos campos distintos vimos de verdad en el crudo, para el pie.
    vistos = len(glob.glob(os.path.join(CRUDO, "*.json")))

    wb = Workbook()
    ws = wb.active
    ws.title = "Campos Model Match"
    cab = ["Dominio", "Campo", "¿Ya lo extrajimos?", "Qué significa",
           "De dónde sale", "¿Cuesta créditos?", "Notas y trampas"]
    ws.append(cab)
    for fila in CAMPOS:
        ws.append(list(fila[:3]) + [fila[3], fila[4], fila[5], fila[6]])

    anchos = [30, 42, 28, 86, 46, 26, 70]
    for i, an in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(i)].width = an
        c = ws.cell(row=1, column=i)
        c.fill = PatternFill("solid", fgColor="1F3864")
        c.font = Font(bold=True, color="FFFFFF", size=10)
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[1].height = 30

    verde = PatternFill("solid", fgColor="E2EFDA")
    gris = PatternFill("solid", fgColor="F2F2F2")
    rojo = PatternFill("solid", fgColor="FCE4D6")
    for i, fila in enumerate(CAMPOS, 2):
        for col in (4, 7):
            ws.cell(row=i, column=col).alignment = Alignment(
                wrap_text=True, vertical="top")
        ws.cell(row=i, column=3).fill = (
            verde if fila[2].startswith("SÍ") else gris)
        if fila[5] == GRATIS:
            ws.cell(row=i, column=6).fill = verde
        elif "PROHIBIDO" in fila[5]:
            ws.cell(row=i, column=6).fill = rojo
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions

    # ── hoja 2: el modelo de costo ──────────────────────────────────────────
    ws2 = wb.create_sheet("Qué cuesta y qué no")
    filas2 = [
        ["GRATIS · no gastan un crédito", ""],
        ["instant-search", "Resolver un nombre o correo a un id. Devuelve hasta 7 secciones de entidades."],
        ["countAgents / countLoans / countSales / countProperties",
         "El conteo exacto con cualquier filtro. Contó 74.103 agentes sin cobrar."],
        ["getMe / getMeCredits / getMePlan", "La cuenta y el saldo."],
        ["suggestLocations / retrieveLocation", "Resolver nombres de lugar a FIPS."],
        ["Los errores (400, 404, 429, 402)",
         "No cobran. Y un 400 devuelve la lista entera de claves aceptadas: es la documentación más barata que tiene esta API."],
        ["", ""],
        ["CUESTAN · 1 crédito POR FILA DEVUELTA", ""],
        ["GET /v1/agents/{id}", "La ficha. 1 crédito, y trae el bloque `scored` que la fila de lista no tiene."],
        ["POST /v1/agents (lista)", "1 por agente devuelto. Pedir 100 cuesta 100."],
        ["breakdowns/{lenders|originators|companies|counties}",
         "1 por fila. Un agente con 43 lenders cuesta 43. El número de filas se sabe antes: está en la ficha."],
        ["agents/{id}/sales · /properties · /related", "1 por fila."],
        ["/v1/market (HMDA)", "1 por fila."],
        ["bulk delivery", "1 por fila entregada. Cancelar un job NO cobra."],
        ["", ""],
        ["PROHIBIDO sin aprobación escrita", ""],
        ["enrichProperty / enrichPropertiesBatch / Bulk",
         "Skip-trace del dueño de la propiedad: nombre, teléfono y correo. Es PII de consumidor para un prestamista, y cuesta 10 créditos por match. El cliente del repo revienta antes de salir a la red si la ruta lo menciona."],
        ["", ""],
        ["LA REGLA", ""],
        ["", "Se cobra lo que devuelve FILAS. Lo que devuelve un NÚMERO es gratis. De ahí sale todo lo demás: contar antes de listar, y usar el conteo con un id para obtener un sí/no por agente sin pagar."],
        ["", ""],
        ["CÓMO SE MIDIÓ", ""],
        ["", "Leyendo `balance.total` de GET /v1/me/credits antes y después de cada llamada. No se estimó ninguno. `usage.spent` NO sirve para esto: va con retraso y no se movió mientras el saldo bajaba 30."],
        ["", ""],
        ["UN PERFIL COMPLETO HOY", ""],
        ["", "1 crédito. La identificación es gratis, la ficha cuesta 1, y las banderas de tipo de préstamo y la exclusión por Everett salen por conteo, que es gratis. Los breakdowns solo si se necesitan los nombres."],
    ]
    ws2.append(["Concepto", "Qué significa"])
    for f in filas2:
        ws2.append(f)
    ws2.column_dimensions["A"].width = 52
    ws2.column_dimensions["B"].width = 118
    for c in ws2[1]:
        c.fill, c.font = PatternFill("solid", fgColor="1F3864"), Font(
            bold=True, color="FFFFFF", size=10)
    for fila in ws2.iter_rows(min_row=2, max_col=2):
        fila[1].alignment = Alignment(wrap_text=True, vertical="top")
        fila[0].alignment = Alignment(wrap_text=True, vertical="top")
        if fila[0].value and not fila[1].value:
            fila[0].font = Font(bold=True, size=11, color="1F3864")
            fila[0].fill = PatternFill("solid", fgColor="D9E2F3")
            fila[1].fill = PatternFill("solid", fgColor="D9E2F3")
    ws2.freeze_panes = "A2"

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, "modelmatch_catalogo_de_campos.xlsx")
    try:
        wb.save(ruta)
    except PermissionError:
        import datetime as dt
        ruta = os.path.join(SALIDA, "modelmatch_catalogo_de_campos_%s.xlsx"
                            % dt.datetime.now().strftime("%H%M"))
        wb.save(ruta)
        print("⚠ estaba abierto en Excel; se guardo al lado")

    ya = sum(1 for f in CAMPOS if f[2].startswith("SÍ"))
    print("campos catalogados : %d" % len(CAMPOS))
    print("   ya extraidos    : %d" % ya)
    print("   disponibles sin usar: %d" % (len(CAMPOS) - ya))
    print("respuestas crudas en disco: %d" % vistos)
    print("guardado en %s" % ruta)


if __name__ == "__main__":
    main()
