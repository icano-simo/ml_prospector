"""Capa PACS-H: las reglas de guardia y el esquema de procedencia.

Este paquete NO reimplementa el motor de reglas PACS-H. El motor vive en la
skill `homesi-pacs-scoring` (`scripts/pacs_engine.py`). Aca estan las guardas
que el pipeline de enriquecimiento tiene que cumplir para que su salida sea un
insumo valido de ese motor.
"""

from pacs.guardas import (  # noqa: F401
    Cifra,
    MixDePrograma,
    Senal,
    ViolacionDeGuarda,
    WalletShare,
    acto_de_habla,
    intensidad_con_techo,
    mascara_de_disponibilidad,
    porcentaje,
    verificar_entradas_de_inferencia,
    verificar_uso_de_tract,
)
