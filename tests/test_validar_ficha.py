"""El validador de la ficha redactada, con casos malos a propósito.

Por qué las pruebas son sobre todo de RECHAZO
---------------------------------------------
Un validador que solo se prueba con fichas buenas no se sabe si valida: una
función que devuelve `[]` siempre pasa todas esas pruebas. Lo que hay que
comprobar es que caza el número inventado, la cita que no existe, el grado que
no corresponde y el término prohibido -- y que NO caza una ficha correcta, que
es el control.

Los datos son inventados con la forma del paquete real.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor.paquete import construir, huella, posts_de_instagram  # noqa: E402
from motor.validar_ficha import (  # noqa: E402
    MAX_SMS,
    secciones_con_problema,
    validar,
)

POST = ("How I meet my clients?? He kept it for a couple months. Worked on "
        "his credit. Once he was ready he called me. We went off to getting "
        "him pre-approved, and off to showings right away!")

PAQUETE = construir(
    realtor={"id": "r-1", "nombre_completo": "AGENTE DE PRUEBA",
             "brokerage": "Una Inmobiliaria", "estado": "IL",
             "sf_lead_id": "00Q000000000000",
             # El archivo original: un teléfono y un email que NO están en
             # ninguna otra fuente. Son los que hay que poder marcar.
             "telefono_e164": "+17735550100",
             "email_principal": "viejo@ejemplo.com"},
    evaluacion={"resultado": {"activaciones": [
        {"qualifier": "P-Q01", "familia": "P", "intensidad": 2, "grado": "E1",
         "acto": "PREGUNTA", "regla_id": "P-Q01-2", "texto": "FHA o DPA",
         "campos_leidos": {"ev2_fha_gob": True}}]}},
    perfil_mm={"buyer_units": 18.0, "sf_buy": 18, "sf_sell": 7,
               "capturado_en": "2026-09-23T23:54:00+00:00",
               "emails": ["agente@ejemplo.com"],
               "contacto": {"telefono_directo": "(773) 362-5798",
                            "oficina": "Una Inmobiliaria"}},
    resumen_tx={
        "compras": {"total": 18, "financiada": 8, "cash_segun_mm": 9,
                    "cash_provisional": 1, "no_leido": 0},
        "ventas": {"total": 7, "financiada": 2, "cash_segun_mm": 4,
                   "cash_provisional": 1, "no_leido": 0},
        "loan_mix_compra": {"Conventional": 5, "FHA": 2, "HE": 1},
        "lenders_compra": {"Guaranteed Rate": 3, "Zillow Home Loans": 2},
        "lenders_venta": {}, "zips_de_compra": {"60638": 3, "60629": 2},
        "precio_mediano_compra": 286000.0, "volumen_compra": 5317000.0,
        "volumen_venta": 2730000.0, "tasas": [6.55, 7.62],
        "pendientes_de_prestamo": [{"fecha": "2026-09-14", "lado": "compra",
                                    "recapturar_despues_de": "2026-10-19"}],
        "unidades_de_la_casa": 0, "trimestres": []},
    filas_tx=[{"fecha": "2026-07-30", "lado": "compra", "ciudad": "Elmwood Park",
               "zip": "60707", "precio": 168000.0, "prestamo": 151000.0,
               "enganche": 17000.0, "tipo": "Conventional", "tasa": 6.55,
               "lender": "Guaranteed Rate Inc", "lo_nombre": "LO 1",
               "estado_prestamo": "financiada"}],
    mercados=[{"nivel": "condado", "etiqueta": "Cook", "estado": "IL",
               "condado_fips": "17031", "metricas": {"mkt_fha": 14.1,
                                                     "fallout": 25.2}}],
    ig={"handle": "agente_de_prueba", "clase_perfil": "realtor_activo",
        "utilizable": True, "captions_n": 20, "comentarios_n": 12,
        "capturado_en": "2026-09-21T20:45:18+00:00",
        "senales": {"captions_texto": "2026-05-15 | %s Hablo Español. "
                                      "Llámame al 773-362-5798 o escribe a "
                                      "agente@ejemplo.com\"." % POST,
                    "comentarios_texto": "Sent you a dm 🙌 ¶ 🔥🔥🔥hmu",
                    "tema_dominante": "celebracion_cierre",
                    "idioma_publica_es": "4", "idioma_publica_en": "16",
                    "marcadores_culturales": "familia:2 | cultura_latina:1",
                    "barrios_mencionados": "Pilsen:2"}},
    # Las filas CRUDAS de `pacs.contactos`. El resto de las fuentes --archivo
    # original, Model Match e Instagram-- las junta `construir`.
    contactos=[{"canal": "telefono", "valor": "(773) 362-5798",
                "fuente": "Instagram"}],
    census=None, veredicto={"estado": "ok", "motivo": "sin operaciones con la casa"},
    salesforce=None)

HASH = PAQUETE["hash_paquete"]


def _ficha(**cambios):
    """Una ficha CORRECTA, con los cambios que pida cada prueba."""
    base = {
        "hash_paquete": HASH,
        "cabecera": {"bio": {
            "texto": "Cierra sobre todo buy side: 18 buys y 7 listings.",
            "evidencias": ["MM-TX-RESUMEN"]}},
        "por_que_ella": {"razones": [
            {"titulo": "Buy side fuerte", "texto": "8 financed buys.",
             "evidencias": ["MM-TX-RESUMEN"],
             "de_donde_sale": {"texto": "Model Match › Transactions.",
                               "evidencias": ["MM-TX-RESUMEN"]}},
            {"titulo": "Muchos cash buyers", "texto": "9 figuran como cash.",
             "evidencias": ["MM-TX-RESUMEN"]},
            {"titulo": "Trabaja el credit", "texto": "Cuenta un caso.",
             "evidencias": ["IG-2026-05-15-a"]}]},
        "dolores": [
            {"dolor": "Buyers que no están listos por credit",
             "evidencia_texto": "el caso que cuenta el 15 may",
             "grado": ["Lo cuenta ella"], "evidencias": ["IG-2026-05-15-a"],
             "pregunta": "¿Cuántos buyers tienes esperando su credit?"},
            {"dolor": "Depende de Guaranteed Rate",
             "evidencia_texto": "3 de 8 financed buys",
             "grado": ["Dato"], "evidencias": ["MM-TX-RESUMEN"],
             "pregunta": "¿Qué pasa cuando no pueden aprobar a un buyer?"}],
        "mensaje": {
            "sms": {"texto": "Hola, soy [tu nombre] de HOMESÍ. Vi tu post del "
                             "buyer que trabajó su credit. ¿Un café de 15 min?",
                    "evidencias": ["IG-2026-05-15-a"]},
            "largo_es": {"texto": "Hola.", "evidencias": ["IG-2026-05-15-a"]},
            "largo_en": {"texto": "Hi.", "evidencias": ["IG-2026-05-15-a"]},
            "canal": {"texto": "Al teléfono que publica.",
                      "evidencias": ["CT-INST-TEL"]},
            "objecion": {"texto": "Ya trabaja con Guaranteed Rate.",
                         "evidencias": ["MM-TX-RESUMEN"]},
            "preguntas": [{"texto": "¿A quién mandas un buyer que no califica?",
                           "evidencias": ["MM-TX-RESUMEN"]}]},
    }
    for k, v in cambios.items():
        base[k] = v
    return base


# ══ 0 · EL CONTROL ═══════════════════════════════════════════════════════════

def test_una_ficha_correcta_pasa():
    """Sin esto, «rechaza todo» pasaría todas las pruebas de abajo."""
    assert validar(_ficha(), PAQUETE) == []


def test_el_paquete_trae_los_ids_que_la_ficha_cita():
    ids = {e["id"] for e in PAQUETE["evidencias"]}
    assert "IG-2026-05-15-a" in ids
    assert "MM-TX-RESUMEN" in ids
    assert "MM-TX-2026-07-30" in ids
    assert "MM-MK-17031" in ids
    assert "PACS-P-Q01" in ids
    assert "VEREDICTO" in ids
    assert "CT-INST-TEL" in ids


# ══ 1 · NÚMERO INVENTADO ═════════════════════════════════════════════════════

def test_un_numero_que_no_esta_en_las_evidencias_se_rechaza():
    """El caso más caro: un número plausible que nadie midió.

    Sale con la misma cara que uno real, y el BD lo dice en la llamada.
    """
    f = _ficha()
    f["cabecera"]["bio"]["texto"] = "Cierra 42 buys y 7 listings."
    p = validar(f, PAQUETE)
    assert any("no está en las evidencias" in x["motivo"] for x in p), p
    assert any("42" in (x["detalle"] or "") for x in p)


def test_un_numero_que_SI_esta_pasa_aunque_se_escriba_distinto():
    """`$286K` contra `286000.0`: es el mismo número con otro formato.

    Rechazarlo sería rechazar un número correcto, y obligaría a quien redacta
    a escribir `286000.0` en la ficha.
    """
    f = _ficha()
    f["cabecera"]["bio"]["texto"] = "Su median purchase price es $286K."
    assert validar(f, PAQUETE) == []


# ══ 2 · CITA QUE NO EXISTE ═══════════════════════════════════════════════════

def test_citar_un_id_que_no_esta_en_el_paquete_se_rechaza():
    f = _ficha()
    f["cabecera"]["bio"]["evidencias"] = ["IG-2020-01-01-a"]
    p = validar(f, PAQUETE)
    assert any("no están en el paquete" in x["motivo"] for x in p), p


def test_una_frase_sin_evidencias_se_rechaza():
    f = _ficha()
    f["cabecera"]["bio"]["evidencias"] = []
    p = validar(f, PAQUETE)
    assert any(x["motivo"] == "frase sin evidencias" for x in p), p


# ══ 3 · TEXTO LITERAL QUE NO ESTÁ EN EL POST ═════════════════════════════════

def test_una_cita_que_no_esta_en_el_post_se_rechaza():
    """Parafrasear y llamarlo cita es lo que hace que el BD lea en voz alta
    algo que la realtor nunca escribió."""
    f = _ficha()
    f["cabecera"]["bio_evidencias_visibles"] = [{
        "texto_literal": "Trabajo con compradores que no califican en el banco",
        "fecha": "2026-05-15", "nota": "x",
        "evidencias": ["IG-2026-05-15-a"]}]
    p = validar(f, PAQUETE)
    assert any("no aparece en la evidencia" in x["motivo"] for x in p), p


def test_una_cita_que_SI_esta_pasa():
    f = _ficha()
    f["cabecera"]["bio_evidencias_visibles"] = [{
        "texto_literal": "He kept it for a couple months. Worked on his credit.",
        "fecha": "2026-05-15", "nota": "x",
        "evidencias": ["IG-2026-05-15-a"]}]
    assert validar(f, PAQUETE) == []


def test_una_cita_recortada_con_puntos_suspensivos_pasa():
    """El «…» del medio es normal al citar; lo que se compara son los trozos."""
    f = _ficha()
    f["cabecera"]["bio_evidencias_visibles"] = [{
        "texto_literal": "He kept it for a couple months… off to showings "
                         "right away!",
        "fecha": "2026-05-15", "nota": "x",
        "evidencias": ["IG-2026-05-15-a"]}]
    assert validar(f, PAQUETE) == []


def test_el_de_donde_sale_de_una_razon_tambien_se_valida():
    """Si no se validara, la razón quedaría comprobada y su justificación no.

    Y la justificación es justo donde alguien pone el número que no se puede
    sostener: la razón dice «se reparten entre varios lenders» y el «De dónde
    sale» dice «25 operaciones entre el 4 ago y el 14 sep».
    """
    f = _ficha()
    f["por_que_ella"]["razones"][0]["de_donde_sale"]["texto"] = \
        "Model Match › Transactions: 99 operaciones."
    p = validar(f, PAQUETE)
    assert any("no está en las evidencias" in x["motivo"] for x in p), p
    assert any("de_donde_sale" in x["seccion"] for x in p), p


def test_una_cita_dentro_del_de_donde_sale_se_valida_como_cita():
    f = _ficha()
    f["por_que_ella"]["razones"][0]["de_donde_sale"]["citas"] = [{
        "texto_literal": "Esto no lo dijo nunca", "fecha": "2026-05-15",
        "nota": "", "evidencias": ["IG-2026-05-15-a"]}]
    p = validar(f, PAQUETE)
    assert any("no aparece en la evidencia" in x["motivo"] for x in p), p


def test_el_grado_detalle_no_cambia_la_regla_del_grado():
    """«Lo cuenta ella · 1 caso» sigue exigiendo citar un post."""
    f = _ficha()
    f["dolores"][0]["grado_detalle"] = "1 caso"
    assert validar(f, PAQUETE) == []
    f["dolores"][0]["evidencias"] = ["MM-TX-RESUMEN"]
    p = validar(f, PAQUETE)
    assert any("el grado no corresponde" in x["motivo"] for x in p), p


# ══ 4 · «LO CUENTA ELLA» SIN FECHA ═══════════════════════════════════════════

def test_una_cita_sin_fecha_se_rechaza():
    """Sin fecha no se puede decir «el 15 de junio dijo», y eso es lo único
    que el BD puede usar."""
    f = _ficha()
    f["cabecera"]["bio_evidencias_visibles"] = [{
        "texto_literal": "Worked on his credit.", "fecha": "", "nota": "x",
        "evidencias": ["IG-2026-05-15-a"]}]
    p = validar(f, PAQUETE)
    assert any(x["motivo"] == "cita sin fecha" for x in p), p


def test_lo_cuenta_ella_sin_citar_un_post_se_rechaza():
    f = _ficha()
    f["dolores"][0]["grado"] = ["Lo cuenta ella"]
    f["dolores"][0]["evidencias"] = ["MM-TX-RESUMEN"]
    p = validar(f, PAQUETE)
    assert any("el grado no corresponde" in x["motivo"] for x in p), p


def test_Dato_sin_citar_Model_Match_ni_Salesforce_se_rechaza():
    f = _ficha()
    f["dolores"][1]["grado"] = ["Dato"]
    f["dolores"][1]["evidencias"] = ["IG-2026-05-15-a"]
    p = validar(f, PAQUETE)
    assert any("el grado no corresponde" in x["motivo"] for x in p), p


def test_Hipotesis_no_exige_ninguna_fuente_en_particular():
    """Es una inferencia: lo que se le exige es que esté marcada, no de dónde
    sale."""
    f = _ficha()
    f["dolores"][0]["grado"] = ["Hipótesis"]
    f["dolores"][0]["evidencias"] = ["MM-TX-RESUMEN"]
    f["dolores"][0]["evidencia_texto"] = "su reparto de lenders"
    assert validar(f, PAQUETE) == []


# ══ 5 · TÉRMINOS PROHIBIDOS ══════════════════════════════════════════════════

def test_el_vocabulario_de_lending_traducido_se_rechaza():
    f = _ficha()
    f["por_que_ella"]["razones"][0]["texto"] = "8 compras financiadas."
    p = validar(f, PAQUETE)
    assert any("traducido" in x["motivo"] for x in p), p


def test_afirmar_que_pago_en_efectivo_se_rechaza():
    """«Cash» en Model Match es «sin loan registrado»."""
    f = _ficha()
    f["por_que_ella"]["razones"][1]["texto"] = "9 de sus buyers pagó en efectivo."
    p = validar(f, PAQUETE)
    assert any("en efectivo" in x["motivo"] for x in p), p


def test_usar_el_lender_que_le_refiere_como_gancho_se_rechaza():
    """RESPA §8: es contexto, nunca gancho."""
    f = _ficha()
    f["mensaje"]["sms"]["texto"] = ("Hola, vi que trabajas con un referral "
                                    "partner. Podemos intercambiar referidos.")
    p = validar(f, PAQUETE)
    assert any("RESPA" in (x["detalle"] or "") or "gancho" in x["motivo"]
               for x in p), p


def test_segmentar_por_origen_en_el_mensaje_se_rechaza():
    f = _ficha()
    f["mensaje"]["sms"]["texto"] = "Hola, ayudamos a compradores hispanos."
    p = validar(f, PAQUETE)
    assert any("origen" in x["motivo"] for x in p), p


def test_la_palabra_hispana_dentro_de_una_cita_suya_NO_se_rechaza():
    """Es su palabra, no una segmentación nuestra. Solo se prohíbe en el
    mensaje, que es lo que le llega a ella."""
    f = _ficha()
    f["cabecera"]["bio"]["texto"] = ("Dice que ayuda a su comunidad hispana, "
                                     "en sus palabras.")
    assert validar(f, PAQUETE) == []


# ══ 6 · EL SMS ═══════════════════════════════════════════════════════════════

def test_un_SMS_largo_se_rechaza():
    f = _ficha()
    f["mensaje"]["sms"]["texto"] = "Hola. " * 100
    p = validar(f, PAQUETE)
    assert any("pasa de %d caracteres" % MAX_SMS in x["motivo"] for x in p), p


def test_un_SMS_que_menciona_sus_transacciones_se_rechaza():
    """Nombrarle su lender es decirle que le miramos las operaciones antes de
    escribirle."""
    f = _ficha()
    f["mensaje"]["sms"]["texto"] = ("Hola, vi que cierras con Guaranteed Rate. "
                                    "¿Un café?")
    p = validar(f, PAQUETE)
    assert any("menciona sus transacciones" in x["motivo"] for x in p), p


def test_un_SMS_que_menciona_un_ZIP_suyo_tambien_se_rechaza():
    f = _ficha()
    f["mensaje"]["sms"]["texto"] = "Hola, veo que compras mucho en 60638."
    p = validar(f, PAQUETE)
    assert any("menciona sus transacciones" in x["motivo"] for x in p), p


# ══ 7 · FORMA ════════════════════════════════════════════════════════════════

def test_tienen_que_ser_exactamente_3_razones():
    f = _ficha()
    f["por_que_ella"]["razones"] = f["por_que_ella"]["razones"][:2]
    p = validar(f, PAQUETE)
    assert any("3 razones" in x["motivo"] for x in p), p


def test_un_dolor_sin_pregunta_se_rechaza():
    f = _ficha()
    f["dolores"][0]["pregunta"] = "Tiene buyers con credit bajo."
    p = validar(f, PAQUETE)
    assert any("pregunta para validarlo" in x["motivo"] for x in p), p


def test_una_ficha_de_otro_paquete_se_marca():
    f = _ficha()
    f["hash_paquete"] = "0" * 64
    p = validar(f, PAQUETE)
    assert any("otro paquete" in x["motivo"] for x in p), p


def test_las_secciones_con_problema_se_pueden_apagar_una_por_una():
    """La pantalla apaga LA SECCIÓN que falló y muestra el resto."""
    f = _ficha()
    f["cabecera"]["bio"]["texto"] = "Cierra 42 buys."
    s = secciones_con_problema(validar(f, PAQUETE))
    assert "cabecera" in s
    assert "dolores" not in s and "mensaje" not in s


# ══ 8 · EL PAQUETE ═══════════════════════════════════════════════════════════

def test_los_posts_se_parten_por_fecha_y_conservan_el_texto_entero():
    posts = posts_de_instagram(
        "2026-07-03 | Primero\". ¶ 2026-05-15 | Segundo con | barra\".")
    assert [p["fecha"] for p in posts] == ["2026-07-03", "2026-05-15"]
    assert posts[1]["texto"] == "Segundo con | barra"


def test_varios_posts_del_mismo_dia_llevan_letra():
    posts = posts_de_instagram("2026-05-15 | Uno\". ¶ 2026-05-15 | Dos\".")
    p = construir(realtor={"id": "r"}, evaluacion=None, perfil_mm=None,
                  resumen_tx=None, filas_tx=None, mercados=None,
                  ig={"senales": {"captions_texto":
                                  "2026-05-15 | Uno\". ¶ 2026-05-15 | Dos\"."}},
                  contactos=None, census=None, veredicto=None)
    ids = [e["id"] for e in p["evidencias"] if e["tipo"] == "post_instagram"]
    assert ids == ["IG-2026-05-15-a", "IG-2026-05-15-b"], ids
    assert len(posts) == 2


def test_el_paquete_no_lleva_marcadores_culturales_ni_barrios():
    """Lista blanca: origen y dónde vive la gente a la que le habla no entran.

    `captions_texto` sí entra, y puede contener lo que ella escribió sobre sí
    misma -- eso es su palabra y el prompt permite citarlo solo en la bio.
    """
    import json

    entero = json.dumps(PAQUETE, ensure_ascii=False)
    assert "marcadores_culturales" not in entero
    assert "barrios_mencionados" not in entero
    assert "cultura_latina" not in entero
    assert "Pilsen" not in entero


def test_el_hash_no_cambia_entre_dos_lecturas_iguales():
    """Si cambiara, la ficha se marcaría desactualizada cada vez que alguien
    abre la pantalla -- lo contrario de lo que el hash existe para detectar."""
    a = construir(realtor={"id": "r-1"}, evaluacion=None, perfil_mm=None,
                  resumen_tx=None, filas_tx=None, mercados=None, ig=None,
                  contactos=None, census=None, veredicto=None)
    b = construir(realtor={"id": "r-1"}, evaluacion=None, perfil_mm=None,
                  resumen_tx=None, filas_tx=None, mercados=None, ig=None,
                  contactos=None, census=None, veredicto=None)
    assert a["hash_paquete"] == b["hash_paquete"]
    assert a["generado_en"] or True   # cambia, y no entra en el hash


def test_el_hash_SI_cambia_cuando_cambia_un_dato():
    a = construir(realtor={"id": "r-1"}, evaluacion=None, perfil_mm=None,
                  resumen_tx=None, filas_tx=None, mercados=None, ig=None,
                  contactos=None, census=None, veredicto={"estado": "ok"})
    b = construir(realtor={"id": "r-1"}, evaluacion=None, perfil_mm=None,
                  resumen_tx=None, filas_tx=None, mercados=None, ig=None,
                  contactos=None, census=None, veredicto={"estado": "excluido"})
    assert a["hash_paquete"] != b["hash_paquete"]


def test_lo_que_falta_entra_como_pendiente_declarado_y_no_como_ausencia():
    """La IA tiene que poder citar «esto no existe todavía» en vez de
    inventarlo o callarlo."""
    ids = {e["id"]: e for e in PAQUETE["evidencias"]}
    assert ids["SF-LEAD"]["tipo"] == "pendiente"
    assert "sync de Salesforce" in ids["SF-LEAD"]["pendiente"]
    assert ids["CENSUS"]["tipo"] == "pendiente"


def test_sin_Transactions_tambien_hay_un_pendiente_que_se_puede_citar():
    """Lo que se calla se lee como que no pasa.

    Sin esta evidencia, la única salida que le queda a la IA es no mencionar
    Transactions -- y la ficha sale hablando de sus compras sin decir que de la
    mitad no sabemos con qué lender cerraron.
    """
    p = construir(realtor={"id": "r"}, evaluacion=None, perfil_mm=None,
                  resumen_tx=None, filas_tx=None, mercados=None, ig=None,
                  contactos=None, census=None, veredicto=None)
    e = {x["id"]: x for x in p["evidencias"]}["MM-TX-RESUMEN"]
    assert e["tipo"] == "pendiente"
    assert "calcula por diferencia" in e["pendiente"]


def test_el_veredicto_va_en_el_paquete_y_dice_que_no_se_toca():
    ids = {e["id"]: e for e in PAQUETE["evidencias"]}
    assert ids["VEREDICTO"]["estado"] == "ok"
    assert "no lo cambia" in ids["VEREDICTO"]["nota"]


# ══ 9 · LOS CONTACTOS, DE LAS CUATRO FUENTES ═════════════════════════════════

def test_los_contactos_salen_de_las_cuatro_fuentes():
    """El paquete traía 2 contactos y en la base había 7.

    No faltaba el dato: faltaba juntarlo. Están en el archivo original, en
    `pacs.contactos`, en el perfil de Model Match y en sus propios captions,
    y ninguna de las cuatro los tiene todos.
    """
    cts = {e["id"]: e for e in PAQUETE["evidencias"]
           if e["tipo"] == "contacto"}
    fuentes = {f for e in cts.values() for f in e["fuentes"]}
    assert "archivo original" in fuentes
    assert "Instagram" in fuentes
    assert any("Model Match" in f for f in fuentes)
    assert {e["canal"] for e in cts.values()} >= {"telefono", "email",
                                                  "instagram"}


def test_el_mismo_telefono_en_varios_formatos_es_UN_contacto():
    """`(773) 362-5798`, `773-362-5798` y `+17733625798` son el mismo número.

    Sin normalizar antes de agrupar, la ficha mostraría cinco teléfonos donde
    hay dos -- y ninguno tendría más de una fuente, así que la marca de «está
    en una sola fuente» diría lo contrario de lo que pasa.
    """
    from motor.paquete import contactos_del_realtor

    cs = contactos_del_realtor(
        {"telefono_e164": "+17733625798"},
        [{"canal": "telefono", "valor": "773.362.5798", "fuente": "lote"}],
        {"contacto": {"telefono_directo": "(773) 362-5798"}},
        {"senales": {"captions_texto": "2026-01-01 | Llámame al 773-362-5798"}})
    tels = [c for c in cs if c["canal"] == "telefono"]
    assert len(tels) == 1, tels
    assert len(tels[0]["fuentes"]) == 4, tels[0]["fuentes"]
    # Y se muestra la forma legible, no la normalizada.
    assert not tels[0]["valor"].startswith("+")


def test_se_marca_el_que_SOLO_esta_en_el_archivo_original():
    """No es «está en una sola fuente» a secas: el teléfono que ella publica
    hoy en Instagram también está en una sola, y ese es el bueno. El que hay
    que mirar es el que solo sobrevive en el archivo."""
    cts = [e for e in PAQUETE["evidencias"] if e["tipo"] == "contacto"]
    viejo = next(c for c in cts if c["valor"] == "viejo@ejemplo.com")
    nuevo = next(c for c in cts if c["valor"] == "agente@ejemplo.com")
    assert viejo["difiere"] is True
    assert nuevo["difiere"] is False
    ig = next(c for c in cts if c["canal"] == "instagram")
    assert ig["difiere"] is False, "su cuenta no es un dato dudoso"


# ══ 10 · UN EXCLUIDO NO TIENE DOLORES NI MENSAJE ═════════════════════════════

def _paquete_excluido():
    return construir(
        realtor={"id": "r-2", "nombre_completo": "EXCLUIDO DE PRUEBA"},
        evaluacion={"resultado": {"activaciones": [
            {"qualifier": "P-Q01", "familia": "P", "intensidad": 3,
             "grado": "E0", "regla_id": "P-Q01-1", "texto": "x",
             "campos_leidos": {}}]}},
        perfil_mm=None, resumen_tx=None, filas_tx=None, mercados=None,
        ig=None, contactos=None, census=None,
        veredicto={"estado": "excluido",
                   "motivo": "ya trabaja con Supreme Lending"})


def test_el_paquete_de_un_excluido_no_lleva_activaciones():
    """La guarda va en el DATO, no en el aviso.

    Dejar las activaciones sería poner el material del que salen los dolores
    encima de la mesa y confiar en que nadie lo use.
    """
    p = _paquete_excluido()
    tipos = [e["tipo"] for e in p["evidencias"]]
    assert "activacion_pacs" not in tipos
    e = {x["id"]: x for x in p["evidencias"]}["PACS"]
    assert e["tipo"] == "pendiente"
    assert "EXCLUIDO" in e["pendiente"]


def test_el_validador_rechaza_dolores_y_mensaje_de_un_excluido():
    p = _paquete_excluido()
    f = {"hash_paquete": p["hash_paquete"],
         "dolores": [{"dolor": "x", "evidencia_texto": "y",
                      "grado": ["Hipótesis"], "pregunta": "¿?",
                      "evidencias": ["VEREDICTO"]}],
         "mensaje": {"sms": {"texto": "Hi", "evidencias": ["VEREDICTO"]}}}
    problemas = validar(f, p)
    assert any(x["seccion"] == "dolores" and "excluido" in x["motivo"]
               for x in problemas), problemas
    assert any(x["seccion"] == "mensaje" and "excluido" in x["motivo"]
               for x in problemas), problemas


def test_un_excluido_SI_puede_tener_bio():
    """«Solo la bio y lo que significa». No se apaga la ficha entera."""
    p = _paquete_excluido()
    f = {"hash_paquete": p["hash_paquete"],
         "cabecera": {"bio": {"texto": "Trabaja con la casa.",
                              "evidencias": ["VEREDICTO"]}}}
    assert validar(f, p) == []


# ══ 11 · EL GRADO, POR FUENTE EXACTA ═════════════════════════════════════════

def test_el_mercado_y_el_Census_NO_sostienen_un_Dato():
    """Son estadísticas del condado, no de esta persona.

    De «en Cook el 14 % son FHA» a «sus buyers usan FHA» hay un salto que
    alguien tiene que validar en la llamada, y llamarlo Dato lo borra.
    """
    f = _ficha()
    f["dolores"][1]["grado"] = ["Dato"]
    f["dolores"][1]["evidencias"] = ["MM-MK-17031"]
    f["dolores"][1]["evidencia_texto"] = "el fallout del condado"
    p = validar(f, PAQUETE)
    assert any("el grado no corresponde" in x["motivo"] for x in p), p


def test_MM_TX_y_MM_OV_si_sostienen_un_Dato():
    f = _ficha()
    for ident in ("MM-TX-RESUMEN", "MM-OV", "MM-TX-2026-07-30"):
        f["dolores"][1]["grado"] = ["Dato"]
        f["dolores"][1]["evidencias"] = [ident]
        f["dolores"][1]["evidencia_texto"] = "su registro"
        assert validar(f, PAQUETE) == [], ident


# ══ 12 · EL IDIOMA DEL SMS ═══════════════════════════════════════════════════

def test_un_SMS_en_espanol_con_evidencia_de_idioma_pasa():
    """El fixture tiene 4 posts en español y un «Hablo Español» suyo."""
    assert validar(_ficha(), PAQUETE) == []


def test_un_SMS_en_espanol_SIN_evidencia_de_idioma_se_rechaza():
    """Es la regla de compliance más fácil de romper sin darse cuenta.

    Un apellido hispano y un SMS en español parecen una cortesía. No lo son:
    es inferir origen y decidir el trato a partir de él.
    """
    p = construir(
        realtor={"id": "r-3", "nombre_completo": "APELLIDO HISPANO"},
        evaluacion=None, perfil_mm=None, resumen_tx=None, filas_tx=None,
        mercados=None,
        ig={"handle": "h", "senales": {
            "captions_texto": "2026-01-01 | Just listed in Chicago",
            "idioma_publica_es": "0", "idioma_publica_en": "20"}},
        contactos=None, census=None, veredicto={"estado": "ok"})
    f = {"hash_paquete": p["hash_paquete"], "mensaje": {
        "sms": {"texto": "Hola, ¿tienes 15 min esta semana para un café?",
                "evidencias": ["VEREDICTO"]}}}
    problemas = validar(f, p)
    assert any("evidencia de idioma" in x["motivo"] for x in problemas), problemas


def test_un_SMS_en_ingles_no_necesita_evidencia_de_idioma():
    """El control: la regla no es «no escribas en español», es «no lo decidas
    por el nombre»."""
    p = construir(
        realtor={"id": "r-4", "nombre_completo": "APELLIDO HISPANO"},
        evaluacion=None, perfil_mm=None, resumen_tx=None, filas_tx=None,
        mercados=None, ig=None, contactos=None, census=None,
        veredicto={"estado": "ok"})
    f = {"hash_paquete": p["hash_paquete"], "mensaje": {
        "sms": {"texto": "Hi, open to a quick 15 min chat this week?",
                "evidencias": ["VEREDICTO"]}}}
    assert validar(f, p) == []


# ══ 13 · EL ENCAJE ═══════════════════════════════════════════════════════════

def test_el_encaje_exige_una_de_las_tres_clases():
    f = _ficha()
    f["encaje"] = {"clase": "Buenísimo", "razones": [
        {"texto": "a", "evidencias": ["MM-TX-RESUMEN"]},
        {"texto": "b", "evidencias": ["MM-TX-RESUMEN"]}]}
    p = validar(f, PAQUETE)
    assert any("no es una de las tres" in x["motivo"] for x in p), p


def test_las_razones_del_encaje_se_validan_como_cualquier_frase():
    """El encaje es juicio, pero el juicio tiene que apoyarse en algo."""
    f = _ficha()
    f["encaje"] = {"clase": "Nutrición", "razones": [
        {"texto": "Cierra 42 buys al año.", "evidencias": ["MM-TX-RESUMEN"]},
        {"texto": "Un solo lender.", "evidencias": ["MM-TX-RESUMEN"]}]}
    p = validar(f, PAQUETE)
    assert any("no está en las evidencias" in x["motivo"] for x in p), p


def test_un_encaje_correcto_pasa():
    f = _ficha()
    f["encaje"] = {"clase": "Cliente ideal", "razones": [
        {"texto": "8 financed buys repartidos.",
         "evidencias": ["MM-TX-RESUMEN"]},
        {"texto": "Ningún lender pasa de 3.", "evidencias": ["MM-TX-RESUMEN"]}]}
    assert validar(f, PAQUETE) == []


def _correr():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    fallas = []
    for nombre, fn in fns:
        try:
            fn()
            print("  ok   %s" % nombre)
        except Exception as exc:  # noqa: BLE001
            fallas.append((nombre, exc))
            print("  FALLA %s -- %r" % (nombre, exc))
    print("")
    print("  %d pruebas, %d fallas" % (len(fns), len(fallas)))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(_correr())
