# Model Match API · Fase 0 · la superficie, sin gastar créditos

Sigue el brief `brief-modelmatch-agents.md`. **Fase 0 está cerrada y este es el
reporte. No paso a fase 1 sin visto bueno.**

Fecha: 2026-09-24 · llave en `.env` local (`MODELMATCH_API_KEY`), gitignored.

## Lo primero: dos correcciones a lo que creíamos

El reconocimiento anterior —el que está en `modelmatch-consulta-api.md` y en el
bloque 5— decía «recursos `agents` / `originators` / `loans` / `properties`».
Es incompleto y el prefijo estaba mal:

- **las rutas llevan `/v1`**, y el propio host las declara. `GET /` devuelve
  `{"name": "ModelMatch API", "version": "3.59.1", "routes": [...]}` con **13
  rutas**: `/v1/admin`, `/v1/agents`, `/v1/branches`, `/v1/companies`,
  `/v1/instant-search`, `/v1/lenders`, `/v1/loans`, `/v1/locations`,
  **`/v1/market`**, `/v1/offices`, `/v1/originators`, `/v1/properties`,
  **`/v1/sales`**;
- **las listas son `POST`, no `GET`.** Por eso cualquier `GET /v1/agents`
  devuelve 404. El detalle sí es `GET /v1/<recurso>/{id}`.

Y el índice de `/` **no es fiel**: `GET /v1/me` funciona y no está en la lista;
la documentación además menciona `/v1/crm`, `/v1/related` e `/v1/integrations`,
que tampoco están.

## La tabla que pedía el brief

| pregunta | respuesta |
|---|---|
| Campos de `POST /v1/agents` (list) | **id**, **modelMatchId**, **licenseNumber**, firstName, lastName, fullName, email, phone · city, state, zip, office · units, volume, **buyerUnits, buyerVolume, sellerUnits, sellerVolume**, dualUnits, dualVolume, avgSoldPrice · totalCompaniesWorkedWith, **totalLendersWorkedWith, totalOriginatorsWorkedWith** · envoltorio: `data`, `total`, `cursor` |
| Campos solo en `GET /v1/agents/{id}` | **no confirmado**: la referencia pública documenta la lista; el detalle no lo pude leer sin gastar una llamada |
| Filtros aceptados | nombre (firstName/lastName/fullName) · geografía (state, city, zip, office, con semántica OR entre las ubicaciones del agente) · todas las métricas de producción con cotas · **`lenderFilters`**: filtrar agentes por su relación de financiación con un lender, con cotas |
| Valores de `period` | años `2017`–`2026`, `last3Months`, `last12Months`, `allTime`, `yearToDate`. **Ventanas rodantes arbitrarias devuelven 400** |
| ¿Campo que ligue al agente con los originadores a los que refiere? | **Sí, pero solo como CONTEO**: `totalOriginatorsWorkedWith` y `totalLendersWorkedWith`. La lista con nombres no aparece en la lista; `lenderFilters` permite filtrar por lender, así que el dato existe del lado de ellos |
| ¿Sub-endpoints de analytics para agents? | no confirmado en la referencia pública |
| **¿Identificador estable?** | **Sí, tres**: `id`, `modelMatchId` y **`licenseNumber`** (licencia estatal), más `email` y `phone`. Es la respuesta al renglón que el brief marca como el más importante: **se puede hacer match contra el roster sin pegar por nombre** |

## LA pregunta, contestada: no, `loans` no trae al agente

La consulta comercial abría con «¿`loans` devuelve las operaciones fila por fila
con el grano de la pestaña Transactions, filtrables por agente?».

**No.** Y el reparto es más interesante que un no:

| | `/v1/loans` | `/v1/sales` | pestaña Transactions (lo que pegamos hoy) |
|---|---|---|---|
| fecha | `mortgageDate` | recording date, transaction date | Date |
| dirección / ZIP | sí | sí, con **APN y FIPS** | sí |
| monto del préstamo | sí | **no** | sí |
| **loan type (FHA/VA/Conv)** | **sí** | **no** | sí |
| tasa | sí | **no** | sí |
| lender | sí | **no** | sí |
| LO + NMLS | sí (`originatorName`, `originatorNmlsId`) | **no** | sí |
| precio de venta / lista | sí | sí | sí |
| **agente comprador / listing** | **NO** | **sí (nombre e id)** | sí |
| down payment | **no** | no | sí |
| plazo | **no** | no | sí |
| filtrar por agente | **no** | no confirmado | — |

