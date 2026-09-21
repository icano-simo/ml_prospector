# Bloque 1-bis · Profundizar el scraper de Instagram

**Fecha:** 2026-09-21 · **Estado:** código hecho y probado (36 pruebas nuevas,
182 en total). **No corrió contra Instagram:** no hay `playwright` en esta
máquina y no tengo la cuenta dedicada.

---

## Cómo leí «no escribas un módulo nuevo»

Extendí los archivos que ya tenían cada rol, sin crear un sistema paralelo:

| Archivo | Qué se le agregó |
|---|---|
| `instagram/finder.py` | la orquestación: lista de objetivo, lote con ritmo y checkpoint, parser, escritura del CSV, CLI |
| `instagram/extraccion.py` | `capturar_crudo()` — la captura profunda con sesión. Es el archivo cuyo trabajo es tocar el DOM |
| `instagram/idioma.py` | el detector de idioma real, reemplazando el conteo de palabras |
| `navegador.py` | la sesión dedicada de Instagram |

No hay `instagram2/` ni `scraper_profundo/`. Si tu intención era literalmente
un solo archivo, decilo y consolido: la lógica no cambia de lugar, solo el
archivo donde vive.

---

## El cambio de fondo · dónde estaba y dónde está

`article img[alt]` **ya no era la fuente** cuando llegué a este bloque: se
retiró en el [Bloque 1](bloque-1-instagram.md). Lo verifiqué —
`grep -rn "img\[alt\]"` solo lo encuentra en docstrings que explican que se
quitó.

Lo que faltaba era otra cosa, y es lo que hace este bloque:

| | Bloque 1 | Bloque 1-bis |
|---|---|---|
| fuente | captions reales | **igual, pero con sesión iniciada** |
| clasificación de idioma | conteo de palabras funcionales | **detector real (`lingua`)** |
| persistencia | nada crudo a disco | **un JSON por perfil, `ig_raw/`** |
| arquitectura | una pasada | **dos pasadas: raspar y parsear** |
| comentarios | hasta 12 posts, sin handle | **hasta 20 por post, con handle en el crudo** |
| salida | columnas `ig_*` en el enriched | **`ig_signals.csv` con el contrato exacto** |

---

## Crudo primero, parser después

```
pasada 1   correr_lote()      navegador  ->  ig_raw/{clave}.json
pasada 2   parsear_crudos()   ig_raw/*.json  ->  ig_signals.csv
```

**La pasada 2 no toca la red.** Si el parser tiene un bug, se arregla y se
re-parsea en segundos. Sin el crudo, cada bug del parser cuesta una pasada
entera: 1.203 perfiles a 30 s son **10 horas**, y cada pasada gasta la cuota de
una cuenta que se puede bloquear.

Interpretar es lo único que se puede repetir gratis.

Tres decisiones que lo hacen cumplirse:

- **el crudo no deriva nada.** Hay una prueba que falla si aparece
  `captions_es_ratio`, `menciona_lender`, `idioma` o `engagement_rate` dentro
  de un JSON de `ig_raw/`;
- **escritura atómica**: se escribe a `.json.tmp` y se renombra, así una
  interrupcion no deja un JSON truncado que el parser lea como válido;
- **un crudo roto no tumba la pasada**: se registra en `ilegibles` y se sigue.

### JSON primero, DOM después · y en la corrida real manda el DOM

`capturar_crudo()` pide el endpoint interno de Instagram
(`/api/v1/users/web_profile_info/`) usando las cookies del contexto, y cae al
DOM si no responde. El JSON es mucho más estable que el DOM y trae en una sola
petición el caption real, el timestamp exacto en epoch, las cuentas etiquetadas
y la ubicación.

**Medido con la sesión funcionando: el endpoint devuelve HTTP 429 sostenido.**
Con la cuenta dedicada recién creada, esperando 4 minutos y calentando la sesión
con navegación normal antes de tocarlo, sigue en 429. El cuerpo del 429 es la
página HTML con `class="logged-in"`, así que la sesión está bien: lo limitado es
el endpoint. Parte del 429 lo causé yo sondeándolo 4 veces por script en dos
corridas, pero la espera no lo levantó.

Así que la vía que corre de verdad es la otra, y **no es un respaldo pobre.**
`capturar_por_dom_con_sesion()`, medido sobre perfiles reales:

| De dónde sale | Qué da |
|---|---|
| `meta[name=description]` | seguidores, seguidos, n\_posts, nombre visible y bio |
| `og:description` del post | caption completo, likes, n\_comentarios y el **autor** |
| `time[datetime]` | fecha exacta, `2023-05-20T14:55:22.000Z` |
| el propio caption | las @menciones |
| la página del post | geotag, «Humboldt Park, Chicago» |
| ancla en «Reply» | los comentarios con su autor |

