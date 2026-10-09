---
name: instagram-scraping
description: Manual operativo completo del scraping de Instagram de realtors — los dos modos de arranque (desde el nombre, buscando el perfil; o desde un handle ya conocido), los insumos exactos, las tres consultas de búsqueda, la regla de verificación del handle, las dos pasadas, las 50 columnas del CSV en su orden de contrato, la salida a Excel, y cómo se reanuda tras un corte. Cárgala ANTES de raspar cualquier lote, antes de tocar `realtor_scraper/`, antes de leer `ig_signals.csv`, y antes de montar cualquier interfaz que lance el scraper. Es prescriptiva y suficiente: un agente que la siga reproduce el proceso entero sin leer el código.
---

# Scraping de Instagram de realtors — manual operativo

**Regla cero: un handle sin verificar no es un handle, es una suposición; y el
crudo se guarda antes de derivarlo, siempre.**

Este manual cubre el proceso entero y es **autosuficiente**: quien lo siga de
principio a fin obtiene el mismo archivo, con las mismas 50 columnas en el
mismo orden.

Para unir esta salida con la de Model Match en un solo libro, ver la skill
`instagram-modelmatch-union`.

---

## 0 · Los dos modos de arranque

| modo | de qué parte | qué fases corre |
|---|---|---|
| **A · desde el nombre** | nombre + apellido + estado (+ licencia si la hay) | **1 · búsqueda** y después 2 y 3 |
| **B · desde el handle** | el handle ya conocido | solo **2 · raspado** y **3 · derivación** |

**No son dos programas: son el mismo, con la fase 1 activada o no.** Si el
insumo ya trae handle, la fase 1 se salta entera y no se gasta ni una
consulta de búsqueda.

```
MODO A   nombre ──► [1 búsqueda] ──► handle verificado ─┐
                                                        ├──► [2 raspado] ──► ig_raw/*.json
MODO B   handle ───────────────────────────────────────-┘           │
                                                                    ▼
                                                        [3 derivación] ──► ig_signals.csv ──► Excel
```

⚠ **Las fases 2 y 3 están separadas a propósito y eso gobierna todo el
diseño.** La 2 cuesta horas y pelea contra bloqueos; la 3 es Python puro sobre
archivos locales y corre en segundos. **Cuando cambia un léxico, una regla o
una columna, se corre solo la 3.** Por eso se guarda el caption crudo y no
solo los flags: los flags cambian cuando cambian las reglas; el texto no.

---

## 1 · Qué hace falta para que corra en otra máquina

### Dependencias

```
patchright>=1.0.0
playwright>=1.44.0
loguru>=0.7.0
openpyxl>=3.1.0
lingua-language-detector
```

`patchright` es un Playwright parcheado para no anunciarse como automatizado.
El código lo intenta primero y cae a `playwright` si no está:

```python
try:
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright
```

Después hay que bajar el navegador:

```
python -m playwright install chromium
```

⚠ **La fase 3 NO necesita navegador.** Es la que se puede correr en cualquier
máquina, y el propio código lo dice cuando falla el import.

### La sesión de Instagram — una sola vez

```
python -m instagram.finder --iniciar-sesion
```

Abre un navegador con ventana, se inicia sesión a mano, y el perfil queda en
disco.

⚠ **El directorio de perfil de Instagram está SEPARADO del general**, y no por
orden:

| | |
|---|---|
| `output/browser_profile` | navegación general |
| `output/browser_profile_instagram` | **solo** la cuenta dedicada |

Dos razones medidas: un bloqueo de Instagram sobre un perfil compartido se
lleva puesta la otra sesión; y si alguien inicia sesión con su cuenta personal
en el perfil general, **el lote entero sale a nombre de esa persona**.

⛔ **Cómo se comprueba que hay sesión: por COOKIE, nunca por DOM.** Antes se
miraba `a[href^='/explore/']` y **daba falso positivo**: ese enlace existe
también sin sesión, así que el lote arrancaba creyendo estar autenticado.
Medido el 2026-09-21: el DOM decía «sesión detectada» y el endpoint JSON
devolvía **401**.

