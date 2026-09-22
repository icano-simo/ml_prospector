"""Cliente del ACS del Census Bureau, a nivel de CONDADO.

La trampa que costo el rato
---------------------------
**api.census.gov devuelve HTTP 200 cuando rechaza la clave.** El error viene en
el cuerpo, como HTML:

    sin parametro key   -> HTTP 200 + <title>Missing Key</title>
    key vacia           -> HTTP 200 + <title>Missing Key</title>
    key equivocada      -> HTTP 200 + <title>Invalid Key</title>
    key buena           -> HTTP 200 + [["NAME","state"],["California","06"]]

Los cuatro son 200. Un cliente que mire `response.status` da el rechazo por
bueno y revienta mas tarde al parsear, en otro sitio y con otro mensaje. Por eso
`consultar()` **valida el cuerpo y no el codigo de estado**.

Y NO funciona sin clave: el limite de ~500 consultas diarias por IP no aplica a
este endpoint, que responde `Missing Key`. No hay plan B sin clave.

De donde sale la clave
----------------------
Del `.env` de la RAIZ del repo, por `supabase.config.cargar_env`. El cliente
viejo de `latino_re_engine` buscaba su propio `.env` en
`latino_re_engine/latino_re_engine/.env`, que no existe -- asi que nunca pudo
ver la clave buena que si esta en la raiz.

ECOA
----
Las variables de condado describen **donde opera** un realtor, no quien es.
Ninguna de ellas entra en una inferencia sobre una persona. Por eso la lista de
abajo es de mercado y de vivienda -- y el idioma esta como atributo del mercado,
nunca como proxy de origen.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.census.gov/data/%s/acs/acs5"
ANIO = 2022

#: La clave del Census mide 40 caracteres hexadecimales.
LARGO_CLAVE = 40


class CensusRechazo(RuntimeError):
    """El API contesto algo que no son datos. Con lo que dijo."""


class ClaveInvalida(RuntimeError):
    """La clave del entorno no tiene forma de clave. Antes de salir a la red."""


#: codigo ACS -> que mide. Verificadas una por una contra Los Angeles County.
VARIABLES = {
    "B01003_001E": "poblacion_total",
    "B11001_001E": "hogares",
    "B19013_001E": "ingreso_medio_hogar",
    "B25003_001E": "viviendas_ocupadas",
    "B25003_002E": "viviendas_en_propiedad",
    "B25003_003E": "viviendas_en_alquiler",
    "B25077_001E": "valor_medio_vivienda",
    "B25064_001E": "alquiler_medio",
    "B25081_002E": "propias_con_hipoteca",
    "C16001_001E": "poblacion_5mas",
    "C16001_003E": "habla_espanol_en_casa",
    "C16001_005E": "espanol_ingles_limitado",
}


def clave_del_entorno(valor: str | None = None) -> str:
    """La clave, comprobada ANTES de salir a la red.

    Un error de forma se ve aca, con el largo y los extremos a la vista, en vez
    de volver como un `Invalid Key` dentro de un HTML de 3 KB.
    """
    clave = (valor if valor is not None
             else os.environ.get("CENSUS_API_KEY", ""))
    clave = (clave or "").strip().strip('"').strip("'")
    if not clave:
        raise ClaveInvalida(
            "No hay CENSUS_API_KEY en el entorno.\n"
            "Va en el .env de la raiz del repo, y se carga con "
            "`supabase.config.cargar_env()`.\n"
            "Sin clave el API responde HTTP 200 con `Missing Key`: el limite "
            "sin clave no aplica a este endpoint.")
    if len(clave) != LARGO_CLAVE or not re.fullmatch(r"[0-9a-fA-F]+", clave):
        raise ClaveInvalida(
            "La CENSUS_API_KEY no tiene forma de clave: mide %d caracteres "
            "(tienen que ser %d hexadecimales) y empieza por %r.\n"
            "Suele ser basura pegada al valor: comillas, un espacio o un salto "
            "de linea." % (len(clave), LARGO_CLAVE, clave[:4]))
    return clave


def url_enmascarada(params: dict) -> str:
    """La URL tal como se manda, con la clave tapada.

    Enmascara los params REALES en vez de reinyectar una clave en la salida: un
    log que muestra una clave en una peticion que no la llevaba miente sobre lo
    que se mando, y es lo que hace perder la tarde.
    """
    visibles = dict(params)
    if "key" in visibles:
        v = str(visibles["key"])
        visibles["key"] = (v[:4] + "…" + v[-4:]) if len(v) > 8 else "(vacia)"
    return (BASE % ANIO) + "?" + urllib.parse.urlencode(visibles)


def interpretar(cuerpo: str, estado: int, params: dict) -> list[list]:
    """El cuerpo -> datos, o `CensusRechazo` con lo que dijo el Census.

    Separada de la red a proposito: la decision que importa -- mirar el cuerpo
    y no el codigo de estado-- se puede probar sin salir a internet, que es lo
    que hace que la prueba corra siempre y no solo cuando hay conexion.
    """
    if cuerpo.lstrip().startswith("["):
        return json.loads(cuerpo)

    titulo = re.search(r"<title>([^<]+)</title>", cuerpo)
    motivo = titulo.group(1).strip() if titulo else cuerpo[:200]
    raise CensusRechazo(
        "El Census contesto HTTP %s con %r en vez de datos.\n"
        "  %s\n"
        "\n"
        "Los rechazos del Census vienen con HTTP 200 y el motivo en el cuerpo, "
        "asi que mirar el codigo de estado no sirve.\n"
        "  `Missing Key`  no llego ninguna clave -- y sin clave este endpoint "
        "no responde datos.\n"
        "  `Invalid Key`  llego una clave y no es la buena."
        % (estado, motivo, url_enmascarada(params)))


def consultar(params: dict, *, clave: str | None = None,
              timeout: int = 60) -> list[list]:
    """Una consulta al ACS. Valida el CUERPO, no el codigo de estado."""
    p = dict(params)
    p["key"] = clave_del_entorno(clave)
    url = (BASE % ANIO) + "?" + urllib.parse.urlencode(p)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            cuerpo = r.read().decode("utf-8", "replace")
            estado = r.status
    except urllib.error.HTTPError as exc:
        cuerpo = exc.read().decode("utf-8", "replace")
        estado = exc.code
    return interpretar(cuerpo, estado, p)


def _num(valor):
    """Los centinelas negativos del ACS no son numeros: son ausencia.

    El ACS usa -666666666 y parientes para "no estimable". Guardarlos como
    numero mete un ingreso medio de menos seiscientos millones en la tabla, y
    cualquier promedio que los toque queda destruido sin que nada falle.
    """
    if valor in (None, "", "null"):
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if v <= -666666:
        return None
    return v


def condados_de_estado(fips_estado: str, *, clave: str | None = None) -> list[dict]:
    """Todos los condados de un estado, con sus variables."""
    codigos = list(VARIABLES)
    filas = consultar({"get": "NAME," + ",".join(codigos),
                       "for": "county:*", "in": "state:" + fips_estado},
                      clave=clave)
    cabecera, cuerpo = filas[0], filas[1:]
    idx = {nombre: i for i, nombre in enumerate(cabecera)}

    salida = []
    for fila in cuerpo:
        variables = {VARIABLES[c]: _num(fila[idx[c]]) for c in codigos}
        salida.append({
            "condado_fips": fila[idx["state"]] + fila[idx["county"]],
            "estado_fips": fila[idx["state"]],
            "nombre": fila[idx["NAME"]],
            "variables": variables,
            "derivadas": derivadas(variables),
            "anio_acs": ANIO,
        })
    return salida


def derivadas(v: dict) -> dict:
    """Las razones, CON su denominador al lado.

    Ninguna se calcula sin base: un porcentaje sobre un denominador ausente es
    un numero inventado con formato correcto.
    """
    def razon(numerador: str, denominador: str):
        n, d = v.get(numerador), v.get(denominador)
        if n is None or not d:
            return None
        return round(100.0 * n / d, 1)

    return {
        "tasa_propiedad_pct": razon("viviendas_en_propiedad",
                                    "viviendas_ocupadas"),
        "base_tenencia": v.get("viviendas_ocupadas"),
        "espanol_en_casa_pct": razon("habla_espanol_en_casa",
                                     "poblacion_5mas"),
        "base_idioma": v.get("poblacion_5mas"),
        # Sobre los que HABLAN español, cuantos tienen ingles limitado. El
        # denominador es el de español, no el de la poblacion: es la diferencia
        # entre "cuanta gente necesita atencion en español" y "que parte de los
        # hispanohablantes la necesita".
        "ingles_limitado_sobre_espanol_pct": razon("espanol_ingles_limitado",
                                                   "habla_espanol_en_casa"),
        "base_espanol": v.get("habla_espanol_en_casa"),
        "con_hipoteca_sobre_propias_pct": razon("propias_con_hipoteca",
                                                "viviendas_en_propiedad"),
        "base_propias": v.get("viviendas_en_propiedad"),
    }
