# Bloque 1 · Instagram real

**Fecha:** 2026-09-21 · **Estado:** reescrito y probado. **No corrió contra
Instagram**: ver *Qué quedó sin resolver*.

---

## El bug de fondo, medido

`_extract_post_alt_texts` leía `article img[alt]`. El atributo `alt` de
Instagram es **texto generado automáticamente por Meta para accesibilidad**,
casi siempre en inglés sin importar el idioma del caption. Todo el análisis de
idioma, comunidad y colaboración estaba construido sobre eso.

Medido sobre `historico_scored.csv`, 5.620 filas:

| Señal | Resultado | Por qué es imposible o inútil |
|---|---|---|
| `ig_is_private` | **0 positivos · 5.620 negativos · 0 nulos** | Ninguna cuenta privada en 5.620 perfiles inmobiliarios. La señal no se medía: se rellenaba con `False` |
| `ig_content_language = spanish` | **185 de 5.620 = 3,29%** | En un lote seleccionado por mercado latino |
| `ig_collaborates` | **33** positivos | Las `@menciones` viven en el caption, no en el alt |
| `ig_nahrep` | **29** positivos | Misma causa |
| `ig_posts_spanish` | 622 positivos | Derivado del mismo texto equivocado |
| handles "encontrados" | **5.516 de 5.620 = 98,1%** | Sin una sola verificación |

Y el daño estructural: **1.075 perfiles con handle y ninguna bio**, **4.557 con
handle y ninguna señal de contenido positiva**. Todos entraron al modelo con
`False` en cada señal — afirmaciones negativas que nadie midió.

La prueba más limpia de que nadie lo notó: **`ig_is_private` terminó con
importancia exactamente `0,000`** en el modelo. Una columna constante no aporta
nada, y un clasificador no se queja de una columna muerta.

---

## Los tres arreglos, en el orden pedido

### 1 · Detección de estado del perfil · [`instagram/estado.py`](../realtor_scraper/instagram/estado.py)

Seis estados explícitos, no cinco: el brief pedía cinco y hacía falta uno más
para el caso «no había handle candidato», que es distinto de «el handle no
existe».

| Estado | Qué significa | `contenido_legible` | Reintentar |
|---|---|---|---|
| `PUBLICO_LEIDO` | se leyeron los posts | **sí** | — |
| `PRIVADO` | bio y contadores sí, posts no | no | no |
| `NO_ENCONTRADO` | el handle no existe | no | **no** |
| `BLOQUEADO` | muro de login, checkpoint, 429 | no | **sí** |
| `HANDLE_EQUIVOCADO` | cargó, pero no es esta persona | no | no |
| `SIN_HANDLE` | no hubo candidato | no | no |

Tres decisiones de diseño que importan:

- **`BLOQUEADO` se evalúa ANTES que `PRIVADO`.** Un muro de login también dice
  "log in to see" y eso no significa que la cuenta sea privada.
- **Una página que cargó sin meta y sin posts es `BLOQUEADO`, no un perfil
  vacío.** Ahí es exactamente donde la versión anterior devolvía `{}`.
- **No hay `else` que caiga en «perfil sin señales».** Si aparece un caso nuevo,
  hay que agregar un estado y decidir qué hacer con él.

`EstadoPerfil.motivo()` devuelve el texto que va a la máscara de disponibilidad,
porque **el motivo importa**: un perfil privado es un dato sobre la persona, un
handle equivocado es un dato sobre nuestro scraper.

### 2 · Verificación del handle · [`instagram/verificacion.py`](../realtor_scraper/instagram/verificacion.py)

El 98,1% venía de una línea:

```python
handles = re.findall(r"instagram\.com/([A-Za-z0-9_.]{3,30})", content)
```

`content` es el HTML **completo** de la página de resultados. Devolvía el primer
`instagram.com/...` que apareciera en cualquier parte: un anuncio, el pie de
DuckDuckGo, el perfil de otra persona con nombre parecido.

Ahora se extraen de los `href` de los resultados (desenvolviendo el `uddg=` de
DuckDuckGo), se evalúan **hasta 5 candidatos** y **se queda con el primero que
verifica**, no con el primero que aparece.

