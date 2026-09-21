# Bloque 4 · Census, HMDA y features relativas

**Fecha:** 2026-09-21 · **Estado:** códigos verificados y **cuatro bugs
preexistentes corregidos**. HMDA probado contra el API real, una llamada.

---

## El hallazgo principal: la capa Census no estaba bien hecha

El brief decía «`latino_re_engine/` completo — la capa Census está bien hecha».
El verificador que escribí para validar **mis** códigos nuevos encontró que
**cuatro de los grupos que ya existían estaban mal mapeados.**

No eran errores de estilo. Cada uno producía columnas con datos de otra cosa, y
todos eran silenciosos: el API de Census devuelve el número que le pidas, y si
le pediste la variable de al lado te la da sin quejarse.

### 1 · `C24030` industria · **las 14 columnas estaban mal, y 5 decían `_f` con datos masculinos**

El comentario del archivo decía «female is +17 offset». El desplazamiento real
es **+27**: el bloque masculino arranca en `_002E` y el femenino en `_029E`. La
tabla tiene **55** variables.

| nombre | código viejo | lo que era en realidad |
|---|---|---|
| `industry_construction_m` | `_004E` | Male: **Agriculture** |
| `industry_manufacturing_m` | `_005E` | Male: **Mining** |
| `industry_transportation_m` | `_008E` | Male: **Wholesale trade** |
| `industry_finance_re_m` | `_011E` | Male: **Transportation+warehousing** |
| `industry_professional_m` | `_012E` | Male: **Utilities** |
| `industry_healthcare_edu_m` | `_013E` | Male: **Information** |
| `industry_hospitality_m` | `_014E` | Male: **Finance+insurance+RE** |
| `industry_construction_f` | `_021E` | **Male**: Educational+health |
| `industry_manufacturing_f` | `_022E` | **Male**: Educational services |
| `industry_transportation_f` | `_025E` | **Male**: Arts+entertainment |
| `industry_finance_re_f` | `_028E` | **Male**: Public administration |
| `industry_professional_f` | `_029E` | Female: **el total** |
| `industry_healthcare_edu_f` | `_030E` | Female: Agriculture (grupo) |
| `industry_hospitality_f` | `_031E` | Female: Agriculture (detalle) |

`economic.py` suma cada par `_m` + `_f` para armar los `industry_*_pct`, así
que **todas** las columnas de industria del dataset estaban mal, y cuatro de
ellas sumaban dato masculino dos veces.

### 2 · `B12001` estado civil · sumaba casados con divorciados

El comentario afirmaba «B12001 has exactly 13 rows (_001E–_013E)» y describía
una estructura que no existe. La tabla tiene **19** variables, y los bloques
masculino y femenino no son simétricos porque «Now married» se subdivide en
spouse present / spouse absent / separated / other.

`female_married` apuntaba a `_010E`, que es **«Male: Divorced»**.

`demographic.py` hace `male_married + female_married` para `married_pct`. Es
decir que estaba sumando **hombres casados con hombres divorciados**, y de ahí
salía también `family_formation_index`.

### 3 · `B16002` idioma · **doble conteo de los hogares LEP**

`_003E` se llamaba `spanish_speak_english_well`, pero es el **total** de hogares
hispanohablantes, no el segmento que habla bien inglés.

`language.py` hacía:

```python
spanish_households = spanish_well + spanish_not_well   # = _003E + _004E
```

que es **total + LEP**, contando dos veces a los hogares LEP. Consecuencias:

| columna | estado |
|---|---|
| `spanish_home_pct` | **inflada** por la cuota LEP |
| `bilingual_spanish_pct` | era el **total** hispanohablante, no el segmento bilingüe |
| `spanish_marketing_opportunity` | mal, porque se compone de las dos anteriores |
| `lep_spanish_pct` | la única correcta |

Esas cuatro columnas están en el dataset como `census_*` y en el dashboard.

Corregido: `spanish_households` usa el total publicado (`_003E`),
`spanish_speak_english_well` pasa a `_005E` («Not a limited English speaking
household») y se agregó `spanish_parts_mismatch`, un control que marca si las
partes no suman el total — porque si no cuadran es un problema de vintage y hay
que verlo, no promediarlo.

### 4 · `B07003` movilidad · todo corrido

El comentario describía un bloque masculino seguido de uno femenino. La
estructura real es al revés: **categoría de movilidad primero, y dentro de cada
una total / male / female.** La tabla tiene 18 variables.

`same_house_1yr_m` apuntaba a `_003E`, que es «Total: Female» — la población
femenina entera, no las mujeres que no se mudaron. `migration.py` suma cada par
`_m` + `_f`, así que **todas las tasas de movilidad del dataset estaban mal**.

