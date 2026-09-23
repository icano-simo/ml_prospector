# Reglas que no cambian

Salieron de bugs reales. Cada una dice **qué error la produjo**, porque una
regla sin su caso se lee como preferencia y se negocia.

---

## 1 · ¿La ausencia viene de la misma lectura que la presencia?

**La pregunta que hay que hacerle a toda regla que concluya desde una
ausencia.**

Una regla que dice *«no le vimos X»* solo significa algo si se miró. La
distinción no es si la regla usa una negación — es **de dónde viene el campo
ausente**:

| | |
|---|---|
| **Se protege sola** | el campo ausente sale de la **misma lectura** que los presentes. Si no se leyó, faltan los dos, la condición da `None` y la regla no se evalúa |
| **Hay que atarla** | el campo ausente sale de **otra fuente** que la que la habilita. Ahí la regla puede dispararse con datos viejos sobre un sujeto que hoy no se puede leer |

### El caso

`P-Q10-2` decía *«audiencia construida sin señal de producción sostenida»* y
disparaba con `ig_seguidores ≥ 1000` y sin señal de video ni educación.

**`ig_seguidores` puede venir de un raspado viejo y sobrevivir a que el perfil
hoy sea privado.** Así que la regla disparaba con la puerta abierta y la ventana
cerrada: los seguidores de antes, el contenido de nunca. Sobre un perfil
privado, *«no vimos»* se convertía en diagnóstico.

`J-Q01-1` y `J-Q01-3` parecían iguales y no lo son: `ev2_buy_side` y
`ev2_listing_side` salen de **la misma bio**. Si no se leyó, faltan los dos y la
regla ni se evalúa.

### Lo que costó y lo que reveló

Atada a `estado_perfil = publico_leido`, P-Q10 pasó de ser el dolor primario de
**1.111 personas a 24**. Y los ~623 que se movieron no cayeron en la cola: se
fueron al segundo qualifier que ya tenían, con mejor evidencia — P-Q06 subió a
756, P-Q01 a 604.

**Una inferencia por ausencia no solo era débil: estaba tapando un diagnóstico
fuerte.**

### Y la asimetría dentro de la misma familia

`P-Q10-1` concluye desde una **presencia** — produce video — y no necesita saber
si leímos el perfil: si hay señal de video, hay señal de video. Las dos reglas
son del mismo qualifier y se comportan al revés.

`tests/test_reglas.py::test_toda_regla_que_concluye_desde_una_ausencia_esta_justificada`
obliga a contestar la pregunta cuando aparezca la quinta.

---

## 2 · Nadie consulta `pacs.evaluaciones` directamente

**La tabla es el histórico. La vista es el estado.**

Toda lectura va por **`pacs.v_evaluacion_actual`**, que hace `DISTINCT ON
(realtor_id)` por `evaluado_en desc`.

### El caso

Un reporte contó `select count(*) from pacs.evaluaciones` después de dos
corridas del motor y dio **8.374 evaluaciones y 34,8% sin dolor primario**. El
número real era **40,4%**: `count(*)` sobre una tabla append-only cuenta
**corridas**, no personas.

Es el tipo de error que produce **un número plausible que nadie cuestiona** — no
revienta, no avisa, y se cita en una reunión.

---

## 3 · Una verificación que pasa porque no tiene nada que verificar

**Tres veces en este proyecto.** Es el patrón más peligroso de todos, porque el
sistema reporta éxito y el error no deja rastro.

| Caso | La verificación decía | Lo que pasaba |
|---|---|---|
| **`Email Owner`** | 100% de cobertura al cruzar | 14 valores únicos sobre 4.386 filas: todo el lote unido a catorce personas |
| **`privado` por descarte** | 7 perfiles «privados», sin error | ninguno tenía evidencia de privacidad; el código lo admitía en su propia cadena |
| **la tabla de condados** | validación de conteo «OK» | el regex devolvía **cero condados**, así que `1 + 0 = 1` y cualquier cantidad de bloques pasaba como «solo el estado» |
| **`aplicar_migracion.py`** | imprimía el constraint de `contactos` y decía «aplicada» | lo imprimía **corriera la migración que corriera**: una salida que no depende de lo que pasó |
| **la guarda de la migración 07** | «la columna `hash_volcado` existe» | la buscaba **en la tabla**, donde sí estaba, mientras la vista seguía sin ella |

