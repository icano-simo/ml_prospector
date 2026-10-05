---
name: modelmatch-minado
description: Manual reproducible del minado de Model Match que produce las 47 columnas de realtors del Excel de HOMESÍ — cómo conectarse, el modelo de costo medido, el tope de 2 créditos por lead, la desambiguación sin adivinar, y qué llamada produce cada columna. Cárgala ANTES de extraer, re-extraer o ampliar datos de Model Match para cualquier lote de realtors, y antes de modificar cualquier cosa en `modelmatch/`. Contiene el presupuesto por perfil y las trampas de porcentajes, ventanas y conteos que no se pueden re-derivar del dato.
---

# Minado de Model Match — manual reproducible

Produce, para cada realtor de una lista, **34 columnas directas de Model Match
y 13 derivadas de ellas**. Está escrito para que otro agente lo ejecute y
obtenga el mismo resultado, no para que lo lea por encima.

**El tope es 2 créditos por lead.** Con el método de abajo, el gasto real es
**1 crédito** en el 97 % de los casos. Si una corrida promedia más de 2, algo
se está pidiendo que no está en este manual: parar y revisar.

---

## 0 · Antes de la primera llamada

### Conexión

Hay dos puertas al mismo backend y al mismo medidor de créditos:

| | cuándo |
|---|---|
| **API REST** (`https://api.modelmatch.com`) | **para esto**. Un lote de cientos de realtors, repetible, con el crudo en disco |
| **MCP** (`https://mcp.modelmatch.com/mcp`, OAuth 2.1) | para explorar y validar formas a mano |

El MCP no sirve para un lote: no guarda el crudo, cada respuesta pasa por el
contexto de un chat y no se puede reejecutar igual. Las herramientas del MCP
se generan desde los mismos endpoints REST, así que lo que se aprende en uno
vale en el otro.

**Autenticación REST:** cabecera `x-api-key`. La llave vive en el `.env` de la
raíz del repo, en `MODELMATCH_API_KEY`, y la carga `supabase.config.cargar_env`.
**Nunca se escribe en código ni se pega en un chat.** Si aparece en un diff,
la tarea se detiene y la llave se rota.

El cliente ya existe: `modelmatch/cliente.py`. Impone, sin que haya que
acordarse: guarda el crudo antes de mirarlo, no sigue el cursor salvo que se
pida, revienta antes de salir a la red si la ruta menciona enrichment o
bulk-delivery, y reintenta el 429.

### Comprobar el saldo (gratis)

```
GET /v1/me/credits
```

Usar **`balance.total`**. `usage.spent` va con retraso: se comprobó que no se
movió ni una décima mientras siete llamadas bajaban el saldo 30. `usage.
spentByCategory` separa lo nuestro (`api`) de lo que gasta el chat de la app
(`ai_agent`), y conviene mirarlo antes de culpar a la extracción por un
consumo que no es suyo.

---

## 1 · El modelo de costo, medido contra el ledger

No está documentado por el proveedor. Esto se midió leyendo `balance.total`
antes y después de cada llamada. **Ninguno está estimado.**

| llamada | costo |
|---|---|
| `POST /v1/instant-search` | **0** |
| `POST /v1/agents/count`, `/v1/loans/count` | **0** |
| `GET /v1/me`, `/v1/me/credits` | **0** |
| errores 400 · 404 · 429 · 402 | **0** |
| `GET /v1/agents/{id}` | **1** |
| `POST /v1/agents` (lista) | **1 por fila devuelta** |
| `POST /v1/agents/{id}/breakdowns/*` | **1 por fila** |
| `/sales`, `/properties`, `/related`, `/v1/market` | **1 por fila** |
| bulk delivery | 1 por fila; cancelar NO cobra |
| enrichment (skip-trace) | 10 por match · **PROHIBIDO** |

**La regla que lo resume: se cobra lo que devuelve FILAS. Lo que devuelve un
NÚMERO es gratis.** De ahí sale todo el método: contar antes de listar, y usar
el conteo con un id concreto para obtener un sí/no por agente sin pagar.

**El corolario que hace cumplible el tope:** `totalLendersWorkedWith`,
`totalOriginatorsWorkedWith` y `totalCompaniesWorkedWith` vienen en la ficha y
**son** el número de filas de su breakdown. Después de pagar 1 crédito se sabe
exactamente lo que costaría cada listado antes de pedirlo.

---

## 2 · El presupuesto por lead

```
tope_duro = 2 créditos por realtor
```

Se comprueba **antes** de cada pedido, no después. Reparto esperado:

| paso | costo | qué columnas paga |
|---|---|---|
| identificar con `instant-search` | **0** | ninguna; da el `mm_id` |
| ficha `GET /v1/agents/{id}` | **1** | las 26 de la ficha |
| banderas FHA / convencional / VA | **0** | 3 |
| exclusión por la casa + su peso | **0** | 2 |
| **subtotal** | **1** | **31 de 34** |
| breakdown de originadores, solo si `totalOriginatorsWorkedWith ≤ 1` | 0 ó 1 | 1 |

Las dos columnas que quedan —`lenders_txt` y `originators_txt`, con los
nombres— cuestan 1 por fila y **no entran en el tope** para un agente normal:
la mediana es 10 lenders y 10 LOs. Se piden solo cuando el conteo de la ficha
dice que caben.

**Guardas obligatorias en el código:**

1. Antes de cada breakdown, comparar `totalXWorkedWith` con lo que queda del
   tope. Si no cabe, **no se pide** y la celda dice por qué.
2. El acumulado por realtor se lleva en el propio registro
   (`creditos_gastados`), y cada script posterior que compre algo para ese
   realtor **tiene que volver a comprobar el tope**. Esto ya falló una vez:
   una compra dirigida posterior sumó sobre perfiles que ya estaban en el
   tope y siete terminaron entre 6 y 8 créditos.
3. Conciliar con el ledger cada 25 realtors: comparar el gasto previsto por el
   modelo contra `balance.total`. Si divergen, parar. En la corrida de
   referencia el modelo predijo 422 y el ledger dijo 422.

---

## 3 · El procedimiento, paso a paso

### Paso 0 · La lista de trabajo

Por cada realtor hacen falta, de nuestra base: nombre, **todos** los correos,
**todos** los teléfonos, estado, y el brokerage que teníamos. Los correos son
la llave de desambiguación y los teléfonos la verificación posterior.

`modelmatch/construir_lista.py` la arma. **Pagina siempre**: PostgREST corta
en ~1000 filas y no avisa.

### Paso 1 · Identificar — 0 créditos

```
POST /v1/instant-search   {"query": "<un correo nuestro>"}
```

Una llamada por correo (máximo 2). Si ninguna resuelve, una más con el nombre
completo. La respuesta trae `results.agents[]` con id, nombre, correos,
brokerage, ciudad, estado y volumen.

**La búsqueda es DIFUSA.** Buscando el correo de una agente salieron cinco
candidatas, dos con su mismo nombre y apellido en otros estados. Por eso el
nombre nunca decide solo.

**Orden de decisión, sin excepciones:**

1. **`email_exacto`** — alguno de nuestros correos aparece en el campo `email`
   del candidato (que trae **varios separados por `;`**). Llave dura.
2. **`email_exacto_varios_perfiles`** — el correo coincide en más de uno: son
   perfiles duplicados del mismo agente. Gana el de más volumen, y queda
   dicho en la columna.
3. **`nombre_exacto_y_estado`** — nombre normalizado idéntico **y** mismo
   estado, y solo uno cumple.
4. **`nombre_exacto_sin_estado`** / **`ambiguo`** / **`sin_candidatos`** — no
   alcanza. **No se elige ninguno.** Se guardan los candidatos con su
   brokerage, ciudad y correo para decidir a mano.

Normalizar = minúsculas, sin tildes, sin puntuación, espacios colapsados.

### Paso 2 · La ficha — 1 crédito

```
GET /v1/agents/{mm_id}
```

Paga 26 columnas de golpe, incluido el bloque `scored`, que **no viene en la
fila de lista aunque cueste lo mismo**. Por eso siempre la ficha y nunca la
lista para un agente concreto.

De aquí se arman también los campos múltiples:

- **correos**: partir `email` por `;` y sumar los de `linkedProfiles[]`;
- **teléfonos**: `phone` más `phone` y `officePhone` de cada
  `linkedProfiles[]`, comparados sin `+1` ni guiones.

### Paso 3 · Verificar la identificación — 0 créditos

Con la ficha ya pagada:

- **`telefono_coincide`**: ¿alguno de nuestros teléfonos está entre los suyos?
- **`cambio_de_brokerage`**: comparar el brokerage nuestro con su `office`,
  normalizados y por las primeras palabras, para que «Realty Concepts Ltd» y
  «realty concepts, ltd. - fresno» no cuenten como cambio.

**Regla de confianza final, y el orden importa:**

