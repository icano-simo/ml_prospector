"""El CSS de la maqueta -> `public/ficha_v3.css`, AISLADO y por contenedor.

Por que no se copia tal cual
----------------------------
La primera version lo copiaba sin tocar una regla, y la ficha se veia bien...
SUELTA, a 1200 px. Dentro de la app vive en un panel al lado de la lista --714
px con la ventana a 1440-- y ahi se rompia entera: una palabra por linea,
texto cortado y scroll horizontal.

Dos causas, las dos del mismo tipo:

1 · **Las clases chocaban.** `.grid`, `.mod`, `.veredicto`, `.fila`, `.chip` y
    `.persona` existen tambien en el CSS de la app. Dos hojas peleando por el
    mismo nombre no dan un ganador: dan un resultado que depende del orden de
    carga, y cambia solo el dia que alguien reordene dos `<link>`.

2 · **Los breakpoints miraban la VENTANA.** `@media (max-width: 860px)` con la
    ventana a 1440 no dispara nunca, aunque el panel mida 714. Un grid de tres
    columnas en 714 px son tres columnas de 230, y ahi «financiadas» no entra.

Que hace este script
--------------------
  · prefija TODA clase con `fv3-`;
  · mete todo bajo `.fv3-raiz`, para que ni los selectores de elemento
    --`table`, `p`, `h2`-- se escapen a la app;
  · pasa `:root` a `.fv3-raiz`, para que las variables de la maqueta no pisen
    las de `tokens.css`;
  · convierte los `@media (max-width)` en `@container`, para que respondan al
    ancho del PANEL;
  · y agrega un corte propio en 1000 px: por debajo, todo a una columna.

Se ejecuta y se commitea el resultado. Hacerlo a mano seria la forma de que
«igual a la maqueta» dejara de serlo en el primer retoque.
"""
import os
import re
import sys

ORIGEN = (r"C:\Users\icano.CL-390BQ04\Downloads\pedido_claude_code_ficha_cowork"
          r"\5_maqueta_v3_NO_REPO.html")
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "public", "ficha_v3.css")

PREFIJO = "fv3-"
RAIZ_CLASE = ".fv3-raiz"

#: La clase raíz DOBLADA, que es con lo que se scopa todo.
#:
#: Prefijar las clases no alcanzó, y el que quedó a la vista fue el nombre del
#: realtor: la app tiene `.main h1{font:800 21px var(--font-display)}` y la
#: maqueta `.fv3-raiz h1{font-family:"Bricolage Grotesque"}`. Misma
#: especificidad (0,1,1), así que gana la hoja que va última -- y el `<style>`
#: de `index.html` va después del `<link>`. No hay clase que chocara: choca un
#: selector de ELEMENTO bajo una clase de la app, que el prefijo no puede ver.
#:
#: `.fv3-raiz.fv3-raiz` es la misma clase escrita dos veces: selecciona
#: exactamente lo mismo y sube la especificidad a (0,2,1). Es más barato que
#: poner `!important` en 176 reglas, y no obliga a la app a saber que la ficha
#: existe.
RAIZ_FUERTE = ".fv3-raiz.fv3-raiz"

#: Por debajo de esto --del PANEL, no de la ventana-- todo va a una columna.
#:
#: 860, que es el corte de la maqueta. La primera versión lo puso en 1000 «por
#: si acaso», y el resultado fue que con la ventana a 1280 --el panel mide 892--
#: la app mostraba una columna donde la maqueta muestra dos. El criterio es
#: parecerse a la maqueta; apretar más que ella hay que ganárselo con una
#: medición, y a 892 px la lista de aceptación pasa entera.
CORTE_UNA_COLUMNA = 860

#: Y por debajo de este, las tablas de prosa se apilan. Es otro corte y no el
#: mismo: a 900 px una tabla de cuatro columnas se lee bien; a 350 no.
CORTE_TABLAS_APILADAS = 620

#: Las reglas de la maqueta que parten en varias columnas. Se anulan enteras
#: por debajo del corte, en vez de tocar cada `grid-template-columns`: una
#: lista de excepciones se desactualiza en cuanto alguien agregue un grid.
_A_UNA_COLUMNA = (
    ".fv3-ficha", ".fv3-veredicto", ".fv3-conversar", ".fv3-abrir",
    ".fv3-grid", ".fv3-razones", ".fv3-hechos", ".fv3-quien-es",
    ".fv3-contacto .fv3-fila", ".fv3-sf-grid", ".fv3-trimestres",
)


def _prefijar_clases(css: str) -> str:
    """`.foo` -> `.fv3-foo`, sin tocar las pseudo-clases ni los `.5rem`."""
    return re.sub(r"\.(?![0-9])([A-Za-z_][A-Za-z0-9_-]*)",
                  lambda m: "." + PREFIJO + m.group(1), css)


