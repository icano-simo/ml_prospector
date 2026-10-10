---
name: instagram-modelmatch-union
description: Manual operativo de la UNIÓN de las dos capas — cómo se pega lo que produce el scraping de Instagram con lo que produce el minado de Model Match en un solo libro de Excel de 130 columnas y 5 hojas, con qué llave se cruzan, por qué Supabase no hace falta para el Excel, en qué orden van las columnas, qué hoja lleva qué y por qué, y las cuatro condiciones que hacen que dos corridas den exactamente el mismo archivo. Cárgala ANTES de generar, leer o modificar `realtors_instagram_model_match.xlsx`, y antes de tocar `modelmatch/a_excel.py`. Presupone las skills `instagram-scraping` y `modelmatch-minado`.
---

# La unión de las dos capas — manual operativo

**Regla cero: la unión no decide nada.** No puntúa, no filtra y no rellena
huecos. Pega dos fuentes por una llave y deja ver de cuál viene cada celda.
Todo lo que parezca una decisión aquí es un defecto.

Este manual presupone las otras dos:

| skill | produce |
|---|---|
| `instagram-scraping` | `realtor_scraper/output/ig_signals.csv` — 50 columnas |
| `modelmatch-minado` | `data/trabajo/mm_por_realtor/<realtor_id>.json` — un registro por realtor |

Y produce:

```
data/salida/realtors_instagram_model_match.xlsx   ← el libro entero
data/salida/realtors_COMPLETOS.xlsx               ← solo las filas sin pendientes
```

---

## 1 · El orden de las operaciones, y por qué es ése

```
 1  construir_lista.py --desde-csv     ig_signals.csv ──► realtors_con_ig.json
 2  extraer.py                         ──► mm_por_realtor/*.json   (1 crédito c/u)
 3  paso4.py                           ──► tipo de préstamo        (0)
 4  everett_bandas.py                  ──► Everett, dos ventanas   (0)
 5  anios_buyside.py                   ──► producción por año      (0)
 6  instagram_lista.py                 Supabase  ──► instagram.json
 7  a_excel.py                         todo lo anterior ──► el libro
```

**El orden no es negociable y cada paso tiene su razón:**

- **1 va primero** porque la lista de a quién minar sale del scraping: solo se
  le compra ficha a quien tiene Instagram.
- **2 antes que 3-5** porque los tres pasos gratis necesitan el `mm_id` que
  trae la ficha.
- **4 antes que 5** porque el 4 **aborta el lote entero** si la cota superior
  dejó de recortar, y conviene que aborte antes de las horas del 5.
- **7 al final**, y **es puramente local**: no hace una sola llamada a ninguna
  API. Se puede correr cien veces sin coste.

⛔ **Nunca dos de los pasos 3, 4 y 5 a la vez.** Los tres actualizan los
**mismos** archivos de `mm_por_realtor/`, con lectura-modificación-escritura
sin bloqueo. El paso 2 sí puede correr en paralelo con ellos, porque **crea**
archivos nuevos para realtors que aún no tienen: son conjuntos disjuntos.

---

## 2 · La llave del cruce

**`realtor_id`**, el identificador de nuestra base.

```python
f.update(ig.get(f.get("realtor_id") or "") or {})
```

Es un `update` sobre el registro de Model Match: **las claves de Instagram
empiezan todas por `ig_`**, así que no pueden pisar ninguna de Model Match. La
separación de prefijos es lo que hace segura esa línea.

### Cómo llega el `realtor_id` a cada lado

| capa | cómo |
|---|---|
| **Model Match** | `construir_lista.py` lo pone en el registro al crearlo |
| **Instagram** | `instagram_lista.py`: de Supabase, **y del CSV local para los que la base todavía no tiene** |

⚠ **El scraper NO conoce el `realtor_id`.** Su CSV se identifica por **correo**
(`email`), y el cruce a `realtor_id` lo hace `construir_lista.py --desde-csv`
contra la tabla `realtors`. **Ese correo es la llave dura de todo el sistema**,
y es la razón de que un realtor sin correo no pueda unirse aunque tenga las
dos capas.

### ⛔ Supabase NO hace falta para el Excel

