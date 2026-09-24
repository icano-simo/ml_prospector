"""El paquete de evidencia: todo lo que se sabe del realtor, con un id por hecho.

Para qué existe
---------------
Cowork --y mañana la API-- redacta la ficha. Para que lo que escriba se pueda
comprobar, cada frase suya cita los ids de los hechos que la sostienen, y el
validador comprueba que esos ids existen, que los números que escribió están en
ellos y que las citas literales aparecen dentro del texto que dice citar.

Eso solo funciona si los ids son ESTABLES y si el paquete es lo único que la IA
ve. Un hecho sin id no se puede citar, y un hecho que cambia de id entre dos
lecturas rompe la ficha que ya se escribió. Por eso el id sale del hecho
--`IG-2026-05-15-a`, `MM-TX-2026-07-30`-- y no de su posición en una lista.

El `hash_paquete`
-----------------
Es el sha256 del JSON canónico de las evidencias, y **no incluye la fecha de
generación**: si la incluyera, cada lectura daría un hash distinto y la ficha
se marcaría desactualizada cada vez que alguien abre la pantalla.

Con él, la app puede decir «hay datos nuevos: ficha pendiente de actualizar» y
seguir mostrando la anterior, en vez de mostrar una ficha que habla de un
mundo que ya no existe sin avisar.

Lo que NO lleva
---------------
Nombres de buyers ni de sellers, ni calles: no están en la base porque
`captura/transacciones.py` los tira al parsear. Tampoco `marcadores_culturales`
ni `barrios_mencionados` de Instagram, que describen origen y dónde vive la
gente a la que le habla -- ECOA Regulation B.

La guarda es una LISTA BLANCA por campo, no una lista negra: lo que no está
declarado no entra, así que el campo siguiente que alguien agregue al scraper
no se cuela solo.

Código puro: sin IO. Quien lea la base es el que llama.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

#: Sube cuando cambia la FORMA del paquete. Va guardado con cada ficha: una
#: ficha escrita contra un paquete v1 no se puede validar contra un v2 sin
#: mirar qué cambió.
VERSION_PAQUETE = "2026-09-24-v1"

#: Los posts vienen en un solo campo, separados así, y cada uno empieza por su
#: fecha. Es el formato que produce el scraper.
_SEPARADOR_POSTS = "¶"
_RE_POST = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\s*$", re.S)

#: De `senales`, lo único que entra al paquete. Lista blanca.
#:
#: `marcadores_culturales` y `barrios_mencionados` NO están, y no es un olvido:
#: el primero es origen y el segundo describe dónde vive la gente a la que le
#: habla. `citas_por_etiqueta` tampoco, porque son fragmentos recortados con
#: «...» que no coinciden literalmente con ningún post -- y una cita que el
#: validador no puede encontrar en su evidencia es una cita que se rechaza.
_IG_PERMITIDO = (
    "audiencia_dominante", "audiencia_segmentos", "tema_dominante", "temas",
    "idioma_publica_es", "idioma_publica_en",
    "idioma_comentarios_es", "idioma_comentarios_en",
    "destacadas_titulos", "geotags_top", "programas_mencionados",
    "precios_mencionados", "ratio_educa_vs_anuncia", "tipo_post_reel_pct",
    "engagement_rate", "dias_entre_posts_mediana", "hueco_max_dias",
)


def _fecha_de(iso) -> str | None:
    return str(iso)[:10] if iso else None


# ══════════════════════════════════════════════════════════════════════════════
# CONTACTOS · de las cuatro fuentes, normalizados
# ══════════════════════════════════════════════════════════════════════════════
#
# El paquete traía dos contactos y en la base había siete. No era que faltara el
# dato: era que nadie lo juntaba. Están en cuatro sitios y ninguno los tiene
# todos:
#
#   · `pacs.realtors`      el teléfono y el email del archivo original;
#   · `pacs.contactos`     lo que el guardado de una captura acumuló;
#   · el perfil de MM      `Direct:`, `Office:` y los emails del Overview;
#   · sus captions de IG   el teléfono y el email que ella misma publica.
#
# Y HAY QUE NORMALIZAR ANTES DE AGRUPAR. El teléfono de una realtor aparecía en
# cuatro formatos --`(773) 362-5798`, `773-362-5798`, `773.362.5798` y
# `+1773…`-- así que sin normalizar la ficha mostraría cinco teléfonos donde
# hay dos, y ninguno tendría más de una fuente: la marca de «está en una sola
# fuente» diría lo contrario de lo que pasa.

#: La fuente que puede estar vieja. Un valor que SOLO está aquí es el que hay
#: que mirar: el archivo se cargó una vez y no se volvió a tocar.
FUENTE_ARCHIVO = "archivo original"

_RE_TEL = re.compile(r"\+?\d[\d\s().\-]{8,20}\d")
_RE_MAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _tel_normalizado(v) -> str | None:
    """Los últimos 10 dígitos, en E.164. Es lo que hace comparables los
    formatos: `(773) 362-5798` y `+17733625798` son el mismo teléfono."""
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) < 10:
        return None
    return "+1" + d[-10:]


def _mail_normalizado(v) -> str | None:
    s = str(v or "").strip().strip(".,;:").lower()
    return s if _RE_MAIL.fullmatch(s) else None


def contactos_del_realtor(realtor: dict, filas: list[dict] | None,
                          perfil_mm: dict | None, ig: dict | None) -> list[dict]:
    """Todos los contactos, agrupados por valor normalizado y con sus fuentes.

    `difiere` marca el valor cuya ÚNICA fuente es el archivo original habiendo
    otros del mismo canal. No es «está en una sola fuente» a secas: el teléfono
    que ella publica hoy en Instagram también está en una sola, y ese es el
    bueno. El que hay que mirar es el que solo sobrevive en el archivo, porque
    el archivo se cargó una vez y no se volvió a tocar.
    """
    por_valor: dict = {}

    def agregar(canal, crudo, fuente):
        if not crudo:
            return
        if canal == "telefono":
            clave = _tel_normalizado(crudo)
            mostrar = str(crudo).strip()
        elif canal == "email":
            clave = _mail_normalizado(crudo)
            mostrar = clave
        else:
            clave = " ".join(str(crudo).split())
            mostrar = clave
        if not clave:
            return
        d = por_valor.setdefault((canal, clave), {
            "canal": canal, "valor": mostrar, "normalizado": clave,
            "fuentes": []})
        # Se prefiere la forma MÁS LEGIBLE para mostrar: `(773) 362-5798` antes
        # que `+17733625798`. El normalizado es para comparar, no para leer.
        if (canal == "telefono" and str(d["valor"]).startswith("+")
                and not str(mostrar).startswith("+")):
            d["valor"] = mostrar
        if fuente not in d["fuentes"]:
            d["fuentes"].append(fuente)

    # 1 · el archivo original
    agregar("telefono", realtor.get("telefono_e164"), FUENTE_ARCHIVO)
    agregar("email", realtor.get("email_principal"), FUENTE_ARCHIVO)

    # 2 · lo acumulado en `pacs.contactos`
    for f in filas or []:
        agregar(f.get("canal"), f.get("valor"), f.get("fuente") or "sin fuente")

    # 3 · Model Match
    c = (perfil_mm or {}).get("contacto") or {}
    agregar("telefono", c.get("telefono_directo"), "Model Match «Direct»")
    agregar("telefono", c.get("telefono_oficina"), "Model Match «Office»")
    agregar("oficina", c.get("oficina"), "Model Match")
    agregar("direccion", c.get("direccion"), "Model Match")
    for e in (perfil_mm or {}).get("emails") or []:
        agregar("email", e, "Model Match")

    # 4 · lo que ella publica en Instagram
    if ig:
        s = (ig.get("senales") or {})
        texto = s.get("captions_texto") or ""
        if ig.get("handle"):
            agregar("instagram", "@" + str(ig["handle"]).lstrip("@"),
                    "su cuenta")
        for t in _RE_TEL.findall(texto):
            agregar("telefono", t, "Instagram")
        for e in _RE_MAIL.findall(texto):
            agregar("email", e, "Instagram")

    salida = list(por_valor.values())
    por_canal: dict = {}
    for d in salida:
        por_canal[d["canal"]] = por_canal.get(d["canal"], 0) + 1
    for d in salida:
        d["difiere"] = bool(d["fuentes"] == [FUENTE_ARCHIVO]
                            and por_canal[d["canal"]] > 1)
        d["una_sola_fuente"] = len(d["fuentes"]) == 1
    salida.sort(key=lambda d: (d["canal"], -len(d["fuentes"]), d["valor"]))
    return salida


def posts_de_instagram(captions_texto: str | None) -> list[dict]:
    """El campo de captions -> una lista de posts con fecha y texto literal.

    El texto se guarda TAL CUAL, sin recortar: el validador busca la cita de la
    IA dentro de él, y si aquí se recortara, una cita correcta se rechazaría.
    """
    salida: list[dict] = []
    for trozo in (captions_texto or "").split(_SEPARADOR_POSTS):
        m = _RE_POST.match(trozo)
        if not m:
            continue
        texto = m.group(2).strip()
        # El scraper cierra cada post con una comilla y un punto.
        if texto.endswith('".'):
            texto = texto[:-2].rstrip()
        elif texto.endswith('"'):
            texto = texto[:-1].rstrip()
        salida.append({"fecha": m.group(1), "texto": texto})
    return salida


def _ids_de_posts(posts: list[dict]) -> list[tuple[str, dict]]:
    """`IG-2026-05-15-a`, `-b`, `-c` cuando hay varios del mismo día.

    La letra sale del ORDEN dentro de esa fecha, que es el orden en que el
    scraper los entrega y no cambia entre lecturas del mismo volcado. Numerar
    sobre la lista entera haría que agregar un post viejo renumerara todo lo
    posterior, y las fichas ya escritas quedarían citando otra cosa.
    """
    por_fecha: dict = {}
    salida = []
    for p in posts:
        n = por_fecha.get(p["fecha"], 0)
        por_fecha[p["fecha"]] = n + 1
        letra = chr(ord("a") + n) if n < 26 else "z%d" % n
        salida.append(("IG-%s-%s" % (p["fecha"], letra), p))
    return salida


def _corto(valor, n=400):
    s = valor if isinstance(valor, str) else json.dumps(valor,
                                                        ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def construir(*, realtor: dict, evaluacion: dict | None,
              perfil_mm: dict | None, resumen_tx: dict | None,
              filas_tx: list[dict] | None, mercados: list[dict] | None,
              ig: dict | None, contactos: list[dict] | None,
              census: dict | None, veredicto: dict | None,
              salesforce: dict | None = None,
              ahora: dt.datetime | None = None) -> dict:
    """Todo lo que se sabe del realtor, con un id por hecho.

    Cada argumento ya viene leído: este módulo no toca la base. Lo que falta
    entra como `None` y sale del paquete como una evidencia `Pendiente` con su
    motivo, **no como una ausencia**: la IA tiene que poder citar «esto no
    existe todavía» en vez de inventarlo o callarlo.
    """
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    ev: list[dict] = []

    # ── EL VEREDICTO, YA DECIDIDO ───────────────────────────────────────────
    # Va primero y con su id propio. La IA lo muestra y no lo comenta: una IA
    # nunca decide la exclusión.
    ev.append({
        "id": "VEREDICTO", "tipo": "veredicto",
        "estado": (veredicto or {}).get("estado"),
        "motivo": (veredicto or {}).get("motivo"),
        "evidencia": (veredicto or {}).get("evidencia") or {},
        "nota": "Calculado por el código. La IA no lo cambia ni lo comenta.",
    })

    # ── MODEL MATCH · Overview ──────────────────────────────────────────────
    p = perfil_mm or {}
    if p:
        ev.append({
            "id": "MM-OV", "tipo": "modelmatch_overview",
            "buyer_units": p.get("buyer_units"),
            "listing_sold": p.get("listing_sold"),
            "side_focus": p.get("side_focus"),
            "sf_buy": p.get("sf_buy"), "sf_sell": p.get("sf_sell"),
            "los_buyer": p.get("los_buyer"), "los_seller": p.get("los_seller"),
            "buyside_anualizado": p.get("buyside_anualizado"),
            "ventana_meses": p.get("ventana_meses"),
            "tpo_pct": p.get("tpo_pct"),
            "producer_tier": p.get("producer_tier"),
            "capturado_en": _fecha_de(p.get("capturado_en")),
        })

    # ── MODEL MATCH · Transactions ──────────────────────────────────────────
    if resumen_tx:
        r = resumen_tx
        ev.append({
            "id": "MM-TX-RESUMEN", "tipo": "transactions_resumen",
            # Todo ya CALCULADO. La regla dura del prompt es que la IA no
            # calcula números nuevos: si un total no está aquí, no se puede
            # escribir.
            "compras": r.get("compras"), "ventas": r.get("ventas"),
            "loan_mix_compra": r.get("loan_mix_compra"),
            "lenders_compra": r.get("lenders_compra"),
            "lenders_venta": r.get("lenders_venta"),
            "zips_de_compra": r.get("zips_de_compra"),
            "precio_mediano_compra": r.get("precio_mediano_compra"),
            "volumen_compra": r.get("volumen_compra"),
            "volumen_venta": r.get("volumen_venta"),
            "tasas": r.get("tasas"),
            "pendientes_de_prestamo": r.get("pendientes_de_prestamo"),
            "unidades_de_la_casa": r.get("unidades_de_la_casa"),
            "trimestres": r.get("trimestres"),
            "nota_cash": ("«Cash» en Model Match significa «sin loan "
                          "registrado». Menos de 35 días es pendiente."),
        })
    else:
        # Declarado y no ausente, igual que Salesforce y el Census. Sin esto,
        # la IA no tiene cómo citar «no hay Transactions» y la única salida que
        # le queda es callarlo -- y lo que se calla se lee como que no pasa.
        ev.append({
            "id": "MM-TX-RESUMEN", "tipo": "pendiente",
            "pendiente": ("la pestaña Transactions todavía no está capturada. "
                          "Sin ella no se sabe cuáles de sus compras figuran "
                          "como cash ni con qué lender cerraron, y eso NO se "
                          "calcula por diferencia."),
        })
    for f in sorted(filas_tx or [], key=lambda x: x.get("fecha") or "",
                    reverse=True):
        if not f.get("fecha"):
            continue
        ev.append({
            "id": "MM-TX-%s" % f["fecha"], "tipo": "transaccion",
            "fecha": f["fecha"], "lado": f.get("lado"),
            "ciudad": f.get("ciudad"), "zip": f.get("zip"),
            "precio": f.get("precio"), "prestamo": f.get("prestamo"),
            "enganche": f.get("enganche"), "tipo_loan": f.get("tipo"),
            "tasa": f.get("tasa"), "plazo": f.get("plazo"),
            "lender": f.get("lender"), "lo_nombre": f.get("lo_nombre"),
            "estado_prestamo": f.get("estado_prestamo"),
            "recapturar_despues_de": f.get("recapturar_despues_de"),
        })

    # ── MODEL MATCH · mercados ──────────────────────────────────────────────
    for m in mercados or []:
        clave = (m.get("condado_fips") or m.get("etiqueta")
                 or m.get("estado") or "?")
        ev.append({
            "id": "MM-MK-%s" % clave, "tipo": "mercado",
            "nivel": m.get("nivel"), "etiqueta": m.get("etiqueta"),
            "estado": m.get("estado"),
            "rango_desde": m.get("rango_desde"),
            "rango_hasta": m.get("rango_hasta"),
            "de_la_biblioteca": bool(m.get("de_la_biblioteca")),
            "metricas": m.get("metricas") or {},
        })

    # ── INSTAGRAM ───────────────────────────────────────────────────────────
    if ig:
        s = ig.get("senales") or {}
        posts = posts_de_instagram(s.get("captions_texto"))
        for pid, post in _ids_de_posts(posts):
            ev.append({"id": pid, "tipo": "post_instagram",
                       "fecha": post["fecha"], "texto": post["texto"]})
        ev.append({
            "id": "IG-RESUMEN", "tipo": "instagram_resumen",
            "handle": ig.get("handle"),
            "clase_perfil": ig.get("clase_perfil"),
            "utilizable": bool(ig.get("utilizable")),
            "leido_en": _fecha_de(ig.get("capturado_en")),
            "posts_leidos": ig.get("captions_n"),
            "comentarios_leidos": ig.get("comentarios_n"),
            "posts_con_fecha": len(posts),
            **{k: s.get(k) for k in _IG_PERMITIDO if s.get(k) is not None},
        })
        if s.get("comentarios_texto"):
            ev.append({
                "id": "IG-COMENTARIOS", "tipo": "comentarios_instagram",
                "texto": s["comentarios_texto"],
                "nota": ("Comentarios recibidos. Un emoji o un «🔥» no es un "
                         "cliente potencial: si no dice quién escribe ni qué "
                         "busca, no lo es."),
            })

    # ── SALESFORCE ──────────────────────────────────────────────────────────
    if salesforce:
        ev.append({"id": "SF-LEAD", "tipo": "salesforce_lead", **salesforce})
        for i, t in enumerate((salesforce.get("actividades") or [])[:5], 1):
            ev.append({"id": "SF-TASK-%d" % i, "tipo": "salesforce_task", **t})
    else:
        ev.append({
            "id": "SF-LEAD", "tipo": "pendiente",
            "pendiente": ("el sync de Salesforce todavía no corre: no sabemos "
                          "si tiene dueño BD ni qué actividad tiene"),
            "sf_lead_id": realtor.get("sf_lead_id"),
        })

    # ── CONTACTOS ───────────────────────────────────────────────────────────
    # Se arman AQUI, de las cuatro fuentes, y no se reciben ya hechos: el
    # paquete traia dos contactos y en la base habia siete, porque quien
    # llamaba solo pasaba `pacs.contactos`. Armarlos dentro es lo que hace que
    # no dependa de que el que llama se acuerde.
    _SIGLA = {"telefono": "TEL", "email": "MAIL", "instagram": "IG",
              "oficina": "OFI", "direccion": "DIR", "web": "WEB",
              "otro": "OTRO"}
    vistos: dict = {}
    for c in contactos_del_realtor(realtor, contactos, perfil_mm, ig):
        canal = c["canal"]
        fuente = (c["fuentes"] or ["?"])[0]
        base = "CT-%s-%s" % (
            re.sub(r"[^A-Z]", "", (fuente or "").upper())[:4] or "X",
            _SIGLA.get(canal, "OTRO"))
        n = vistos.get(base, 0)
        vistos[base] = n + 1
        ev.append({
            "id": base if not n else "%s-%d" % (base, n + 1),
            "tipo": "contacto", "canal": canal, "valor": c["valor"],
            "normalizado": c["normalizado"], "fuentes": c["fuentes"],
            "difiere": c["difiere"], "una_sola_fuente": c["una_sola_fuente"],
        })

    # ── CENSUS ──────────────────────────────────────────────────────────────
    if census:
        ev.append({"id": "CENSUS-%s" % (census.get("condado_fips") or "?"),
                   "tipo": "census", **census})
    else:
        ev.append({"id": "CENSUS", "tipo": "pendiente",
                   "pendiente": ("el Census por ZIP todavía no está cargado; "
                                 "a nivel condado es un área demasiado grande "
                                 "para describir su zona")})

    # ── PACS-H · las activaciones, con su cadena ────────────────────────────
    #
    # Son INSUMO, no un veredicto: Cowork las usa junto con Transactions,
    # Instagram y Model Match para decidir qué es de verdad un dolor de esta
    # persona. Por eso van con su regla, sus campos y su nota, y no como una
    # lista de dolores ya elegidos.
    #
    # **A UN EXCLUIDO NO SE LE MANDAN.** Un excluido no tiene dolores ni
    # mensajes: ya trabaja con la casa, y escribirle es competirle su cartera a
    # un colega. Dejar las activaciones en su paquete sería poner el material
    # del que salen los dolores encima de la mesa y confiar en que nadie lo
    # use. La guarda va en el dato, no en el aviso.
    excluido = (veredicto or {}).get("estado") == "excluido"
    if excluido:
        ev.append({
            "id": "PACS", "tipo": "pendiente",
            "pendiente": ("este realtor está EXCLUIDO, así que su paquete no "
                          "lleva activaciones PACS-H: no se le escriben "
                          "dolores, ni SMS, ni versión larga. Solo la bio y "
                          "«Lo que significa»."),
        })
    for a in ([] if excluido else
              ((evaluacion or {}).get("resultado") or {}).get("activaciones")
              or []):
        ev.append({
            "id": "PACS-%s" % a.get("qualifier"), "tipo": "activacion_pacs",
            "qualifier": a.get("qualifier"), "familia": a.get("familia"),
            "intensidad": a.get("intensidad"), "grado_evidencia": a.get("grado"),
            "acto_de_habla": a.get("acto"), "regla": a.get("regla_id"),
            "texto_de_la_regla": a.get("texto"),
            "campos_leidos": a.get("campos_leidos") or {},
            "nota": ("El texto de la regla describe la HIPÓTESIS del método, "
                     "no un hecho comprobado de esta persona."),
        })

    ev.sort(key=lambda e: e["id"])
    return {
        "version_paquete": VERSION_PAQUETE,
        "realtor_id": realtor.get("id"),
        "nombre": realtor.get("nombre_completo"),
        "brokerage": realtor.get("brokerage"),
        "estado": realtor.get("estado"),
        "generado_en": ahora.isoformat(timespec="seconds"),
        "evidencias": ev,
        "hash_paquete": huella(ev),
    }


def huella(evidencias: list[dict]) -> str:
    """sha256 del JSON canónico de las evidencias.

    **No entra la fecha de generación.** Si entrara, cada lectura daría un hash
    distinto y la ficha se marcaría desactualizada cada vez que alguien abre la
    pantalla -- que es exactamente lo contrario de lo que el hash existe para
    detectar.
    """
    canonico = json.dumps(evidencias, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def por_id(paquete: dict) -> dict:
    """`{id: evidencia}`. Lo que usa el validador."""
    return {e["id"]: e for e in (paquete or {}).get("evidencias") or []}