Las dos condiciones del brief, las dos necesarias:

| nombre coincide | señal inmobiliaria | `handle_confidence` | ¿se usan sus señales? |
|---|---|---|---|
| sí | sí | **ALTA** | sí |
| sí | no | **MEDIA** | sí — puede ser su cuenta personal |
| no | sí | **BAJA** | **no** |
| no | no | **BAJA** | **no** |

Más una excepción que vale mucho: **si la bio declara un número de licencia que
coincide con el nuestro, es ALTA sin importar el nombre.** La licencia es la
llave de identidad del sistema entero; un nombre es una cadena.
`extraer_licencias_de_bio()` reconoce TREC, DRE, BK/SL de Florida y el genérico
`Lic #`. Los agentes la publican y nadie la estaba mirando.

La comparación de nombre resuelve los casos reales:

- quita el ruido de oficio (`realtor`, `realty`, `homes`, `team`…) antes de
  comparar, si no `"Ana Tapia | Realtor"` no matchea `"Ana Tapia"`;
- separa camelCase: `NancyLopezRealtor` → `nancy lopez realtor`;
- resuelve handles pegados por subcadena: `anatapia01` contiene `ana` y `tapia`;
- exige **dos tokens**, o **uno si es el apellido y tiene ≥5 letras**. Un nombre
  de pila suelto — "Ana" contra "Ana Gómez" — **no alcanza**: hay demasiadas
  Anas.

> **Nota sobre ECOA:** esto es comparación de cadenas entre el nombre que dio la
> fuente y el nombre que la persona puso en su propio perfil. Es identidad, no
> inferencia de nicho. No se compara apellido con origen ni etnia, ni acá ni en
> ningún otro módulo.

Y el patrón de lujo **no** incluye `\bestates?\b`, que matchea "real estate" e
infló el sub-nicho de lujo de ~126 a más de 1.000 filas en una corrida real.
Hay una prueba específica para eso.

### 3 · Captions reales, últimos 30-50 posts, con fecha

`N_POSTS_OBJETIVO = 40`. **El caption crudo se guarda entero**, no solo los
flags: los flags cambian cuando cambian las reglas, el texto no. Un léxico que
hoy no busca "203k" lo va a buscar mañana, y re-scrapear 5.000 perfiles para eso
es absurdo cuando se puede re-derivar.

| Campo nuevo | Módulo | Alimenta |
|---|---|---|
| `caption` completo por post, con `fecha` | `posts.py` | P-Q14 con la evidencia que la matriz exige: ≥10 piezas |
| ratio español/inglés por post y su evolución (`serie_ratio`) | `idioma.py` | distingue intensidad 1 de 2 |
| `menciones` y cuentas etiquetadas | `posts.py` | **S6 gratis** |
| `es_co_marketing` | `posts.py` | S6 + P-Q21 (exposición RESPA) |
| comentarios: texto, idioma, si es del agente | `comentarios.py` | **S8**, que se queda sin Zillow |
| `programas`: FHA, DPA, ITIN, VA, USDA, 203k, crédito | `posts.py` | P-Q01, P-Q07, P-Q17, P-Q19 |
| `tipo`, cadencia, huecos | `posts.py` | P-Q10, J-Q04 |
| engagement real (likes+comentarios ÷ seguidores) | `posts.py` | **R1 verdadero** |
| `geotag` | `posts.py` | S7 sub-estatal |
| `titulos_de_destacadas` | `extraccion.py` | S3, S4 |
| `destino_link_de_bio` | `extraccion.py` | S4 |

#### El umbral de evidencia de la matriz, implementado

P-Q14 exige **≥10 piezas o ≥5 reviews**. Ahora se cuentan y se declara:

```
intensidad_pq14 = 1
regla_pq14 = "contenido bilingue ocasional (3 de 6 piezas validas).
              EVIDENCIA POR DEBAJO DEL ESTANDAR: la matriz exige >=10 piezas
              o >=5 reviews y hay 6 piezas validas"
```