En los tres, **la guarda corría y no fallaba** — no porque el dato estuviera
bien, sino porque el conjunto que examinaba estaba vacío o degenerado.

### Cómo se detecta

No basta con que la validación no falle. Hay que preguntarle **sobre cuántos
elementos corrió**:

```
cero condados leídos   ⇒  la validación de conteo no valida nada
cero comentarios       ⇒  el ratio de idioma no mide nada
un solo comentario     ⇒  el desajuste de 0,92 es ruido
14 emails distintos    ⇒  el cruce del 100% no es cobertura
```

**Toda guarda que compare una cantidad contra otra tiene que declarar su
denominador y desconfiar del cero.** Un conjunto vacío hace verdadera cualquier
afirmación universal — y eso, en una verificación, se ve exactamente igual que
pasar.

### La forma corta

> Cuando una comprobación pase, preguntá cuántas cosas revisó. Si la respuesta
> es ninguna, no pasó: no corrió.

---

## 4 · Un paso aparte es un paso que no corre

**El corolario operativo de la §3.** Si la promoción de un dato de una tabla a
otra vive en un script que alguien tiene que acordarse de ejecutar, entonces
mientras no se ejecuta **no falla nada**: la primera tabla se llena, todo
parece bien, y la segunda sigue vacía.

### El caso

`pacs.mercados` estuvo en **cero filas** con cuatro bloques de Market Signals ya
guardados y **45 métricas parseadas cada uno**. La captura funcionaba, el parser
funcionaba, el crudo estaba entero. Ningún contraste de Model Match podía correr
y nada lo decía — porque nada estaba roto: lo que faltaba era un paso que nunca
se escribió.

### Las dos mitades de la regla

1. **La promoción ocurre en la misma operación que la escritura.**
   `api.rutas.guardar` escribe la captura y promueve a la biblioteca en la misma
   petición. `supabase/promover_mercados.py` existe solo para lo capturado
   antes, y usa **la misma función** que el endpoint, para que la vía de
   respaldo y la viva no puedan divergir.

2. **Un dato listo que no llega a su destino es un fallo declarado.** Un bloque
   con métricas parseadas que no produce fila en `pacs.mercados` sale como
   `FALLO DE PROMOCIÓN` en los avisos del guardado, con cuántos eran y cuántos
   entraron. El silencio no es una opción, porque el silencio es exactamente lo
   que hubo durante cuatro bloques.

---

## 5 · Un rechazo puede venir con el código de éxito

Pariente de la anterior: la comprobación corre, pero **mira la señal
equivocada**.

`api.census.gov` contesta **HTTP 200 en los cuatro casos**, y el motivo del
rechazo viaja en el cuerpo, como HTML:

| lo que se manda | respuesta |
|---|---|
| clave buena | `200` · `[["NAME","state"],["California","06"]]` |
| sin parámetro `key` | `200` · `<title>Missing Key</title>` |
| `key` vacía | `200` · `<title>Missing Key</title>` |
| `key` equivocada | `200` · `<title>Invalid Key</title>` |

Un cliente que mire `response.status` da el rechazo por bueno y revienta más
tarde al parsear — **en otro sitio y con otro mensaje**, que es lo que hace
perder la tarde buscando en el lugar equivocado.

`geo/census.py` valida el **cuerpo**: si no empieza por `[`, es un rechazo, y el
error dice cuál de los dos es porque el arreglo no es el mismo (falta
configuración vs. la clave equivocada).

### Y el log que miente

La primera versión del diagnóstico enmascaraba la URL **reinyectando** `key=` en
lo que imprimía, así que mostró una clave en la petición que no llevaba
ninguna. Un log que miente sobre lo que se mandó es peor que no tener log: se
descarta la hipótesis correcta con la evidencia a la vista.

Se enmascaran los parámetros **reales**, nunca se construye la salida aparte.

### El corolario del plan B que no existía

«El API funciona sin clave hasta unas 500 consultas diarias por IP» es cierto
para otros endpoints y **no para `acs5`**: sin clave responde `Missing Key`.
Medido, no supuesto — y por eso el mensaje de `ClaveInvalida` lo dice, para que
nadie vuelva a intentar ese camino.

