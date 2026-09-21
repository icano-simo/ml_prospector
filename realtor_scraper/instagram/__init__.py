"""Capa de Instagram: captions reales, comentarios agregados y estado del perfil.

Reescrita el 2026-09-21. La version anterior analizaba `article img[alt]` -- el
texto de accesibilidad que Meta genera automaticamente, casi siempre en ingles
sin importar el idioma del caption -- y devolvia `{}` ante cualquier fallo, que
aguas abajo se volvia `False` en catorce columnas.

Modulos, en orden de dependencia:

    estado.py        los cinco estados del perfil. Nunca False donde va null.
    verificacion.py  el handle es de esta persona? handle_confidence.
    idioma.py        idioma por pieza, con el umbral de evidencia de la matriz.
    posts.py         caption crudo + fecha, programas, cadencia, engagement.
    comentarios.py   perfil de audiencia agregado y anonimo. Reemplaza S8.
    extraccion.py    lo unico que toca el DOM.
    finder.py        el orquestador.

Los cinco primeros son puro Python y tienen 51 pruebas en
tests/test_instagram.py. Si algo falla en una corrida, que las pruebas pasen
dice que el problema es el selector y no la logica.
"""