### El navegador, configurado igual siempre

```python
chromium.launch_persistent_context(
    user_data_dir=...,
    headless=headless,
    args=["--disable-blink-features=AutomationControlled",
          "--no-first-run", "--no-default-browser-check", "--disable-infobars"],
    viewport={"width": 1366, "height": 768},
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    locale="en-US",
    timezone_id="America/Chicago",
)
```

**`locale` y `timezone_id` no son decorativos:** una sesión que dice estar en
EEUU y pide páginas con reloj europeo es una incoherencia observable.

⛔ **Un solo proceso a la vez.** Chromium **bloquea** el `user_data_dir`: un
segundo proceso sobre el mismo directorio falla al arrancar o corrompe el
perfil. Y el checkpoint es un *read-modify-write sin bloqueo*, así que dos
lotes en paralelo se pisan el progreso en silencio. Si hace falta
paralelismo, es **una cola con un solo trabajador**, no N procesos.

---

## 2 · Los insumos, modo por modo

### Modo A · desde el nombre

| campo | obligatorio | para qué |
|---|---|---|
| `nombre` + `apellido` | **sí** | sin ellos devuelve `sin nombre de realtor` |
| `estado` | no, pero pesa | entra en las tres consultas y desempata homónimos |
| `licencia` | no | **si está, manda sobre todo lo demás** (ver 3·C) |
| `email` | no | sirve de llave del archivo crudo y para comparar identidad |

### Modo B · desde el handle

Basta el handle. El resto de los campos mejora la verificación pero no la
bloquea.

### De dónde sale la lista en este repo

`cargar_objetivo()` lee el libro de scoring PACS, hoja **`Realtors PACS`**, y
aplica el **filtro literal del brief**: `nivel_de_calificacion = MQL` **o**
`TIER` que empiece por **A** o por **B**.

El libro vive en `Data_inputIA/`, **fuera del control de versiones**. Si falta,
el programa se detiene diciendo dónde lo buscaba.

```
python -m instagram.finder --objetivo
```

imprime la composición de la lista **y no raspa nada**. Correrlo antes de un
lote: el filtro literal tiene consecuencias que conviene ver antes de gastar
diez horas.

### La clave del archivo crudo

Cada perfil se guarda como `ig_raw/<clave>.json`, y la clave sale, **en este
orden**:

1. el **email** en minúsculas;
2. si no hay, el **handle** sin `@`;
3. si no hay, el **nombre** sin acentos, en minúsculas, con `_` por espacios.

Después se sanea a `[a-z0-9._@-]` y se corta a 120 caracteres, porque va a ser
un nombre de archivo en Windows.

**Esa clave es la identidad del perfil en todo el proceso**, y es lo que hace
que reanudar funcione.

---

## 3 · FASE 1 · La búsqueda del handle (solo modo A)

> ⚠ **El fallo que originó este diseño, porque explica cada decisión.** La
> primera versión encontraba handle para el **98,1 %** de los realtors (5.516
> de 5.620). Un 98 % buscando cuentas por nombre no es creíble, y la causa
> estaba en una línea:
>
> ```
> handles = re.findall(r"instagram\.com/([A-Za-z0-9_.]{3,30})", content)
> ```
>
> `content` era el HTML **completo** de la página de resultados, así que el
> primer `instagram.com/...` que apareciera —un anuncio, el pie de página, el
> perfil de otra persona— se devolvía como el handle. **Nunca se comprobó que
> el perfil fuera de esa persona.** Y como no había verificación, un handle
> equivocado **no producía un error**: producía señales de contenido sobre la
> persona equivocada, con el mismo aspecto que las correctas.

### A · Las tres consultas, exactas y en este orden

```
site:instagram.com "<nombre completo>" realtor <estado>
site:instagram.com "<nombre completo>" real estate <estado>
site:instagram.com <nombre completo> realtor <estado>
```

