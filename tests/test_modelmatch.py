"""Las cuatro trampas verificadas de Model Match, como pruebas.

Cada caso usa los numeros reales leidos en el perfil de prueba. Si el parser
deja de detectar una de estas, la prueba falla.

    python tests/test_modelmatch.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modelmatch.esquema import (  # noqa: E402
    ESQUEMA_VERSION,
    ConteoDeLados,
    PerfilAgente,
    Procedencia,
    WalletShareCapturado,
)
from modelmatch.parser import (  # noqa: E402
    CapturaInvalida,
    diagnosticar,
    leer_benchmark_condado,
    leer_perfil,
)


def _escribir(texto: str, sufijo: str = ".txt") -> Path:
    fd, ruta = tempfile.mkstemp(suffix=sufijo)
    os.close(fd)
    Path(ruta).write_text(texto, encoding="utf-8")
    return Path(ruta)


def _proc(pestana, momento, ventana="trailing 14 months"):
    return Procedencia(
        pestana=pestana,
        capturado_en=momento,
        ventana_declarada=ventana,
        metodo="texto_pegado",
    )


# ── Trampa 1 · dos definiciones de wallet share ───────────────────────────────

def test_trampa1_dos_bases_de_wallet_share_se_guardan_las_dos():
    """Overview 33/33/33 por unidades vs Originators 40,6/35,3/24,0 por volumen."""
    t0 = dt.datetime(2026, 9, 21, 10, 0, 0)
    t1 = dt.datetime(2026, 9, 21, 10, 4, 0)
    perfil = PerfilAgente(licencia="TX-123456")
    for lender, share in (("Lender A", 0.33), ("Lender B", 0.33), ("Lender C", 0.33)):
        perfil.wallet_shares.append(WalletShareCapturado(
            lender=lender, share=share, base="unidades", lado="sin_declarar",
            ops=None, procedencia=_proc("overview", t0),
        ))
    for lender, share in (("Lender A", 0.406), ("Lender B", 0.353), ("Lender C", 0.240)):
        perfil.wallet_shares.append(WalletShareCapturado(
            lender=lender, share=share, base="volumen", lado="sin_declarar",
            ops=None, procedencia=_proc("originators", t1),
        ))

    inf = diagnosticar(perfil)
    assert set(inf["wallet_share_por_base"]) == {"unidades", "volumen"}
    assert len(inf["wallet_share_por_base"]["unidades"]) == 3
    assert len(inf["wallet_share_por_base"]["volumen"]) == 3
    assert any("ninguna es 'la correcta'" in a for a in inf["avisos"])


# ── Trampa 2 · los numeros se mueven en la misma sesion ───────────────────────

def test_trampa2_conflicto_entre_pestanas_se_reporta_no_se_promedia():
    """7 buy / 21 sell / 15 total / 28 sold  vs  6 / 21 / 14 / 27."""
    perfil = PerfilAgente(licencia="TX-123456")
    perfil.conteos.append(ConteoDeLados(
        buy=7, sell=21, total=15, sold=28,
        procedencia=_proc("overview", dt.datetime(2026, 9, 21, 10, 0, 0)),
    ))
    perfil.conteos.append(ConteoDeLados(
        buy=6, sell=21, total=14, sold=27,
        procedencia=_proc("originators", dt.datetime(2026, 9, 21, 10, 4, 0)),
    ))

    conflictos = perfil.conflictos_de_conteo()
    texto = " ".join(conflictos)
    assert "buy" in texto and "7" in texto and "6" in texto
    assert "total" in texto
    assert "sold" in texto
    # sell coincide en las dos, no debe aparecer como conflicto de valores
    assert "sell reportado con" not in texto
    # y ninguna de las dos lecturas cuadra: buy+sell != total
    assert all(c.cuadra is False for c in perfil.conteos)


def test_trampa2_captura_sin_timestamp_se_rechaza():
    captura = """\
# esquema: {v}
licencia: TX-1