def _scopar(selector: str) -> str:
    """Cada selector, bajo `.fv3-raiz.fv3-raiz`."""
    partes = []
    for s in selector.split(","):
        s = s.strip()
        if not s:
            continue
        if s in (":root", "html", "body"):
            partes.append(RAIZ_FUERTE)
        elif s.startswith(":root"):
            partes.append(RAIZ_FUERTE + s[len(":root"):])
        elif s.startswith("@"):
            partes.append(s)
        else:
            partes.append("%s %s" % (RAIZ_FUERTE, s))
    return ", ".join(partes)


def _procesar_bloques(css: str) -> str:
    """Recorre el CSS y scopa cada selector. Respeta los bloques `@`."""
    salida, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            salida.append(css[i:])
            break
        selector = css[i:j].strip()
        # Un bloque `@media`/`@container` lleva dentro otras reglas.
        if selector.startswith("@"):
            profundidad, k = 1, j + 1
            while k < n and profundidad:
                if css[k] == "{":
                    profundidad += 1
                elif css[k] == "}":
                    profundidad -= 1
                k += 1
            dentro = css[j + 1:k - 1]
            salida.append("%s{\n%s\n}\n" % (_regla_arroba(selector),
                                            _procesar_bloques(dentro)))
            i = k
            continue
        k = css.find("}", j)
        if k < 0:
            k = n
        salida.append("%s{%s}\n" % (_scopar(selector), css[j + 1:k]))
        i = k + 1
    return "".join(salida)


