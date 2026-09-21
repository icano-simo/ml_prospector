# Bloque 5 · Model Match, en prueba gratuita

**Fecha:** 2026-09-21 · **Estado:** el código está listo; **la captura es trabajo
humano y no se hizo.**

> **Esto es lo primero que tenés que saber:** no tengo acceso a la cuenta de
> Model Match. Nada de lo que sigue se ejecutó contra su interfaz. Lo que hay es
> el protocolo, el esquema de captura, el parser con las cuatro trampas
> codificadas y la lista de condados con sus FIPS. El que se sienta frente a la
> pantalla sos vos.
>
> Lo escribo así porque un documento que dice "capturé los benchmarks" cuando
> nadie los capturó es peor que no tener documento.

---

## Lo que está listo para usar

| Archivo | Qué es |
|---|---|
| [`docs/condados-captura.csv`](condados-captura.csv) | **Los 25 condados, con FIPS.** Generado, no escrito a mano. |
| [`modelmatch/esquema.py`](../modelmatch/esquema.py) | Esquema versionado `mm-captura-v1` + las dos plantillas de texto |
| [`modelmatch/parser.py`](../modelmatch/parser.py) | Parser con las cuatro trampas verificadas |
| [`modelmatch/volcar_dom.js`](../modelmatch/volcar_dom.js) | Snippet de DevTools: DOM → JSON |
| [`modelmatch/lista_de_captura.py`](../modelmatch/lista_de_captura.py) | Regenera la lista si cambia la cobertura |
| [`geo/fips.py`](../geo/fips.py) | Resuelve FIPS contra la referencia oficial de Census |
| [`tests/test_modelmatch.py`](../tests/test_modelmatch.py) | 15 pruebas, las cuatro trampas cubiertas. Pasan. |

Las plantillas se sacan así:

```bash
python -c "from modelmatch.esquema import PLANTILLA_CONDADO; print(PLANTILLA_CONDADO)"
```

---

## El orden, y por qué es ese

La prueba caduca. El orden está armado para que lo que **no** caduca se capture
primero.

### Paso 1 · Verificar el export nativo · primer día

Hay tres botones de export y los tres hay que probarlos:

1. **"Export Profile"**, arriba a la derecha del perfil de un agente.
2. **Export** en la pestaña **Originators**.
3. **Export** en la pestaña **Lenders**.

Documentá, para cada uno: qué formato entrega, qué campos trae, si declara la
ventana de tiempo y si trae el FIPS o solo el nombre del condado.

**Si alguno da CSV completo, todo lo manual de los pasos 2 y 4 sobra.** Por eso
va primero: es la única prueba que puede ahorrar los otros pasos enteros.

Guardá los tres archivos crudos tal como bajan, sin abrirlos en Excel. Excel
reformatea fechas y trunca ceros a la izquierda, y un FIPS de Texas que empieza
en 48 sobrevive pero uno de Alabama que empieza en 01 se convierte en 1.

### Paso 2 · Los benchmarks de mercado por condado · **el activo permanente**

**Esto es lo más valioso del bloque y casi nadie lo haría primero.**

Un perfil individual caduca con la prueba. Un benchmark de condado **no**: no
cambia de semana a semana, sirve para todos los realtors de ese condado y
sobrevive al vencimiento.

En la pestaña **Market Signals**, el control **Set Location** fija la geografía.
En la captura de prueba estaba en **TX**: hay que **bajarlo a condado**. Un
benchmark estatal no sirve — el gradiente entre un condado caro y uno de entrada
es justamente la señal.

Por cada condado se captura:

| Campo | Para qué |
|---|---|
| **fallout %** + su denominador | Convierte el argumento comercial de HOMESI en dato citable |
| **tiempo medio de cierre** | Elimina la promesa sin respaldo que hoy aparece en los borradores de copy |
| mix de tipo de préstamo del mercado | Contexto para leer el mix del agente |
| distribución de score crediticio | P-Q19, reingreso tras evento de crédito |
| tipos de comprador (primerizos, veteranos, self-employed) | P-Q01, P-Q17, P-Q20 |
| generación | R3, audiencia joven |
| tasa media · LTV · canal · tipo de lender | Contexto de mercado |

