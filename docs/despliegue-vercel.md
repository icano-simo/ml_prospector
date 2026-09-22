# Despliegue en Vercel

## Qué es cada cosa

| | |
|---|---|
| `public/index.html` | la mesa de trabajo. Estático, sin build |
| `api/*.py` | funciones serverless en Python. Hablan con Supabase |
| `api/_comun.py` | **empieza con `_`, así que no es una ruta**: es el helper |
| `captura/` | el parser y el protocolo. Se importan desde `api/` |

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
