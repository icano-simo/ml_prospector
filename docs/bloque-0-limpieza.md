# Bloque 0 · Limpieza

**Fecha:** 2026-09-21 · **Estado:** cerrado

---

## Qué se hizo

### El repo estaba público con datos de contacto de ~33.000 personas

Esto no estaba en el alcance del bloque como se pidió. Se pidió retirar dos
archivos; el inventario encontró cinco, y el repo era **público** en GitHub.

| Archivo | Filas | Qué traía |
|---|---|---|
| `latino_re_engine/Calls.xlsx` | 5.372 | nombre + disposiciones de CRM (`total_calls`, `calls_answered`, `avg_duration_seconds`, `converted`) |
| `latino_re_engine/Historico Realtors.xlsx` | 14.270 | nombre, email, teléfono, estado, `Lead Status`, volumen |
| `latino_re_engine/MMI Data.xlsx` | 4.388 | nombre, email, teléfono, estado, volumen |
| `data/realtors.csv` | 4.249 | nombre, email, teléfono, handle IG, bio, score |
| `realtor_scraper/output/model/historico_scored.csv` | 5.620 | nombre, IG, `label`, `was_called`, `call_duration_min`, `answer_rate` |

Los dos últimos no estaban en la lista original. Son la misma clase de dato y
estaban igual de expuestos. Se consultó y se purgaron los cinco.

### Secuencia ejecutada

1. **Repo a privado primero.** `gh repo edit --visibility private`. Es lo único
   que cierra la exposición de inmediato; la reescritura de historial sola no
   basta. Verificado: `visibility: PRIVATE`, `forkCount: 0`.
2. **Respaldo antes de reescribir.** Bundle de todas las refs (10,6 MB) y clon
   `--mirror`, los dos en
   `../ml_prospector_backup_prepurga_20260921/`. `HEAD` previo:
   `ee462bb79b94ab565f983f263ca5d4e11331f7a5`.
3. **Los datos salieron del árbol, no se destruyeron.** Once archivos movidos a
   `../ml_prospector_datos_privados/` (`insumos/`, `crm/`,
   `modelo_retirado/`). Nada se borró: `MMI Data.xlsx` y `realtors.csv` son
   insumos del pipeline y siguen en disco.
4. **Purga del historial** con `git-filter-repo --invert-paths` sobre los cinco
   archivos con PII más `latino_re_engine/data/raw/*` (26 MB de volcados crudos
   del API de Census, regenerables).
5. **Verificación**, no confianza en el código de salida. El script está en
   `scratchpad/verificar_purga.py`:
   - cero commits tocando las rutas purgadas;
   - cero objetos con esos nombres en `git rev-list --objects --all`;
   - los cinco blobs SHA originales dan `cat-file: not found`.
   El repo pasó de ~30 MB a **759 KiB** empaquetados.
6. **Force-push** a `origin/master`: `ee462bb...d1e66ec (forced update)`.

### La guarda redundante

El `.gitignore` se amplió, pero **no es la guarda**: un `git add -f` lo ignora
sin ruido. La guarda es `scripts/verificacion/sin_pii_versionada.py`, instalada
como pre-commit por `scripts/verificacion/instalar_hooks.py`.

Mira **el índice de git**, no el disco. Reconoce:

- nombres de archivo que ya filtraron una vez;
- encabezados de columna de contacto (`email`, `phone`, `first_name`,
  `address`…) en CSV y en XLSX, leyendo el XML del zip sin depender de openpyxl;
- encabezados de CRM (`converted`, `was_called`, `call_duration*`,
  `lead_status`, `disposition`…);
- cualquier hoja de cálculo de más de 2 MB en el índice.

Falla el commit con un mensaje que dice qué encontró y por qué. Es redundante a
propósito.

### Código retirado

| Qué | Por qué |
|---|---|
| `train_model.py`, `build_training_dataset.py`, `analyze_model.py` | dependen del label inválido |
| `output/model/*` (pkl, features.json, medians.json, state_rates.json, feature_importances.csv, model_report.png) | artefactos del modelo retirado, archivados |
| `historico_enricher.py` | construía el dataset de entrenamiento |
| `zillow/` completo (5 archivos) | cero columnas en toda la salida; ToS lo prohíbe |
| `debug_california.py` | leía `state_rates.json` |
| `debug_ddg.py`, `debug_ig.py`, `debug_ig2.py` | depuraban la ruta de alt-text que se reescribió |
| `show_ig.py` | imprimía columnas de Zillow |

Se conservó `debug_dbpr.py`: `state_licenses/dbpr.py` sigue vivo y ese script
sigue sirviendo para ver qué publica hoy el portal de Florida.

### Código intervenido

- **`score_mmi.py` → `consolidar_mmi.py`.** Se le quitó todo el scoring
  XGBoost. Lo que quedó (consolidación de los enriched, Census por estado
  ponderado por población, léxico de brokerage) sigue siendo útil como insumo
  del motor PACS. **Se renombró** porque un archivo llamado `score_mmi.py` que
  no puntúa es exactamente el artefacto engañoso que este bloque existe para
  eliminar. Además, `normalizar_booleanos()` pasa las señales a booleano
  nullable —ausente queda `<NA>`, no `False`— y un assert falla ruidosamente si
  alguna fila sin handle quedó con una señal en `False`.
