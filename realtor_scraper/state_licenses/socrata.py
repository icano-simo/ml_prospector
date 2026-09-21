"""Licencias estatales via API Socrata. Sin scraping, sin formularios, sin muro.

Que resuelve
------------
`trec.py` y `dbpr.py` raspan formularios de busqueda: una peticion por ciudad,
parseo de HTML, y todo se rompe cuando el board rediseña la pagina.

Varios estados publican **el padron completo como dataset Socrata**, con API
paginada, filtros SoQL y un esquema estable. Eso es estrictamente mejor: se pide
una vez, se filtra del lado del servidor y no hay nada que evadir.

Estados verificados el 2026-09-21
---------------------------------
| Estado | Dataset | Filas | LOs activos / locales |
|---|---|---|---|
| NY | `data.ny.gov/yg7h-zjbf` | 147.111 | 2 / 1 |
| CO | `data.colorado.gov/4zse-6bnw` | 110.118 | 3 / 1 |
| CT | `data.ct.gov/7y8e-cawe` (salespersons) | 97.438 | 4 / 2 |
| CT | `data.ct.gov/fwpc-pgqj` (brokers) | 21.801 | 4 / 2 |
| TX | `data.texas.gov/s7ft-44qi` | no verificado | 12 / 8 |

El de Texas existe en el catalogo pero no se pudo consultar desde esta maquina:
`SSL: CERTIFICATE_VERIFY_FAILED`, que es un problema del almacen de
certificados local y no del servidor. Queda declarado como **no verificado**.

**CA, AZ, NV e IL no publican dataset Socrata de licencias inmobiliarias.**
Ver docs/bloque-3-identidad.md.

Dos trampas de estos datasets
-----------------------------
1. **El padron incluye residentes de otros estados.** En el de Colorado, el
   primer registro es alguien con direccion en San Diego. Una licencia de
   Colorado no significa que la persona opere en Colorado, y filtrar por
   `state` del domicilio descarta a quien vive en la frontera pero trabaja del
   otro lado. Se guarda el domicilio y se declara.

2. **El de Colorado mezcla tipos de licencia.** `licensetype` incluye
   "Mortgage Loan Originator" junto con las inmobiliarias. **Eso es util**: un
   MLO con licencia inmobiliaria del mismo estado es exactamente el caso de
   doble licencia que la metodologia manda descartar como prospecto. Pero si se
   carga sin filtrar, el padron "de realtors" trae originadores.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

#: Socrata pagina de 1.000 en 1.000 por omision y admite hasta 50.000.
PAGINA = 5_000
PAUSA = 0.4

USER_AGENT = "ml_prospector/1.0 (prospeccion B2B)"


class SocrataNoDisponible(RuntimeError):
    """No se pudo consultar. No se devuelve una lista vacia como si fuera exito."""


@dataclass(frozen=True)
class FuenteEstatal:
    """Un dataset Socrata de licencias, con el mapeo a nuestros campos.

    `columnas` mapea nuestro nombre canonico al nombre en el dataset. Si una
    columna no existe en ese estado, no se pone: el campo queda en None, y eso
    es distinto de estar vacio.
    """

    estado: str
    dominio: str
    dataset: str
    etiqueta: str
    columnas: dict[str, str]
    #: Filtro SoQL del lado del servidor. Se aplica antes de descargar.
    where: str | None = None
    #: Valores de la columna de tipo que SI son licencias inmobiliarias.
    tipos_inmobiliarios: tuple[str, ...] = ()
    #: Valores que indican licencia de originacion hipotecaria -> doble licencia.
    tipos_de_originacion: tuple[str, ...] = ()
    verificado: bool = True
    nota: str = ""

    @property
    def url(self) -> str:
        return "https://%s/resource/%s.json" % (self.dominio, self.dataset)


#: Las fuentes verificadas. Cada entrada se comprobo contra el API: el conteo de
#: filas y el esquema estan en el docstring del modulo.
FUENTES: dict[str, list[FuenteEstatal]] = {
    "NY": [FuenteEstatal(
        estado="NY", dominio="data.ny.gov", dataset="yg7h-zjbf",
        etiqueta="Active Real Estate Salespersons and Brokers",
        columnas={
            "nombre": "license_holder_name",
            "licencia": "license_number",
            "tipo_licencia": "license_type",
            "brokerage": "business_name",
            "ciudad": "business_city",
            "estado_domicilio": "business_state",
            "zip": "business_zip",
            "condado": "county",
            "vencimiento": "license_expiration_date",
        },
        nota=("el dataset ya es solo de licencias ACTIVAS, asi que no trae "
              "columna de status. 'county' viene en NONE en parte de las filas."),
    )],
    "CO": [FuenteEstatal(
        estado="CO", dominio="data.colorado.gov", dataset="4zse-6bnw",
        etiqueta="Licensed Real Estate Professionals in Colorado",
        columnas={
            "apellido": "lastname",
            "nombre_pila": "firstname",
            "segundo_nombre": "middlename",
            "licencia": "licensenumber",
            "prefijo_licencia": "licenseprefix",
            "tipo_licencia": "licensetype",
            "estatus": "licensestatus",
            "ciudad": "city",
            "estado_domicilio": "state",
            "zip": "zipcode",
            "emision": "licensefirstissuedate",
            "vencimiento": "licenseexpirationdate",
        },
        where="licensestatus='Active'",
        tipos_inmobiliarios=("Broker", "Real Estate Broker", "Broker Associate"),
        tipos_de_originacion=("Mortgage Loan Originator",),
        nota=("MEZCLA tipos: licensetype incluye 'Mortgage Loan Originator'. "
              "Hay que filtrar, y los MLO sirven para detectar doble licencia."),
    )],
    "CT": [
        FuenteEstatal(
            estado="CT", dominio="data.ct.gov", dataset="7y8e-cawe",
            etiqueta="Real Estate Salesperson Licenses",
            columnas={
                "nombre": "name",
                "licencia": "credentialnumber",
                "licencia_completa": "fullcredentialcode",
                "tipo_licencia": "credential",
                "estatus": "status",
                "ciudad": "city",
                "estado_domicilio": "state",
                "zip": "zip",
                "emision": "issuedate",
                "vencimiento": "expirationdate",
            },
            where="active=1",
        ),
        FuenteEstatal(
            estado="CT", dominio="data.ct.gov", dataset="fwpc-pgqj",
            etiqueta="Real Estate Broker Licenses",
            columnas={
                "nombre": "name",
                "licencia": "credentialnumber",
                "licencia_completa": "fullcredentialcode",
                "tipo_licencia": "credential",
                "estatus": "status",
                "tipo_entidad": "type",
                "dba": "dba",
                "ciudad": "city",
                "estado_domicilio": "state",
                "zip": "zip",
            },
            where="active=1",
            nota=("'type' puede ser LIMITED LIABILITY COMPANY: son entidades, "
                  "no personas. Hay que filtrarlas o quedan como prospectos."),
        ),
    ],
    "TX": [FuenteEstatal(
        estado="TX", dominio="data.texas.gov", dataset="s7ft-44qi",
        etiqueta="Broker and Sales Agent License Holder Information",
        columnas={},  # sin verificar: no se mapea a ciegas
        verificado=False,
        nota=("existe en el catalogo federado pero no se pudo consultar: "
              "SSL CERTIFICATE_VERIFY_FAILED desde esta maquina, que es el "
              "almacen de certificados local y no el servidor. El esquema esta "
              "SIN MAPEAR a proposito: mapear a ciegas produce columnas vacias."),
    )],
}


def _pedir(url: str, params: dict) -> list[dict]:
    consulta = "%s?%s" % (url, urllib.parse.urlencode(params))
    req = Request(consulta, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json",
    })
    try:
        with urlopen(req, timeout=120) as respuesta:  # noqa: S310 - dominios fijos
            return json.loads(respuesta.read().decode("utf-8"))
    except HTTPError as exc:
        detalle = ""
        try:
            detalle = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        raise SocrataNoDisponible(
            "HTTP %d en %s. %s" % (exc.code, consulta, detalle)
        ) from exc
    except (URLError, json.JSONDecodeError) as exc:
        raise SocrataNoDisponible(
            "no pude consultar %s: %s%s"
            % (consulta, exc,
               "\nEl CERTIFICATE_VERIFY_FAILED es el almacen de certificados "
               "local, no el servidor: probar con `pip install certifi` o desde "
               "otra maquina." if "CERTIFICATE_VERIFY" in str(exc) else "")
        ) from exc


@dataclass
class ResultadoDeCarga:
    estado: str
    fuente: str
    registros: list[dict] = field(default_factory=list)
    n_descargados: int = 0
    n_descartados_por_tipo: int = 0
    n_descartados_por_entidad: int = 0
    n_con_doble_licencia: int = 0
    avisos: list[str] = field(default_factory=list)

    def resumen(self) -> str:
        return (
            "%s · %s: %d registros utiles de %d descargados "
            "(%d descartados por tipo de licencia, %d por ser entidad y no "
            "persona, %d marcados con doble licencia)"
            % (self.estado, self.fuente, len(self.registros), self.n_descargados,
               self.n_descartados_por_tipo, self.n_descartados_por_entidad,
               self.n_con_doble_licencia)
        )


def cargar_estado(
    estado: str,
    *,
    condados: set[str] | None = None,
    limite: int | None = None,
) -> list[ResultadoDeCarga]:
    """Descarga el padron de un estado. Levanta si el estado no esta verificado."""
    codigo = estado.strip().upper()[:2]
    fuentes = FUENTES.get(codigo)
    if not fuentes:
        raise SocrataNoDisponible(
            "No hay fuente Socrata para %r.\n"
            "Verificados: %s.\n"
            "\n"
            "CA, AZ, NV e IL NO publican dataset Socrata de licencias "
            "inmobiliarias: hay que raspar sus portales o pedir el padron por "
            "registro publico. Ver docs/bloque-3-identidad.md."
            % (codigo, ", ".join(sorted(FUENTES)))
        )

    salida = []
    for fuente in fuentes:
        if not fuente.verificado:
            raise SocrataNoDisponible(
                "La fuente %s/%s existe pero NO esta verificada: %s"
                % (fuente.estado, fuente.dataset, fuente.nota)
            )
        salida.append(_cargar_fuente(fuente, condados=condados, limite=limite))
    return salida


def _cargar_fuente(
    fuente: FuenteEstatal,
    *,
    condados: set[str] | None,
    limite: int | None,
) -> ResultadoDeCarga:
    resultado = ResultadoDeCarga(estado=fuente.estado, fuente=fuente.etiqueta)
    if fuente.nota:
        resultado.avisos.append(fuente.nota)

    col_condado = fuente.columnas.get("condado")
    if condados and not col_condado:
        resultado.avisos.append(
            "se pidio filtrar por condado pero %s no publica columna de "
            "condado: se descarga el estado entero y se filtra despues por ZIP"
            % fuente.etiqueta
        )

    desplazamiento = 0
    while True:
        params: dict = {
            "$limit": min(PAGINA, limite - desplazamiento) if limite else PAGINA,
            "$offset": desplazamiento,
            "$order": ":id",
        }
        if fuente.where:
            params["$where"] = fuente.where
        if condados and col_condado:
            lista = ",".join("'%s'" % c.upper().replace("'", "") for c in condados)
            params["$where"] = "%s AND upper(%s) IN (%s)" % (
                params.get("$where", "1=1"), col_condado, lista,
            )

        pagina = _pedir(fuente.url, params)
        if not pagina:
            break
        resultado.n_descargados += len(pagina)

        for cruda in pagina:
            fila = _normalizar(cruda, fuente)

            tipo = (fila.get("tipo_licencia") or "").strip()
            if fuente.tipos_de_originacion and any(
                t.lower() == tipo.lower() for t in fuente.tipos_de_originacion
            ):
                # No se descarta: se marca. Un MLO con licencia inmobiliaria del
                # mismo estado es el caso de doble licencia que hay que detectar.
                fila["es_originador"] = True
                resultado.n_con_doble_licencia += 1
                resultado.registros.append(fila)
                continue

            if fuente.tipos_inmobiliarios and tipo and not any(
                t.lower() in tipo.lower() for t in fuente.tipos_inmobiliarios
            ):
                resultado.n_descartados_por_tipo += 1
                continue

            entidad = (fila.get("tipo_entidad") or "").strip().upper()
            if entidad and entidad != "INDIVIDUAL":
                resultado.n_descartados_por_entidad += 1
                continue

            resultado.registros.append(fila)

        desplazamiento += len(pagina)
        if limite and desplazamiento >= limite:
            break
        if len(pagina) < params["$limit"]:
            break
        time.sleep(PAUSA)

    return resultado


def _normalizar(cruda: dict, fuente: FuenteEstatal) -> dict:
    """Mapea las columnas del dataset a nuestros nombres canonicos."""
    fila: dict = {"estado_licencia": fuente.estado,
                  "fuente": "%s/%s" % (fuente.dominio, fuente.dataset)}
    for canonico, en_dataset in fuente.columnas.items():
        fila[canonico] = cruda.get(en_dataset)

    # Nombre completo: algunos traen un campo, otros lo parten en tres.
    if not fila.get("nombre"):
        partes = [fila.get("nombre_pila"), fila.get("segundo_nombre"),
                  fila.get("apellido")]
        armado = " ".join(p.strip() for p in partes if p and str(p).strip())
        fila["nombre"] = armado or None

    fila.setdefault("es_originador", False)
    return fila


def estados_disponibles() -> dict[str, dict]:
    """Que estados se pueden cargar hoy, y cuales no. Para el reporte."""
    salida: dict[str, dict] = {}
    for codigo, fuentes in FUENTES.items():
        salida[codigo] = {
            "datasets": [f.dataset for f in fuentes],
            "verificado": all(f.verificado for f in fuentes),
            "notas": [f.nota for f in fuentes if f.nota],
        }
    return salida
