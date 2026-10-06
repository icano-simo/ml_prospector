---
name: modelmatch-minado
description: Manual operativo del minado de Model Match para realtors de HOMESÍ — las 34 columnas aprobadas, el payload exacto de cada llamada, la transformación de cada campo, el tope de 2 créditos por lead y la lista de llamadas prohibidas. Cárgala ANTES de extraer, re-extraer o ampliar datos de Model Match para cualquier lote de realtors, y antes de modificar cualquier cosa en `modelmatch/`. Es prescriptiva: si una llamada no está acá, no se hace.
---

# Minado de Model Match — manual operativo

**Regla cero: si una llamada no está en este manual, no se hace.** Cada
llamada cuesta dinero y cada campo de más es un campo que alguien va a leer
mal. Lo aprobado son **34 columnas**, y están listadas una por una.

**Tope: 2 créditos por realtor.** Con este procedimiento el gasto real es
**1** en el 97 % de los casos.

---

## 1 · Conexión

### Qué usar

| | |
|---|---|
| **API REST** `https://api.modelmatch.com` | **para esto**: un lote, repetible, con el crudo en disco |
| MCP `https://mcp.modelmatch.com/mcp` | solo para explorar a mano. **No se usa para un lote** |

El MCP no guarda el crudo, pasa cada respuesta por el contexto de un chat y no
se puede reejecutar igual. Es el mismo backend y el mismo medidor.

### Autenticación

```
Cabecera:  x-api-key: <MODELMATCH_API_KEY>
           Content-Type: application/json
           Accept: application/json
```

La llave vive en el `.env` de la raíz del repo, variable
`MODELMATCH_API_KEY`, y la carga `supabase.config.cargar_env()`.

- **Nunca** se escribe en código, en un docstring, en un log ni en un chat.
- Si aparece en un diff, **la tarea se detiene y la llave se rota**.

### El cliente

Usar `modelmatch/cliente.py`. Ya impone, sin que haya que acordarse: guarda el
crudo antes de mirarlo, no sigue el cursor, revienta antes de salir a la red
si la ruta menciona `enrich` o `bulk-delivery`, reintenta el 429 y espera
entre llamadas.

```python
from modelmatch.cliente import llamar, saldo
d = llamar("/v1/agents/%s" % mm_id, etiqueta="det_%s" % mm_id)
```

### Comprobar el saldo (cuesta 0)

```
GET /v1/me/credits
```

Leer **`balance.total`**. **NO usar `usage.spent`**: va con retraso — se midió
que no se movió ni una décima mientras `balance.total` bajaba 30.

---

## 2 · El presupuesto, y cómo se hace cumplir

```
TOPE_POR_REALTOR = 2
```

### El modelo de costo, medido contra el ledger

| llamada | costo |
|---|---|
| `POST /v1/instant-search` | **0** |
| `POST /v1/agents/count` | **0** |
| `GET /v1/me/credits` | **0** |
| errores 400 · 404 · 429 · 402 | **0** |
| `GET /v1/agents/{id}` | **1** |
| `POST /v1/agents` (lista) | **1 por fila devuelta** |
| `POST /v1/agents/{id}/breakdowns/*` | **1 por fila devuelta** |

**La regla: se cobra lo que devuelve FILAS. Lo que devuelve un NÚMERO es
gratis.**

### Reparto esperado por realtor

| paso | costo | columnas que paga |
|---|---|---|
| 1 · identificar | 0 | — |
| 2 · ficha | **1** | 26 |
| 3 · verificar | 0 | — |
| 4 · banderas y exclusión | 0 | 5 |
| 5 · breakdown, solo si cabe | 0 ó 1 | 3 |

### Las cuatro guardas, obligatorias

1. **Antes de cada breakdown**, comparar `totalXWorkedWith` de la ficha con lo
   que queda del tope. Si no cabe, **no se pide** y la celda dice por qué.
2. **El acumulado vive en el registro del realtor** (`creditos_gastados`), y
   **cualquier script posterior que compre algo para ese realtor tiene que
   volver a comprobar el tope**. Esto ya falló: una compra dirigida sumó sobre
   perfiles que ya estaban en el tope y siete terminaron entre 6 y 8.
3. **Conciliar con el ledger cada 25 realtors**: gasto previsto contra
   `balance.total`. Si divergen, parar. En la corrida de referencia el modelo
   predijo 422 y el ledger dijo 422.
4. **Reanudable**: cada realtor se guarda apenas termina, en su propio
   archivo. Volver a correr no re-paga lo hecho.

---

## 3 · El procedimiento, paso a paso

### Paso 1 · Identificar al realtor — 0 créditos

