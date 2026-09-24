"""La ficha del realtor, v3: las nueve secciones que el BD lee antes de escribir.

Qué es esto y qué no
--------------------
Es la maqueta v3 que revisaron Isabella y un BD, hecha con datos de la base. No
es una pantalla nueva sobre los mismos números: es un ORDEN distinto, y el
orden es la decisión. Primero quién es y cómo se le escribe, después por qué
ella, y el motor --reglas, qualifiers, intensidades-- queda plegado en «Cómo se
calculó», que es donde vive lo que al BD no le sirve para hablar.

Las cuatro reglas que gobiernan todo lo de aquí
-----------------------------------------------
1 · **Cada dato lleva su «De dónde sale»**, con la cita y su fecha, o la fila de
    Model Match. Un conteo suelto --«20 publicaciones»-- no es evidencia de
    nada: es un número que nadie puede comprobar sin volver a la fuente.

2 · **Lo que no existe se muestra como `Pendiente`, no se estima.** Es la misma
    regla que sostiene `pendiente_modelmatch` y `no_leido`: una ausencia
    declarada se puede resolver, y una estimada se convierte en un hecho a la
    tercera vez que alguien la lee.

3 · **Las hipótesis se escriben como hipótesis.** «2 buys con Zillow Home Loans
    podría indicar que le llegan buyers por Zillow» y no «le llegan buyers por
    Zillow». El grado va al lado de cada fila, visible.

4 · **Vocabulario de lending en inglés, sin traducir.** loan, down payment,
    rate, closing, pre-approval, buy side, Conventional, FHA, cash, non-QM.
    Traducirlo obliga al BD a volver a traducirlo en la llamada.

Lo que NO sale de aquí
----------------------
Nombres de buyers ni de sellers, ni la calle: no están en la base. Nombres de
tablas, ids de regla ni explicaciones del motor en el texto visible: eso va en
«Cómo se calculó», que es otra pestaña.

Y el dato de que un lender le refiere clientes se muestra como CONTEXTO y nunca
en el mensaje ni en «Por qué ella»: RESPA §8.
"""
from __future__ import annotations

import datetime as dt

#: Grados de evidencia, en el lenguaje del BD. La traducción va aquí y no en la
#: pantalla, para que sea una sola.
#:
#: No es el grado E0–E3 del motor renombrado: es otra pregunta. El motor
#: pregunta «¿cuán fuerte es esto?»; el BD pregunta «¿esto lo midió alguien, me
#: lo contó ella, o lo estamos suponiendo?», que es lo que decide si se puede
#: decir en voz alta.
DATO = "Dato"
LO_CUENTA_ELLA = "Lo cuenta ella"
HIPOTESIS = "Hipótesis"

#: Lo que todavía no existe, con el motivo. Se muestra, no se estima.
PENDIENTES = {
    "puntaje": "hasta validar las compuertas del motor",
    "lo_asignado": "falta decidir qué LO de HOMESÍ la atiende",
    "census_zip": "el Census por ZIP todavía no está cargado",
    "seguidores": "el número de seguidores viene de handles sin verificar",
    "salesforce": "el sync de Salesforce todavía no corre",
}


#: Prefijos de campo -> quién observó el dato. El orden es el de la lista.
#:
#: NO se decide por el grado E0–E3 del motor. Se probó y da mal: `P-Q01-2` lee
#: `ev2_dpa_enganche`, que sale de su propia bio, y está declarada E1 -- así
#: que por grado saldría «Hipótesis» sobre una frase que ella escribió. El
#: grado mide cuán fuerte es la evidencia; esto mide de quién es.
_QUIEN_LO_OBSERVO = (
    ("mm_", DATO),            # Model Match: operaciones cerradas, medidas
    ("ig_", DATO),            # su muro, contado post por post
    ("ev2_", LO_CUENTA_ELLA),  # su bio y sus publicaciones
    ("ev_", LO_CUENTA_ELLA),
    ("estado_perfil", DATO),
)