- identificado por correo → **alta**. Un teléfono distinto **no** lo
  contradice: Model Match suele tener el de la oficina y nosotros el celular;
- si el correo no resolvió y el teléfono coincide → **alta, confirmada por
  teléfono**;
- si el correo no resolvió y el teléfono **no** coincide → **a revisión**,
  aunque el nombre y el estado calcen. Es justo la señal de que son dos
  personas.

### Paso 4 · Banderas y exclusión — 0 créditos

Usar el endpoint de **conteo**, que no cobra, con el id del agente:

```
POST /v1/agents/count
{"flatFilters": {"id": "<mm_id>"},
 "footprint": {"dimension": "lender",
               "product": {"mix": "loanType", "key": "fha"}},
 "period": "last24Months"}
```

`total` da **1** o **0**: ese es el sí/no. Repetir con `conventional` y `va`.

Para la casa, el mismo patrón con la lista de ids de Everett y
`units: {gte: N}` para el tramo:

```
"footprint": {"lender": [<ids de la casa>], "units": {"gte": 3}}
```

**Dos cosas que hay que respetar o el número miente:**

- **la ventana**: con `last24Months` dan 28 realtors y con `allTime` dan 79.
  Para una exclusión va `allTime`: una operación con la casa hace tres años
  sigue siendo una relación. Citar siempre el número con su ventana;
- **la lista de ids**: está en `modelmatch/everett.py`, comprobada contra
  `instant-search`, junto con `NO_ES_LA_CASA` — hay bancos de la ciudad de
  Everett y una persona apellidada Everette que **no** son la casa.

### Paso 5 · Breakdowns — solo si caben

```
POST /v1/agents/{mm_id}/breakdowns/{lenders|originators|companies|counties}
```

Pedir únicamente si `totalXWorkedWith ≤ (tope − gastado)`. Si no cabe, la
celda dice «no consultado · N filas y quedaban M créditos», que es
información, no un hueco.

---

## 4 · Columna por columna

### A · De la ficha, `GET /v1/agents/{id}` — 1 crédito las 26

| columna del Excel | campo de la API |
|---|---|
| ID Model Match | `id` / `modelMatchId` |
| Brokerage (Model Match, hoy) | `office` |
| Emails en Model Match | `email` partido por `;` + `linkedProfiles[].email` |
| Teléfonos en Model Match | `phone` + `linkedProfiles[].phone` + `.officePhone` |
| Perfiles enlazados | `linkedProfileCount` |
| Ciudad (MM) · Estado (MM) · ZIP (MM) | `city` · `state` · `zip` |
| Licencia (MM) | `licenseNumber` (vacío en ~la mitad) |
| Unidades 12m · Volumen 12m | `units` · `volume` |
| Precio medio | `avgSoldPrice` |
| Compras (u) · Compras ($) | `buyerUnits` · `buyerVolume` |
| Ventas (u) · Ventas ($) | `sellerUnits` · `sellerVolume` |
| Dual (u) | `dualUnits` |
| **Compras FINANCIADAS (u)** | `scored.total_mortgaged_buyer_units` |
| Compras financiadas ($) | `scored.total_mortgaged_buyer_volume` |
| Ventas financiadas (u) | `scored.total_mortgaged_listing_units` |
| % unidades financiadas | `scored.total_percent_units_mortgaged` |
| % volumen financiado | `scored.total_percent_volume_mortgaged` |
| Loan medio de sus compradores | `scored.average_mortgaged_loan_amount` |
| Nº lenders | `totalLendersWorkedWith` |
| Nº originadores | `totalOriginatorsWorkedWith` |
| Nº compañías | `totalCompaniesWorkedWith` |

### B · De consultas aparte — 8 columnas

| columna | de dónde | costo |
|---|---|---|
| ¿Produce FHA? · ¿convencional? · ¿VA? | `agents/count` + `footprint.product` | **0** |
| ¿Ya financia con la casa? | `agents/count` + `footprint.lender` | **0** |
| Operaciones con la casa (al menos) | el mismo, con `units {gte:N}` por tramos | **0** |
| Su loan officer principal | `breakdowns/originators` | 1 por fila |
| Lenders (si cupo) | `breakdowns/lenders` | 1 por fila |
| Originadores (si cupo) | `breakdowns/originators` | 1 por fila |

### C · Calculadas — 13 columnas, 0 créditos

