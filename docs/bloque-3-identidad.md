# Bloque 3 · Identidad

**Fecha:** 2026-09-21 · **Estado:** el módulo está hecho y probado (35 pruebas).
La extensión de estados **cambia de prioridad respecto del brief**, y abajo está
por qué, con medición.

---

## El módulo · no un merge por nombre

El brief lo pide explícito: *«Módulo propio, no un merge por nombre.»*

Un merge por nombre parece funcionar porque produce filas. Lo que no produce es
la información de **cuánto confiar en cada fila**, y ésa es la única cosa que
distingue un registro unificado de un registro inventado.

Cuatro archivos en [`identidad/`](../identidad/):

| Archivo | Qué hace |
|---|---|
| `normalizacion.py` | las llaves de cruce: E.164, email, nombre, licencia |
| `valores.py` | valores versionados con fuente y fecha. **Nada se sobrescribe** |
| `cascada.py` | la cascada de cruce con `match_confidence` y log de conflictos |
| `registro.py` | el registro unificado |

### La cascada, y por qué el último escalón no alcanza

```
licencia estatal → teléfono E.164 → email → nombre + condado + rango de volumen
```

| `match_confidence` | Cruce | Vale para |
|---|---|---|
| **CIERTO** | licencia estatal | todo, incluido escribirle |
| **ALTO** | teléfono o email, **con nombre compatible** | todo |
| **MEDIO** | teléfono o email **sin** nombre compatible | enriquecer, no contactar |
| **BAJO** | nombre + condado + rango de volumen | cola de revisión manual |
| **NINGUNO** | no hubo cruce | nada |

El corte está en MEDIO: por debajo **no se le escribe**. Un toque humano sobre
un registro mal unido se pierde dos veces — gasta el toque y ensucia el dato.

Tres decisiones que importan y están probadas:

- **Dos licencias distintas del mismo estado → `NINGUNO`**, aunque el nombre
  coincida exacto. No es la misma persona, y el nombre no puede ganarle al
  registro de gobierno.
- **Teléfono igual sin nombre compatible → `MEDIO`, no `ALTO`.** Puede ser un
  teléfono de oficina compartido. Sirve para enriquecer, no para escribirle
  como si fuera esa persona.
- **Dos candidatos que cruzan con la misma confianza (y no es CIERTO) →
  `NINGUNO`.** Si el cruce no distingue, elegir uno por orden de aparición es
  inventar.

### El volumen se compara como rango, no como cifra

`TOLERANCIA_UNIDADES = 0.35`. La razón está medida: en el lote de 4.249 filas,
**689 marcaban exactamente 9 y 679 marcaban 10.** Eso no es distribución
natural, es un bucket de la fuente. Tratarlo como cifra exacta rompe cruces
legítimos.

### Nunca se sobrescribe un campo

`Campo.agregar()` acumula; nada borra. Y esto no es purismo:

> **Model Match entrega varios emails y teléfonos con porcentaje de confianza, y
> el de nuestra lista puede coincidir con uno secundario.**

Si el pipeline se queda con el de mayor confianza y descarta el resto, pierde el
único cruce que confirmaba identidad. Hay una prueba con tres emails de
confianza 92%, 31% y 15% que verifica que los tres sobreviven.

Al revés también: un teléfono que MMI dice `+15125550100` y el board dice
`+15125550199` **no es un dato mejor**, es una pregunta abierta. Y una pregunta
abierta guardada como un solo valor es una respuesta inventada.

`LogDeConflictos` es un **entregable**, no un log de debug. Su nota dice:

> un conflicto no se resuelve promediando ni quedándose con el de mayor
> confianza: es una pregunta abierta.

Y los conflictos se acumulan **incluso cuando el cruce es CIERTO**: dos fuentes
que coinciden en licencia y difieren en teléfono son la misma persona con un
teléfono en disputa, y eso hay que saberlo.

### La confianza del cruce pone techo a la del dato

Un email con 99% de confianza declarada que llegó por un cruce `BAJO` no puede
valer más que el cruce. Los techos son 1,00 / 0,85 / 0,60 / 0,35. Hay prueba.

### Normalización: cuatro detalles que cambian el resultado

