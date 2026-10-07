"""Renombra las claves `casa_*` a `everett_*` en los registros ya escritos.

«La casa» es jerga de adentro: dentro de un año nadie va a saber de que casa
se hablaba, y el dato dice algo concreto y verificable --que esas operaciones
las financio Everett Financial-- que el nombre deberia decir.

Se corre una vez. Cada sustitucion lleva su assert.
"""
import glob
import io
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(RAIZ, "data", "trabajo", "mm_por_realtor")

VIEJAS = {"casa_historico": "everett_historico",
          "casa_u_historico": "everett_u_historico",
          "casa_12m": "everett_12m",
          "casa_u_12m": "everett_u_12m",
          "casa_bandas_en": "everett_bandas_en"}

tocados = 0
for ruta in sorted(glob.glob(os.path.join(DIR, "*.json"))):
    with io.open(ruta, encoding="utf-8") as fh:
        f = json.load(fh)
    if not any(v in f for v in VIEJAS):
        continue
    for viejo, nuevo in VIEJAS.items():
        if viejo in f:
            f[nuevo] = f.pop(viejo)
    assert not any(v in f for v in VIEJAS), ruta
    with io.open(ruta, "w", encoding="utf-8") as fh:
        json.dump(f, fh, ensure_ascii=False, indent=1)
    tocados += 1

print("registros renombrados: %d" % tocados)
