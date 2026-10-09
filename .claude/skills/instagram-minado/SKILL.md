---
name: instagram-minado
description: Manual operativo del MINADO de Instagram a partir de un handle ya conocido — las dos pasadas (crudo a disco, después derivación), lo que se lee del DOM, los seis módulos de señales, las 50 columnas del CSV en su orden exacto de contrato, la regla de privacidad sobre comentarios de terceros y los límites medidos de cada dato. Cárgala ANTES de raspar cualquier lote, antes de tocar `realtor_scraper/instagram/`, antes de leer o filtrar `ig_signals.csv`, y antes de construir cualquier interfaz que lance el raspado. Es prescriptiva: el crudo se guarda antes de derivar, siempre.
---

# Minado de Instagram — manual operativo

**Regla cero: el crudo se guarda antes de derivarlo, y el derivado nunca se
mezcla con la fuente.** Hay una prueba que falla si aparece algo derivado
dentro de `ig_raw/`. Un derivado mezclado con su fuente deja de ser
re-derivable, y re-derivar es la única forma de cambiar una regla sin volver a
raspar 1.200 perfiles.

Este manual cubre la **segunda mitad**: de un handle a las 50 columnas. Cómo se
llega al handle está en `instagram-busqueda`.

Lo que produce son **50 columnas**: 33 del bloque base y 17 del perfil de
audiencia, en `realtor_scraper/output/ig_signals.csv`.

---

## 1 · La arquitectura de dos pasadas, y por qué

```
PASADA 1   --lote      Instagram ──► ig_raw/<handle>.json     (lo caro)
PASADA 2   --parsear   ig_raw/ ──► ig_signals.csv             (lo barato)
```

**Están separadas a propósito.** La pasada 1 cuesta horas y pelea contra
bloqueos; la pasada 2 es Python puro sobre archivos locales y corre en
segundos.

Consecuencia operativa, que es la razón de todo el diseño: **cuando cambia un
léxico, una regla o una columna, se corre solo la pasada 2.** Un léxico que hoy
no busca «203k» lo va a buscar mañana, y re-raspar 5.000 perfiles para eso es
absurdo cuando se puede re-derivar del texto que ya está en disco.

Por eso **se guarda el caption crudo, no solo los flags**: los flags cambian
cuando cambian las reglas; el texto no.

### Reanudable

Hay un checkpoint en `output/ig_checkpoint.json`. Volver a correr la pasada 1
no repite lo hecho. `--desde-cero` lo ignora.

---

## 2 · Qué se lee de Instagram, y a qué ritmo

### Los topes, con su razón medida

| | valor | por qué |
|---|---|---|
| posts por perfil | **30** (`N_POSTS_CRUDO`) | el brief pide 30-50; más arriba Instagram exige scroll infinito y el costo por dato se dispara |
| posts de los que se leen comentarios | los más recientes | abrir cada post es una navegación entera |
| comentarios por post | acotado | suficiente para un perfil de audiencia sin convertir esto en un corpus de mensajes de gente que no sabe que los leemos |

Por DOM, cada post cuesta **~8,5 s**. Es el número con el que se estima un lote.

### Las pausas

| | |
|---|---|
| entre posts | 2,0 – 4,5 s |
| entre perfiles | 6,0 – 12,0 s (y 20-40 s en el lote) |
| tras un scroll | 1,2 – 2,8 s |
| ante bloqueo | backoff exponencial, y después se rinde |

Todas aleatorias dentro del rango, por la misma razón que en la búsqueda: un
ritmo uniforme es una firma.

### Dos trampas del DOM, las dos medidas

⛔ **El enlace de la bio NO es `header a[href^='http']:not([href*='instagram.com'])`.**
Ese selector devolvía el **badge de Threads** (`threads.com/@...`) en 3 de 9
perfiles: no contiene «instagram.com», así que pasaba el filtro. Y peor que un
valor falso: un agente que dice «DM or visit link» probablemente **tiene**
enlace, y nos quedábamos con el badge.

