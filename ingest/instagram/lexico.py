"""Los lexicos de Instagram, como DATOS, con su version y su huella.

Por que separados del codigo que los usa
----------------------------------------
Un lexico es una decision de producto que cambia sin que cambie la logica. Si
vive incrustado en la funcion, cada ajuste de una palabra es un cambio de
codigo, y no hay forma de decir «este qualifier se activo con la version X del
lexico» -- que es justo lo que hace auditable un texto seis meses despues.

`VERSION_LEXICO` viaja en cada señal que se emite. `huella()` se calcula sobre
los patrones, asi que un cambio que alguien olvide versionar igual se nota.

La tabla de lo que NO se usa
----------------------------
Es la parte mas valiosa de todo este modulo, y cada fila salio de un falso
positivo medido sobre el lote real. Esta escrita como dato --`NO_USAR`-- y hay
una prueba que falla si alguno de esos patrones vuelve a aparecer suelto dentro
de `LEX`. Un comentario que dice «no usar X» no impide que alguien use X.
"""
from __future__ import annotations

import hashlib
import re

VERSION_LEXICO = "ig-2026.09.23-v2"

#: Separador con el que el scraper une los posts en `captions_texto`.
SEP_POST = " ¶ "


# ══════════════════════════════════════════════════════════════════════════════
# 1 · ¿Este post es del oficio? DOS NIVELES (correccion A3)
# ══════════════════════════════════════════════════════════════════════════════
#
# El clasificador de referencia contaba un solo termino debil como post de real
# estate, y por eso una cuenta que la auditoria marco como PERSONAL salia
# `realtor_mixto` y filtraba al motor. De los 4 desacuerdos medidos, era el
# unico que iba del lado peligroso.
#
# «Finally got the keys to our new boat», «Closing out summer with the family» y
# «Pending: my birthday party» son los tres casos del golden.

#: Un solo termino de estos ya hace que el post sea del oficio.
RE_FUERTE = re.compile(
    r"(real ?estate|realtor\b|just sold|under contract|open house|"
    r"home ?buyers?\b|escrow|mortgage|bienes ra[ií]ces|inmobiliari|"
    r"first.?time (home)?buyer|primera casa|pre.?approv|preaprob|\bmls\b|"
    r"sq\.? ?ft\b|bedrooms?\b|rec[aá]maras|open ?house|listing agent|"
    # Español de oficio que faltaba. Sin esto, «En venta en Bogotá, 120 m2, 3
    # habitaciones» no contaba como post de real estate -- o sea que el lexico
    # leia mejor a un realtor que publica en ingles, en un proyecto cuyo nicho
    # es justo el contrario.
    r"en venta\b|se vende\b|habitaciones?\b|ba[nñ]os completos|"
    r"comprador(es)? primerizo)", re.I)

#: De estos hacen falta DOS DISTINTOS en el mismo post.
RE_DEBIL = re.compile(
    r"(\blisting\b|\bsold\b|\bpending\b|\bbuyers?\b|\bsellers?\b|closing|"
    r"closed|\bkeys\b|llaves|propiedad|cierre|\bhome\b|\bhouse\b|casa\b|"
    # «ya son dueños» / «became homeowners» es el anuncio de un cierre. Va de
    # DEBIL y no de fuerte: «los dueños del perro» existe, y un falso positivo
    # aca mete cuentas personales al motor, que es la direccion cara.
    r"due[nñ][oa]s?\b|homeowners?\b|propietari|"
    # Las abreviaturas de listado: «3 bed | 2.5 bath». El lexico tenia
    # `bedrooms?` entero y se perdia la forma corta, que es la que mas se usa.
    # Van de DEBILES: «beds» solo aparece tambien en un post de muebles, y con
    # la regla de dos distintos «3 bed» + «2.5 bath» ya cuenta.
    r"\d\s?beds?\b|\d\s?baths?\b|\bba[nñ]os?\b)", re.I)


# ══════════════════════════════════════════════════════════════════════════════
# 2 · Identidad
# ══════════════════════════════════════════════════════════════════════════════

#: Paises y ciudades extranjeras. **Solo se consulta cuando el geotag NO trae un
#: estado de EE. UU.** (correccion A1): «Panama City Beach, Florida» trae
#: Florida, asi que nunca llega aca.
#:
#: `(?<!new )m[eé]xico` sigue estando porque «New Mexico» es EE. UU. y el
#: gazetteer de estados lo resuelve por otra via; el lookbehind es la segunda
#: red, a proposito.
PAISES_NO_EEUU = re.compile(
    r"\b(panam[aá]|paraguay|bolivia|chile|colombia|venezuela|caracas|"
    r"(?<!new )m[eé]xico|espa[nñ]a|spain|brasil|brazil|argentina|per[uú]|"
    r"ecuador|guatemala|honduras|el salvador|nicaragua|costa rica|"
    r"rep[uú]blica dominicana|cuba|uruguay|puerto pe[nñ]asco|tijuana|"
    r"rosarito|monter[ií]a|hernandarias|santa cruz de la sierra|veraguas|"
    r"canc[uú]n|tulum|medell[ií]n|quintana roo|bogot[aá]|lima, per)\b", re.I)