Esto costó 788 filas vacías antes de verse, así que conviene que quede dicho:

**`instagram_lista.py` leía solo `v_ig_senales_current`**, que tenía 298
perfiles mientras el CSV del scraper tenía 1.098. El resultado eran **788
filas con las 55 columnas de Instagram vacías, con cara de «no tiene
Instagram», mientras el dato estaba en el disco de al lado.**

Ahora lee las dos fuentes, **con la base por delante**: el CSV solo rellena
huecos. Es la misma regla que `construir_lista.py --desde-csv`.

**Y la clase del perfil se CALCULA, no se espera de la base.**
`v_ig_clase_actual` la guarda, pero `ingest/instagram/clase_perfil.py` la
calcula con **funciones puras** a partir de `estado_perfil`, `captions_texto`
y `handle` — las tres columnas del CSV. Para el Excel la base no aporta nada
que no se pueda derivar; **hacía falta para la app, no para esto.**

⚠ **`Clase IG` e `IG · clase` son el MISMO concepto con dos orígenes.** La
primera venía de nuestra base —que solo la tiene para lo ya cargado— y la
segunda del cálculo. Tener una llena y la otra vacía en la misma fila es peor
que no tener ninguna: quien filtre por la equivocada pierde 788 filas sin
enterarse. **La primera se rellena con la segunda cuando la base no la
tiene.**

### Qué pasa cuando una capa falta

| caso | qué sale |
|---|---|
| tiene Instagram y no Model Match | la fila existe, con las 64 columnas de MM **vacías o `sin comprobar`** |
| tiene Model Match y no Instagram | las 55 columnas `IG ·` van **vacías** |
| raspado pero sin cargar a la base | **ya no es un problema**: el CSV local lo cubre |
| no tiene correo | **no se puede cruzar**: sin esa llave no hay unión |

---

## 3 · El libro: cinco hojas

| # | hoja | una fila por | de dónde |
|---|---|---|---|
| 1 | **Realtors** | realtor | la unión: 130 columnas |
| 2 | Revisar | realtor no resuelto | los `ambiguo` con sus candidatos |
| 3 | Diccionario de campos | columna | generado desde el código |
| 4 | Cómo interpretar | idea | cómo se leen juntas |
| 5 | Cómo leer esto | límite | estado del archivo y trampas |

### Las tres hojas que se RETIRARON

Había **Lenders**, **Originadores** y **Companias** con el formato largo de
los breakdowns: una fila por relación. Se quitaron.

**Por qué, y no solo porque ya no crecen:** esos listados cuestan 1 crédito
por fila y dejaron de comprarse, así que solo tenían las filas de la corrida
de septiembre —50 realtors— y *Companias* estaba vacía desde siempre. **Una
hoja con 125 filas en un libro de 1.086 realtors se lee como «estos son sus
lenders», y no lo son: son los de 50 realtors de hace un mes.** Un dato
parcial sin etiqueta de parcialidad es peor que ninguno.

⚠ **Lo ya pagado no se perdió:** sigue en
`data/trabajo/mm_por_realtor/<realtor_id>.json`, en las claves `mm_lenders` y
`mm_originators`. Si algún día hacen falta, se vuelven a volcar sin pagar.

### Por qué existe cada una de las que quedan

- **Realtors** es el producto. Todo lo demás existe para poder leerla.
- **Revisar** existe por una razón concreta: **un match por nombre que nadie
  revisó se ve igual que uno confirmado por correo**, y actuar sobre el
  equivocado es peor que no tener el dato. Todo lo dudoso se concentra ahí —
  pero **también sigue en Realtors**, con su columna de desconfianza. Sacarlo
  de la tabla principal lo escondía: quien busca a alguien y no lo encuentra
  concluye que no lo sacamos.
- **Diccionario** se genera desde `COLUMNAS`, no se escribe. Cubre las 130.
- **Cómo leer esto** abre con el **estado del archivo**, que es lo que dice si
  se puede entregar.

---

## 4 · Las 130 columnas: el plano