def _regla_arroba(regla: str) -> str:
    """`@media (max-width: 860px)` -> `@container ficha (max-width: 860px)`.

    Es el cambio que hace que la ficha responda al PANEL. Lo demas --keyframes,
    `prefers-color-scheme`-- se deja como esta: el modo oscuro depende del
    sistema, no del ancho.
    """
    if regla.startswith("@media") and "width" in regla and "prefers" not in regla:
        condicion = regla[len("@media"):].strip()
        return "@container ficha %s" % condicion
    return regla


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    html = open(ORIGEN, encoding="utf-8").read()
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    if not m:
        print("no encontré el <style> de la maqueta")
        return 1
    css = m.group(1).strip()

    for prohibido in ("Osorio", "773", "captivatereg", "60638", "Captivate"):
        if prohibido in css:
            print("el CSS trae un dato real: %r" % prohibido)
            return 1

    css = _prefijar_clases(css)
    css = _procesar_bloques(css)

    cabecera = """/* La plantilla de la ficha v3, AISLADA.
 *
 * Generado por `scripts/extraer_css_maqueta.py` desde la maqueta que revisaron
 * Isabella y un BD. No se edita a mano: se cambia el script y se vuelve a
 * correr, o «igual a la maqueta» deja de significar nada.
 *
 * Tres cosas que NO están en la maqueta y sí aquí, y las tres porque la ficha
 * vive dentro de la app y no sola:
 *
 *   · todas las clases llevan `fv3-` y todo cuelga de `.fv3-raiz`. `.grid`,
 *     `.mod`, `.veredicto`, `.fila`, `.chip` y `.persona` existen también en
 *     el CSS de la app, y dos hojas peleando por el mismo nombre no dan un
 *     ganador: dan un resultado que depende del orden de los `<link>`;
 *
 *   · los breakpoints son `@container`, no `@media`. La ficha vive en un panel
 *     de ~714 px con la ventana a 1440, así que `@media (max-width: 860px)` no
 *     disparaba nunca y los grids de tres columnas se quedaban en 230 px cada
 *     una;
 *
 *   · por debajo de %d px DE PANEL todo va a una columna.
 */
.fv3-raiz{container-type:inline-size; container-name:ficha}

""" % CORTE_UNA_COLUMNA

    una_columna = """

/* ── Por debajo de %d px de PANEL, una sola columna ──────────────────────
 *
 * Se anulan los grids enteros en vez de ajustar cada `grid-template-columns`:
 * una lista de excepciones se desactualiza en cuanto alguien agregue un grid,
 * y el síntoma sería otra vez una palabra por línea.
 */
@container ficha (max-width: %dpx){
  %s{grid-template-columns:minmax(0,1fr) !important}
  .fv3-raiz .fv3-tabla-wrap{max-height:none}
  .fv3-raiz .fv3-hechos{gap:10px}
  .fv3-raiz .fv3-trimestres{grid-template-columns:repeat(5,minmax(0,1fr)) !important}
}
""" % (CORTE_UNA_COLUMNA, CORTE_UNA_COLUMNA,
       ",\n  ".join("%s %s" % (RAIZ_CLASE, s) for s in _A_UNA_COLUMNA))

    # ── EL PADDING QUE CORRIA EL CORTE 32 PX ──────────────────────────────
    #
    # Una `@container` se evalúa contra la CAJA DE CONTENIDO del contenedor, no
    # contra su borde. `.fv3-raiz` hereda del `body` de la maqueta un
    # `padding-inline:16px`, así que con el panel en 892 px el contenedor medía
    # 860 y `(max-width:860px)` --que es `<=`-- disparaba: la app mostraba una
    # columna justo donde la maqueta muestra dos. El corte estaba bien; lo que
    # estaba mal era contra qué se comparaba.
    #
    # El padding se mueve al `.fv3-wrap`, que no es el contenedor. Se ve igual
    # y el corte pasa a comparar contra el ancho del panel, que es el número
    # que uno tiene en la cabeza al elegirlo.
    sin_padding = """
/* El padding, en el envoltorio y no en el contenedor: ver el comentario de
   `scripts/extraer_css_maqueta.py`. Mismo aspecto, 32 px menos de trampa. */
%s{padding-inline:0}
%s .fv3-wrap{padding-inline:16px}
""" % (RAIZ_FUERTE, RAIZ_FUERTE)

    tablas = """
/* ── Por debajo de %d px, las tablas se apilan ─────────────────────────────
 *
 * `overflow-x:auto` sobre una tabla de 720 px dentro de un panel de 352 px no
 * es responsive: es una tabla escondida detrás de un gesto. En un teléfono
 * nadie la desliza, y lo que se ve es media palabra por columna.
 *
 * Apilada, cada fila es un bloque y cada celda lleva encima el nombre de su
 * columna (`data-col`, que pone la plantilla). Se pierde la comparación entre
 * filas --que a este ancho ya estaba perdida-- y se gana poder leerla.
 *
 * Se apilan las dos que llevan `data-col` en sus celdas: dolores y
 * operaciones. La marca la pone la plantilla, que es la que sabe si las celdas
 * traen el nombre de su columna; una tabla sin `data-col` apilada quedaría sin
 * encabezados y sin manera de saber qué es cada línea.
 *
 * El `thead` se apaga con `display:none` y no escondiéndolo con `clip`: la
 * primera versión lo dejaba en una caja de 1 px que seguía teniendo 463 px de
 * contenido, así que la medición de «texto cortado» lo encontraba a él. Un
 * encabezado invisible que desborda es un falso positivo que cuesta media hora.
 */
@container ficha (max-width: %dpx){
  .fv3-raiz .fv3-dolores-wrap, .fv3-raiz .fv3-tabla-wrap{overflow-x:visible;
    max-height:none}
  .fv3-raiz table.fv3-dolores, .fv3-raiz table.fv3-ops{min-width:0}
  .fv3-raiz table.fv3-dolores thead, .fv3-raiz table.fv3-ops thead{display:none}
  .fv3-raiz table.fv3-dolores tr, .fv3-raiz table.fv3-ops tr{display:block;
    padding:12px 0; border-top:1px solid var(--rule2)}
  .fv3-raiz table.fv3-dolores tr:first-child,
  .fv3-raiz table.fv3-ops tr:first-child{border-top:none}
  .fv3-raiz table.fv3-dolores td, .fv3-raiz table.fv3-ops td{display:block;
    border-top:none; padding:2px 0 8px; text-align:left}
  .fv3-raiz table.fv3-dolores td::before,
  .fv3-raiz table.fv3-ops td::before{content:attr(data-col); display:block;
    font-size:11px; letter-spacing:.06em; text-transform:uppercase;
    color:var(--ink3); font-weight:700; margin-bottom:2px}
}
""" % (CORTE_TABLAS_APILADAS, CORTE_TABLAS_APILADAS)

    # Los dos bloques de arriba están escritos con `.fv3-raiz` a secas para que
    # se lean; salen con la raíz doblada, igual que todo lo demás.
    anadidos = (sin_padding + una_columna + tablas).replace(
        RAIZ_CLASE + " ", RAIZ_FUERTE + " ")

    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    with open(DESTINO, "w", encoding="utf-8") as fh:
        fh.write(cabecera + css + anadidos)

    print("escrito: %s" % DESTINO)
    print("reglas: %d · caracteres: %d" % (css.count("{"), len(css)))
    print("clases sin prefijar: %d"
          % len(re.findall(r"(?<![\w-])\.(?!fv3-)[A-Za-z_][\w-]*", css)))
    print("@media con ancho que quedaron: %d"
          % len(re.findall(r"@media[^{]*width", css)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