**Lo que hace falta de nuestra base:** nombre completo, **todos** los correos,
**todos** los teléfonos, estado, y el brokerage que teníamos.

#### Llamada

```json
POST /v1/instant-search
{"query": "<correo nuestro>"}
```

Una llamada por correo, **máximo 2**. Si ninguna resuelve, **una más** con el
nombre completo. No más de 3 en total.

La respuesta trae `results.agents[]`, cada uno con: `id`, `modelMatchId`,
`fullName`, `firstName`, `lastName`, `email`, `office`, `officeKey`, `city`,
`state`, `zip`, `volume`, `units`, `avgSoldPrice`, `_geo`.

#### Cómo decidir cuál es — en este orden, sin saltarse ninguno

La búsqueda es **difusa**: buscando un correo pueden salir cinco personas, dos
con el mismo nombre y apellido en otros estados.

Normalizar = minúsculas, sin tildes, sin puntuación, espacios colapsados.

| orden | criterio | se anota como | confianza |
|---|---|---|---|
| 1 | alguno de **nuestros correos** está en el campo `email` del candidato (que trae **varios separados por `;`**) | `email_exacto` | alta |
| 2 | el correo coincide en **más de un** candidato (perfiles duplicados) → gana el de mayor `volume` | `email_exacto_varios_perfiles` | alta |
| 3 | `fullName` normalizado idéntico **y** `state` igual al nuestro, y **solo uno** cumple | `nombre_exacto_y_estado` | media |
| 4 | nada de lo anterior | `nombre_exacto_sin_estado`, `ambiguo` o `sin_candidatos` | **ninguna** |

**En el caso 4 NO se elige a nadie y NO se gasta ni un crédito.** Se guardan
los candidatos con su nombre, brokerage, ciudad, estado y correo para que una
persona decida.

### Paso 2 · La ficha — 1 crédito

```
GET /v1/agents/{mm_id}
```

Sin cuerpo. Devuelve `data` con 27 campos de primer nivel más el bloque
`scored`. **Paga 26 de las 34 columnas de una sola vez.**

**Siempre la ficha, nunca `POST /v1/agents` para un agente concreto:** cuestan
lo mismo (1) y la lista **no trae el bloque `scored`**, que es donde están las
compras financiadas.

### Paso 3 · Verificar la identificación — 0 créditos

Con la ficha ya pagada, sin llamadas nuevas:

- **`telefono_coincide`**: ¿alguno de nuestros teléfonos está entre los suyos?
  Comparar **solo dígitos**, quitando el `1` inicial si quedan 11.
- **`cambio_de_brokerage`**: comparar nuestro brokerage con `office`,
  normalizados y **por los primeros 12 caracteres**, para que «Realty Concepts
  Ltd» y «realty concepts, ltd. - fresno» no cuenten como cambio.

**Confianza final — el orden importa:**

1. criterio empieza por `email_exacto` → **alta**. Un teléfono distinto **no**
   lo contradice: Model Match suele tener el de oficina y nosotros el celular.
2. si no, y el teléfono coincide → **alta, confirmada por teléfono**.
3. si no, y el teléfono **no** coincide → **a revisión**, aunque el nombre y el
   estado calcen. Es la señal de que son dos personas.
4. si no hay teléfono para comparar → se queda con la confianza del paso 1.

### Paso 4 · Banderas y exclusión — 0 créditos

**Usar el endpoint de CONTEO, que no cobra, con el id del agente.** `total`
devuelve **1** (sí) o **0** (no).

#### Tipo de préstamo — 3 llamadas, una por tipo

```json
POST /v1/agents/count
{"flatFilters": {"id": "<mm_id>"},
 "footprint": {"dimension": "lender",
               "product": {"mix": "loanType", "key": "fha"}},
 "period": "last24Months"}
```

Repetir con `"key": "conventional"` y `"key": "va"`.

⚠ **NO agregar `shareOfUnits` ni ningún umbral de porcentaje a este
footprint.** Con `dimension: lender` sin lender fijo, el porcentaje se mide
**dentro de un bucket de lender suelto**, no sobre el agente: un agente con
20 % de FHA real aparece en la banda «≥50 %». Costó 503 créditos descubrirlo.
**Solo el sí/no es válido.**

#### Relación con la casa — 1 llamada

```json
POST /v1/agents/count
{"flatFilters": {"id": "<mm_id>"},
 "footprint": {"lender": [<ids de la casa>]},
 "period": "allTime"}
```

- Los ids están en `modelmatch/everett.py`, lista `CASA`, **comprobados contra
  `instant-search`**. Ahí mismo está `NO_ES_LA_CASA`: bancos de la ciudad de
  Everett y una persona apellidada Everette que **no** son la casa.
