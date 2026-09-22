"""Otorga o revoca el claim `pacs` en app_metadata.allowed_apps.

Las tres cosas que la skill simologic-supabase pide y que este script hace
-------------------------------------------------------------------------

1 · **Relee la fila despues de escribir.** Un script que reporta exito porque la
    llamada no dio error ya mintio en este proyecto. Aca el exito se declara
    unicamente si el claim esta en la fila leida DESPUES.

2 · **No reescribe el app_metadata entero.** `provider` y `providers` son claims
    reservados de GoTrue, y devolverlos en un update puede hacer que la
    escritura se descarte en silencio. Se manda solo `allowed_apps`, que es lo
    que la API de admin mergea sobre lo existente.

3 · **COALESCE sobre allowed_apps ausente.** Un usuario sin el campo da NULL, no
    lista vacia, y cualquier comparacion construida sobre eso se evalua a NULL.

Uso
---
    python -m supabase.otorgar_claim --listar
    python -m supabase.otorgar_claim --otorgar alguien@supremelending.com
    python -m supabase.otorgar_claim --revocar alguien@supremelending.com

Sin argumentos no hace nada: no hay modo "aplicar a todos".
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from supabase.config import credenciales

CLAIM = "pacs"


def _api(cred, metodo: str, ruta: str, cuerpo: dict | None = None):
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(
        cred.url.rstrip("/") + ruta,
        data=datos,
        method=metodo,
        headers={
            "apikey": cred.service_key,
            "Authorization": "Bearer " + cred.service_key,
            "Content-Type": "application/json",
            "User-Agent": "ml_prospector/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, {"error": exc.read().decode("utf-8", "replace")[:300]}


def _usuarios(cred) -> list[dict]:
    estado, doc = _api(cred, "GET", "/auth/v1/admin/users?per_page=200")
    if estado != 200:
        raise SystemExit("no pude listar usuarios: %s %s" % (estado, doc))
    return doc.get("users", [])


def _apps(u: dict) -> list[str]:
    """La lista, con el COALESCE hecho en Python."""
    meta = u.get("app_metadata") or {}
    valor = meta.get("allowed_apps")
    return list(valor) if isinstance(valor, list) else []


def listar(cred) -> None:
    usuarios = _usuarios(cred)
    con = [u for u in usuarios if CLAIM in _apps(u)]
    print("usuarios: %d · con el claim %r: %d" % (len(usuarios), CLAIM, len(con)))
    print("")
    for u in sorted(usuarios, key=lambda x: x.get("email") or ""):
        marca = "SI " if CLAIM in _apps(u) else "   "
        print("  %s %-42s %s" % (marca, u.get("email"), ", ".join(_apps(u)) or "-"))


def _buscar(cred, email: str) -> dict:
    for u in _usuarios(cred):
        if (u.get("email") or "").lower() == email.lower():
            return u
    raise SystemExit("no existe ese usuario: %s" % email)


def cambiar(cred, email: str, *, otorgar: bool) -> int:
    u = _buscar(cred, email)
    apps = _apps(u)

    if otorgar and CLAIM in apps:
        print("%s ya tiene el claim. No toco nada." % email)
        return 0
    if not otorgar and CLAIM not in apps:
        print("%s no tiene el claim. No toco nada." % email)
        return 0

    nuevas = sorted(set(apps) | {CLAIM}) if otorgar else \
        sorted(set(apps) - {CLAIM})

    # SOLO allowed_apps. Nada de provider ni providers.
    estado, doc = _api(cred, "PUT", "/auth/v1/admin/users/%s" % u["id"],
                       {"app_metadata": {"allowed_apps": nuevas}})
    if estado != 200:
        print("la escritura fallo: %s %s" % (estado, doc))
        return 1

    # ── La relectura. El exito se declara desde aca, no desde el status ─────
    despues = _apps(_buscar(cred, email))
    ok = (CLAIM in despues) if otorgar else (CLAIM not in despues)
    print("%s -> %s" % (email, ", ".join(despues) or "-"))
    if not ok:
        print("!!! la fila releida NO refleja el cambio. NO se aplico.")
        return 1

    # Y que no se haya perdido nada de lo que ya tenia.
    perdidas = set(apps) - set(despues) - ({CLAIM} if not otorgar else set())
    if perdidas:
        print("!!! se perdieron claims que ya tenia: %s" % sorted(perdidas))
        return 1

    print("verificado releyendo la fila.")
    return 0


def _main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Claim %r" % CLAIM)
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--otorgar", metavar="EMAIL")
    ap.add_argument("--revocar", metavar="EMAIL")
    args = ap.parse_args(argv)

    cred = credenciales()
    if args.listar:
        listar(cred)
        return 0
    if args.otorgar:
        return cambiar(cred, args.otorgar, otorgar=True)
    if args.revocar:
        return cambiar(cred, args.revocar, otorgar=False)

    ap.print_help()
    print("")
    print("No hay modo 'a todos': el claim se da de a uno y se verifica de a uno.")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