Contra `https://duckduckgo.com/?q=<consulta>&kl=us-en`.

**Las dos primeras llevan el nombre entre comillas y la tercera no.** No es
redundancia: las comillas piden coincidencia exacta; la tercera es la red de
seguridad para los nombres que la fuente escribió distinto de como la persona
los usa.

**Se para en cuanto hay 5 candidatos** (`MAX_CANDIDATOS = 5`), así que la
tercera consulta a menudo no se ejecuta.

### B · De dónde se extraen los handles

⛔ **De los `href` de los enlaces, NUNCA del HTML de la página.**

```python
enlaces = page.query_selector_all("a[href*='instagram.com']")
```

DuckDuckGo **envuelve** sus resultados, así que el destino real va en `uddg=`:

```python
if "uddg=" in href:
    partes = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    href = (partes.get("uddg") or [href])[0]
```

Y el handle se extrae con:

```
instagram\.com/([A-Za-z0-9_.]{2,30})(?:/|\?|$)
```

### C · Las rutas que NO son handles

Instagram usa su dominio para muchas cosas que no son personas. **Esta lista
se descarta siempre**, copiable tal cual:

```
p
reel
reels
explore
accounts
stories
tv
about
privacy
legal
help
tags
directory
developer
api
instagram
web
direct
challenge
emails
session
oauth
graphql
static
images
ajax
your_activity
```

### D · El ritmo de la búsqueda

| | |
|---|---|
| entre consultas | **2.5 a 5.0 s**, aleatorio |
| ante `403` o `429` de DuckDuckGo | **30 a 70 s** y se salta esa consulta |

El rango aleatorio no es cosmético: un ritmo uniforme durante horas es una
firma de automatización.

---

## 4 · La verificación del handle — la parte que no es opcional

Los candidatos **no están verificados**. Esto decide si se usan.

### A · Las dos condiciones

1. **el nombre del perfil se parece al del realtor**, y
2. **la bio o los posts traen señal inmobiliaria**.

### B · La tabla de confianza

| nombre coincide | señal inmobiliaria | confianza |
|---|---|---|
| sí | sí | **alta** |
| sí, pero **por email** | sí | **media** |
| sí | no | **media** |
| no | sí | **baja** |
| no | no | **baja** |

**Coincidir por email da `media` y no `alta`**: son dos señales, pero la de
identidad es indirecta. **`media` sin señal inmobiliaria** significa «puede ser
su cuenta personal»: la persona es la correcta, la cuenta quizá no sea la
profesional.

### C · La excepción que manda sobre todo: la licencia

Si la bio declara un número de licencia que **coincide con el que ya
teníamos**, la confianza es **alta sin mirar el nombre**. La licencia es la
llave de identidad de todo el sistema; un nombre es una cadena. Se compara
**sin ceros a la izquierda**, porque las fuentes los escriben distinto.

### D · Lo que NO se compara

⛔ **No se compara apellido con origen, etnia ni nacionalidad.** Es comparación
de **cadenas** entre el nombre que dio la fuente y el que la persona puso en su
perfil. Eso es verificación de identidad, no inferencia sobre una persona.

### E · La limpieza que hace que la comparación funcione

- se **quitan las palabras de oficio** del nombre de perfil, para que
  `| Realtor®` no rompa la coincidencia;
- se **separan camelCase y dígitos** del handle;
- se **parten tokens pegados** por palabras de ruido de **4 letras o más**.

⚠ **Las de 2 y 3 letras están fuera a propósito, y está medido.** Con `by`,
`mi`, `tu`, `the`, `my` dentro: `mirna → rna`, `byron → ron`,
`michelle → chelle`, `temperance → mperance`, `themis → mis`. **Cinco nombres
reales arruinados para rescatar uno.**

Los conectores de 2-3 letras **solo se recortan de un fragmento que ya vino de
un corte**, nunca de un token entero: si `byclarissa` apareció tras cortar
`sold`, ese `by` es ruido; `byron` nunca se cortó, así que su `by` se respeta.