---

## 6 · No supongas la forma del destino. Pregúntasela

**Tres veces en dos días, el mismo patrón.**

| Qué se supuso | Qué pasó |
|---|---|
| que toda tabla lleva `upload_batch_id` | `pacs.realtors` no lo lleva — es registro maestro, no tabla de carga |
| que la guarda ECOA va sobre el archivo | corría sobre las 156 columnas del libro y frenó una carga por dos que el cargador ni mira |
| que una `list` de Python es `jsonb` | `dolores_secundarios` es `text[]`: *malformed array literal* |
| que `employee_key` es `text` | es `bigint`, y el JOIN que daba la integridad no compilaba |

En los cuatro, la forma real estaba a **una consulta de distancia**:
`information_schema.columns`.

### El corolario que duele

En el caso de `employee_key`, el tipo mal supuesto **no rompía una consulta:
borraba la garantía**. Ese `INNER JOIN` es lo que hace que una licencia huérfana
deje de contar sola. Que Postgres se negara al aplicar fue suerte; con un cast
implícito se habría perdido en silencio.

---

## 7 · Una guarda sobre el tráfico equivocado termina desactivada

Nadie quita una guarda por maldad. La quitan porque estorba.

`verificar_dataset` corría sobre las 156 columnas del libro cuando el cargador
toma 6, y frenó la carga entera por dos columnas que no miraba. **Un guardia en
la puerta equivocada, parando tráfico que no debería parar, tiene los días
contados.**

Que cada validación corra sobre lo que de verdad toca es lo que hace que siga
viva dentro de seis meses.

---

## 8 · Un dato que existe y nadie lee se comporta igual que uno que no existe

Hermano del §3, y peor de detectar. Allá una guarda corría y no encontraba nada
que mirar. Acá **no hay guarda**: hay una columna, con el dato correcto, que
ningún camino de código abre. Nada falla, nada queda vacío, ningún conteo se ve
raro. El sistema se comporta exactamente como si la columna no estuviera — pero
se *siente* cubierto, porque el dato está ahí y se puede señalar.

**El caso.** El libro trae `pacs: nivel_de_calificacion` con 135 `DESCARTADO`,
25 `BLOQUEADO POR COBERTURA` y 1 `RECLASIFICADO POR MMI`. `correr_motor.py`
nunca leyó esa columna. Resultado, medido el 2026-09-23: **158 personas
excluidas por metodología recibieron evaluación normal, y 122 de ellas salieron
con dolor primario** — Lisa Munoz con P-Q10 y confianza MEDIA, lista para
cualquier cola de contacto. El diagnóstico era correcto; lo que faltaba era la
decisión, ya tomada, de no contactarla.

Lo que lo hizo visible no fue una prueba: fue preguntar por dos nombres
concretos. **Un agregado nunca lo habría mostrado** — 158 sobre 4.187 no mueve
ningún porcentaje que alguien estuviera mirando.

### La otra cara: una columna que nadie escribe

**El mismo día, la misma forma, al revés.** `capturas_modelmatch.realtor_id`
existe desde el esquema original y estuvo **NULL en las 60 filas**: el guardado
escribía el id dentro de `parseado` y nunca en la columna. Nadie lo notó porque
`capturas_que_mandan()` lee `parseado->>realtor_id`, que sí estaba lleno. La
columna no estaba rota: estaba **muerta**.

Y el costo no fue el dato perdido —no se perdió nada— sino **la conclusión
falsa**: mirar esa columna lleva a decidir que las capturas están huérfanas
cuando están perfectamente pegadas. Una columna muerta no devuelve un error;
devuelve NULL, que se lee como un hecho.

De ahí: **si un dato vive en dos sitios, los dos se escriben en el mismo acto**
—nunca uno «por ahora»— y el sitio que lleva la restricción es el que tiene que
poder rechazar. La restricción se puso `NOT VALID` a propósito: 33 filas de
ensayo retirado apuntan a realtors sintéticos que nunca existieron, y crear un
realtor de mentira para satisfacerla es cómo se ensucia una tabla de identidad.
`NOT VALID` rige lo que se escriba de ahora en más sin reescribir la historia,
y deja constancia en el esquema de que hay historia que no la cumple.