**E.164.** El mismo número aparece como `+1 (512) 522-0477`, `5125220477`,
`512.522.0477` y `1-512-522-0477`. Un cruce por teléfono sin normalizar **no
encuentra nada y no falla**: devuelve cero coincidencias, que se lee como «no
está en la otra fuente». Se validan además los prefijos del NANP: un número que
empieece en 0 o 1 no existe, y `1111111111` es relleno.

**Email: no se quitan los puntos.** En Gmail `a.b@x.com` y `ab@x.com` son el
mismo buzón; en un dominio corporativo **son dos personas distintas**.
Normalizar de más une a quien no hay que unir.

**Licencia: no se quitan los ceros a la izquierda.** En California `01998877` y
`1998877` son cadenas distintas y el board publica la primera.

**Clave de nombre ordenada alfabéticamente.** `"TAPIA, ANA"` y `"Ana Tapia"` dan
los dos `ana|tapia`. Es como vienen las dos mitades de casi todo export de
gobierno.

---

## La extensión de estados · el brief pide la prioridad equivocada

El brief pide *«extiende cobertura más allá de TX y FL, priorizando CA, AZ, NV e
IL»*. Medí dos cosas y las dos apuntan en contra.

### Razón 1 · CA y AZ no tienen capacidad para atender la demanda

Del cruce del [Bloque 5](bloque-5-modelmatch.md) sobre
`Loan_Officers_Licencias.xlsx`, aplicando la regla de la referencia 09 (un LO
cuenta como **local** solo si está licenciado en 5 estados o menos):

| Estado | LOs activos | LOs **locales** | Lectura |
|---|---|---|---|
| **CA** | 2 | **0** | cobertura nominal |
| **AZ** | 1 | **0** | cobertura nominal |
| **NV** | 2 | 1 | delgada, pero real |
| **IL** | 4 | 1 | media con un solo local |

**Minar realtors en California y Arizona hoy produce demanda que no podemos
atender**, que es exactamente lo que la referencia 09 llama un pasivo: *«un
realtor activado y perdido cuesta más que uno nunca contactado: consumió la
credibilidad y la devolvió deteriorada.»*

### Razón 2 · ninguno de los cuatro publica un dataset consultable

Probé los portales de los cuatro:

| Estado | URL probada | Resultado |
|---|---|---|
| CA | `www2.dre.ca.gov/PublicASP/pplinfo.asp` | 200, **formulario de búsqueda**, cero enlaces a archivos |
| CA | `dre.ca.gov/Licensees/LicenseeLists.html` | **404** (URL supuesta, no existe) |
| AZ | `azre.gov/public-database` | **403** |
| NV | `red.nv.gov/Licensees/Licensee_Lists/` | 200, **247 bytes**, cero enlaces |
| IL | `idfpr.illinois.gov/profs/licenselookup.html` | **404** |

Los cuatro exigirían raspar formularios, que es la misma apuesta que perdimos
con Zillow y con Realtor.com.

### Y hay tres estados que SÍ publican API, y sí tienen cobertura real

Buscando en el catálogo Socrata federado apareció otra cosa. **Verificado contra
el API el 2026-09-21:**

| Estado | Dataset | Filas | LOs activos / locales |
|---|---|---|---|
| **NY** | `data.ny.gov/yg7h-zjbf` | **147.111** | 2 / 1 |
| **CO** | `data.colorado.gov/4zse-6bnw` | **110.118** | 3 / 1 |
| **CT** | `data.ct.gov/7y8e-cawe` salespersons | **97.438** | 4 / 2 |
| **CT** | `data.ct.gov/fwpc-pgqj` brokers | **21.801** | 4 / 2 |

API paginada, filtros SoQL del lado del servidor, esquema estable, sin muro y
sin nada que evadir. Es estrictamente mejor que lo que `trec.py` y `dbpr.py`
hacen hoy.

**Y también apareció TX:** `data.texas.gov/s7ft-44qi`, *«Broker and Sales Agent
License Holder Information»* — el padrón de TREC como dataset, en vez del
formulario que `trec.py` raspa. **No lo pude consultar** desde esta máquina:
`SSL: CERTIFICATE_VERIFY_FAILED`, que es el almacén de certificados local y no
el servidor. Queda marcado `verificado=False` y con el **esquema sin mapear a
propósito**: mapear a ciegas produce columnas vacías.

### Mi recomendación

**Cargar NY, CO y CT primero**, que son gratis, estables y donde sí podemos
originar. Y verificar el dataset de Texas, porque reemplazaría el scraping que
ya tenemos.