Y con evidencia por debajo del estándar **la intensidad se recorta a 1**, aunque
el ratio diera 2. Con ≥10 piezas válidas y mayoría en español, llega a 2 con
grado E1. La intensidad 3 requiere que la persona lo declare con su propio texto
(E0), y `declara_acompanamiento()` devuelve el **fragmento literal** para que
vaya al dossier como `evidencia_ancla`.

Tres detalles del detector de idioma:

- **Palabras funcionales, no de contenido.** "casa" y "familia" aparecen en
  textos en inglés de agentes latinos: *"Your new casa awaits"* es inglés.
- **Los términos de oficio no cuentan como inglés.** `realtor`, `listing`,
  `down payment`, `closing` aparecen en medio de textos en español.
- **Un caption de emoji es `INDETERMINADO`, no inglés.** El 82,14% de "english"
  salió justamente de tratar la ausencia de señal como inglés.

#### Los comentarios, con la guarda de privacidad implementada

El brief pide que los comentarios se agreguen como perfil de audiencia, que
nunca se perfile individualmente a quien comenta y que no se almacenen sus datos
personales. Está implementado, no prometido:

- **el handle del comentarista no se guarda.** `Comentario.desde_crudo()` es el
  único camino de construcción: usa el handle para compararlo con el del agente
  y lo descarta. `Comentario` no tiene campo de autor, solo
  `autor_es_el_agente: bool`;
- emails, teléfonos, `@menciones` y números largos se **redactan** del texto;
- `verificar_anonimato()` revisa el agregado final y **falla ruidosamente** si
  algo se coló. Es redundante a propósito, y corre antes de guardar en disco;
- máximo 3 ejemplos por fricción: el ejemplo existe para que el BD entienda el
  tono, no para armar un corpus de mensajes de gente que no sabe que los leemos;
- **con menos de 15 comentarios de terceros se reporta pero no activa
  qualifiers.** Tres comentarios no son un perfil de audiencia.

La distinción que hace el módulo: las `@cuentas` que **el agente** etiqueta en
**sus propios captions** sí se guardan — son sus socios comerciales y es
información de negocio. Un tercero que comenta en un post no eligió aparecer en
nuestro CRM.

El léxico de fricción tiene 10 entradas y cada una declara su qualifier:
`enganche` → P-Q07 · `itin_documentos` → P-Q01 · `credito` → P-Q19 ·
`ingreso_no_w2` → P-Q01/P-Q20 · `cuota_mensual` → P-Q06 · `precalificacion` →
P-Q12 · `veterano` → P-Q17 · `proceso_opaco` → P-Q16 · `caso_caido` → P-Q03 ·
`idioma` → P-Q14.

Las dos últimas importan especialmente: **P-Q03 y P-Q16 están entre los cinco
dolores que la referencia 11 declara inalcanzables sin S6 y S8.** Un comentario
que dice "me lo negaron" o "sigo esperando" es evidencia directa, fechada y en
palabras del cliente.

---

## El engagement, que era el otro error

`ig_followers` correlaciona con `units_sold`:

| Medida | r | n |
|---|---|---|
| Pearson, crudo | **+0,0014** | 3.234 |
| Pearson, `log1p` | +0,078 | 3.234 |
| Spearman | +0,075 | 3.234 |

R1 ("propensión a responder") y R3 ("audiencia joven digital") se apoyaban los
dos en seguidores. Ahora `calcular_engagement()` da
`(likes + comentarios) / seguidores` por post, con media y mediana, y **declara
que es insuficiente con menos de 5 posts con datos**. Si falta `likes` o
`n_comentarios`, el post no suma: **no se suma con un cero inventado**.

---

## Límites de tasa y términos de uso

- pausas aleatorias entre posts (2–4,5 s) y entre perfiles (6–12 s);
- **backoff exponencial** de 60 / 180 / 420 s, y solo ante `BLOQUEADO`.
  `NO_ENCONTRADO` no se reintenta: el handle no existe y volver a pedirlo gasta
  cuota;
- los posts y comentarios se leen **una sola vez, para el handle ya elegido**.
  Hacerlo por cada uno de los 5 candidatos multiplicaría por cinco las
  peticiones;
- `BLOQUEADO` es un **resultado legítimo** del pipeline, no un error a
  reintentar en bucle.

---

## Arquitectura: por qué está partido así

