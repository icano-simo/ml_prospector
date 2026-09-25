# Model Match API · Fase 1 · Ana Osorio, medida contra lo que ya teníamos

Sigue `brief-modelmatch-agents.md`, fase 1. Autorizada por Isabella el
2026-09-24 con la página de uso en 0 créditos consumidos y 1.800 disponibles.

**La conclusión primero:** la API resuelve **el perfil del agente** mejor de lo
que esperábamos, **no resuelve la pestaña Transactions**, y trae una tercera
cosa que no buscábamos y que vale más que las dos: **los registros HMDA del
condado, solicitud por solicitud**.

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

## 4 · Lo que costó

**No lo puedo leer, y el brief prohíbe estimarlo.** `GET /v1/me` devuelve 200 y
no trae saldo. Lo que sí queda registrado, para cotejarlo contra la página de
uso:

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

## 5 · Qué se puede hacer con esto, en orden de valor

1. **Llenar la biblioteca de mercados por API.** Hoy tiene 4 condados. Falta
   resolver cómo agregar sin paginar 882 páginas: el filtro `mode` aparece en
   los tres recursos y podría ser el modo agregado. **Una llamada lo contesta.**
2. **Enriquecer los 4.249 del libro con el perfil de agente**: producción,
   split, subconjunto financiado y conteo de lenders, sin abrir la interfaz.
   Falta medir cuántos cruzan por email o teléfono — es la fase 2 del brief.
3. **Dejar Transactions como está.** Es la única fuente de las operaciones, y
   se pega a mano.

## 6 · Lo que hay que decidir

- **¿`mode` es el modo agregado?** Decide si el mercado se puede traer sin
  paginar.
- **¿`hmdaActionTaken` se puebla?** Decide si el fallout se calcula o se sigue
  copiando del panel.
- **Rotar la llave** al cerrar la evaluación: llegó por chat, que es lo que la
  regla 1 del brief prohíbe.