- **`mmi_enricher.py`.** Fuera Zillow. La ruta del insumo ahora se resuelve por
  `datos_privados.py`, que falla con un mensaje útil en vez de dejar que pandas
  reviente tres pasos después.
- **`main.py`.** Fuera el paso 2 (Zillow). Queda la capa de licencias
  estatales, que es la llave de identidad. Las columnas de contacto salieron de
  su salida: ese archivo ya no produce teléfonos ni emails.
- **`navegador.py`** (nuevo). `make_browser_context` vivía dentro de
  `zillow/profile_scraper.py` y era lo único de ese módulo que valía la pena.
  Se extrajo sin nada específico de Zillow.
- **`datos_privados.py`** (nuevo). Resuelve dónde viven los insumos con PII.
  Una sola ruta en un solo lugar.

### El README

Tiene la sección [Qué se intentó y no funcionó](../README.md#qué-se-intentó-y-no-funcionó)
con cuatro entradas: Zillow, el modelo XGBoost, el análisis por alt-text y el
proxy de seguidores. **Todas las cifras se midieron** contra
`historico_scored.csv`, no se citaron de memoria.

---

## Qué se encontró

### El brief erraba el dedo en `has_instagram`, y la corrección importa

El brief decía «fuga por `has_instagram`». Medido: `has_instagram` correlaciona
**+0,065** con el label. Eso no es una fuga; es casi nada.

El problema real es peor y más interesante: **el modelo la puso segunda en
importancia (0,074) de todas formas.** `has_instagram` no dice nada del
realtor — dice que nuestro scraper funcionó en esa fila, y eso depende del lote,
del estado y de cuándo se cargó. El modelo estaba leyendo la historia operativa
del scraper y llamándola propensión.

Si se hubiera "arreglado la fuga" quitando la correlación, no habría cambiado
nada, porque no había correlación que quitar.

### El label es incoherente, y se puede demostrar en una tabla

| | label=1 | de | tasa |
|---|---|---|---|
| `was_called=0` | 653 | 1.339 | **48,8%** |
| `was_called=1` | 2.557 | 4.281 | 59,7% |

653 realtors marcados como convertidos sin haber sido llamados nunca. Ése es el
argumento decisivo para retirar el modelo, y no hace falta hablar de AUC.

### `ig_is_private` con importancia exactamente 0,000

La columna era constante `False` en las 5.620 filas. El modelo no aportó nada
con ella y **nadie se dio cuenta**, porque un clasificador no se queja de una
columna muerta. Es la mejor evidencia de por qué la regla «ausente es `null`,
nunca `False`» tiene que ser un assert y no una convención.

### GitHub sigue sirviendo los blobs huérfanos

Después del force-push, verificado con la API:

```
GET repos/icano-simo/ml_prospector/commits/ee462bb...  → 200, sha devuelto
GET repos/icano-simo/ml_prospector/git/blobs/99119c07...→ 200, size 237042
```

Es decir: **el commit viejo y el blob de `Calls.xlsx` siguen alcanzables por
SHA.** La reescritura del historial no los borra del servidor. Lo que cerró la
exposición fue pasar el repo a privado.

---

## Qué quedó sin resolver

1. **Los blobs huérfanos siguen en GitHub.** Hoy no son públicos porque el repo
   es privado, pero si alguien lo vuelve a poner público, vuelven con él.
   Cerrarlo del todo requiere un ticket a GitHub Support pidiendo el
   garbage-collect de objetos inalcanzables, citando el repo y que se hizo un
   force-push tras una filtración. El texto está en
   [`docs/ticket-github-gc.md`](ticket-github-gc.md). **No se envió**: eso es
   una comunicación externa y no me corresponde iniciarla.

2. **Nadie sabe si esos datos se descargaron mientras el repo estuvo público.**
   El repo se creó con la PII adentro (`999fb98 Initial commit` y
   `c2562be Add Calls.xlsx`) y el último push fue el 2026-06-20. GitHub no
   expone logs de clonado para repos sin GitHub Advanced Security, así que
   **esta pregunta no se puede responder con los datos disponibles.** Si hace
   falta una respuesta, hay que preguntarle a GitHub Support en el mismo ticket.

3. **Si corresponde notificar** a los ~33.000 titulares de esos datos es una
   decisión legal, no técnica. La menciono porque nadie más la va a plantear:
   eran nombres, emails y teléfonos de agentes inmobiliarios en un repo público
   junto con nuestras disposiciones de CRM sobre ellos.

4. **No había venv en la máquina.** El README anterior decía
   `latino_re_engine\.venv\Scripts\activate` y ese directorio no existe. Ni
   `numpy` ni `pandas` están en el Python global, así que **nada del pipeline se
   pudo ejecutar** en esta sesión. Toda la verificación de cifras se hizo con la
   librería estándar sobre el CSV archivado. El código nuevo compila
   (`py_compile`) pero **no corrió**.

5. **`dashboard.py` todavía carga el modelo XGBoost** en su ruta de scoring
   en-navegador (líneas ~176-185) y va a fallar, porque los artefactos ya no
   están. Se adapta en un paso posterior, cuando el esquema de salida del motor
   PACS esté fijo; adaptarlo antes sería adivinar las columnas.