Los comentarios se anclan en el botón *Reply* / *Responder*, que es texto
visible y no una clase CSS: las clases de Instagram son ofuscadas y cambian en
cada deploy. Desde ahí se sube hasta el bloque que tiene el handle y el texto.
En el post de prueba dio 15 comentarios con autor donde todos los selectores por
clase daban cero.

Lo único que no se alcanza son las **cuentas etiquetadas en la foto**, que
necesitan un clic sobre la imagen. Las @menciones del caption sí, y son la vía
principal de S6.

`correr_lote()` ya **no se detiene** si el endpoint no responde: sigue por DOM,
lo declara en el manifiesto y en cada crudo, y lo dice en el log. Detenerse
tenía sentido cuando el DOM era pobre; con esta tabla, no.

**El costo quedó medido: ~8,5 s por post**, porque es una navegación por post.
Unas diez veces más lento que el JSON. Por eso `--posts` pasó a ser parámetro y
el log estima el tiempo con ese número, no con la pausa entre perfiles — que no
es lo que domina.

### El bug que habría envenenado el lote en silencio

El selector de la grilla del perfil agarraba **cualquier** enlace a post de la
página, y en `@javierhernandezrealtor` 2 de 23 eran de otras cuentas
(`/yourgirltheadvisor/reel/...`). Sin filtro, esos captions habrían entrado como
si fueran del realtor. Es la misma familia que el bug del alt-text y el de
DuckDuckGo: **un selector amplio leído como si fuera el sujeto.**

Ahora hay dos filtros y son independientes:

1. se descartan los enlaces cuya ruta no empieza con `/p/`, `/reel/` o
   `/{handle}/`;
2. al abrir cada post se compara el **autor** que declara `og:description`
   contra el handle esperado. Si no coincide, el post se descarta.

Lo descartado se cuenta en `posts_ajenos_descartados`, dentro del crudo. En la
corrida real: 4 descartados en ese perfil, 0 en los demás.

Dos más, encontrados en la prueba de punta a punta:

- **`nombre_visible` salía `None` en todos los perfiles**, porque lo sacaba del
  `<title>` y en `domcontentloaded` el título todavía dice solo «Instagram».
  Ahora sale del meta description. Importa porque sin él la verificación de
  handle compara solo contra el handle y queda más débil: con el arreglo, el
  perfil de prueba pasa de *sin nombre* a `handle_confianza = alta`.
- **`categoria_declarada` traía el bloque entero del header**, doscientos
  caracteres pegados. Ahora se busca la línea exacta contra una lista de
  categorías conocidas y da `Real Estate Agent`.

---

## El detector de idioma · medido, no elegido

El brief pide «un detector de idioma real sobre el texto, no conteo de palabras
clave». Probé dos sobre 17 captions realistas de agentes inmobiliarios —
cortos, con emoji, hashtags y términos del oficio en inglés en medio del
español:

| detector | aciertos |
|---|---|
| `langdetect` | 15 / 17 |
| **`lingua`** | **17 / 17** |

Y los dos fallos de `langdetect` son exactamente el caso que importa:

```
"¡Vendida! 🏡🔑 Felicidades"                      ->  pt  confianza 1.00
"Casa abierta este sabado 🏠 #openhouse #austin"  ->  pt  confianza 1.00
```

**Portugués, con confianza máxima.** Ningún umbral los habría filtrado. Además
`langdetect` levanta excepción con texto de solo emoji y es no determinista sin
fijar semilla.

La ventaja decisiva de `lingua` acá es poder **restringir el espacio de
hipótesis a {español, inglés}**, que es lo correcto en este dominio y elimina la
confusión con portugués e italiano.

Rendimiento medido: **11.307 detecciones/s**. El lote completo son ~758.000
detecciones, o sea **~1 minuto de CPU**. No es un costo a optimizar.

### La limpieza previa hace la mitad del trabajo

Antes de preguntarle al detector se sacan URLs, `@menciones`, `#hashtags`, emoji
y puntuación. Sin eso, `#realtor #austin #texas #realestate` se clasifica como
inglés con 0,83 de confianza — y un hashtag no es evidencia de idioma.

Con la limpieza, todo texto sin letras queda **indeterminado por construcción**,
no por un umbral. En la calibración, los cuatro casos de basura (`🔥🔥🔥`, `👏`,
`!!!`, `@otro_agente`) dieron los cuatro 0 letras.

### Dos pisos, porque un caption y un comentario no miden lo mismo

| pieza | mín. letras | mín. confianza |
|---|---|---|
| caption | 18 | 0,60 |
| comentario | **10** | 0,60 |

`"Se puede con ITIN?"` son 14 letras: con el piso de caption se perdería, y es
justo el comentario que importa para S8.

En la calibración sobre 26 comentarios reales hubo **cero clasificaciones
erróneas en todos los pisos probados**. Lo único que cambia el piso es cuántos
comentarios reales se descartan.

### Si falta el detector, falla ruidosamente

