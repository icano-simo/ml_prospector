# Consulta a Model Match sobre la API

**Estado: NO ENVIADA.** Es una comunicación comercial externa; la manda una
persona, con su nombre.

**Actualizada el 2026-09-24** con el inventario exacto de campos que la app
consume hoy. El cambio de fondo respecto de la versión anterior: ya no hay que
preguntar «¿qué tienen?», sino **«¿cuáles de estos devuelve `loans`?»** — la
lista sale del código, no de la memoria.

## Cuándo mandarla

**Mientras la prueba está corriendo y la relación comercial está caliente.** Una
vez que la prueba vence, la conversación empieza desde la posición de quien ya
dijo no.

## Por qué importa: el cuello de botella es el pegado, no el motor

| | |
|---|---|
| realtors en el libro | 4.249 |
| evaluados por el motor | 4.187 |
| **con Model Match capturado a mano** | **46** (1,1 %) |
| con la pestaña Transactions pegada | 41 |
| con veredicto `ok` y ficha redactada | 31 |
| operaciones guardadas | 1.130 |
| condados en la biblioteca de mercado | 4 |

Cada perfil son cinco pestañas abiertas, copiadas y pegadas a mano. El motor
corre sobre 4.187 y la ficha existe para 31: la diferencia entera es captura
manual. **Eso es lo que la API compraría**, y por eso la pregunta que importa
no es de cobertura de datos sino de grano.

## Lo que ya se sabe de la API

Del reconocimiento hecho durante la prueba —mirando el tráfico de la propia
interfaz, no de documentación—:

| | |
|---|---|
| host | `api.modelmatch.com` |
| autenticación | header `x-api-key` |
| recursos | `agents` · `originators` · `loans` · `properties` |
| filtros | planos |
| paginación | por cursor |

**No tenemos llave.** Nada de esto está confirmado contra una respuesta real.

## LA pregunta, antes que las demás

**¿`loans` devuelve las operaciones fila por fila, con el grano de la pestaña
Transactions, filtrables por agente?**

Si la respuesta es sí, la API reemplaza la captura entera y el resto de las
preguntas son de precio. Si devuelve agregados, no nos sirve para casi nada:
todo lo que decide el encaje lo derivamos nosotros de las filas.

Esto **corrige** la versión anterior de esta consulta, que preguntaba si la API
exponía el mix de tipo de préstamo agregado a nivel de agente. Ya no hace falta
que lo agreguen: lo calculamos de las filas. Es una pregunta más barata para
ellos y más útil para nosotros.

### Las 21 columnas que leemos de Transactions

Una fila por operación. Son las que el parser exige completas —21 exactas o la
fila no se lee— y de las que salen el lado, el loan mix, los lenders, la
exclusión y la cobertura de originador:

| # | columna | para qué la usamos |
|---|---|---|
| 1 | Date | ventana, trimestres, «cash provisional» de menos de 35 días |
| 2 | Property Address | **solo ciudad, estado y ZIP**; la calle se redacta al guardar |
| 3 | Home Builder | contexto |
| 4 | Buyers | **no la queremos** (ECOA Reg. B) |
| 5 | Sellers | **no la queremos** (ECOA Reg. B) |
| 6 | Title Company | contexto |
| 7 | Mortgage Amount | financiada vs cash; «Cash» ≠ pagó en efectivo |
| 8 | Down Payment | señal de FHA / DPA |
| 9 | Transaction Type | purchase vs refi |
| 10 | Loan Type | **el mix de programa del agente** |
| 11 | Interest Rate | delata el non-QM |
| 12 | Loan Term | contexto |
| 13 | Loan Officer + NMLS | con quién cierra, y la llave de cruce |
| 14 | Employer + NMLS | **decide la exclusión**: si es de la casa, no se le escribe |
| 15 | Broker | canal |
| 16 | Lender | concentración de wallet y la objeción probable |
| 17 | Sold Amount | volumen y precio mediano |
| 18 | List Amount | contexto |
| 19 | Buyer Agent | **decide el lado** de la operación |
| 20 | Listing Agent | ídem |
| 21 | Co-Listing Agent | ídem |

**Las columnas 4 y 5 preferimos no recibirlas.** Hoy las descartamos al parsear
y redactamos el texto crudo antes de guardarlo, por ECOA Regulation B. Si la
API permite pedir la respuesta sin ellas, mejor para los dos.

## Las preguntas que siguen, en orden

1. **¿Los tres clasificadores de cabecera están en `agents`** — `Producer
   Tier`, `Side Focus` y `Referral Concentration`? El tercero es nuestro S6
   precomputado y es la categoría vacía en casi todos los lotes.

