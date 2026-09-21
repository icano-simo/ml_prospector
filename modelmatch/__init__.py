"""Capa Model Match: captura, parseo y calibracion contra HMDA.

La prueba de Model Match caduca. El orden de trabajo de este modulo esta
ordenado por lo que NO caduca:

1. verificar el export nativo (si da CSV completo, lo manual sobra);
2. capturar los benchmarks de condado, que son un activo permanente;
3. calibrar contra HMDA, para tener un reemplazo gratuito y nacional;
4. la muestra de perfiles individuales, que si caduca;
5. pedir la API antes de que expire.

El protocolo completo esta en docs/bloque-5-modelmatch.md.
"""