`instagram/idioma.py` **no se degrada** a conteo de palabras clave. Si `lingua`
no está instalado, levanta con instrucciones de instalación. Hay un escape
explícito (`ML_PROSPECTOR_IDIOMA_HEURISTICA=1`) y con él **cada pieza sale
marcada con `motor="heuristica"`**, y el informe de la pasada 2 lo declara en
`motor_idioma`. Nadie confunde una estimación con una medición por accidente.

---

## Estado del perfil · el bug que había que matar

`estado_perfil` expone los cinco valores del brief:

| valor | significa |
|---|---|
| `publico_leido` | se leyeron los posts |
| `privado` | bio y contadores sí, posts no |
| `no_encontrado` | el handle no existe |
| `bloqueado` | muro de login, checkpoint, 429 |
| `handle_dudoso` | cargó, pero no verifica que sea esta persona |

Internamente hay un sexto (`sin_handle`, que distingue «no hubo candidato» de
«el handle no existe»); se mapea a `no_encontrado` y el detalle fino queda en el
JSON crudo. Hay una prueba que verifica que el CSV **solo** emite esos cinco.

**Toda señal ausente es celda vacía, nunca 0 ni False.** La distinción que
importa, vista en la demo:

| perfil | `captions_n` | `captions_es_ratio` | por qué |
|---|---|---|---|
| Michael Brennan (inglés) | `10` | **`0.0`** | se leyeron 10 captions y ninguno era español. Es una medición |
| Luis Gómez (privado) | *(vacío)* | *(vacío)* | no se leyó nada. **No es un cero** |
| Rosa Méndez (bloqueado) | *(vacío)* | *(vacío)* | idem |

Un perfil privado no es un perfil sin español: es un perfil que no leímos.

---

## Verificación del handle · lo que caza el 98,1%

La demo incluye a propósito un caso real de la forma del bug: el libro trae
`carmen` como handle de **CARMEN VILLASEÑOR**, y `instagram.com/carmen` es
Carmen Electra.

```
--- CARMEN VILLASENOR (carmen) ---
    estado_perfil        handle_dudoso
    handle_confianza     baja
    captions_n           <- null
    captions_es_ratio    <- null
    menciona_lender      <- null
    ... las 20 señales de contenido en null
```

Sin esta verificación, ese perfil habría aportado 3 captions en inglés, 1,2
millones de seguidores y un `engagement_rate` — todo sobre la persona
equivocada. Un handle equivocado no produce un error: produce veinte señales
sobre otra persona.

---

## Ritmo y sesión

| Requisito | Cómo está implementado |
|---|---|
| cuenta dedicada | `PERFIL_IG_DIR` es un directorio de perfil **separado** del general. `iniciar_sesion_instagram()` lo dice en pantalla en mayúsculas antes de abrir la ventana |
| 20-40 s por perfil, aleatorio | `PAUSA_ENTRE_PERFILES_LOTE = (20.0, 40.0)`, más una pausa larga de 3-7 min cada 40 perfiles |
| reutilizar la sesión | contexto persistente; se comprueba **una vez** al empezar el lote con `sesion_de_instagram_iniciada()` |
| detenerse ante desafío | `MAX_BLOQUEOS_SEGUIDOS = 3` → corta, escribe el motivo en el checkpoint y **no reintenta** |
| checkpoint por perfil | se marca en cuanto el JSON está en disco. Una interrupción cuesta un perfil, no el lote |

**No automaticé el login**, y es deliberado: automatizar el ingreso de
credenciales significa guardarlas en algún lado, y la cuenta dedicada de
Instagram es exactamente la credencial que no conviene tener en un archivo. El
flujo abre una ventana, una persona inicia sesión una vez, y las cookies quedan
en el perfil persistente.

**Sin sesión, el lote no arranca.** `correr_lote()` comprueba y sale con un
mensaje explicando por qué: sin sesión Instagram sirve una versión recortada del
perfil, y eso *no da error* — da un lote entero de perfiles que parecen vacíos.
Es la misma familia de fallo que el `{}` del Bloque 1.

Lo de **horario de baja actividad y una sola IP estable** es operativo y no lo
puedo hacer cumplir desde el código. Queda como instrucción.

---

## Sobre quiénes correrlo · el filtro da 1.203, no 750-1.000

`cargar_objetivo()` aplica el filtro del brief **literal**: hoja
`Realtors PACS`, `nivel_de_calificacion = MQL` **o** `TIER` que empiece por A o
por B.

```
filas en la hoja        4.249
objetivo                1.203      <- no 750-1.000
con handle en el libro  1.200
sin handle              3
con email               1.191
horas a 30 s            10,0       <- no 8
```

Es una **unión**, no una intersección: MQL son 756, TIER A+B son 876, y se
solapan en 429. De ahí el número.

Dos consecuencias que conviene ver antes de empezar diez horas de scraping:

