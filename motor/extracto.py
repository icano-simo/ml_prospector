"""El extracto: el material exacto con el que se escribe.

Un solo objeto
--------------
Lo que devuelve `/api/extracto` es literalmente lo que va a `insumos`. Si el
extracto y los insumos se calcularan en dos sitios, la verificación compararía
el texto contra algo distinto de lo que se leyó -- y una guarda que compara
contra otra cosa es peor que no tenerla, porque aprueba.

El vocabulario cerrado
----------------------
El extracto lleva `_vocabulario`: los conjuntos CERRADOS contra los que se
puede comprobar que el texto no nombró algo ajeno.

  condados   los 2.261 de `pacs.census_condados`
  programas  la lista declarada de abajo
  lenders    los que el sistema conoce, de `pacs.lenders` y `pacs.originadores`

Lo que ese vocabulario NO puede atrapar está dicho en `verificar_entidades`:
un lender que el sistema nunca vio. Una guarda que parece completa y no lo es
se confía, y ahí es donde entra lo inventado.
"""
from __future__ import annotations

#: Los programas hipotecarios que el copy puede nombrar. Cerrado a propósito:
#: si el texto nombra uno que no está en la munición ni en el mix del agente,
#: se lo inventó.
PROGRAMAS = (
    "FHA", "VA", "USDA", "203k", "HELOC", "ITIN", "HomeReady", "Home Possible",
    "bank statement", "DSCR", "DPA", "down payment assistance", "jumbo",
    "conforming", "convencional", "conventional", "HE", "home equity",
    "reverse", "Tax ID MAX", "Supreme Dream", "EAD",
)


def armar_extracto(*, realtor: dict, narrativa: str, cabecera: dict,
                   hipotesis: list, lecturas: list, perfil_zona: dict | None,
                   condado_dominante: str | None, gancho: dict,
                   cobertura: dict, evaluacion: dict | None,
                   instagram: list | None = None,
                   vocabulario: dict | None = None) -> dict:
    """El extracto completo. Es lo que se lee Y lo que se verifica."""
    ev = evaluacion or {}
    principal = next((h for h in hipotesis if h.get("papel") == "principal"),
                     None)
    dominante = next((l for l in lecturas
                      if str(l.get("papel", "")).startswith("dominante")), None)

    extracto = {
        "identidad": {
            "nombre": realtor.get("nombre_mostrado"),
            "brokerage": realtor.get("brokerage"),
            "estado": realtor.get("estado"),
            "estado_nombre": realtor.get("estado_nombre"),
            "condado_dominante": condado_dominante,
        },
        "narrativa": narrativa,
        "diagnostico": {
            "nivel": cabecera.get("nivel"),
            "acto_de_habla": cabecera.get("acto_de_habla"),
            "confianza": cabecera.get("confianza"),
            "gating": cabecera.get("gating"),
        },
        "qualifier_principal": principal and {
            "qualifier": principal.get("qualifier"),
            "enunciado": principal.get("enunciado"),
            "fuerza": principal.get("intensidad"),
            "grado": principal.get("grado"),
            "regla": principal.get("regla"),
            "regla_id": principal.get("regla_id"),
            "angulo": principal.get("angulo"),
            "municion": principal.get("municion"),
        },
        "secundarios": [
            {"qualifier": h["qualifier"], "enunciado": h.get("enunciado"),
             "fuerza": h.get("intensidad"), "grado": h.get("grado")}
            for h in hipotesis if h.get("papel") == "secundario"],
        "moduladores": list(ev.get("moduladores") or []),
        "gancho": gancho,
        # El contraste CON SU DENOMINADOR: un porcentaje sin base no se puede
        # citar, y es lo primero que un texto generado convierte en afirmación.
        "contraste": dominante and {
            "geografia": dominante.get("geografia"),
            "el_agente": dominante.get("valor_agente"),
            "su_mercado": dominante.get("valor_mercado"),
            "veces": dominante.get("veces"),
            "activa": dominante.get("afirma"),
            "evidencia": dominante.get("evidencia"),
        },
        "perfil_del_comprador": perfil_zona,
        "podemos_originarle": cobertura,
        "no_se_pudo_evaluar": {
            "campos_ausentes": list(ev.get("campos_ausentes") or []),
            "reglas_no_evaluadas": len(ev.get("no_evaluadas") or []),
        },
        # Cuando Instagram esté cargado: lo que ÉL escribió es lo único que un
        # realtor reconoce como suyo.
        "instagram": instagram or [],
        # Los conjuntos CERRADOS contra los que se comprueba. `programas` va
        # siempre: es la lista declarada y no depende de la base.
        "_vocabulario": {"programas": list(PROGRAMAS), **(vocabulario or {})},
    }
    return extracto


def _todo_el_texto(extracto: dict) -> str:
    """Todo lo que el extracto dice, en una cadena.

    La regla es «nada que no esté en el extracto», así que lo permitido es lo
    que el extracto MENCIONA, mire donde mire. Buscar solo en dos campos
    elegidos a mano deja fuera lo que el propio extracto ya decía -- y eso
    rechaza texto correcto, que es como una guarda se acaba desactivando.
    """
    partes: list[str] = []

    def recorrer(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k != "_vocabulario":
                    recorrer(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                recorrer(x)
        elif isinstance(v, str):
            partes.append(v)

    recorrer(extracto)
    return " ".join(partes)


def vocabulario_del_extracto(extracto: dict) -> dict:
    """Lo que el texto SÍ puede nombrar, sacado del propio extracto."""
    ident = extracto.get("identidad") or {}
    contraste = extracto.get("contraste") or {}
    zona = extracto.get("perfil_del_comprador") or {}

    condados = {x for x in (ident.get("condado_dominante"),
                            contraste.get("geografia"), zona.get("donde"))
                if x}
    dicho = _todo_el_texto(extracto).lower()
    programas = {p for p in PROGRAMAS if p.lower() in dicho}

    # Los lenders SUYOS: los de sus originadores. Sin esto, `Everett
    # Financial` -- que es su originador y es la exclusion dura-- se leeria
    # como entidad ajena.
    lenders = set(extracto.get("lenders_del_agente") or [])
    for o in (extracto.get("originadores") or []):
        for k in ("nombre", "empresa"):
            if o.get(k):
                lenders.add(o[k])
    return {"condados": sorted(condados), "programas": sorted(programas),
            "lenders": sorted(lenders)}