### Lo que esto significa

Las cuatro son la misma clase de error que `ig_is_private` constante en 5.620
filas: **un dato que se calculaba, se reportaba y estaba mal, sin que nada
fallara.** Por eso el verificador ahora es código del repo y no un script
suelto:

```bash
python -m src.config.verificar_variables          # desde latino_re_engine/latino_re_engine/
```

Compara los 150 códigos contra el catálogo del API — 28.299 variables para ACS5
2023 — y además marca los casos donde **el nombre interno no se parece a la
etiqueta del API**, que es justo donde se esconde el copiar-pegar de la fila de
al lado. Esa heurística es la que cazó los cuatro bugs. Sale con 1 si algo
falta, así que sirve en CI.

> **Advertencia:** los datos ya generados con el mapeo viejo están mal. Las
> columnas `census_*` de cualquier CSV producido antes del 2026-09-21 no son
> confiables para industria, estado civil, idioma ni movilidad. **Hay que
> regenerar la capa geográfica**, y eso no se pudo hacer acá: no hay `pandas` ni
> `requests` en esta máquina.

---

## Las cinco tablas nuevas

Todos los códigos verificados contra el API de Census, ACS5 2023, uno por uno.

| Tabla | Variables | Se toman | Alimenta |
|---|---|---|---|
| **B25003I** Tenure (Hispanic or Latino Householder) | 3 | 3 | los arrendatarios latinos son los compradores futuros |
| **B11017** Multigenerational Households | 3 | 3 | **P-Q07**, el argumento de ingreso de hogar combinado |
| **B24080** Sex by Class of Worker | 21 | 7 | **P-Q01** y **P-Q20** |
| **B25106** Tenure by Housing Costs as % of Income | 46 | 17 | **P-Q06**, la cuota que enfría al cliente |
| **B03002** Hispanic or Latino Origin by Race | 21 | 4 | complementa B03003 |

Dos decisiones que importan:

**B24080** — el campo que vale es *«Self-employed in own **NOT** incorporated
business»* (`_010E` hombres, `_020E` mujeres). La distinción entre incorporated
y not incorporated no es un detalle contable: el no incorporado declara en
Schedule C y es justamente el expediente que un lender por defecto rechaza de
entrada. Se guardan los dos para poder contrastarlos.

**B25106** — se toman las celdas «30 percent or more», que es el umbral estándar
de HUD para carga de costo, en los cinco tramos de ingreso de propietarios y los
cinco de arrendatarios, **más los totales de los dos tramos de ingreso bajo**,
que son el denominador del comprador de entrada. Sin esos denominadores el
porcentaje no se puede reportar.

**B03002** se usa para el denominador y para detectar zonas donde `B03003` y
`B03002_012E` no cuadran, que suele indicar un problema de vintage. **No se usa
para clasificar a nadie ni para segmentar campañas** — la guarda es
`verificar_uso_de_tract()` en [`pacs/guardas.py`](../pacs/guardas.py).

---

## HMDA · [`hmda/cliente.py`](../hmda/cliente.py)

El fallout %, el score medio, el LTV y el ingreso por condado salen del registro
público de HMDA. **Es literalmente lo que Model Match vende como Market
Signals**, y Model Match caduca mientras HMDA no.

Endpoint: `https://ffiec.cfpb.gov/v2/data-browser-api/view/aggregations`.
Público, gratuito, sin ToS hostil.

### La trampa del denominador, que es todo el asunto

`action_taken` tiene ocho valores y **uno de ellos no es una solicitud**:

| código | significado |
|---|---|
| 1 | Loan originated |
| 2 | Application approved but not accepted |
| 3 | Application denied |
| 4 | Application withdrawn by applicant |
| 5 | File closed for incompleteness |
| **6** | **Purchased loan — NO es una solicitud** |
| 7 | Preapproval request denied |
| 8 | Preapproval request approved but not accepted |

El 6 es un préstamo comprado en el mercado secundario: la solicitud la tomó otra
institución y ya está contada en su propio registro. Meterlo en el denominador
infla el total y baja el fallout.

**Medido el 2026-09-21**, Harris County TX (48201), 2023, sin filtro de universo:

```
originadas (1)                 55.607
aprobadas no aceptadas (2)      3.456
negadas (3)                    24.652
retiradas (4)                  18.692
cerradas por incompletas (5)    5.895
compradas (6)                  17.266   <-- excluidas, 13,7% del archivo
preaprob. negadas (7)             119
preaprob. no aceptadas (8)        176

fallout = 52.990 / 108.597 = 48,8%
```