#: Puerto Rico es EE. UU. y su nombre contiene «puerto», que no dispara nada,
#: pero la regla esta escrita para que se vea.
ES_EEUU_SIEMPRE = re.compile(r"puerto rico|\bpr\b|islas v[ií]rgenes|guam", re.I)

TELEFONO_EXTRANJERO = re.compile(
    r"\+\s?(5[0-9]|52|57|58|56|591|595|507)\s?\d[\d\s-]{6,}"
    r"|\b04(1[246]|2[46])-?\d{7}\b")

PORTUGUES = re.compile(
    r"\b(obrigad[oa]|voc[eê]|n[aã]o|muito|pra|meu|minha|tamb[eé]m|ent[aã]o|"
    r"precisamos|esque[cç]a|vezes)\b", re.I)

#: hashtag -> estados donde es legitimo, en CODIGO DE DOS LETRAS.
#:
#: Estaban con el nombre completo («Virginia»), y el lead trae el codigo
#: («VA»), asi que `perfil_V` --un realtor de Virginia que publica
#: `#dmvrealestate`-- salia `persona_equivocada`. Es el mismo error de CA
#: contra California que ya costo la biblioteca de geografias: se compara
#: SIEMPRE por el codigo, y quien tenga el nombre lo normaliza antes.
HASHTAG_REGIONAL = {
    "dmvrealestate": {"VA", "MD", "DC"},
    "dmvrealtor": {"VA", "MD", "DC"},
}

#: Hashtags de una ciudad, con el estado donde son legitimos. **No excluyen**:
#: un realtor de Colorado puede publicar #miamirealestate por mil razones --
#: referidos, una segunda casa, un cliente que se muda. Pero tres casos en el
#: lote son suficientes para pedir que alguien mire el estado del lead, que es
#: lo unico que la señal sostiene.
HASHTAG_CIUDAD = {
    "miamirealestate": "FL", "miamirealtor": "FL",
    "houstonrealestate": "TX", "austinrealestate": "TX",
    "phoenixrealestate": "AZ", "vegasrealestate": "NV",
    "atlantarealestate": "GA", "chicagorealestate": "IL",
}

#: Señales de que un listado esta FUERA de EE. UU. (correccion A2). No basta un
#: geotag de viaje: hace falta que el POST DE REAL ESTATE este afuera.
LISTADO_EXTRANJERO = re.compile(
    r"(\bm2\b|metros cuadrados|\bm²|\bCOP\b|\bMXN\b|\bARS\b|\bBs\b|"
    r"\bpesos\b|\bsoles\b|\bquetzales\b)", re.I)

#: Otra profesion (correccion A7). Con 3+ posts de esto y <=1 de real estate,
#: es `persona_equivocada` -- no `personal_sin_re`, que le diria al BD que
#: busque otra cuenta de la misma persona.
OTRA_ACTIVIDAD = re.compile(
    r"(gallo|gallin|criadero|pelea de gallos|"
    r"candidat[oa]|campa[nñ]a pol[ií]tica|diputad|concejal|senador|"
    r"academia de danza|clases de baile|coreograf|"
    r"seguros? de vida|life insurance agent|p[oó]liza)", re.I)

#: `otro_perfil` automatico (correccion A6). Tres familias, TODAS con
#: AUTOATRIBUCION exigida.
#:
#: La primera version salio de la correccion tal cual y dio 16 falsos positivos
#: sobre 18, medidos en el lote real. Los patrones matcheaban MENCIONAR a un
#: loan officer, no SERLO -- que es la regla 4 de la spec («mencion no es
#: verbalizacion») aplicada al lado equivocado. Lo que disparaba:
#:
#:   «fluent Spanish speaker»                        -> conferencista
#:   «Costco Wholesale ✨Walmart»                     -> wholesaler
#:   «That's a win in my book 😅»                     -> conferencista
#:   «hold my books 📚»                               -> conferencista
#:   «our preferred loan officer ready to pre-qualify you»  -> originador
#:   «shout out to one of the best loan officers, @un_loan_officer»-> originador
#:   «great opportunity for a fix and flip» (descripcion de listado)
#:   «negotiated it down from the wholesaler's asking price»
#:
#: Cuesta caro porque `otro_perfil` NO produce qualifiers transaccionales: cada
#: falso positivo es un realtor real que pierde su diagnostico entero.
#:
#: La regla ahora: tiene que decir que LO ES, en primera persona o como titulo
#: propio. Una mencion de tercero, un @handle al lado o un modismo no alcanzan.

