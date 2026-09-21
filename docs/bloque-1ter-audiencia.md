# Bloque 1-ter · Perfil de audiencia desde los crudos

Sin red. Todo sale de los JSON que ya están en `ig_raw/`, en una pasada
posterior sobre los mismos archivos.

Módulo nuevo: [`instagram/audiencia.py`](../realtor_scraper/instagram/audiencia.py).
Enchufado en `parsear_crudo`, que sigue siendo la única función que interpreta.

---

## La respuesta a la pregunta que decidía si valía la pena

> ¿Alguno de los ocho perfiles con `captions_es_ratio = 0,0` habla de primera
> compra, crédito o enganche en inglés?

**Seis de ocho.** Con su cita al lado, que es lo que las hace discutibles:

| Perfil | Lo que el sistema anterior veía | Lo que ahora se ve |
|---|---|---|
| `@mybrokerjanie` | `0,0` → descartar | `educacion:3 · enganche:1 · programas_gobierno:1 · mercado_tasas:1`, **educa/anuncia 0,86** |
| `@javierhernandezrealtor` | `0,0` → descartar | `enganche:1` — *«provide you with 5k towards your down payment/closing cost»* |
| `@anakaren_properties` | `0,0` → descartar | `credito:1` — *«worked on his credit. once he was ready he called me»*; `programas_gobierno:1` — *«financing (conventional, fha, va, usda…)»* |
| `@eva.diaz_realestate` | `0,0` → descartar | `primera_compra:2` — *«CLOSED and MOVING IN: First-Time Homebuyers Beat Out Dozens of Offers»* |
| `@therealestatelion` | `0,0` → descartar | `proceso_compra:4`, educa/anuncia 0,57 |
| `@elsajimenezrealtor10` | `0,0` → descartar | ver abajo: es el caso más fuerte de todos |

Dos de los ocho quedaron sin nada (`@gussellz` publica listados y vida
personal; `@arturofloresrealty` tiene ocho captions). Eso también es una
medición, y ahora viene con su denominador.

---

## El campo que más importa · `desajuste_idioma`

Ratio de español en comentarios **menos** ratio en publicaciones. Positivo y
grande = **su audiencia es más latina que su contenido**.

Los 20 del piloto, ordenados:

| Perfil | Desajuste | Publica | Le comentan | `captions_es_ratio` |
|---|---|---|---|---|
| **`@elsajimenezrealtor10`** | **+0,83** | es 0 / en 13 | **es 10 / en 2** | 0,0 |
| `@claudiahernandezrealtormiami` | +0,19 | es 12 / en 6 | es 31 / en 5 | 0,67 |
| `@anakaren_properties` | +0,14 | es 0 / en 19 | es 2 / en 12 | 0,0 |
| `@javierhernandezrealtor` | +0,06 | es 0 / en 19 | es 2 / en 32 | 0,0 |
| `@angelicaesnegocio` | +0,03 | es 17 / en 3 | es 7 / en 1 | 0,85 |
| cinco en 0,00 | | | | |
| `@j_pantojagrp` | −0,26 | es 5 / en 14 | es 0 / en 11 | 0,25 |

**`@elsajimenezrealtor10` es el hallazgo del bloque.** Publica trece veces en
inglés y ninguna en español; le escriben diez comentarios en español y dos en
inglés. El sistema anterior la resumía en `0,0` y la descartaba. Y hay dos
señales independientes que apuntan al mismo lado, capturadas por otros bloques:
su bio dice *«Bilingual Realtor»* y el destino de su enlace de bio es
**`compratucasanc.com`** — un dominio en español.

Tres fuentes distintas, una conclusión: su audiencia le habla en español y ella
publica en inglés. Eso es una conversación comercial concreta, y es distinta de
la de un agente que no atiende ese mercado.

### Dos decisiones sobre este campo, las dos con su motivo medido