**1 · Los 1.200 handles del libro ahorran la búsqueda.** El lote los usa como
candidato de partida en vez de buscarlos en DuckDuckGo — pero **los verifica
igual**, porque esos handles vienen del 98,1% sin verificar. Solo 3 perfiles
necesitan búsqueda.

**2 · El filtro literal re-admite a 6 que la metodología ya excluyó.** Hay 5
`DESCARTADO` y 1 `RECLASIFICADO POR MMI — fuera de ICP` cuyo TIER es A o B.
`DESCARTADO` significa *no contactar* — lujo, inversión pura, o bajo el piso de
volumen — y el reclasificado lo sacó del ICP el dato transaccional de MMI.

Raspar sus perfiles no hace daño; meterlos en un CSV que alimenta prospección
sí. Se comportan así:

- **entran, porque el filtro es el que pedís**, y se listan en
  `informe["excluidos_por_metodologia"]` con nombre y motivo;
- `--excluir-descartados` los saca. Es una decisión de una línea y es tuya.

También entran 279 TIER C y 48 TIER D por ser MQL, que sí es lo correcto: MQL es
el veredicto de la metodología y TIER es el score viejo.

---

## Muestra truncada · un ratio truncado no es un ratio peor

Si el perfil declara N publicaciones y se recuperaron **menos del 60% de las
solicitadas sin que haya llegado el fin de la paginación**, se marca
`paginacion_truncada = true` y **`captions_es_ratio` va a null**.

La distinción entre «no habla español» y «no lo leímos» ya costó 1.075 perfiles
una vez. Un ratio calculado sobre una muestra truncada no es una medición peor:
es otra cosa.

### Cómo se decide

`_evaluar_truncamiento()` en `extraccion.py` escribe cinco campos **en el
crudo**, porque son hechos de la captura y no derivaciones:

```
posts_solicitados            30
posts_recuperados            12
n_publicaciones_declaradas   340
posts_esperados              30      <- min(solicitados, declaradas)
fin_de_paginacion            False
paginacion_truncada          True
motivo_truncamiento          "se recuperaron 12 de 30 esperados (40%,
                              umbral 60%) y la paginacion no llego al final.
                              El perfil declara 340 publicaciones."
```

Dos decisiones que evitan falsos positivos:

**`posts_esperados = min(solicitados, declaradas)`.** Pedirle 30 posts a quien
tiene 8 no es un truncamiento: es un perfil chico. Si declara 8 y trajimos 8 con
`fin_de_paginacion = true`, la muestra está **completa**, no al 27%.

**`fin_de_paginacion` gana sobre el umbral.** Si el timeline se agotó, no hay
nada truncado por definición, cualquiera sea el conteo.

Y `fin_de_paginacion` distingue dos cosas que antes se confundían: *«no hay más
posts»* de *«no pudimos seguir pidiendo»*. `_mas_posts_por_json()` ahora devuelve
`(posts, llego_al_final, fallo)` — y cuando el endpoint GraphQL no responde,
devuelve `False` y deja el motivo en `errores`, en vez de cortar el bucle en
silencio como si se hubiera acabado el timeline.

### Qué se anula y qué no

| campo | con muestra truncada |
|---|---|
| `captions_es_ratio` | **null** |
| `captions_n` | **se conserva** — es la evidencia de por qué el ratio está vacío |
| `paginacion_truncada` | `true` |
| `estado_perfil` | sigue siendo `publico_leido`: el perfil SÍ se leyó, incompleto |

En un perfil privado o bloqueado, `paginacion_truncada` es **null**, no `false`:
no hubo timeline que truncar, y el estado ya dice qué pasó.

> **Lo que NO hice, y es una decisión tuya.** El mismo argumento aplica a
> `comentarios_es_ratio` —los comentarios vienen de esos mismos posts truncados—
> y a `hueco_max_dias`, que sobre una ventana recortada **subestima** los huecos.
> El pedido nombraba `captions_es_ratio`, así que anulé ese y nada más. Cada uno
> de los otros es una línea en `parsear_crudo`.

---

## El piloto de 20 · desde el Top 300

```bash
python -m instagram.finder --iniciar-sesion              # una sola vez
python -m instagram.finder --objetivo --solo-top300      # ver la lista
python -m instagram.finder --piloto 20 --con-ventana
python -m instagram.finder --parsear
python -m instagram.finder --revisar-piloto
```

`--piloto` implica `--solo-top300`: la hoja está ordenada por **SCORE ACCIÓN
SEPT descendente**, así que los primeros 20 son los mejores prospectos, que es
donde tiene sentido mirar los captions contra la pantalla.

### El cruce con Top 300 tuvo un bug que vale contar

La hoja `Top 300` **no tiene columna de handle**, solo `IG url`. Así que hay que
cruzarla con `Realtors PACS` por email, con el nombre como respaldo.