| columna | cómo |
|---|---|
| ¿En Model Match? | si el paso 1 resolvió |
| Cómo se identificó | el criterio del paso 1 |
| Confianza | la regla del paso 3 |
| ⚠ Revisar porque… | el motivo concreto, vacío si no hay |
| ¿Teléfono coincide? | nuestros teléfonos ∩ los suyos, sin `+1` ni guiones |
| Candidatos vistos | cuántos ids distintos devolvió la búsqueda |
| ¿Cambió de casa? | brokerage nuestro vs `office`, normalizados |
| Nº emails · Nº teléfonos | el largo de cada lista |
| ¿Fidelizado con un LO? | tramos de `totalOriginatorsWorkedWith` |
| % por su LO principal | unidades del LO top ÷ **suma de los suyos** |
| Créditos gastados | el acumulado real del realtor |
| Consultado | sello de tiempo UTC |

---

## 5 · Las trampas. Ninguna es opcional

**1 · Ningún porcentaje de esta API significa lo que parece hasta comprobarlo.**
Van tres comprobadas:

- `footprint.product.shareOfUnits` con `dimension: lender` mide la proporción
  **dentro de un bucket de lender**, no la del agente. Un agente con 20 % de
  FHA real aparece en la banda «≥50 %». Costó 503 créditos descubrirlo;
- `pctUnits` del breakdown de originadores llegó a **167 %**: su denominador
  no son las operaciones del agente. La concentración se calcula a mano, como
  unidades del LO sobre la **suma de los LOs de ese agente**;
- en cambio `footprint` con un **lender explícito** y `units {gte:N}` sí
  significa «N operaciones con ese lender».

**Antes de usar cualquier porcentaje, contrastarlo con un caso cuya respuesta
se conozca por otra vía.** Los scripts de `modelmatch/` lo hacen solos y
avisan si deja de cuadrar.

**2 · La ventana cambia la respuesta**, a veces por un factor de tres. Todo
número se cita con su ventana.

**3 · Un negativo puede ser que la pregunta no podía verlo.** «La pestaña
Transactions no se puede reconstruir» estuvo mal semanas: se habían probado
`/v1/sales` con filtros y `/v1/related`, pero no las rutas colgadas del
agente, que sí existen. Cuando algo no aparezca por varias vías, sospechar de
las vías.

**4 · Los nombres de lenders vienen crudos**, con varias grafías de la misma
empresa y alguna con el nombre mal escrito. No agrupar por texto sin revisar.

**5 · PostgREST corta en ~1000 filas y no avisa.** Paginar siempre.

**6 · El crudo se guarda antes de mirarlo.** Es lo que permite volver a leer
sin re-pagar. 812 respuestas de la corrida de referencia siguen en
`data/raw/`, y de ahí salieron después columnas que nadie había pedido.

---

## 6 · Reanudación y verificación

**Reanudable o no sirve.** Cada realtor se guarda apenas termina, en su propio
archivo. Volver a correr **no re-paga** lo hecho: es la única protección real
contra un corte a mitad de un lote largo.

Al terminar, comprobar las cuatro:

1. **gasto previsto == gasto del ledger**. Si no, el modelo de costo cambió;
2. **ningún realtor por encima del tope**;
3. **ningún match inventado**: los no resueltos están marcados, con sus
   candidatos;
4. **cuadran dos caminos al mismo hecho**: por ejemplo, los realtors con la
   casa según `footprint` deben coincidir con los que tienen a la casa en su
   tabla cruda de lenders, en los que se haya comprado esa tabla.

### Resultado de referencia

Un lote de 298 realtors dio: 273 identificados (189 por correo, 51 por nombre
confirmado con teléfono), 50 a revisión manual, **445 créditos**, media 1,49
por realtor, y el ledger confirmó el modelo al crédito.

---

## 7 · Lo prohibido

- **`enrichProperty` / `enrichPropertiesBatch` / `enrichPropertiesBulk`.** Es
  skip-trace del dueño de la propiedad: nombre, teléfono y correo de un
  consumidor, para un prestamista. 10 créditos por match. El cliente revienta
  antes de salir a la red si la ruta lo menciona.
- **Paginar sin pedirlo.** Seguir el cursor multiplica el costo en silencio.
- **Los filtros de tract de `/v1/market`** —`minorityTractPct`,
  `majorityMinorityTract`, `lowModIncomeTract`— para **elegir** a quién
  contactar. Segmentar por el porcentaje de minoría del tract es redlining y
  es exposición de fair lending. Sirven para medir nuestra cobertura, nunca
  para elegir.
- **Nombres de realtors en el código o en los docstrings**, ni como ejemplo:
  este repo es público. El agente de prueba se busca en `data/`, que está
  fuera de git.
