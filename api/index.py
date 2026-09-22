"""El entrypoint unico de Vercel. WSGI puro, sin dependencias.

Por que uno solo y no una funcion por archivo
---------------------------------------------
El runtime de Python de Vercel pide un entrypoint cuando el proyecto tiene .py
fuera de `api/` -- y este repo tiene `captura/`, `motor/`, `pacs/`. El build
fallaba asi:

    Error: No python entrypoint found in default locations, but found
    potential entrypoints:
      api/geografias.py (variable: handler)
      ...
      captura/servidor.py (variable: Handler)

O sea que escaneaba el repo entero y encontraba hasta el servidor local. Con un
entrypoint declarado en `pyproject.toml` la ambiguedad desaparece.

Efecto lateral bueno: una sola funcion en vez de tres significa un solo arranque
en frio, y el parser se importa una vez.

Sin framework a proposito: WSGI de la biblioteca estandar. Nada que instalar,
nada que se desactualice, y el build no depende de resolver dependencias.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
for _r in (AQUI, os.path.dirname(AQUI)):
    if _r not in sys.path:
        sys.path.insert(0, _r)

from rutas import RUTAS  # noqa: E402

RAIZ = os.path.dirname(AQUI)
INDICE = os.path.join(RAIZ, "public", "index.html")


def _json(inicio, codigo: int, datos) -> list[bytes]:
    cuerpo = json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8")
    inicio("%d %s" % (codigo, "OK" if codigo < 400 else "ERROR"), [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(cuerpo))),
        ("Cache-Control", "no-store"),
    ])
    return [cuerpo]


def app(entorno, inicio):
    ruta = entorno.get("PATH_INFO", "/") or "/"
    metodo = entorno.get("REQUEST_METHOD", "GET").upper()

    # La mesa de trabajo. `outputDirectory` normalmente la sirve antes de
    # llegar aca; esto es el respaldo para que la raiz nunca sea un 404.
    if ruta in ("/", "/index.html"):
        try:
            with open(INDICE, "rb") as fh:
                cuerpo = fh.read()
        except OSError:
            return _json(inicio, 500, {"error": "no encuentro public/index.html"})
        inicio("200 OK", [("Content-Type", "text/html; charset=utf-8"),
                          ("Content-Length", str(len(cuerpo)))])
        return [cuerpo]

    entrada = RUTAS.get(ruta.rstrip("/") or "/")
    if not entrada:
        return _json(inicio, 404, {"error": "ruta desconocida: %s" % ruta})

    funcion, metodo_esperado = entrada
    if metodo != metodo_esperado:
        return _json(inicio, 405,
                     {"error": "%s espera %s" % (ruta, metodo_esperado)})

    if metodo == "GET":
        crudo = entorno.get("QUERY_STRING", "")
        datos = {k: v[0] for k, v in urllib.parse.parse_qs(crudo).items()}
    else:
        try:
            largo = int(entorno.get("CONTENT_LENGTH") or 0)
        except ValueError:
            largo = 0
        cuerpo = entorno["wsgi.input"].read(largo) if largo else b""
        try:
            datos = json.loads(cuerpo.decode("utf-8")) if cuerpo else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json(inicio, 400, {"error": "el cuerpo no es JSON"})

    try:
        codigo, salida = funcion(datos)
    except Exception as exc:  # noqa: BLE001
        # El mensaje llega al navegador a proposito: quien captura tiene que
        # poder decir que fallo sin abrir los logs de Vercel.
        return _json(inicio, 500,
                     {"error": "%s: %s" % (type(exc).__name__, exc)})
    return _json(inicio, codigo, salida)


# Alias por si el builder busca otro nombre.
application = app
handler = app