- **`period` = `allTime`, no `last24Months`.** Con 24 meses dan 28 realtors y
  con el historial completo dan 79. Para una exclusión, una operación de hace
  tres años sigue contando.

#### El peso de esa relación — solo si la anterior dio 1

Repetir la misma llamada agregando `"units": {"gte": N}` dentro del
`footprint`, con N = 2, 3, 5, 10, 20. El mayor N que devuelva 1 es el tramo.

✅ **Acá el umbral SÍ significa lo que dice**, porque el lender es explícito.
Comprobado contra un caso con 3 operaciones en su tabla cruda: aparece en 1, 2
y 3 y desaparece en 5.

### Paso 5 · Breakdown de originadores — solo si cabe

```json
POST /v1/agents/{mm_id}/breakdowns/originators
{}
```

**Pedir SOLO si `totalOriginatorsWorkedWith ≤ (2 − gastado)`.** Si no cabe, la
celda dice «no consultado · N filas y quedaban M créditos».

⛔ **NO se puede pedir solo la primera fila. Medido.** Se mandó
`pagination: {size: 1}` con `sort` por unidades: **no lo rechazó, lo ignoró** —
devolvió 3 filas y cobró 3. **No reintentar.**

⚠ **El orden que devuelve la API es por VOLUMEN, no por unidades.** Para
nosotros manda **unidades**: lo que cuenta es a cuántos clientes les presentó
un prestamista, no cuán caras eran las casas. En un caso real el primero por
volumen tenía 2 operaciones y el segundo 4. **Reordenar por `units` antes de
tomar el principal.**

---

## 4 · Campo por campo

Para cada columna: de qué llamada sale, qué campo de la API es, y qué
transformación se le aplica. **El nombre de la columna es exactamente el de la
tercera fila de la tabla** — no se renombra.

### A · De la ficha `GET /v1/agents/{id}` — 26 columnas, 1 crédito

| campo de la API | columna del Excel | transformación |
|---|---|---|
| `id` | `ID Model Match` | tal cual |
| `office` | `Brokerage (Model Match, hoy)` | tal cual |
| `email` + `linkedProfiles[].email` | `Emails en Model Match` | partir por `;` y `,`, minúsculas, quedarse con los que tienen `@`, quitar repetidos, ordenar, unir con `" · "` |
| `phone` + `linkedProfiles[].phone` + `linkedProfiles[].officePhone` | `Teléfonos en Model Match` | solo dígitos; si quedan 11 y empieza por `1`, quitar el `1`; quitar repetidos y vacíos; unir con `" · "` |
| `linkedProfileCount` | `Perfiles enlazados` | si viene vacío, usar `len(linkedProfiles)` |
| `city` | `Ciudad (MM)` | tal cual |
| `state` | `Estado (MM)` | tal cual |
| `zip` | `ZIP (MM)` | tal cual |
| `licenseNumber` | `Licencia (MM)` | tal cual. Vacío en ~la mitad: vacío es «no lo sabe», no «no tiene» |
| `units` | `Unidades 12m (MM)` | tal cual |
| `volume` | `Volumen 12m (MM)` | tal cual |
| `avgSoldPrice` | `Precio medio` | tal cual |
| `buyerUnits` | `Compras (u)` | tal cual |
| `buyerVolume` | `Compras ($)` | tal cual |
| `sellerUnits` | `Ventas (u)` | tal cual |
| `sellerVolume` | `Ventas ($)` | tal cual |
| `dualUnits` | `Dual (u)` | tal cual |
| `scored.total_mortgaged_buyer_units` | `Compras FINANCIADAS (u)` | tal cual. **Es el número que decide el encaje** |
| `scored.total_mortgaged_buyer_volume` | `Compras financiadas ($)` | tal cual |
| `scored.total_mortgaged_listing_units` | `Ventas financiadas (u)` | tal cual |
| `scored.total_percent_units_mortgaged` | `% unidades financiadas` | redondear a 1 decimal |
| `scored.total_percent_volume_mortgaged` | `% volumen financiado` | redondear a 1 decimal |
| `scored.average_mortgaged_loan_amount` | `Loan medio de sus compradores` | tal cual |
| `totalLendersWorkedWith` | `Nº lenders` | tal cual |
| `totalOriginatorsWorkedWith` | `Nº originadores` | tal cual |
| `totalCompaniesWorkedWith` | `Nº compañías` | tal cual |

### B · De los conteos — 5 columnas, 0 créditos

