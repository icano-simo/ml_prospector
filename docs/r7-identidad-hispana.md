# R7 · Identidad hispana — de dónde sale

**Resultado de la investigación: R7 se calcula desde el apellido y el nombre de
pila del realtor.** Eso dispara la condición de parada de la tarea 5 del PR 1.
Este documento es el reporte, no una descripción neutra.

Investigado el 2026-09-23 sobre `Data_inputIA/Homesi_Scoring_Realtors_v3_PACS
(2).xlsx`, que es la única fuente de R7 que existe en el repo.

## La fórmula, literal del libro

Hoja **`Metodologia`**, fila `R7`, columnas «fuente» y «cálculo»:

> **Fuente:** Base de apellidos del U.S. Census Bureau (Frequently Occurring
> Surnames), filtrada a los apellidos con 75% o más de portadores
> auto-identificados como Hispanic/Latino, más una lista de nombres de pila.
>
> **Cálculo:** Base 3. Suma 4 si el apellido está en la base censal, 1,5
> adicional si hay un segundo apellido hispano (patrón de doble apellido), 2 si
> el nombre de pila es hispano. Si nada coincide pero el apellido termina en
> -ez/-es/-az/-iz/-oz, suma 1,5 por heurística patronímica. Tope en 10.
>
> **Escala:** 10 = nombre y doble apellido hispanos / 3 = sin indicios.

Y la columna «qué mide», también literal:

> **Probabilidad de que el realtor pertenezca a la comunidad latina.**

Hoja **`Pesos`**: `R7 | Identidad hispana del realtor | 0.08 | Realtor` — pesa
un 8% del score ponderado.

Hoja **`Leeme`**: `Con apellido hispano del propio realtor | 2354`.

No hace falta inferir nada: el libro declara que la entrada es el apellido y el
nombre, y que la salida es una probabilidad de pertenencia a un grupo.

## La contradicción dentro del propio libro

Hoja **`PACS · Leeme`**, sección «Lo que este motor NO hace»:

> 1) No infiere nicho por apellido, etnia u origen nacional: eso sería
> discriminación bajo ECOA Reg. B. El apellido entra solo como el criterio R7
> que ya existía en v2, como señal terciaria.

La primera mitad de la frase describe una regla; la segunda declara la
excepción que la anula. Lo que la excepción dice, en los hechos, es que el
apellido sí infiere — el criterio R7 es literalmente «probabilidad de que el
realtor pertenezca a la comunidad latina», y alimenta cuatro reglas de nicho.

«Señal terciaria» tampoco describe bien lo que hace: ver más abajo.

## Qué columnas la alimentan

Ninguna. **R7 no se deriva de otra columna del libro**: llega ya calculada.
Comprobado de tres formas:

- El `.xlsx` no trae fórmula en esa celda. La hoja `Realtors` tiene 16.996
  fórmulas, pero la columna Z (`R7 Identidad hispana`) contiene valores
  literales (`<v>9</v>`), no `<f>`.
- Ninguna columna del libro la determina: el mejor candidato deja 8 valores
  distintos de R7 dentro de un mismo grupo.
- `ev: broker apellido hisp` **no** la explica: cada valor de R7 aparece con esa
  bandera en 0 y en 1, en proporciones casi iguales (R7=9 → 22% con bandera;
  R7=3 → 20%). Esa columna es del *brokerage* y alimenta R6, no R7.

**El código del repo no la calcula: la lee.** `supabase/correr_motor.py:52` mapea
`"R7 Identidad hispana" → R7_identidad_hispana` y la pasa tal cual al motor.

**Lo que haría falta para reproducirla** es el script que generó el libro v3 —
el que descargó la tabla del Census Bureau, aplicó el filtro del 75% y recorrió
los nombres. Ese script no está en el repo, y sin él R7 no es reproducible ni
auditable: es un número heredado.

## Dónde entra en el motor

Cuatro reglas de [motor/reglas.py](../motor/reglas.py), todas con umbral
`R7 >= 8`:

| Regla | Qualifier | Fuerza | Grado | Condición |
|---|---|---|---|---|
| `P-Q01-4` ([:218](../motor/reglas.py#L218)) | P-Q01 | 1 | E3 | `R5_espanol >= 6` **o** `R7 >= 8` |
| `P-Q14-3` ([:241](../motor/reglas.py#L241)) | P-Q14 | 1 | E3 | `R7 >= 8` **solo** |
| `P-Q13-1` ([:249](../motor/reglas.py#L249)) | P-Q13 | 2 | E1 | `ev2_comunidad` **y** (`R5 >= 6` o `R7 >= 8`) |
| `P-Q13-2` ([:258](../motor/reglas.py#L258)) | P-Q13 | 1 | E3 | `ev2_fe_familia` **y** `R7 >= 8` |

`P-Q14-3` es el caso puro: *«identidad hispana sin evidencia de contenido en
español»*, fuerza 1, grado E3 — el qualifier se activa **por el apellido y por
nada más**. Su propio enunciado dice que no hay evidencia de idioma.

## Cuánto pesa, medido

Sobre las 4.187 evaluaciones vigentes:

| | |
|---|---|
| evaluaciones con R7 en su `entrada` | 4.187 de 4.187 (100%) |
| con `R7 >= 8`, el umbral de las cuatro reglas | 853 |
| activaciones de `P-Q01-4` | 987 |
| activaciones de `P-Q14-3` | 722 |
| activaciones de `P-Q13-2` | 144 |
| activaciones de `P-Q13-1` | 50 |
| **realtors contactables cuyo dolor primario lo da una regla con R7** | **559** |
| de esos, los que se quedarían **sin ninguna activación** si R7 sale | **201** |
| los que conservan otra activación | 358 |

«Señal terciaria» no describe esto. A 559 personas contactables el motor les
asigna el dolor primario —el que gobierna el gancho, el ángulo y los siete
toques— por una regla que lee el apellido, y a 201 de ellas no les queda
ninguna otra señal.

## Por qué la guarda no lo detectó

`verificar_entradas_de_inferencia` ([pacs/guardas.py:301](../pacs/guardas.py#L301))
compara **nombres de campo** contra un conjunto: `apellido`, `surname`,
`etnia`, `race`, `origen`…

`R7_identidad_hispana` no contiene ninguna de esas palabras. **El campo está
nombrado por lo que dice medir, no por lo que lo calcula** — y eso es
precisamente lo que una guarda sobre el nombre no puede ver.

Es el §3 del [libro de reglas](reglas-que-no-cambian.md) otra vez: la guarda
corría, no fallaba, y no comprobaba nada. Con el agravante de que aquí el
conjunto examinado no estaba vacío por accidente: **la etiqueta es el único
lugar donde la procedencia prohibida no aparece.**

Ampliar la lista a subcadenas (`surname`, `apellido`, `etnia`, `ethnic`), como
pedía la tarea 5, **tampoco habría atrapado a R7** — sigue sin contener ninguna.
Por eso la guarda ahora tiene un segundo mecanismo: un registro explícito de
campos cuya **procedencia** es una base prohibida, con independencia de cómo se
llamen. Un campo se declara ahí una vez, por lo que se sabe de su origen, y deja
de depender de que alguien lo haya nombrado con honestidad.

## Lo que queda por decidir (no es de Claude Code)

La decisión de negocio registrada dice: *«R7 se mantiene por ahora. Si resulta
que usa apellido, etnia u origen, sale del motor (riesgo ECOA / Reg B).»*

Resulta que sí. La decisión está tomada por su propio texto, pero el alcance —
201 realtors que se quedan sin diagnóstico y 358 que cambian de dolor primario —
no se puede ejecutar sin que alguien lo mire. Queda para Isabella.

Nota aparte, del mismo hallazgo: **R6 `Broker latino` también usa apellido** —
*«2 si el nombre contiene un apellido hispano»*. Es el apellido de una empresa,
no de una persona, así que no es el mismo problema; pero si R7 sale, R6 merece
la misma pregunta, porque el patrón que describe («oficina fundada por un agente
latino») vuelve a ser inferencia de origen sobre un individuo.
