---
name: modelmatch-minado
description: Manual operativo del minado de Model Match para realtors de HOMESÍ — las 47 columnas aprobadas (34 de la API y 13 calculadas), el payload exacto de cada llamada, la transformación de cada campo, los vocabularios exactos que el scoring filtra por igualdad, el tope de 2 créditos por lead y la lista de llamadas prohibidas. Cárgala ANTES de extraer, re-extraer o ampliar datos de Model Match para cualquier lote de realtors, y antes de modificar cualquier cosa en `modelmatch/`. Es prescriptiva: si una llamada no está acá, no se hace.
---

# Minado de Model Match — manual operativo

**Regla cero: si una llamada no está en este manual, no se hace.** Cada
llamada cuesta dinero y cada campo de más es un campo que alguien va a leer
mal.

**Lo aprobado son 47 columnas**: **34 salen de la API** (26 de la ficha, 8 de
consultas aparte) y **13 se calculan** a partir de ellas sin gastar nada.
Están listadas una por una en la sección 4. En el archivo de 113 columnas
ocupan de la 4 a la 56; las demás son de nuestra base y de Instagram, y no se
le piden a nadie.

**Tope: 2 créditos por realtor.**

> ⚠ **Los textos de las columnas de vocabulario cerrado son exactos, y el
> scoring filtra por igualdad.** Poner una coma donde va el separador `·`, o
> quitar un acento, no es un matiz de estilo: deja fuera a 51 realtors. No se
> reescriben, no se traducen, no se abrevian.
>
> Por eso este manual **no escribe en ninguna parte una variante equivocada**,
> ni siquiera como contraejemplo: alguien la copiaría.
>
> `python modelmatch/verificar_manual.py` comprueba que este manual y el
> código digan lo mismo carácter a carácter, y falla nombrando el valor que
> falte. **Correrlo después de tocar cualquiera de los dos.**

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

| orden | criterio | se anota como | ¿se elige candidato? |
|---|---|---|---|
| 1 | alguno de **nuestros correos** está en el campo `email` del candidato (que trae **varios separados por `;`**) | `email_exacto` | sí, ése |
| 2 | el correo coincide en **más de un** candidato (perfiles duplicados) | `email_exacto_varios_perfiles` | sí, **el de mayor `volume`** |
| 3 | `fullName` normalizado idéntico **y** `state` igual al nuestro, y **solo uno** cumple | `nombre_exacto_y_estado` | sí, ése |
| 4 | varios cumplen nombre **y** estado | `nombre_y_estado_varios` | sí, **el de mayor `volume`** |
| 5 | `fullName` idéntico pero **ninguno** en nuestro estado, y hay exactamente uno | `nombre_exacto_sin_estado` | sí, ése |
| 6 | había candidatos y ninguno encaja | `ambiguo` | **no** |
| 7 | la búsqueda no devolvió nada | `sin_candidatos` | **no** |

**Dos grupos, y la diferencia es si se gasta:**

- **Casos 1 a 5 → se compra UNA ficha** (paso 2), la del candidato elegido.
  **Una sola, nunca varias**, aunque haya tres homónimos: el tope es por
  realtor, no por candidato. Los casos 4 y 5 son identificaciones flojas, y
  por eso la ficha sirve para algo más que traer datos — el teléfono que
  devuelve es lo que las confirma o las refuta en el paso 3.
- **Casos 6 y 7 → NO se elige a nadie y NO se gasta ni un crédito.** Se
  guardan los candidatos con su nombre, brokerage, ciudad, estado y correo
  para que una persona decida.

**Desempate del `volume`:** si dos candidatos empatan, gana el que la búsqueda
devolvió primero.

> El valor `ninguna` existe dentro del código como confianza intermedia de los
> casos 6 y 7, pero **nunca llega a la columna `Confianza`**: ahí esos casos
> se escriben `no encontrado`. No usarlo.

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
2. si no, y el teléfono coincide → `alta · confirmada por teléfono`.
3. si no, y el teléfono **no** coincide → `contradicha por el teléfono`,
   aunque el nombre y el estado calcen. Es la señal de que son dos personas.