Las 21 columnas que hoy leemos de una sola tabla **están repartidas entre dos
recursos que no se cruzan por sí solos**: `loans` tiene el préstamo sin el
agente, `sales` tiene el agente sin el préstamo. Model Match hace ese cruce
dentro de su interfaz y no lo expone como recurso.

Quedan dos caminos, y los dos hay que preguntarlos antes de presupuestar:

1. **`/v1/related`** — la documentación lo describe como «records linked to a
   given record». Si liga una venta con su préstamo, el problema está resuelto
   y es el endpoint que importa.
2. **Cruzarlo nosotros**, `sales` ⟕ `loans` por APN o dirección + fecha. Es
   posible y es **inferencia**: dos registros que coinciden en dirección y
   fecha *probablemente* son la misma operación. Este proyecto no afirma cosas
   probables sin decirlo, así que ese cruce tendría que viajar con su grado y
   su tasa de acierto medida, no como un dato.

Y dos columnas se pierden en cualquier caso: **down payment y plazo** no están
en ninguno de los dos. El down payment es la señal de FHA/DPA que usan dos
qualifiers.

## El hallazgo que no esperábamos: `/v1/market`

Creíamos que las métricas de condado vivían solo en la interfaz de Market
Signals. **Están en la API**, por estado, **condado** y ZIP: volumen y unidades,
tasa media, LTV, distribución de score, mix FHA/VA/Conventional, distribución
de canal y de tipo de lender, share de first-time buyers, DTI e ingresos.

Es el activo que no caduca con la prueba y hoy la biblioteca tiene **4
condados**. Por API se llena sin abrir la interfaz.

**No confirmado, y son justo los dos que más usamos**: `fallout %` y `Avg Time
to Close` no aparecen en la descripción de la referencia. El toque 2 de la
secuencia se construye con el fallout del condado.

## Créditos: lo que no puedo decir

El brief exige leer el gasto del ledger y **no estimarlo**. No puedo:

- **`GET /v1/me` devuelve 200 con perfil de usuario y organización, y NO trae
  saldo de créditos**, aunque la documentación lo anuncia como «account profile
  and credit balance». Es una discrepancia abierta entre el spec y la
  respuesta.
- No encontré endpoint de saldo en las 13 rutas declaradas.
- Las páginas `usage-and-credits` y la referencia interactiva están en
  `docs.modelmatch.com` (públicas); las mismas rutas bajo `api.modelmatch.com`
  dan 404. La página de uso hay que mirarla desde la cuenta en el navegador.

**Lo que sí sé que hice**, para que se pueda auditar contra el ledger: unas 30
peticiones a `api.modelmatch.com`, de las cuales **una sola devolvió datos**
(`GET /v1/me`, 200, 672 bytes). El resto fueron 404 de rutas que no existen —
`GET` sobre recursos que son `POST`— y tres `OPTIONS` que devolvieron 204.
**Ninguna llamada a un endpoint de datos.** Si el cobro es por llamada
facturable y no por 404, el gasto debería ser cero, pero **eso hay que
verificarlo en la página de uso**, no creerme a mí.

Lo único publicado sobre precio: **bulk delivery cuesta 1 crédito por fila** y
pide un entitlement por encima de 1.000 filas, que no tenemos.

## Otras dos cosas que conviene saber

- **Hay un servidor MCP oficial** (`/developers/mcp-server`, con página propia
  para Claude). Si funciona, es una vía de integración que no pasa por escribir
  un cliente.
- **`/v1/instant-search`** existe como recurso propio; por nombre, es la
  búsqueda de la interfaz.

## Lo que hay que decidir antes de la fase 1

1. **¿Preguntamos por `/v1/related` antes de gastar?** Es la diferencia entre
   «la API reemplaza la captura» y «la API nos deja a mitad de camino y el
   cruce lo inferimos nosotros».
2. **¿El `fallout` y el `time to close` están en `/v1/market`?** Una llamada lo
   contesta, pero es fase 1.
3. **Rotar la llave.** La que estoy usando llegó por chat, y la regla 1 del
   propio brief dice que la llave no se pega en el chat. Funciona, está en
   `.env` (gitignored, nunca commiteado), pero conviene rotarla cuando termine
   la evaluación.

## Rastro

Las respuestas crudas quedaron en `data/raw/`, que **añadí a `.gitignore` en
este mismo trabajo**: no estaba, y la primera respuesta guardada —`/v1/me`—
trae nombre y correo de la cuenta. El repo es público. Verificado con
`git check-ignore` y con `git log --all -- data/raw` (nunca estuvo en el
historial).
