# Etapa 1 · Esquema y motor

Qué se hizo, qué se encontró, qué quedó sin resolver.

---

## Qué se hizo

| | |
|---|---|
| [`motor/reglas.py`](../motor/reglas.py) | las 37 reglas, declaradas como datos |
| [`motor/evaluar.py`](../motor/evaluar.py) | el motor: aplica y devuelve la cadena de evidencia |
| [`motor/sincronizar_reglas.py`](../motor/sincronizar_reglas.py) | proyecta el catálogo a la tabla `reglas` |
| [`supabase/esquema.sql`](../supabase/esquema.sql) | el esquema, con `evaluaciones` desde el día uno |
| [`tests/test_reglas.py`](../tests/test_reglas.py) | **134 pruebas**: tres por regla más las invariantes |

449 pruebas en total, 0 fallas.

### No son 25 reglas: son 37 sobre 19 qualifiers

El brief decía «unas 25». El conteo exacto, portado del archivo 06 y de
`qualifiers_de()` en `pacs_engine.py`:

| Familia | Qualifiers | Reglas |
|---|---|---|
| P · dolores | 13 | 24 |
| J · jobs | 5 | 12 |
| G · gains | 1 | 1 |

Hay una prueba que fija el número: si cambia, se ve en el diff.

### Qué cambió y qué no

**El contenido no.** Cada regla conserva su condición, su intensidad, su grado
de evidencia y su texto literal. **La forma sí**: donde había una cadena de
`if/elif` de 120 líneas, ahora cada regla es un registro con `condicion`,
`qualifier`, `intensidad`, `grado`, `texto`, `campos`, `origen` y `referencia`.

Eso es lo que permite **una prueba por regla** en vez de una por módulo. Cada
regla tiene tres:

```
activa      con el dato que la dispara sale exactamente su intensidad
no_activa   con el dato contrario no sale
sin_dato    sin el dato NO sale y queda declarada como no evaluada
```

**La tercera es la que habría cazado el bug de `privado`.** Las siete pruebas de
`estado_perfil` cubrían la rama afirmativa y ninguna la rama sin evidencia.
Ahora esa rama es obligatoria y generada del catálogo: si se agrega una regla y
no se agrega su fila de datos, `test_toda_regla_tiene_su_dato_de_prueba` falla.

Los datos de entrada **están escritos a mano, regla por regla**, a propósito.
Generarlos del propio catálogo haría que la prueba y el código compartieran el
error: si la condición está mal, el dato generado también lo estaría y la
prueba pasaría igual.

### El campo `origen`

Las 37 son `propia`. La tabla `reglas` y el dataclass llevan
`origen ∈ {propia, matriz}` desde ahora, para que el reemplazo por las 124
reglas de la matriz sea **un cambio de datos y no una reescritura**. Hay una
prueba que verifica que hoy todas son propias.

---

## Qué se encontró

Cuatro puntos donde el prototipo y la documentación no coinciden. **Ninguno se
resolvió en silencio**: se portó lo documentado, se midió la diferencia sobre
las **4.249 filas del libro v3**, y se deja anotada en el campo `discrepancia`
de la regla.

### A · Resolución: `elif` contra «gana la mayor intensidad» · 23 filas (0,5%)

El archivo 06 dice literalmente: *«cuando varias reglas apuntan al mismo
qualifier, gana la de mayor intensidad»*. El prototipo usa `if/elif`, o sea
**la primera que coincide**, y para P-Q07 las evalúa en este orden:

```
dpa_enganche (3)  →  E6≤3 y R4≥7 (1)  →  primera_casa (2)
```

La regla de intensidad **1** se evalúa antes que la de **2**, así que un agente
que cumple las dos se queda con 1. Son **23 realtors** — por ejemplo ARMANDO
OCHOA, que el prototipo diagnostica con P-Q07 en intensidad 1 y la regla
documentada pone en 2.

El motor implementa lo documentado. La regla que perdió queda registrada en
`tambien_activaron`, porque también es evidencia.

### B · Dolor primario: solo P, o la mayor intensidad · 89 filas (2,1%)

El prototipo restringe el primario a la familia **P**:

```python
pains = [x for x in ordenados if x[0].startswith('P-')]
primario = pains[0] if pains else (ordenados[0] if ordenados else None)
```

El archivo 06 dice otra cosa: ordenar por intensidad, desempatar P > J > G, y
**excluir solo J-Q01**. O sea que un J- con intensidad 3 debería ganarle a un
P- con intensidad 1, y en el prototipo nunca gana.

**89 realtors cambian de dolor primario.** Ejemplos medidos:

| | Prototipo | Documentado |
|---|---|---|
| JUAN ACOSTA | P-Q01 | J-Q04 |
| SINDY MATA | P-Q11 | J-Q03 |
| WAFAA BARAJAS | P-Q06 | J-Q03 |

Es la discrepancia con más consecuencia: **el dolor primario decide el copy del
primer mensaje.** El motor implementa lo documentado, y es la que más conviene
que revises: puede ser que la intención real sea la del prototipo y el archivo
06 esté mal escrito.

### C · El techo por grado de evidencia · 191 filas (4,5%)

**Conflicto entre dos documentos de la metodología, no una decisión mía.** El
archivo 06 declara J-Q04 con intensidad **3** y grado **E1**; el techo del
archivo 05 dice que **E1 no pasa de 2**. El prototipo emite 3 porque
sencillamente no aplica ningún techo — la función no existe ahí.

El motor declara 3, el techo la recorta a 2 y deja la nota en `nota_techo`:

```
recortada de 3 a 2: evidencia E1 no sostiene mas.
```

**191 realtors** reciben J-Q04 en 2 donde el prototipo daba 3. Resolverlo es
una decisión de metodología: o la regla baja a 2, o el archivo 05 declara la
excepción E1→3 por escrito, que es el mecanismo que `intensidad_con_techo` ya
soporta.

### D · Acto de habla · 0 filas

El prototipo afirma con evidencia E0 e intensidad **≥ 2**; el archivo 05 exige
intensidad **3**. Medido: **cero filas afectadas**, porque no existe ninguna
regla con grado E0 e intensidad 2 en el catálogo. La diferencia es teórica hoy
y se volvería real en cuanto se escriba una.

---

## Dos hallazgos que no venían en el brief

### El libro v3 tiene una columna que infiere desde el apellido

`ev: broker apellido hisp`, entre las 156 columnas de la hoja `Realtors PACS`.

**Ninguna regla del motor la usa**, y no puede usarla: `verificar_catalogo()`
pasa los campos de cada regla por `verificar_entradas_de_inferencia`, que
levanta `ViolacionDeGuarda` con cualquier campo de apellido, etnia u origen. Hay
una prueba que recorre las 37.

Pero la columna existe en el dato, y si alguien la mapea a un campo del motor la
guarda salta. Queda dicho porque el brief pide que ECOA se cumpla también en lo
que se hereda, no solo en lo que se escribe nuevo.

### Los nueve campos que creí que faltaban, están

Mi primera medición reportó nueve campos sin fuente en el libro
(`ev2_primera_casa`, `ev2_comunidad`, `ev2_buy_side`…). **Era un error de mi
mapeo, no del libro**: las columnas están todas, con otro nombre. La primera
medición también usó un desempate que no era el del prototipo y dio 739 filas
donde la medición correcta da 89.

Lo digo porque el número equivocado ya estaba calculado y era plausible.

---

## El esquema

Doce tablas. Las decisiones que vale la pena mirar:

**`evaluaciones` existe desde hoy aunque no sirva para nada todavía.** Guarda la
evaluación completa, la entrada, la versión de reglas y una **huella del
catálogo** — sin la huella, si alguien toca una intensidad sin subir la versión,
las evaluaciones viejas y las nuevas quedan indistinguibles. Append-only por
convención: no hay `UPDATE` ni `DELETE` en el cargador.

**`evaluacion_contrastes` guarda el contraste, no la conclusión.** Cada fila
lleva el valor del agente y el de su mercado **con sus dos denominadores**, la
distancia, y las ramas cuando el contraste admite más de una explicación. Las
guardias van como restricciones de la base:

```sql
check (agente_num is null or agente_den is not null)
check (nombre <> 'mix_prestamo' or agente_den >= 10)
```

Un porcentaje sin denominador no se puede guardar, y el mix de préstamo con
menos de 10 operaciones tampoco.

**`ig_senales.estado_perfil` admite los nueve valores**, incluidos
`sin_grid`, `muro_de_sesion`, `degradado` y `vacio`. `privado` solo entra con
evidencia afirmativa.

**Ningún booleano que describa a una persona lleva `DEFAULT false`.** Son
nullables a propósito: nada se llena por descarte.

**`realtor_originadores` lleva `lado`**, porque el wallet share solo se calcula
sobre buyside — en un agente de listados el lender que aparece no es su socio,
es el del comprador que trajo otro agente.

**Everett Financial / Supreme Lending, NMLS 2129**, va insertado en `lenders`
con `es_la_casa = true` en el propio esquema, no en un script aparte.

---

## Qué quedó sin resolver

1. **No se cargó nada.** No tengo credenciales de Supabase y no las pedí. El
   esquema está escrito y el generador de reglas produce el SQL, pero **nada se
   aplicó contra una base real**, así que el esquema no está validado por
   Postgres. Lo que sí corre es el generador, con su prueba de idempotencia.

2. **El motor no tiene todavía la capa geográfica, ni Instagram, ni Model
   Match.** Esta etapa es el esqueleto de reglas. Los campos que las reglas leen
   (`R5_espanol`, `E6_asequibilidad`…) hoy vienen del libro v3; conectarlos a
   `ig_senales` y a `mercados` es la etapa de contrastes.

3. **Las cuatro discrepancias están medidas pero no decididas.** La B —89 filas
   que cambian de dolor primario— es la que más consecuencia tiene, porque el
   primario decide el copy. Necesita tu decisión, no la mía.

4. **La confianza global del archivo 06 no está implementada.** Sus coeficientes
   están declarados como arbitrarios en la propia documentación
   (`0,15 + 0,07×categorías + 0,06×qualifiers + 0,10 si bio legible`). La dejé
   afuera a propósito: es un puntaje compuesto, y el brief pide no producirlos
   sin poder mostrar de dónde salen. Si la querés, va con sus cuatro términos
   visibles y no como un número.

5. **Los sub-nichos SN01-SN11 y los arquetipos no se portaron.** Están en
   `sub_nichos()` del prototipo y en el archivo 07. No entraban en esta etapa.

6. **Lo que el archivo 11 pide verificar antes de entregar una secuencia sigue
   sin verificarse:** el copy promete mapas de DPA por condado, desgloses de
   documentación y tiempos de cierre reales. **Nadie confirmó que esos
   materiales existan.** No es trabajo de esta etapa, pero es bloqueante para la
   etapa de salida y conviene empezarlo ya.