4. si **no hay teléfono para comparar**, la confianza depende del caso del
   paso 1: **caso 3 → `media`**; **casos 4 y 5 → `baja`**, y además llevan
   `identificado solo por nombre, sin confirmar con correo ni teléfono` en la
   columna de revisión.

**«No hay teléfono para comparar»** es cualquiera de las tres: que nosotros no
tengamos ninguno, que Model Match no devuelva ninguno, o las dos. En los tres
casos `¿Teléfono coincide?` va `sin_dato`.

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

**Los ids de la casa, fijados acá** (comprobados contra `instant-search` el
2026-09-25; el espejo ejecutable está en `modelmatch/everett.py`, lista
`CASA`, y si los dos difieren manda este manual hasta que alguien decida):

El bloque es copiable tal cual: **un id por línea, sin comentarios dentro.**

```
everett_financial
everett_financial_texas
everett_financial_incdba_lending_supreme
dba_everett_financial_financial_supr
dba_everett_financial_lending_spureme
dba_everett_finance_lending_supreme
dba_evertt_financial_lending_supreme
dba_everett_financial_superme
dba_dupreme_everett_financial_lending
```

El séptimo lleva **«Evertt»** mal escrito: el typo es de la fuente, no de este
manual. Copiarlo así.

**Y los que NO son la casa, aunque el nombre se parezca.** Agregarlos
excluiría gente con la que sí se puede trabajar:

```
everett_mutual_savings
bank_cooperative_everett
everette_f_gary
lending_mortgage_supreme
funding_supreme
credit_supreme
lending_supreme_team
lending_mortgage_solutions_supreme
```

Qué es cada uno, por si alguien duda: los dos primeros son bancos de la
**ciudad** de Everett (el segundo es Everett Co-operative Bank, NMLS 443050);
`everette_f_gary` es una **persona** apellidada Everette; y los cinco de
`supreme` son otras empresas, entre ellas Supreme Mortgage Lending Inc.,
NMLS 2371076.
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

**Se pide según LA REGLA ÚNICA de abajo, no según ninguna otra condición.** Si
no cabe, la celda lleva el centinela de la sección 4·C, con su texto exacto.

⛔ **NO se puede pedir solo la primera fila. Medido.** Se mandó
`pagination: {size: 1}` con `sort` por unidades: **no lo rechazó, lo ignoró** —
devolvió 3 filas y cobró 3. **No reintentar.**

⚠ **El orden que devuelve la API es por VOLUMEN, no por unidades.** Para
nosotros manda **unidades**: lo que cuenta es a cuántos clientes les presentó
un prestamista, no cuán caras eran las casas. En un caso real el primero por
volumen tenía 2 operaciones y el segundo 4. **Reordenar por `units` antes de
tomar el principal.**

#### Los tres breakdowns y su prioridad dentro del tope

Hay tres rutas posibles, todas `POST` con cuerpo `{}`:

```
/v1/agents/{mm_id}/breakdowns/originators
/v1/agents/{mm_id}/breakdowns/lenders
/v1/agents/{mm_id}/breakdowns/companies
```

**Con tope 2 y la ficha ya pagada queda 1 crédito, así que cabe como mucho un
breakdown de 1 fila.** El orden de prioridad es fijo y no se negocia:

**LA REGLA, ÚNICA.** Se recorren en este orden fijo —**`originators`, después
`lenders`**— y de cada uno se pide si, y solo si:

```
0 < totalXWorkedWith ≤ (TOPE − gastado hasta ahora)
```

El presupuesto se descuenta a medida que se compra, así que bajo tope 2 (con
la ficha ya pagada queda 1) **se compra como mucho UNO**, y es el de
originadores siempre que quepa. No hay excepciones ni casos «en la práctica»:
se aplica la fórmula.

`originators` va primero porque da `Su loan officer principal`, que es el
nombre contra el que se compite. **`companies` no se pide nunca**: no produce
ninguna de las 47 columnas.

