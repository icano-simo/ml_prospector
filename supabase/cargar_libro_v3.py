"""Carga los 4.249 realtors del libro v3 en `pacs.realtors`.

Que se carga y que NO
---------------------
Solo identidad y ficha base. Los 156 campos del libro incluyen scores, criterios
y evidencias derivadas: eso lo recalcula el motor desde los crudos y no se
guarda como si fuera un dato de la persona.

Y `ev: broker apellido hisp` no entra: lo bloquea `motor.entrada`, que es la
barrera que existe para que un campo prohibido no llegue al dataset.

Tres decisiones que se toman aca y conviene que se vean
------------------------------------------------------
1 · **`condado_fips` queda NULL.** El libro trae `mmi: condado_dominante`, que
    es un NOMBRE de condado, no un FIPS. La columna es `text`, asi que el
    nombre entraria sin error y nadie lo notaria hasta cruzar con Census. Un
    dato en la columna equivocada es peor que una columna vacia.

2 · **El telefono se normaliza a E.164 o se deja NULL.** Si no se puede
    reconocer como numero de EE.UU., no se guarda: la columna se llama
    `telefono_e164` y meter ahi otra cosa es la misma familia del punto 1.

3 · **`match_confidence` = 1.0 con la nota de que no hubo cruce.** Esta es la
    carga semilla: estas filas no se cruzaron con nada, son el origen. Poner
    otro numero seria inventar la confianza de un cruce que no ocurrio.
"""
from __future__ import annotations

import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.entrada import verificar_dataset  # noqa: E402
from supabase.cargar import cargar, conectar  # noqa: E402

LIBRO = os.path.join(RAIZ, "Data_inputIA",
                     "Homesi_Scoring_Realtors_v3_PACS (2).xlsx")
HOJA = "Realtors PACS"
FUENTE = "libro_v3"

#: Las unicas columnas del libro que entran. El resto son derivadas.
COLUMNAS = ("Nombre", "Brokerage", "Estado", "Email", "Telefono",
            "Unidades/ano")


def _texto(v) -> str | None:
    import pandas as pd
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def telefono_e164(v) -> tuple[str | None, str | None]:
    """(numero E.164, motivo de descarte). Uno de los dos es None.

    No adivina pais: si no son 10 digitos, u 11 empezando en 1, se descarta con
    el motivo. Guardar un numero que no es E.164 en una columna llamada
    `telefono_e164` es mentirle al que la lea despues.
    """
    s = _texto(v)
    if not s:
        return None, "vacio"
    digitos = re.sub(r"\D", "", s)
    if len(digitos) == 10:
        return "+1" + digitos, None
    if len(digitos) == 11 and digitos.startswith("1"):
        return "+" + digitos, None
    return None, "no reconocido como numero de EE.UU. (%d digitos)" % len(digitos)


def email_limpio(v) -> str | None:
    s = _texto(v)
    if not s or "@" not in s:
        return None
    s = s.lower()
    return s if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", s) else None


def clave_de(licencia, telefono, email) -> str:
    """La cascada del brief: licencia -> telefono -> email -> nombre."""
    if licencia:
        return "licencia"
    if telefono:
        return "telefono"
    if email:
        return "email"
    return "nombre_condado_volumen"


