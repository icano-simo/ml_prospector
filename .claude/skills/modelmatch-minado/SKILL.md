---
name: modelmatch-minado
description: Manual operativo del minado de Model Match para realtors de HOMESÍ — las 62 columnas aprobadas (43 de la API y 19 calculadas), el payload exacto de cada llamada, la transformación de cada campo, los vocabularios exactos que el scoring filtra por igualdad, el tope de 1 crédito por lead y la lista de llamadas prohibidas. Cárgala ANTES de extraer, re-extraer o ampliar datos de Model Match para cualquier lote de realtors, y antes de modificar cualquier cosa en `modelmatch/`. Es prescriptiva: si una llamada no está acá, no se hace.
---

# Minado de Model Match — manual operativo

**Regla cero: si una llamada no está en este manual, no se hace.** Cada
llamada cuesta dinero y cada campo de más es un campo que alguien va a leer
mal.

**Lo aprobado son 62 columnas**: **43 salen de la API** y **19 se calculan** a
partir de ellas sin gastar nada. Están listadas una por una en la sección 4, y
con su número de posición en 4·I — esa tabla **la regenera
`modelmatch/actualizar_tabla_manual.py` desde el código**, para que no pueda
desfasarse. Las demás columnas del archivo son de nuestra base y de Instagram,
y no se le piden a nadie.

**Tope: 1 crédito por realtor.** No dos. Con los breakdowns retirados, la
única llamada que cobra es la ficha y cuesta exactamente 1: **un techo que
nadie puede alcanzar no es un techo, es permiso.** Todo lo demás —Everett con
sus dos ventanas, los programas, la producción por año— sale de `count`, que
**no cobra**.

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

Las tres cabeceras de toda llamada:

```
x-api-key: <MODELMATCH_API_KEY>
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
TOPE_POR_REALTOR = 1
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
| 2 · ficha | **1** | 35 |
| 3 · verificar | 0 | — |
| 4 · banderas y exclusión | 0 | 4 |
| 4 bis · Everett con número, programas y producción por año | 0 | 4 |
| — | | + 19 calculadas a partir de las anteriores |

**La ficha es la única línea con un número distinto de cero, y ese número es
1.** No hay un paso 5: los breakdowns se retiraron.

### Las cuatro guardas, obligatorias

1. **Antes de gastar, comprobar que el realtor no tiene ya ficha comprada.**
   Con el tope en 1 y una sola llamada que cobra, la forma de pasarse es
   comprar dos veces la misma ficha, no comprar algo caro. El registro del
   realtor ya dice `creditos_gastados`: si es ≥ 1, **no se compra nada más**,
   y si hace falta re-leer la ficha se lee del crudo en `data/raw/`, que ya
   está pagado.
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

Una llamada por correo, **máximo 2**. Si ninguna **resuelve**, **una más** con
el nombre completo. No más de 3 en total.

**«Resuelve» significa: alguno de nuestros correos aparece en el campo `email`
de algún candidato** — es decir, se llegó al caso 1 o al 2. Nada más cuenta
como resolver: que un candidato comparta nombre y estado **no** resuelve,
porque eso todavía puede ser un homónimo.

**La búsqueda por nombre se hace siempre que el correo no resolvió**, y los
casos 3 a 7 se evalúan **sobre todos los candidatos de todas las búsquedas
juntas**, sin repetidos por `id`. Si no se hiciera, dos agentes con el mismo
realtor llegarían a listas de candidatos distintas.

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
`scored`. **Paga 35 columnas de una sola vez.**

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

#### Quién es Everett, y los nueve ids

**«La casa» es Everett Financial, Inc. (NMLS 2129), que opera como Supreme
Lending, y nadie más.** En el código la constante se llama `CASA` por
herencia; **en las columnas, en los informes y en este manual se escribe
Everett**, porque «la casa» no se entiende fuera de aquí.

La pregunta de si trabajó con Everett **no se hace acá**: es la llamada base
de las bandas del paso 4 bis, que la hace una vez por ventana y sigue
preguntando el número. Esta sección fija **con qué ids se pregunta**; el paso
4 bis fija **cómo**.

**Los nueve ids de Everett, fijados acá** (comprobados contra `instant-search`
el 2026-09-25). Son los mismos que usan el paso 4 bis y cualquier otra llamada
que nombre a Everett: **la lista es una sola, no se recorta por llamada.**

El código la tiene **duplicada en dos sitios**, y los dos deben decir esto
mismo: `CASA` en `modelmatch/everett.py`, y `CONFIRMADOS + DUDOSOS` en
`modelmatch/auditar_casa.py` —que es de donde la lee `everett_bandas.py`—.
`verificar_manual.py` comprueba que los tres coincidan. Si alguno difiere,
**manda este manual** hasta que alguien decida:

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

El número de operaciones **no** se pide acá: sale de las bandas del paso 4
bis, que son excluyentes y dan el número en vez de un «al menos N».

### Paso 4 bis · Everett con número, programas y producción por año — 0 créditos

Todo esto es `POST /v1/agents/count`, así que **no cobra**, y reemplaza a las
columnas que antes salían de llamadas por fila.

#### El orden, y por qué importa aunque sea gratis

Gratis no es instantáneo: el cliente espera entre llamadas, y un realtor
completo son **del orden de 40 conteos**. El orden fijo es:

| | qué | script | llamadas por realtor |
|---|---|---|---|
| 1 | tipo de préstamo (paso 4) | `modelmatch/paso4.py` | 3 |
| 2 | Everett, dos ventanas con bandas | `modelmatch/everett_bandas.py` | 2 a 16 |
| 3 | producción por año | `modelmatch/anios_buyside.py` | 1 a 13 por periodo |

**Van en ese orden y no en otro por una razón concreta: el 2 aborta el lote
entero si la cota superior dejó de recortar**, y conviene que aborte antes de
gastar horas en el 3, que es el largo —en la corrida de referencia, 471
realtors tardaron unas 20 horas y 15.500 llamadas.

**Los tres son independientes y reanudables**: cada uno escribe en el registro
del realtor apenas termina con él y se salta a los que ya lo tienen. Volver a
correr cualquiera de los tres no rompe nada y no cuesta nada.

#### Everett, en dos ventanas y con el número

El `footprint` con lender explícito acepta **las dos cotas en la misma
llamada**, así que la banda se pide de una:

```json
{"flatFilters": {"id": "<mm_id>"},
 "footprint": {"lender": [<la lista CASA entera>], "units": {"gte": 3, "lt": 5}},
 "period": "allTime"}
