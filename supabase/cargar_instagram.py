"""Carga ig_signals.csv a pacs.ig_senales y los crudos a pacs.ig_crudo.

    python supabase/cargar_instagram.py            # solo reporta
    python supabase/cargar_instagram.py --aplicar

LA LLAVE · y por que no es sf_lead_id
-------------------------------------
El brief pedia cruzar "por sf_lead_id y por email como respaldo". **El CSV no
trae sf_lead_id**: sus columnas de identidad son `email`, `nombre` y `handle`.
Asi que el orden real es el inverso -- se cruza por EMAIL, y el `sf_lead_id`
se alcanza a traves del realtor, no al reves.

El nombre no es llave y no se usa ni de respaldo: hay dos ANDREA SAAVEDRA en el
libro y el cruce por nombre ya dio 301 filas sobre 300.

EL BOM
------
La primera columna del CSV se llama `﻿email`, no `email`. Se abre con
`utf-8-sig` o la llave entera se lee como ausente -- que es justo lo que le
paso al primer diagnostico que corri sobre este archivo.

LOS DOS JUNTOS, EN UN LOTE
--------------------------
`capturado_en` es NOT NULL en las dos tablas y **solo esta en el crudo**. Cargar
las señales sin los crudos no se puede, y separarlos en dos lotes dejaria que
uno viva sin el otro.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)

import psycopg  # noqa: E402

from supabase.config import cargar_env  # noqa: E402

CSV = os.path.join(RAIZ, "realtor_scraper", "output", "ig_signals.csv")
CRUDOS = os.path.join(RAIZ, "realtor_scraper", "output", "ig_raw")
FUENTE = "instagram"

#: Columnas del CSV que van a COLUMNA propia. El resto entra en `senales`.
A_COLUMNA = {
    "handle", "estado_perfil", "handle_confianza", "captions_n",
    "comentarios_n", "paginacion_truncada", "desajuste_idioma",
}
#: Columnas de identidad: no son señal y no entran en el jsonb.
DE_IDENTIDAD = {"email", "nombre", "estado"}

#: Los nueve estados que acepta el check de la tabla.
ESTADOS_VALIDOS = {
    "publico_leido", "privado", "no_encontrado", "bloqueado", "handle_dudoso",
    "muro_de_sesion", "sin_grid", "degradado", "vacio",
}

#: Columnas que pueden traer texto de terceros. La redaccion ya corrio en el
#: scraper; esto es la guarda redundante, a proposito: cuando un cambio
#: protege datos sensibles, la segunda guarda falla ruidosamente.
#:
#: `citas_por_etiqueta` MEZCLA citas de captions (del agente) con citas de
#: comentarios (de terceros), y no dice de cual viene cada una.
CON_TEXTO_DE_TERCEROS = ("comentarios_texto", "citas_por_etiqueta",
                         "preguntas_recibidas")

#: Columnas que son, por definicion, del AGENTE en su propio muro.
DEL_AGENTE = ("captions_texto", "comentarios_del_agente", "email")

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
_RE_TELEFONO = re.compile(r"(?<!\d)(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})(?!\d)")


def _mismo_contacto(dato: str, texto: str) -> bool:
    """¿Aparece este email o telefono en ese texto, con cualquier formato?

    Los telefonos se comparan por sus DIGITOS: `(773) 362-5798`, `773.362.5798`
    y `7733625798` son el mismo numero y se escriben de tres formas. Comparar
    las cadenas daria que no coinciden, y eso convertiria el dato del agente en
    un falso positivo de terceros.
    """
    if not texto:
        return False
    if "@" in dato:
        return dato.lower() in texto.lower()
    solo = re.sub(r"\D", "", dato)
    return any(re.sub(r"\D", "", m.group(0)) == solo
               for m in _RE_TELEFONO.finditer(texto))


class CargaInstagramFallida(RuntimeError):
    pass


def leer_csv(ruta: str = CSV) -> list[dict]:
    # utf-8-sig, no utf-8: el BOM convierte `email` en `﻿email`.
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def verificar_sin_pii_de_terceros(filas: list[dict]) -> dict:
    """Ningun email ni telefono de un TERCERO entra en la base.

    La primera version marcaba cualquier contacto en `citas_por_etiqueta` y
    freno la carga por diez hallazgos que resultaron ser **del propio agente**:
    realtors que ponen su telefono en sus propios captions. Un dato de negocio,
    no una fuga.

    Es la misma equivocacion que ya cometi una vez, y el motivo por el que una
    guarda tiene que mirar el trafico correcto: la que para lo que no debe
    termina desactivada por estorbar.

    Asi que cada hallazgo se contrasta contra lo que el agente escribio EL
    MISMO. Si esta ahi, es suyo. Si solo esta en los comentarios ajenos, o si
    no aparece en ninguna de las dos, se para la carga -- la procedencia
    desconocida no es un aprobado.
    """
    de_terceros, del_agente = [], []
    for i, f in enumerate(filas):
        suyo = " ".join((f.get(c) or "") for c in DEL_AGENTE)
        ajeno = f.get("comentarios_texto") or ""
        for col in CON_TEXTO_DE_TERCEROS:
            texto = f.get(col) or ""
            for patron in (_RE_EMAIL, _RE_TELEFONO):
                for m in patron.finditer(texto):
                    dato = m.group(0)
                    if _mismo_contacto(dato, suyo):
                        del_agente.append((f.get("handle"), dato))
                        continue
                    donde = ("en comentarios de terceros"
                             if _mismo_contacto(dato, ajeno)
                             else "de procedencia desconocida")
                    de_terceros.append((i, f.get("handle"), col, dato[:28],
                                        donde))
    if de_terceros:
        raise CargaInstagramFallida(
            "NO SE CARGA: %d datos de contacto que NO son del agente.\n%s"
            % (len(de_terceros),
               "\n".join("  fila %d (%s) · %s · %r · %s" % h
                         for h in de_terceros[:8])))
    return {"del_agente": del_agente}


def _num(v):
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _bool(v):
    if v in (None, "", "None"):
        return None
    return str(v).strip().lower() in ("true", "1", "si", "sí")


def cargar_crudos(directorio: str = CRUDOS) -> dict[str, dict]:
    """email -> el JSON tal cual. Los archivos se llaman por email."""
    salida = {}
    for ruta in glob.glob(os.path.join(directorio, "*.json")):
        clave = os.path.splitext(os.path.basename(ruta))[0].strip().lower()
        try:
            with open(ruta, encoding="utf-8") as fh:
                salida[clave] = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print("   crudo ilegible %s: %s" % (os.path.basename(ruta), exc))
    return salida


def resolver_realtors(cur, emails: list[str]) -> dict[str, tuple]:
    """email -> (realtor_id, sf_lead_id). El email es la UNICA llave del CSV."""
    if not emails:
        return {}
    cur.execute("""
        select lower(email_principal), id, sf_lead_id
          from pacs.realtors
         where lower(email_principal) = any(%s)
    """, ([e.lower() for e in emails],))
    return {e: (rid, lead) for e, rid, lead in cur.fetchall()}


def main(aplicar: bool) -> int:
    cargar_env()
    url = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if not url:
        print("falta SUPABASE_DB_URL")
        return 1
    if not os.path.exists(CSV):
        print("no existe %s -- el scraper todavia no escribio el CSV" % CSV)
        return 1

    filas = leer_csv()
    print("ig_signals.csv: %d filas, %d columnas"
          % (len(filas), len(filas[0]) if filas else 0))
    if not filas:
        print("CSV vacio")
        return 1

    # La guarda de PII corre ANTES de tocar la base.
    hallado = verificar_sin_pii_de_terceros(filas)
    propios = hallado["del_agente"]
    print("guarda de PII: %d filas revisadas en %d columnas de texto · sin "
          "datos de terceros" % (len(filas), len(CON_TEXTO_DE_TERCEROS)))
    if propios:
        # Que la guarda tenga algo que revisar es parte del reporte: "ningun
        # hallazgo" sobre cero coincidencias no prueba nada.
        print("   (%d contactos encontrados y verificados como DEL AGENTE, en "
              "%d perfiles: %s…)"
              % (len(propios), len({h for h, _d in propios}),
                 ", ".join(d for _h, d in propios[:3])))
        print("   son de negocio, no una fuga: el realtor publica su teléfono "
              "en su propio caption. Valdría la pena llevarlos a "
              "pacs.contactos con fuente instagram.")

    crudos = cargar_crudos()
    print("crudos en ig_raw/: %d" % len(crudos))

    malos = {f.get("estado_perfil") for f in filas} - ESTADOS_VALIDOS
    if malos:
        print("ABORTADO: estados fuera de los nueve del check: %s" % malos)
        return 1

    # ── EL CSV Y EL CRUDO TIENEN QUE DECIR LO MISMO ─────────────────────────
    #
    # El crudo es la fuente y el CSV es derivado. Si discrepan, el CSV se
    # genero de una corrida ANTERIOR: sus señales salen de crudos viejos y
    # cargarlo mezcla estados nuevos con señales viejas -- una combinacion que
    # nunca existio.
    #
    # Paso de verdad: el CSV del piloto era de antes de arreglar el detector de
    # privacidad, y traia como `privado` a siete perfiles que el crudo
    # re-diagnosticado llama `sin_grid` y `publico_leido`. Son exactamente los
    # siete falsos positivos que ya habiamos corregido.
    desacuerdos = []
    for f in filas:
        email = (f.get("email") or "").strip().lower()
        c = crudos.get(email)
        if c and c.get("estado_perfil") != f.get("estado_perfil"):
            desacuerdos.append((f.get("handle"), f.get("estado_perfil"),
                                c.get("estado_perfil")))
    if desacuerdos:
        print("")
        print("ABORTADO: el CSV y el crudo discrepan en %d perfiles."
              % len(desacuerdos))
        print("   %-28s %-16s %s" % ("handle", "dice el CSV", "dice el crudo"))
        for h, a, b in desacuerdos[:10]:
            print("   %-28s %-16s %s" % (h, a, b))
        print("")
        print("   El crudo es la fuente; el CSV es derivado. Que discrepen")
        print("   significa que el CSV salio de una corrida anterior, asi que")
        print("   sus señales tampoco son de estos crudos. Hay que volver a")
        print("   derivar el CSV desde ig_raw/ antes de cargar.")
        return 1
    print("coherencia CSV/crudo: los %d perfiles con crudo dicen el mismo "
          "estado" % sum(1 for f in filas
                         if (f.get("email") or "").strip().lower() in crudos))

    with psycopg.connect(url) as con:
        cur = con.cursor()
        emails = [(f.get("email") or "").strip() for f in filas]
        mapa = resolver_realtors(cur, [e for e in emails if e])

        con_realtor = sum(1 for e in emails if e and e.lower() in mapa)
        con_lead = sum(1 for e in emails
                       if e and mapa.get(e.lower(), (None, None))[1])
        sin_crudo = [f.get("handle") for f, e in zip(filas, emails)
                     if e.lower() not in crudos]

        # Un 100% de cruce no dice nada sin saber contra CUANTAS personas
        # distintas. `Email Owner` cruzaba al 100% contra catorce valores sobre
        # 4.386 filas, y esa cobertura perfecta era el sintoma.
        ids = {mapa[e.lower()][0] for e in emails if e.lower() in mapa}
        print("")
        print("EL CRUCE · por email, que es la unica llave del CSV")
        print("   filas con email            : %d de %d"
              % (sum(1 for e in emails if e), len(filas)))
        print("   cruzan con un realtor      : %d (%.1f%%)"
              % (con_realtor, 100.0 * con_realtor / len(filas)))
        print("   realtors DISTINTOS         : %d" % len(ids))
        print("   y de esos, con sf_lead_id  : %d" % con_lead)
        print("   sin crudo en ig_raw/       : %d %s"
              % (len(sin_crudo), sin_crudo[:5]))

        if con_realtor and len(ids) < con_realtor:
            print("")
            print("ABORTADO: %d filas cruzan contra solo %d realtors "
                  "distintos. Un cruce que colapsa muchas filas en pocas "
                  "personas se ve como cobertura perfecta y no lo es."
                  % (con_realtor, len(ids)))
            return 1

        if con_realtor == 0:
            print("")
            print("ABORTADO: ni una fila cruza. Cargar señales que no se pegan")
            print("a nadie es llenar una tabla que despues no se puede leer.")
            return 1

        if not aplicar:
            print("")
            print("(solo reporta; pasar --aplicar para escribir)")
            return 0

        lote = str(uuid.uuid4())
        cur.execute("""
            insert into pacs.upload_batch
                (id, fuente, archivo, es_vigente, filas_esperadas, nota)
            values (%s, %s, 'ig_signals.csv', false, %s, %s)
        """, (lote, FUENTE, len(filas),
              "cruce por email (el CSV no trae sf_lead_id); %d de %d filas "
              "pegadas a un realtor" % (con_realtor, len(filas))))

        n_sen = n_cru = 0
        for f, email in zip(filas, emails):
            rid, _lead = mapa.get(email.lower(), (None, None))
            crudo = crudos.get(email.lower())
            # `capturado_en` es NOT NULL y solo esta en el crudo.
            capturado = (crudo or {}).get("capturado_en")
            if not capturado:
                continue

            senales = {k: v for k, v in f.items()
                       if k not in A_COLUMNA and k not in DE_IDENTIDAD
                       and (v or "").strip()}
            cur.execute("""
                insert into pacs.ig_senales
                    (upload_batch_id, realtor_id, handle, estado_perfil,
                     estado_evidencia, handle_confianza, senales, captions_n,
                     comentarios_n, paginacion_truncada, capturado_en,
                     desajuste_idioma)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (lote, rid, f.get("handle"), f.get("estado_perfil"),
                  (crudo or {}).get("estado_evidencia"),
                  f.get("handle_confianza") or None,
                  json.dumps(senales, ensure_ascii=False),
                  _num(f.get("captions_n")), _num(f.get("comentarios_n")),
                  _bool(f.get("paginacion_truncada")), capturado,
                  _num(f.get("desajuste_idioma"))))
            n_sen += 1

            if crudo is not None:
                cur.execute("""
                    insert into pacs.ig_crudo
                        (upload_batch_id, realtor_id, handle, crudo,
                         capturado_en, via, estado_perfil)
                    values (%s,%s,%s,%s,%s,%s,%s)
                """, (lote, rid, f.get("handle"),
                      json.dumps(crudo, ensure_ascii=False), capturado,
                      crudo.get("via"), crudo.get("estado_perfil")))
                n_cru += 1

        # Recien ahora se enciende, y se apaga el anterior: Instagram SI es
        # fuente de reemplazo -- un raspado nuevo sustituye al viejo entero,
        # al reves que las capturas de Model Match, que acumulan.
        cur.execute("update pacs.upload_batch set es_vigente = false "
                    "where fuente = %s and id <> %s", (FUENTE, lote))
        cur.execute("update pacs.upload_batch set es_vigente = true, "
                    "filas_cargadas = %s where id = %s", (n_sen, lote))
        con.commit()

        cur.execute("select count(*) from pacs.v_ig_senales_current")
        vivas = cur.fetchone()[0]
        cur.execute("select count(*) from pacs.v_ig_crudo_current")
        vivos = cur.fetchone()[0]
        cur.execute("""
            select count(*) from pacs.v_ig_senales_current
             where realtor_id is not null
        """)
        pegadas = cur.fetchone()[0]
        print("")
        print("DESPUES, leido de la base")
        print("   v_ig_senales_current : %d (%d pegadas a un realtor)"
              % (vivas, pegadas))
        print("   v_ig_crudo_current   : %d" % vivos)
        print("   escritas: %d señales, %d crudos" % (n_sen, n_cru))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main("--aplicar" in sys.argv))
    except CargaInstagramFallida as exc:
        print(exc)
        raise SystemExit(1)
