"""Pruebas de la capa de identidad.

    python tests/test_identidad.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from identidad.cascada import (  # noqa: E402
    Candidato,
    Confianza,
    LogDeConflictos,
    cruzar,
    mejor_cruce,
)
from identidad.normalizacion import (  # noqa: E402
    a_e164,
    clave_de_licencia,
    clave_de_nombre,
    normalizar_email,
    normalizar_licencia,
    tokens_de_nombre,
)
from identidad.registro import RegistroUnificado  # noqa: E402
from identidad.valores import Campo  # noqa: E402

HOY = dt.date(2026, 9, 21)


# ══ NORMALIZACION ═════════════════════════════════════════════════════════════

def test_e164_acepta_las_cuatro_formas_del_mismo_numero():
    """El mismo numero venia como cuatro cadenas distintas de cuatro fuentes."""
    for crudo in ("+1 (512) 522-0477", "5125220477", "512.522.0477",
                  "1-512-522-0477", " (512) 522 0477 "):
        num, motivo = a_e164(crudo)
        assert num == "+15125220477", "%r dio %r (%s)" % (crudo, num, motivo)


def test_e164_rechaza_lo_que_no_es_un_telefono():
    for crudo, esperado in (
        ("", "vacio"),
        ("abc", "sin digitos"),
        ("12345", "solo 5 digitos"),
        ("0125220477", "no existe en el NANP"),
        ("1115220477", "no existe en el NANP"),
        ("5121110477", "no existe en el NANP"),
        ("1111111111", "no existe en el NANP"),
        ("521234567890123", "internacional"),
    ):
        num, motivo = a_e164(crudo)
        assert num is None, "%r se acepto como %r" % (crudo, num)
        assert esperado in motivo, "%r dio motivo %r" % (crudo, motivo)


def test_e164_declara_que_habia_extension():
    num, motivo = a_e164("512-522-0477 ext 204")
    assert num == "+15125220477"
    assert "extension" in motivo


def test_email_no_junta_a_dos_personas_quitando_puntos():
    """En Gmail a.b@ y ab@ son iguales; en un dominio corporativo no."""
    a, _ = normalizar_email("Ana.Tapia@casaprorealty.com")
    b, _ = normalizar_email("AnaTapia@casaprorealty.com")
    assert a == "ana.tapia@casaprorealty.com"
    assert b == "anatapia@casaprorealty.com"
    assert a != b


def test_email_rechaza_dominios_de_relleno():
    for crudo in ("x@example.com", "nada@noemail.com", "a@na.com"):
        mail, motivo = normalizar_email(crudo)
        assert mail is None
        assert "relleno" in motivo


def test_clave_de_nombre_resuelve_apellido_coma_nombre():
    assert clave_de_nombre("TAPIA, ANA") == clave_de_nombre("Ana Tapia")
    assert clave_de_nombre("Ana Tapia") == "ana|tapia"


def test_el_ruido_de_oficio_no_es_parte_del_nombre():
    assert tokens_de_nombre("Ana Tapia, REALTOR® ABR GRI") == ["ana", "tapia"]


def test_licencia_no_pierde_ceros_a_la_izquierda():
    """En California 01998877 y 1998877 son cadenas distintas."""
    norm, _ = normalizar_licencia("01998877", "CA")
    assert norm == "01998877"


def test_licencia_sin_formato_verificado_avisa():
    norm, aviso = normalizar_licencia("01998877", "CA")
    assert norm == "01998877"
    assert "no hay formato verificado" in aviso, (
        "si no verificamos el formato del estado, hay que decirlo"
    )


def test_licencia_fuera_de_formato_conocido_avisa_pero_guarda():
    norm, aviso = normalizar_licencia("AB", "TX")
    assert norm is None or "no coincide" in aviso


def test_clave_de_licencia_lleva_el_estado():
    """Hay una licencia 654321 en Texas y otra en Florida."""
    assert clave_de_licencia("654321", "TX") == "TX:654321"
    assert clave_de_licencia("654321", "FL") != clave_de_licencia("654321", "TX")


# ══ VALORES VERSIONADOS ═══════════════════════════════════════════════════════

def test_agregar_no_sobrescribe():
    c = Campo("telefono")
    c.agregar("+15125550100", fuente="mmi", fecha=HOY, confianza=0.9)
    c.agregar("+15125550199", fuente="board_los", fecha=HOY, confianza=0.7)
    assert len(c.valores) == 2
    assert c.preferido().valor == "+15125550100"
    assert c.en_conflicto is True


def test_el_conflicto_se_registra_no_se_resuelve():
    c = Campo("telefono")
    c.agregar("+15125550100", fuente="mmi", fecha=HOY, confianza=0.9)
    c.agregar("+15125550199", fuente="board_los", fecha=HOY, confianza=0.7)
    texto = " ".join(c.conflictos())
    assert "2 valores distintos" in texto
    assert "mmi" in texto and "board_los" in texto


def test_el_mismo_valor_de_la_misma_fuente_se_refresca_no_se_duplica():
    c = Campo("email")
    c.agregar("a@x.com", fuente="mmi", fecha=dt.date(2026, 1, 1), confianza=0.8)
    c.agregar("a@x.com", fuente="mmi", fecha=HOY, confianza=0.8)
    assert len(c.valores) == 1
    assert c.valores[0].fecha == HOY


def test_confianza_en_porcentaje_se_rechaza():
    c = Campo("email")
    try:
        c.agregar("a@x.com", fuente="model_match", fecha=HOY, confianza=92)
    except ValueError as exc:
        assert "porcentaje" in str(exc)
    else:
        raise AssertionError("acepto confianza=92")


def test_a_dict_guarda_todos_los_valores():
    c = Campo("email")
    c.agregar("a@x.com", fuente="model_match", fecha=HOY, confianza=0.92)
    c.agregar("b@y.com", fuente="model_match", fecha=HOY, confianza=0.31)
    d = c.a_dict()
    assert d["n_valores"] == 2
    assert len(d["valores"]) == 2, (
        "el de baja confianza puede ser el que coincide con nuestra lista"
    )


# ══ CASCADA ═══════════════════════════════════════════════════════════════════

def _nuestro(**kw):
    base = dict(id_fuente="r-1", fuente="lote_original", nombre="Ana Tapia",
                estado="TX", condado="Harris", unidades=13.0)
    base.update(kw)
    return Candidato(**base)


def test_escalon_1_licencia_es_cierto():
    a = _nuestro(licencia="654321")
    b = Candidato(id_fuente="mm-9", fuente="model_match", nombre="A. Tapia",
                  licencia="654321", estado="TX")
    c = cruzar(a, b)
    assert c.confianza is Confianza.CIERTO
    assert c.escalon == "licencia_estatal"


def test_dos_licencias_distintas_del_mismo_estado_no_es_la_misma_persona():
    """Aunque el nombre coincida exacto."""
    a = _nuestro(licencia="654321")
    b = Candidato(id_fuente="mm-9", fuente="model_match", nombre="Ana Tapia",
                  licencia="999999", estado="TX")
    c = cruzar(a, b)
    assert c.confianza is Confianza.NINGUNO
    assert "No es la misma persona" in c.evidencia


def test_escalon_2_telefono_con_nombre_compatible_es_alto():
    a = _nuestro(telefonos=["(512) 522-0477"])
    b = Candidato(id_fuente="mmi-3", fuente="mmi", nombre="Ana Tapia",
                  telefonos=["5125220477"])
    c = cruzar(a, b)
    assert c.confianza is Confianza.ALTO
    assert c.escalon == "telefono_e164"


def test_telefono_sin_nombre_compatible_es_medio_no_alto():
    """Puede ser un telefono de oficina compartido."""
    a = _nuestro(telefonos=["(512) 522-0477"])
    b = Candidato(id_fuente="mmi-3", fuente="mmi", nombre="Jose Ramirez",
                  telefonos=["5125220477"])
    c = cruzar(a, b)
    assert c.confianza is Confianza.MEDIO
    assert "oficina compartido" in c.evidencia
    assert c.se_puede_contactar is True
    assert c.confianza.se_puede_afirmar_identidad is False


def test_escalon_4_nombre_condado_volumen_es_bajo_y_no_se_contacta():
    a = _nuestro()
    b = Candidato(id_fuente="mm-1", fuente="model_match", nombre="Ana Tapia",
                  condado="Harris", unidades=15.0)
    c = cruzar(a, b)
    assert c.confianza is Confianza.BAJO
    assert c.se_puede_contactar is False
    assert "revision manual" in c.evidencia


def test_volumen_se_compara_como_rango_no_como_cifra():
    """Las unidades vienen apelmazadas: 689 filas con 9 y 679 con 10."""
    a = _nuestro(unidades=9.0)
    cerca = Candidato(id_fuente="x", fuente="mmi", nombre="Ana Tapia",
                      condado="Harris", unidades=11.0)
    lejos = Candidato(id_fuente="y", fuente="mmi", nombre="Ana Tapia",
                      condado="Harris", unidades=40.0)
    assert cruzar(a, cerca).confianza is Confianza.BAJO
    assert cruzar(a, lejos).confianza is Confianza.NINGUNO


def test_nombre_de_pila_suelto_no_cruza():
    a = _nuestro(nombre="Ana Tapia")
    b = Candidato(id_fuente="x", fuente="mmi", nombre="Ana Gomez",
                  condado="Harris", unidades=13.0)
    assert cruzar(a, b).confianza is Confianza.NINGUNO


def test_apellido_largo_solo_alcanza_para_compatible():
    a = _nuestro(nombre="Maria Villanueva", telefonos=["5125220477"])
    b = Candidato(id_fuente="x", fuente="mmi", nombre="M. Villanueva",
                  telefonos=["5125220477"])
    assert cruzar(a, b).confianza is Confianza.ALTO


def test_los_conflictos_se_acumulan_incluso_con_cruce_cierto():
    """Misma licencia, telefonos distintos: es la misma persona con un
    telefono en disputa, y eso hay que saberlo."""
    a = _nuestro(licencia="654321", telefonos=["5125550100"],
                 emails=["ana@casaprorealty.com"])
    b = Candidato(id_fuente="mm", fuente="model_match", nombre="Ana Tapia",
                  licencia="654321", estado="TX",
                  telefonos=["5125550199"], emails=["atapia@gmail.com"])
    c = cruzar(a, b)
    assert c.confianza is Confianza.CIERTO
    assert any("telefono:" in x for x in c.conflictos)
    assert any("email:" in x for x in c.conflictos)


def test_dos_candidatos_que_cruzan_igual_no_se_desempatan_por_orden():
    a = _nuestro(telefonos=["5125220477"])
    b1 = Candidato(id_fuente="x1", fuente="mmi", nombre="Ana Tapia",
                   telefonos=["5125220477"])
    b2 = Candidato(id_fuente="x2", fuente="mmi", nombre="Ana Tapia",
                   telefonos=["5125220477"])
    elegido, cruce = mejor_cruce(a, [b1, b2])
    assert elegido is None
    assert cruce.escalon == "ambiguo"
    assert "inventar" in cruce.evidencia


def test_pero_dos_con_la_misma_licencia_si_se_resuelven():
    a = _nuestro(licencia="654321")
    b1 = Candidato(id_fuente="x1", fuente="mmi", nombre="Ana Tapia",
                   licencia="654321", estado="TX")
    b2 = Candidato(id_fuente="x2", fuente="mmi", nombre="Ana Tapia",
                   licencia="654321", estado="TX")
    elegido, cruce = mejor_cruce(a, [b1, b2])
    assert elegido is not None
    assert cruce.confianza is Confianza.CIERTO


# ══ REGISTRO UNIFICADO ════════════════════════════════════════════════════════

def test_model_match_entrega_varios_contactos_y_se_guardan_todos():
    """El de nuestra lista puede coincidir con un secundario."""
    reg = RegistroUnificado(id_interno="r-42")
    mm = Candidato(
        id_fuente="mm-9", fuente="model_match", nombre="Ana Tapia",
        licencia="654321", estado="TX",
        emails=["ana@casaprorealty.com", "atapia@gmail.com", "ana.t@old.com"],
        telefonos=["5125550100", "5125550199"],
    )
    cruce = cruzar(Candidato(id_fuente="r-42", fuente="lote_original",
                             nombre="Ana Tapia", licencia="654321",
                             estado="TX"), mm)
    reg.absorber(mm, cruce, fecha=HOY, confianzas_de_contacto={
        "ana@casaprorealty.com": 0.92,
        "atapia@gmail.com": 0.31,
        "ana.t@old.com": 0.15,
        "5125550100": 0.88,
        "5125550199": 0.44,
    })

    emails = reg.todos_los_emails()
    assert len(emails) == 3, "los de baja confianza NO se descartan"
    assert emails[0]["valor"] == "ana@casaprorealty.com"
    assert any(abs(e["confianza"] - 0.15) < 1e-9 for e in emails)
    assert len(reg.todos_los_telefonos()) == 2


def test_la_confianza_del_cruce_pone_techo_a_la_del_dato():
    """Un email perfecto que llego por un cruce debil no vale mas que el cruce."""
    reg = RegistroUnificado(id_interno="r-1")
    otro = Candidato(id_fuente="x", fuente="mmi", nombre="Ana Tapia",
                     condado="Harris", unidades=13.0,
                     emails=["ana@casaprorealty.com"])
    cruce = cruzar(_nuestro(), otro)
    assert cruce.confianza is Confianza.BAJO
    reg.absorber(otro, cruce, fecha=HOY,
                 confianzas_de_contacto={"ana@casaprorealty.com": 0.99})
    email = reg.campos["email"].preferido()
    assert email.confianza <= 0.35, (
        "el techo del cruce BAJO es 0,35: %r" % email.confianza
    )


def test_un_cruce_ninguno_no_absorbe_nada_y_deja_aviso():
    reg = RegistroUnificado(id_interno="r-1")
    otro = Candidato(id_fuente="x", fuente="mmi", nombre="Jose Ramirez")
    cruce = cruzar(_nuestro(), otro)
    reg.absorber(otro, cruce, fecha=HOY)
    assert reg.preferido("email") is None
    assert any("NO se absorbio" in a for a in reg.avisos)


def test_telefono_invalido_deja_aviso_no_se_guarda_silenciosamente():
    reg = RegistroUnificado(id_interno="r-1")
    otro = Candidato(id_fuente="x", fuente="mmi", nombre="Ana Tapia",
                     licencia="654321", estado="TX",
                     telefonos=["0000000000", "5125220477"])
    cruce = cruzar(_nuestro(licencia="654321"), otro)
    reg.absorber(otro, cruce, fecha=HOY)
    assert len(reg.todos_los_telefonos()) == 1
    assert any("descartado" in a for a in reg.avisos)


def test_nmls_propio_descarta_como_prospecto():
    reg = RegistroUnificado(id_interno="r-1")
    reg.marcar_nmls("1234567", fuente="nmls", fecha=HOY)
    ok, motivo = reg.es_prospecto
    assert ok is False
    assert "origina el mismo" in motivo.lower()


def test_contactabilidad_r9_y_la_compuerta():
    vacio = RegistroUnificado(id_interno="r-1")
    assert vacio.contactabilidad()[0] == 0

    reg = RegistroUnificado(id_interno="r-2")
    otro = Candidato(id_fuente="x", fuente="model_match", nombre="Ana Tapia",
                     licencia="654321", estado="TX",
                     telefonos=["5125220477"], emails=["ana@casaprorealty.com"])
    cruce = cruzar(_nuestro(licencia="654321"), otro)
    reg.absorber(otro, cruce, fecha=HOY, confianzas_de_contacto={
        "5125220477": 0.9, "ana@casaprorealty.com": 0.95,
    })
    r9, razon = reg.contactabilidad()
    assert r9 >= 7, razon
    assert reg.a_fila()["id_pasa_compuerta_contactabilidad"] is True


def test_la_fila_trae_el_preferido_y_todos():
    reg = RegistroUnificado(id_interno="r-1")
    otro = Candidato(id_fuente="x", fuente="model_match", nombre="Ana Tapia",
                     licencia="654321", estado="TX",
                     emails=["a@x.com", "b@y.com"])
    cruce = cruzar(_nuestro(licencia="654321"), otro)
    reg.absorber(otro, cruce, fecha=HOY,
                 confianzas_de_contacto={"a@x.com": 0.9, "b@y.com": 0.2})
    fila = reg.a_fila()
    assert fila["id_email"] == "a@x.com"
    assert fila["id_email_n_valores"] == 2
    assert "b@y.com" in fila["id_emails_todos"]
    assert fila["id_email_fuente"] == "model_match"
    assert fila["id_email_fecha"] == "2026-09-21"


def test_log_de_conflictos_resume_por_campo():
    log = LogDeConflictos()
    a = _nuestro(licencia="654321", telefonos=["5125550100"])
    b = Candidato(id_fuente="mm", fuente="model_match", nombre="Ana Tapia",
                  licencia="654321", estado="TX", telefonos=["5125550199"])
    log.registrar("r-1", b, cruzar(a, b), fecha=HOY)
    resumen = log.resumen()
    assert resumen["registros_con_conflicto"] == 1
    assert resumen["conflictos_por_campo"]["telefono"] == 1
    assert "no se resuelve promediando" in resumen["nota"]


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
