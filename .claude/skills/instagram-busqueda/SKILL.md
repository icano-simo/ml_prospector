---
name: instagram-busqueda
description: Manual operativo de la BÚSQUEDA del perfil de Instagram de un realtor a partir de su nombre, estado y licencia — las tres consultas a DuckDuckGo, los cinco candidatos, la regla de verificación de dos condiciones que decide la confianza del handle, los diez estados del perfil y la regla de que un handle no verificado no aporta señales. Cárgala ANTES de buscar handles para cualquier lote, antes de cambiar `realtor_scraper/instagram/finder.py` o `verificacion.py`, y antes de construir cualquier interfaz que lance esta búsqueda. Es prescriptiva: la verificación no es opcional.
---

# Búsqueda del perfil de Instagram — manual operativo

**Regla cero: un handle sin verificar no es un handle, es una suposición.**
Esta capa no termina cuando encuentra una cuenta; termina cuando puede decir
**por qué** cree que esa cuenta es de esa persona, y con cuánta confianza.

Este manual cubre la **primera mitad** del sistema: de un realtor a un handle
verificado. Lo que se hace con ese handle después —leer posts, comentarios y
derivar las 50 columnas— está en la skill `instagram-minado`.

> ⚠ **El fallo que originó todo este diseño, porque explica cada decisión que
> sigue.** La primera versión encontraba handle para el **98,1 %** de los
> realtors (5.516 de 5.620). Un 98 % de acierto buscando cuentas por nombre no
> es creíble, y no lo era: la causa estaba en una línea.
>
> ```
> handles = re.findall(r"instagram\.com/([A-Za-z0-9_.]{3,30})", content)
> ```
>
> `content` era el HTML **completo** de la página de resultados, así que el
> primer `instagram.com/...` que apareciera —un anuncio, el pie de página de
> DuckDuckGo, el perfil de otra persona— se devolvía como el handle del
> realtor. **Nunca se comprobó que el perfil fuera de esa persona.**
>
> Y como no había verificación, un handle equivocado **no producía un error**:
> producía catorce señales de contenido sobre la persona equivocada, con el
> mismo aspecto que las correctas.

---

## 1 · Qué hace falta para que funcione en otra máquina

### Dependencias

```
patchright>=1.0.0
playwright>=1.44.0
loguru>=0.7.0
```

`patchright` es un Playwright parcheado para no anunciarse como automatizado.
El código lo intenta primero y cae a `playwright` si no está:

```python
try:
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright
```

Después de instalar, hace falta bajar el navegador:

```
python -m playwright install chromium
```

### La sesión de Instagram

**Instagram no muestra casi nada sin sesión iniciada.** Hay un paso previo,
que se hace **una sola vez** y deja las cookies en disco:

```
python -m instagram.finder --iniciar-sesion
```

Abre un navegador con ventana, se inicia sesión a mano, y el perfil queda
guardado.

⚠ **El directorio de perfil de Instagram está SEPARADO del general**, y no por
orden:

| | |
|---|---|
| `output/browser_profile` | navegación general |
| `output/browser_profile_instagram` | **solo** la cuenta dedicada |

Dos razones, las dos medidas: un bloqueo de Instagram sobre un perfil
compartido se lleva puesta la otra sesión; y si alguien inicia sesión con su
cuenta personal en el perfil general, **el lote entero sale a nombre de esa
persona**.

⛔ **Cómo se comprueba que hay sesión: por COOKIE, nunca por DOM.** Antes se
miraba un selector (`a[href^='/explore/']`) y **daba falso positivo**: ese
enlace existe también en la página sin sesión, así que el lote arrancaba
creyendo estar autenticado. Medido el 2026-09-21: el DOM decía «sesión
detectada» y el endpoint JSON devolvía **401**. La comprobación mira el token
de autenticación que emite Instagram, que no es una heurística.

### Qué hace falta de cada realtor

| campo | obligatorio | para qué |
|---|---|---|
| nombre | **sí** | sin él no se busca; devuelve `sin nombre de realtor` |
| apellido | **sí** | se concatena con el nombre |
| estado | no, pero pesa | entra en las tres consultas y desempata homónimos |
| licencia | no | **si está, manda sobre todo lo demás** — ver 3·C |

---

## 2 · La búsqueda — tres consultas, cinco candidatos

### Las consultas, exactas y en este orden

```
site:instagram.com "<nombre completo>" realtor <estado>
site:instagram.com "<nombre completo>" real estate <estado>
site:instagram.com <nombre completo> realtor <estado>
```

Contra `https://duckduckgo.com/?q=<consulta>&kl=us-en`.

**Las dos primeras llevan el nombre entre comillas y la tercera no.** No es
redundancia: las comillas piden coincidencia exacta y la tercera es la red de
seguridad para los nombres que la fuente escribió distinto de como la persona
los usa.

**Se para en cuanto hay 5 candidatos** (`MAX_CANDIDATOS`), así que la tercera
consulta a menudo no se ejecuta.

### De dónde se extraen los handles