```

**`<la lista CASA entera>` son los nueve ids del paso 4**, los mismos y todos,
sin recortar y sin agregar ninguno de la lista de parecidos. El espejo
ejecutable es `CASA` en `modelmatch/everett_bandas.py`, que la arma como
`CONFIRMADOS + DUDOSOS` desde `modelmatch/auditar_casa.py`.

##### La comprobación que va ANTES del lote

✅ **La cota superior recorta de verdad.** Comprobado contra un realtor con 3
operaciones conocidas por su tabla cruda: la banda `[3,4)` devuelve 1 y la
`[4,5)` devuelve 0. Si `lt` se ignorara, **todas** las bandas darían positivo
y el número sería siempre el de la primera.

**Esto no es una nota histórica: es un paso obligatorio.** Antes de cada lote
se vuelve a medir contra un realtor cuyo número se conoce por su tabla cruda
de lenders, y **si no da `[n, n+1) → 1` y `[n+1, n+2) → 0`, el lote no se
corre.** El script lo hace solo y aborta; un agente que repita el
procedimiento a mano tiene que hacerlo igual.

##### Las bandas, exactas

Siete llamadas por ventana, **en este orden y con estos cortes**:

| `gte` | `lt` | lo que se escribe en la celda |
|---|---|---|
| 1 | 2 | `1` |
| 2 | 3 | `2` |
| 3 | 5 | `3-4` |
| 5 | 10 | `5-9` |
| 10 | 20 | `10-19` |
| 20 | 50 | `20-49` |
| 50 | — | `50` |

Un guion en la columna `lt` significa **que esa llamada va sin `lt`**, no que
lleve un `lt` vacío: el `units` queda en `{"gte": 50}` y nada más.

Finas abajo, gruesas arriba: la diferencia entre 2 y 3 operaciones decide, la
de 60 a 70 no.

**Antes de las siete va una llamada más, la base**: `units: {"gte": 1}` sin
`lt`. Si devuelve 0, el realtor no trabajó con Everett en esa ventana, la
celda del número queda **vacía** —no `0`— y **las siete bandas no se piden**.
Son 8 llamadas por ventana en el peor caso, 1 en el mejor, y las 16 juntas
siguen costando 0.

##### Qué hacer si ninguna banda devuelve 1, o si devuelve 1 más de una

- **Son excluyentes por construcción** —`[1,2)`, `[2,3)`, `[3,5)`…— así que
  dos positivas serían una contradicción de la API, no una ambigüedad del
  método. **Se recorren en el orden de la tabla y se toma la primera que dé
  1**, y no se sigue preguntando.
- **Si la base dio ≥1 y ninguna de las siete da 1**, se escribe `50+`. Es el
  caso de alguien por encima del último corte sin cota superior, que no
  debería existir —la última banda no tiene `lt`— y por eso vale como señal de
  que algo se movió en la API.
- **Si una llamada no devuelve un `total` numérico** (error, respuesta rara),
  cuenta como «no es esta banda» y se sigue con la siguiente. No se reintenta
  dentro del lote.

##### Las dos ventanas

Todo lo anterior se hace **dos veces**: con `period: "allTime"` y con
`period: "last12Months"`. Una relación de hace cuatro años no es la misma cosa
que una viva, y la diferencia entre las dos columnas es el hallazgo: de 136
con relación histórica, 21 la tienen en 12 meses.

Las cuatro celdas que salen de acá, con su nombre exacto:

| ventana | sí/no | número |
|---|---|---|
| `allTime` | `¿Trabajó con Everett · histórico?` | `Operaciones con Everett · histórico` |
| `last12Months` | `¿Trabajó con Everett · 12 meses?` | `Operaciones con Everett · 12 meses` |

El sí/no lleva `SÍ` (con tilde y en mayúsculas) o `no`; el número lleva lo de
la tabla de bandas, o vacío.

#### Programas — ya están en el paso 4

Las tres llamadas de FHA, convencional y VA **son las del paso 4 y no se
repiten acá**. Están ahí porque son banderas, no números, y porque su límite
—que solo el sí/no es válido— se explica junto al payload.

Si hiciera falta el **número** de operaciones por programa, el rodeo bien
definido es nombrar el lender: `{"lender": [...], "product": {...}}` sí mide
sobre el agente («N operaciones FHA financiadas por Everett»). **No está
aprobado como columna**, así que hoy no se pide.

#### Historical units — producción por año

**Cuenta `buyerUnits`, NO las unidades totales.** Es el lado comprador y nada
más: un realtor que vende mucho y compra poco sale bajo acá, y está bien que
salga bajo, porque lo que se origina es la compra. No confundir con
`Unidades 12m (MM)`, que son las dos puntas.

El filtro va en `flatFilters` —no en el `footprint`— y acepta las dos cotas:

```json
{"flatFilters": {"id": "<mm_id>", "buyerUnits": {"gte": 3, "lt": 4}},
 "period": "2024"}