**Qué pasa cuando `totalXWorkedWith` es 0:** no se pide (lo excluye el `> 0`)
y la celda correspondiente queda **vacía**, no lleva centinela. El centinela
dice «no cupo»; aquí no es que no cupo, es que no hay nada que traer.

Si no cabe ninguno, las columnas `Lenders (si cupo en el tope)` y
`Originadores (si cupo)` llevan el centinela, con este formato **exacto**:

```
no consultado · <N> filas y quedaban <K> creditos del tope
```

donde **`N` = el `totalXWorkedWith` de la ficha** (las filas que habría
traído) y **`K` = TOPE − gastado hasta ese momento** (lo que quedaba).
`creditos` va **sin acento** y `del tope` al final: es el texto que ya está en
el archivo y que el scoring reconoce.

---

## 4 · Campo por campo

Para cada columna: de qué llamada sale, qué campo de la API es, y qué
transformación se le aplica. **El nombre de la columna es, carácter a
carácter, el de la segunda columna de cada tabla** — no se renombra, no se
traduce, no se le quitan acentos ni el `⚠`.

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
| `Lenders (si cupo en el tope)` | `"<label> (<units> u)"` unidos con `" · "`. Si **no cupo**, el centinela exacto: `no consultado · <N> filas y quedaban <K> creditos del tope`. Si `Nº lenders` es **0**, la celda va **vacía, sin centinela** |
| `Originadores (si cupo)` | ídem con originadores: centinela si no cupo, **vacía** si `Nº originadores` es 0 |

### D · Calculadas — 13 columnas, 0 créditos

| columna | cómo |
|---|---|
| `¿En Model Match?` | `sí` en los casos 1 a 5 del paso 1; `NO` en los casos 6 y 7 |
| `Cómo se identificó` | el criterio del paso 1, textual |
| `Confianza` | la regla del paso 3 |
| `⚠ Revisar porque…` | uno de los tres textos de 4·E; **vacía** si el match es confiable |
| `¿Teléfono coincide?` | `si` / `no` / `sin_dato` |
| `Candidatos vistos` | cuántos `id` distintos devolvió la búsqueda |
| `¿Cambió de casa?` | `si` / `no` / `sin_dato` |
| `Nº emails` | cuántos correos distintos trae Model Match — el largo de `Emails en Model Match`. Vacía si no se identificó |
| `Nº teléfonos` | ídem con `Teléfonos en Model Match` |
| `¿Fidelizado con un LO?` | tramos de `Nº originadores`. **Los seis textos exactos están en 4·E** |
| `% por su LO principal` | unidades del LO top ÷ **suma de las unidades de todos sus LOs**. ⚠ **NO usar el `pctUnits` de la API**: su denominador no son las operaciones del agente y llega a dar 167 % |
| `Créditos gastados` | el acumulado real del realtor. Entero |
| `Consultado` | ISO 8601 con zona UTC, p. ej. `2026-09-24T20:59:16.308783+00:00` |

> ⚠ **Discrepancia conocida con otra skill, sobre `Nº emails` y
> `Nº teléfonos`.** La de las 113 columnas las describe como «conteos solo de
> Model Match», que puede leerse como «cuántos son nuevos respecto de los
> nuestros». **No es eso**: el código cuenta todos los que trae Model Match,
> coincidan o no con los nuestros. Manda esta definición, que es la que
> produce el archivo. La otra skill hay que corregirla desde los ajustes de
> la cuenta.

### E · Vocabularios cerrados — copiar carácter a carácter

Estas columnas **solo** pueden tomar estos valores. Nada más.

**`Confianza`** — estos seis y ninguno más

```
alta
alta · confirmada por teléfono
contradicha por el teléfono
media
baja
no encontrado
```

**`Cómo se identificó`**

```
email_exacto
email_exacto_varios_perfiles
nombre_exacto_y_estado
nombre_y_estado_varios
nombre_exacto_sin_estado
ambiguo
sin_candidatos
```

**`⚠ Revisar porque…`** — vacío cuando el match es confiable, o uno de:

```
no se encontró en Model Match
identificado solo por nombre y el teléfono NO coincide: puede ser otra persona con el mismo nombre
identificado solo por nombre, sin confirmar con correo ni teléfono
```

**`¿Fidelizado con un LO?`** — según `Nº originadores`

```
sin operaciones financiadas atribuidas   (n = 0)
CAUTIVO · 1 solo LO                      (n = 1)
muy concentrado · 2-3 LOs
concentrado · 4-6 LOs
reparte · 7-12 LOs
reparte mucho · 13+ LOs
```

⚠ **Cero NO es cautivo.** Cero loan officers significa que Model Match no le
atribuye ninguna operación financiada, no que dependa de uno: es lo contrario
de un objetivo de desplazamiento. Seis realtors salían como `CAUTIVO · 1 solo
LO` teniendo n = 0, y eso manda a un comercial a disputarle un LO a alguien
que no tiene ninguno.

**`¿Teléfono coincide?`** y **`¿Cambió de casa?`** → `si` · `no` · `sin_dato`
(en minúscula y sin acento, los tres).

**`¿En Model Match?`** → `sí` · `NO`.

**`¿Produce FHA?`**, **`¿Produce convencional?`**, **`¿Produce VA?`** →
`sí` · `no` · `sin comprobar`.

**`¿Ya financia con la casa?`** → `SÍ` · `no` · `sin comprobar`.

### E bis · La tabla que une los tres textos — **la más importante**

Las tres columnas de identificación se llenan **juntas**. El scoring acepta la
identidad solo si `Confianza` es `alta`, `alta · confirmada por teléfono` o
`media` **y** `⚠ Revisar porque…` está vacía. Poner el texto equivocado en un
caso `media` deja fuera a ese realtor.

Esta tabla cubre **todos** los casos posibles. No hay más.

| caso | `Cómo se identificó` | `Confianza` | `⚠ Revisar porque…` |
|---|---|---|---|
| nuestro correo está en su ficha | `email_exacto` | `alta` | *(vacía)* |
| el correo coincide en varios perfiles | `email_exacto_varios_perfiles` | `alta` | *(vacía)* |
| nombre + estado, y el teléfono coincide | `nombre_exacto_y_estado` | `alta · confirmada por teléfono` | *(vacía)* |
| nombre + estado, sin teléfono para comparar | `nombre_exacto_y_estado` | `media` | *(vacía)* |
| nombre + estado, el teléfono **no** coincide | `nombre_exacto_y_estado` | `contradicha por el teléfono` | `identificado solo por nombre y el teléfono NO coincide: puede ser otra persona con el mismo nombre` |
| varios con nombre + estado, teléfono coincide | `nombre_y_estado_varios` | `alta · confirmada por teléfono` | *(vacía)* |
| varios con nombre + estado, sin teléfono | `nombre_y_estado_varios` | `baja` | `identificado solo por nombre, sin confirmar con correo ni teléfono` |
| varios con nombre + estado, teléfono **no** coincide | `nombre_y_estado_varios` | `contradicha por el teléfono` | `identificado solo por nombre y el teléfono NO coincide: puede ser otra persona con el mismo nombre` |
| nombre exacto sin estado, teléfono coincide | `nombre_exacto_sin_estado` | `alta · confirmada por teléfono` | *(vacía)* |
| nombre exacto sin estado, sin teléfono | `nombre_exacto_sin_estado` | `baja` | `identificado solo por nombre, sin confirmar con correo ni teléfono` |
| nombre exacto sin estado, teléfono **no** coincide | `nombre_exacto_sin_estado` | `contradicha por el teléfono` | `identificado solo por nombre y el teléfono NO coincide: puede ser otra persona con el mismo nombre` |
| hubo candidatos y ninguno convenció | `ambiguo` | `no encontrado` | `no se encontró en Model Match` |
| la búsqueda no devolvió nada | `sin_candidatos` | `no encontrado` | `no se encontró en Model Match` |

**La regla que se lee de la tabla:** un match por **correo** nunca va a
revisión, aunque el teléfono difiera. Model Match suele tener el de la oficina
y nosotros el celular.