Esas dos primeras filas resuelven **de una vez** dos deudas declaradas de la
metodología. No es un dato más: es el que cambia el copy de todos los toques.

**Los 25 condados a capturar están en [`docs/condados-captura.csv`](condados-captura.csv),
con FIPS.** Cómo se eligieron está más abajo, en *Cómo se armó la lista*.

Plantilla: `PLANTILLA_CONDADO`. Nombre de archivo: `condado_{FIPS}_{YYYYMMDD}.txt`.

### Paso 3 · Calibrar contra HMDA · **el uso más rentable de la prueba**

Construir el fallout % y la cuota FHA por condado desde **HMDA** (Bloque 4) y
compararlos con lo que muestra Model Match.

**Si coinciden, tenemos el reemplazo gratuito y nacional.** Eso es lo que vale
más que cualquier perfil: usar una fuente de pago que caduca como verdad de
referencia para validar una fuente libre que no caduca.

El comparador vive en [`modelmatch/calibracion.py`](../modelmatch/calibracion.py).
Se corre cuando existan los dos lados:

```bash
python -m modelmatch.calibracion --mm docs/capturas/ --hmda hmda/salida/fallout_por_condado.csv
```

Si **no** coinciden, eso también es un resultado: dice que el fallout de Model
Match se calcula sobre un universo distinto, y hay que preguntarles cuál antes
de citarlo a un realtor.

### Paso 4 · La muestra de calibración de perfiles

40 a 60 agentes, **estratificados por tier del scoring actual**, de estados con
cobertura.

**Objetivo declarado: medir cuántos Tier A resultan fuera del ICP.** Es una
prueba falsable de la tasa de falsos positivos del modelo retirado, y por lo
tanto de cuánto hay que desconfiar de la cola que el equipo está usando hoy.

Por agente:

- los **tres clasificadores de cabecera**: `Producer Tier`, `Side Focus` y
  `Referral Concentration` — este último es **nuestro S6 precomputado**, que es
  la categoría vacía en casi todos los lotes;
- Overview;
- Originators, **con NMLS** (es la llave de cruce);
- Lenders;
- Title Companies;
- geografía por condado;
- **todos** los contactos con su confianza.

Plantilla: `PLANTILLA_PERFIL`. Nombre: `{licencia}_{apellido}_{YYYYMMDD}.txt`.

> **Los contactos: guardá todos, también los de confianza baja.** Model Match
> entrega varios emails y teléfonos con porcentaje de confianza. El de nuestra
> lista puede coincidir con un **secundario**, y ese cruce es a veces la única
> forma de confirmar que estamos hablando de la misma persona. El parser avisa
> si ve contactos bajo 50% y recuerda que no se descartan.

### Paso 5 · Pedir la API antes de que expire

`api.modelmatch.com`, autenticación por `x-api-key`, recursos
`agents` / `originators` / `loans` / `properties`, filtros planos y paginación
por cursor.

Preguntá **alcance y precio mientras la relación comercial está caliente**. El
texto de la consulta está en [`docs/modelmatch-consulta-api.md`](modelmatch-consulta-api.md).
**No lo mandé**: es una comunicación comercial externa.

---

## Orden de preferencia de captura

| | Método | Por qué |
|---|---|---|
| 1 | **Export nativo** | Es el único que no pasa por un intermediario |
| 2 | **`volcar_dom.js`** en la consola | Vuelca el DOM a JSON con pestaña y timestamp |
| 3 | **Texto pegado** en `.txt` con el esquema | Lento pero auditable |
| ✗ | **Imágenes** | **Nunca.** Los números no sobreviven al OCR, y una captura de pantalla no se puede versionar ni comparar |

El snippet es deliberadamente tonto: agarra toda tabla y todo elemento con
números, en vez de apuntar a clases específicas que se rompen con cada deploy
de Model Match. Si queda ruido, el ruido se filtra después. Lo que no se
recupera después es un dato que el selector no agarró.

También vuelca `title`, `aria-label` y `data-tooltip`, porque **el dato que
importa suele estar en el tooltip**: así se descubrió que un mes decía
"Total Volume $1.0M · Mortgaged Volume: $0".