El primer cruce dio **301 filas sobre 300**, y con un `TIER D` adentro — cuando
la hoja es solo Tier A y B. Ese `TIER D` fue la señal: el cruce por nombre
estaba matcheando dos veces la misma fila.

Hay **dos ANDREA SAAVEDRA** en el libro. La del Top 300 cruzaba por email; la
otra, Tier D, cruzaba por nombre contra la misma fila.

Ahora el cruce es **uno a uno**: primero email, que es la llave confiable;
después nombre, solo para las filas que nadie reclamó. Y los descartes quedan
nombrados en la salida:

```
"descartados_por_nombre_ambiguo": [
  "ANDREA SAAVEDRA (D - BAJO AJUSTE) coincide por nombre con el puesto 217,
   que ya reclamo otro registro por email"
]
```

Resultado: **300 exactas, 0 sin cruzar, 168 Tier A + 132 Tier B** — idéntico a
la hoja.

### Las cuatro preguntas, en tu orden

`revisar_piloto()` las imprime, y el orden importa: **la 1 invalida a las otras
tres.**

**1 · ¿Cuántos posts llegaron por perfil?** Tabla por perfil con posts
recuperados, publicaciones declaradas, `fin_de_paginacion` y `paginacion_truncada`.
Y el chequeo que decide:

```
!!! DETENERSE. Los 4 perfiles legibles trajeron EXACTAMENTE 12
    posts, que es lo que devuelve la primera pagina del JSON del
    perfil. La paginacion NO corrio: el query_hash del timeline
    caduco.

    Donde se arregla: QUERY_HASH_TIMELINE en instagram/extraccion.py.
    Se saca del DevTools del navegador mirando la peticion a
    /graphql/query/ al hacer scroll en un perfil.

    Los crudos NO se pierden: estan en disco y se re-parsean gratis
    cuando el hash este bien. Pero hay que volver a raspar, porque
    los posts 13 a 30 nunca llegaron.
```

**2 · ¿Los captions son el texto real?** Los tres primeros captions de cada
perfil, **junto al `accessibility_caption` de Meta** para comparar, y el enlace
`instagram.com/handle/` para abrir al lado.

**3 · ¿Algún privado quedó marcado como privado?** Si hay, los lista con su
`captions_es_ratio` para confirmar que está vacío. Si no hay **ninguno**, avisa
que es la misma forma del bug viejo y pide confirmar a mano.

**4 · ¿El ratio de español tiene sentido?** Media, mediana y el ratio por
perfil con su denominador. Si la media es **≤ 6%**, `DETENERSE`.

Y cierra con un veredicto explícito.

### Probado en los dos escenarios que deciden

Corrí la revisión sobre dos conjuntos sintéticos:

| | posts/perfil | truncadas | privados | ratio | veredicto |
|---|---|---|---|---|---|
| **A** hash caducado | 12 clavados | 4 de 4 | 0 | `None` | **NO LANZAR** |
| **B** paginación corre | 28 | 0 | 1 | 71,4% | sigue |

Lo que hace bien el orden, en el escenario A:

```
4 · ¿EL RATIO DE ESPAÑOL TIENE SENTIDO?
   Ninguna fila tiene ratio.
   Motivo: 4 con muestra truncada. Arregla la paginacion (1)
   antes de sacar conclusiones de idioma.
```

En el escenario B, el privado sale bien marcado:

```
   OK: 1 marcados como privados.
      @xochiltherealtor    captions_es_ratio=None (tiene que estar vacio)
```

Y de paso la revisión reporta S6 y S8, que son las dos categorías que estaban
vacías.

> **Nota operativa:** los glifos `⚠` se cambiaron por `!!!`. La consola de
> Windows usa cp1252 y no puede imprimirlos: un `UnicodeEncodeError` corta la
> salida **justo donde estaba la advertencia**. Hay un verificador en el
> scratchpad que revisa que ninguna línea emitida por `print()` o `logger` tenga
> caracteres fuera de cp1252.

---

## La salida

### `ig_raw/{email_o_handle}.json`