#: Titulo propio: el NMLS o el cargo pegado a un dato de contacto propio, o en
#: primera persona. `@handle` cerca lo descarta: es el credito a otra persona.
ORIGINADOR = re.compile(
    r"((?:soy|i am|i'm|we are)\s+(?:un[ao]?\s+)?(?:loan officer|mlo|"
    r"mortgage (?:broker|banker|loan originator))"
    r"|\b(?:loan officer|mlo|mortgage broker)\s*[|·\-–]\s*nmls"
    r"|nmls\s*#?\s*\d{4,}\s*[|·\-–]?\s*(?:loan officer|mlo|mortgage)"
    r"|mi\s+nmls\b)", re.I)

#: DOBLE LICENCIA COMO FIRMA. Una cuenta del lote firma «Century 21 Affiliated
#: DRE #01417038 | NMLS #2061139». Ninguna forma de `ORIGINADOR` matchea: no
#: dice «loan officer» ni habla en primera persona. Pero una licencia
#: inmobiliaria y un NMLS en la MISMA firma es doble licencia, y la regla 7 la
#: descarta.
#:
#: Va APARTE porque NO pasa por el guarda del `@`: una firma con los dos
#: numeros es autoatribucion aunque el post etiquete a alguien. Nadie firma con
#: la licencia de otro.
DOBLE_LICENCIA = re.compile(
    r"(\b(?:dre|lic(?:ense)?|cal ?dre)\s*#?\s*\d{5,}\s*[|·/–-]+\s*"
    r"nmls\s*#?\s*\d{4,}"
    r"|\bnmls\s*#?\s*\d{4,}\s*[|·/–-]+\s*(?:dre|lic(?:ense)?)\s*#?\s*\d{5,})",
    re.I)

#: «I have multiple loan strategies» NO alcanza sola.
#:
#: El caso golden la trae junto a una bio «Loan Officer | NMLS 123456», y asi
#: es autoatribucion. Sola, la dice tambien un realtor que trabaja con varios
#: lenders: `perfil_R` la publica y su post siguiente es un condo de
#: $619K en Spring Valley. Hace falta que ADEMAS haya titulo o NMLS propio, y
#: eso es lo que `ORIGINADOR` ya exige.
ORIGINADOR_DEBIL = re.compile(
    r"(i have multiple loan strategies|multiple loan (?:programs|options))",
    re.I)

#: Es wholesaler quien COMPRA para revender, en primera persona del plural.
#: `Costco Wholesale` y «the wholesaler's asking price» quedan fuera.
WHOLESALER = re.compile(
    r"((?:we|nosotros)\s+(?:purchase[d]?|buy|bought)\s+"
    r"(?:this |these |the )?(?:propert|house|home)"
    r"|direct.to.seller marketing"
    r"|we (?:wholesale|buy houses)|wholesaling\b"
    r"|(?:our|nuestr[oa]s?)\s+(?:wholesale|fix and flip)\s+"
    r"(?:deal|business|company))", re.I)

#: Vive de formar agentes. `speaker` suelto matchea «Spanish speaker» y
#: `my book` es un modismo («a win in my book») y un estante de libros.
CONFERENCISTA = re.compile(
    # `charl[oa] en` salio: matcheaba «¿Quieres esta charla en tu negocio?» de
    # una realtor que da educacion a compradores, y el resumen de un evento al
    # que FUE. Queda la forma que dice que vive de eso.
    r"(conferencista|keynote speaker|\bspeaker at\b|doy charlas"
    r"|autor[ao] de[l]? libro|mi libro (?:ya |est[aá] |sali[oó])"
    r"|my book is (?:out|available)|coach de agentes"
    r"|(?:doy|imparto|dicto)\s+(?:mi\s+)?masterclass"
    r"|mi masterclass)", re.I)

#: El NMLS de la casa. Es el UNICO que excluye, y se verifica -- nunca por
#: texto: «Supreme Mortgage» (PA) no es Supreme Lending.
NMLS_DE_LA_CASA = "2129"


# ══════════════════════════════════════════════════════════════════════════════
# 3 · Los lexicos de señal
# ══════════════════════════════════════════════════════════════════════════════