### F · El orden de evaluación, y por qué ahorra el 80 % de las peticiones

Por cada candidato, **en orden**:

1. se lee el perfil **sin comentarios** — lo mínimo para tener nombre de
   perfil, bio y captions;
2. se extraen las licencias de la bio y se comparan con la nuestra;
3. se verifica y se anota el resultado;
4. **si la confianza es `alta`, se corta ahí**;
5. si no, se espera 2.5-5.0 s y se pasa al siguiente.

Al terminar se toma **el mejor por confianza** (`alta` > `media` > `baja`), no
el primero que apareció.

⛔ **Solo entonces, y solo si la confianza es usable, se paga la lectura
completa** —posts, comentarios y destino del link de la bio—. Hacerlo por cada
candidato multiplicaría por cinco las peticiones, que es lo que provoca un
bloqueo.

### G · Qué pasa con la confianza `baja`

**El handle se guarda igual**, con su confianza y su razón: sigue siendo un
punto de partida para revisión manual.

⛔ **Pero sus señales NO se usan.** *Un handle equivocado no produce un error,
produce señales sobre la persona equivocada.*

---

## 5 · FASE 2 · El raspado

```
python -m instagram.finder --lote
```

### Los topes, con su razón medida

| | valor | por qué |
|---|---|---|
| posts por perfil | **30** (`N_POSTS_CRUDO`) | el brief pide 30-50; más arriba Instagram exige scroll infinito y el costo por dato se dispara |
| posts con comentarios | los más recientes | abrir cada post es una navegación entera |
| comentarios por post | acotado | suficiente para un perfil de audiencia sin convertir esto en un corpus de mensajes de gente que no sabe que los leemos |

**Por DOM, cada post cuesta ~8,5 s.** Es el número con el que se estima:

```
segundos por perfil ≈ (pausa_media) + n_posts × 8,5
```

El propio lote lo imprime al arrancar, con la proyección en horas.

### Las pausas

| | |
|---|---|
| entre posts | 2.0 – 4.5 s |
| entre perfiles | 6.0 – 12.0 s (20-40 s en el lote) |
| tras un scroll | 1.2 – 2.8 s |
| ante bloqueo | backoff exponencial, y después se rinde |

Cada tantos perfiles hay una **pausa larga**. No estaba en el brief: está
porque un ritmo perfectamente uniforme durante diez horas es, en sí mismo, una
firma.

### Lo que detiene el lote

⛔ **Ante un desafío, un captcha o un bloqueo, el lote se DETIENE — no
reintenta.** Es pedido explícito del brief, y la razón es que insistir contra
un bloqueo convierte un problema de una hora en una cuenta quemada.

### Dos trampas del DOM, las dos medidas

⛔ **El enlace de la bio NO es
`header a[href^='http']:not([href*='instagram.com'])`.** Ese selector devolvía
el **badge de Threads** en 3 de 9 perfiles: `threads.com` no contiene
«instagram.com», así que pasaba el filtro. Y peor que un valor falso: un agente
que dice «DM or visit link» probablemente **tiene** enlace.

⚠ **`instagram.com` NO va en la lista de dominios excluidos.** `l.instagram.com`
es el envoltorio legítimo del enlace de bio; excluirlo mata el caso bueno —
comprobado poniéndolo y viendo los 13 destinos irse a `None` de golpe.

⛔ **«Locations» no es un geotag.** El enlace del pie apunta a
`/explore/locations/` y dice «Locations». Salió **106 veces de unos 180
geotags** en el piloto.

---

## 6 · Los diez estados del perfil

**Nunca se devuelve `False` donde corresponde `null`.** Una señal ausente lleva
su motivo, y el motivo importa: **un perfil privado es un dato sobre la
persona; un handle equivocado es un dato sobre nuestro scraper.**