CA y AZ **después de resolver la cobertura de loan officers**, no antes. Y antes
de tramitar licencias nuevas conviene medir la métrica de tensión
(`MQL del estado ÷ LOs activos`) sobre **MD (19 activos / 14 locales), VA (18/13)
y FL (18/13)**: si sale bajo 4, hay capacidad ociosa y minar ahí convierte
capacidad ya pagada en pipeline sin contratar a nadie ni tramitar una licencia.

> Esto es una recomendación, no una decisión. Si la prioridad comercial de CA y
> AZ viene de algo que no está en los datos que vi, el orden es tuyo y el
> módulo soporta cualquiera: agregar un estado es una entrada en `FUENTES`.

---

## `state_licenses/socrata.py`

Dos trampas de estos datasets, codificadas:

**1 · El padrón incluye residentes de otros estados.** En el de Colorado, el
primer registro es alguien con dirección en **San Diego**. Una licencia de
Colorado no significa que la persona opere en Colorado, y filtrar por el `state`
del domicilio descarta a quien vive en la frontera y trabaja del otro lado. Se
guarda el domicilio y se declara; no se filtra por él.

**2 · El de Colorado mezcla tipos de licencia.** `licensetype` incluye
**«Mortgage Loan Originator»** junto con las inmobiliarias.

Eso es un regalo: un MLO con licencia inmobiliaria del mismo estado es
exactamente el caso de **doble licencia que la metodología manda descartar como
prospecto** (regla 7: «Descarta como prospecto a quien tenga NMLS o doble
licencia propia: origina él mismo»). Así que el cargador **no los descarta: los
marca** con `es_originador=True` y los cuenta aparte.

Pero si alguien carga ese dataset sin filtrar, el padrón «de realtors» trae
originadores. `ResultadoDeCarga.resumen()` imprime los cuatro conteos:
descargados, descartados por tipo, descartados por ser entidad y no persona, y
marcados con doble licencia.

CT brokers trae `type = LIMITED LIABILITY COMPANY`: **son entidades, no
personas**, y si no se filtran quedan como prospectos con nombre de empresa.

---

## Qué quedó sin resolver

1. **Nada se cargó.** Los datasets se verificaron (esquema, conteo de filas, una
   fila de ejemplo) pero **no se descargaron**: son ~376.000 filas entre los
   tres estados y el pipeline que las consumiría necesita `pandas`, que no está
   instalado acá.

2. **El dataset de Texas no se verificó**, por el problema de certificados
   local. Su esquema quedó sin mapear a propósito. **Es el de mayor valor
   inmediato**, porque reemplazaría el scraping de `trec.py`.

3. **CA, AZ, NV e IL siguen sin resolver.** Lo que encontré es que no hay camino
   fácil. Las opciones reales, en orden de sensatez:
   - **pedir el padrón por solicitud de registro público** a cada board — es
     gratis, legal y da un archivo completo, y es lo que hacen `main.py` y
     `file_processor.py` para TX y FL hoy;
   - raspar los formularios, que es la apuesta que ya perdimos dos veces;
   - comprar la lista.

   No decidí por vos: la primera es claramente la mejor y **requiere que una
   persona escriba el pedido**, no código.

4. **`file_processor.py` no se tocó.** Procesa los CSV descargados a mano de TX y
   FL. `socrata.py` es un camino paralelo, no un reemplazo, y **no están
   unificados**: cargar TX por los dos caminos produciría duplicados que sólo la
   cascada de identidad resolvería. Falta un cargador único por encima.

5. **La cascada no se corrió contra datos reales.** Las 35 pruebas usan casos
   construidos, incluidos los números medidos del lote (el bucket de 9 y 10
   unidades). **Cuántos registros cruzan a nivel CIERTO contra cuántos caen a
   BAJO es una pregunta empírica** y es el número que dice si esta capa sirve.
   Mi expectativa: pocos a CIERTO hasta que existan los padrones estatales,
   porque hoy el lote no trae número de licencia.

6. **El NMLS no se cruza contra nada.** `RegistroUnificado.marcar_nmls()` existe
   y descarta correctamente, pero **nadie lo llama**: hace falta la fuente de
   NMLS. El dataset de Colorado la trae gratis para ese estado (los MLO están en
   el mismo padrón), y el registro nacional del NMLS Consumer Access es la
   fuente general. No lo conecté.