⚠ **`instagram.com` NO va en la lista de dominios excluidos.** `l.instagram.com`
es el envoltorio legítimo del enlace de bio; excluirlo mata el caso bueno —
comprobado poniéndolo y viendo los 13 destinos irse a `None` de golpe.

⛔ **«Locations» no es un geotag.** El enlace del pie apunta a
`/explore/locations/` y dice literalmente «Locations». Salió **106 veces de unos
180 geotags** en el piloto. Está en la lista de textos de interfaz que se
descartan.

---

## 3 · Los seis módulos, en orden de dependencia

| módulo | qué resuelve |
|---|---|
| `estado.py` | los diez estados del perfil. **Nunca `False` donde va `null`** |
| `verificacion.py` | ¿el handle es de esta persona? → `handle_confianza` |
| `idioma.py` | idioma por pieza, con umbral de evidencia |
| `posts.py` | caption crudo + fecha, programas, cadencia, engagement |
| `comentarios.py` | perfil de audiencia **agregado y anónimo** |
| `extraccion.py` | **lo único que toca el DOM** |

Los cinco primeros son **Python puro** y tienen 51 pruebas en
`tests/test_instagram.py`. Eso no es decoración: si una corrida falla, que las
pruebas pasen dice que el problema es **el selector y no la lógica**, que es
la mitad del trabajo de diagnóstico ya hecha.

---

## 4 · La detección de idioma

Se usa **`lingua`, restringido a {español, inglés}**. No es intercambiable.

### Por qué no `langdetect` — medido sobre 17 captions reales

| detector | aciertos |
|---|---|
| langdetect | 15 / 17 |
| **lingua** | **17 / 17** |

Y los dos fallos de langdetect son exactamente el caso que importa:

```
"¡Vendida! 🏡🔑 Felicidades"                      -> portugués, confianza 1.00
"Casa abierta este sabado 🏠 #openhouse #austin"  -> portugués, confianza 1.00
```

**Confianza máxima en el idioma equivocado, así que ningún umbral lo habría
filtrado.** Además langdetect levanta excepción con texto de solo emoji y es
no determinista sin fijar semilla.

La ventaja decisiva de lingua es **poder restringir el espacio de hipótesis** a
español e inglés, que es lo correcto en este dominio y lo que elimina la
confusión con portugués e italiano.

**Costo: ~1 minuto de CPU para el lote completo** (11.307 detecciones/s;
~758.000 detecciones). No es algo a optimizar.

### La historia, para no repetirla

| versión | fuente | método | resultado |
|---|---|---|---|
| 1 | `article img[alt]` — texto que **Meta genera en inglés** | conteo de palabras | **3,29 % en español** en un lote de mercado latino |
| 2 | captions reales | conteo de palabras | mejor fuente, mismo método frágil |
| **3** | captions reales | **detector real** | el actual |

El 3,29 % es el síntoma clásico: un número que parece un dato y es un defecto.

---

## 5 · La regla de privacidad sobre comentarios — no es negociable

**Nunca se perfila individualmente a quien comenta, y no se almacenan sus datos
personales.** Los comentarios entran como **agregado**: cuántos preguntan por
enganche, en qué idioma, si responde el agente. **Nunca quién preguntó.**

Está **implementado, no prometido**:

- `Comentario.autor_es_el_agente` es un **booleano, no un handle**;
- el handle del comentarista **se descarta en el constructor**;
- las `@menciones` dentro del comentario **se redactan**;
- el texto se guarda **solo si pasa el filtro de anonimato**;
- correos y teléfonos que alguien dejó en un comentario **se redactan
  siempre**.

### La distinción que hay que entender

| quién | qué | ¿se guarda? |
|---|---|---|
| **el agente**, en **sus propios captions** | las `@cuentas` que etiqueta | **sí** — son sus socios comerciales, es información de negocio |
| **un tercero**, comentando | su handle | **no** — no eligió aparecer en nuestro CRM |

