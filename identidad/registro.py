"""El registro unificado de un realtor. Acumula fuentes, nunca sobrescribe.

Como se usa
-----------
    reg = RegistroUnificado(id_interno="r-00042")
    reg.absorber(candidato_de_licencias, cruce_cierto, fecha=hoy)
    reg.absorber(candidato_de_mmi, cruce_alto, fecha=hoy)
    reg.absorber(candidato_de_model_match, cruce_alto, fecha=hoy)

    reg.telefono_preferido()   -> para operar
    reg.todos_los_telefonos()  -> todos, con confianza, que es lo que se guarda
    reg.a_fila()               -> la fila de la sabana
    reg.conflictos()           -> lo que hay que resolver a mano

Lo que este objeto garantiza
----------------------------
1. Nada se sobrescribe. `absorber` acumula valores con su fuente y fecha.
2. Ningun dato entra con confianza menor a MEDIO sin quedar marcado.
3. Los contactos de Model Match entran TODOS, con su porcentaje de confianza.
   El de nuestra lista puede coincidir con un secundario, y descartar los
   secundarios es perder el unico cruce posible.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from identidad.cascada import Candidato, Confianza, Cruce
from identidad.normalizacion import a_e164, normalizar_email, normalizar_licencia
from identidad.valores import Campo, Valor

#: Campos que el registro mantiene versionados.
CAMPOS = (
    "nombre", "licencia", "estado", "condado", "brokerage",
    "telefono", "email", "unidades", "nmls",
)


@dataclass
class RegistroUnificado:
    """Un realtor visto por todas las fuentes, con la procedencia de cada dato."""

    id_interno: str
    campos: dict[str, Campo] = field(default_factory=dict)
    #: {fuente: (id en esa fuente, confianza del cruce, escalon, evidencia)}
    procedencia_de_cruces: dict[str, dict] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for nombre in CAMPOS:
            self.campos.setdefault(nombre, Campo(nombre))

    # ── Entrada de datos ──────────────────────────────────────────────────────

    def absorber(
        self,
        otro: Candidato,
        cruce: Cruce,
        *,
        fecha: dt.date | None = None,
        confianzas_de_contacto: dict[str, float] | None = None,
    ) -> None:
        """Incorpora los datos de una fuente cruzada.

        `confianzas_de_contacto` es el mapa {valor de contacto: confianza 0-1}
        que entrega Model Match. Se guarda tal cual, por contacto.
        """
        fecha = fecha or dt.date.today()

        if cruce.confianza is Confianza.NINGUNO:
            self.avisos.append(
                "NO se absorbio %s/%s: %s"
                % (otro.fuente, otro.id_fuente, cruce.evidencia)
            )
            return

        self.procedencia_de_cruces[otro.fuente] = {
            "id_en_la_fuente": otro.id_fuente,
            "confianza": cruce.confianza.value,
            "escalon": cruce.escalon,
            "evidencia": cruce.evidencia,
            "fecha": fecha.isoformat(),
        }

        if not cruce.confianza.se_puede_afirmar_identidad:
            self.avisos.append(
                "%s entro con confianza %s (%s): sus datos sirven para "
                "enriquecer, no para afirmar identidad"
                % (otro.fuente, cruce.confianza.value, cruce.escalon)
            )

        # La confianza del cruce pone techo a la del dato: un email perfecto
        # que llego por un cruce debil no vale mas que el cruce.
        techo = {
            Confianza.CIERTO: 1.0, Confianza.ALTO: 0.85,
            Confianza.MEDIO: 0.6, Confianza.BAJO: 0.35,
        }[cruce.confianza]

        def agregar(campo: str, valor, *, confianza: float | None = None,
                    nota: str | None = None) -> None:
            if valor is None or (isinstance(valor, str) and not valor.strip()):
                return
            final = min(confianza, techo) if confianza is not None else techo
            self.campos[campo].agregar(
                valor, fuente=otro.fuente, fecha=fecha,
                confianza=final, nota=nota,
            )

        agregar("nombre", otro.nombre)
        agregar("estado", (otro.estado or "").strip().upper()[:2] or None)
        agregar("condado", otro.condado)
        agregar("unidades", otro.unidades)

        if otro.licencia:
            norm, aviso = normalizar_licencia(otro.licencia, otro.estado)
            agregar("licencia", norm, nota=aviso or None)
            if aviso:
                self.avisos.append("%s: %s" % (otro.fuente, aviso))

        mapa = confianzas_de_contacto or {}

        for crudo in otro.telefonos:
            num, aviso = a_e164(crudo)
            if num is None:
                self.avisos.append(
                    "telefono %r de %s descartado: %s" % (crudo, otro.fuente, aviso)
                )
                continue
            agregar("telefono", num, confianza=mapa.get(crudo), nota=aviso or None)

        for crudo in otro.emails:
            mail, aviso = normalizar_email(crudo)
            if mail is None:
                self.avisos.append(
                    "email %r de %s descartado: %s" % (crudo, otro.fuente, aviso)
                )
                continue
            agregar("email", mail, confianza=mapa.get(crudo))

    def marcar_nmls(self, nmls: str, *, fuente: str, fecha: dt.date | None = None
                    ) -> None:
        """Con NMLS propio origina el mismo: no es prospecto, es colega."""
        self.campos["nmls"].agregar(
            nmls, fuente=fuente, fecha=fecha or dt.date.today(), confianza=1.0,
        )

    # ── Lectura ───────────────────────────────────────────────────────────────

    def preferido(self, campo: str) -> Valor | None:
        return self.campos[campo].preferido() if campo in self.campos else None

    def telefono_preferido(self) -> str | None:
        v = self.preferido("telefono")
        return v.valor if v else None

    def todos_los_telefonos(self) -> list[dict]:
        return [
            {"valor": v.valor, "fuente": v.fuente, "confianza": v.confianza,
             "fecha": v.fecha.isoformat()}
            for v in self.campos["telefono"].todos()
        ]

    def todos_los_emails(self) -> list[dict]:
        return [
            {"valor": v.valor, "fuente": v.fuente, "confianza": v.confianza,
             "fecha": v.fecha.isoformat()}
            for v in self.campos["email"].todos()
        ]

    @property
    def es_prospecto(self) -> tuple[bool, str]:
        nmls = self.preferido("nmls")
        if nmls:
            return False, (
                "DESCARTADO: tiene NMLS propio (%s). Origina el mismo: es "
                "competencia o colega, no prospecto." % nmls.valor
            )
        return True, ""

    def contactabilidad(self) -> tuple[int, str]:
        """R9 de la capa de realtor. 0-10, y por que.

        R9 no entra al score ponderado: es operativa. Pero la compuerta 1 del
        sistema es R9 >= 7, y por debajo el registro va a **pre-MQL, cola de
        re-enriquecimiento, no descarte** -- un toque humano sobre un registro
        incompleto se pierde dos veces.
        """
        tels = self.campos["telefono"].todos()
        mails = self.campos["email"].todos()

        puntos = 0
        detalle: list[str] = []

        if tels:
            mejor = tels[0]
            puntos += 5 if (mejor.confianza or 0) >= 0.8 else 3
            detalle.append("%d telefono(s), mejor confianza %.0f%%"
                           % (len(tels), (mejor.confianza or 0) * 100))
        if mails:
            mejor = mails[0]
            puntos += 4 if (mejor.confianza or 0) >= 0.8 else 2
            detalle.append("%d email(s), mejor confianza %.0f%%"
                           % (len(mails), (mejor.confianza or 0) * 100))
        if self.preferido("licencia"):
            puntos += 1
            detalle.append("licencia conocida")

        if not detalle:
            return 0, "sin ningun canal de contacto"
        return min(puntos, 10), " · ".join(detalle)

    def conflictos(self) -> list[str]:
        salida: list[str] = []
        for campo in self.campos.values():
            salida.extend(campo.conflictos())
        return salida

    # ── Salida ────────────────────────────────────────────────────────────────

    def a_fila(self) -> dict:
        """La fila de la sabana. Trae el preferido Y todos los valores."""
        import json

        fila: dict = {"id_interno": self.id_interno}
        for nombre, campo in self.campos.items():
            pref = campo.preferido()
            fila["id_%s" % nombre] = pref.valor if pref else None
            fila["id_%s_fuente" % nombre] = pref.fuente if pref else None
            fila["id_%s_fecha" % nombre] = pref.fecha.isoformat() if pref else None
            fila["id_%s_confianza" % nombre] = pref.confianza if pref else None
            fila["id_%s_en_conflicto" % nombre] = campo.en_conflicto
            fila["id_%s_n_valores" % nombre] = len(campo.valores)

        # Todos los contactos, con su confianza. Es lo que pide el brief.
        fila["id_telefonos_todos"] = json.dumps(
            self.todos_los_telefonos(), ensure_ascii=False
        )
        fila["id_emails_todos"] = json.dumps(
            self.todos_los_emails(), ensure_ascii=False
        )

        r9, razon_r9 = self.contactabilidad()
        fila["id_r9_contactabilidad"] = r9
        fila["id_r9_razon"] = razon_r9
        fila["id_pasa_compuerta_contactabilidad"] = r9 >= 7

        prospecto, motivo = self.es_prospecto
        fila["id_es_prospecto"] = prospecto
        fila["id_motivo_descarte"] = motivo or None

        fila["id_fuentes_cruzadas"] = json.dumps(
            self.procedencia_de_cruces, ensure_ascii=False
        )
        fila["id_conflictos"] = json.dumps(self.conflictos(), ensure_ascii=False)
        fila["id_avisos"] = json.dumps(self.avisos, ensure_ascii=False)
        return fila

    def a_dict_completo(self) -> dict:
        """Todo, con la procedencia de cada valor. Para auditar una fila."""
        return {
            "id_interno": self.id_interno,
            "campos": {n: c.a_dict() for n, c in self.campos.items()},
            "cruces": self.procedencia_de_cruces,
            "conflictos": self.conflictos(),
            "avisos": self.avisos,
            "contactabilidad": self.contactabilidad(),
            "es_prospecto": self.es_prospecto,
        }
