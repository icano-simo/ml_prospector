# Despliegue en Vercel

## Qué es cada cosa

| | |
|---|---|
| `public/index.html` | la mesa de trabajo. Estático, sin build |
| `api/index.py` | **el entrypoint único**: una app WSGI que despacha las tres rutas |
| `api/rutas.py` | la lógica de cada endpoint, como funciones puras |
| `api/_comun.py` | Supabase por REST con la `service_role` |
| `captura/` | el parser y el protocolo. Se importan desde `api/` |
| `pyproject.toml` | declara el entrypoint. Sin esto el build falla |

## Un entrypoint, no una función por archivo

El runtime de Python pide un entrypoint cuando el proyecto tiene `.py` fuera de
`api/` — y este repo tiene `captura/`, `motor/`, `pacs/`. Con una función por
archivo el build falla así:

```
Error: No python entrypoint found in default locations, but found
potential entrypoints:
  api/geografias.py (variable: handler)
  ...
  captura/servidor.py (variable: Handler)
```

Escanea el repo entero y encuentra hasta el servidor local de captura. Con
`[tool.vercel] entrypoint = "api.index:app"` la ambigüedad desaparece.

Efecto lateral bueno: **una sola función en vez de tres** es un solo arranque en
frío, y el parser se importa una vez.

WSGI de la biblioteca estándar, sin framework: nada que instalar, y el build no
depende de resolver dependencias.

## `vercel.json`, y por qué cada línea

```json
"outputDirectory": "public"
```
Dice dónde están los estáticos. Explícito a propósito: el default para un
proyecto sin framework depende de la detección, y una suposición ahí devuelve un
404 en la raíz que parece un problema de rutas.

```json
"functions": { "api/*.py": { "includeFiles": "captura/**" } }
```
`includeFiles` es lo que sube `captura/` junto con las funciones. Sin eso,
`from captura.parser_mm import …` falla en Vercel y funciona en local, que es la
peor combinación.

### Lo que NO va, y el error que da

**No se fija la versión del runtime.** Vercel autodetecta Python en `api/*.py`.
Poner `"runtime": "@vercel/python@4.3.1"` produce, en el build:

```
Error: Failed to load Builders after installing them:
@vercel/python (pin-version-mismatch)
```

Es un error del builder, no del código: nada en el repo es incorrecto y el
mensaje no dice qué versión esperaba. Se quita el pin y listo.

**No hace falta el rewrite `/` → `/index.html`.** Con `outputDirectory`, Vercel
ya sirve `index.html` en la raíz. Y un rewrite interno dispara este aviso:

```
WARNING! Internal rewrites in backend framework projects now route requests
using the rewritten destination path.
```

## Variables de entorno

En **los tres entornos** — Production, Preview y Development:

```
SUPABASE_URL
SUPABASE_SERVICE_KEY
```

**Vercel no aplica variables nuevas a un build que ya existe.** Hay que
redesplegar después de agregarlas, o la función levanta con el mensaje de que
faltan.

La `service_role` vive **solo** acá y en `.env` local. Nunca llega al navegador:
el front habla con `/api/*` y esas funciones hablan con Supabase.

## La cabecera que hay que mandar siempre

`pacs` no es `public`, así que toda petición a PostgREST lleva su perfil:

| | |
|---|---|
| leer | `Accept-Profile: pacs` |
| escribir | `Content-Profile: pacs` |

Sin eso PostgREST busca en `public` y devuelve un 404 de tabla inexistente que
se lee como «no se expuso el esquema» cuando sí se expuso.

## Verificar que quedó bien

```
GET  /                    la mesa de trabajo
GET  /api/realtors        {"filas":[…], "total":"4249"}
GET  /api/geografias      {"geografias":[…]}
```

Si `/api/realtors` devuelve `{"error":"Faltan SUPABASE_URL…"}`, las variables
están puestas pero no se redesplegó.

---

## La marca no se escribe acá

`public/tokens.css` está **portado sin cambios** desde
`icano-simo/homesi-reporte-actividad`, `app/styles/tokens.css`. Canvas
`#FCFCFA`, navy `#001A40`, coral `#FF4040`, Light Sky `#A6DEFF`.

Si hay que actualizar la paleta, **se vuelve a bajar el archivo; no se edita
este**. Dos copias divergentes de una paleta es como se pierde una marca, y la
divergencia no falla: simplemente las apps dejan de parecerse.

`public/homesi.css` sí es propio, pero sus patrones de tabla —primera y última
columna fijas, zebra, hover Light Sky al 20%— salen de `components.css` de esa
misma app, con los mismos nombres de clase (`.tbl-scroll`, `table.piv`,
`th.lbl`, `td.totcol`, `tr.metric`).

Una diferencia declarada: allá `.totcol` tiene el aspecto de última columna pero
**no** es sticky. Acá se le agregó `position: sticky; right: 0` con su fondo
opaco, siguiendo el razonamiento que el original documenta para la primera —un
fondo translúcido deja ver las columnas pasando por debajo al scrollear.

---

## Listas vacías: los tres modos de fallo, y cuál NO aplica acá

De la skill `commercial-activity`, porque saber cuál es cuál ahorra una hora:

| | Síntoma |
|---|---|
| sin `GRANT` | PostgREST dice que **la tabla no existe** — construye su caché de esquema con lo que el rol puede ver |
| con `GRANT`, sin política | **cero filas y `error: null`**, indistinguible de una tabla vacía. El peligroso |
| con los dos | los datos |

Y la trampa de los claims: **un claim otorgado después del login no surte efecto
hasta volver a iniciar sesión**, porque viaja dentro del token. RLS no rechaza,
**filtra**: sin el claim la política devuelve cero filas, que se ven igual que
una tabla vacía.

### Por qué acá el diagnóstico es otro

**Esta app no habla con Supabase desde el navegador.** El front pide a `/api/*`
y esas funciones usan la `service_role` del lado del servidor, que **salta RLS
por completo**. No hay sesión de usuario, no hay claim, no hay política que
filtre.

O sea: **una lista vacía acá no es RLS.** Las causas reales son otras —filtro
demasiado estrecho, `Accept-Profile` faltante, lote apagado— y buscarla en las
políticas es perder la hora que la tabla de arriba quería ahorrar.

Queda escrita por dos razones: el día que la pantalla pase a Supabase Auth va a
aplicar entera, y cualquiera que consulte `pacs` con la `anon` key desde otro
sitio se la va a encontrar.

### La que sí aplica: el lote apagado

El equivalente local de «cero filas sin error» es
`v_capturas_modelmatch_current`, que solo devuelve filas de lotes con
`es_vigente = true`. Una captura que no aparece puede estar guardada con su lote
apagado: las filas siguen en `pacs.capturas_modelmatch` y la vista no las
muestra.

`supabase/apagar_lotes_de_ensayo.py` sin `--aplicar` lista el estado de cada
lote con su evidencia, que es el primer sitio donde mirar.
