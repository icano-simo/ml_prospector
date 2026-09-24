"""Saca el CSS de la maqueta TAL CUAL, sin tocar una regla.

La maqueta trae datos reales y no va al repo; su CSS son solo estilos y si.
Copiarlo a mano seria la forma de que «igual a la maqueta» dejara de serlo.
"""
import os
import re

ORIGEN = (r"C:\Users\icano.CL-390BQ04\Downloads\pedido_claude_code_ficha_cowork"
          r"\5_maqueta_v3_NO_REPO.html")
DESTINO = r"C:\Users\icano.CL-390BQ04\ml_prospector\public\ficha_v3.css"

html = open(ORIGEN, encoding="utf-8").read()
m = re.search(r"<style>(.*?)</style>", html, re.S)
assert m, "no encontre el <style> de la maqueta"
css = m.group(1).strip()

# La guarda: el CSS no puede traer datos. Si trae un nombre o un telefono, algo
# se copio de mas.
for prohibido in ("Osorio", "773", "captivatereg", "60638", "Captivate"):
    assert prohibido not in css, "el CSS trae un dato real: %r" % prohibido

cabecera = """/* La plantilla de la ficha v3.
 *
 * EXTRAIDO TAL CUAL de la maqueta que revisaron Isabella y un BD. No se toca
 * una regla: como se ve lo decide esta hoja, y que dice lo decide el JSON.
 * Si alguien «mejora» algo aqui, la aceptacion visual --renderizar el golden y
 * compararlo con la maqueta-- deja de significar nada.
 *
 * La maqueta trae datos reales y NO va al repo. Esto son solo estilos.
 * Se regenera con scripts/extraer_css_maqueta.py.
 */
"""
os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
with open(DESTINO, "w", encoding="utf-8") as fh:
    fh.write(cabecera + css + "\n")

print("escrito: %s" % DESTINO)
print("reglas: %d · caracteres: %d" % (css.count("{"), len(css)))