---

## Las cuatro trampas, codificadas

Verificadas en el perfil de prueba. Cada una tiene su prueba en
[`tests/test_modelmatch.py`](../tests/test_modelmatch.py).

### 1 · Dos definiciones de wallet share en el mismo perfil

| Pestaña | Números | Base |
|---|---|---|
| Overview (tarjeta) | 33 / 33 / 33 | **unidades** |
| Originators | 40,6 / 35,3 / 24,0 | **volumen** |

Se capturan **las dos**, etiquetadas. El parser no elige. `WalletShare` en
`pacs/guardas.py` **rechaza** un share sin base declarada.

### 2 · Los números se mueven dentro de la misma sesión

Dos pestañas consecutivas del mismo perfil, mismo rango de 14 meses:

```
7 buy / 21 sell · 15 total · 28 Sold
6 buy / 21 sell · 14 total · 27 Sold
```

Cada captura lleva **timestamp y pestaña de origen**, y el parser **rechaza**
una sección sin `capturado_en`. Los conflictos se reportan, no se promedian: un
conflicto entre dos pestañas es información sobre la fuente.

Nótese además que **ninguna de las dos lecturas cuadra**: `buy + sell ≠ total`
en ambas. `ConteoDeLados.cuadra` lo detecta.

### 3 · "Top 3 Concentration 100%" no significa concentración

En el perfil de prueba el tipo de préstamo se conocía para **3 de 14** unidades
del lado comprador. El tooltip de un mes decía
"Total Volume $1.0M · Mortgaged Volume: $0".

**No hay concentración: hay tres operaciones casadas.** El parser calcula la
tasa de casamiento (`3/14`) y emite el aviso.

Y la guarda de `pacs/guardas.py`: el mix de programa **no activa ni desactiva
ningún qualifier** con menos de 10 operaciones con tipo identificado, o menos
del 50% del lado comprador identificado. Por debajo: `[insuficiente: 3 de 14]`.

### 4 · "Side Focus" y "Buyer vs Listing Side" reportan conteos distintos

Se guardan ambos. El parser avisa que reportan cosas distintas.

---

## Cómo se armó la lista de 25 condados

El brief pedía "los 15-25 condados donde tenemos loan officers con licencia
activa". **Esa lista no sale de un archivo**: las licencias NMLS son por
estado, no por condado. Hubo que cruzar dos fuentes y aplicar una regla.

**Fuentes:** `Loan_Officers_Licencias.xlsx` (hoja `Licencias (largo)`, 175 filas,
37 LOs con licencia) y `census_latinos_estados_counties.xlsx` (hoja `Counties`,
3.234 filas).

**La regla que cambia la lista entera** — de la referencia 09 de la skill: *la
licencia multiestado no es capacidad.* Un LO cuenta como **local** solo si está
licenciado en 5 estados o menos. Un estado cuya única cobertura viene de un LO
multiestado es **COBERTURA NOMINAL**, no "cubierto".

Medido sobre el board:

| | |
|---|---|
| LOs con al menos una licencia | 37 |
| **LOs multiestado (>5 estados)** | **6** — uno con **35 estados**, otro con 19, otro con 12 |
| Estados con ≥1 LO activo | 43 |
| **Estados con cobertura REAL (≥1 local)** | **20** |
| **Estados solo nominales** | **23** |

Los 23 nominales: `AR AZ CA DE IA KY ME MI MN MS ND NH NM OH OK OR RI SC TN UT VT WA WI`.

### Esto tiene una consecuencia directa sobre el Bloque 3

El brief pide extender la cobertura de licencias estatales *"priorizando CA, AZ,
NV e IL"*. Medido:

| Estado | LOs activos | LOs locales | Lectura |
|---|---|---|---|
| **CA** | 2 | **0** | cobertura nominal: no podemos sostener la plaza |
| **AZ** | 1 | **0** | cobertura nominal |
| **NV** | 2 | 1 | delgada, pero real |
| **IL** | 4 | 1 | media con un solo local |
| NM | 2 | **0** | nominal |

**Minar realtors en California y Arizona hoy produce demanda que no podemos
atender**, que es exactamente lo que la referencia 09 llama un pasivo: un
realtor activado y perdido cuesta más que uno nunca contactado.

