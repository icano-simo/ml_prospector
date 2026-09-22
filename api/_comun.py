"""Lo compartido por las funciones de Vercel: Supabase por REST, service_role.

Por que REST y no conexion directa
----------------------------------
Es lo que ya usan las otras apps de la division. No hay razon para inventar otro
camino, y una conexion directa a Postgres desde serverless necesita pooler y
trae sus propios problemas.

La `service_role` vive SOLO del lado del servidor, en las variables de entorno
de Vercel. Nunca llega al navegador: el front habla con `/api/*` y estas
funciones hablan con Supabase.

Y `pacs` no es `public`, asi que toda peticion lleva su cabecera de perfil:
`Accept-Profile` para leer y `Content-Profile` para escribir. Sin eso PostgREST
busca en `public` y devuelve un 404 de tabla inexistente que se lee como "no se
expuso el esquema" cuando si se expuso.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

ESQUEMA = "pacs"


class SinCredenciales(RuntimeError):
    pass


def _cred() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_KEY") or "").strip()
    if not url or not key:
        raise SinCredenciales(
            "Faltan SUPABASE_URL o SUPABASE_SERVICE_KEY en el entorno de "
            "Vercel. Project Settings -> Environment Variables, en los tres "
            "entornos, y redesplegar: Vercel no aplica variables nuevas a un "
            "build que ya existe."
        )
    return url, key


def _pedir(metodo: str, ruta: str, *, cuerpo=None, cabeceras=None):
    url, key = _cred()
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(
        url + ruta, data=datos, method=metodo,
        headers={
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(cabeceras or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            texto = r.read().decode("utf-8")
            return r.status, (json.loads(texto) if texto.strip() else None), \
                dict(r.headers)
    except urllib.error.HTTPError as exc:
        texto = exc.read().decode("utf-8", "replace")
        try:
            detalle = json.loads(texto)
        except json.JSONDecodeError:
            detalle = {"mensaje": texto[:400]}
        return exc.code, detalle, {}


def leer(tabla: str, consulta: str = "", *, rango: str | None = None):
    cab = {"Accept-Profile": ESQUEMA}
    if rango:
        cab["Range"] = rango
        cab["Prefer"] = "count=exact"
    return _pedir("GET", "/rest/v1/%s%s" % (tabla, consulta), cabeceras=cab)


def escribir(tabla: str, filas: list[dict], *, devolver: bool = True,
             sin_duplicar: bool = False):
    """POST a PostgREST.

    `sin_duplicar` agrega `resolution=ignore-duplicates`, para las tablas que
    acumulan con `unique`: capturar dos veces el mismo perfil es normal y no
    deberia devolver un 409 que tire la peticion entera.
    """
    prefer = ["return=representation" if devolver else "return=minimal"]
    if sin_duplicar:
        prefer.append("resolution=ignore-duplicates")
    cab = {"Content-Profile": ESQUEMA, "Prefer": ",".join(prefer)}
    return _pedir("POST", "/rest/v1/%s" % tabla, cuerpo=filas, cabeceras=cab)


def actualizar(tabla: str, consulta: str, cambios: dict):
    return _pedir("PATCH", "/rest/v1/%s%s" % (tabla, consulta),
                  cuerpo=cambios,
                  cabeceras={"Content-Profile": ESQUEMA,
                             "Prefer": "return=minimal"})


def responder(handler, datos, codigo: int = 200) -> None:
    cuerpo = json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(codigo)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(cuerpo)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(cuerpo)


def cuerpo_json(handler) -> dict:
    largo = int(handler.headers.get("Content-Length") or 0)
    if not largo:
        return {}
    try:
        return json.loads(handler.rfile.read(largo).decode("utf-8"))
    except json.JSONDecodeError:
        return {}
