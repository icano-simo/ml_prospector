"""El dossier A–G: el perfil de un realtor, de punta a punta.

Los siete bloques, en el orden en que se leen
---------------------------------------------
  A   quién es
  B   qué clase de realtor es -- la narrativa, en prosa
  C   su mercado: el condado DOMINANTE, no los cuatro
  D   la hipótesis principal, con fuerza, grado y la regla que la activó
  E   cómo abrir: el gancho literal de la ficha
  E2  ángulo y munición, literales de la matriz
  F   lo que NUNCA se le dice
  G   la pregunta que cierra la brecha

Nada de esto se inventa
-----------------------
El enunciado, el ángulo y la munición son literales de la hoja 8. El gancho es
literal de la ficha del corpus. La narrativa se compone de campos con su fuente
declarada. Lo único escrito aquí es el orden y las transiciones.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from motor.nunca import BLOQUE_F, verificar_nunca
from motor.qualifiers import ficha as ficha_q

#: La pregunta del bloque G. Es la misma para todos a propósito: cierra la
#: categoría vacía en el 100% de las filas, que es lo único que sabemos que
#: falta en todas.
PREGUNTA_DE_BRECHA = (
    "¿Con qué lender estás cerrando hoy, y qué es lo que más se te complica "
    "con ellos — el pre-approval, los tiempos o el closing?")


@dataclass
class Bloque:
    letra: str
    titulo: str
    #: Prosa, cuando el bloque se lee; `datos` cuando se mira.
    texto: str = ""
    datos: list = field(default_factory=list)
    #: De dónde salió, literal, para que nadie lo reescriba creyendo que es
    #: redacción nuestra.
    fuente: str = ""
    vacio_porque: str = ""

    def __post_init__(self) -> None:
        # Corre sobre el texto Y sobre los datos: el bloque D trae el enunciado
        # de la matriz y el C la lectura del contraste, y los dos son prosa que
        # el BD copia. Solo el bloque F se exceptua -- es la lista de lo que NO
        # se dice, asi que por definicion contiene las frases prohibidas.
        if self.letra != "F":
            if self.texto:
                verificar_nunca(self.texto)
            for d in self.datos:
                for v in (d.values() if isinstance(d, dict) else []):
                    if isinstance(v, str):
                        verificar_nunca(v)


def armar_dossier(*, realtor: dict, narrativa: str, cabecera: dict,
                  hipotesis: list, lecturas: list, perfil_zona: dict | None,
                  condado_dominante: str | None, gancho: str,
                  gancho_fuente: str) -> list[Bloque]:
    """Los siete bloques, con lo que haya. Lo que falta dice por qué falta."""
    nombre = realtor.get("nombre_mostrado") or realtor.get("nombre_completo")
    bloques: list[Bloque] = []

    # ── A · quién es ────────────────────────────────────────────────────────
    datos_a = [("nombre", nombre),
               ("brokerage", realtor.get("brokerage")),
               ("estado", realtor.get("estado_nombre")
                or realtor.get("estado")),
               ("email", realtor.get("email_principal")),
               ("teléfono", realtor.get("telefono_e164")),
               ("Lead de Salesforce", realtor.get("sf_lead_id"))]
    bloques.append(Bloque(
        "A", "Quién es",
        datos=[{"k": k, "v": v} for k, v in datos_a if v],
        fuente="pacs.realtors",
        vacio_porque="" if realtor.get("sf_lead_id")
                     else "sin Lead ID: la captura se pega por MMI Agent ID"))

    # ── B · qué clase de realtor es ─────────────────────────────────────────
    bloques.append(Bloque(
        "B", "Qué clase de realtor es", texto=narrativa,
        fuente="libro + Model Match, cada cifra con su ventana en el texto"))

    # ── C · su mercado ──────────────────────────────────────────────────────
    dom = next((l for l in lecturas if l.get("papel", "").startswith("dominante")),
               None)
    if dom:
        c = Bloque("C", "Su mercado · %s" % (condado_dominante or dom["geografia"]),
                   datos=[{"k": "él", "v": dom.get("valor_agente")},
                          {"k": "su mercado", "v": dom.get("valor_mercado")},
                          {"k": "veces", "v": dom.get("veces")}],
                   fuente="pacs.mercados, bloque de Market Signals de su "
                          "condado dominante")
        c.texto = dom.get("que_dice_del_borrower", "")
        bloques.append(c)
    else:
        bloques.append(Bloque(
            "C", "Su mercado", vacio_porque=(
                "no hay contraste contra su condado dominante: falta capturar "
                "su Market Signals, o falta resolver en qué condado opera")))

    # ── D · la hipótesis principal ──────────────────────────────────────────
    principal = next((h for h in hipotesis if h.get("papel") == "principal"),
                     None)
    if principal:
        bloques.append(Bloque(
            "D", "La hipótesis principal · %s" % principal["qualifier"],
            texto=principal.get("enunciado") or "",
            datos=[{"k": "fuerza", "v": "%s/3" % principal.get("intensidad")},
                   {"k": "grado de evidencia", "v": principal.get("grado")},
                   {"k": "acto de habla", "v": principal.get("acto")},
                   {"k": "se activó porque", "v": principal.get("regla")},
                   {"k": "regla", "v": principal.get("regla_id")}],
            fuente="enunciado literal de la matriz, hoja 8 · Qualifiers v2"))
    else:
        bloques.append(Bloque(
            "D", "La hipótesis principal", vacio_porque=(
                "ninguna hipótesis alcanza intensidad acreditable. El primer "
                "mensaje abre por la pregunta del bloque G.")))

    # ── E · cómo abrir ──────────────────────────────────────────────────────
    bloques.append(Bloque("E", "Cómo abrir", texto=gancho,
                          fuente=gancho_fuente))

    # ── E2 · ángulo y munición ──────────────────────────────────────────────
    if principal:
        f = ficha_q(principal["qualifier"])
        e2 = Bloque(
            "E2", "Ángulo y munición",
            datos=[{"k": "ángulo", "v": f.get("angulo_que_activa")},
                   {"k": "munición", "v": f.get("municion_PR_GC")},
                   {"k": "ruta de copy", "v": f.get("ruta_de_copy")}],
            fuente="literales de la matriz, hoja 8")
        if not f:
            e2.vacio_porque = ("%s no está en el banco de qualifiers: sin "
                               "ángulo, el BD sabe qué le duele y no sabe qué "
                               "ofrecerle" % principal["qualifier"])
        bloques.append(e2)
    else:
        bloques.append(Bloque("E2", "Ángulo y munición", vacio_porque=(
            "sin hipótesis principal no hay ángulo que activar")))

    # ── F · lo que nunca se le dice ─────────────────────────────────────────
    bloques.append(Bloque(
        "F", "Lo que nunca se le dice",
        datos=[dict(x) for x in BLOQUE_F],
        fuente="regla ejecutable: `motor/nunca.py` revienta la construcción de "
               "cualquier texto que lo diga"))

    # ── G · la pregunta que cierra la brecha ────────────────────────────────
    bloques.append(Bloque(
        "G", "La pregunta que cierra la brecha", texto=PREGUNTA_DE_BRECHA,
        fuente="va igual en todas: es lo único que sabemos que falta en el "
               "100% de las filas"))

    return bloques