| estado | qué significa | ¿hay contenido? | ¿reintentar? |
|---|---|---|---|
| `publico_leido` | se leyó de verdad | **sí** | no hace falta |
| `privado` | la cuenta es privada | no | **no**: no mejora |
| `muro_de_sesion` | pidió iniciar sesión | no | **sí** |
| `sin_grid` | cargó sin cuadrícula de posts | no | **sí** |
| `degradado` | cargó a medias | no | **sí** |
| `vacio` | existe y no tiene posts | no | **no**: no mejora |
| `no_encontrado` | el handle no existe | no | no, hay que buscar otro |
| `bloqueado` | Instagram cortó | no | sí, más tarde |
| `handle_equivocado` | el perfil no es de esta persona | no | no, hay que buscar otro |
| `sin_handle` | la búsqueda no devolvió candidatos | no | no |

⚠ **El enum pasó de 5 a 10 valores y los nuevos salen tal cual**, sin mapearse
de vuelta: mapearlos escondería exactamente la distinción que existen para
hacer. **`publico_leido` no cambió**, que es el valor sobre el que filtra la
app que consume el archivo.

---

## 7 · FASE 3 · La derivación

```
python -m instagram.finder --parsear
```

Lee `ig_raw/*.json` y escribe `ig_signals.csv`. **No toca la red.**

Un crudo que rompe el parser **no tumba la pasada**: se registra como ilegible
y se sigue. El crudo está en disco, así que re-parsear es gratis.

⚠ **Antes de escribir, comprueba que el CSV no esté abierto en Excel.** Windows
lo bloquea, y el peor momento para descubrirlo es al final de un lote de diez
horas. Si lo está, se detiene diciendo qué hacer y **sin tocar los crudos**.

### Los seis módulos, en orden de dependencia

| módulo | qué resuelve |
|---|---|
| `estado.py` | los diez estados. Nunca `False` donde va `null` |
| `verificacion.py` | ¿el handle es de esta persona? → `handle_confianza` |
| `idioma.py` | idioma por pieza, con umbral de evidencia |
| `posts.py` | caption crudo + fecha, programas, cadencia, engagement |
| `comentarios.py` | audiencia **agregada y anónima** |
| `extraccion.py` | **lo único que toca el DOM** |

Los cinco primeros son **Python puro** y tienen 51 pruebas. Si una corrida
falla, que las pruebas pasen dice que el problema es **el selector y no la
lógica**.

### La detección de idioma

Se usa **`lingua`, restringido a {español, inglés}**. No es intercambiable.

| detector | aciertos sobre 17 captions reales |
|---|---|
| langdetect | 15 / 17 |
| **lingua** | **17 / 17** |

Los dos fallos de langdetect son el caso que importa:

```
"¡Vendida! 🏡🔑 Felicidades"                      -> portugués, confianza 1.00
"Casa abierta este sabado 🏠 #openhouse #austin"  -> portugués, confianza 1.00
```

**Confianza máxima en el idioma equivocado: ningún umbral lo habría
filtrado.** Además langdetect levanta excepción con texto de solo emoji y es no
determinista sin fijar semilla. La ventaja decisiva de lingua es **restringir
el espacio de hipótesis**, que elimina la confusión con portugués e italiano.

Costo: **~1 minuto de CPU** para el lote entero (11.307 detecciones/s).

---

## 8 · La regla de privacidad — no es negociable

**Nunca se perfila individualmente a quien comenta.** Los comentarios entran
como **agregado**: cuántos preguntan por enganche, en qué idioma, si responde
el agente. **Nunca quién preguntó.**

Está **implementado, no prometido**:

- `Comentario.autor_es_el_agente` es un **booleano, no un handle**;
- el handle del comentarista **se descarta en el constructor**;
- las `@menciones` dentro del comentario **se redactan**;
- el texto se guarda **solo si pasa el filtro de anonimato**;
- correos y teléfonos dejados en un comentario **se redactan siempre**.

