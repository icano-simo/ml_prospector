"""Las credenciales de Supabase, leidas del entorno.

Mismo patron que `google_places/cliente.py`: si falta, se levanta con el
mensaje de donde se saca. No se degrada en silencio ni se inventa un cliente
que despues falla en otro lado.

Ninguna clave se escribe en el codigo, ni se pasa por la linea de comandos: un
argumento queda en el historial del shell.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class SupabaseNoConfigurado(RuntimeError):
    """Faltan credenciales. No se sigue con una base inventada."""


#: Donde se saca cada cosa. Va en el error, no en un README que nadie abre.
_DONDE = """
Se sacan en el panel del proyecto, en Project Settings -> API:

  SUPABASE_URL          "Project URL", https://<ref>.supabase.co
  SUPABASE_SERVICE_KEY  "service_role secret"

Hace falta la service_role y no la anon: la anon esta limitada por las policies
de RLS y no puede aplicar el esquema. La service_role saltea RLS por completo,
asi que va solo en maquinas de trabajo y en el servidor -- nunca en el front de
Vercel, que usa la anon.

Para aplicar `supabase/esquema.sql` hace falta ademas la cadena de Postgres:

  SUPABASE_DB_URL       Project Settings -> Database -> Connection string -> URI

Ponelas en `.env` (esta en .gitignore) o en el entorno. NO en la linea de
comandos: un argumento queda en el historial del shell.
"""


@dataclass(frozen=True)
class Credenciales:
    url: str
    service_key: str
    db_url: str | None = None

    def __str__(self) -> str:
        """Nunca imprime la clave. Un repr descuidado va a parar a un log."""
        return "Credenciales(url=%s, service_key=***, db_url=%s)" % (
            self.url, "***" if self.db_url else None
        )

    __repr__ = __str__


def cargar_env(ruta: str = ".env") -> None:
    """Lee un `.env` simple al entorno. No pisa lo que ya este puesto.

    Sin dependencias: `python-dotenv` no esta instalado y esto son doce lineas.
    """
    if not os.path.exists(ruta):
        return
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            clave, valor = clave.strip(), valor.strip().strip('"').strip("'")
            if clave and valor and clave not in os.environ:
                os.environ[clave] = valor


def credenciales(*, exigir_db: bool = False) -> Credenciales:
    """Las credenciales, o un error que dice de donde sacarlas."""
    cargar_env()
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    db = os.environ.get("SUPABASE_DB_URL", "").strip() or None

    faltan = [n for n, v in (("SUPABASE_URL", url),
                             ("SUPABASE_SERVICE_KEY", key)) if not v]
    if exigir_db and not db:
        faltan.append("SUPABASE_DB_URL")
    if faltan:
        raise SupabaseNoConfigurado(
            "Falta %s en el entorno.\n%s" % (", ".join(faltan), _DONDE)
        )
    return Credenciales(url=url, service_key=key, db_url=db)


def esta_configurado() -> bool:
    """Para que un script pueda saltearse un paso sin reventar."""
    try:
        credenciales()
        return True
    except SupabaseNoConfigurado:
        return False