⛔ **De los `href` de los enlaces, NUNCA del HTML de la página.** Es la línea
que causó el 98,1 %.

```python
enlaces = page.query_selector_all("a[href*='instagram.com']")
```

DuckDuckGo **envuelve** sus resultados, así que el destino real va dentro del
parámetro `uddg=` y hay que desenvolverlo antes de leerlo:

```python
if "uddg=" in href:
    partes = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    href = (partes.get("uddg") or [href])[0]
```

Y después se extrae el handle con:

```
instagram\.com/([A-Za-z0-9_.]{2,30})(?:/|\?|$)
```

### Las rutas que NO son handles

Instagram usa su propio dominio para muchas cosas que no son personas.
**Esta lista se descarta siempre**, y es copiable tal cual:

```
p
reel
reels
explore
accounts
stories
tv
about
privacy
legal
help
tags
directory
developer
api
instagram
web
direct
challenge
emails
session
oauth
graphql
static
images
ajax
your_activity
```

### El ritmo de la búsqueda

| | |
|---|---|
| entre consultas | **2,5 a 5,0 s**, aleatorio |
| ante un `403` o `429` de DuckDuckGo | **30 a 70 s** y se salta esa consulta |

El rango aleatorio no es cosmético: un ritmo perfectamente uniforme durante
horas es, en sí mismo, una firma de automatización.

---

## 3 · La verificación — la parte que no es opcional

Los candidatos **no están verificados**. Lo que sigue es lo que decide si se
usan.

### A · Las dos condiciones

1. **el nombre del perfil se parece al del realtor**, y
2. **la bio o los posts traen señal inmobiliaria**.

### B · La tabla de confianza

| nombre coincide | señal inmobiliaria | confianza |
|---|---|---|
| sí | sí | **alta** |
| sí (pero **por email**) | sí | **media** |
| sí | no | **media** |
| no | sí | **baja** |
| no | no | **baja** |

**Coincidir por email da `media` y no `alta`**: son dos señales, pero la de
identidad es indirecta.

**`media` sin señal inmobiliaria significa «puede ser su cuenta personal»** —
es la persona correcta, pero la cuenta quizá no sea la profesional.

### C · La excepción que manda sobre todo: la licencia

Si la bio declara un número de licencia que **coincide con el que ya
teníamos**, la confianza es **alta sin mirar el nombre**.

**Por qué:** la licencia es la llave de identidad de todo el sistema —el resto
del repo identifica realtors por número de licencia, no por nombre—. Un
nombre es una cadena de texto; una licencia es un identificador emitido por un
estado.

La comparación se hace **sin ceros a la izquierda** (`lstrip("0")`), porque las
fuentes los escriben distinto.

### D · Qué NO se compara

⛔ **No se compara apellido con origen, etnia ni nacionalidad.** La comparación
de nombre es **comparación de cadenas** entre el nombre que dio la fuente y el
nombre que la persona puso en su propio perfil. Eso es verificación de
identidad, no inferencia sobre una persona.

### E · El detalle que hace que la comparación funcione

Comparar «Ana Tapia» con «Ana Tapia | Realtor®» exige limpiar antes. El módulo:

- **quita las palabras de oficio** del nombre de perfil, para que el `| Realtor`
  no rompa la coincidencia;
- **separa camelCase y dígitos** del handle (`soldbyclarissa` → fragmentos);
- **parte tokens pegados** por palabras de ruido de **4 letras o más**.

⚠ **Las de 2 y 3 letras están fuera a propósito, y está medido por qué.** Con
`by`, `mi`, `tu`, `the`, `my` dentro: `mirna → rna`, `byron → ron`,
`michelle → chelle`, `temperance → mperance`, `themis → mis`. **Cinco nombres
reales arruinados para rescatar uno.**

Los conectores de 2-3 letras **solo se recortan de un fragmento que ya vino de
un corte**, nunca de un token entero. Esa distinción es lo que lo hace seguro:
si `byclarissa` apareció después de cortar `sold`, el `by` del borde es casi
seguro ruido; en cambio `byron` nunca se cortó por nada, así que su `by` se
respeta.

---

## 4 · El orden de evaluación, y por qué ahorra el 80 % de las peticiones

Por cada candidato, **en orden**:

1. se lee el perfil **sin comentarios** (`con_comentarios=False`) — lo mínimo
   para tener nombre de perfil, bio y captions;
2. se extraen las licencias de la bio y se comparan con la nuestra;
3. se verifica y se anota el resultado;
4. **si la confianza es `alta`, se corta ahí y no se miran los demás**;
5. si no, se espera 2,5-5,0 s y se pasa al siguiente.

Al terminar se toma **el mejor por confianza** (`alta` > `media` > `baja`),
no el primero que apareció.

⛔ **Solo entonces, y solo si la confianza es usable, se paga la lectura
completa** —posts, comentarios y el destino del link de la bio—. Hacerlo por
cada candidato multiplicaría por cinco las peticiones a Instagram, que es
justo lo que provoca un bloqueo.