| quién | qué | ¿se guarda? |
|---|---|---|
| **el agente**, en **sus propios captions** | las `@cuentas` que etiqueta | **sí** — son socios comerciales, es información de negocio |
| **un tercero**, comentando | su handle | **no** — no eligió aparecer en nuestro CRM |

`comentarios_redactados` es el **log de auditoría** de esa redacción.

---

## 9 · Las **50 columnas**, en su orden exacto

⚠ **El orden es contrato con la app que consume el archivo. No se reordenan ni
se renombran.** Las 17 de audiencia van **al final**, para no mover ni un
índice de lo que ya se consume.

### A · Identidad y estado — 6

| # | columna | qué es |
|---|---|---|
| 1 | `email` | la llave con la que se cruza contra nuestra base |
| 2 | `nombre` | el de la fuente, no el del perfil |
| 3 | `estado` | el estado de EEUU |
| 4 | `handle` | el handle verificado |
| 5 | `estado_perfil` | uno de los **diez** valores de §6 |
| 6 | `handle_confianza` | `alta` · `media` · `baja`. **Con `baja`, las señales no se usan** |

### B · Volumen de evidencia — 4

| # | columna |
|---|---|
| 7 | `captions_n` |
| 8 | `captions_es_ratio` |
| 9 | `comentarios_n` |
| 10 | `comentarios_es_ratio` |

⚠ **`captions_n` es el denominador de todo lo demás.** Un `menciona_fha = false`
con `captions_n = 2` no dice que no hable de FHA: dice que se leyeron dos posts.

### C · Programas y temas — 7

| # | columna |
|---|---|
| 11 | `menciona_lender` |
| 12 | `menciona_itin` |
| 13 | `menciona_dpa` |
| 14 | `menciona_credito` |
| 15 | `menciona_va` |
| 16 | `menciona_fha` |
| 17 | `menciona_primera_casa` |

Salen de léxicos **bilingües**. **Hay una prueba que recorre cada entrada de
cada léxico y falla si no tiene al menos un patrón en español y uno en
inglés**: un léxico que solo detecta en español reproduce el sesgo que este
sistema corrige.

### D · Audiencia y co-marketing — 3

| # | columna | qué es |
|---|---|---|
| 18 | `comentarios_pregunta_calificacion` | terceros preguntando por requisitos. **Evidencia directa del dolor del cliente, en sus palabras** |
| 19 | `cuentas_hipotecarias_etiquetadas` | cuentas que **parecen** de hipotecas |
| 20 | `posts_comarketing` | posts en co-marketing |

⚠ **La 19 es una PISTA, no un hecho.** Hay que confirmarla contra NMLS antes de
escribirla en un dossier: **el handle de alguien no prueba su oficio.**

### E · Ritmo y alcance — 4

| # | columna |
|---|---|
| 21 | `tipo_post_reel_pct` |
| 22 | `dias_entre_posts_mediana` |
| 23 | `hueco_max_dias` |
| 24 | `engagement_rate` |

### F · Contexto del perfil — 3

| # | columna |
|---|---|
| 25 | `designaciones` |
| 26 | `destacadas_titulos` |
| 27 | `geotags_top` |

### G · Texto crudo — 5

| # | columna | qué es |
|---|---|---|
| 28 | `captions_texto` | los captions enteros |
| 29 | `comentarios_texto` | de terceros, **redactados** |
| 30 | `comentarios_del_agente` | lo que respondió él |
| 31 | `texto_truncado` | si se cortó por tope de celda |
| 32 | `comentarios_redactados` | **qué se redactó y cuántas veces** |

**Excel aguanta 32.767 caracteres por celda; acá se corta en 30.000 y se
declara.** Un corte silencioso haría que un análisis sobre el texto diera
menos de lo que hay sin que nadie lo notara.

### H · Muestra corta — 1

| # | columna |
|---|---|
| 33 | `paginacion_truncada` |