### F · Qué escribir cuando el realtor NO se identifica

**Nunca `no`, nunca `0`.** Un `no` en «¿Produce FHA?» para alguien a quien no
encontramos afirma que no produce FHA, y eso es falso: no se comprobó.

| columna | valor |
|---|---|
| `¿En Model Match?` | `NO` |
| `Cómo se identificó` | `ambiguo` o `sin_candidatos`, según el caso |
| `Confianza` | `no encontrado` |
| `⚠ Revisar porque…` | `no se encontró en Model Match` |
| las 26 de la ficha | **vacías** |
| `¿Produce FHA?` · `convencional` · `VA` · `¿Ya financia con la casa?` | `sin comprobar` |
| `Operaciones con la casa (al menos)` | **vacía** |
| `Lenders (si cupo en el tope)` · `Originadores (si cupo)` | `no consultado · ` (con el motivo vacío, porque no hubo conteo) |
| `¿Fidelizado con un LO?` · `Su loan officer principal` · `% por su LO principal` | **vacías** |
| `¿Teléfono coincide?` · `¿Cambió de casa?` | `sin_dato` |
| `Nº emails` · `Nº teléfonos` | **vacías** (no se sabe cuántos tiene, no es que tenga cero) |
| `Candidatos vistos` | el número real de candidatos distintos que devolvió la búsqueda, **también cuando no se eligió ninguno** |
| `Créditos gastados` | `0` |
| `Consultado` | el sello de tiempo igual: se consultó, aunque no se resolviera |

### F bis · Celdas sin regla obvia, para identificados

| situación | columna | valor |
|---|---|---|
| no se pidió el de **originadores** — por no caber, o por ser 0, o porque se compró el de lenders en su lugar | `Su loan officer principal` | **vacía** |
| ídem | `% por su LO principal` | **vacía** |
| `Nº originadores` = 0 | `Originadores (si cupo)` | **vacía**, sin centinela |
| `Nº lenders` = 0 | `Lenders (si cupo en el tope)` | **vacía**, sin centinela |
| `¿Ya financia con la casa?` = `no` | `Operaciones con la casa (al menos)` | **vacía** |
| la casa da `SÍ` pero el tramo N = 2 da 0 | `Operaciones con la casa (al menos)` | `1` |
| `Nº originadores` = 1 y se compró el breakdown | `% por su LO principal` | `100` |
| la API devuelve un porcentaje > 100 | el que sea | **se guarda tal cual**, no se recorta |

### F ter · Los realtors en revisión SÍ se completan

Un realtor con `⚠ Revisar porque…` no vacío **ya pagó su ficha**, así que los
pasos 4 y 5 se hacen igual: los conteos son gratis y el breakdown, si cabe,
cuesta lo mismo. Sus columnas se llenan como las de cualquier otro.

Lo que está en revisión es **la identidad**, no el dato: si resulta ser otra
persona, se descarta la fila entera, no se recalcula.

### G · Ordenamientos y desempates

Sin esto, dos corridas producen el mismo dato en distinto orden y el archivo
deja de ser comparable.

| qué | regla |
|---|---|
| correos | minúsculas, sin repetidos, **orden alfabético**, unidos con `" · "` |
| teléfonos | solo dígitos, sin repetidos, **orden alfabético de la cadena**, unidos con `" · "` |
| `Lenders (si cupo)` / `Originadores (si cupo)` | en el orden que devuelve la API (por volumen), `"<label> (<units> u)"` unidos con `" · "` |
| `Su loan officer principal` | el de **más `units`**; si empatan, el de más `volume`; si vuelven a empatar, el primero que devolvió la API |
| perfiles duplicados con el mismo correo | gana el de mayor `volume`; si empatan, el primero que devolvió la búsqueda |
| qué correos se buscan | los **2 primeros en orden alfabético** de los nuestros |
| `Candidatos vistos` | ids **distintos** sumando todas las búsquedas hechas para ese realtor |

### H · Formato de los números