**1 · El denominador son las piezas clasificables, no el total.** Es una
desviación deliberada de la fórmula literal del brief, y la razón está medida:
**el 26% de los comentarios del piloto son prácticamente solo emoji.** Un
«Congrats! 🔥🔥🔥» no tiene idioma. Con el total como denominador,
`comentarios_es_ratio` queda diluido por los indeterminados y la resta sale
negativa por construcción — o sea que el campo diría «su audiencia es menos
latina» justo cuando lo que pasa es que su audiencia aplaude con emoji.

Las cuatro columnas de conteo van igual al CSV, así que **la versión con el
total se puede calcular a mano.** Es por eso que van.

**2 · Hace falta una base mínima de 5 piezas clasificables de cada lado.**
Sin ese mínimo el ranking lo encabezaba `@miguelsanchezz7_` con **0,9167**
calculado sobre **un** comentario. Un 0,92 que sale de n=1 es ruido presentado
como señal, y manda a alguien a la conversación equivocada con toda confianza.
Por debajo del mínimo la columna va vacía y los conteos siguen ahí.

---

## La regla que gobierna la salida

**Cada etiqueta lleva el texto que la produjo.** No hay ninguna función en el
módulo que devuelva solo conteos: `Etiquetado.anotar()` es la única vía de
conteo y guarda las dos cosas a la vez, así que un conteo sin cita es
estructuralmente imposible. Hay una prueba que lo verifica en las ocho
familias.

**Nada de puntajes compuestos.** Ninguna columna mezcla señales, y hay una
prueba que falla si aparece una que se llame `score`, `puntaje`, `indice`,
`afinidad` o `latinidad`.

### El bug que la regla de la cita destapó en sí misma

Revisando a mano, la cita de `credito` en `@anakaren_properties` mostraba *«How
I meet my clients?? My marketing strategies vary…»*. Parecía un falso positivo
del léxico.

No lo era. La frase real —*«worked on his credit. once he was ready he called
me»*— estaba **800 caracteres más adelante**, y la cita se guardaba desde el
principio del caption y se recortaba a 200. **En un caption largo la cita no
contenía la frase que produjo la etiqueta**, o sea que la regla que gobierna el
bloque estaba rota, y rota justo en los captions largos — que son los
educativos, que son los que más nos interesan.

Ahora la cita es una ventana centrada en la coincidencia. El texto completo
sigue entero en el derivado.

---

## Los léxicos son bilingües, y eso es verificable

Un léxico que solo detecta en español reproduce el sesgo que este bloque existe
para corregir. `test_todos_los_lexicos_son_bilingues` recorre **cada** entrada
de **cada** léxico y falla si le falta un lado.

La prueba cazó una asimetría real mientras escribía esto: el lado español de
`credito` tenía `\bcredito\b` pelado y el inglés exigía un compuesto de una
lista corta, así que *«credit report»* y *«your credit»* no entraban. El sesgo
de este bloque, en espejo.

| Familia | Etiquetas |
|---|---|
| **A quién le habla** | primera\_compra, inversion, vendedor, obra\_nueva, reubicacion, lujo, militar, renta, refinanciacion |
| **De qué habla** | educacion, credito, enganche, programas\_gobierno, proceso\_compra, listado, celebracion\_cierre, mercado\_tasas, vida\_personal, comunidad |
| **Qué le preguntan** | calificacion, precio, proceso, zona, disponibilidad |
| **Qué señala sin decirlo** | fe, familia, cultura\_latina, idioma\_declarado, + 20 banderas |

`ratio_educa_vs_anuncia` = educa / (educa + anuncia), y lleva sus dos conteos
pegados: `0.8571 (educa 6 / anuncia 1)`. Nueve de diez y noventa de cien son el
mismo 0,9 y no son la misma evidencia.

---

## `registro` · cómo habla

Decide la voz del primer mensaje, que es para lo que existe.

- `@claudiahernandezrealtormiami` → `tuteo:8 | usted:1`
- `@anakaren_properties` → vacío, porque publica en inglés y el tuteo no existe
  en inglés. Vacío correcto, no cero.

El vocabulario regional se reporta como `vocabulario_mx`, `vocabulario_carib`…
y **solo con dos o más marcadores distintos**. La etiqueta dice `vocabulario:` a
propósito: **es una observación sobre palabras, no una afirmación sobre de
dónde es nadie.**