Y el movimiento más barato aparece del otro lado de la tabla:

| Estado | LOs activos | LOs locales |
|---|---|---|
| **MD** | 19 | 14 |
| **VA** | 18 | 13 |
| **FL** | 18 | 13 |
| **TX** | 12 | 8 |
| DC | 5 | 3 |

**El corredor MD–VA–DC concentra 42 loan officers activos, 30 de ellos
locales.** Si ahí hay capacidad ociosa, minar más realtors en Maryland,
Virginia y el DC metro convierte capacidad ya pagada en pipeline **sin
contratar a nadie** — y sin tramitar una licencia nueva. Esa hipótesis no la
puedo cerrar: hace falta el conteo de MQL por estado, que depende del motor
PACS corriendo sobre un lote enriquecido.

**Recomendación concreta:** antes de extender licencias a CA y AZ, correr la
métrica de tensión (`MQL del estado ÷ LOs activos`) sobre MD, VA, DC y FL. Si
sale bajo 4, hay capacidad ociosa y la extensión a CA/AZ es la segunda
prioridad, no la primera.

### Criterio de orden dentro de los 20 estados con cobertura real

Población latina absoluta del condado, 2024. **No es el único criterio
defendible**, y lo digo porque importa: lo correcto sería ordenar por
concentración de *nuestros realtors prospectados*, pero **no tenemos el condado
de operación de nuestros realtors** — el lote trae estado y nada más. Ese dato
lo da justamente Model Match (pestaña de geografía), así que es circular.

Cuando exista, se reordena. `lista_de_captura.py` acepta otro criterio sin
tocar el resto.

### Dos avisos sobre la lista

- **Connecticut** reemplazó sus ocho condados por nueve regiones de
  planificación en 2022. Ninguna entró al top 25, pero si se amplía la lista,
  `lista_de_captura.py` las marca en la columna `nota` y sus FIPS son nuevos:
  una tabla de referencia vieja no los tiene.
- **PR / San Juan Municipio** entró por población latina (98,2%) con 1 LO local.
  Puerto Rico tiene su propio marco regulatorio hipotecario; antes de capturarlo
  conviene confirmar que Model Match lo cubre con el mismo grano.

---

## Qué quedó sin resolver

1. **Nada se capturó.** No tengo acceso a la cuenta. Los cinco pasos son trabajo
   humano. El código está probado contra capturas sintéticas que reproducen los
   números reales del perfil de prueba, no contra la interfaz.

2. **No sé cuándo vence la prueba.** El brief dice que caduca y que si hay que
   sacrificar algo se sacrifica el Bloque 3, no el 5. No puse fecha porque no la
   tengo. **Ponela arriba de este documento en cuanto la sepas**, porque el
   orden de los pasos 1 a 5 solo tiene sentido contra un reloj concreto.

3. **El mix de programa por agente no existe en Model Match.** Lo declara el
   propio export. Y es justamente el campo que decide el encaje del ICP. Eso
   **solo** lo da MMI. Los dos proveedores son complementarios, no sustitutos:
   si solo se puede pagar uno, la pregunta es qué falta más — el encaje del
   cliente (mix de programa → MMI) o la dependencia del financiamiento
   (buyside → Model Match).

4. **`Borrower Insights` no se toca.** Trae datos demográficos del prestatario.
   Usarlos para seleccionar o priorizar realtors, o para segmentar campañas, es
   terreno de ECOA y fair lending. La señal legítima es transaccional: FHA,
   bandas de precio, geografía, LMI. Esa ya hace todo el trabajo.
   **No lo capturé y no hay campo para eso en el esquema, a propósito.**

5. **La calibración contra HMDA no corrió** porque necesita los dos lados: la
   captura de Model Match (no existe) y la descarga de HMDA (Bloque 4, el
   cliente está escrito pero `requests` no está instalado en esta máquina).

6. **La métrica de tensión por estado no se calculó.** Necesita el conteo de MQL
   por estado, que sale del motor PACS sobre un lote enriquecido. Es lo que
   convertiría la hipótesis del corredor MD–VA–DC en una recomendación cerrada.
