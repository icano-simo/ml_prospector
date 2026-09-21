# Bloque 2 · Reemplazo de S8 sin Zillow

**Fecha:** 2026-09-21 · **Estado:** prioridad 1 hecha, prioridad 2 escrita sin
correr, **prioridad 3 evaluada y descartada con evidencia.**

---

## Por qué importa S8

S8 es «fricción declarada»: reviews, quejas, casos caídos, posts de
frustración. La referencia 05 de la skill la marca como **vacía casi siempre**
y como la que **da las aperturas más potentes**.

Y sin ella, cinco de los dolores mejor documentados del corpus **no se pueden
activar nunca**:

| Qualifier | Dolor |
|---|---|
| P-Q02 | latencia del ciclo |
| P-Q03 | caída tardía del contrato |
| P-Q05 | tasación |
| P-Q15 | cobrador de documentos |
| P-Q16 | opacidad del estatus |

Zillow iba a cubrir esto y produjo **cero columnas**.

---

## Prioridad 1 · Comentarios de Instagram · **hecha**

Está en el [Bloque 1](bloque-1-instagram.md), en
[`instagram/comentarios.py`](../realtor_scraper/instagram/comentarios.py).

Un comentario como *«¿cuánto necesito de enganche?»* o *«¿se puede con ITIN?»*
es **evidencia directa del dolor del cliente, en palabras del cliente**, con
fecha. Ninguna otra fuente gratis da eso.

El léxico de fricción tiene 10 entradas, cada una declarando su qualifier. Dos
de ellas son exactamente los dolores que la referencia 11 declaraba
inalcanzables:

| clave | qualifier | qué detecta |
|---|---|---|
| `enganche` | P-Q07 | «cuánto necesito», «down payment», «no tengo para el…» |
| `itin_documentos` | P-Q01 | «ITIN», «sin seguro social», «permiso de trabajo» |
| `credito` | P-Q19 | «mi crédito está malo», «bankruptcy», «foreclosure» |
| `ingreso_no_w2` | P-Q01/P-Q20 | «1099», «cuenta propia», «bank statement» |
| `cuota_mensual` | P-Q06 | «cuánto pagaría», «monthly payment» |
| `precalificacion` | P-Q12 | «cómo empiezo», «por dónde empiezo» |
| `veterano` | P-Q17 | «VA loan», «funding fee», «soy veterano» |
| **`proceso_opaco`** | **P-Q16** | «cuánto tarda», «no me contestan», «sigo esperando» |
| **`caso_caido`** | **P-Q03** | «me lo negaron», «se cayó», «didn't qualify» |
| `idioma` | P-Q14 | «¿hablan español?» |

Con las guardas de privacidad implementadas y probadas: el handle del
comentarista no se guarda, los datos personales se redactan, y con menos de 15
comentarios de terceros se reporta pero **no activa qualifiers**.

---

## Prioridad 2 · Google Places API · **escrita, no corrida**

[`google_places/cliente.py`](../google_places/cliente.py). Places API (New),
oficial y de pago. **No hay muro anti-bot, no hay ToS que lo prohíba y no hay
nada que evadir.** Esa es toda la diferencia con Zillow.

| Campo | Alimenta |
|---|---|
| `rating` + `userRatingCount` | S8 con denominador |
| hasta 5 textos de review | S8 y el dolor del cliente en sus palabras |
| `languageCode` de cada review | **el idioma de los CLIENTES** |
| `publishTime` | fecha, para la cadena de evidencia |

Dos funciones de búsqueda: `buscar_agente()` y `buscar_oficina()`. La oficina
suele tener muchas más reviews que el agente individual — pero son reviews **de
la oficina**: sirven para contexto de fricción y para el idioma de los clientes
del lugar, **no** para atribuirle una queja a un agente concreto.

### El idioma de los clientes vale más que el del agente

La matriz acepta para P-Q14 «≥10 piezas **o** ≥5 reviews». **Cinco reviews es
exactamente el umbral**, así que un lugar con las cinco que devuelve la API
cumple el estándar de la matriz *sin* necesidad de los captions.

Y mide algo distinto: que el agente escriba en español es su posicionamiento;
que sus **clientes** dejen reviews en español es su libro de negocio.

### Tres trampas codificadas

**1 · El denominador de las reviews es 5, no `userRatingCount`.** La API
devuelve como máximo 5 y **las elige Google**: no son una muestra aleatoria.
Con `userRatingCount = 180` y 5 textos, cualquier proporción tiene denominador
5. `pct_reviews_en_espanol()` lo dice explícitamente:

```
60% (3/5 de las reviews devueltas, de 180 totales que tiene el lugar)
```

Es la misma trampa que «Top 3 Concentration 100%» en Model Match.

**2 · La política de Google limita guardar contenido de Places.** El `place_id`
se puede guardar indefinidamente; el resto, no. Por eso
`a_fila_persistible()` devuelve **solo agregados** — conteos, rating, idiomas,
qualifiers — y el texto crudo vive en memoria vía `textos()`. Hay una prueba que
verifica que la palabra de una review no aparece en la fila persistida.

