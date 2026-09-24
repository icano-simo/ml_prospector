"""El 40,4% sin dolor primario: el copy mas usado de todos.

No es un defecto del motor
--------------------------
Es **la medicion de lo poco que sabemos de esa gente**. Por eso va como titular
del reporte y no como nota al pie: 1.716 de 4.249 personas sobre las que el
sistema no tiene nada que decir todavia es el hallazgo, no el residuo.

Tres reglas
-----------
1 · El copy se RAMIFICA por lo poco que si sabemos: estado, volumen, brokerage
    y lado comprador. Un generico igual para todos desperdicia los cuatro datos
    que si hay.
2 · La apertura es la PREGUNTA DEL LENDER, porque cierra la categoria vacia en
    el 100% de las filas -- es lo unico que sabemos que falta en todas.
3 · Estos registros van a COLA DE ENRIQUECIMIENTO, no de contacto. Primero
    Instagram y Model Match. Llamar sin saber nada quema el contacto y no
    devuelve informacion.
"""
from __future__ import annotations

from dataclasses import dataclass

#: El codigo que pone `motor.evaluar` cuando la compuerta J-Q01 cierra. Se
#: importa de alla, y no se copia, para que no haya dos literales que un dia
#: puedan separarse sin que nada falle.
from motor.evaluar import APERTURA_SIN_HIPOTECA as SIN_APERTURA_HIPOTECARIA
from motor.lectura import de_cada_diez, verificar_vocabulario

COLA_ENRIQUECIMIENTO = "enriquecimiento"
COLA_CONTACTO = "contacto"

#: Umbrales de volumen, en unidades al año del lado comprador.
ALTO = 24
MEDIO = 8


@dataclass
class CopySinDolor:
    titular: str
    cuerpo: str
    apertura: str
    cola: str
    rama: str
    #: Que habria que conseguir para que este realtor deje esta categoria.
    falta: tuple[str, ...]

    def __post_init__(self) -> None:
        for campo in (self.titular, self.cuerpo, self.apertura):
            verificar_vocabulario(campo)


def _volumen(unidades: float | None) -> str:
    if unidades is None:
        return "sin_volumen"
    if unidades >= ALTO:
        return "alto"
    if unidades >= MEDIO:
        return "medio"
    return "bajo"


def copy_sin_dolor(realtor: dict, *, nombre_estado: str | None = None,
                   apertura_motor: str | None = None) -> CopySinDolor:
    """El copy del caso mas frecuente, ramificado por lo poco que sabemos."""
    nombre = (realtor.get("nombre_completo") or "").strip() or "este realtor"
    # Los nombres del libro vienen en mayusculas; en una frase eso grita.
    if nombre.isupper():
        nombre = nombre.title()
    estado = nombre_estado or realtor.get("estado") or "su estado"

    # ── LA COMPUERTA J-Q01 NO ES «NO SABEMOS» ───────────────────────────────
    #
    # Sin esta rama, quien cierra la mayoria de sus operaciones del lado
    # vendedor caeria en el copy de arriba --«lo que falta es nuestro»,
    # cola de enriquecimiento-- y es exactamente al reves: de el sabemos
    # bastante, incluido lo que lo descarta. Lo que no aplica es EL ANGULO.
    #
    # Y se puede contactar. La pregunta no es de financiamiento del comprador
    # como producto suyo, es de una venta suya que se cae porque al comprador
    # no le sale el prestamo -- que es el unico lugar donde una hipoteca le
    # duele a un agente de listings.
    if apertura_motor == SIN_APERTURA_HIPOTECARIA:
        return CopySinDolor(
            titular=("A %s no le abrimos por la hipoteca: su negocio no pasa "
                     "por ahí." % nombre),
            cuerpo=("Cierra la mayoría de sus operaciones del lado vendedor, "
                    "según su propio registro de Model Match. Un ángulo de "
                    "financiamiento del comprador no le toca el negocio, y "
                    "abrirle con uno es decirle que no lo conocemos."),
            apertura=("¿Se te ha caído alguna venta este año porque al "
                      "comprador no le salió el préstamo?"),
            cola=COLA_CONTACTO, rama="sin apertura hipotecaria",
            falta=("con qué lender trabajan los compradores de sus listings",))
    brokerage = (realtor.get("brokerage") or "").strip()
    unidades = realtor.get("unidades_ano")
    rama_vol = _volumen(unidades)

    falta = ["con qué lender trabaja hoy"]
    if not realtor.get("sf_lead_id"):
        falta.append("una llave dura para pegarle lo que averigüemos")
    falta.append("su perfil de Model Match")
    falta.append("su Instagram")

    # ── el cuerpo, por rama ──────────────────────────────────────────────────
    if rama_vol == "alto":
        cuerpo = ("%s cierra %s operaciones al año en %s. Es volumen "
                  "suficiente para que su lender actual sea una relación "
                  "establecida, no una casualidad."
                  % (nombre, "{:,.0f}".format(unidades).replace(",", "."),
                     estado))
        rama = "volumen alto"
    elif rama_vol == "medio":
        cuerpo = ("%s cierra %s operaciones al año en %s. A ese ritmo, una o "
                  "dos operaciones que se caen le pesan en el año."
                  % (nombre, "{:,.0f}".format(unidades).replace(",", "."),
                     estado))
        rama = "volumen medio"
    elif rama_vol == "bajo":
        cuerpo = ("%s cierra pocas operaciones al año en %s. Puede ser "
                  "part-time o puede estar empezando, y eso cambia por "
                  "completo qué le sirve de nosotros." % (nombre, estado))
        rama = "volumen bajo"
    else:
        cuerpo = ("De %s sabemos que opera en %s y poco más." % (nombre,
                                                                 estado))
        rama = "sin volumen"

    if brokerage:
        cuerpo += (" Trabaja en %s, así que es probable que tenga un lender "
                   "preferido de la oficina." % brokerage)
        rama += " + brokerage"

    titular = ("No tenemos todavía un dolor que nombrarle a %s. Lo que falta "
               "no es del realtor: es nuestro." % nombre)

    # ── la apertura · siempre la pregunta del lender ────────────────────────
    apertura = ("¿Con qué lender estás cerrando hoy, y qué es lo que más se "
                "te complica con ellos — el pre-approval, los tiempos o el "
                "closing?")

    return CopySinDolor(titular=titular, cuerpo=cuerpo, apertura=apertura,
                        cola=COLA_ENRIQUECIMIENTO, rama=rama,
                        falta=tuple(falta))


def titular_del_reporte(sin_dolor: int, total: int) -> str:
    """El numero va ARRIBA del reporte, no al pie.

    En lenguaje hablado, porque se lee sin traducir.
    """
    if not total:
        return "No hay realtors evaluados todavía."
    pct = 100.0 * sin_dolor / total
    hablado = de_cada_diez(pct)
    cuanto = hablado or ("%s%%" % ("%g" % round(pct, 1)).replace(".", ","))
    return ("De cada diez realtors del lote, sobre %s no tenemos todavía nada "
            "que decirles: %s de %s. No es un fallo del motor — es la medida "
            "de lo poco que sabemos de esa gente, y es el trabajo que sigue."
            % (cuanto.replace(" de cada diez", ""),
               "{:,.0f}".format(sin_dolor).replace(",", "."),
               "{:,.0f}".format(total).replace(",", ".")))