```

##### Cómo sale el número exacto

Igual que las bandas de Everett, y por la misma razón: el conteo responde
sí/no, así que se acorrala. Por **cada periodo**:

1. **La base**: `buyerUnits: {"gte": 1}` sin `lt`. Si devuelve 0, ese periodo
   queda **vacío** —no `0`— y **no se piden las bandas**.
2. Si dio 1, se recorren **doce bandas en este orden**, y se toma la primera
   que devuelva 1:

| `gte` | `lt` | celda | | `gte` | `lt` | celda |
|---|---|---|---|---|---|---|
| 1 | 2 | `1` | | 7 | 10 | `7-9` |
| 2 | 3 | `2` | | 10 | 15 | `10-14` |
| 3 | 4 | `3` | | 15 | 20 | `15-19` |
| 4 | 5 | `4` | | 20 | 30 | `20-29` |
| 5 | 7 | `5-6` | | 30 | 50 | `30-49` |
| | | | | 50 | 100 | `50-99` |
| | | | | 100 | — | `100+` |

Si la base dio ≥1 y ninguna de las doce da 1, se escribe `100+`. Las mismas
tres reglas de las bandas de Everett valen aquí: excluyentes, primera que da
1, y una respuesta sin `total` numérico cuenta como «no es esta banda».

##### Qué periodos se piden

**Los años completos desde 2017 hasta el anterior al año en curso**, más
`yearToDate` y `last3Months`. El rango se calcula solo —`range(2017, año en
curso)`— así que no hay que tocar nada en enero.

- **2017 es el más viejo que acepta el enum.** No es que nadie produjera
  antes: es que no se puede preguntar.
- **«Año en curso» es el año del reloj de la máquina en UTC**, el mismo con el
  que se sella `Consultado`.

⛔ **El año en curso NO se pide como año literal.** Está medido: para un
agente con más de cinco operaciones en `yearToDate`, `period: "2026"` devuelve
**0**. El bucket del año corriente no está poblado, y pedirlo así hace creer
que el realtor dejó de producir. **Para el año en curso va `yearToDate`.**

⛔ **No hay trimestres calendario.** El `period` de agentes no los tiene;
`last3Months` es un trimestre **móvil**. Los trimestres de verdad solo salen
de `agentAnalyticsTimeSeries`, que devuelve filas y **cuesta**.

##### Dónde aterriza cada periodo

**Los tres tipos de periodo van a la MISMA celda**, `Historical units · por
año`, uno por segmento, en el formato `<periodo>: <número>`, unidos con
`" · "` y ordenados alfabéticamente —que deja los años primero, después
`last3Months` y al final `yearToDate`—. Los periodos vacíos **no se escriben**:
la celda solo nombra los que tuvieron producción.

```
2019: 3 · 2020: 5-6 · 2021: 10-14 · 2024: 2 · last3Months: 1 · yearToDate: 4
```

**No hay columna propia para `yearToDate` ni para `last3Months`.** Si alguien
los busca aparte, están ahí dentro y en ningún otro lugar.

#### Derivados, sin una sola llamada más

Los tres salen de la misma celda, y **los tres ignoran `yearToDate` y
`last3Months`**: solo miran las claves que son un año de cuatro dígitos. Si no
fuera así, `last3Months` contaría como un año más y la antigüedad saldría
inflada.

- **`Primer año con producción`** = el año más viejo con unidades.
- **`Años con producción`** = en cuántos años distintos cerró al menos una.
  **No es un rango**: alguien que produjo en 2017 y en 2025 y nada en medio
  lleva `2`, no `9`.
- **`Antigüedad aproximada (años)`** = año en curso − primer año + 1. Vacía si
  no hay primer año.
- ⚠ **Si el primer año es 2017, la antigüedad está topada**: 2017 es el año
  más viejo del enum, así que su primera operación puede ser anterior y no hay
  forma de saberlo desde aquí. Esa fila lleva su propio aviso.

### Paso 5 · RETIRADO — los breakdowns ya no se compran

**Ninguna llamada por fila entra en el minado estándar.** Los breakdowns de
`originators`, `lenders`, `companies` y `counties` **no se piden**, quepan o
no en el tope.

Por qué se retiraron, en orden de peso:

1. **La única pregunta que de verdad usábamos de ellos —la relación con
   Everett— sale gratis y mejor** por conteo (paso 4 bis): en vez de un sí/no
   histórico, da el número de operaciones en dos ventanas.
2. **Cuestan 1 crédito por fila y no se pueden acotar.** Está medido: se mandó
   `pagination: {size: 1}` con `sort` por unidades y **la API no lo rechazó,
   lo ignoró** — devolvió 3 filas y cobró 3. No hay forma de comprar solo la
   primera. **No reintentar.**
3. **Con el tope de 1 no cabían nunca**: la mediana es 10 lenders y 10 LOs por
   realtor, así que en la mayoría la celda decía «no consultado» y no aportaba
   nada.

**Lo que se perdió, dicho sin adornos:** el **nombre** del loan officer
principal y el de los lenders. El conteo responde sobre un lender que uno
nombre; **no descubre nombres**. Si algún día hace falta ese nombre para una
lista corta de realtors prioritarios, se compra a propósito y fuera del
minado estándar, sabiendo que cuesta 1 por fila.

> Si se reactivaran, dos cosas medidas que hay que respetar: el orden que
> devuelve la API es **por volumen, no por unidades** —en un caso real el
> primero por volumen tenía 2 operaciones y el segundo 4— y `companies` no
> aporta ninguna columna.

---

## 4 · Campo por campo

Para cada columna: de qué llamada sale, qué campo de la API es, y qué
transformación se le aplica. **El nombre de la columna es, carácter a
carácter, el de la segunda columna de cada tabla** — no se renombra, no se
traduce, no se le quitan acentos ni el `⚠`.

### A · De la ficha `GET /v1/agents/{id}` — 35 columnas, 1 crédito

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
| `scored.LastTransactionDate` | `Última operación` | epoch en milisegundos → fecha ISO. **Es la única señal de recencia** |
| `licenses[]` | `Licencias (todas)` | `"<número> (<estado>, vence <fecha>)"` unidos con `" · "` |
| `licenses[].state` | `Estados con licencia` | los estados distintos, ordenados, unidos con `" · "` |
| `licenses[].expirationDate` | `Licencia vence` | **el vencimiento más próximo** |
| `dualVolume` | `Dual ($)` | tal cual |
| `scored.total_mortgaged_listing_volume` | `Ventas financiadas ($)` | tal cual |
| `scored.total_mortgaged_dual_units` | `Dual financiadas (u)` | tal cual. Suele ser 0 |
| `scored.total_mortgaged_dual_volume` | `Dual financiadas ($)` | tal cual. Suele ser 0 |
| `scored.total_list_price` | `Suma de precios de listado` | tal cual |

### B · De los conteos — 8 columnas, 0 créditos

| llamada | columna | valor |
|---|---|---|
| count + `product.key: fha` | `¿Produce FHA?` | `total == 1` → `"sí"`, si no `"no"` |
| count + `product.key: conventional` | `¿Produce convencional?` | ídem |
| count + `product.key: va` | `¿Produce VA?` | ídem |
| count + `footprint.lender`, `allTime` | `¿Trabajó con Everett · histórico?` | `total == 1` → `"SÍ"`, si no `"no"` |
| el mismo con `units {gte, lt}` por bandas | `Operaciones con Everett · histórico` | la banda que dio 1 |
| count + `footprint.lender`, `last12Months` | `¿Trabajó con Everett · 12 meses?` | ídem |
| el mismo con bandas | `Operaciones con Everett · 12 meses` | ídem |
| count + `buyerUnits` por año | `Historical units · por año` | los años con producción |

### C · De los conteos por bandas

| columna | cómo |
|---|---|
| `¿Trabajó con Everett · histórico?` | `SÍ` si el conteo con `allTime` da 1 |
| `Operaciones con Everett · histórico` | la banda que dio 1: exacto hasta `2`, luego `3-4`, `5-9`, `10-19`, `20-49`, `50`. La tabla completa está en el paso 4 bis |
| `¿Trabajó con Everett · 12 meses?` | lo mismo con `period: last12Months` |
| `Operaciones con Everett · 12 meses` | ídem |
| `Historical units · por año` | `"<año>: <unidades>"` de los años con producción, unidos con `" · "` |

### D · Calculadas — 19 columnas, 0 créditos

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
| `Precio medio de sus COMPRAS` | `buyerVolume ÷ buyerUnits`. **Distinto de `Precio medio`**, que mezcla los dos lados: éste es el precio de las casas que compran sus clientes |
| `Precio medio de sus compras financiadas` | `scored.total_mortgaged_buyer_volume ÷ scored.total_mortgaged_buyer_units`. **Es un PRECIO de casa, no un préstamo** — ver el aviso de abajo |
| `Precio medio de sus listings` | `sellerVolume ÷ sellerUnits` |
| `Venta vs listado (%)` | `total_sale_price ÷ total_list_price × 100`, un decimal. Bajo 100 vende con descuento sobre lo que pide |
| `Primer año con producción` | el año más viejo con unidades |
| `Años con producción` | en cuántos años distintos cerró algo |
| `Antigüedad aproximada (años)` | año en curso − primer año + 1 |
| `Créditos gastados` | el acumulado real del realtor. Entero |
| `Consultado` | ISO 8601 con zona UTC, p. ej. `2026-09-24T20:59:16.308783+00:00` |

> **Los cuatro cocientes —tres precios medios y `Venta vs listado (%)`— son
> aritmética, no datos nuevos.** Se comprobó número a número contra el bloque
> `scored`: el cociente coincide. Por eso se calculan en vez de guardarse dos
> veces.
>
> ⚠ **`Precio medio de sus compras financiadas` y
> `Loan medio de sus compradores` NO son la misma cosa, y se parecen lo
> bastante para confundirse.** El primero es el **precio de la casa** y se
> calcula; el segundo es el **monto del préstamo**, viene de la ficha
> (`scored.average_mortgaged_loan_amount`) y **no es un cociente de nada que
> tengamos**. En la ficha de referencia valen 241.974 y 231.284: la diferencia
> es el pie que puso el comprador, y es justo el dato que se pierde si se
> toman por intercambiables.
>
> **Dos campos de la ficha se leen sin tener columna propia**:
> `scored.total_sale_price` —solo alimenta el numerador de
> `Venta vs listado (%)`— y `licenses[]`, que alimenta las tres columnas de
> licencia. Que no tengan columna no los hace opcionales: sin ellos esas
> celdas quedan vacías.

> ⚠ **Discrepancia conocida con otra skill, sobre `Nº emails` y
> `Nº teléfonos`.** La skill de lectura las describe como «conteos solo de
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

**`¿Fidelizado con un LO?`** — los seis textos, copiables tal cual:

```
sin operaciones financiadas atribuidas
CAUTIVO · 1 solo LO
muy concentrado · 2-3 LOs
concentrado · 4-6 LOs
reparte · 7-12 LOs
reparte mucho · 13+ LOs
```

Y a qué tramo de `Nº originadores` corresponde cada uno:

| `Nº originadores` | texto |
|---|---|
| 0 | `sin operaciones financiadas atribuidas` |
| 1 | `CAUTIVO · 1 solo LO` |
| 2 a 3 | `muy concentrado · 2-3 LOs` |
| 4 a 6 | `concentrado · 4-6 LOs` |
| 7 a 12 | `reparte · 7-12 LOs` |
| 13 o más | `reparte mucho · 13+ LOs` |

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

**`¿Trabajó con Everett · histórico?`** y **`· 12 meses?`** → `SÍ` · `no` ·
`sin comprobar`.

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
| las de la ficha | **vacías**, las 35 |
| `Precio medio de sus COMPRAS` · `Precio medio de sus compras financiadas` · `Precio medio de sus listings` · `Venta vs listado (%)` | **vacías**: son cocientes de celdas vacías, y un cociente sin numerador no es `0` |
| `¿Produce FHA?` · `convencional` · `VA` | `sin comprobar` |
| `¿Trabajó con Everett · histórico?` · `· 12 meses?` | `sin comprobar` |
| `Operaciones con Everett · histórico` · `· 12 meses` | **vacías** |
| `Historical units · por año` · `Primer año con producción` · `Años con producción` · `Antigüedad aproximada (años)` | **vacías** |
| `¿Fidelizado con un LO?` | **vacía** |
| `¿Teléfono coincide?` · `¿Cambió de casa?` | `sin_dato` |
| `Nº emails` · `Nº teléfonos` | **vacías** (no se sabe cuántos tiene, no es que tenga cero) |
| `Candidatos vistos` | el número real de candidatos distintos que devolvió la búsqueda, **también cuando no se eligió ninguno** |
| `Créditos gastados` | `0` |
| `Consultado` | el sello de tiempo igual: se consultó, aunque no se resolviera |

### F bis · Celdas sin regla obvia, para identificados

| situación | columna | valor |
|---|---|---|
| `¿Trabajó con Everett · histórico?` = `no` | `Operaciones con Everett · histórico` | **vacía** |
| ídem con la ventana de 12 meses | `Operaciones con Everett · 12 meses` | **vacía** |
| da `SÍ` pero la banda `[2,3)` y las de arriba dan 0 | `Operaciones con Everett · …` | `1` |
| `Nº originadores` = 0 | `¿Fidelizado con un LO?` | `sin operaciones financiadas atribuidas` — **no** `CAUTIVO` |
| no produjo nada en ningún año | `Primer año con producción` · `Antigüedad aproximada (años)` | **vacías** |
| el primer año con producción es 2017 | `Antigüedad aproximada (años)` | se escribe igual, **pero es un piso**: 2017 es el año más viejo del enum y su primera operación puede ser anterior |
| la API devuelve un porcentaje > 100 | el que sea | **se guarda tal cual**, no se recorta |
| la ficha no trae `licenses` o la trae vacía | `Licencia (MM)` · `Licencias (todas)` · `Estados con licencia` · `Licencia vence` | **vacías**. Model Match tiene licencia para ~la mitad: **vacío significa «no lo sabe», no «no tiene licencia»**, y nadie puede descartar a un realtor por esa celda |
| una licencia viene **sin** `expirationDate` | `Licencias (todas)` | se escribe `<número> (<estado>)`, **sin** la coma ni el «vence». No se inventa una fecha ni se escribe «sin fecha» dentro del paréntesis |
| todas sus licencias están **vencidas** | las cuatro | **se escriben igual**, con su fecha pasada. Filtrar por vencimiento es decisión del scoring, no de la extracción: una licencia vencida en el dato puede ser una renovación que Model Match no vio |
| `buyerUnits` = 0, o `sellerUnits` = 0, o `total_list_price` = 0 | el cociente que lo tenga de divisor | **vacía**. Dividir por cero no da `0`: escribir `0` afirmaría que las casas valían cero |
| cualquiera de los dos términos de un cociente no es un número | ese cociente | **vacía**, sin intentar convertir el texto |

### F ter · Los realtors en revisión SÍ se completan

Un realtor con `⚠ Revisar porque…` no vacío **ya pagó su ficha**, así que los
pasos 4 y 4 bis se hacen igual: son conteos y no cuestan nada, así que no hay
nada que ahorrar dejándolo a medias. Sus columnas se llenan como las de
cualquier otro.

Lo que está en revisión es **la identidad**, no el dato: si resulta ser otra
persona, se descarta la fila entera, no se recalcula.

### G · Ordenamientos y desempates

Sin esto, dos corridas producen el mismo dato en distinto orden y el archivo
deja de ser comparable.

| qué | regla |
|---|---|
| correos | minúsculas, sin repetidos, **orden alfabético**, unidos con `" · "` |
| teléfonos | solo dígitos, sin repetidos, **orden alfabético de la cadena**, unidos con `" · "` |
| `Historical units · por año` | por año ascendente, `"<año>: <unidades>"` unidos con `" · "`, **omitiendo los años sin producción** |
| `Licencias (todas)` | por número, `"<número> (<estado>, vence <fecha>)"` unidos con `" · "` |
| `Estados con licencia` | los estados distintos, **orden alfabético** |
| perfiles duplicados con el mismo correo | gana el de mayor `volume`; si empatan, el primero que devolvió la búsqueda |
| qué correos se buscan | los **2 primeros en orden alfabético** de los nuestros |
| `Candidatos vistos` | ids **distintos** sumando todas las búsquedas hechas para ese realtor |

### H · Formato de los números

- Los importes y las unidades van **tal cual los devuelve la API, sin
  redondear ni convertir**. Si devuelve un decimal —pasa con `Precio medio` y
  `Loan medio de sus compradores`— se guarda el decimal. Lo que no se hace
  nunca es inventar precisión ni recortarla.
- `% unidades financiadas`, `% volumen financiado` y `Venta vs listado (%)`:
  **un decimal**.
- Los precios medios calculados y `Antigüedad aproximada (años)`: **enteros**.
  El redondeo es el de Python —`round()`, mitad al par: `2,5 → 2` y
  `3,5 → 4`—. No es un detalle de estilo: es lo que hace que dos corridas del
  mismo dato den el mismo número.
- `Última operación` y `Licencia vence`: **fecha ISO**, `AAAA-MM-DD`, **sin
  hora y sin zona**. Son fechas de calendario tal como las da la API; no se
  convierten a ninguna zona horaria, porque convertirlas podría correrlas un
  día.
- `Consultado` es lo contrario: **instante**, ISO 8601 **con zona y siempre en
  UTC** (`…+00:00`). Nunca hora local de la máquina — un archivo hecho en dos
  máquinas distintas dejaría de ser ordenable.
- **El «año en curso» de `Antigüedad aproximada (años)` es el año de esa misma
  hora UTC**, no el del reloj local. En los últimos días de diciembre las dos
  cosas pueden no coincidir.
- **`Operaciones con Everett · …` mezcla números y texto a propósito**: `1`,
  `2` y `50` son números; `3-4`, `5-9`, `10-19` y `20-49` son texto. En el
  Excel conviven en la misma columna, así que **ordenar esa columna no da un
  orden numérico** y una fórmula que sume sobre ella falla en las bandas. Para
  ordenar por relación con Everett se usa el sí/no, o se parte la banda a
  mano. Lo mismo vale para `Historical units · por año`, que es texto entero.
- **Vacío no es `0`.** Vacío = no se sabe; `0` = se sabe que es cero.
- **Los porcentajes no se recortan a 100.** Si la API devuelve más, se guarda
  tal cual: el recorte, si hace falta, lo hace el scoring.

---

### I · Las columnas, con su número de posición

<!-- TABLA-POSICIONES:inicio -->

#### El plano entero de la hoja *Realtors*

Son **128 columnas** en una sola tabla, en este orden y sin huecos:

| posiciones | qué | de dónde |
|---|---|---|
| 1 a 3 | `Realtor` · `Instagram` · `Clase IG` | nuestra base: no se le piden a nadie |
| 4 a 71 | las aprobadas de Model Match, **intercaladas** con el resto de las nuestras | la tabla de abajo |
| 72 a 128 | Instagram | scraper propio, fuera de este manual |

Las **55 columnas de Instagram no se listan acá y no se listan en ninguna parte a mano**: el generador las descubre de los datos, así que una señal nueva del scraper aparece sola. Listarlas sería prometer que están todas.

#### Las columnas de Model Match, con su número de posición

**Van de la 4 a la 71, pero no son contiguas**: las posiciones 11, 14, 17, 21, 26, 27 son de nuestra base y no se le piden a Model Match.

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
| 42 | `Última operación` | ficha |
| 43 | `Licencias (todas)` | ficha |
| 44 | `Estados con licencia` | ficha |
| 45 | `Licencia vence` | ficha |
| 46 | `Precio medio de sus COMPRAS` | calculada |
| 47 | `Precio medio de sus compras financiadas` | calculada |
| 48 | `Precio medio de sus listings` | calculada |
| 49 | `Suma de precios de listado` | ficha |
| 50 | `Venta vs listado (%)` | calculada |
| 51 | `Ventas financiadas ($)` | ficha |
| 52 | `Dual ($)` | ficha |
| 53 | `Dual financiadas (u)` | ficha |
| 54 | `Dual financiadas ($)` | ficha |
| 55 | `¿Produce FHA?` | aparte |
| 56 | `¿Produce convencional?` | aparte |
| 57 | `¿Produce VA?` | aparte |
| 58 | `¿Trabajó con Everett · histórico?` | aparte |
| 59 | `Operaciones con Everett · histórico` | aparte |
| 60 | `¿Trabajó con Everett · 12 meses?` | aparte |
| 61 | `Operaciones con Everett · 12 meses` | aparte |
| 62 | `Nº lenders` | ficha |
| 63 | `Nº originadores` | ficha |
| 64 | `¿Fidelizado con un LO?` | calculada |
| 65 | `Nº compañías` | ficha |
| 66 | `Historical units · por año` | aparte |
| 67 | `Primer año con producción` | calculada |
| 68 | `Años con producción` | calculada |
| 69 | `Antigüedad aproximada (años)` | calculada |
| 70 | `Créditos gastados` | calculada |
| 71 | `Consultado` | calculada |

<!-- TABLA-POSICIONES:fin -->

---

## 5 · Llamadas prohibidas

Si el código las menciona, el cliente revienta antes de salir a la red.

| | por qué |
|---|---|
| `enrichProperty`, `enrichPropertiesBatch`, `enrichPropertiesBulk` | skip-trace del **dueño de la propiedad**: nombre, teléfono y correo de un consumidor, para un prestamista. **10 créditos por match** |
| cualquier `*BulkDelivery` sin aprobación escrita | 1 crédito por fila, sin tope natural |
| seguir el `cursor` | multiplica el costo en silencio |
| `POST /v1/agents` para un agente concreto | cuesta lo mismo que la ficha y trae menos |
| `/sales`, `/properties`, `/related`, `/v1/market` | no producen ninguna de las 62 columnas aprobadas |
| **cualquier** `POST /v1/agents/{id}/breakdowns/*` — `originators`, `lenders`, `companies`, `counties` | **nunca, sin excepción y sin «si cabe»**: 1 por fila, no se pueden acotar, y con el tope en 1 no cabe ninguno. Ver el paso 5 |
| los filtros de tract de `/v1/market` para **elegir** a quién contactar | `minorityTractPct`, `majorityMinorityTract`, `lowModIncomeTract`: segmentar por ahí es redlining y es exposición de fair lending |

---

## 6 · Antes de dar por buena una corrida

1. **gasto previsto == gasto del ledger**. Si no, el modelo de costo cambió.
2. **ningún realtor por encima de 1 crédito**, y el total == el número de
   identificados. Un realtor en 2 significa que se le compró la ficha dos
   veces.
3. **ningún match inventado**: los no resueltos están marcados y con sus
   candidatos guardados.
4. **la cota superior se comprobó antes del lote**: la banda `[n, n+1)` del
   testigo dio 1 y la `[n+1, n+2)` dio 0. Sin esa comprobación, todas las
   bandas darían positivo y los números de Everett serían todos el primero.
   El script aborta solo; a mano hay que acordarse.
5. **dos caminos al mismo hecho coinciden**: los marcados con Everett por
   `footprint` tienen que aparecer con Everett en su tabla cruda de lenders,
   **en los pocos realtors de la corrida vieja donde esa tabla se pagó**. En
   los nuevos no hay con qué contrastar, y eso no es un fallo: es el precio de
   haber dejado de comprarla.
6. **ningún porcentaje de la API usado sin contrastar** contra un caso cuya
   respuesta se conozca por otra vía.

### Resultado de referencia

⚠ **La corrida de 298 realtors de septiembre de 2026 NO es el resultado
esperado de este procedimiento, y no sirve de patrón de gasto.** Se hizo con
un tope de 5, no de 1, y además siete realtors terminaron entre 6 y 8 porque
una compra dirigida posterior sumó sin volver a mirar el tope. También se
compraron breakdowns que este procedimiento ya no pide.

Lo que sí es comparable de aquella corrida, porque no depende del tope:

| | |
|---|---|
| realtors procesados | 298 |
| identificados | 273 — 189 por correo, 51 confirmados por teléfono |
| con `⚠ Revisar porque…` no vacío | 52 |
| no encontrados | 25 |
| el ledger confirmó el modelo de costo | 422 previstos, 422 reales |

**Bajo este manual, una corrida de 298 cuesta exactamente un crédito por
realtor identificado**, ni uno más: 273 identificados, 273 créditos. No hay
margen ni rango, porque no queda ninguna llamada opcional que cobre. **Si el
ledger dice otra cosa, algo se está pidiendo que no está acá.**

### Dónde va cada cosa

| qué | dónde |
|---|---|
| un registro por realtor, con todo lo extraído | `data/trabajo/mm_por_realtor/<realtor_id>.json` |
| **toda** respuesta cruda, antes de mirarla | `data/raw/mm_<etiqueta>_<sello>.json` |
| los candidatos de los no resueltos | dentro del registro del realtor, clave `candidatos`, con nombre, brokerage, ciudad, estado y correo de cada uno |
| las tablas crudas de lenders y originadores | dentro del registro, claves `mm_lenders` y `mm_originators`, **solo en los realtors de la corrida vieja que sí las pagó**. El minado de hoy no las pide, así que en un realtor nuevo esas claves no existen — y su ausencia no es un fallo |
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
- **Antigüedad en la industria del realtor** — **el campo no existe**, y eso
  no cambió. Lo que sí cambió es que ahora **se deriva**: el rodeo que antes
  estaba anotado como «si algún día se aprueba» se aprobó, se ejecuta en el
  paso 4 bis y produce `Antigüedad aproximada (años)`, la columna 69.
  Qué significa esa diferencia, porque importa al leerla: **no es la fecha en
  que se hizo realtor, es el año más viejo en que se le ve producción**. Es un
  **piso**, y es más exigente que la licencia —obliga a que estuviera
  cerrando, no solo habilitado—, pero a quien estuvo un año sin cerrar nada al
  principio lo cuenta tarde, y a quien empezó antes de 2017 lo topa ahí.
  **Nunca escribirla como «años en la industria» a secas**: con ese nombre se
  lee como un dato de Model Match, y no lo es.
- **Las operaciones una por una con su tipo de préstamo y monto** — la
  pestaña Transactions se sigue pegando a mano.