## overview  ventana: trailing 14 months
buy: 7
sell: 21
""".format(v=ESQUEMA_VERSION)
    ruta = _escribir(captura)
    try:
        leer_perfil(ruta)
    except CapturaInvalida as exc:
        assert "capturado_en" in str(exc)
    else:
        raise AssertionError("acepto una captura sin timestamp")
    finally:
        ruta.unlink()


# ── Trampa 3 · "Top 3 Concentration 100%" no es concentracion ────────────────

def test_trampa3_concentracion_que_es_tasa_de_casamiento():
    """3 de 14 unidades del lado comprador tenian tipo de prestamo conocido."""
    perfil = PerfilAgente(licencia="TX-123456")
    perfil.conteos.append(ConteoDeLados(
        buy=14, sell=21, total=35, sold=35,
        procedencia=_proc("overview", dt.datetime(2026, 9, 21, 10, 0, 0)),
    ))
    for nombre, ops in (("Orig A", 1), ("Orig B", 1), ("Orig C", 1)):
        perfil.originadores.append({"nombre": nombre, "nmls": None, "ops": ops,
                                    "share": 1 / 3})

    inf = diagnosticar(perfil)
    assert inf["tasa_de_casamiento"] == "3/14"
    assert any("NO es concentracion" in a for a in inf["avisos"])
    assert any("casamiento" in a for a in inf["avisos"])


# ── Trampa 4 · Side Focus contra el conteo de lados ──────────────────────────

def test_trampa4_side_focus_y_conteo_se_guardan_los_dos():
    perfil = PerfilAgente(licencia="TX-1", side_focus="Listing Side (75%)")
    perfil.conteos.append(ConteoDeLados(
        buy=7, sell=21, total=15, sold=28,
        procedencia=_proc("overview", dt.datetime(2026, 9, 21, 10, 0, 0)),
    ))
    inf = diagnosticar(perfil)
    assert any("Side Focus" in a for a in inf["avisos"])
    assert perfil.side_focus == "Listing Side (75%)"
    assert perfil.conteos[0].buy == 7


# ── Descarte por NMLS propio ─────────────────────────────────────────────────

def test_con_nmls_propio_no_es_prospecto():
    perfil = PerfilAgente(licencia="TX-1", nmls_si_tiene="1234567")
    ok, motivo = perfil.es_prospecto()
    assert ok is False
    assert "NMLS propio" in motivo
    assert diagnosticar(perfil)["es_prospecto"] is False


# ── Contactos: se guardan todos, tambien los de baja confianza ───────────────

def test_contactos_de_baja_confianza_no_se_descartan():
    captura = """\
# esquema: {v}
licencia: TX-1
apellido: Perez

## contacts  capturado_en: 2026-09-21 10:00
contacto: email|a@x.com|92
contacto: email|b@y.com|31
contacto: telefono|+15125550100|64
""".format(v=ESQUEMA_VERSION)
    ruta = _escribir(captura)
    try:
        perfil = leer_perfil(ruta)
        assert len(perfil.contactos) == 3
        inf = diagnosticar(perfil)
        assert inf["n_contactos"] == 3
        assert any("NO se descartan" in a for a in inf["avisos"])
    finally:
        ruta.unlink()


# ── Esquema declarado ─────────────────────────────────────────────────────────

def test_captura_sin_esquema_se_rechaza():
    ruta = _escribir("licencia: TX-1\n")
    try:
        leer_perfil(ruta)
    except CapturaInvalida as exc:
        assert "esquema" in str(exc)
    else:
        raise AssertionError("acepto una captura sin esquema declarado")
    finally:
        ruta.unlink()


def test_esquema_de_otra_version_se_rechaza():
    ruta = _escribir("# esquema: mm-captura-v0\nlicencia: TX-1\n")
    try:
        leer_perfil(ruta)
    except CapturaInvalida as exc:
        assert "no adivino" in str(exc).lower()
    else:
        raise AssertionError("acepto un esquema de otra version")
    finally:
        ruta.unlink()


# ── Benchmark de condado ──────────────────────────────────────────────────────

def test_benchmark_condado_completo():
    captura = """\