`comentarios_redactados` es el **log de auditoría** de esa redacción: si un
lote redacta mucho, alguien tiene que enterarse de que la gente está dejando su
teléfono en los comentarios.

---

## 6 · Las 50 columnas, en su orden exacto

⚠ **El orden es contrato con la app que consume el archivo. No se reordenan ni
se renombran sin avisar.** Las 17 de audiencia van **al final**, después de
todo lo anterior, para no mover ni un índice de lo que ya se consume.

### A · Identidad y estado — 6

| # | columna | qué es |
|---|---|---|
| 1 | `email` | la llave con la que se cruza contra nuestra base |
| 2 | `nombre` | el de la fuente, no el del perfil |
| 3 | `estado` | el estado de EEUU |
| 4 | `handle` | el handle verificado |
| 5 | `estado_perfil` | uno de los **nueve** valores — ver `instagram-busqueda` §5 |
| 6 | `handle_confianza` | `alta` · `media` · `baja`. **Con `baja`, las señales no se usan** |

### B · Volumen de evidencia — 4

| # | columna | qué es |
|---|---|---|
| 7 | `captions_n` | cuántos captions se leyeron de verdad |
| 8 | `captions_es_ratio` | proporción en español |
| 9 | `comentarios_n` | cuántos comentarios se agregaron |
| 10 | `comentarios_es_ratio` | proporción en español |

⚠ **`captions_n` es el denominador de todo lo demás.** Un `menciona_fha = false`
con `captions_n = 2` no dice que no hable de FHA: dice que se leyeron dos
posts.

### C · Programas y temas detectados — 7

| # | columna |
|---|---|
| 11 | `menciona_lender` |
| 12 | `menciona_itin` |
| 13 | `menciona_dpa` |
| 14 | `menciona_credito` |
| 15 | `menciona_va` |
| 16 | `menciona_fha` |
| 17 | `menciona_primera_casa` |

Salen de léxicos **bilingües**. Un léxico que solo detecta en español
reproduce el sesgo que este sistema corrige, y **hay una prueba que recorre
cada entrada de cada léxico y falla si no tiene al menos un patrón en español y
uno en inglés**.

### D · Señales de audiencia y co-marketing — 3

| # | columna | qué es |
|---|---|---|
| 18 | `comentarios_pregunta_calificacion` | terceros preguntando por requisitos. **Es evidencia directa del dolor del cliente, en sus palabras** |
| 19 | `cuentas_hipotecarias_etiquetadas` | cuentas que **parecen** de hipotecas |
| 20 | `posts_comarketing` | posts en co-marketing |

⚠ **`cuentas_hipotecarias_etiquetadas` es una PISTA, no un hecho.** Hay que
confirmarla contra NMLS antes de escribirla en un dossier: **el handle de
alguien no prueba su oficio.**

### E · Ritmo y alcance — 4

| # | columna | qué es |
|---|---|---|
| 21 | `tipo_post_reel_pct` | qué parte son reels |
| 22 | `dias_entre_posts_mediana` | cadencia |
| 23 | `hueco_max_dias` | el silencio más largo |
| 24 | `engagement_rate` | (likes + comentarios) ÷ seguidores |

### F · Contexto del perfil — 3

| # | columna |
|---|---|
| 25 | `designaciones` |
| 26 | `destacadas_titulos` |
| 27 | `geotags_top` |

### G · El texto crudo — 5

| # | columna | qué es |
|---|---|---|
| 28 | `captions_texto` | **los captions enteros** |
| 29 | `comentarios_texto` | comentarios de terceros, **redactados** |
| 30 | `comentarios_del_agente` | lo que respondió él |
| 31 | `texto_truncado` | si se cortó por tope de celda |
| 32 | `comentarios_redactados` | **qué se redactó y cuántas veces** |

**Excel aguanta 32.767 caracteres por celda; acá se corta en 30.000 y se
declara.** Un corte silencioso haría que un análisis sobre el texto diera
menos de lo que hay sin que nadie lo notara.

### H · La bandera de muestra corta — 1

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

---