⛔ **Cuando es `true`, `captions_es_ratio` va VACÍO a propósito** y `captions_n`
dice cuántos sí se leyeron. Significa que se leyó **menos del 60 %** de los
posts esperados sin llegar al final de la paginación. Un ratio sobre una
muestra truncada parece un dato y no lo es.

### I · Perfil de audiencia — 17, al final

| # | columna |
|---|---|
| 34 | `audiencia_segmentos` |
| 35 | `audiencia_dominante` |
| 36 | `temas` |
| 37 | `tema_dominante` |
| 38 | `ratio_educa_vs_anuncia` |
| 39 | `idioma_publica_es` |
| 40 | `idioma_publica_en` |
| 41 | `idioma_comentarios_es` |
| 42 | `idioma_comentarios_en` |
| 43 | `desajuste_idioma` |
| 44 | `registro` |
| 45 | `marcadores_culturales` |
| 46 | `precios_mencionados` |
| 47 | `barrios_mencionados` |
| 48 | `programas_mencionados` |
| 49 | `preguntas_recibidas` |
| 50 | `citas_por_etiqueta` |

### Las dos reglas que gobiernan este bloque

**Cada etiqueta lleva el texto que la produjo.** Si el sistema dice
`credito:4`, tiene que poder mostrar las cuatro frases. Por eso `etiquetar()`
devuelve un `Etiquetado` con conteo y citas, y **no existe ninguna función que
devuelva solo conteos**.

⛔ **Nada de puntajes compuestos.** No hay «audiencia latina: 7,3» en ningún
lado: un número así no se puede discutir ni verificar, y esconde de dónde
salió.

**Por qué existe este bloque:** un realtor que publica **en inglés** sobre
primera compra, enganche y crédito salía con `captions_es_ratio = 0,0` y se
descartaba — **y es exactamente nuestro cliente, en otro idioma**. El idioma es
un atributo del público, no un requisito de entrada.

⚠ **Los marcadores culturales describen el CONTENIDO publicado, no a la
persona.** Que un caption lleve una bandera de Guatemala dice que eso se
publicó; **no dice de dónde es quien lo publicó**, y no se usa para inferirlo.

---

## 10 · La salida a Excel

```
python realtor_scraper/exportar_ig_excel.py
```

Lee `output/ig_signals.csv` y escribe `data/salida/instagram_perfiles.xlsx`.
Las celdas se cortan a **32.000** caracteres.

⚠ **Avisa si el CSV está atrasado respecto del crudo.** El scraper guarda un
JSON por perfil y **el CSV solo se actualiza al correr `--parsear`**. El 30/09
había **513 crudos y 300 filas** en el CSV: 213 perfiles raspados que no
estaban en ningún lado. **Un exportador que no mire eso entrega un Excel
incompleto con cara de completo.**

### Las citas completas van aparte

El CSV lleva 3 citas por etiqueta recortadas a 200 caracteres, porque es una
vista para leer. **Las completas van a `output/ig_audiencia.json`**, en su
propio archivo y **no dentro de `ig_raw/`**: ese directorio es el crudo, y hay
una prueba que falla si aparece algo derivado adentro.

---

## 11 · Cómo se reanuda tras un corte

**El checkpoint vive en `output/ig_checkpoint.json`** y lleva:

```json
{"hechos": ["<clave>", ...], "detenido_por": null, "iniciado_en": "..."}
```

Cada perfil se marca **en cuanto su JSON está en disco**, así que una
interrupción cuesta **un perfil, no el lote**.

Se escribe a un temporal y se renombra (`os.replace`), de modo que un corte a
mitad de escritura no deja un JSON truncado que el parser lea como válido. Lo
mismo con cada crudo.

| bandera | efecto |
|---|---|
| *(nada)* | reanuda: salta los que están en `hechos` |
| `--desde-cero` | ignora el checkpoint y reempieza |
| `--reintentar-ilegibles` | devuelve al montón los crudos sin contenido legible |
| `--excluir-descartados` | saca los `DESCARTADO` y `RECLASIFICADO` |
| `--limite N` | corta el lote |