Es la diferencia deliberada con los captions de Instagram, que sí se guardan
enteros porque ahí no hay esa restricción.

**3 · El autor de la review no se guarda.** Igual que en
`instagram/comentarios.py`: `Review.desde_api()` ve el nombre y lo descarta, y
redacta emails y teléfonos del texto.

`rating` ausente es **`None`, no 0**. Un lugar sin reviews no tiene rating cero.

**10 pruebas, 0 fallas**, sin red y sin clave:

```bash
python tests/test_google_places.py
```

**No corrió.** Necesita `GOOGLE_PLACES_API_KEY`, que se saca en Google Cloud
Console habilitando Places API (New). La clave se lee **del entorno**, nunca de
un argumento: un argumento queda en el historial del shell.

---

## Prioridad 3 · Realtor.com · **evaluado, no sobrevive**

El brief pedía evaluarlo *antes* de invertirle tiempo. Lo evalué. **No
sobrevive**, por dos razones independientes y cada una suficiente.

### 1 · Su `robots.txt` prohíbe justo la página que necesitamos

El bloque `User-agent: *` de <https://www.realtor.com/robots.txt> trae **290
directivas**. Entre ellas:

```
Disallow: /realestateagents/*agentname-
Disallow: /realestateagents/*_$
```

La primera es **el perfil individual del agente**, que es donde están el rating
y las reviews — lo único que serviría para S8.

La búsqueda por ZIP (`/realestateagents/{zip}/`), que es lo que raspa
`realtor_com/scraper.py`, **sí** está permitida. Pero solo da el listado: no
trae reviews.

O sea: lo permitido no sirve y lo que sirve está prohibido.

### 2 · HTTP 429 en la primera petición

Sin ninguna petición previa desde esta IP, con User-Agent de navegador:

| URL | resultado |
|---|---|
| `/realestateagents/77036/` | **HTTP 429**, `Server: CloudFront` |
| `/realestateagents/Houston_TX/` | **HTTP 429**, `Server: CloudFront` |

Las dos devolvieron una página intersticial de ~19,6 KB con **cero datos de
agentes**: ni `__NEXT_DATA__`, ni `ld+json`, ni una tarjeta, ni un teléfono, ni
una clave JSON con `rating` o `review`.

### El docstring original decía lo contrario

> «Realtor.com is much less aggressively protected than Zillow.»

Medido, no es cierto. Es el mismo patrón: la escalada de evasión no termina en
datos, termina en más código de evasión. Y acá además hay un `robots.txt`
explícito, que Zillow no tenía como argumento separado.

### Qué hice con el módulo

Le puse ese veredicto en el encabezado del archivo, con los números, para que
nadie lo abra y le invierta una tarde.

**Mi recomendación es borrarlo.** Lo conservé porque el Bloque 0 pedía
conservarlo *hasta evaluarlo*, y la evaluación es ésta. Es una decisión de una
línea y es tuya.

---

## Qué quedó sin resolver

1. **Google Places no se probó contra la API.** Hace falta la clave y habilitar
   Places API (New) en un proyecto de Google Cloud. Las 10 pruebas cubren el
   parseo, la anonimización, los denominadores y la restricción de
   almacenamiento, pero **la forma real de la respuesta no se verificó.** El
   nombre del campo `originalText` contra `text` es el punto más probable de
   ajuste.

2. **No estimé el costo.** Places API (New) cobra por máscara de campos, y
   `reviews` está en la banda caraofrecida. Para 4.249 realtors, con una
   búsqueda más un detalle por cada uno, son ~8.500 llamadas. **Hay que mirar
   el precio vigente antes de lanzar el lote**, y probablemente conviene
   consultar solo a los que pasen las compuertas del motor PACS, no a todos.

3. **La verificación de identidad del lugar no está escrita.** `buscar()`
   devuelve candidatos **sin verificar**, con la misma advertencia que los
   handles de Instagram: el primer resultado no es necesariamente la persona.
   La lógica de verificación de `instagram/verificacion.py` se puede reutilizar
   casi entera —comparación de nombre más señal inmobiliaria, y acá además hay
   dirección y `types` para desambiguar— pero **no lo hice**. Sin eso, las
   reviews pueden ser de otro agente con nombre parecido.

4. **El léxico de fricción no se aplicó a las reviews.** `LEXICO_FRICCION` de
   `instagram/comentarios.py` está escrito para comentarios de Instagram y
   sirve igual para reviews, pero el cableado no está: falta pasar
   `Lugar.textos()` por `perfilar_audiencia()`. Es poco trabajo y no lo hice
   porque sin haber visto una respuesta real de la API preferí no decidir la
   forma del acople.

5. **Las reviews no se conectaron a P-Q14.** `perfilar()` de `instagram.idioma`
   acepta `n_reviews` para el umbral de la matriz, y `Lugar` ya sabe si cumple
   con `cumple_umbral_matriz`, pero nadie pasa el número de uno al otro
   todavía. Misma razón que el punto 4.