- Los importes y las unidades van **tal cual los devuelve la API, sin
  redondear ni convertir**. Si devuelve un decimal —pasa con `Precio medio` y
  `Loan medio de sus compradores`— se guarda el decimal. Lo que no se hace
  nunca es inventar precisión ni recortarla.
- `% unidades financiadas` y `% volumen financiado`: **un decimal**.
- `% por su LO principal`: **entero**.
- **Vacío no es `0`.** Vacío = no se sabe; `0` = se sabe que es cero.
- **Los porcentajes no se recortan a 100.** Si la API devuelve más, se guarda
  tal cual: el recorte, si hace falta, lo hace el scoring.

---

### I · Las 47 columnas, con su número de posición

En la hoja *Realtors* del archivo de 113 columnas. **Van de la 4 a la 56, pero
no son contiguas**: las posiciones 11, 14, 17, 21, 26 y 27 son de nuestra base
y no se le piden a Model Match.

| nº | encabezado exacto | origen |
|---|---|---|
| 4 | `¿En Model Match?` | calculada |
| 5 | `Cómo se identificó` | calculada |
| 6 | `Confianza` | calculada |
| 7 | `⚠ Revisar porque…` | calculada |
| 8 | `¿Teléfono coincide?` | calculada |
| 9 | `Candidatos vistos` | calculada |
| 10 | `ID Model Match` | ficha |
| 12 | `Brokerage (Model Match, hoy)` | ficha |
| 13 | `¿Cambió de casa?` | calculada |
| 15 | `Emails en Model Match` | ficha |
| 16 | `Nº emails` | calculada |
| 18 | `Teléfonos en Model Match` | ficha |
| 19 | `Nº teléfonos` | calculada |
| 20 | `Perfiles enlazados` | ficha |
| 22 | `Ciudad (MM)` | ficha |
| 23 | `Estado (MM)` | ficha |
| 24 | `ZIP (MM)` | ficha |
| 25 | `Licencia (MM)` | ficha |
| 28 | `Unidades 12m (MM)` | ficha |
| 29 | `Volumen 12m (MM)` | ficha |
| 30 | `Precio medio` | ficha |
| 31 | `Compras (u)` | ficha |
| 32 | `Compras ($)` | ficha |
| 33 | `Ventas (u)` | ficha |
| 34 | `Ventas ($)` | ficha |
| 35 | `Dual (u)` | ficha |
| 36 | `Compras FINANCIADAS (u)` | ficha |
| 37 | `Compras financiadas ($)` | ficha |
| 38 | `Ventas financiadas (u)` | ficha |
| 39 | `% unidades financiadas` | ficha |
| 40 | `% volumen financiado` | ficha |
| 41 | `Loan medio de sus compradores` | ficha |
| 42 | `¿Produce FHA?` | aparte |
| 43 | `¿Produce convencional?` | aparte |
| 44 | `¿Produce VA?` | aparte |
| 45 | `¿Ya financia con la casa?` | aparte |
| 46 | `Operaciones con la casa (al menos)` | aparte |
| 47 | `Nº lenders` | ficha |
| 48 | `Nº originadores` | ficha |
| 49 | `¿Fidelizado con un LO?` | calculada |
| 50 | `Su loan officer principal` | aparte |
| 51 | `% por su LO principal` | calculada |
| 52 | `Nº compañías` | ficha |
| 53 | `Lenders (si cupo en el tope)` | aparte |
| 54 | `Originadores (si cupo)` | aparte |
| 55 | `Créditos gastados` | calculada |
| 56 | `Consultado` | calculada |

---

## 5 · Llamadas prohibidas

Si el código las menciona, el cliente revienta antes de salir a la red.