## 7 · Las dos reglas que gobiernan el bloque de audiencia

### Cada etiqueta lleva el texto que la produjo

**Si el sistema dice `credito:4`, tiene que poder mostrar las cuatro frases.**
Conteo y cita, siempre juntos — por eso `etiquetar()` no devuelve un dict de
números sino un `Etiquetado` con los dos, y **por eso no existe ninguna función
que devuelva solo conteos**. Esas citas son la columna 50,
`citas_por_etiqueta`.

### Nada de puntajes compuestos

⛔ **No hay «audiencia latina: 7,3» en ningún lado.** Un número así no se puede
discutir ni verificar, y esconde de dónde salió.

### Por qué existe este bloque

El problema que resuelve, dicho con el caso real que lo motivó: un realtor que
publica **en inglés** sobre primera compra, ayuda de enganche y crédito salía
con `captions_es_ratio = 0,0` y se descartaba — **y es exactamente nuestro
cliente, en otro idioma**.

**El idioma es un atributo del público, no un requisito de entrada.**

La prueba de que el dato estaba ahí es un caption del piloto: *«Mucha gente
cree que su puntaje de crédito no es lo suficientemente bueno para comprar una
casa»*. En inglés, el sistema anterior no lo veía.

### Sobre los marcadores culturales

⚠ **Describen el CONTENIDO que la persona publicó, no a la persona.** Que un
caption lleve una bandera de Guatemala dice que eso se publicó; **no dice de
dónde es quien lo publicó**, y no se usa para inferirlo. **No hay ninguna
inferencia de origen ni de etnia desde nombres**, ni del agente ni de quien
comenta.

---

## 8 · Cómo se ejecuta

```
python -m instagram.finder --lote            # pasada 1: raspa y guarda crudo
python -m instagram.finder --parsear         # pasada 2: crudo -> CSV
```

| bandera | efecto |
|---|---|
| `--posts N` | posts por perfil (por defecto 30; ~8,5 s cada uno) |
| `--sin-comentarios` | salta la lectura de comentarios |
| `--desde-cero` | ignora el checkpoint |
| `--limite N` | corta el lote |
| `--con-ventana` | navegador visible |

---

## 9 · Dónde queda cada cosa

| qué | dónde |
|---|---|
| el crudo, uno por perfil | `output/ig_raw/<handle>.json` |
| el checkpoint | `output/ig_checkpoint.json` |
| **la salida** | `output/ig_signals.csv` |
| los derivados con citas completas | el JSON derivado, **nunca `ig_raw/`** |
| el manifiesto del lote | `output/ig_manifiesto.json` |

⛔ **Nada de esto se versiona.** Lleva texto de cuentas personales y
comentarios de terceros. El repo es público.

---

## 10 · Los límites que hay que decir al leer el CSV

- **`captions_n` manda sobre todo lo demás.** Cualquier `false` con pocos
  captions es «no se vio», no «no hay».
- **`handle_confianza = baja` invalida la fila entera** para señales de
  contenido. El handle sirve para revisión manual; sus señales no.
- **`paginacion_truncada = true` vacía `captions_es_ratio` a propósito.**
- **`estado_perfil != publico_leido` significa que no hay contenido legible**,
  y el valor concreto dice si el problema es de la persona (`privado`, `vacio`)
  o nuestro (`handle_equivocado`, `muro_de_sesion`).
- **Las cuentas hipotecarias etiquetadas son una pista sin confirmar.**
- **Los marcadores culturales describen publicaciones, no personas.**

---

## 11 · Lo que esta capa NO hace

- **No saca contactos de Instagram.** Teléfono y correo salen del módulo de
  identidad y de los insumos privados.
- **No perfila a quien comenta.**
- **No infiere origen, etnia ni estatus** de nadie, ni por nombre ni por
  contenido.
- **No puntúa.** Produce señales; el scoring es otra capa.
- **No usa Zillow.** Retirado el 2026-09-21: cero columnas producidas y sus
  términos prohíben el scraping.