def construir_filas() -> tuple[list[dict], dict]:
    import pandas as pd

    df = pd.read_excel(LIBRO, sheet_name=HOJA)

    # La guarda de ECOA va sobre lo que ESTE cargador toma, no sobre las 156
    # columnas del libro. El libro tiene `ev: broker apellido hisp` y seguira
    # teniendola por trazabilidad de la v2; lo que no puede es entrar aca.
    #
    # Lo aprendi corriendo esto: puse la guarda sobre `df.columns` y freno la
    # carga entera por dos columnas que el cargador ni mira. Un guardia en la
    # puerta equivocada para el trafico que no deberia parar, y a la larga lo
    # desactivan.
    verificar_dataset(COLUMNAS)

    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        raise SystemExit("faltan columnas en el libro: %s" % faltan)

    filas = []
    cuenta = {"telefonos_descartados": 0, "emails_descartados": 0,
              "sin_nombre": 0, "por_clave": {}}

    for _, r in df.iterrows():
        nombre = _texto(r["Nombre"])
        if not nombre:
            cuenta["sin_nombre"] += 1
            continue

        tel, motivo = telefono_e164(r["Telefono"])
        if motivo and motivo != "vacio":
            cuenta["telefonos_descartados"] += 1

        crudo_email = _texto(r["Email"])
        email = email_limpio(r["Email"])
        if crudo_email and not email:
            cuenta["emails_descartados"] += 1

        clave = clave_de(None, tel, email)
        cuenta["por_clave"][clave] = cuenta["por_clave"].get(clave, 0) + 1

        unidades = r["Unidades/ano"]
        filas.append({
            # El libro no trae licencia. Queda NULL y eso es el dato.
            "licencia_estado": None,
            "licencia_numero": None,
            "telefono_e164": tel,
            "email_principal": email,
            "nombre_completo": nombre,
            # NULL a proposito: el libro trae nombre de condado, no FIPS.
            "condado_fips": None,
            "rango_volumen": None,
            "clave_resolucion": clave,
            # Carga semilla: no hubo cruce. Ver la nota del modulo.
            "match_confidence": 1.0,
            "brokerage": _texto(r["Brokerage"]),
            "estado": _texto(r["Estado"]),
            "unidades_ano": None if pd.isna(unidades) else float(unidades),
            # No se verifico contra originadores todavia. NULL, no false.
            "es_cliente_de_la_casa": None,
            "cliente_de_la_casa_motivo": None,
        })
    return filas, cuenta


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    filas, cuenta = construir_filas()
    print("filas a cargar: %d" % len(filas))
    print("  sin nombre, descartadas   : %d" % cuenta["sin_nombre"])
    print("  telefonos no reconocidos  : %d" % cuenta["telefonos_descartados"])
    print("  emails mal formados       : %d" % cuenta["emails_descartados"])
    print("  clave de resolucion       : %s" % cuenta["por_clave"])
    print("")

    res = cargar(
        "realtors", filas,
        fuente=FUENTE,
        archivo=os.path.basename(LIBRO),
        nota=("carga semilla: no hubo cruce, match_confidence=1.0. "
              "El libro NO trae licencia estatal: las 4.249 filas quedan sin "
              "la llave dura del modelo. condado_fips NULL porque el libro trae "
              "nombre de condado y no FIPS."),
    )
    print(res)
    print("")

    # ── La deuda de identidad, contada EN LA BASE ───────────────────────────
    #
    # Dos numeros distintos que conviene no confundir:
    #
    #   sin_llave_dura  ninguna de las tres: ni licencia, ni telefono, ni email.
    #                   Son los que no se pueden cruzar con NADA.
    #   sin licencia    la llave que el modelo declara primaria y la que usan
    #                   Model Match y los padrones estatales.
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from pacs.realtors")
            total = cur.fetchone()[0]
            cur.execute("select count(*) from pacs.realtors where sin_llave_dura")
            sin_llave = cur.fetchone()[0]
            cur.execute("select count(*) from pacs.realtors "
                        " where licencia_numero is null")
            sin_lic = cur.fetchone()[0]
            cur.execute("select clave_resolucion, count(*) from pacs.realtors "
                        " group by 1 order by 2 desc")
            por_clave = cur.fetchall()
            cur.execute("select count(*) from pacs.realtors "
                        " where email_principal is not null")
            con_email = cur.fetchone()[0]
            cur.execute("select count(*) from pacs.realtors "
                        " where telefono_e164 is not null")
            con_tel = cur.fetchone()[0]

    print("=" * 70)
    print("LA DEUDA DE IDENTIDAD, contada en la base")
    print("=" * 70)
    print("  realtors en la tabla        : %d" % total)
    print("  con email                   : %d (%.1f%%)"
          % (con_email, 100.0 * con_email / total))
    print("  con telefono E.164          : %d (%.1f%%)"
          % (con_tel, 100.0 * con_tel / total))
    print("")
    print("  sin_llave_dura = true       : %d (%.1f%%)"
          % (sin_llave, 100.0 * sin_llave / total))
    print("      ni licencia, ni telefono, ni email: no se cruzan con nada")
    print("")
    print("  SIN LICENCIA ESTATAL        : %d (%.1f%%)"
          % (sin_lic, 100.0 * sin_lic / total))
    print("      la llave primaria del modelo, y la que usan Model Match y")
    print("      los padrones estatales. El libro v3 no trae la columna.")
    print("")
    print("  clave de resolucion:")
    for clave, n in por_clave:
        print("      %-24s %5d" % (clave, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