---

## Lo que la revisión a mano corrigió

El brief pedía leer dos perfiles caption por caption antes de escalar. Eso
encontró tres cosas, y dos eran defectos míos.

**1 · El caption de manicura.** *«GEL X EXTRA SHORT ALMOND SHAPE»* quedó **sin
etiqueta**. El brief decía: si quedó como `educacion`, el léxico está mal. No
quedó.

**2 · `barrios_mencionados` estaba inservible.** Mi regla era «entra si aparece
dos veces», y repetirse dos veces no le cuesta nada a la primera palabra de una
frase. Salió esto, presentado como barrios:

```
Locations:13 · Ana Osorio:4 · Claudia:6 · Download:4 · Looking:4 ·
Rent:4 · This:2 · Would:1 · Send:1 · Congratulations:1 · Hispanic:1
```

Entre medio **sí** estaban Logan Square, Pilsen, Uptown, West Loop, Woodlawn,
Doral y Lakeview: la señal existía y el ruido la tapaba. Una columna así es peor
que no tenerla, porque invita a creerle.

Tres cambios, todos hacia precisión:

- **los hashtags se descartan como fuente.** Parecían buenos —quien escribe
  `#LoganSquare` eligió esa etiqueta, igual que un geotag— y la revisión lo
  desmintió: en inmobiliaria son abrumadoramente temáticos. Salieron *Dream
  Home*, *Homes For Sale*, *Real Estate Life* e *Investment Property* como
  barrios, y no hay forma léxica de separar `#LoganSquare` de `#DreamHome`;
- **el aval tiene que estar pegado, no cerca.** Con una ventana de 30
  caracteres entraba *Download* ocho veces, porque el pin estaba en la misma
  línea del CTA: *«Download my free guide 📍 link in bio»*;
- **el nombre del agente se veta.** «Ana Osorio» salía listada como un barrio de
  sí misma. Se usa **solo para excluir**: no alimenta ningún léxico y no produce
  ninguna etiqueta.

Resultado: `Chicago:2 | Chicago, IL:2 | Chicagoland:1 | Garfield Ridge:1 | Logan
Square:1 | Midway:1 | Near North Side:1 | Old Town, Chicago:1`. Queda algún
residuo de una palabra (*Located*, *Julio*), y la columna lleva su cita al lado
para poder descartarlo.

**3 · Y un bug que no era de este bloque.** `Locations` aparecía 13 veces como
si fuera un barrio. Fui a ver de dónde salía:

> **«Locations» apareció 106 veces de unos 180 geotags del piloto** — siete
> veces más que el lugar real más frecuente.

Es el enlace del **pie de página de Instagram**, que apunta a
`/explore/locations/` y está en todas las páginas. El selector
`a[href*='/explore/locations/']` lo agarraba. Se coló en `geotags_top`, una
columna del Bloque 1-bis **ya entregada**.

El geotag de verdad apunta a `/explore/locations/<id>/<slug>/`; el del pie no
tiene id. Eso los separa. Arreglado en el scraper para lo que venga, **y
filtrado en el parser** para que los 20 crudos ya capturados salgan limpios sin
volver a raspar — que es exactamente para lo que se guarda el crudo.

---

## Reglas de guardia, aplicadas

| Regla | Cómo se cumple |
|---|---|
| Etiqueta ausente es **null**, nunca 0 | Las 17 columnas van vacías si `estado_perfil != publico_leido`. Un privado no tiene «cero temas de crédito» |
| Los comentarios se agregan; nadie se perfila | `perfilar_audiencia_1ter` **no recibe el autor**, así que no puede filtrarlo: no lo tiene. Y los textos le llegan ya redactados |
| La cita va sin autor | Por lo de arriba, estructuralmente |
| Ninguna inferencia de origen desde nombres | El nombre entra solo como **veto** de barrios. Hay una prueba que compara con y sin veto y verifica que ninguna otra etiqueta cambia |
| Los marcadores describen contenido | Una bandera cuenta porque se publicó. La cita muestra qué se publicó, que es lo único que se afirma |
| Todo con su denominador | `Etiquetado.denominador`, los conteos de idioma, y `ratio_educa_vs_anuncia` con sus dos términos |