Todo lo que **decide** algo es Python puro y tiene pruebas:

| Módulo | Qué decide | Pruebas |
|---|---|---|
| `estado.py` | el estado del perfil | 7 |
| `verificacion.py` | si el handle es de esta persona | 12 |
| `idioma.py` | el idioma y el umbral de evidencia | 11 |
| `posts.py` | programas, cadencia, engagement, red | 13 |
| `comentarios.py` | el perfil de audiencia y su anonimato | 8 |
| **`extraccion.py`** | **nada** — solo toca el DOM | 0, no se puede sin navegador |
| `finder.py` | orquesta | — |

**51 pruebas, 0 fallas.** Corren sin navegador y sin `pandas`:

```bash
python tests/test_instagram.py
```

El motivo de la separación es operativo: cuando algo falle en una corrida real,
la pregunta *"¿es el selector o la lógica?"* se responde corriendo las pruebas.

---

## Lo que entrega al motor de reglas

`SenalesInstagram` en vez de catorce booleanos. Los campos que deciden si
creerle al resto van primero en el CSV:

```
ig_handle · ig_url · ig_estado_perfil · ig_handle_confidence
ig_motivo_estado · ig_razon_confianza
```

Y dos campos que son el reporte de lote de cada fila:

- **`ig_disponibilidad`** — `{señal: bool}` para 13 señales;
- **`ig_motivos_de_ausencia`** — `{señal: por qué falta}`.

`senales_usables` es `False` si el handle no verifica **o** el perfil no se
leyó. El motor de reglas mira eso antes que nada.

`_save()` en `mmi_enricher.py` ya no hardcodea las columnas: las de MMI van
primero, después la cabecera de identidad, después todas las `ig_*` alfabéticas.
Antes, agregar una señal la dejaba fuera del CSV en silencio.

---

## Qué quedó sin resolver

1. **No corrió contra Instagram.** No hay venv en esta máquina: ni `pandas`, ni
   `playwright`, ni `patchright`, ni `requests`. Lo único instalado es
   `openpyxl`. Todos los módulos compilan y las 51 pruebas pasan, pero
   **`extraccion.py` nunca vio un DOM real.**

2. **Los selectores son la parte frágil y no verificada.** Instagram los cambia.
   Cada extractor prueba varias vías y devuelve `None` si ninguna anda —
   `None`, no un valor por defecto — así que un selector roto produce un hueco
   declarado y no un cero. Pero **la primera corrida real va a requerir
   ajustarlos**, y conviene hacerla con `--no-headless --limit 5` mirando la
   pantalla antes de lanzar un lote.

3. **La tasa de verificación real es desconocida.** El 98,1% anterior era falso.
   Cuánto queda con verificación ALTA es una pregunta empírica que se responde
   con la primera corrida. **Mi expectativa es que baje mucho** — y eso es el
   resultado correcto: un handle de confianza baja declarado es mejor que un
   handle equivocado con catorce señales.

4. **Los comentarios cuestan una navegación por post.** Con
   `N_POSTS_PARA_COMENTARIOS = 12`, un perfil son ~52 navegaciones contra ~2 de
   antes. A 3 s de pausa media, unos 3 minutos por realtor. Para 4.249 realtors
   son **~9 días de corrida continua**, que no es viable de una vez. Opciones:
   `--skip-comentarios` para el barrido amplio y comentarios solo para los que
   pasen las compuertas, o bajar `N_POSTS_PARA_COMENTARIOS`. **No decidí esto**:
   depende de cuánto urge el lote y es una decisión de negocio.

5. **`ig_community_type` desapareció.** Estaba en el esquema viejo y lo
   reemplazan `programas` (con su qualifier, conteo, fechas y fragmento
   literal), que es estrictamente más informativo. Si algo aguas abajo lo lee
   por nombre, se rompe. El único consumidor que encontré es `dashboard.py`, que
   igual hay que adaptar.

6. **Las reviews no se tocaron.** La matriz acepta «≥10 piezas **o** ≥5
   reviews», y `perfilar()` acepta `n_reviews`, pero nadie se lo pasa todavía.
   Las reviews vienen de Google Places, que es el [Bloque 2](bloque-2-s8.md).