Incluir las compradas bajaría el fallout más de 6 puntos. Hay una prueba que
cuantifica ese error, no solo lo evita.

### Ese 48,8% NO es comparable con el ~22% de Model Match

La diferencia casi seguro es el universo: **Model Match filtra.** El filtro
estándar del oficio es compra de vivienda, 1-4 unidades site-built, una unidad,
primer lien.

Por eso `Fallout` lleva su filtro adentro y `__str__` lo imprime:

```
48201 (condado) 2023 · fallout 48.8% (52990/108597) · 17266 compradas
excluidas · universo: SIN FILTRO DE UNIVERSO
```

**Un fallout sin su universo declarado no se puede citar a un realtor.**

Descubrir cuál filtro usa Model Match es el paso 3 del
[Bloque 5](bloque-5-modelmatch.md), y
[`modelmatch/calibracion.py`](../modelmatch/calibracion.py) lo hace por
ingeniería inversa: prueba cuatro universos de HMDA contra el número capturado y
dice cuál se parece más.

### Límite de tasa

El endpoint está detrás de Akamai y devuelve **403 «Access Denied»** ante
ráfagas. Comprobado: la segunda llamada consecutiva ya vino bloqueada. **No es
un problema de permisos** — el cliente tiene `PAUSA_MINIMA = 2.5 s`, backoff de
15/60/180 s y caché en disco, y el mensaje de error lo aclara para que nadie
pierda una tarde pensando que le falta una credencial.

---

## FFIEC · LMI del tract · [`hmda/ffiec.py`](../hmda/ffiec.py)

LMI (Low-and-Moderate Income) es la clasificación regulatoria de un tract según
su ingreso mediano relativo al del área metropolitana: **LMI = ratio < 80%**.

Es la señal que usan CRA y muchos DPA estatales para definir elegibilidad, así
que alimenta **P-Q07** directamente. Y **ya es relativa al área**, que es
exactamente lo que el bloque pide.

`NivelDeIngreso.es_lmi` devuelve **`None` para desconocido**. Desconocido no es
«no es LMI».

**No lo descarga automáticamente.** El FFIEC lo publica detrás de un formulario
y el enlace cambia de año a año; adivinar la URL produce un 404 silencioso o,
peor, el archivo del año equivocado. Se baja a mano una vez desde
<https://www.ffiec.gov/censusapp.htm> y se guarda en `hmda/cache/`. Si no está,
falla con esas instrucciones.

---

## Crosswalk HUD · [`geo/crosswalk.py`](../geo/crosswalk.py)

Las fuentes hablan geografías distintas: Census usa ZCTA y tract, HMDA usa
condado y tract, FFIEC usa tract, nuestro lote usa ZIP y estado. **Un ZIP no es
un ZCTA y tampoco es un tract.**

El crosswalk del HUD reparte con cuatro pesos, y **cuál se usa importa**:

| peso | qué reparte |
|---|---|
| **`RES_RATIO`** | direcciones **residenciales** ← el que se usa |
| `BUS_RATIO` | comerciales |
| `OTH_RATIO` | otras |
| `TOT_RATIO` | todas |

Para cualquier cosa de vivienda va `RES_RATIO`. Usar `TOT_RATIO` mete oficinas y
depósitos en el reparto, y en un ZIP con un parque industrial eso corre el peso
hacia tracts donde no vive nadie. Es un error silencioso: el resultado es
plausible y está mal.

Dos detalles:

- los pesos se **normalizan a 1**, porque el crosswalk del HUD a veces no suma
  exacto por redondeo y un reparto que suma 0,98 sesga el agregado hacia abajo;
- `valor_por_zip()` devuelve `(valor, cobertura)`, y la cobertura dice qué
  fracción del ZIP tenía dato **con su denominador**. Un valor calculado sobre
  el 30% de un ZIP no es el valor del ZIP.

Necesita `HUD_API_TOKEN` (gratuito, con registro) o el Excel bajado a mano.

---

## FIPS · [`geo/fips.py`](../geo/fips.py)

Los códigos FIPS **no se escriben a mano**. Se leen del archivo de referencia
oficial de Census, que el módulo descarga y cachea:
`national_county2020.txt`, **3.229 condados**, verificado.

La razón es la alucinación nº 2 de la skill: «listas de entidades escritas a
mano». Los estados punitivos y santuario estaban hardcodeados, incluyendo cinco
que ni aparecían en el lote, y coincidían con el ILRC real **por suerte y no por
método**.

Un FIPS escrito a mano es peor, porque nadie lo revisa: `48201` y `48021` son
los dos válidos y uno es Harris, Texas y el otro Bastrop, Texas.

