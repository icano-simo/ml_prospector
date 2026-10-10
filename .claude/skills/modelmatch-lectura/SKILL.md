---
name: modelmatch-lectura
description: Cómo leer y usar la extracción de Model Match de este repo — el Excel de realtors, qué significa cada campo, qué NO se puede concluir de él, y cuánto cuesta cada llamada a la API. Cárgala antes de interpretar `data/salida/realtors_instagram_model_match.xlsx`, antes de escribir o modificar cualquier cosa en `modelmatch/`, y antes de pedirle datos nuevos a la API de Model Match. Contiene el modelo de costo medido y las trampas de porcentajes y ventanas, que no se pueden re-derivar del dato.
---

# 4 de 4 · LECTURA DEL RESULTADO — cómo se lee y cómo se amplía

> **Los cuatro manuales de este repositorio.** Se leen en este orden, que es
> el del flujo: cada uno produce lo que el siguiente consume.
>
> | | manual | qué cubre |
> |---|---|---|
> | 1 | `instagram-scraping` | **SCRAPER** · del nombre o del handle a las 50 columnas |
> | 2 | `modelmatch-minado` | **MINADO MODEL MATCH** · de un realtor a sus 64 columnas, con el tope de 1 crédito |
> | 3 | `instagram-modelmatch-union` | **UNIÓN** · las dos capas en un libro de 130 columnas |
> | **4** | **`modelmatch-lectura`** | **LECTURA** · cómo se interpreta y qué NO se puede concluir ← **estás aquí** |
>
> ⚠ **Éste es el más viejo de los cuatro y el que no tiene verificador
> automático.** Los otros tres se comprueban contra el código
> (`verificar_manual.py` y `verificar_manuales_ig.py`) y fallan si se
> desfasan; éste no, así que ante una contradicción **mandan los otros
> tres**. Hay una discrepancia conocida, sobre `Nº emails` y `Nº teléfonos`,
> documentada en `modelmatch-minado` §4·D.

Qué hay: los realtors a los que se les encontró Instagram, cruzados contra
Model Match. Una fila por realtor en
`data/salida/realtors_instagram_model_match.xlsx`, hoja *Realtors*.

**Los datos no están en git** (`data/` está ignorado): traen nombre, correo y
teléfono de personas reales y este repo es público. En el repo está el código
que los produce, no los datos. **Tampoco pongas nombres de realtors en el
código ni en los docstrings**, ni siquiera como ejemplo: ya pasó una vez, con
el agravante de que el ejemplo decía además con qué lender trabajaba esa
persona.

## Dónde está cada cosa

| | |
|---|---|
| Lista de campos, autoritativa | `modelmatch/a_excel.py`, tabla `COLUMNAS` |
| Diccionario para humanos | hoja *Diccionario de campos* del Excel |
| Cómo interpretar | hoja *Cómo interpretar*, la segunda del libro |
| Cliente de la API | `modelmatch/cliente.py` |

**El diccionario se genera de `COLUMNAS`, no se escribe aparte.** Si agregas un
campo, agrega su descripción en la misma tupla; el generador avisa de los que
quedan mudos. No hagas una lista paralela: se desfasa y entonces el archivo
dice que tiene unos campos y tiene otros.

## El modelo de costo, medido contra el ledger

No está documentado por el proveedor. Esto se midió leyendo `balance.total`
antes y después de cada llamada:

| llamada | costo |
|---|---|
| `POST /v1/instant-search` | **0** |
| `GET /v1/agents/count`, `POST /v1/loans/count` | **0** |
| `GET /v1/agents/{id}` | 1 |
| `POST /v1/agents` (lista) | **1 por fila devuelta** |
| `/v1/agents/{id}/breakdowns/{lenders,originators,companies,counties}` | **1 por fila** |
| `/v1/agents/{id}/sales`, `/properties`, `/related` | 1 por fila |
| bulk delivery | 1 por fila |

**La regla es: se cobra lo que devuelve filas.** Lo que devuelve un número es
gratis. Eso se descubrió tarde y costó ~700 créditos en banderas que se
podrían haber sacado contando.

Dos consecuencias prácticas:

- **Antes de listar, cuenta.** `count` es gratis y dice si vale la pena.
- **El costo de un breakdown se sabe antes de pedirlo:**
  `totalLendersWorkedWith`, `totalOriginatorsWorkedWith` y
  `totalCompaniesWorkedWith` vienen en la ficha y **son** el número de filas
  de cada breakdown.

El saldo se lee en `GET /v1/me/credits`, gratis. Usa `balance.total`:
`usage.spent` va con retraso y no se mueve aunque el saldo baje.