⛔ **`--reintentar-ilegibles` NO repite los privados ni los vacíos**, y es
correcto: **no mejoran repitiendo**. Solo vuelven los estados cuyo
`conviene_reintentar` es verdadero (ver la tabla de §6).

### ⚠ No te fíes del código de salida

Si el lote se lanza con una tubería (`| tee archivo.log`), el código de salida
es el de la tubería, **no el del script**: un proceso que revienta puede
terminar con `0`. **La forma de saber si terminó es contar los crudos y
comparar con el objetivo**, no mirar el código.

---

## 12 · Cómo se ejecuta, de principio a fin

```
# 0 · una sola vez
pip install -r realtor_scraper/requirements.txt
python -m playwright install chromium
python -m instagram.finder --iniciar-sesion

# 1 · ver qué se va a raspar, sin raspar
python -m instagram.finder --objetivo

# 2 · el piloto, OBLIGATORIO antes del lote grande
python -m instagram.finder --piloto 20 --con-ventana
python -m instagram.finder --revisar-piloto

# 3 · el lote
python -m instagram.finder --lote

# 4 · derivar (no necesita navegador)
python -m instagram.finder --parsear

# 5 · a Excel
python realtor_scraper/exportar_ig_excel.py

# en cualquier momento: qué falta
python realtor_scraper/pendientes_instagram.py
```

⚠ **El piloto va con `--con-ventana` y la revisión a mano va ANTES del lote.**
El propio script lo recuerda al terminar. No es burocracia: es la única forma
de ver que los selectores siguen funcionando antes de gastar diez horas.

### Qué falta, y por qué hay que mirar tres fuentes

`pendientes_instagram.py` cruza **tres** y cada una sabe algo distinto:

| fuente | qué sabe |
|---|---|
| el libro PACS | el **objetivo**: quién tiene handle |
| el checkpoint | qué raspó el proceso local |
| Supabase `v_ig_senales_current` | qué llegó a la base |

**Las dos últimas pueden no coincidir**: un perfil raspado cuyo parseo nunca se
cargó está hecho para el checkpoint y ausente para la base. Ese caso **se
reporta aparte en vez de decidirlo solo**, porque volver a raspar cuesta tiempo
y sesión.

---

## 13 · Cómo leer el CSV — los límites

- **`captions_n` manda sobre todo lo demás.** Cualquier `false` con pocos
  captions es «no se vio», no «no hay».
- **`handle_confianza = baja` invalida la fila** para señales de contenido.
- **`paginacion_truncada = true` vacía `captions_es_ratio` a propósito.**
- **`estado_perfil != publico_leido` significa que no hay contenido legible**,
  y el valor dice si el problema es de la persona (`privado`, `vacio`) o
  nuestro (`handle_equivocado`, `muro_de_sesion`, `sin_grid`).
- **Las cuentas hipotecarias etiquetadas son una pista sin confirmar.**
- **Los marcadores culturales describen publicaciones, no personas.**

---

## 14 · Lo que este proceso NO hace

- **No saca contactos de Instagram.** Teléfono y correo salen del módulo de
  identidad (`state_licenses/`) y de los insumos privados.
- **No perfila a quien comenta.**
- **No infiere origen, etnia ni estatus** de nadie, ni por nombre ni por
  contenido.
- **No puntúa.** Produce señales; el scoring es otra capa.
- **No usa Zillow.** Retirado el 2026-09-21: produjo cero columnas y sus
  términos de uso prohíben el scraping.

---

## 15 · El verificador

```
python realtor_scraper/verificar_manuales_ig.py
```

Lee **del código** las 50 columnas con su posición, los diez estados, los tres
niveles de confianza, las 27 rutas que no son handles, las constantes de ritmo
y las tres consultas, y **falla si este manual dice otra cosa**.

No importa los módulos —arrastran Playwright y loguru— sino que parsea la
fuente, así que corre en una máquina que solo quiera revisar la documentación.

**Correrlo después de tocar el manual o el código.**