| posiciones | qué | color de cabecera |
|---|---|---|
| 1 – 3 | `Realtor` · `Instagram` · `Clase IG` | gris |
| 4 – 73 | las 64 aprobadas de Model Match, **intercaladas** con seis nuestras | azules |
| 74 – 75 | `realtor_id` · `sf_lead_id` | gris |
| 76 – 130 | Instagram, **55 columnas** | morado |

### Los colores, y para qué sirven

| color | origen | cuántas |
|---|---|---|
| azul oscuro | Model Match · la ficha — **la única que cobra** | 35 |
| azul medio | Model Match · conteos, gratis | 8 |
| azul claro | calculado sobre las dos anteriores | 21 |
| **morado** | **Instagram · scraping propio** | 55 |
| gris | nuestra base (MMI / Salesforce) | 11 |

**No es decoración: las columnas de las tres fuentes están intercaladas**, y de
ahí depende **cómo se lee un vacío**. Vacío en azul es «Model Match no lo
trae»; vacío en morado puede ser «la cuenta es privada»; vacío en azul claro es
«le faltan sus insumos».

### El orden de las de Instagram

Las descubre el generador **de los datos**, no de una lista a mano, para que
una señal nueva del scraper no se pierda en silencio. Dentro:

1. las de `DESC_IG`, en el orden en que están ahí;
2. las que aparecieron y no están en `DESC_IG`, **alfabéticas**;
3. **al final, las cuatro largas**: `citas_por_etiqueta`, `captions_texto`,
   `comentarios_texto`, `comentarios_del_agente`.

⚠ **Las largas van al final a propósito:** en medio empujan todo lo demás
fuera de la pantalla y la tabla deja de poder leerse.

⛔ **Y la lista queda CONGELADA en `modelmatch-minado` §4·I.** El generador
las descubre, pero `verificar_manual.py` **falla** si los datos traen una que
no esté congelada o dejan de traer una que sí. Cuando falle, se decide: o se
agrega al manual —y el archivo cambia de versión— o se arregla el scraper. **Lo
que no puede pasar es que el archivo cambie de columnas solo**, porque eso
rompe cualquier scoring que lea por posición.

---

## 5 · Las cuatro condiciones de reproducibilidad

Para que dos corridas den **exactamente** el mismo archivo:

**1 · Un solo origen por dato.** El valor sale del registro del realtor o no
sale. ⛔ **Nunca se rellena desde un archivo lateral de una corrida vieja.**
Esto ya falló: el generador caía a `mix_prestamos.json` cuando faltaba el
paso 4, y como ese archivo se generó una vez, **cualquiera minado después
salía con `fha=no conv=no va=no`** — tres afirmaciones producidas por la
ausencia de un archivo. Fueron 62 realtors.

**2 · Vacío no es `0`, y `no` solo si se preguntó.** Un `no` por falta de dato
se lee igual que un `no` medido. Donde no se midió va `sin comprobar`.

**3 · Todo orden es explícito.** Correos y teléfonos alfabéticos; periodos por
clave; licencias por número; candidatos por volumen con desempate por orden de
aparición. Sin esto, dos corridas producen el mismo dato en distinto orden y
el archivo deja de ser comparable.

**4 · Todo número de la prosa se cuenta, no se escribe.** Los que estaban a
mano ya se desfasaron: la hoja afirmaba «5 créditos por realtor» con el tope
en 1, y los números de Everett eran de una corrida de 471 con tres tandas sin
actualizar.

---

## 6 · Cuándo el archivo se puede entregar

El libro **se dice a sí mismo** si está listo. En la hoja *Cómo leer esto*, el
bloque `Estado de este archivo`, y en la salida del generador:

```
pendientes : 0 de N identificados  OK, se puede entregar
```

### La columna `⚠ Datos pendientes`

Vacía si la fila está completa; si no, qué falta, **en este orden fijo** y
terminando en `NO PUNTUAR`:

```
tipo de préstamo · Everett · producción por año · NO PUNTUAR
```

**El riesgo que cubre es de scoring, no de prolijidad:** un cliente de Everett
cuya llamada se cayó queda en `sin comprobar`, **se salta el tope de ≥3
operaciones con Everett** —que manda a grado D— y saldría con grado A. **El
dato que falta no es neutro: su ausencia favorece al realtor.**

### Mientras el lote corre: el archivo parcial

