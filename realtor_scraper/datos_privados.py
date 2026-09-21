"""Resuelve donde viven los insumos con datos personales, que es fuera del repo.

Por que existe
--------------
Hasta el 2026-09-21 los insumos con nombre, email y telefono estaban dentro del
repo, que estaba publico en GitHub. Ahora viven en un directorio hermano y el
codigo los pide por aca. Mantener la ruta en un solo lugar es lo que evita que
alguien vuelva a poner un xlsx de contactos adentro del arbol "solo para
probar".

Orden de resolucion del directorio base:

1. la variable de entorno ML_PROSPECTOR_DATOS, si esta;
2. ../ml_prospector_datos_privados relativo a la raiz del repo.

Si el archivo pedido no esta, falla con un mensaje que dice donde buscarlo. No
devuelve una ruta que no existe: un FileNotFoundError tres pasos despues, en
pandas, no dice nada util.
"""
from __future__ import annotations

import os
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parent.parent
_ENV = "ML_PROSPECTOR_DATOS"


def directorio_base() -> Path:
    """Directorio raiz de los datos privados, sin garantizar que exista."""
    desde_env = os.environ.get(_ENV)
    if desde_env:
        return Path(desde_env).expanduser().resolve()
    return (RAIZ_REPO.parent / "ml_prospector_datos_privados").resolve()


def _resolver(subcarpeta: str, nombre: str) -> Path:
    base = directorio_base()
    ruta = base / subcarpeta / nombre
    if ruta.exists():
        return ruta

    # Segunda oportunidad: plano en la base, sin subcarpeta.
    plano = base / nombre
    if plano.exists():
        return plano

    raise FileNotFoundError(
        "No encuentro %r.\n"
        "  Busque en: %s\n"
        "        y en: %s\n"
        "\n"
        "Los insumos con datos de contacto viven FUERA del repo. Si los tenes\n"
        "en otro lado, apunta la variable de entorno %s al directorio base.\n"
        "Lo que NO hay que hacer es copiarlos dentro del repo: el pre-commit de\n"
        "scripts/verificacion/sin_pii_versionada.py lo va a rechazar, y por algo."
        % (nombre, ruta, plano, _ENV)
    )


def ruta_insumo(nombre: str) -> Path:
    """Un insumo de prospeccion (la lista cruda de realtors, exports de MMI)."""
    return _resolver("insumos", nombre)


def ruta_crm(nombre: str) -> Path:
    """Un export de CRM. Trae disposiciones de llamada: nunca se versiona."""
    return _resolver("crm", nombre)