---

## Salidas

**`ig_signals.csv`** — 17 columnas nuevas **al final**, para no mover ni un
índice de lo que la app ya consume. Hay una prueba que lo verifica.

`citas_por_etiqueta` es un JSON en una celda, hasta 3 citas por etiqueta
recortadas a 200 caracteres, cada una **centrada en su coincidencia**.

**`output/ig_audiencia.json`** — las citas completas, sin recortar, con todos
los conteos y denominadores.

Va en **su propio archivo y no dentro de `ig_raw/`**: ese directorio es el
crudo, y hay una prueba que falla si aparece algo derivado adentro. Un derivado
mezclado con su fuente deja de ser re-derivable, que es lo único que este
proyecto puede repetir gratis.

---

## Pruebas

**54 nuevas, 293 en total, 0 fallas.** Sin red, sin navegador, sin pandas.

```bash
python tests/test_audiencia.py
```

Las que vale conocer por nombre:

- `test_todos_los_lexicos_son_bilingues` — la regla del brief, mecánica
- `test_el_realtor_que_habla_de_credito_en_INGLES_no_se_pierde` — el caso que justifica el bloque
- `test_el_mismo_caption_traducido_cae_igual` — la simetría
- `test_la_cita_contiene_la_frase_que_disparo_la_etiqueta` — el bug de la ventana
- `test_un_solo_comentario_no_sostiene_un_desajuste` — el 0,92 con n=1
- `test_el_emoji_no_arrastra_el_desajuste` — por qué el denominador es el de clasificables
- `test_la_basura_que_la_revision_a_mano_encontro_ya_no_entra` — *Would*, *Send*, *Congratulations*
- `test_cerca_de_un_pin_no_es_ser_un_lugar` — *Download* ×8
- `test_el_nombre_del_agente_solo_sirve_para_EXCLUIR`
- `test_un_privado_no_tiene_cero_temas_sino_ninguno`
- `test_no_hay_conteo_sin_cita_en_ninguna_familia`

---

## Qué quedó sin resolver

1. **`barrios_mencionados` sigue siendo heurístico.** Después de tres vueltas de
   precisión quedan residuos de una palabra (*Located*, *Julio*, *Cruceros*).
   Lo que lo arreglaría de verdad es un gazetteer de lugares —el Census tiene
   uno gratis, `place` y `county subdivision`— y eso es trabajo de otro bloque.
   Mientras tanto la columna lleva su cita para poder descartar a ojo.

2. **`vocabulario_*` no disparó en ningún perfil del piloto.** Los términos
   están elegidos por precisión y hacen falta dos distintos. Con 13 perfiles
   legibles no se puede decir si el umbral es correcto o si el léxico es
   demasiado estrecho; el lote grande lo dirá.

3. **El vocabulario regional es la parte más delicada del bloque.** Está
   implementado como observación sobre palabras y así está nombrado, pero si en
   el lote grande resulta que casi no dispara, **conviene sacarlo** en vez de
   dejarlo: un campo que rara vez se llena y que habla de variedades del español
   es más riesgo que información.

4. **`preguntas_recibidas` hereda el resultado del Bloque 2.** Con 396
   comentarios de terceros el piloto dio una sola pregunta clasificada
   (`precio:1`). No es el léxico —acierta 6 de 6 en controles— es que los
   comentarios públicos son felicitaciones. Ver
   [bloque-2-s8.md](bloque-2-s8.md).

5. **`ratio_educa_vs_anuncia` mide piezas, no intención.** Un caption que
   celebra un cierre *y* explica el programa que lo hizo posible cuenta en los
   dos lados. Es lo correcto —habla de las dos cosas— pero el ratio de un
   agente que siempre mezcla queda cerca de 0,5 por construcción, no por
   equilibrio.