| | por qué |
|---|---|
| `enrichProperty`, `enrichPropertiesBatch`, `enrichPropertiesBulk` | skip-trace del **dueño de la propiedad**: nombre, teléfono y correo de un consumidor, para un prestamista. **10 créditos por match** |
| cualquier `*BulkDelivery` sin aprobación escrita | 1 crédito por fila, sin tope natural |
| seguir el `cursor` | multiplica el costo en silencio |
| `POST /v1/agents` para un agente concreto | cuesta lo mismo que la ficha y trae menos |
| `/sales`, `/properties`, `/related`, `/v1/market` | no producen ninguna de las 47 columnas aprobadas |
| el breakdown de `companies` | **nunca**, quepa o no: no produce ninguna de las 47 columnas |
| los breakdowns de `lenders` y `counties` sin que quepan en el tope | 1 por fila |
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

⚠ **La corrida de 298 realtors de septiembre de 2026 NO es el resultado
esperado de este procedimiento, y no sirve de patrón de gasto.** Se hizo con
un tope de 5, no de 2, y además siete realtors terminaron entre 6 y 8 porque
una compra dirigida posterior sumó sin volver a mirar el tope. En ese archivo
`% por su LO principal` tiene valores como 90, imposibles bajo el tope de 2,
donde esa columna solo puede valer `100` o quedar vacía.

Lo que sí es comparable de aquella corrida, porque no depende del tope:

| | |
|---|---|
| realtors procesados | 298 |
| identificados | 273 — 189 por correo, 51 confirmados por teléfono |
| con `⚠ Revisar porque…` no vacío | 52 |
| no encontrados | 25 |
| el ledger confirmó el modelo de costo | 422 previstos, 422 reales |

**Bajo este manual, una corrida de 298 debería costar entre 273 y 300
créditos** (1 por identificado, más los pocos breakdowns de una fila que
quepan). Si da mucho más, algo se está pidiendo que no está acá.

### Dónde va cada cosa

| qué | dónde |
|---|---|
| un registro por realtor, con todo lo extraído | `data/trabajo/mm_por_realtor/<realtor_id>.json` |
| **toda** respuesta cruda, antes de mirarla | `data/raw/mm_<etiqueta>_<sello>.json` |
| los candidatos de los no resueltos | dentro del registro del realtor, clave `candidatos`, con nombre, brokerage, ciudad, estado y correo de cada uno |
| las tablas crudas de lenders y originadores | dentro del registro, claves `mm_lenders` y `mm_originators` |
| la hoja de los que hay que revisar a mano | hoja *Revisar* del Excel, con los candidatos en una celda |
| las tablas largas, una fila por relación | hojas *Lenders* y *Originadores*. La hoja *Companias* existe en el libro pero **queda siempre vacía**: ese breakdown no se pide |

**Nada de esto se versiona**: lleva nombre, correo y teléfono de personas
reales y el repo es público. `data/` está en el `.gitignore`.

### Datos de contacto

Los correos y teléfonos son **de uso interno del equipo**. No se comparten
fuera ni se cargan en herramientas de terceros sin aprobación. Esta
información es comercial, sobre profesionales inmobiliarios, y no se usa para
decidir nada sobre un consumidor ni sobre su crédito.

### Y una advertencia sobre reproducibilidad

Este manual garantiza **el mismo procedimiento y el mismo formato**, no los
mismos valores: Model Match actualiza sus datos y un realtor puede cambiar de
brokerage, cerrar más operaciones o aparecer con otro correo. Dos corridas en
fechas distintas deben dar las mismas **columnas**, con los mismos textos
exactos, y pueden dar distintos **números**.

---

## 7 · Lo que NO sale de Model Match

Para que nadie lo busque ahí:

- **Instagram** — es scraper propio.
- **Idioma, apellido, origen** — no están, y es correcto que no estén. Esas
  señales salen de Instagram y del modelo de scoring.
- **Antigüedad en la industria del realtor** — no existe el campo.
  ⛔ **No se ejecuta en el minado estándar**, porque no produce ninguna de las
  47 columnas y la regla cero manda. Si algún día se aprueba como columna
  nueva, el rodeo medido sería pedir producción en un año viejo
  (`period: "2024"`, `units {gte:1}`), que además es más exigente que la
  licencia porque obliga a que estuviera produciendo.
- **Las operaciones una por una con su tipo de préstamo y monto** — la
  pestaña Transactions se sigue pegando a mano.