Un archivo por perfil. La clave prefiere el email; si no hay, el handle; si no,
el nombre. Se sanea para que sea un nombre de archivo válido en Windows — hay
prueba de que no quedan `/`, `\` ni `:`.

Trae, sin derivar nada: el bloque de perfil completo, hasta 30 posts con caption
íntegro, timestamp, tipo, likes, comentarios, etiquetadas y ubicación, hasta 20
comentarios por post **con el handle del autor**, el destino final del enlace de
la bio, y el bloque `objetivo` con lo que decía el libro.

### `ig_signals.csv`

Las **27 columnas del brief en su orden exacto**, más 5 agregadas al final. Hay
una prueba que falla si el orden o los nombres cambian, porque es contrato con
la app que lo consume.

| Columna | Qué trae |
|---|---|
| `menciona_lender` | **el nombre**, no un booleano: `@maria.loanofficer` |
| `comentarios_pregunta_calificacion` | **cuántos** comentarios de terceros preguntan por enganche, crédito, calificación, ITIN o documentos |
| `menciona_itin/dpa/credito/va/fha/primera_casa` | **conteo de posts** que lo mencionan (0 si ninguno, vacío si no se leyó) |
| `cuentas_hipotecarias_etiquetadas` | todas, con su frecuencia: `@maria.loanofficer (5)` |
| `comentarios_redactados` | qué se le sacó al texto de terceros y cuántas veces: `telefono (1), mencion (4)`. Vacío si no hubo nada |
| `paginacion_truncada` | `true` si la muestra quedó incompleta. Va **al final** para no mover el orden que ya consume la app |

> **Una ambigüedad que resolví y conviene que revises.** El brief define
> `menciona_lender` como un nombre y `comentarios_pregunta_calificacion` como un
> conteo, pero no dice qué son los otros `menciona_*`. Los emití como **conteo
> de posts**: es más informativo y sigue funcionando con `if row.menciona_itin`.
> Si la app espera `"True"`/`"False"`, se rompe — y es un cambio de una línea.

Formato de las columnas de texto, tal como pide el brief:

```
captions_texto:
  2026-09-15 | Felicidades a la familia Ramirez por su primera casa. Gracias
  @maria.loanofficer por cerrar tan rapido ¶ 2026-09-09 | Cerramos con FHA y
  ayuda de enganche. Mi cliente no sabia que ya calificaba ¶ ...

comentarios_texto:
  Cuanto necesito de enganche para una casa asi? ¶ Se puede con ITIN? No tengo
  seguro social ¶ Mi credito esta en 580, califico? ¶ ...

comentarios_del_agente:
  Claro que si, escribeme por privado y lo vemos ¶ Dejame consultarlo con mi
  lender y te escribo hoy