def grado_de(activacion: dict, citas: dict | None = None) -> str:
    """Dato / Lo cuenta ella / Hipótesis, desde los CAMPOS que la regla leyó.

    **`Lo cuenta ella` EXIGE LA CITA.** Sin una frase suya con su fecha, un
    `ev2_*` es `Hipótesis` y no su palabra.

    El motivo salió de un caso real: `ev2_fha_gob` llega por dos caminos --una
    columna del libro v3 cuya derivación no está documentada, y `menciona_fha`
    de Instagram, que cuenta menciones en los captions-- así que «lo cuenta
    ella» podía ser un puntaje heredado o un post que enumera tipos de
    financing. El BD lo iba a repetir en la llamada como si ella lo hubiera
    dicho, y lo que se cae cuando no lo reconoce no es la frase: es la
    credibilidad de todo lo demás.

    `citas` es {campo: {"texto": ..., "fecha": ...}}. Mientras no exista el
    mecanismo que las junte, llega vacío y todos los `ev2_*` son hipótesis --
    que es lo correcto: no tenemos la cita.

    La pregunta no es la del motor. El motor pregunta «¿cuán fuerte es esto?»;
    el BD pregunta «¿esto lo midió alguien, me lo contó ella, o lo estamos
    suponiendo?», que es lo que decide si se puede decir en voz alta y cómo.

      · Model Match e Instagram medido -> `Dato`. Lo observó un tercero sobre
        hechos, no sobre intenciones;
      · su bio y sus posts -> `Lo cuenta ella`. Es verdad que lo dijo, no que
        sea así, y el copy tiene que sonar a eso;
      · los puntajes del libro y las métricas de mercado -> `Hipótesis`. De
        «en su condado el 14% son FHA» a «sus buyers usan FHA» hay un salto que
        alguien tiene que validar en la llamada.

    Con varias fuentes gana la más observada: una regla que cruza Model Match
    con la bio se sostiene en Model Match.
    """
    campos = [str(c) for c in ((activacion or {}).get("campos_leidos") or {})]
    citas = citas or {}
    for prefijo, grado in _QUIEN_LO_OBSERVO:
        coinciden = [c for c in campos if c.startswith(prefijo)]
        if not coinciden:
            continue
        if grado is LO_CUENTA_ELLA and not any(
                _cita_util(citas.get(c)) for c in coinciden):
            return HIPOTESIS
        return grado
    return HIPOTESIS


def _cita_util(cita) -> bool:
    """Una cita sirve si trae la frase Y la fecha. Sin fecha no se puede
    decir «el 15 de junio dijo», y sin eso el BD no la puede usar."""
    return bool(isinstance(cita, dict) and cita.get("texto")
                and cita.get("fecha"))


def iniciales(nombre: str | None) -> str:
    """`Ana Osorio` -> `AO`. La ficha no lleva foto."""
    partes = [p for p in (nombre or "").replace(".", " ").split() if p]
    if not partes:
        return "··"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def _pct(parte, total):
    if not total:
        return None
    return round(100.0 * (parte or 0) / total, 1)


def contactos_por_canal(filas: list[dict]) -> list[dict]:
    """Los contactos agrupados por valor, con TODAS sus fuentes.

    Un teléfono que está en tres fuentes y otro que está en una no valen lo
    mismo, y el que está en una sola puede ser el bueno --el que usa hoy-- o
    el que quedó de un archivo viejo. Las dos cosas se ven si se muestran las
    fuentes; ninguna se ve si se muestra un teléfono.
    """
    por_valor: dict = {}
    for f in filas or []:
        canal = f.get("canal")
        valor = (f.get("valor") or "").strip()
        if not canal or not valor:
            continue
        clave = (canal, valor)
        d = por_valor.setdefault(clave, {"canal": canal, "valor": valor,
                                         "fuentes": []})
        fuente = f.get("fuente") or "sin fuente"
        if fuente not in d["fuentes"]:
            d["fuentes"].append(fuente)

    salida = list(por_valor.values())
    # Una sola fuente se marca: no es un error, es algo que hay que mirar.
    for d in salida:
        d["una_sola_fuente"] = len(d["fuentes"]) == 1
    # Los de más fuentes primero, y dentro de cada canal el orden es estable.
    salida.sort(key=lambda d: (d["canal"], -len(d["fuentes"]), d["valor"]))
    return salida


