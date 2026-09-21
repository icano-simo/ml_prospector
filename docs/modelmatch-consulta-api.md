# Consulta a Model Match sobre la API

**Estado: NO ENVIADA.** Es una comunicación comercial externa; la manda una
persona, con su nombre.

## Cuándo mandarla

**Mientras la prueba está corriendo y la relación comercial está caliente.** Una
vez que la prueba vence, la conversación empieza desde la posición de quien ya
dijo no.

## Lo que ya se sabe de la API

Del reconocimiento hecho durante la prueba:

| | |
|---|---|
| host | `api.modelmatch.com` |
| autenticación | header `x-api-key` |
| recursos | `agents` · `originators` · `loans` · `properties` |
| filtros | planos |
| paginación | por cursor |

## Las preguntas que importan, en orden

Las tres primeras son las que deciden si la API sirve. Van primero a propósito.

1. **¿La API expone el mix de tipo de préstamo a nivel de agente?** El export de
   la interfaz declara que no lo tiene. Si la API tampoco, hay que saberlo antes
   de presupuestar, porque ese es el campo que decide el encaje del cliente.

2. **¿Expone el split buyside/listside con volumen, unidades y share para cada
   lado?** Es lo que la interfaz hace mejor que su competencia y lo que resuelve
   la compuerta de encaje.

3. **¿Las métricas de mercado por condado están en la API** — fallout %, tiempo
   medio de cierre, mix del mercado, distribución de score, tipos de comprador,
   tasa, LTV, canal, tipo de lender — **o solo en la interfaz de Market
   Signals?**

4. ¿Qué ventana de tiempo devuelve por defecto y se puede fijar? La interfaz
   corre sobre trailing 14 months y permite configurar desde 2017 en los planes
   superiores. **Cada respuesta debería declarar su ventana**, porque hoy en la
   interfaz no lo hace y eso obliga a adivinar el grano.

5. ¿Devuelve FIPS de condado, o solo nombre? Con nombre solo, cruzar es
   ambiguo: hay 31 condados llamados Washington.

6. ¿Devuelve NMLS del originador y número de licencia del agente? Son las dos
   llaves de cruce.

7. ¿Cuál es el límite de llamadas y el modelo de precio — por llamada, por
   registro, por asiento?

8. ¿Hay endpoint de cambios o webhook, para no re-descargar todo?

## Una observación de método que conviene plantearles

Dos cosas que se detectaron en la prueba y que a ellos les sirve saber, porque
son bugs de presentación y no de dato:

- **Dos definiciones de wallet share en el mismo perfil sin etiquetar.** La
  tarjeta de Overview muestra 33/33/33 y la pestaña Originators 40,6/35,3/24,0
  para el mismo agente. Son por unidades y por volumen respectivamente, pero la
  interfaz no lo dice, así que cualquiera de los dos números se puede citar
  creyendo que es el otro.

- **"Top 3 Concentration 100%" cuando solo hay 3 operaciones casadas** de 14
  unidades del lado comprador. Leído como concentración de wallet share, es
  exactamente lo contrario de lo que pasa. Un denominador al lado del porcentaje
  lo resolvería.

Plantearlo así, como dos sugerencias de producto, suele abrir mejor la
conversación de API que pedir precio de entrada.
