# Model Match API · Fase 1 · Ana Osorio, medida contra lo que ya teníamos

Sigue `brief-modelmatch-agents.md`, fase 1. Autorizada por Isabella el
2026-09-24 con la página de uso en 0 créditos consumidos y 1.800 disponibles.

**La conclusión primero:** la API resuelve **el perfil del agente** mejor de lo
que esperábamos —incluido el **wallet share**, que no sabíamos que estaba—,
**no resuelve la pestaña Transactions**, y trae una tercera cosa que no
buscábamos: **los registros HMDA del condado, solicitud por solicitud**.

**Y una advertencia operativa que llegó al final:** el saldo real de la cuenta
es de **5,22 créditos**, y una llamada de breakdown cuesta **10**. Lo dice el
cuerpo de un 402, que es la única lectura de saldo que da la API. La evaluación
está frenada por saldo, no por alcance.

## 1 · El agente: mejor de lo esperado

`POST /v1/agents` con `{"name": {"match": "Ana Osorio"}, "state": "IL"}`
devolvió **`total: 1`**. Una sola coincidencia en Illinois: no hay que
desambiguar.

El detalle (`GET /v1/agents/{id}`) trae 28 campos, y tres bloques que la
referencia pública no menciona:

| bloque | qué trae |
|---|---|
| producción | units, volume, avgSoldPrice, y el split buy/seller/dual en unidades y volumen |
| **`scored`** (32 claves) | **el subconjunto FINANCIADO**: `total_mortgaged_buyer_units`, `total_mortgaged_buyer_volume`, `average_mortgaged_loan_amount`, `total_percent_units_mortgaged`, `total_percent_volume_mortgaged`, y lo mismo para el lado listing y dual |
| **`linkedProfiles`** (8) | los perfiles duplicados que la API considera la misma persona, cada uno con su teléfono, su teléfono de oficina y su número de operaciones |
| red | `totalLendersWorkedWith`, `totalOriginatorsWorkedWith`, `totalCompaniesWorkedWith` — **conteos, no nombres** |

### Contra nuestra captura a mano

| | API · 12 meses | pegado · 14 meses |
|---|---|---|
| buys | 17 | 18 |
| listings | 6 | 7 |
| volumen buy side | $5.131.000 | $5.317.000 |
| volumen listing side | $2.420.000 | $2.730.000 |
| **compras financiadas** | **9** | **8** |
| % unidades con hipoteca | 60,9 % | — |
| loan medio | $241.974 | — |
| lenders con los que trabajó | 8 | **5** |

Las diferencias de unidades y volumen se explican por la ventana (12 contra
14 meses) y van en la dirección correcta. Las dos filas que importan:

- **«compras financiadas 9 contra 8»** es el número que decide el encaje, y
  sale de la API ya calculado. Nosotros lo derivamos de 25 filas pegadas.
- **«8 lenders contra 5»** no es ventana: nosotros contamos solo los lenders
  que aparecen en las compras que pudimos leer. La API cuenta todos. Nuestro
  «5» era un piso, no un total, y no lo decíamos.

### Y una cosa que no teníamos

El campo `email` de la API trae **dos direcciones separadas por `;`**: la
personal que ya teníamos, y una corporativa del brokerage **anterior**. Su
`office`, en cambio, dice el brokerage **actual**. Es justo la queja pública
sobre Model Match —agentes con la casa vieja— y aquí se ve el mecanismo: el
office está al día y el correo arrastra el anterior.

Para nosotros eso es una regla, no una anécdota: **el correo corporativo que
venga de la API no se usa para contactar sin comprobar el brokerage**, porque
puede ser un buzón que ya no lee nadie.

`licenseNumber` viene **null**, y `licenses` también. El identificador estable
existe (`id` / `modelMatchId`) pero **la licencia estatal no está poblada**
para ella, así que el cruce con nuestro roster va por email o teléfono.

## 2 · La pestaña Transactions: NO se puede reconstruir

Es la respuesta a la pregunta que abría la consulta comercial, y ahora está
medida, no supuesta:

| intento | resultado |
|---|---|
| `/v1/loans` filtrado por agente | **no existe el filtro**: `loans` no conoce al agente |
| `/v1/sales` con `flatFilters.agentId` | 400 · la clave no existe |
| `/v1/sales` con `soldAgent` = su `modelMatchId` | 200 · **`total: 0`** |
| `/v1/sales` con `soldAgent` = `{"match": "ana osorio"}` | 200 · **1.052 filas**, con «Anna Comer», «Lisa Soltesz» y «Jason Osorno» dentro |
| `/v1/sales` con `soldAgent` = `"ana osorio"` exacto | 200 · `total: 0` |
| `/v1/related` | **404** · está en la documentación y no en este despliegue |

Y en las filas de `sales`, **`soldAgentId` y `listingAgentId` vienen `null`**:
solo hay nombre. Atribuir operaciones a una persona por un nombre en búsqueda
difusa es exactamente lo que este proyecto no hace.

**Conclusión:** las 21 columnas de Transactions no tienen equivalente por API.
Model Match hace ese cruce dentro de su interfaz y no lo expone. Para las
operaciones, el pegado sigue siendo la única fuente.

## 3 · El hallazgo: `/v1/market` es HMDA, no el panel

Esperábamos el panel de Market Signals. Es otra cosa, y es mejor: **registros
de solicitud de préstamo, uno por fila**, filtrables por condado.

`{"county": "Cook", "state": "IL"}`, 12 meses → **`total: 88.195`**.

30 campos por fila. Los de una fila real de Cook:

```
loanType conventional · loanPurpose purchase · loanAmount 126000
purchasePrice 130000 · appraisedValue 145000 · ltv 97 · combinedLtv 102
noteRate 7.75 · loanTerm 360 · amortizationType fixed · channel correspondent
creditScore 787 · income 53372.76 · dti 29.107 · dtifront 24.251
firstTimeHomebuyer False · currentHomeOwner True · selfEmployed False
veteranIndicator False · borrowerGeneration 'gen x'
occupancyType primary · propertyType detached · zip 60636 · county '031'
loanApplicationDate 2026-09-23 · closingDate 2026-09-21 · fundingDate None
hmdaActionTaken ''
```

**Todo lo que hoy raspamos del panel se puede calcular de estas filas, con el
denominador a la vista** — que es justo lo que al panel le falta. Y dos cosas
que el panel da masticadas salen aquí mejor:

- **`time to close`**: `loanApplicationDate` → `closingDate`, por préstamo. Hoy
  copiamos un promedio sin denominador.
- **fallout**: el campo es `hmdaActionTaken`. **En la fila que trajimos viene
  vacío**, así que hay que comprobar si se puebla; si se puebla, el fallout se
  calcula en vez de copiarse.

### ⚠ Y una advertencia de cumplimiento, en voz alta

Los filtros aceptados de `/v1/market` incluyen `minorityTractPct`,
`majorityMinorityTract`, `lowModIncomeTract`, `communityIncomeLevel` y
`craEligible`.

**Que el dato esté no significa que se pueda usar.** Segmentar prospectos por
el porcentaje de minoría del tract es redlining de manual, y para un lender es
exposición de fair lending, no una métrica más. Estos cinco campos no entran en
el motor ni en un filtro de prospección. Si algún día se usan, será para
*medir* nuestra propia cobertura, nunca para *elegir* a quién escribirle — y
esa decisión no la toma el código.

## 3 bis · Los breakdowns: la tabla de originadores SÍ sale por API

Lo dijo la propia respuesta. Dentro de `scored` viene:

> `Per-relationship arrays were omitted to keep this response small. Fetch them
> via POST /agents/{id}/breakdowns/{originators|companies|lenders}`

No está en la referencia pública. Las tres rutas responden 200 con el prefijo
`/v1`, y cada fila trae **`label`, `units`, `volume`, `pctUnits`, `pctVolume`**:

| breakdown | filas de Ana |
|---|---|
| `originators` | 10 · el más grande con 3 unidades, el resto con 1 o 2 |
| `lenders` | 8 · el mayor con 4 unidades y 13 % del volumen |
| `companies` | 7 · el mayor con 3 unidades y 12 % del volumen |

Los nombres de los originadores no van acá: el repo es público y son personas.
Están en el crudo de `data/raw/`, que sí está ignorado.

Es el wallet share que hoy se pega a mano, y con **los dos porcentajes
explícitos** — que es más de lo que tenemos: nuestro parser tiene que deducir
si el reparto está en unidades o en volumen y guardarlo en `wallet_share_base`.

**Con dos limitaciones que importan y una sin medir:**

1. **No trae NMLS.** El originador es un `label` de texto. Nuestra `tab_orig`
   guarda el NMLS, que es lo que identifica a la persona sin ambigüedad.
2. **No separa por lado.** `pctUnits` de una relación con 1 unidad da
   `0,04347…` = **1/23**, y 23 es `total_sold_units`: compras **más** ventas.
   La exclusión por no-canibalización se decide sobre el reparto del lado
   comprador (17). Son otro denominador y otro reparto.
3. **Si acepta `side` quedó sin medir**: la llamada que lo probaba se cortó por
   saldo. Es **una sola llamada** y decide si `orig_buyer` sale por API.

## 4 · Lo que costó: el saldo lo dice el 402, no `/v1/me`

`GET /v1/me` responde 200 y no trae saldo, pero **el error de saldo sí lo
trae**, y es la única lectura autorizada que conseguimos:

```
402 payment_required
{"balance": 5.2212, "cost": 10, "reason": "out_of_credits"}
```

Dos cosas, las dos medidas:

- **Una llamada de breakdown cuesta 10 créditos.** Las tres de Ana costaron 30.
- **El saldo real es 5,22.** La página de uso decía «10 de 1800» cuando el
  saldo ya estaba en ~35. **Las dos cifras no hablan de lo mismo**, y la que
  manda es la del 402: con 5,22 no entra ninguna llamada de 10.

Antes de seguir hay que aclarar qué cuenta la página de uso y recargar. Lo que
sí queda registrado de esta fase:

| llamada | veces | estado |
|---|---|---|
| `POST /v1/agents` | 2 | un 400 (clave mal) y un 200 con 1 fila |
| `GET /v1/agents/{id}` | 2 | un 429 y un 200 con 3.546 bytes |
| `POST /v1/sales` | 4 | un 400, dos 200 con `total: 0`, un 200 con 5 filas |
| `POST /v1/market` | 3 | un 400, un 200 con `total: 0`, un 200 con 3 filas |
| `POST /v1/related` | 1 | 404 |

**Doce llamadas, de las cuales cinco devolvieron datos** (una lista de agentes
de 1 fila, un detalle, 5 ventas, 3 filas de mercado y dos respuestas vacías).
Ninguna paginada, ninguna de enrichment, ninguna de bulk delivery.

Dos cosas operativas que conviene saber:

- **Hay límite de velocidad.** Dos llamadas seguidas con un segundo de pausa
  dieron `429 rate_limited`. El cliente espera **12 segundos** entre llamadas.
- **Los 400 son la mejor documentación que hay.** Cada clave equivocada
  devuelve la lista entera de claves aceptadas, y es más completa que la
  referencia pública. Así se descubrió que el filtro es `name` y no
  `fullName`, y que `/v1/market` es HMDA.

## 5 · Lo que capturamos a mano, campo por campo

El inventario sale de `captura/parser_mm.py`, que es lo que de verdad se
parsea, no de lo que recordamos que se pega.

### Perfil / Overview — **la mayoría sale, y algo sale mejor**