def trimestres_de(filas_tx: list[dict], *, lado="compra") -> list[dict]:
    """Los closings por trimestre, con los incompletos marcados.

    Un trimestre parcial dibujado igual que uno completo cuenta una caída que
    no pasó: el último siempre va a la mitad porque el trimestre va a la mitad.
    """
    fechas = sorted(f["fecha"] for f in (filas_tx or [])
                    if f.get("fecha") and f.get("lado") in (lado, "ambos"))
    if not fechas:
        return []
    por_tri: dict = {}
    for f in fechas:
        ano, mes = int(f[:4]), int(f[5:7])
        clave = (ano, (mes - 1) // 3 + 1)
        por_tri[clave] = por_tri.get(clave, 0) + 1

    primera, ultima = fechas[0], fechas[-1]
    salida = []
    for (ano, tri), n in sorted(por_tri.items()):
        ini = dt.date(ano, (tri - 1) * 3 + 1, 1)
        fin_mes = tri * 3
        fin = (dt.date(ano + (fin_mes == 12), (fin_mes % 12) + 1, 1)
               - dt.timedelta(days=1))
        parcial = (ini.isoformat() < primera) or (fin.isoformat() > ultima)
        salida.append({"ano": ano, "trimestre": tri, "n": n,
                       "parcial": parcial,
                       "etiqueta": "%s %s" % (
                           ("ene–mar", "abr–jun", "jul–sep", "oct–dic")[tri - 1],
                           str(ano)[2:])})
    return salida


def razones(resumen_tx: dict | None, activaciones: list[dict],
            perfil: dict | None) -> list[dict]:
    """«Por qué ella»: tres razones, cada una con de dónde sale.

    Se construyen de lo MEDIDO y no del puntaje: el BD las va a decir en voz
    alta, y una razón que sale de un score no se puede sostener en una llamada.

    RESPA §8: que un lender le refiera clientes NO puede ser una razón. Es
    contexto y vive en la sección de Instagram.
    """
    salida: list[dict] = []
    if resumen_tx:
        c = resumen_tx.get("compras") or {}
        v = resumen_tx.get("ventas") or {}
        lenders = resumen_tx.get("lenders_compra") or {}
        financiadas = c.get("financiada") or 0
        top = max(lenders.items(), key=lambda kv: kv[1]) if lenders else None

        if (c.get("total") or 0) > (v.get("total") or 0):
            detalle = ("Sus %d financed buys se reparten entre %d lenders%s."
                       % (financiadas, len(lenders),
                          (", y %s, el que más usa, tiene solo %d"
                           % (top[0], top[1])) if top else ""))
            salida.append({
                "titulo": "Buy side fuerte y sin lender fijo",
                "texto": ("Cerró %d buys y %d listings. %s"
                          % (c.get("total") or 0, v.get("total") or 0, detalle)),
                "de_donde": ("Model Match › Transactions: %d operaciones. La "
                             "tabla está en «Su producción»."
                             % ((c.get("total") or 0) + (v.get("total") or 0))),
            })

        cash = c.get("cash_segun_mm") or 0
        con_datos = (c.get("total") or 0) - (c.get("cash_provisional") or 0)
        if cash and con_datos:
            salida.append({
                "titulo": "Muchos cash buyers",
                "texto": ("%d de sus %d closings con más de 5 semanas figuran "
                          "como cash. No sabemos si son investors o familias "
                          "que no consiguieron financing, así que hay que "
                          "preguntarle." % (cash, con_datos)),
                "de_donde": ("Model Match marca «Cash» mientras no recibe el "
                             "loan. Estas compras tienen más de 35 días."),
                "hipotesis": True,
            })

    # La tercera sale del dolor más fuerte que el motor sí sostiene.
    fuertes = [a for a in (activaciones or [])
               if a.get("familia") == "P" and (a.get("intensidad") or 0) >= 2]
    fuertes.sort(key=lambda a: -(a.get("intensidad") or 0))
    if fuertes:
        a = fuertes[0]
        salida.append({
            "titulo": "Buyers que necesitan prepararse",
            "texto": a.get("texto") or "",
            "de_donde": "%s · %s" % (a.get("origen") or "",
                                     a.get("referencia") or ""),
            "hipotesis": grado_de(a) == HIPOTESIS,
        })
    return salida[:3]


def dolores_posibles(activaciones: list[dict], enunciados: dict,
                     ganchos: dict) -> list[dict]:
    """La tabla de dolores: evidencia, grado y la pregunta que lo valida.

    Solo familia P y solo lo que se activó. Un dolor sin pregunta no sirve: el
    BD no puede validarlo en la llamada, y un dolor que no se valida es una
    suposición que se va repitiendo.
    """
    salida = []
    for a in activaciones or []:
        if a.get("familia") != "P":
            continue
        q = a.get("qualifier")
        salida.append({
            "qualifier": q,
            "dolor": enunciados.get(q) or a.get("texto") or q,
            "evidencia": a.get("texto") or "",
            "grado": grado_de(a),
            "intensidad": a.get("intensidad"),
            "pregunta": ganchos.get(q),
            "regla_id": a.get("regla_id"),
        })
    salida.sort(key=lambda d: -(d["intensidad"] or 0))
    return salida


def objecion(resumen_tx: dict | None) -> dict | None:
    """El lender contra el que se compite, y cómo NO plantearlo.

    «Ya trabajo con X» es la objeción que llega, y la respuesta no es
    reemplazarlo: es ofrecerse para los buyers que ese lender no puede aprobar.
    """
    lenders = (resumen_tx or {}).get("lenders_compra") or {}
    if not lenders:
        return None
    nombre, n = max(lenders.items(), key=lambda kv: kv[1])
    total = (resumen_tx.get("compras") or {}).get("financiada") or 0
    return {
        "lender": nombre, "buys": n, "de": total,
        "texto": ("«Ya trabajo con %s». Lo usó en %d de sus %d financed buys. "
                  "No busques reemplazarlo: ofrécete para los buyers que ellos "
                  "no pueden aprobar." % (nombre, n, total)),
    }


def telefono_para_el_primer_contacto(contactos: list[dict]) -> dict | None:
    """Al que usa HOY, y no al que ya recibió el SMS de campaña.

    El orden de preferencia es el de cuán vivo está el canal: el que publica en
    Instagram es el que contesta; el del archivo original puede tener dos años.
    """
    orden = ("instagram", "model match", "modelmatch", "salesforce", "lote",
             "archivo")
    telefonos = [c for c in contactos if c["canal"] == "telefono"]
    if not telefonos:
        # `None` no alcanza: la pantalla mostraría un hueco y el hueco se lee
        # como «no hace falta». Sin teléfono no hay primer contacto, y eso es
        # lo primero que hay que resolver.
        return {"pendiente": ("no hay ningún teléfono suyo en la base: sin eso "
                              "no hay primer contacto")}

    def _rango(c):
        fuentes = " ".join(c["fuentes"]).lower()
        for i, f in enumerate(orden):
            if f in fuentes:
                return i
        return len(orden)

    telefonos.sort(key=_rango)
    return telefonos[0]