# esquema: {v}
fips: 48453
nombre_condado: Travis
estado: TX
los_activos: 3
capturado_en: 2026-09-21 11:30
ventana_declarada: trailing 14 months
fallout_pct: 22.4
fallout_denominador: 18420
dias_medios_al_cierre: 41.5
mix: FHA|18.2
mix: VA|6.1
mix: Conventional|74.0
mix: USDA|1.7
mix_denominador: 18420
score: <620|3.9
score: 620-679|12.4
comprador: primerizos|38.1
comprador: veteranos|5.2
tasa_media: 6.42
ltv_medio: 81.3
ingreso_medio_hogar: 98400
""".format(v=ESQUEMA_VERSION)
    ruta = _escribir(captura)
    try:
        b = leer_benchmark_condado(ruta)
        assert b.fips == "48453"
        assert b.los_activos == 3
        assert abs(b.fallout_pct - 0.224) < 1e-9
        assert b.fallout_denominador == 18420
        assert abs(b.dias_medios_al_cierre - 41.5) < 1e-9
        assert abs(b.mix_tipo_prestamo["FHA"] - 0.182) < 1e-9
        assert abs(b.ltv_medio - 0.813) < 1e-9
        assert b.ingreso_medio_hogar == 98400.0
        assert b.falta() == []
    finally:
        ruta.unlink()


def test_fallout_sin_denominador_se_rechaza():
    captura = """\
# esquema: {v}
fips: 48453
capturado_en: 2026-09-21 11:30
fallout_pct: 22.4
""".format(v=ESQUEMA_VERSION)
    ruta = _escribir(captura)
    try:
        leer_benchmark_condado(ruta)
    except CapturaInvalida as exc:
        assert "denominador" in str(exc)
    else:
        raise AssertionError("acepto un fallout sin denominador")
    finally:
        ruta.unlink()


def test_mix_sin_denominador_se_rechaza():
    captura = """\
# esquema: {v}
fips: 48453
capturado_en: 2026-09-21 11:30
mix: FHA|18.2
""".format(v=ESQUEMA_VERSION)
    ruta = _escribir(captura)
    try:
        leer_benchmark_condado(ruta)
    except CapturaInvalida as exc:
        assert "mix_denominador" in str(exc)
    else:
        raise AssertionError("acepto un mix sin denominador")
    finally:
        ruta.unlink()


def test_fips_por_nombre_se_rechaza():
    captura = """\
# esquema: {v}
fips: Travis
capturado_en: 2026-09-21 11:30
""".format(v=ESQUEMA_VERSION)
    ruta = _escribir(captura)
    try:
        leer_benchmark_condado(ruta)
    except CapturaInvalida as exc:
        assert "Washington" in str(exc)
    else:
        raise AssertionError("acepto un FIPS que no es un FIPS")
    finally:
        ruta.unlink()


def test_benchmark_incompleto_declara_que_falta():
    captura = """\
# esquema: {v}
fips: 48453
capturado_en: 2026-09-21 11:30
tasa_media: 6.42
""".format(v=ESQUEMA_VERSION)
    ruta = _escribir(captura)
    try:
        b = leer_benchmark_condado(ruta)
        faltan = b.falta()
        assert "fallout_pct" in faltan
        assert "dias_medios_al_cierre" in faltan
        assert "mix_tipo_prestamo" in faltan
    finally:
        ruta.unlink()


# ── Lectura de numeros con coma decimal ──────────────────────────────────────

def test_lee_coma_decimal_y_separador_de_miles():
    captura = """\
# esquema: {v}
licencia: TX-1

## originators  capturado_en: 2026-09-21 10:04  ventana: trailing 14 months
buy: 6
sell: 21
total: 14
sold: 27
ws_originators_1: Lender A|40,6|5
ws_originators_2: Lender B|35,3|4
ws_originators_3: Lender C|24,0|3
""".format(v=ESQUEMA_VERSION)
    ruta = _escribir(captura)
    try:
        perfil = leer_perfil(ruta)
        shares = sorted(w.share for w in perfil.wallet_shares)
        assert abs(shares[0] - 0.240) < 1e-9
        assert abs(shares[1] - 0.353) < 1e-9
        assert abs(shares[2] - 0.406) < 1e-9
        assert all(w.base == "volumen" for w in perfil.wallet_shares)
    finally:
        ruta.unlink()


def _main() -> int:
    pruebas = [(n, o) for n, o in sorted(globals().items())
               if n.startswith("test_") and callable(o)]
    fallos = []
    for nombre, fn in pruebas:
        try:
            fn()
            print("  ok   %s" % nombre)
        except Exception as exc:  # noqa: BLE001
            fallos.append((nombre, exc))
            print("  FALLA %s -- %r" % (nombre, exc))
    print("")
    print("%d pruebas, %d fallas" % (len(pruebas), len(fallos)))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(_main())