| llamada | columna | valor |
|---|---|---|
| count + `product.key: fha` | `¿Produce FHA?` | `total == 1` → `"sí"`, si no `"no"` |
| count + `product.key: conventional` | `¿Produce convencional?` | ídem |
| count + `product.key: va` | `¿Produce VA?` | ídem |
| count + `footprint.lender: CASA`, `allTime` | `¿Ya financia con la casa?` | `total == 1` → `"SÍ"`, si no `"no"` |
| el mismo con `units {gte:N}` por tramos | `Operaciones con la casa (al menos)` | el mayor N que dio 1 |

### C · Del breakdown — 3 columnas, 1 por fila

| columna | cómo |
|---|---|
| `Su loan officer principal` | del breakdown de originadores, el `label` de la fila con **más `units`** (no la primera que devuelve la API) |
| `Lenders (si cupo en el tope)` | `"<label> (<units> u)"` unidos con `" · "`; si no se pidió, `"no consultado · <N> filas y quedaban <M> créditos"` |
| `Originadores (si cupo)` | ídem con originadores |

### D · Calculadas — 13 columnas, 0 créditos

| columna | cómo |
|---|---|
| `¿En Model Match?` | `"sí"` si el paso 1 resolvió, si no `"NO"` |
| `Cómo se identificó` | el criterio del paso 1, textual |
| `Confianza` | la regla del paso 3 |
| `⚠ Revisar porque…` | el motivo concreto; **vacío** si el match es confiable |
| `¿Teléfono coincide?` | `"si"` / `"no"` / `"sin_dato"` |
| `Candidatos vistos` | cuántos `id` distintos devolvió la búsqueda |
| `¿Cambió de casa?` | `"si"` / `"no"` / `"sin_dato"` |
| `Nº emails` · `Nº teléfonos` | el largo de cada lista |
| `¿Fidelizado con un LO?` | tramos de `Nº originadores`: 1 = `CAUTIVO · 1 solo LO`; 2-3 = `muy concentrado`; 4-6 = `concentrado`; 7-12 = `reparte`; 13+ = `reparte mucho` |
| `% por su LO principal` | unidades del LO top ÷ **suma de las unidades de todos sus LOs**. ⚠ **NO usar el `pctUnits` de la API**: su denominador no son las operaciones del agente y llega a dar 167 % |
| `Créditos gastados` | el acumulado real del realtor |
| `Consultado` | sello de tiempo UTC |

---

## 5 · Llamadas prohibidas

Si el código las menciona, el cliente revienta antes de salir a la red.

| | por qué |
|---|---|
| `enrichProperty`, `enrichPropertiesBatch`, `enrichPropertiesBulk` | skip-trace del **dueño de la propiedad**: nombre, teléfono y correo de un consumidor, para un prestamista. **10 créditos por match** |
| cualquier `*BulkDelivery` sin aprobación escrita | 1 crédito por fila, sin tope natural |
| seguir el `cursor` | multiplica el costo en silencio |
| `POST /v1/agents` para un agente concreto | cuesta lo mismo que la ficha y trae menos |
| `/sales`, `/properties`, `/related`, `/v1/market` | no producen ninguna de las 34 columnas aprobadas |
| breakdowns de `lenders`, `companies`, `counties` sin que quepan en el tope | 1 por fila |
| los filtros de tract de `/v1/market` para **elegir** a quién contactar | `minorityTractPct`, `majorityMinorityTract`, `lowModIncomeTract`: segmentar por ahí es redlining y es exposición de fair lending |

---

## 6 · Antes de dar por buena una corrida

1. **gasto previsto == gasto del ledger**. Si no, el modelo de costo cambió.
2. **ningún realtor por encima de 2 créditos.**
3. **ningún match inventado**: los no resueltos están marcados y con sus
   candidatos guardados.
4. **dos caminos al mismo hecho coinciden**: los marcados con la casa por
   `footprint` tienen que aparecer con la casa en su tabla cruda de lenders,
   en aquellos donde se haya comprado esa tabla.
5. **ningún porcentaje de la API usado sin contrastar** contra un caso cuya
   respuesta se conozca por otra vía.

### Resultado de referencia

298 realtors → 273 identificados (189 por correo, 51 por teléfono), 50 a
revisión, **445 créditos**, media 1,49. El ledger confirmó el modelo al
crédito.

---

## 7 · Lo que NO sale de Model Match

Para que nadie lo busque ahí:

- **Instagram** — es scraper propio.
- **Idioma, apellido, origen** — no están, y es correcto que no estén. Esas
  señales salen de Instagram y del modelo de scoring.
- **Antigüedad en la industria del realtor** — no existe el campo. El rodeo:
  pedir producción en un año viejo (`period: "2024"`, `units {gte:1}`), que
  además es más duro, porque exige que estuviera produciendo.
- **Las operaciones una por una con su tipo de préstamo y monto** — la
  pestaña Transactions se sigue pegando a mano.
