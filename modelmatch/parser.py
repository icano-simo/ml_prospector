"""Parsea las capturas de Model Match y codifica las trampas verificadas.

Las cuatro trampas estan comprobadas en el perfil de prueba y cada una tiene su
prueba en tests/test_modelmatch.py:

1. **Dos definiciones de wallet share en el mismo perfil.** La tarjeta de
   Overview muestra 33/33/33 (por unidades); la pestaña Originators muestra
   40,6/35,3/24,0 (por volumen). Se capturan las dos, etiquetadas. El parser NO
   elige una.

2. **Los numeros se mueven dentro de la misma sesion.** Dos pestañas
   consecutivas del mismo perfil, mismo rango de 14 meses:
   "7 buy / 21 sell · 15 total · 28 Sold" contra
   "6 buy / 21 sell · 14 total · 27 Sold". El parser guarda las dos lecturas con
   su timestamp y reporta el conflicto. No promedia.

3. **La tasa de casamiento hipotecario es baja y visible.** El tooltip de un mes
   decia "Total Volume $1.0M · Mortgaged Volume: $0". En el perfil de prueba el
   tipo de prestamo se conocia para 3 de 14 unidades del lado comprador. Por eso
   "Top 3 Concentration 100%" NO significa concentracion: significa que solo hay
   tres casados. El parser lo detecta y lo dice.

4. **"Side Focus" y "Buyer vs Listing Side" reportan conteos distintos.** Se
   guardan ambos.

No hay "limpieza" de datos aca. Un conflicto entre dos pestañas es informacion
sobre la fuente.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from modelmatch.esquema import (
    ESQUEMA_VERSION,
    BenchmarkCondado,
    ConteoDeLados,
    PerfilAgente,
    Procedencia,
    WalletShareCapturado,
)


class CapturaInvalida(ValueError):
    """La captura no se puede parsear sin adivinar. Se rechaza."""


SIN_DATO = {"", "[sin dato]", "[sin datos]", "-", "—", "n/a", "na", "null", "none"}


def _limpio(valor: str | None) -> str | None:
    if valor is None:
        return None
    v = valor.strip()
    return None if v.lower() in SIN_DATO else v


def _entero(valor: str | None) -> int | None:
    v = _limpio(valor)
    if v is None:
        return None
    v = v.replace(",", "").replace(".", "") if v.count(".") > 1 else v.replace(",", "")
    m = re.search(r"-?\d+", v)
    return int(m.group()) if m else None


def _decimal(valor: str | None) -> float | None:
    """Lee un numero con coma o punto decimal, y % o $ alrededor."""
    v = _limpio(valor)
    if v is None:
        return None
    v = v.replace("$", "").replace("%", "").strip()
    # 40,6 es cuarenta y seis decimas; 1,234 es mil doscientos treinta y cuatro.
    if "," in v and "." not in v:
        entero, _, resto = v.partition(",")
        v = "%s.%s" % (entero, resto) if len(resto) <= 2 else v.replace(",", "")
    else:
        v = v.replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", v)
    return float(m.group()) if m else None


def _fraccion(valor: str | None) -> float | None:
    """Un porcentaje a fraccion 0-1. 40,6 -> 0.406 · 0,406 -> 0.406."""
    d = _decimal(valor)
    if d is None:
        return None
    if d < 0:
        raise CapturaInvalida("porcentaje negativo: %r" % valor)
    if d > 100:
        raise CapturaInvalida(
            "porcentaje %r mayor que 100: revisa si es un porcentaje o un conteo"
            % valor
        )
    return d / 100.0 if d > 1.0 else d


def _fecha_hora(valor: str | None) -> dt.datetime | None:
    v = _limpio(valor)
    if v is None:
        return None
    for formato in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(v, formato)
        except ValueError:
            continue
    raise CapturaInvalida(
        "no entiendo el timestamp %r. Usa YYYY-MM-DD HH:MM. La hora importa: "
        "los numeros de Model Match se mueven dentro de la misma sesion." % v
    )


# ── Lector del formato de texto ───────────────────────────────────────────────

def _pares_en_linea_de_seccion(resto: str) -> list[tuple[str, str]]:
    """Extrae `clave: valor` de la linea del `##`, con valores que traen `:`.

    El caso que importa es `capturado_en: 2026-09-21 10:04  ventana: trailing
    14 months`: el valor del timestamp contiene dos puntos, asi que no se puede
    cortar por `:`. Se corta por el patron `<dos o mas espacios><palabra>:`, que
    es como la plantilla separa los campos.
    """
    if ":" not in resto:
        return []
    # Inserta un separador antes de cada clave que arranca tras 2+ espacios.
    marcado = re.sub(r"\s{2,}(?=[A-Za-z_]\w*\s*:)", "\x00", resto.strip())
    pares: list[tuple[str, str]] = []
    for trozo in marcado.split("\x00"):
        if ":" not in trozo:
            continue
        clave, _, valor = trozo.partition(":")
        clave = clave.strip().lower()
        if re.fullmatch(r"[a-z_]\w*", clave):
            pares.append((clave, valor.strip()))
    return pares


def _secciones(texto: str) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """Parte el .txt en (campos de cabecera, lineas por seccion).

    `lineas` preserva duplicados a proposito: una captura de condado trae varias
    lineas `mix:` y varias `score:`, y un dict las colapsaria dejando solo la
    ultima. La cabecera si es un dict, y ahi el primero gana.

    Un archivo de condado no tiene `##`, asi que sus lineas salen con seccion
    vacia y aparecen tanto en la cabecera como en `lineas`.
    """
    cabecera: dict[str, str] = {}
    lineas: list[tuple[str, str, str]] = []
    seccion = ""
    for cruda in texto.splitlines():
        linea = cruda.rstrip()
        desnuda = linea.strip()
        if not desnuda:
            continue
        if desnuda.startswith("##"):
            resto = desnuda.lstrip("#").strip()
            if not resto:
                continue
            seccion = resto.split()[0].lower().rstrip(":")
            primero = resto.split(None, 1)
            if len(primero) > 1:
                for clave, valor in _pares_en_linea_de_seccion(primero[1]):
                    lineas.append((seccion, clave, valor))
            continue
        if desnuda.startswith("#"):
            continue
        if ":" not in desnuda:
            continue
        clave, _, valor = desnuda.partition(":")
        clave = clave.strip().lower()
        valor = valor.strip()
        lineas.append((seccion, clave, valor))
        if not seccion:
            cabecera.setdefault(clave, valor)
    return cabecera, lineas


def _verificar_esquema(texto: str) -> None:
    m = re.search(r"#\s*esquema\s*:\s*(\S+)", texto)
    if not m:
        raise CapturaInvalida(
            "la captura no declara esquema. La primera linea tiene que ser\n"
            "    # esquema: %s\n"
            "Sin esquema declarado el archivo es ilegible a los tres meses, "
            "cuando la prueba ya caduco y no se puede volver a mirar la pantalla."
            % ESQUEMA_VERSION
        )
    if m.group(1) != ESQUEMA_VERSION:
        raise CapturaInvalida(
            "esquema %r pero este parser lee %r. No adivino la diferencia."
            % (m.group(1), ESQUEMA_VERSION)
        )


def leer_perfil(ruta: str | Path) -> PerfilAgente:
    """Lee una captura de perfil de agente."""
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8")
    _verificar_esquema(texto)
    cabecera, lineas = _secciones(texto)

    perfil = PerfilAgente(
        licencia=_limpio(cabecera.get("licencia")),
        nmls_si_tiene=_limpio(cabecera.get("nmls_si_tiene")),
        apellido=_limpio(cabecera.get("apellido")),
        nombre=_limpio(cabecera.get("nombre")),
        producer_tier=_limpio(cabecera.get("producer_tier")),
        side_focus=_limpio(cabecera.get("side_focus")),
        referral_concentration=_limpio(cabecera.get("referral_concentration")),
    )

    # Agrupa por seccion
    por_seccion: dict[str, list[tuple[str, str]]] = {}
    for seccion, clave, valor in lineas:
        por_seccion.setdefault(seccion, []).append((clave, valor))

    for seccion, pares in por_seccion.items():
        campos = dict(pares)
        capturado = _fecha_hora(campos.get("capturado_en"))
        ventana = _limpio(campos.get("ventana")) or _limpio(
            campos.get("ventana_declarada")
        )

        if seccion in ("overview", "originators"):
            if capturado is None:
                raise CapturaInvalida(
                    "la seccion '%s' de %s no trae capturado_en. Sin timestamp no "
                    "se puede reconciliar con la otra pestaña, y las dos "
                    "reportan numeros distintos." % (seccion, ruta.name)
                )
            proc = Procedencia(
                pestana=seccion,  # type: ignore[arg-type]
                capturado_en=capturado,
                ventana_declarada=ventana or "[sin declarar]",
                metodo="texto_pegado",
            )
            conteo = ConteoDeLados(
                buy=_entero(campos.get("buy")),
                sell=_entero(campos.get("sell")),
                total=_entero(campos.get("total")),
                sold=_entero(campos.get("sold")),
                procedencia=proc,
            )
            if any(v is not None for v in (conteo.buy, conteo.sell,
                                           conteo.total, conteo.sold)):
                perfil.conteos.append(conteo)

            base = "unidades" if seccion == "overview" else "volumen"
            prefijo = "ws_%s_" % seccion
            for clave, valor in pares:
                if not clave.startswith(prefijo):
                    continue
                v = _limpio(valor)
                if v is None:
                    continue
                partes = [p.strip() for p in v.split("|")]
                lender = partes[0]
                share = _fraccion(partes[1]) if len(partes) > 1 else None
                ops = _entero(partes[2]) if len(partes) > 2 else None
                if share is None:
                    raise CapturaInvalida(
                        "%s en %s sin porcentaje. Formato: lender|pct|ops"
                        % (clave, ruta.name)
                    )
                perfil.wallet_shares.append(WalletShareCapturado(
                    lender=lender, share=share, base=base,  # type: ignore[arg-type]
                    lado="sin_declarar", ops=ops, procedencia=proc,
                ))

            for clave, valor in pares:
                if clave != "originador":
                    continue
                v = _limpio(valor)
                if v is None:
                    continue
                p = [x.strip() for x in v.split("|")]
                perfil.originadores.append({
                    "nombre": p[0] if p else None,
                    "nmls": _limpio(p[1]) if len(p) > 1 else None,
                    "ops": _entero(p[2]) if len(p) > 2 else None,
                    "share": _fraccion(p[3]) if len(p) > 3 else None,
                    "procedencia": proc.clave(),
                })

        elif seccion == "lenders":
            for clave, valor in pares:
                if clave != "lender":
                    continue
                v = _limpio(valor)
                if v is None:
                    continue
                p = [x.strip() for x in v.split("|")]
                perfil.lenders.append({
                    "nombre": p[0] if p else None,
                    "ops": _entero(p[1]) if len(p) > 1 else None,
                    "share": _fraccion(p[2]) if len(p) > 2 else None,
                })

        elif seccion == "title_companies":
            for clave, valor in pares:
                if clave == "title" and _limpio(valor):
                    perfil.title_companies.append({"nombre": _limpio(valor)})

        elif seccion == "geography":
            for clave, valor in pares:
                if clave != "condado":
                    continue
                v = _limpio(valor)
                if v is None:
                    continue
                p = [x.strip() for x in v.split("|")]
                perfil.condados.append({
                    "fips": _limpio(p[0]) if p else None,
                    "nombre": _limpio(p[1]) if len(p) > 1 else None,
                    "unidades": _entero(p[2]) if len(p) > 2 else None,
                    "pct": _fraccion(p[3]) if len(p) > 3 else None,
                })

        elif seccion == "contacts":
            for clave, valor in pares:
                if clave != "contacto":
                    continue
                v = _limpio(valor)
                if v is None:
                    continue
                p = [x.strip() for x in v.split("|")]
                if len(p) < 2:
                    raise CapturaInvalida(
                        "contacto %r sin valor. Formato: tipo|valor|confianza_pct"
                        % v
                    )
                perfil.contactos.append({
                    "tipo": p[0].lower(),
                    "valor": p[1],
                    "confianza": _fraccion(p[2]) if len(p) > 2 else None,
                })

        elif seccion == "ausencias_declaradas":
            for clave, valor in pares:
                if clave == "ausencia" and _limpio(valor):
                    perfil.ausencias_declaradas.append(_limpio(valor))  # type: ignore[arg-type]

    return perfil


def leer_benchmark_condado(ruta: str | Path) -> BenchmarkCondado:
    """Lee una captura de benchmark de condado. Esto es el activo permanente."""
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8")
    _verificar_esquema(texto)
    cabecera, lineas = _secciones(texto)
    campos = dict(cabecera)
    for _, clave, valor in lineas:
        campos.setdefault(clave, valor)

    fips = _limpio(campos.get("fips"))
    if fips and not re.fullmatch(r"\d{5}", fips):
        raise CapturaInvalida(
            "FIPS %r invalido: son 5 digitos, estado(2)+condado(3). El nombre "
            "no sirve como llave: hay 31 condados llamados Washington." % fips
        )

    capturado = _fecha_hora(campos.get("capturado_en"))
    proc = None
    if capturado:
        proc = Procedencia(
            pestana="market_signals",
            capturado_en=capturado,
            ventana_declarada=_limpio(campos.get("ventana_declarada")) or "[sin declarar]",
            metodo="texto_pegado",
        )

    def multi(prefijo: str) -> dict[str, float]:
        salida: dict[str, float] = {}
        for _, clave, valor in lineas:
            if clave != prefijo:
                continue
            v = _limpio(valor)
            if v is None or "|" not in v:
                continue
            etiqueta, _, pct = v.partition("|")
            f = _fraccion(pct)
            if f is not None:
                salida[etiqueta.strip()] = f
        # tambien admite el formato "mix: FHA|0.21" que deja la clave como 'mix'
        return salida

    bench = BenchmarkCondado(
        fips=fips,
        nombre_condado=_limpio(campos.get("nombre_condado")),
        estado=_limpio(campos.get("estado")),
        los_activos=_entero(campos.get("los_activos")),
        fallout_pct=_fraccion(campos.get("fallout_pct")),
        fallout_denominador=_entero(campos.get("fallout_denominador")),
        dias_medios_al_cierre=_decimal(campos.get("dias_medios_al_cierre")),
        mix_tipo_prestamo=multi("mix"),
        mix_denominador=_entero(campos.get("mix_denominador")),
        distribucion_score=multi("score"),
        tipos_de_comprador=multi("comprador"),
        generacion=multi("generacion"),
        tasa_media=_decimal(campos.get("tasa_media")),
        ltv_medio=_fraccion(campos.get("ltv_medio")),
        ingreso_medio_hogar=_decimal(campos.get("ingreso_medio_hogar")),
        canal=multi("canal"),
        tipo_de_lender=multi("tipo_de_lender"),
        procedencia=proc,
    )

    if bench.fallout_pct is not None and bench.fallout_denominador is None:
        raise CapturaInvalida(
            "fallout_pct sin fallout_denominador. Ningun porcentaje se reporta "
            "sin su denominador: el fallout es el argumento comercial entero y "
            "un 22%% sobre 9 solicitudes no es un argumento."
        )
    if bench.mix_tipo_prestamo and bench.mix_denominador is None:
        raise CapturaInvalida(
            "hay mix de tipo de prestamo sin mix_denominador. Sin el, el mix no "
            "puede activar ni desactivar ningun qualifier."
        )
    return bench


# ── Diagnostico de las trampas ────────────────────────────────────────────────

def diagnosticar(perfil: PerfilAgente) -> dict:
    """Aplica las cuatro trampas verificadas y devuelve un informe.

    No modifica el perfil y no resuelve los conflictos. Los expone.
    """
    informe: dict = {
        "licencia": perfil.licencia,
        "conflictos_de_conteo": perfil.conflictos_de_conteo(),
        "avisos": [],
        "wallet_share_por_base": {},
    }

    es_prospecto, motivo = perfil.es_prospecto()
    informe["es_prospecto"] = es_prospecto
    if motivo:
        informe["avisos"].append(motivo)

    # Trampa 1: dos definiciones de wallet share
    for ws in perfil.wallet_shares:
        informe["wallet_share_por_base"].setdefault(ws.base, []).append(
            {"lender": ws.lender, "share": ws.share,
             "pestana": ws.procedencia.pestana}
        )
    bases = set(informe["wallet_share_por_base"])
    if len(bases) > 1:
        informe["avisos"].append(
            "hay wallet share por %s. Son definiciones distintas del mismo "
            "perfil y ninguna es 'la correcta': la de Overview es por unidades, "
            "la de Originators por volumen. Reportar ambas, etiquetadas."
            % " y por ".join(sorted(bases))
        )

    # Trampa 3: concentracion que no es concentracion
    ops_identificadas = sum(
        (o.get("ops") or 0) for o in perfil.originadores
    )
    buyside = None
    for c in perfil.conteos:
        if c.buy is not None:
            buyside = c.buy if buyside is None else min(buyside, c.buy)
    if buyside is not None and ops_identificadas:
        if ops_identificadas < buyside:
            informe["avisos"].append(
                "Top-N Concentration calculado sobre %d de %d unidades del lado "
                "comprador. Si suma 100%%, eso NO es concentracion: es que solo "
                "hay %d operaciones casadas con un originador. La tasa de "
                "casamiento hipotecario es baja y visible."
                % (ops_identificadas, buyside, ops_identificadas)
            )
        informe["tasa_de_casamiento"] = "%d/%d" % (ops_identificadas, buyside)

    # Trampa 4: Side Focus contra el conteo de lados
    if perfil.side_focus and perfil.conteos:
        informe["avisos"].append(
            "'Side Focus' dice %r y el conteo buy/sell viene aparte. Los dos se "
            "guardan: reportan cosas distintas." % perfil.side_focus
        )

    # Contactos: se guardan todos
    if perfil.contactos:
        informe["n_contactos"] = len(perfil.contactos)
        bajos = [c for c in perfil.contactos
                 if c.get("confianza") is not None and c["confianza"] < 0.5]
        if bajos:
            informe["avisos"].append(
                "%d de %d contactos con confianza bajo 50%%. NO se descartan: el "
                "de nuestra lista puede coincidir con un secundario, y ese cruce "
                "es la unica forma de confirmar identidad."
                % (len(bajos), len(perfil.contactos))
            )

    if perfil.ausencias_declaradas:
        informe["ausencias_declaradas"] = list(perfil.ausencias_declaradas)

    return informe