```
python modelmatch/a_excel.py --solo-completos
```

Escribe `realtors_COMPLETOS.xlsx` **solo con las filas que tienen los TRES
sellos** (`paso4_en`, `everett_bandas_en`, `anios_buyside_en`) y están
identificadas.

⚠ **Exige los tres sellos, no la ausencia de pendientes.** `⚠ Datos
pendientes` **no marca el paso que no se corrió para nadie** —está decidido
así— así que filtrar solo por esa columna dejaba entrar filas sin producción
por año, con sus cuatro columnas vacías, en un archivo llamado COMPLETOS. **El
nombre del archivo es una promesa.**

**Nombre distinto a propósito:** dos archivos con el mismo nombre y distinto
número de filas es como alguien termina puntuando el parcial creyendo que es
el entero.

---

## 7 · Los dos archivos de revisión manual

La unión no inventa: lo que no se pudo resolver sale a un archivo para que una
persona decida.

| archivo | quiénes | se genera con |
|---|---|---|
| `revisar_model_match.xlsx` | los `ambiguo`: la búsqueda dio candidatos y ninguno cumplió la regla | `python modelmatch/para_revisar.py` |
| `revisar_handles_instagram.xlsx` | handles `no_encontrado`, `handle_dudoso` o sin verificar | `python realtor_scraper/handles_para_revisar.py` |

Los dos traen una **columna en amarillo para escribir la respuesta** y aceptan
`NINGUNO` / `NO TIENE`, que también es una respuesta: evita que se vuelva a
preguntar.

⚠ **Ninguno de los dos cuesta créditos ni peticiones**: solo leen lo que ya
está en disco.

---

## 8 · Qué hace falta para repetir esto en otro servidor

### Las tres piezas

| pieza | de dónde |
|---|---|
| el scraper | `python realtor_scraper/empaquetar_scraper.py` → paquete portable con su manual y su verificador |
| el minado | `modelmatch/`, con la llave en `.env` como `MODELMATCH_API_KEY` |
| la unión | `modelmatch/a_excel.py` |

### Lo que NO viaja y hay que sustituir

- **La lista de objetivo.** Sale de un libro de scoring y de Supabase. En otro
  servidor hay que sustituir `cargar_objetivo()` y `construir_lista.py` por lo
  que haya ahí. **Lo único que tienen que devolver** es, por realtor: nombre,
  estado, correos, teléfonos, brokerage y —si existe— handle y licencia.
- **Las credenciales.** Llave de Model Match y cuenta de Instagram.
- **Los datos.** `data/` está en el `.gitignore` entero.

### El orden de arranque en limpio

```
1  pip install -r realtor_scraper/requirements.txt
2  python -m playwright install chromium
3  python -m instagram.finder --iniciar-sesion
4  python -m instagram.finder --piloto 20 --con-ventana
5  python -m instagram.finder --revisar-piloto     ← revisión a mano, obligatoria
6  python -m instagram.finder --lote
7  python -m instagram.finder --parsear
8  python modelmatch/construir_lista.py --desde-csv
9  python modelmatch/extraer.py                    ← lo único que cuesta
10 python modelmatch/paso4.py
11 python modelmatch/everett_bandas.py
12 python modelmatch/anios_buyside.py
13 python modelmatch/a_excel.py
```

### Las tres comprobaciones antes de dar por buena una corrida

```
python modelmatch/verificar_manual.py          # manual de MM contra el código
python realtor_scraper/verificar_manuales_ig.py # manual de IG contra el código
python tests/correr_todo.py                     # la suite entera
```

⛔ **Y el chequeo que decide si se entrega**: `pendientes` en **0**. Está en la
salida del generador y dentro del libro.

---

## 9 · Lo que esta capa NO hace

- **No puntúa ni ordena.** Contesta «quién es esta persona hoy y cuánto
  negocio hipotecario mueve»; **no** contesta «a quién llamo primero».
- **No rellena huecos.** Un vacío se queda vacío y dice por qué.
- **No resuelve ambigüedades.** Las saca a un archivo para que decida una
  persona.
- **No versiona nada de lo que produce.** Todo lleva nombres, correos y
  teléfonos reales, y el repositorio es público.