### La consecuencia de la confianza `baja`

**El handle se guarda igual**, con su confianza y su razón. No se descarta:
un handle de confianza baja sigue siendo un punto de partida para una
verificación a mano.

⛔ **Pero sus señales NO se usan.** Esa es la regla, y la razón está escrita en
el propio mensaje que emite el código: *«un handle equivocado no produce un
error, produce catorce señales sobre la persona equivocada»*.

---

## 5 · Los diez estados del perfil

**Nunca se devuelve `False` donde corresponde `null`.** Una señal ausente
lleva su motivo, y el motivo importa: **un perfil privado es un dato sobre la
persona; un handle equivocado es un dato sobre nuestro scraper.**

| estado | qué significa | ¿hay contenido? |
|---|---|---|
| `publico_leido` | se leyó de verdad | **sí** |
| `privado` | la cuenta es privada | no |
| `muro_de_sesion` | Instagram pidió iniciar sesión | no |
| `sin_grid` | cargó, pero no había cuadrícula de posts | no |
| `degradado` | cargó a medias | no |
| `vacio` | la cuenta existe y no tiene posts | no |
| `no_encontrado` | el handle no existe | no |
| `bloqueado` | Instagram cortó | no |
| `handle_equivocado` | el perfil no es de esta persona | no |
| `sin_handle` | la búsqueda no devolvió candidatos | no |

⚠ **El enum pasó de 5 valores a 9 (más `sin_handle`), y los cuatro nuevos
salen tal cual en vez de mapearse de vuelta.** Mapearlos escondería
exactamente la distinción que existen para hacer. **`publico_leido` no
cambió**, que es el valor sobre el que filtra la app que consume el archivo, y
ninguno de los nuevos tiene contenido legible —igual que `privado`—. Lo único
que cambia de comportamiento es el código que comparaba `== "privado"`, y a
ese código se le estaba mintiendo.

---

## 6 · Qué devuelve

Un objeto `SenalesInstagram` con tres partes que hay que entender juntas:

| parte | qué es |
|---|---|
| las señales | el contenido leído |
| `disponibilidad` | un booleano **por señal**: ¿se pudo acreditar? |
| `motivos_de_ausencia` | **por qué no**, señal por señal |

Las trece señales que llevan máscara de disponibilidad:

```
seguidores
bio
captions
idioma_contenido
programas
menciones
co_marketing
cadencia
engagement
geotags
audiencia
destacadas
link_de_bio
```

Más `evaluados`: la lista de todos los candidatos mirados, cada uno con su
handle, su estado, su confianza y la razón. **Eso es lo que permite auditar
una identificación sin repetir la búsqueda.**

---

## 7 · Cómo se ejecuta

```
python -m instagram.finder --iniciar-sesion     # una vez
python -m instagram.finder --objetivo           # qué se va a buscar, sin buscar
python -m instagram.finder --piloto 20 --con-ventana
python -m instagram.finder --revisar-piloto     # revisión a mano
python -m instagram.finder --lote               # el lote entero
```

⚠ **El piloto va con `--con-ventana` (no headless) y la revisión a mano va
ANTES del lote grande.** El propio script lo recuerda al terminar el piloto.
No es burocracia: es la única forma de ver que los selectores siguen
funcionando antes de gastar diez horas.

### Banderas que cambian el resultado

| bandera | qué hace |
|---|---|
| `--desde-cero` | ignora el checkpoint y reempieza |
| `--reintentar-ilegibles` | repite los `sin_grid`, `muro_de_sesion`, `degradado` y los `privado` viejos inferidos por ausencia de posts |
| `--excluir-descartados` | saca del objetivo los `DESCARTADO` y `RECLASIFICADO` |
| `--limite N` | corta el lote |
| `--con-ventana` | navegador visible |

⛔ **`--reintentar-ilegibles` NO repite los privados de verdad ni los vacíos**,
y es correcto: **no mejoran repitiendo**. Un privado seguirá privado y una
cuenta sin posts seguirá sin posts; reintentarlos es gastar peticiones contra
un bloqueo.

---

## 8 · Lo que detiene el lote

El lote se **detiene** —no reintenta— ante un desafío, un captcha o un bloqueo.
Está así por pedido explícito del brief, y la razón es que insistir contra un
bloqueo convierte un problema de una hora en una cuenta quemada.

Entre perfiles hay una pausa de **20 a 40 segundos**, y cada ciertos perfiles
una **pausa larga**. La pausa larga no estaba en el brief: está porque un ritmo
perfectamente uniforme durante diez horas es una firma.

---

## 9 · Lo que esta capa NO hace

- **No saca contactos.** Teléfono y correo salen del módulo de identidad
  (`state_licenses/`) y de los insumos privados, no de Instagram.
- **No decide si el realtor sirve.** Eso es del motor de scoring.
- **No infiere nada sobre la persona** más allá de comparar cadenas de texto
  para verificar identidad.
- **No usa Zillow.** Se retiró el 2026-09-21: produjo cero columnas y sus
  términos de uso prohíben el scraping.