_LEX_CRUDO = {
    "itin": r"\bitin\b|tax ?id\b|sin (n[uú]mero de )?seguro social|sin social"
            r"|no social security|sin cr[eé]dito",
    # `bank statements` SOLO no: es una lista de documentos. Hace falta el
    # contexto de financiamiento.
    "self_emp": r"self.?employed|bank statement (loans?|programs?|mortgage)"
                r"|pr[eé]stamos? (con|de) estados de cuenta"
                r"|1099 (income|loan|borrower)"
                r"|(trabajas|trabajan) por (tu|su) cuenta"
                r"|(ingresos|trabajador(es)?) independientes? "
                r"(pueden|califican|tambi[eé]n)",
    "owner_fin": r"owner financ|financiamiento (del|por) due[nñ]o"
                 r"|due[nñ]o financia|sin bancos|denied by the bank"
                 r"|el banco te (dijo|neg[oó])",
    "dpa": r"down ?payment assistance|\bdpa\b"
           r"|asistencia (para|de|con) (el )?(pago inicial|enganche|down ?payment)"
           r"|ayuda (para|con) (el )?(pago inicial|enganche|down)"
           r"|\bgrants?\b.{0,40}(buyer|down|closing)|programas? de asistencia",
    "zero_down": r"\$0 (de )?(enganche|down)|zero down|0% down|no money down"
                 r"|sin dinero",
    "gob": r"\bfha\b|\busda\b|203k|\bhud\b",
    "va_esp": r"especialista (en )?(pr[eé]stamos? )?va\b|va (loan )?specialist"
              r"|expert(o|a)? en va\b|va loans? (expert|specialist)"
              r"|military relocation professional|\bmrp\b",
    "va_aud": r"\bva (loan|buyer|financing)s?\b|pr[eé]stamo va\b|veteran"
              r"|veterano|military|militar|\bpcs\b|air force|army|navy",
    # `foreclosure` y `bankruptcy` SOLOS no: son comentario de mercado y
    # hashtags de listado. Van pegados a la recuperacion.
    "cred_reing": r"credit repair|reparaci[oó]n de cr[eé]dito"
                  r"|rebuild(ing)? (your )?credit|credit restoration"
                  r"|(after|despu[eé]s de) (a |una )?"
                  r"(bankruptcy|bancarrota|foreclosure|ejecuci[oó]n)",
    "credito": r"credit score|puntaje de cr[eé]dito|\bcr[eé]dito\b"
               r"|bad credit|mal cr[eé]dito",
    "preaprob": r"pre.?approv|pre.?qualif|precalific|preaprob",
    "primera": r"first.?time (home)?buyer|primera casa|primera vivienda"
               r"|primer hogar|comprador(es)? primerizo",
    # `biling[uü]e` SOLO no: «una comunidad bilingüe» describe un barrio.
    "es_decl": r"se habla espa|habl[oa]\s?espa|soy biling[uü]e"
               r"|(realtor|agente|agent|servicio|service)s? biling[uü]e"
               r"|bilingual (realtor|agent|service|team)|realestatebilingue"
               r"|te atiendo en espa|en tu idioma|que habla espa[nñ]ol|traduzco",
    "lujo": r"\bluxury\b|\blujo\b|waterfront|penthouse|million dollar"
            r"|\$\d(\.\d)?m\b|estate homes?",
    # `airbnb` suelto NO (correccion A8): «Airbnb gift card». Y `invest` suelto
    # tampoco: «invest in yourself».
    "invers": r"\binvestors?\b|\binvestment propert|inversi[oó]n(ista)?"
              r"|cash ?flow|rental propert|multifamily|\bdscr\b"
              r"|airbnb\b.{0,40}(rental|str|cash ?flow|investment|property)"
              r"|(rental|str|cash ?flow|investment|property).{0,40}\bairbnb\b",
}
LEX = {k: re.compile(v, re.I) for k, v in _LEX_CRUDO.items()}


#: Los patrones que NO se usan, con su motivo y donde fallaron. Es DATO, no un
#: comentario: `tests/test_ig_lexico.py` falla si alguno reaparece suelto.
NO_USAR = {
    r"independiente": ("«entrada / taller / casita independiente»", "8 perfiles"),
    r"business owners?": ("comercial, golf y seguros", "3 perfiles"),
    r"bank statements": ("es una lista de documentos", "1 perfil"),
    r"biling[uü]e": ("«una comunidad bilingüe» describe un barrio", "1 perfil"),
    r"foreclosure": ("comentario de mercado y hashtag de listado", "2 perfiles"),
    r"bankruptcy": ("comentario de mercado y hashtag de listado", "2 perfiles"),
    r"estates?": ("matchea «real estate»", "lote v3"),
    r"airbnb": ("«Airbnb gift card»", "auditoría del scraper"),
    r"invest": ("«invest in yourself»", "corrección A8"),
}


def huella() -> str:
    """sha256 de los patrones. Un cambio sin versionar igual se nota."""
    material = "\n".join("%s=%s" % (k, v) for k, v in sorted(_LEX_CRUDO.items()))
    material += "\nFUERTE=%s\nDEBIL=%s" % (RE_FUERTE.pattern, RE_DEBIL.pattern)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