### Y lo que sí podía perderse: la captura pegada a la persona equivocada

Una captura huérfana no sirve para nada **y se nota**. Una captura pegada al
realtor equivocado **sirve para lo que no es**, y no se nota nunca: los cuatro
mercados entran, el perfil parsea, la confirmación dice que todo salió bien, y
el diagnóstico de Fulano se calcula con la producción de Mengano.

El volcado trae con qué comprobarlo —el Overview abre con el nombre del agente
y su email—, así que `captura/pertenencia.py` compara y la confirmación dice
**a quién quedó pegada** antes que ninguna otra cosa. No bloquea el guardado: el
crudo ya se pegó y tirarlo obliga a repetir el trabajo. Los tres veredictos son
`respalda`, `discrepa` y `no_consta` — y **`no_consta` no es `respalda`**, que
es la distinción del §3 otra vez.

Dos piezas del nombre, no una: `MARIA CRESPO` y `ARMANDO CRESPO` son dos
realtors de eXp en Florida, y aceptar por apellido es aceptar a la familia
entera.

### Las tres reglas que salen de ahí

**La exclusión se lee, no se deduce.** Un descarte por cobertura, por NMLS
propio o por estar fuera del ICP es una decisión de otra etapa. Si el motor la
recalculara, el día que cambie un qualifier volvería a contactar a alguien que
ya se decidió no contactar — y el motor habría «funcionado».

**Corta donde se produce la acción, no donde se muestra.** `/api/lectura`
devuelve la evaluación completa de un excluido: su diagnóstico no estorba, y
esconderlo haría que alguien lo capturara otra vez sin entender por qué no
aparece. Lo que responde **409** es `/api/dossier`, que ES la secuencia de 7
toques, y `/api/extracto`, que es el material para escribirle. Devolver el
dossier confiando en que la pantalla no lo mande es la misma omisión un piso
más arriba.

**Un valor nuevo no puede caer del lado permisivo.** `motor/exclusion.py`
declara las dos listas —`NO_CONTACTABLES` y `CONTACTABLES`— y **levanta
`NivelDesconocido`** ante cualquier nivel que no esté en ninguna. El error
original fue una omisión silenciosa; que la siguiente grite es lo único que
evita repetirlo. Por lo mismo `RECLASIFICADO POR MMI` se compara **por prefijo**:
el valor real llega con coletilla (`· fuera de ICP`), y una igualdad exacta
contra él devolvería «contactable» sin avisar — que es el §3 otra vez, dentro
de la guarda escrita para evitarlo.

Un nivel **vacío no es una exclusión**: es una fila sin diagnosticar, y eso lo
gobierna la confianza. Confundirlos dejaría fuera a los 3.332 PRE-MQL por no
haber llegado a mirarlos.

---

## 9 · Las tres guardias de PACS-H

Sin denominador no hay porcentaje. El mix de programa no activa ni desactiva
nada con menos de 10 operaciones con tipo identificado o menos del 50% de
cobertura del lado comprador. El wallet share solo sobre buyside.

**Y el wallet share de la exclusión por no-canibalización se decide por
unidades, no por volumen.** Lo que importa es cuántas operaciones pasan por un
colega, no cuántos dólares: la relación con el realtor se construye por
operación.

Model Match reparte de las dos formas en el mismo perfil — el Overview por
unidades, la pestaña Originators por volumen — y **Chris Ruiz da 50,0% por
unidades y 30,7% por volumen**. Con un umbral en 40%, el mismo originador entra
o no entra según cuál se lea, y las dos salen del mismo volcado sin que nada
avise.

`captura/trampas.py` lo fija: `wallet_share_para_exclusion()` lee `orig_buyer` y
**no cae** a `tab_orig` si falta — un reparto con la otra base da un número
plausible con la definición equivocada.

Nada se llena por descarte: sin evidencia afirmativa, el valor es **desconocido
con su razón**.

Ninguna inferencia desde apellido, etnia u origen — ni del realtor, ni de sus
clientes, ni de los loan officers. Las variables de tract describen **dónde
opera**, no quién es. Es ECOA Regulation B, no una preferencia.