2. **¿Expone el split buyside/listside con volumen, unidades y share para cada
   lado?** Es lo que la interfaz hace mejor que su competencia y lo que
   resuelve la compuerta de encaje.

3. **¿Las métricas de mercado por condado están en la API, o solo en la
   interfaz de Market Signals?** Son ~42 campos por condado y es el activo que
   **no caduca con la prueba**. Hoy los leemos de *Market Signals* con *Set
   Location* bajado a condado:

   - estado del mercado, ventana en meses declarada;
   - applications, approvals, locks (variación %);
   - `Avg Time to Close` en días, `Funded %`, **`Fall Out %`**, Mortgage
     Acquisition Rate;
   - Total Loan Volume y Total Units (del Market Overview, **no** del gráfico
     rodante);
   - Avg Interest Rate, Avg LTV, Avg Loan Term, Avg Credit Score, Avg Household
     Income;
   - First-Time Buyers, Repeat, Veterans, Self-Employed;
   - score: Poor 300-579 / Fair 580-669 / Good 670-739;
   - generación: Millennial, Gen Z;
   - Loan Type Distribution: Conventional, FHA, VA, HE, HELOC, Reverse;
   - Transaction Type: Purchase, Refinance, Construction, Equity;
   - Loan Channel: Banked-Retail, Banked-Wholesale, Correspondent, Brokered,
     Not Labeled;
   - Conforming vs Jumbo, **cada uno con su propio denominador**.

4. **¿Cada respuesta declara su ventana de tiempo?** La interfaz corre sobre
   trailing 14 months y permite configurar desde 2017 en los planes superiores,
   pero **no dice qué ventana está mostrando**, y eso obliga a adivinar el
   grano. Para nosotros, una respuesta sin ventana declarada es una respuesta
   que no se puede citar.

5. **¿Devuelve FIPS de condado, o solo nombre?** Con nombre solo, cruzar es
   ambiguo: hay 31 condados llamados Washington. Ya nos pasó con «Du Page» y
   «De Kalb».

6. **¿Devuelve NMLS del originador y número de licencia del agente?** Son las
   dos llaves de cruce.

7. **¿Los contactos vienen con su porcentaje de confianza, todos?** Guardamos
   también los de confianza baja: el de nuestra lista coincide a veces con un
   secundario, y ese cruce es la única forma de confirmar que es la misma
   persona.

8. **¿Cuál es el límite de llamadas y el modelo de precio** — por llamada, por
   registro, por asiento?

9. **¿Hay endpoint de cambios o webhook**, para no re-descargar todo? Con 4.249
   agentes, la diferencia entre delta y full es la diferencia entre correr
   diario y correr una vez.

## Una observación de método que conviene plantearles

Tres cosas que se detectaron en la prueba y que a ellos les sirve saber, porque
son bugs de presentación y no de dato:

- **Dos definiciones de wallet share en el mismo perfil sin etiquetar.** La
  tarjeta de Overview muestra 33/33/33 y la pestaña Originators 40,6/35,3/24,0
  para el mismo agente. Son por unidades y por volumen respectivamente, pero la
  interfaz no lo dice, así que cualquiera de los dos números se puede citar
  creyendo que es el otro.

- **«Top 3 Concentration 100 %» cuando solo hay 3 operaciones casadas** de 14
  unidades del lado comprador. Leído como concentración de wallet share, es
  exactamente lo contrario de lo que pasa. Un denominador al lado del
  porcentaje lo resolvería.

- **El nombre del agente en el perfil viene cortado a 24 caracteres** y en la
  tabla de Transactions viene entero. «Brayan Valdovinos-sauced» contra «Brayan
  Valdovinos-saucedo»: 25 de sus operaciones quedaron sin lado hasta que lo
  detectamos. Y en otro caso el mismo agente aparece como «Vasquez» en el
  perfil y «Vazquez» en 17 de sus 25 filas.

Plantearlo así, como sugerencias de producto, suele abrir mejor la conversación
de API que pedir precio de entrada.

## Lo que la API no resuelve, y conviene tener claro antes de presupuestar

- **Instagram** es raspado propio y no tiene nada que ver con esto.
- **Salesforce** tampoco.
- Si Market Signals no está expuesto, la biblioteca de condados se sigue
  llenando a mano — hoy tiene 4.
- **La redacción de PII cambia de sitio, no desaparece.** Hoy la calle y los
  nombres de compradores se redactan al capturar, antes de guardar. Por API
  habría que redactarlos al ingerir, con la misma lista blanca.