`resolver()` **no hace fuzzy matching**, a propósito: un FIPS aproximado es un
FIPS equivocado, y un benchmark de condado atribuido al condado de al lado es
peor que no tener benchmark. Cuando no encuentra, sugiere parecidos **del mismo
estado** y falla. Verificado: `Harris/TX → 48201`, `Bexar/TX → 48029`,
`Hidalgo/TX → 48215`, y se niega a devolver `Cook/TX` aunque exista
`Cooke County`.

---

## Features relativas · [`features/relativas.py`](../latino_re_engine/latino_re_engine/src/features/relativas.py)

El cambio de tratamiento que pide el bloque. El modelo anterior **excluía** las
métricas de Census «para evitar que memorizara estados». Excluir resuelve la
memorización tirando la señal.

Ahora se **normaliza contra el condado**:

| tipo de métrica | operación | por qué |
|---|---|---|
| nivel (`median_home_value`, ingreso, renta) | **cociente** contra la mediana del condado | pone California y Texas en la misma escala |
| proporción (`hispanic_pct`, `homeownership_rate`, …) | **diferencia en puntos** | un cociente de proporciones pierde la escala: 40/20 y 60/30 dan los dos 2,0 |

**Por qué el condado y no el estado:** el estado es demasiado grueso. La mediana
de California está dominada por la bahía y Los Ángeles; un agente en Bakersfield
comparado contra la mediana estatal parece barato en un estado caro, cuando en
su propio condado puede estar en el tramo alto. El condado es la unidad en la
que un agente compite.

Tres guardas:

- con menos de **4 ZCTAs** en el condado la feature queda en **NaN, no en 1.0**.
  Un ratio de 1,0 significa «igual a su condado», que es una afirmación; la
  ausencia de dato no lo es;
- mediana 0 o nula → el cociente no existe, y no se rellena;
- `reporte_de_cobertura()` dice cuántas filas tienen feature y cuántas no, con
  el motivo. Va a la salida, no a un log.

`clasificar_tramo_de_entrada()` etiqueta entrada / medio / caro **para su
condado** con cortes en 0,80 y 1,25. Son una **regla propia**, no vienen de
ningún archivo, y están escritas en el código para que alguien pueda
discutirlas. La evidencia que sostienen es **E3: techo de intensidad 1 y nunca
más.** Un ratio de asequibilidad no verbaliza nada, sugiere.

---

## Qué quedó sin resolver

1. **Hay que regenerar la capa geográfica.** Los datos producidos con el mapeo
   viejo están mal en industria, estado civil, idioma y movilidad. No se pudo
   regenerar acá: no hay `pandas` ni `requests` instalados, y el pipeline los
   necesita. **Es lo primero que hay que correr cuando haya entorno.**

2. **No pude medir el impacto numérico de las correcciones.** Sé que las
   columnas estaban mal y por qué; cuánto cambia cada `census_*` después de
   corregir requiere correr el pipeline contra el API. Lo único que puedo decir
   con certeza es la dirección en un caso: `spanish_home_pct` estaba
   **inflado**, porque sumaba los LEP dos veces.

3. **El universo de HMDA que usa Model Match es desconocido.** El 403 de Akamai
   cortó la prueba después de una llamada. Los cuatro universos candidatos
   están codificados en `calibracion.py` y la comparación corre sola cuando
   haya una captura de condado.

4. **FFIEC y el crosswalk del HUD no se descargaron.** Los dos necesitan una
   acción humana: bajar el flat file del FFIEC a mano (el enlace cambia por año)
   y registrarse para el `HUD_API_TOKEN`. Los dos módulos fallan con
   instrucciones en vez de devolver una tabla vacía. **Las posiciones de campo
   del flat file del FFIEC están escritas según el diccionario estándar pero no
   se verificaron contra un archivo real**, así que la primera carga puede
   necesitar ajustar las constantes `CAMPO_*`; `cargar()` avisa si más del 5% de
   las filas salen mal formadas.

5. **`features/relativas.py` no está enchufado al pipeline.** Existe y es
   correcto, pero `features/engine.py` no lo llama todavía, y necesita una
   columna `county_fips` que hoy no se calcula — sale del crosswalk del punto 4.
   Es una cadena de dependencias: crosswalk → `county_fips` → features
   relativas.

6. **Nada de esto se probó a nivel tract.** Todas las mediciones son de
   condado. El API de HMDA acepta `tracts`, y las cinco tablas nuevas de Census
   deberían existir a nivel tract, pero **no lo verifiqué** — y el catálogo de
   variables no declara disponibilidad por nivel, así que hace falta una
   consulta real.