| lo nuestro | API | |
|---|---|---|
| `nombre`, `emails` | `fullName`, `email` | ✅ |
| `buyer_units`, `listing_sold`, `buyer_volume` | `buyerUnits`, `sellerUnits`, `buyerVolume` | ✅ |
| `buyside_anualizado` | se calcula igual | ✅ |
| — (no lo teníamos) | **subconjunto financiado**: 9 compras, loan medio, % | ✅ **gana la API** |
| `cabecera_lenders.total_lenders` | `totalLendersWorkedWith` | ✅ |
| `cabecera_lenders.avg_loan_size` | `average_mortgaged_loan_amount` | ✅ |
| `total_originators_declarado` | `totalOriginatorsWorkedWith` | ✅ |
| `tabla_lenders` | `breakdowns/lenders` | ✅ |
| `tab_orig` | `breakdowns/originators`, **pero sin NMLS** | ⚠ |
| `orig_buyer` / `orig_seller` | el breakdown **no separa por lado** | ⚠ sin medir |
| `licencia` | `licenseNumber` viene `null` para Ana | ⚠ |
| `contacto` | `phone`, `office`, `city`, `zip`; **sin dirección de calle** | ⚠ |
| `los_buyer` / `los_seller` | solo el total, sin repartir por lado | ⚠ |
| `producer_tier`, `side_focus`, `referral_concentration` | no están | ❌ |
| `loan_mix_buyer` (la mitad de agente del contraste FHA) | no está | ❌ |
| `tpo_pct` | no está | ❌ |
| `condados` (`View Counties`) | no están en el detalle del agente | ❌ |

### Transactions — **no sale nada**

Las 21 columnas no tienen equivalente. Ver la sección 2.

### Market Signals — **el insumo sí, los indicadores no**

De las ~30 métricas que parsea `parsear_mercado`:

- **Se pueden recalcular** de las filas HMDA, con mejor denominador:
  `avg_rate`, `avg_ltv`, `avg_term`, `avg_score`, `avg_income`, `ftb`,
  `repeat`, `veterans`, `self_emp`, las tres bandas de crédito,
  `millennial`/`genz`, la distribución por `loanType`, el canal, `jumbo` y
  `conforming` por monto, y `time_to_close` **por préstamo**.
- **No están, porque son cálculos de Model Match sobre datos que no expone**:
  `status` (Market Status), `applications`, `approvals`, `locks` —los tres son
  variaciones porcentuales—, `funded`, `adquisicion` (Mortgage Acquisition
  Rate) y `fallout` (su campo, `hmdaActionTaken`, vino vacío).
- **Y el costo lo vuelve teórico por ahora**: recalcular Cook pide recorrer
  88.195 filas.

**Resumen en una línea:** el **perfil del agente** y el **wallet share** salen
por API y en parte mejoran lo que tenemos; **Transactions no sale**; y de
**Market Signals** sale el insumo crudo pero no los seis indicadores que Model
Match calcula.

## 6 · Qué se puede hacer con esto, en orden de valor

1. **Llenar la biblioteca de mercados por API.** Hoy tiene 4 condados. Falta
   resolver cómo agregar sin paginar 882 páginas: el filtro `mode` aparece en
   los tres recursos y podría ser el modo agregado. **Una llamada lo contesta.**
2. **Enriquecer los 4.249 del libro con el perfil de agente**: producción,
   split, subconjunto financiado y conteo de lenders, sin abrir la interfaz.
   Falta medir cuántos cruzan por email o teléfono — es la fase 2 del brief.
3. **Dejar Transactions como está.** Es la única fuente de las operaciones, y
   se pega a mano.

## 7 · Lo que hay que decidir

- **El saldo, primero.** 5,22 créditos y la llamada más barata que probamos
  cuesta 10. Hay que aclarar qué mide el «10 de 1800» de la página de uso y
  recargar antes de cualquier otra cosa.
- **¿El breakdown acepta `side`?** Una llamada. Decide si `orig_buyer` —el
  reparto que dispara la exclusión por no-canibalización— sale por API o se
  sigue pegando.
- **¿`mode` es el modo agregado?** Decide si el mercado se puede traer sin
  paginar 882 páginas.
- **¿`hmdaActionTaken` se puebla?** Decide si el fallout se calcula o se sigue
  copiando del panel.
- **Rotar la llave** al cerrar la evaluación: llegó por chat, que es lo que la
  regla 1 del brief prohíbe.
