"""Bloque 1-ter · Perfil de audiencia, derivado de los crudos.

El problema que resuelve
------------------------
Hoy veinte publicaciones se reducen a un numero: `captions_es_ratio`. Un
realtor que publica **en ingles** sobre primera compra, ayuda de enganche y
credito sale con ratio 0,0 y se descarta -- y es exactamente nuestro cliente,
en otro idioma.

**El idioma es un atributo del publico, no un requisito de entrada.** Este
modulo extrae a quien le habla, de que habla, como habla y que le preguntan, en
los dos idiomas, y deja que los criterios se evaluen contra eso.

La prueba de que el dato esta ahi es un caption del piloto: *«Mucha gente cree
que su puntaje de credito no es lo suficientemente bueno para comprar una
casa»*. Eso es P-Q19 casi literal. En ingles, el sistema anterior no lo veia.

La regla que gobierna la salida
-------------------------------
**Cada etiqueta lleva el texto que la produjo.** Si el sistema dice
`credito:4`, tiene que poder mostrar las cuatro frases. Conteo y cita, siempre
juntos -- por eso `etiquetar()` no devuelve un dict de numeros sino un
`Etiquetado` con los dos, y por eso no hay ninguna funcion que devuelva solo
conteos.

**Nada de puntajes compuestos.** No hay «audiencia latina: 7,3» en ningun lado.
Un numero asi no se puede discutir ni verificar, y esconde de donde salio.

Los lexicos son bilingues, todos
--------------------------------
Un lexico que solo detecta en español reproduce el sesgo que estamos
corrigiendo. Hay una prueba que recorre **cada** entrada de **cada** lexico y
falla si no tiene al menos un patron en español y uno en ingles.

Sobre los marcadores culturales y el vocabulario
------------------------------------------------
Describen **el contenido que la persona publico**, no a la persona. Que un
caption lleve una bandera de Guatemala dice que eso se publico; no dice de
donde es quien lo publico, y no se usa para inferirlo. No hay ninguna
inferencia de origen ni de etnia desde nombres, ni del agente ni de quien
comenta.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field

from instagram.idioma import (
    Idioma,
    clasificar_comentario,
    clasificar_pieza,
)

# ══════════════════════════════════════════════════════════════════════════════
# LEXICOS
# ══════════════════════════════════════════════════════════════════════════════
#
# Formato: nombre -> (patrones en español, patrones en ingles).
#
# La separacion por idioma no es decorativa: es lo que hace verificable que el
# lexico detecte en los dos. Una entrada con la tupla inglesa vacia falla la
# prueba.
#
# Los patrones se aplican sobre texto SIN ACENTOS y en minuscula (ver
# `_plano`), asi que van escritos sin acentos. `credito`, no `crédito`.

#: A QUIEN LE HABLA. Multi-etiqueta: un realtor puede tener dos o tres.
LEX_AUDIENCIA: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "primera_compra": (
        (r"\bprimera (?:casa|vivienda|propiedad)\b", r"\bprimer hogar\b",
         r"\bcomprar (?:tu|su) primera\b", r"\bdeja(?:r)? de rentar\b",
         r"\bdejar de pagar renta\b", r"\bprimeriz[oa]s?\b"),
        (r"\bfirst[\s-]?time (?:home\s?)?buyers?\b", r"\bfthb\b",
         r"\bfirst home\b", r"\bstop renting\b", r"\bfirst[\s-]?time buyer\b"),
    ),
    "inversion": (
        (r"\binversionistas?\b", r"\binversi[o]n(?:es)?\b", r"\brentabilidad\b",
         r"\bflujo de efectivo\b", r"\bplusval[i]a\b",
         r"\bpropiedad de inversi[o]n\b"),
        (r"\binvestors?\b", r"\binvestment propert(?:y|ies)\b",
         r"\bcash\s?flow\b", r"\broi\b", r"\brental income\b",
         r"\bbuild(?:ing)? wealth\b", r"\bdoor\s?number \d+\b"),
    ),
    "vendedor": (
        (r"\bvender (?:tu|su) casa\b", r"\bvendedor(?:es)?\b",
         r"\bcuanto vale (?:tu|su) casa\b", r"\bquieres vender\b",
         r"\bvaluaci[o]n gratis\b", r"\bpiensas vender\b",
         r"\bpensando en vender\b"),
        (r"\bsellers?\b", r"\bsell(?:ing)? your home\b", r"\bhome value\b",
         r"\blist your home\b", r"\bthinking of selling\b",
         r"\bwhat'?s your home worth\b", r"\bdidn'?t sell\b"),
    ),
    "obra_nueva": (
        (r"\bobra nueva\b", r"\bpreventa\b", r"\bsobre planos\b",
         r"\bde estreno\b", r"\bconstrucci[o]n nueva\b"),
        (r"\bnew construction\b", r"\bnew build\b", r"\bpre[\s-]?construction\b",
         r"\bbrand new home\b", r"\bbuilder(?:'?s)? incentive\b"),
    ),
    "reubicacion": (
        (r"\bmudar(?:se|te)? a\b", r"\breubicaci[o]n\b",
         r"\bte mudas\b", r"\bllegando a la ciudad\b"),
        (r"\brelocat(?:e|ing|ion)\b", r"\bmoving to\b", r"\bout of state\b",
         r"\bnew to (?:the city|town|chicago|miami|texas)\b"),
    ),
    "lujo": (
        (r"\blujo\b", r"\bexclusiv[ao]s?\b", r"\bresidencia de lujo\b",
         r"\balto nivel\b"),
        (r"\bluxury\b", r"\bhigh[\s-]?end\b", r"\bmulti[\s-]?million\b",
         r"\bestate home\b", r"\bpenthouse\b"),
    ),
    "militar": (
        (r"\bveteran[oa]s?\b", r"\bmilitares?\b", r"\bpr[e]stamo va\b",
         r"\bservicio militar\b"),
        (r"\bva loan\b", r"\bveterans?\b", r"\bmilitary\b",
         r"\bactive duty\b", r"\bfunding fee\b", r"\bpcs\b"),
    ),
    "renta": (
        (r"\ben renta\b", r"\bse renta\b", r"\balquiler\b", r"\binquilin[oa]s?\b",
         r"\barrendamiento\b", r"\bse alquila\b"),
        (r"\bfor rent\b", r"\brental(?:s)?\b", r"\btenants?\b",
         r"\blease(?:d|ing)?\b", r"\bavailable for lease\b"),
    ),
    "refinanciacion": (
        (r"\brefinanciar\b", r"\brefinanciamiento\b",
         r"\bbajar (?:tu|su) (?:pago|tasa)\b", r"\bsacar equidad\b"),
        (r"\brefinanc(?:e|ing)\b", r"\brefi\b", r"\bcash[\s-]?out\b",
         r"\btap(?:ping)? (?:into )?(?:your )?equity\b",
         r"\blower your (?:payment|rate)\b"),
    ),
}

#: DE QUE HABLA.
LEX_TEMAS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "educacion": (
        (r"\bsabias que\b", r"\bte explico\b", r"\bcomo funciona\b",
         r"\bpaso a paso\b", r"\bgu[i]a\b", r"\bmito[s]?\b", r"\bconsejos?\b",
         r"\bmucha gente cree\b", r"\bno sab[i]as\b", r"\baprende\b",
         r"\b(?:3|4|5|tres|cuatro|cinco) (?:cosas|pasos|razones)\b",
         r"\blo que nadie te dice\b", r"\berror(?:es)? que\b"),
        (r"\bdid you know\b", r"\bhere'?s how\b", r"\bhow (?:it|this) works\b",
         r"\bstep by step\b", r"\bmyth\b", r"\btips?\b", r"\blet'?s talk about\b",
         r"\bmost people (?:think|believe|don'?t know)\b",
         r"\b(?:3|4|5|three|four|five) (?:things|steps|reasons)\b",
         r"\bwhat (?:nobody|no one) tells you\b", r"\bmistakes? (?:that|to)\b",
         r"\bhere'?s what\b"),
    ),
    "credito": (
        (r"\bpuntaje de credito\b", r"\bcredito\b", r"\bhistorial de credito\b",
         r"\breparar (?:tu |su )?credito\b", r"\bbur[o] de credito\b",
         r"\bquiebra\b", r"\bdeudas?\b"),
        # El lado español tiene `credito` pelado y el ingles exigia un
        # compuesto de una lista corta, asi que "credit report" y "your credit"
        # no entraban. Es el sesgo de este bloque en espejo: el lexico detecta
        # mejor en español que en ingles y descarta al agente que habla del
        # tema en ingles. Por eso el lado ingles cubre tambien las formas
        # sueltas, sin caer en "credit card rewards".
        (r"\bcredit score\b", r"\bfico\b", r"\bcredit repair\b",
         r"\bbad credit\b", r"\bcredit history\b", r"\bcredit report\b",
         r"\b(?:your|my|his|her|their) credit\b", r"\bbuild(?:ing)? credit\b",
         r"\bcredit (?:is|was|isn'?t|matters)\b", r"\bfix(?:ing)? (?:your )?credit\b",
         r"\bbankruptcy\b", r"\bcollections?\b",
         r"\bdebt[\s-]?to[\s-]?income\b", r"\bdti\b"),
    ),
    "enganche": (
        (r"\benganche\b", r"\bpago inicial\b", r"\bayuda (?:con|para) el enganche\b",
         r"\bcuanto necesito\b", r"\bsin enganche\b", r"\bahorro para la casa\b"),
        (r"\bdown\s?payment\b", r"\bdpa\b", r"\bdown payment assistance\b",
         r"\bzero down\b", r"\b0%\s?down\b", r"\bhow much do you need\b",
         r"\bclosing costs?\b", r"\bearnest money\b"),
    ),
    "programas_gobierno": (
        (r"\bprograma (?:de la ciudad|del estado|del condado|federal)\b",
         r"\bsubsidio\b", r"\bsubvenci[o]n\b", r"\bprestamo va\b",
         r"\bprograma de asistencia\b"),
        (r"\bfha\b", r"\bva loan\b", r"\busda\b", r"\b203\s?k\b",
         r"\bhome\s?ready\b", r"\bhome\s?possible\b", r"\bgrant\b",
         r"\bcity program\b", r"\bfirst[\s-]?time buyer program\b",
         r"\btax credit\b", r"\bhomegrown\b"),
    ),
    "proceso_compra": (
        (r"\bpreaprobaci[o]n\b", r"\bpre[\s-]?aprobad[oa]\b",
         r"\bproceso de compra\b", r"\binspecci[o]n\b", r"\baval[u]o\b",
         r"\bcierre\b", r"\bcontrato\b", r"\boferta\b", r"\bescritura\b"),
        (r"\bpre[\s-]?approv(?:al|ed)\b", r"\bunder contract\b",
         r"\bclosing process\b", r"\binspection\b", r"\bappraisal\b",
         r"\bescrow\b", r"\bcontingenc(?:y|ies)\b", r"\bmaking an offer\b",
         r"\btitle (?:company|search)\b", r"\bunderwriting\b"),
    ),
    "listado": (
        (r"\bnueva propiedad\b", r"\ben venta\b", r"\bcasa abierta\b",
         r"\bnuevo listado\b", r"\bdisponible\b", r"\brecien listada\b",
         r"\bproximamente\b"),
        (r"\bjust listed\b", r"\bnew listing\b", r"\bopen house\b",
         r"\bfor sale\b", r"\bcoming soon\b", r"\bnow available\b",
         r"\bprice (?:drop|improvement)\b", r"\bback on (?:the )?market\b"),
    ),
    "celebracion_cierre": (
        (r"\bfelicidades\b", r"\bfelicitaciones\b", r"\bvendida\b",
         r"\bcerramos\b", r"\bentrega de llaves\b", r"\bnuevos? dueñ[oa]s?\b",
         r"\botra familia\b", r"\bmision cumplida\b"),
        (r"\bcongrat(?:s|ulations)\b", r"\bjust (?:sold|closed)\b",
         r"\bsold\b", r"\bclosed\b", r"\bkeys? to (?:their|your)\b",
         r"\bhome\s?owners?\b", r"\bnew home\s?owners?\b",
         r"\banother (?:one|family|happy)\b"),
    ),
    "mercado_tasas": (
        (r"\btasas?\b", r"\btasa de interes\b", r"\bmercado\b",
         r"\binventario\b", r"\bprecios? (?:suben|bajan|del mercado)\b",
         r"\breporte del mercado\b"),
        (r"\binterest rates?\b", r"\bmarket (?:update|report|shift)\b",
         r"\binventory\b", r"\brates? (?:dropped|went|are)\b",
         r"\bmedian (?:price|home)\b", r"\bappreciation\b",
         r"\bbuyer'?s market\b", r"\bseller'?s market\b"),
    ),
    "vida_personal": (
        (r"\bmi familia\b", r"\bcumpleaños\b", r"\bvacaciones\b",
         r"\bmi hij[oa]s?\b", r"\bmi esposa?o?\b", r"\bgracias a dios\b",
         r"\bmi perr[oa]\b", r"\bviaje\b"),
        (r"\bmy family\b", r"\bbirthday\b", r"\bvacation\b", r"\bmy kids?\b",
         r"\bmy (?:wife|husband)\b", r"\bmy dog\b", r"\bgym\b",
         r"\bpersonal note\b", r"\bproud (?:dad|mom)\b", r"\bbest friend\b"),
    ),
    "comunidad": (
        (r"\bcomunidad\b", r"\bnegocio local\b", r"\bbarrio\b",
         r"\bevento\b", r"\btaller\b", r"\bferia\b", r"\bapoyemos\b"),
        (r"\bcommunity\b", r"\blocal business\b", r"\bneighborhood spotlight\b",
         r"\bevent\b", r"\bworkshop\b", r"\bsupport local\b",
         r"\bsmall business\b", r"\bfundraiser\b", r"\bgiveaway\b"),
    ),
}

#: Temas que EDUCAN. Quien educa tiene clientes que no saben comprar.
TEMAS_EDUCA = ("educacion", "credito", "enganche", "programas_gobierno",
               "proceso_compra", "mercado_tasas")
#: Temas que ANUNCIAN.
TEMAS_ANUNCIA = ("listado", "celebracion_cierre")

#: QUE LE PREGUNTAN. Se aplica a comentarios de terceros, ya redactados.
LEX_PREGUNTAS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "calificacion": (
        (r"\bcalific\w*\b", r"\benganch\w*\b", r"\bcuanto necesito\b",
         r"\bmi credito\b", r"\bitin\b", r"\bsin seguro social\b",
         r"\bque documentos\b", r"\bpreaprobaci[o]n\b", r"\bpuedo comprar\b"),
        (r"\bqualif\w*\b", r"\bdown\s?payment\b", r"\bhow much do i need\b",
         r"\bmy credit\b", r"\bcredit score\b", r"\bpre[\s-]?approv\w*\b",
         r"\bwhat documents\b", r"\bcan i (?:buy|afford)\b"),
    ),
    "precio": (
        (r"\bprecio\b", r"\bcuanto (?:cuesta|vale|piden)\b", r"\bque precio\b",
         r"\bcuanto es\b"),
        (r"\bprice\b", r"\bhow much (?:is|are|does)\b", r"\basking\b",
         r"\bwhat'?s the price\b", r"\bcost\b"),
    ),
    "proceso": (
        (r"\bcomo empiezo\b", r"\bpor donde empiezo\b", r"\bcuanto tarda\b",
         r"\bque sigue\b", r"\bcomo funciona\b", r"\bque necesito hacer\b"),
        (r"\bhow do i (?:start|begin)\b", r"\bwhere do i start\b",
         r"\bhow long does\b", r"\bwhat'?s next\b", r"\bhow does (?:it|this) work\b",
         r"\bwhat do i need to do\b"),
    ),
    "zona": (
        (r"\bque zona\b", r"\bdonde (?:esta|queda)\b", r"\ben que (?:area|barrio)\b",
         r"\bque colonia\b", r"\bcerca de\b"),
        (r"\bwhat area\b", r"\bwhere is (?:this|that|it)\b",
         r"\bwhat neighborhood\b", r"\bwhich part of\b", r"\bclose to\b",
         r"\bhow far\b"),
    ),
    "disponibilidad": (
        (r"\besta disponible\b", r"\bsigue disponible\b", r"\bya se vendio\b",
         r"\btodavia (?:esta|hay)\b", r"\bqueda algo\b"),
        (r"\bstill available\b", r"\bis this available\b",
         r"\bstill (?:on the market|active|open)\b", r"\bsold (?:already|yet)\b",
         r"\bany (?:left|units)\b"),
    ),
}

#: QUE SEÑALA SIN DECIRLO. Describe el CONTENIDO publicado, no a la persona.
LEX_MARCADORES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "fe": (
        (r"\bgracias a dios\b", r"\bdios (?:es|te|los|me)\b", r"\bbendiciones\b",
         r"\bbendecid[oa]s?\b", r"\bcon fe\b", r"\bprimeramente dios\b"),
        (r"\bgod (?:is|bless|first)\b", r"\bblessed\b", r"\bblessings\b",
         r"\bfaith\b", r"\bpraise god\b", r"\bthank god\b"),
    ),
    "familia": (
        (r"\bfamilia\b", r"\bmam[a]\b", r"\bpap[a]\b", r"\babuel[oa]s?\b",
         r"\bpara los tuyos\b", r"\bpatrimonio familiar\b",
         r"\bgeneraci[o]n(?:es)?\b"),
        (r"\bfamil(?:y|ies)\b", r"\bmom\b", r"\bdad\b", r"\bgrandparents?\b",
         r"\bfor your loved ones\b", r"\bgenerational wealth\b",
         r"\bmulti[\s-]?generational\b"),
    ),
    "cultura_latina": (
        (r"\bquinceaner[a]\b", r"\bposada\b", r"\btamales\b",
         r"\bdia de (?:los )?muertos\b", r"\bvirgen de guadalupe\b",
         r"\bsuenos?\b", r"\bpaisan[oa]s?\b", r"\bhispan[oa]s?\b",
         r"\blatin[oa]s?\b", r"\bnuestra gente\b", r"\bnuestra comunidad\b"),
        (r"\bquinceanera\b", r"\bhispanic\b", r"\blatin[oax]s?\b",
         r"\bour (?:people|community)\b", r"\bimmigrant\b",
         r"\bhispanic heritage\b", r"\bfirst generation\b"),
    ),
    "idioma_declarado": (
        (r"\bhablo espanol\b", r"\bse habla espanol\b", r"\ben espanol\b",
         r"\bbilingue\b", r"\bte atiendo en espanol\b"),
        (r"\bse habla espanol\b", r"\bspanish[\s-]?speaking\b",
         r"\bbilingual\b", r"\bi speak spanish\b", r"\bhablo espanol\b"),
    ),
}

#: Banderas de paises hispanohablantes. Es contenido publicado, no un origen.
#:
#: Va aparte de los lexicos de texto porque un emoji no tiene idioma: no se
#: puede pedir que tenga un patron en español y uno en ingles.
BANDERAS_HISPANAS = {
    "\U0001F1F2\U0001F1FD": "MX", "\U0001F1EC\U0001F1F9": "GT",
    "\U0001F1F8\U0001F1FB": "SV", "\U0001F1ED\U0001F1F3": "HN",
    "\U0001F1F3\U0001F1EE": "NI", "\U0001F1E8\U0001F1F7": "CR",
    "\U0001F1F5\U0001F1E6": "PA", "\U0001F1E8\U0001F1FA": "CU",
    "\U0001F1E9\U0001F1F4": "DO", "\U0001F1F5\U0001F1F7": "PR",
    "\U0001F1E8\U0001F1F4": "CO", "\U0001F1FB\U0001F1EA": "VE",
    "\U0001F1EA\U0001F1E8": "EC", "\U0001F1F5\U0001F1EA": "PE",
    "\U0001F1E7\U0001F1F4": "BO", "\U0001F1E8\U0001F1F1": "CL",
    "\U0001F1E6\U0001F1F7": "AR", "\U0001F1FA\U0001F1FE": "UY",
    "\U0001F1F5\U0001F1FE": "PY", "\U0001F1EA\U0001F1F8": "ES",
}

# ── COMO HABLA ────────────────────────────────────────────────────────────────
#
# Solo tiene sentido sobre texto en español: el tuteo no existe en ingles.

#: Marcas de tuteo. Decide la voz del primer mensaje.
_TUTEO = (r"\btu casa\b", r"\btu credito\b", r"\btu primera\b", r"\btienes\b",
          r"\bpuedes\b", r"\bquieres\b", r"\bsabes\b", r"\bnecesitas\b",
          r"\bescribeme\b", r"\bllamame\b", r"\bte ayudo\b", r"\bte explico\b",
          r"\bcontactame\b", r"\bmandame\b")
#: Marcas de usted.
_USTED = (r"\bsu casa\b", r"\bsu credito\b", r"\bsu primera\b",
          r"\busted(?:es)?\b", r"\bescribame\b", r"\bllameme\b",
          r"\bcontacteme\b", r"\ble ayudo\b", r"\bpermitame\b",
          r"\bcomun[i]quese\b")
#: Jerga tecnica. Mucha jerga = habla a colegas o a clientes informados.
_JERGA = (r"\bdti\b", r"\bltv\b", r"\bpmi\b", r"\bmip\b", r"\bescrow\b",
          r"\bamortizaci[o]n\b", r"\bamortization\b", r"\bcontingenc\w*\b",
          r"\bunderwriting\b", r"\bdebt[\s-]?to[\s-]?income\b",
          r"\bloan[\s-]?to[\s-]?value\b", r"\barm\b", r"\bpiti\b",
          r"\bseller concessions?\b", r"\bcap rate\b", r"\bnoi\b",
          r"\b1031\b", r"\baval[u]o\b", r"\bcomps?\b")

#: Vocabulario regional. **Describe el vocabulario del texto, no a la persona.**
#:
#: Solo se reporta con 2 o mas marcadores distintos de la misma variedad, y la
#: etiqueta dice `vocabulario:` a proposito: es una observacion sobre palabras,
#: no una afirmacion sobre de donde es nadie. Los terminos estan elegidos por
#: precision, no por cobertura.
_VOCABULARIO_REGIONAL: dict[str, tuple[str, ...]] = {
    "mx": (r"\breca[m]ara\b", r"\bplaticar\b", r"\bchid[oa]\b", r"\bandale\b",
           r"\bcolonia\b", r"\bpadr[i]simo\b", r"\balberca\b"),
    "carib": (r"\bch[e]vere\b", r"\bapartamento\b", r"\bguagua\b",
              r"\bmarquesina\b", r"\bpana\b"),
    "centroam": (r"\bcabal\b", r"\bpisto\b", r"\bcolocho\b", r"\bcheque\b"),
    "conosur": (r"\bdepartamento\b", r"\bpileta\b", r"\bplata\b",
                r"\bche\b", r"\blucas\b"),
}

# ══════════════════════════════════════════════════════════════════════════════
# ETIQUETADO CON CITA
# ══════════════════════════════════════════════════════════════════════════════

#: Citas por etiqueta en el CSV. El derivado completo las guarda todas.
MAX_CITAS_CSV = 3
#: Largo de cada cita en el CSV.
LARGO_CITA = 200
#: Minimo de marcadores distintos para reportar una variedad de vocabulario.
MIN_MARCADORES_VARIEDAD = 2
#: Piezas clasificables minimas en CADA lado para reportar `desajuste_idioma`.
#: Ver la docstring de `desajuste_idioma`: sin esto el ranking lo encabezaba un
#: perfil cuyo desajuste de 0,92 salia de UN comentario.
MIN_BASE_DESAJUSTE = 5


def _plano(texto: str | None) -> str:
    """Minuscula y sin acentos. Los lexicos se escriben contra esto."""
    sin = "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )
    return sin.lower()


def _limpiar_cita(texto: str) -> str:
    """Una cita en una sola linea. El recorte del CSV se hace aparte."""
    return re.sub(r"\s+", " ", texto or "").strip()


def _cita_del_match(limpio: str, frase: str | None) -> str:
    """Una ventana de `limpio` centrada en `frase`.

    **El bug que esta funcion arregla.** Antes la cita era el caption entero y
    el CSV lo recortaba a los primeros 200 caracteres. En un caption de 1.200
    caracteres cuya coincidencia esta en el 800, la cita del CSV **no contiene
    la frase que produjo la etiqueta** -- o sea que se rompe justo la regla que
    gobierna el bloque, y se rompe en los captions largos, que son los
    educativos, que son los que mas nos interesan.

    Lo encontre revisando a mano: la cita de `credito` en
    `@anakaren_properties` mostraba «How I meet my clients?? My marketing
    strategies vary...» y la frase real era «worked on his credit. once he was
    ready he called me», 800 caracteres mas adelante. Parecia un falso positivo
    del lexico y era un falso negativo de la cita.

    La frase se BUSCA en vez de cortarse por indice, porque `_plano` puede
    acortar el texto si venia descompuesto y ahi los indices no coinciden.
    Se busca sobre las dos versiones aplanadas, que si son comparables entre
    si, y si aun asi no aparece se devuelve la cabeza -- degradado, no roto.
    """
    if len(limpio) <= LARGO_CITA:
        return limpio

    pos = -1
    if frase:
        plano_limpio = _plano(limpio)
        plano_frase = _plano(frase)
        # Solo sirve si aplanar no movio los indices dentro de `limpio`.
        if len(plano_limpio) == len(limpio):
            pos = plano_limpio.find(plano_frase)
        if pos < 0:
            pos = limpio.lower().find((frase or "").lower())
    if pos < 0:
        pos = 0

    margen = max((LARGO_CITA - len(frase or "")) // 2, 0)
    desde = max(0, pos - margen)
    hasta = min(len(limpio), desde + LARGO_CITA)
    desde = max(0, hasta - LARGO_CITA)

    # Cortar en borde de palabra, para no partir una palabra al medio.
    trozo = limpio[desde:hasta]
    if desde > 0 and " " in trozo:
        trozo = trozo.split(" ", 1)[1]
    if hasta < len(limpio) and " " in trozo:
        trozo = trozo.rsplit(" ", 1)[0]

    return "%s%s%s" % ("..." if desde > 0 else "",
                       trozo,
                       "..." if hasta < len(limpio) else "")


@dataclass
class Etiquetado:
    """Conteos y las citas que los sostienen. **Nunca uno sin el otro.**

    `denominador` es sobre cuantas piezas se conto. Sin el, `credito:4` no se
    puede leer: 4 de 5 y 4 de 500 no dicen lo mismo.

    Dos juegos de citas a proposito:

      `citas`    el texto completo, para el JSON derivado;
      `ventanas` la ventana alrededor de la frase que disparo, para el CSV.

    Estan separados porque recortar el texto completo a 200 caracteres desde el
    principio puede dejar afuera la frase que produjo la etiqueta. Ver
    `_cita_del_match`.
    """

    conteos: dict[str, int] = field(default_factory=dict)
    citas: dict[str, list[str]] = field(default_factory=dict)
    ventanas: dict[str, list[str]] = field(default_factory=dict)
    denominador: int = 0

    def anotar(self, clave: str, texto: str, frase: str | None = None) -> None:
        """Suma uno a `clave` y guarda las dos formas de la cita.

        Es la unica via para contar: no hay ningun `conteos[k] += 1` suelto en
        este modulo, asi que no puede existir un conteo sin su cita.

        `frase` es el texto que disparo la etiqueta, tal como lo devolvio el
        patron. Se usa para centrar la ventana del CSV.
        """
        self.conteos[clave] = self.conteos.get(clave, 0) + 1
        completo = _limpiar_cita(texto)
        self.citas.setdefault(clave, []).append(completo)
        self.ventanas.setdefault(clave, []).append(
            _cita_del_match(completo, frase)
        )

    @property
    def dominante(self) -> str | None:
        """La etiqueta de mayor conteo. None si no hay ninguna.

        Con empate gana la primera en orden alfabetico, a proposito: que sea
        determinista importa mas que cual gane, porque un empate no tiene
        ganador real.
        """
        if not self.conteos:
            return None
        return sorted(self.conteos.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    def ordenadas(self) -> list[tuple[str, int]]:
        return sorted(self.conteos.items(), key=lambda kv: (-kv[1], kv[0]))

    def formatear(self, *, tope: int | None = None) -> str | None:
        """`educacion:9 | credito:4 | enganche:3`, por conteo descendente.

        `tope` recorta la lista y agrega cuantas quedaron afuera, para que el
        recorte se vea en vez de fingir que no hubo mas.
        """
        if not self.conteos:
            return None
        pares = self.ordenadas()
        sobran = len(pares) - tope if tope is not None else 0
        if sobran > 0:
            pares = pares[:tope]
        texto = " | ".join("%s:%d" % (k, v) for k, v in pares)
        if sobran > 0:
            texto += " | (+%d mas)" % sobran
        return texto

    def citas_para_csv(self) -> dict[str, list[str]]:
        """Hasta 3 citas por etiqueta, cada una centrada en su coincidencia.

        Sale de `ventanas`, no de `citas`: la ventana **contiene** la frase que
        disparo la etiqueta, y el texto completo recortado a 200 puede no
        contenerla.
        """
        return {
            k: list(self.ventanas.get(k, [])[:MAX_CITAS_CSV])
            for k, _ in self.ordenadas()
            if self.ventanas.get(k)
        }


def etiquetar(
    textos: list[str],
    lexico: dict[str, tuple[tuple[str, ...], tuple[str, ...]]],
) -> Etiquetado:
    """Cuenta piezas por etiqueta y guarda la frase que disparo cada una.

    Una pieza cuenta **una vez** por etiqueta aunque dispare tres patrones de
    esa etiqueta: el conteo es de piezas, no de coincidencias. Y una pieza
    puede caer en varias etiquetas, que es lo que hace esto multi-etiqueta.
    """
    et = Etiquetado(denominador=len(textos))
    for texto in textos:
        plano = _plano(texto)
        if not plano.strip():
            continue
        for nombre, (pat_es, pat_en) in lexico.items():
            for patron in pat_es + pat_en:
                m = re.search(patron, plano)
                if not m:
                    continue
                # Se pasa la FRASE encontrada, no sus indices. `_plano`
                # normalmente conserva el largo, pero no siempre: un texto que
                # ya venga descompuesto (e + acento combinante) se acorta, y
                # ahi los indices de `plano` no sirven para cortar `texto`.
                # Buscar la frase no depende de eso.
                et.anotar(nombre, texto, m.group(0))
                break
    return et


# ══════════════════════════════════════════════════════════════════════════════
# LO QUE NO SALE DE UN LEXICO
# ══════════════════════════════════════════════════════════════════════════════

#: Un precio: $625,000 · $1.2M · $15K. Con separador o sufijo, para no agarrar
#: "$5 de cafe".
_RE_PRECIO = re.compile(
    r"\$\s?(\d{1,3}(?:[,.]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?\s?[KkMm])\b"
)


def precios(textos: list[str]) -> Etiquetado:
    """Precios mencionados, normalizados a numero, con su frase.

    La etiqueta es el precio normalizado en miles (`625k`, `1.2m`), asi que
    `$625,000` y `$625K` caen en la misma. Sirve para leer el rango en el que
    trabaja el agente, que es contexto de la conversacion.
    """
    et = Etiquetado(denominador=len(textos))
    for texto in textos:
        for m in _RE_PRECIO.finditer(texto or ""):
            valor = _normalizar_precio(m.group(1))
            if valor is None:
                continue
            et.anotar(_formatear_precio(valor), texto, m.group(0))
    return et


def _normalizar_precio(crudo: str) -> float | None:
    s = (crudo or "").strip().lower().replace(" ", "")
    mult = 1.0
    if s.endswith("k"):
        mult, s = 1_000.0, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000.0, s[:-1]
    else:
        # 625,000 y 1.200.000 usan el separador como millar.
        if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", s):
            s = s.replace(",", "").replace(".", "")
    try:
        return float(s.replace(",", "")) * mult
    except ValueError:
        return None


def _formatear_precio(valor: float) -> str:
    if valor >= 1_000_000:
        return "%gm" % round(valor / 1_000_000, 1)
    return "%dk" % round(valor / 1_000)


#: Palabras que marcan que lo de al lado es un lugar.
_CLAVES_DE_LUGAR = (
    "neighborhood", "area", "suburb", "district", "side of", "located in",
    "barrio", "colonia", "zona", "vecindario", "sector", "ubicacion",
    "\U0001F4CD",  # el pin: en esta data es la marca de lugar mas fiable
)
#: Maximo de lugares en la celda del CSV. El derivado los lleva todos.
MAX_LUGARES_CSV = 8
#: Candidato a nombre propio de lugar: dos a tres palabras en Title Case.
_RE_TITLE = re.compile(
    r"\b([A-Z][a-zà-ÿ]{2,}(?:\s+(?:de|del|la|las|los|el)\s+[A-Z][a-zà-ÿ]{2,}"
    r"|\s+[A-Z][a-zà-ÿ]{2,}){0,2})\b"
)
#: Lo que el Title Case agarra y no es un lugar.
_NO_SON_LUGARES = {
    "real estate", "open house", "new listing", "just listed", "first time",
    "home buyer", "down payment", "credit score", "happy new year",
    "merry christmas", "thank you", "god bless", "let me", "dm me", "click the",
    "swipe up", "link in", "coming soon", "for sale", "under contract",
    "home value", "loan officer", "mortgage broker", "se habla", "feliz ano",
    "muchas felicidades", "dios los", "gracias a", "mi familia",
}


def lugares(
    textos: list[str],
    geotags: list[str],
    *,
    excluir: tuple[str, ...] = (),
) -> Etiquetado:
    """Barrios y ciudades nombrados. **El geotag manda; el texto necesita aval.**

    Un geotag es el lugar que el agente *eligio* etiquetar: entra solo. Un
    candidato sacado del texto entra unicamente si algo lo avala -- el pin 📍,
    una palabra de lugar al lado, o ser un hashtag.

    La regla anterior era «entra si aparece dos veces», y la revision a mano
    sobre los perfiles reales la mato: el Title Case suelto agarra la primera
    palabra de cada frase, y repetirse dos veces no cuesta nada. Salio esto,
    presentado como barrios:

        Locations:13 · Ana Osorio:4 · Claudia:6 · Download:4 · Looking:4 ·
        Rent:4 · This:2 · Would:1 · Send:1 · Congratulations:1 · Hispanic:1

    Entre medio si estaban Logan Square, Pilsen, Uptown, West Loop, Woodlawn,
    Doral y Lakeview -- o sea que la señal existia y el ruido la tapaba. Una
    columna asi no se puede leer, y una columna que no se puede leer es peor
    que no tenerla: invita a creerle.

    `excluir` recibe el nombre y el handle del agente, porque «Ana Osorio» y
    «Claudia Hernandez Realtor» salian como barrios de si mismos.
    """
    et = Etiquetado(denominador=len(textos))

    for g in geotags:
        nombre = _limpiar_cita(g)
        if not nombre:
            continue
        et.anotar(nombre, "geotag: %s" % nombre, nombre)

    vetados = {_plano(e) for e in excluir if e}
    # Tambien las palabras sueltas del nombre del agente: «Osorio», «Claudia».
    for e in excluir:
        for palabra in re.split(r"[\s_.@-]+", _plano(e or "")):
            if len(palabra) >= 4:
                vetados.add(palabra)

    def _vetado(nombre: str) -> bool:
        plano_n = _plano(nombre)
        if plano_n in _NO_SON_LUGARES or len(nombre) < 4:
            return True
        if plano_n in vetados:
            return True
        return any(p in vetados for p in plano_n.split())

    for texto in textos:
        limpio = _limpiar_cita(texto)
        plano = _plano(limpio)

        # Los hashtags parecian una buena fuente -- quien escribe #LoganSquare
        # eligio esa etiqueta, igual que un geotag-- y la revision a mano lo
        # desmintio: en inmobiliaria son abrumadoramente TEMATICOS, no
        # geograficos. Salieron «Dream Home», «Homes For Sale», «Real Estate
        # Life», «Investment Property» y «List With Me» presentados como
        # barrios. No hay forma lexica de separar #LoganSquare de #DreamHome,
        # asi que la fuente se descarta entera.
        #
        # Queda solo el Title Case CON AVAL: el pin o una palabra de lugar.
        for m in _RE_TITLE.finditer(limpio):
            nombre = m.group(1).strip()
            if _vetado(nombre):
                continue
            # El aval tiene que estar PEGADO, no cerca. Con una ventana de 30
            # caracteres entraba «Download» ocho veces, porque el pin estaba en
            # la misma linea del CTA: «Download my free guide 📍 link in bio».
            # Cerca de una marca de lugar no es ser un lugar.
            antes = limpio[max(0, m.start() - 3):m.start()]
            despues = _plano(limpio[m.end():m.end() + 16])
            pegado = (
                "\U0001F4CD" in antes
                or any(despues.lstrip(" ,.–-").startswith(cl)
                       for cl in _CLAVES_DE_LUGAR)
                or any(_plano(antes).rstrip().endswith(cl)
                       for cl in ("in the", "en el", "en la", "de"))
            )
            if pegado:
                et.anotar(nombre, limpio, nombre)

    return et


def banderas(textos: list[str]) -> Etiquetado:
    """Banderas de paises hispanohablantes en el texto publicado.

    Describe el contenido, no a la persona: que alguien publique una bandera de
    Guatemala dice que eso se publico y nada mas.
    """
    et = Etiquetado(denominador=len(textos))
    for texto in textos:
        for emoji, codigo in BANDERAS_HISPANAS.items():
            if emoji in (texto or ""):
                et.anotar("bandera_%s" % codigo.lower(), texto, emoji)
    return et


def registro(textos: list[str]) -> Etiquetado:
    """Tuteo o usted, jerga o llano, y el vocabulario regional observado.

    Decide la voz del primer mensaje, que es para lo que existe.
    """
    et = Etiquetado(denominador=len(textos))

    def _contar(clave: str, patrones: tuple[str, ...]) -> None:
        for texto in textos:
            plano = _plano(texto)
            for p in patrones:
                m = re.search(p, plano)
                if m:
                    et.anotar(clave, texto, m.group(0))
                    break

    _contar("tuteo", _TUTEO)
    _contar("usted", _USTED)
    _contar("jerga_tecnica", _JERGA)

    # Vocabulario regional: hace falta variedad, no una palabra suelta.
    for variedad, patrones in _VOCABULARIO_REGIONAL.items():
        distintos: set[str] = set()
        encontrados: list[tuple[str, str]] = []
        for texto in textos:
            plano = _plano(texto)
            for p in patrones:
                m = re.search(p, plano)
                if m:
                    distintos.add(p)
                    encontrados.append((texto, m.group(0)))
        if len(distintos) >= MIN_MARCADORES_VARIEDAD:
            for texto, frase in encontrados:
                et.anotar("vocabulario_%s" % variedad, texto, frase)
    return et


# ══════════════════════════════════════════════════════════════════════════════
# IDIOMA: CONTEOS, Y EL DESAJUSTE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConteoDeIdioma:
    """Piezas por idioma, con el total. El total es el denominador."""

    es: int = 0
    en: int = 0
    total: int = 0

    @property
    def clasificables(self) -> int:
        return self.es + self.en

    @property
    def ratio_sobre_clasificables(self) -> float | None:
        if not self.clasificables:
            return None
        return self.es / self.clasificables


def contar_idioma_de_captions(captions: list[str]) -> ConteoDeIdioma:
    c = ConteoDeIdioma(total=len(captions))
    for texto in captions:
        v = clasificar_pieza(texto)
        if v.idioma is Idioma.ESPANOL:
            c.es += 1
        elif v.idioma is Idioma.INGLES:
            c.en += 1
    return c


def contar_idioma_de_comentarios(comentarios: list[str]) -> ConteoDeIdioma:
    c = ConteoDeIdioma(total=len(comentarios))
    for texto in comentarios:
        v = clasificar_comentario(texto)
        if v.idioma is Idioma.ESPANOL:
            c.es += 1
        elif v.idioma is Idioma.INGLES:
            c.en += 1
    return c


def desajuste_idioma(
    comentarios: ConteoDeIdioma, publicaciones: ConteoDeIdioma
) -> float | None:
    """Ratio de español en comentarios menos ratio en publicaciones.

    **Positivo y grande = su audiencia es mas latina que su contenido.** Le
    escriben en español y el publica en ingles: conversion que se esta dejando
    en la mesa, y una conversacion distinta a la de un agente que simplemente
    no atiende ese mercado.

    El denominador es el de las piezas CLASIFICABLES (español + ingles), no el
    total, y eso es una desviacion deliberada de la formula literal. La razon
    esta medida: **el 26% de los comentarios del piloto son practicamente solo
    emoji** («Congrats! 🔥🔥🔥»), y un emoji no tiene idioma. Con el total como
    denominador, `comentarios_es_ratio` queda diluido por los indeterminados y
    la resta sale negativa por construccion -- o sea que el campo que mas
    importa mostraria «su audiencia es menos latina» justo cuando lo que pasa
    es que su audiencia aplaude con emoji.

    Las dos columnas de conteo (`idioma_comentarios_es/_en`,
    `idioma_publica_es/_en`) van igual en el CSV, asi que la version con el
    total tambien se puede calcular a mano. Es por eso que van.

    None si alguno de los dos lados tiene menos de `MIN_BASE_DESAJUSTE` piezas
    clasificables. Sin base no hay resta, y un cero seria una afirmacion que no
    se midio.

    **El minimo no es decorativo.** Sin el, el piloto encabezaba el ranking con
    `@miguelsanchezz7_` en 0,9167 -- calculado sobre **un** comentario en
    español y ninguno en ingles. Un 0,92 que sale de n=1 es ruido presentado
    como señal, y manda a alguien a la conversacion equivocada con toda
    confianza. Es la misma regla que el resto del proyecto: ningun porcentaje
    sin su denominador, y un denominador de 1 no sostiene un porcentaje.
    """
    if (comentarios.clasificables < MIN_BASE_DESAJUSTE
            or publicaciones.clasificables < MIN_BASE_DESAJUSTE):
        return None
    r_com = comentarios.ratio_sobre_clasificables
    r_pub = publicaciones.ratio_sobre_clasificables
    if r_com is None or r_pub is None:
        return None
    return round(r_com - r_pub, 4)


# ══════════════════════════════════════════════════════════════════════════════
# EL PERFIL COMPLETO
# ══════════════════════════════════════════════════════════════════════════════

#: Columnas que este bloque agrega a `ig_signals.csv`, en orden.
COLUMNAS_AUDIENCIA = [
    "audiencia_segmentos", "audiencia_dominante",
    "temas", "tema_dominante", "ratio_educa_vs_anuncia",
    "idioma_publica_es", "idioma_publica_en",
    "idioma_comentarios_es", "idioma_comentarios_en", "desajuste_idioma",
    "registro", "marcadores_culturales",
    "precios_mencionados", "barrios_mencionados", "programas_mencionados",
    "preguntas_recibidas",
    "citas_por_etiqueta",
]


@dataclass
class PerfilDeAudiencia1ter:
    """Todo lo derivado, con sus citas completas.

    Las citas completas viven aca y en el JSON derivado, **no** en `ig_raw/`:
    ese directorio es el crudo y hay una prueba que falla si aparece algo
    derivado dentro. Un derivado que se mezcla con la fuente deja de ser
    re-derivable.
    """

    audiencia: Etiquetado
    temas: Etiquetado
    registro_: Etiquetado
    marcadores: Etiquetado
    precios: Etiquetado
    lugares: Etiquetado
    programas: Etiquetado
    preguntas: Etiquetado
    idioma_publica: ConteoDeIdioma
    idioma_comentarios: ConteoDeIdioma
    n_captions: int = 0
    n_comentarios: int = 0

    def ratio_educa_vs_anuncia(self) -> tuple[float | None, int, int]:
        """(ratio, n_educa, n_anuncia). El ratio es educa/(educa+anuncia).

        Se devuelven los dos conteos con el ratio porque 9 de 10 y 90 de 100
        son el mismo 0,9 y no son la misma evidencia.
        """
        n_educa = sum(self.temas.conteos.get(t, 0) for t in TEMAS_EDUCA)
        n_anuncia = sum(self.temas.conteos.get(t, 0) for t in TEMAS_ANUNCIA)
        if n_educa + n_anuncia == 0:
            return None, 0, 0
        return round(n_educa / (n_educa + n_anuncia), 4), n_educa, n_anuncia

    def citas_completas(self) -> dict[str, dict[str, list[str]]]:
        return {
            "audiencia": self.audiencia.citas,
            "temas": self.temas.citas,
            "registro": self.registro_.citas,
            "marcadores_culturales": self.marcadores.citas,
            "precios": self.precios.citas,
            "barrios": self.lugares.citas,
            "programas": self.programas.citas,
            "preguntas_recibidas": self.preguntas.citas,
        }

    def citas_para_csv(self) -> dict[str, list[str]]:
        """Un solo dict plano para la celda. Prefijo por familia, sin colisiones."""
        salida: dict[str, list[str]] = {}
        for familia, et in (
            ("audiencia", self.audiencia), ("tema", self.temas),
            ("registro", self.registro_), ("marcador", self.marcadores),
            ("programa", self.programas), ("pregunta", self.preguntas),
        ):
            for clave, citas in et.citas_para_csv().items():
                salida["%s:%s" % (familia, clave)] = citas
        return salida

    def a_columnas(self) -> dict:
        """Las 17 columnas del CSV."""
        ratio, n_educa, n_anuncia = self.ratio_educa_vs_anuncia()
        return {
            "audiencia_segmentos": self.audiencia.formatear(),
            "audiencia_dominante": self.audiencia.dominante,
            "temas": self.temas.formatear(),
            "tema_dominante": self.temas.dominante,
            # El ratio lleva sus dos conteos pegados: 9 de 10 y 90 de 100 son
            # el mismo 0,9 y no son la misma evidencia.
            "ratio_educa_vs_anuncia": (
                None if ratio is None
                else "%.4g (educa %d / anuncia %d)" % (ratio, n_educa, n_anuncia)
            ),
            "idioma_publica_es": self.idioma_publica.es,
            "idioma_publica_en": self.idioma_publica.en,
            "idioma_comentarios_es": self.idioma_comentarios.es,
            "idioma_comentarios_en": self.idioma_comentarios.en,
            "desajuste_idioma": desajuste_idioma(
                self.idioma_comentarios, self.idioma_publica
            ),
            "registro": self.registro_.formatear(),
            "marcadores_culturales": self.marcadores.formatear(),
            "precios_mencionados": self.precios.formatear(),
            # Topeado: una celda con 35 lugares no se lee. El derivado los
            # lleva todos.
            "barrios_mencionados": self.lugares.formatear(tope=MAX_LUGARES_CSV),
            "programas_mencionados": self.programas.formatear(),
            "preguntas_recibidas": self.preguntas.formatear(),
            "citas_por_etiqueta": json.dumps(
                self.citas_para_csv(), ensure_ascii=False, sort_keys=True
            ) if self.citas_para_csv() else None,
        }


#: Las columnas de este bloque, vacias. Es lo que devuelve un perfil que NO se
#: leyo: un privado no tiene «cero temas de credito», no lo leimos.
def columnas_vacias() -> dict:
    return {c: None for c in COLUMNAS_AUDIENCIA}


def perfilar_audiencia_1ter(
    *,
    captions: list[str],
    comentarios_de_terceros: list[str],
    geotags: list[str],
    bio: str | None = None,
    nombres_a_vetar: tuple[str, ...] = (),
) -> PerfilDeAudiencia1ter:
    """Deriva todo. Sin red, sin estado, sin leer disco.

    `comentarios_de_terceros` tiene que llegar **ya redactado y sin autor**:
    aca se agregan como perfil de audiencia y no se perfila a nadie
    individualmente. La cita va sin autor porque nunca lo recibe.

    La bio entra solo en marcadores y registro, no en temas: lo que la bio dice
    es una declaracion permanente, y un tema es algo de lo que se habla en una
    publicacion con fecha.

    `nombres_a_vetar` es el nombre y el handle del agente, y se usa **solo para
    excluir**: sin el, «Ana Osorio» y «Claudia Hernandez Realtor» salian
    listados como barrios de si mismos. No entra en ningun lexico y no produce
    ninguna etiqueta -- no hay aca ninguna inferencia a partir de un nombre, que
    es justo lo que la regla prohibe. Se le resta, no se le suma.
    """
    textos_con_bio = list(captions) + ([bio] if bio else [])

    from instagram.posts import LEXICO_PROGRAMAS

    programas = Etiquetado(denominador=len(captions))
    for texto in textos_con_bio:
        plano = _plano(texto)
        for nombre, (_qualifier, patrones) in LEXICO_PROGRAMAS.items():
            for p in patrones:
                m = re.search(p, plano, re.IGNORECASE)
                if m:
                    programas.anotar(nombre, texto, m.group(0))
                    break

    marcadores = etiquetar(textos_con_bio, LEX_MARCADORES)
    de_banderas = banderas(textos_con_bio)
    marcadores.conteos.update(de_banderas.conteos)
    marcadores.citas.update(de_banderas.citas)
    marcadores.ventanas.update(de_banderas.ventanas)

    return PerfilDeAudiencia1ter(
        audiencia=etiquetar(captions, LEX_AUDIENCIA),
        temas=etiquetar(captions, LEX_TEMAS),
        registro_=registro(textos_con_bio),
        marcadores=marcadores,
        precios=precios(captions),
        lugares=lugares(captions, geotags, excluir=nombres_a_vetar),
        programas=programas,
        preguntas=etiquetar(comentarios_de_terceros, LEX_PREGUNTAS),
        idioma_publica=contar_idioma_de_captions(captions),
        idioma_comentarios=contar_idioma_de_comentarios(comentarios_de_terceros),
        n_captions=len(captions),
        n_comentarios=len(comentarios_de_terceros),
    )
