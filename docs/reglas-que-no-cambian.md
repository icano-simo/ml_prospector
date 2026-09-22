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

## 4 · No supongas la forma del destino. Pregúntasela

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

## 5 · Una guarda sobre el tráfico equivocado termina desactivada

Nadie quita una guarda por maldad. La quitan porque estorba.

`verificar_dataset` corría sobre las 156 columnas del libro cuando el cargador
toma 6, y frenó la carga entera por dos columnas que no miraba. **Un guardia en
la puerta equivocada, parando tráfico que no debería parar, tiene los días
contados.**

Que cada validación corra sobre lo que de verdad toca es lo que hace que siga
viva dentro de seis meses.

---

## 6 · Las tres guardias de PACS-H

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