```

Cronológico inverso, prefijados con la fecha, `¶` con espacios, saltos de línea
convertidos a espacio, **sin el handle del autor** en los comentarios — vive en
el JSON crudo. UTF-8 **con BOM**, comillas escapadas según CSV estándar, corte a
30.000 caracteres con `texto_truncado = true`.

Esa última columna vale lo que dice el brief. En la demo:

> alguien pregunta *«¿Se puede con ITIN?»* y el agente responde *«Déjame
> consultarlo con mi lender y te escribo hoy»*.

Ahí hay un dolor confirmado, en las palabras del propio agente, y está en su
propia columna.

### Una muestra real

Corrí el parser sobre 6 perfiles sintéticos que cubren los cinco estados:

```
motor_idioma            lingua
crudos_leidos           6
filas_escritas          6
por_estado_perfil       publico_leido 3 · privado 1 · bloqueado 1 · handle_dudoso 1
por_handle_confianza    alta 4 · media 1 · baja 1
captions_es_ratio       media 0,489 · mediana 0,667   (sobre 3 filas con ratio)
S6 menciona_lender      1 de 6
S8 preguntas            2 de 6
```

Y la fila del caso bueno:

```
captions_n                        10
captions_es_ratio                 0.8          <- 8 de 10, correcto
comentarios_n                     6
comentarios_es_ratio              0.8333
menciona_lender                   @maria.loanofficer
cuentas_hipotecarias_etiquetadas  @maria.loanofficer (5)
comentarios_pregunta_calificacion 4
posts_comarketing                 1
engagement_rate                   0.03038
hueco_max_dias                    7
geotags_top                       Houston, Texas (2), Katy, Texas (1)
designaciones                     ABR, GRI
```

La prueba central del bloque construye un perfil con **8 de 12 captions en
español** y verifica que el parser recupere exactamente `8/12`. Es la única
forma de distinguir «el detector anda» de «el detector devuelve algo».

---

## Pruebas

**65 en esta suite, 220 en total, 0 fallas.** Sin navegador, sin red, sin
`pandas`.

```bash
python tests/test_instagram_profundo.py
python tests/correr_todo.py
```

Las que vale la pena conocer por nombre:

- `test_el_ratio_de_espanol_recupera_la_verdad` — 8/12 conocidos
- `test_el_alt_text_no_contamina_el_caption` — captions en español, alt en inglés
- `test_el_caso_que_langdetect_falla` — los dos que daban portugués
- `test_privado_deja_las_senales_en_null_no_en_cero`
- `test_handle_de_otra_persona_queda_dudoso_y_sin_senales`
- `test_menciona_lender_devuelve_el_NOMBRE_no_un_booleano`
- `test_el_crudo_guardado_conserva_el_objetivo_y_no_deriva_nada`
- `test_ida_y_vuelta_por_disco_con_bom_y_comillas`
- `test_los_cinco_estados_del_brief_y_nada_mas`

Y las del truncamiento y el Top 300:

- `test_doce_de_treinta_con_mas_paginas_es_truncada` — el caso del hash caducado
- `test_dieciocho_de_treinta_alcanza_el_60_por_ciento` — el borde exacto
- `test_diecisiete_de_treinta_no_alcanza` — el otro lado del borde
- `test_perfil_chico_agotado_no_es_truncamiento` — 8 de 8 es completo
- `test_perfil_chico_sin_llegar_al_final_se_mide_contra_lo_declarado` — 7 de 10, no de 30
- `test_fin_de_paginacion_gana_sobre_el_umbral`
- `test_privado_no_tiene_truncamiento_sino_estado` — `null`, no `false`
- `test_el_piloto_detecta_los_doce_clavados`
- `test_el_piloto_no_alarma_cuando_la_paginacion_corre`
- `test_el_piloto_alarma_si_el_ratio_ronda_el_tres_por_ciento`
- `test_el_cruce_con_top300_es_uno_a_uno` — el que caza las 301 sobre 300
- `test_top300_conserva_el_orden_de_la_hoja`

Y las de la sesión y la redacción, que son las últimas:

- `test_sin_cookies_de_sesion_no_hay_sesion_aunque_el_dom_diga_que_si` — el falso positivo
- `test_el_dom_solo_sirve_como_evidencia_secundaria`
- `test_el_telefono_de_un_tercero_no_llega_al_csv`
- `test_el_email_y_la_mencion_de_un_tercero_tampoco`
- `test_el_comentario_del_agente_conserva_su_contacto` — la asimetría, a propósito
- `test_la_guarda_redundante_falla_ruidosamente`
- `test_la_pregunta_de_calificacion_sobrevive_a_la_redaccion` — S8 no se come la redacción

---

## Privacidad de terceros

El brief permite guardar el handle del comentarista, y ahí hay una diferencia
entre los dos archivos:

- **`ig_raw/*.json`**: guarda el handle, porque es la fuente y porque es lo que
  permite saber si un comentario es del agente o de un tercero;
- **`ig_signals.csv`**: **no** lo guarda. Los comentarios van solo como texto.
  Son terceros que no son nuestro prospecto, y el CSV es el archivo que circula.

Ambos están en `.gitignore`, junto con el directorio de sesión de la cuenta
dedicada — que son cookies, o sea una credencial. Y la guarda pre-commit ya
rechazaba `ig_signals.csv` por sus columnas `email` y `nombre`.

### El hueco: la guarda estaba escrita y no enchufada

`redactar()` existía en `comentarios.py` desde el Bloque 1 y corría dentro de
`Comentario.desde_crudo`. Pero `parsear_crudo()` arma las columnas de texto
leyendo el crudo **directo**, sin construir `Comentario`, así que la redacción
**no corría en la ruta que produce el CSV**. Lo vi auditando el idioma sobre la
captura real, en un comentario con teléfono y email dentro.

Dos cosas que vale separar, porque la conclusión primera era la equivocada:

- **El hueco era real.** Ninguna llamada a `redactar()` en `finder.py`.
- **Ese dato concreto no era de un tercero.** Las cuatro apariciones en el
  crudo de ANA OSORIO son de `@anakaren_properties`, o sea ella misma, y van a
  `comentarios_del_agente`. Donde la guarda sí actúa sobre terceros es en
  JAVIER HERNANDEZ: cuatro @cuentas ajenas, ahora `[cuenta]`.

Ahora el texto de terceros pasa por `redactar()` antes de entrar al CSV, y qué
se redactó queda declarado en la columna `comentarios_redactados` —
`telefono (1), mencion (4)` — porque una redacción silenciosa no le avisa a
nadie de que la gente está dejando su teléfono en los comentarios.

**La asimetría con el agente es deliberada.** Sus propios comentarios **no** se
redactan: es nuestro prospecto, su teléfono y su email ya los tenemos de Model
Match, y que los publique en su propio perfil es información de negocio. Un
tercero que comenta en un post no eligió aparecer en nuestro CRM.

Y como el bug fue justamente una guarda escrita sin enchufar,
`_verificar_sin_pii_de_terceros()` revienta al final de `parsear_crudo()` si
queda un email, un teléfono o un número largo en `comentarios_texto`. Es
redundante a propósito: usa los mismos patrones que `redactar()`, así que no
puede desincronizarse, y si alguien vuelve a armar esa columna por otra vía
falla en vez de publicar un teléfono.

> La regla que sale de acá, y sirve más allá de este archivo: **una guarda que
> no está en el camino que produce el archivo que circula, no es una guarda.**
> Que exista la función y que tenga pruebas no dice nada sobre si corre.

---

## Qué quedó sin resolver

1. ~~**No corrió contra Instagram.**~~ **Ya corrió.** Con la cuenta dedicada y
   `patchright` instalados, el piloto de 20 del Top 300 está capturando de
   verdad. Lo medido en esa corrida está arriba: el 429 del endpoint, la vía
   DOM con sesión, los 8,5 s por post, la contaminación de la grilla,
   `nombre_visible`, `categoria_declarada` y el hueco de redacción. Ninguno de
   esos seis se ve sin correrlo.

2. **Los endpoints internos de Instagram son la pieza frágil, y uno ya falló.**
   `/api/v1/users/web_profile_info/` **devuelve 429** para la cuenta nueva (ver
   arriba), y los dos `query_hash` de GraphQL —paginación del timeline y
   comentarios— **caducan sin aviso**. La vía que sostiene la captura hoy es el
   DOM con sesión, que es más lento pero no depende de ningún hash.

   Esto ya **no** se corta en silencio: la paginación devuelve
   `fin_de_paginacion = False` con el motivo en `errores`, el perfil queda con
   `paginacion_truncada = true`, su `captions_es_ratio` va a null, y
   `--revisar-piloto` grita `DETENERSE` con la ubicación del arreglo. Pero el
   hash sigue siendo algo que **hay que actualizar a mano** cuando caduque, y
   **el piloto de 20 es lo que lo detecta.** Es lo primero que hay que mirar.

3. **`tipo_post_reel_pct` no distingue reel de video.** El JSON de Instagram
   marca los dos como `GraphVideo`; no hay un campo que los separe. Todo video
   cuenta como reel. En la práctica casi todo video vertical de un agente *es*
   un reel, pero el número es «% de posts en video», no «% de reels».

4. **`captions_es_ratio` usa `captions_n` como denominador, tal como lo define el
   brief.** Eso incluye los captions indeterminados —emoji, solo hashtags— así
   que **subestima** la cuota de español cuando hay muchos. El denominador está
   en el CSV como su propia columna, así que la cifra es auditable, pero si
   querés el ratio sobre los *clasificables* hay que agregar una columna.

   **Y hay un caso que el detector colapsa: el caption bilingüe.** Hay agentes
   que escriben el mismo post dos veces, inglés arriba, español abajo,
   separados por una línea de guiones bajos. `@j_pantojagrp` tiene uno de 1.182
   caracteres así. El detector devuelve **un** idioma para todo el texto —
   `es`, con confianza **1,00** sobre algo que es mitad y mitad. La confianza
   miente; el veredicto, no tanto.

   **Medido antes de decidir: 3 de 132 captions, el 2,3%.** Con ese número no
   toqué nada, y la razón importa más que el número: contar el bilingüe como
   español **es** el comportamiento correcto. Un agente que escribe cada post
   en los dos idiomas está sirviendo a una audiencia hispanohablante, y
   mandarlo a `MIXTO` lo sacaría del numerador — o sea que subestimaría
   justamente al agente que más nos interesa. Lo que queda mal es la confianza
   de 1,00, y es interna: el portón está en 0,60, así que un caption bilingüe
   pasa como español, que es lo que se quiere.

   Si el bilingüe pasara del 2% al 20% en el lote grande, esto cambia de
   tamaño: ahí sí vale una columna que lo declare, porque «escribe en los dos»
   y «escribe la mitad en español» son intensidades distintas de P-Q14 y hoy
   dan el mismo número.

5. **El tiempo real es otro, y hay que decidirlo.** La estimación de 10 horas
   para 1.203 perfiles asumía el JSON. Con el endpoint en 429 y la captura por
   DOM, lo medido es **~8,5 s por post**, así que:

   | Alcance | Posts/perfil | Tiempo medido |
   |---|---|---|
   | piloto de 20 | 20 | ~1,1 h |
   | Top 300 | 20 | **~14 h**, no las 2,5 h estimadas con JSON |
   | Top 300 | 10 | ~7 h |
   | 1.203 (MQL + A/B) | 20 | ~56 h |

   Un perfil privado cuesta ~30 s —no se abre ningún post—, así que la cifra
   real del Top 300 depende de cuántos privados haya; en los primeros 7 del
   piloto son 3 de 7. **Las palancas son `--posts N` y `--sin-comentarios`**, y
   cuál tirar es decisión tuya, no mía: bajar `--posts` recorta el tiempo lineal
   pero empuja perfiles hacia `paginacion_truncada` y deja
   `captions_es_ratio` en null, que es exactamente el trade que el Bloque 1
   existe para no hacer a ciegas.

6. **No hay reintento de los bloqueados.** Cuando el lote se detiene por 3
   bloqueos seguidos, los perfiles ya marcados en el checkpoint no se vuelven a
   pedir — incluidos los que quedaron en `bloqueado`. Para reintentarlos hay que
   borrar sus entradas del checkpoint a mano. **No lo automaticé** porque
   reintentar en automático tras un bloqueo es exactamente cómo se pasa de un
   desafío temporal a una cuenta suspendida, y esa decisión la tiene que tomar
   una persona mirando el estado de la cuenta.

7. **Horario y IP no se pueden hacer cumplir desde el código.** Quedan como
   instrucción en este documento y en el mensaje de `--iniciar-sesion`.