## Las trampas que ya costaron dinero o una conclusión falsa

**1 · Ningún porcentaje de esta API significa lo que parece hasta comprobarlo.**
Van tres:

- `footprint.product.shareOfUnits` con `dimension: lender` mide la proporción
  *dentro de un bucket de lender*, no la del agente. Un agente con 20 % de FHA
  real aparece en la banda «≥50 %». Se gastaron 503 créditos en descubrirlo.
- `pctUnits` del breakdown de originadores llegó a **167 %**: su denominador
  no son las operaciones del agente. Las unidades hipotecarias se miden aparte
  de las de venta y pueden ser más.
- En cambio `footprint` con un **lender explícito** y `units: {gte: N}` sí
  significa «N operaciones financiadas por ese lender». La diferencia es que
  ahí el bucket es el que se quiere medir.

**Antes de usar cualquier porcentaje, contrástalo con un caso del que ya se
sepa la respuesta por otra vía.** Los scripts de este paquete lo hacen solos y
avisan cuando no cuadra.

**2 · La ventana cambia la respuesta, a veces por un factor de tres.** La
exclusión por Everett da 28 realtors a 24 meses y 79 a historial completo. Para
una exclusión va `allTime`. Cita siempre el número con su ventana.

**3 · Un negativo puede ser que la pregunta no podía verlo.** La conclusión
«la pestaña Transactions no se puede reconstruir» estuvo mal varias semanas:
se había probado `/v1/sales` con filtros y `/v1/related`, pero no las rutas
colgadas del agente, que sí existen. Cuando algo no aparezca por varias vías,
sospecha de las vías antes de concluir que no está.

**4 · Los nombres de lenders vienen crudos y con faltas de ortografía.** La
lista de ids de la casa está en `modelmatch/everett.py`, con las variantes
comprobadas contra `instant-search` y —tan importante como eso— con las que
**no** son la casa: hay bancos de la ciudad de Everett y una persona apellidada
Everette. También hay otras empresas con «Supreme» en el nombre que no tienen
nada que ver.

**5 · PostgREST corta en ~1000 filas y no avisa.** Pagina siempre al leer de
Supabase.

## Model Match manda sobre MMI

**Los datos de MMI están viejos, y está medido:** una cuarta parte de los
realtors había cambiado de inmobiliaria. Cuando una columna `(MMI)` y su gemela
`(MM)` discrepen, vale la de Model Match.

- `R6` (brokerage con identidad latina) del modelo de scoring se estaba
  calculando sobre la oficina anterior en esa cuarta parte.
- Para producción usa la de Model Match; la de MMI solo sirve para ver cuánto
  se había corrido.
- Para contactar: teléfono, ciudad y brokerage de Model Match. Con el correo
  prueba los dos, porque cada fuente conserva uno distinto.
- **Vacío en Model Match no es «no tiene», es «no lo sabe».** La licencia solo
  está en la mitad de los agentes.

## Lo que Model Match permite dejar de suponer

- `mortgagedBuyerUnits` son las veces reales que el realtor puede presentar un
  prestamista. Es mejor insumo para `R2` que las unidades totales.
- `totalOriginatorsWorkedWith` **mide** la captividad. La regla vieja la
  infería del volumen («sobre 60 unidades ya tiene lender cautivo») y eso
  falla en los dos sentidos.

## Identificar a una persona sin adivinar

El orden importa y está implementado en `modelmatch/extraer.py`:

1. **Correo exacto** contra el que ya teníamos. Es llave dura.
2. **Nombre exacto + estado.** El nombre solo no alcanza: hay homónimos en
   otros estados, y `instant-search` es difuso.
3. **El teléfono se comprueba después**, contra la ficha, porque la búsqueda
   no devuelve teléfonos. Confirma una identificación floja; y si contradice,
   manda el caso a revisión.
4. **Si nada alcanza, no se inventa:** la fila queda marcada con los
   candidatos que devolvió la API para decidir a mano.

Un teléfono distinto **no** contradice un correo que coincide: Model Match
suele tener el de la oficina y nosotros el celular.

## Reglas de uso

- Es información comercial sobre **profesionales inmobiliarios**. No se usa
  para decidir nada sobre un consumidor ni sobre su crédito.
- Que un realtor trabaje con la casa es contexto para no pisarle el cliente a
  un colega. Nunca un gancho de venta.
- **Nada de property enrichment.** Es skip-trace de dueños de propiedad: PII de
  consumidor, 10 créditos por match. El cliente revienta antes de salir a la
  red si la ruta lo menciona.
- La llave de la API vive en `.env`. No se escribe en código ni se pega en un
  chat.
