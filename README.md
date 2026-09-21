# ML Prospector — HomeSí

Pipeline de **enriquecimiento por capas** que alimenta el motor de reglas de la
metodología **PACS-H**. Toma una lista cruda de agentes inmobiliarios y produce
las señales que ese motor necesita para diagnosticar dolores, asignar sub-nicho
y decidir nivel de calificación.

> **Ya no es un clasificador.** El modelo XGBoost que vivía acá se retiró el
> 2026-09-21. El label sobre el que se entrenó no es válido. No se reentrena ni
> se reintenta clasificación hasta que existan resultados reales de la
> prospección de 60 días, registrados con una definición escrita de qué cuenta
> como conversión. Los detalles están abajo, en
> [Qué se intentó y no funcionó](#qué-se-intentó-y-no-funcionó).

La metodología, el vocabulario, los qualifiers y las reglas de guardia están en
la skill `homesi-pacs-scoring`. Este repo **no** la reimplementa: produce sus
insumos.

---

## Las reglas de guardia

No son comentarios. Están codificadas como asserts y el pipeline falla si se
violan.

| Regla | Dónde se hace cumplir |
|---|---|
| Ninguna señal ausente es `False`. Toda señal ausente es `null` y lleva su máscara de disponibilidad. | `consolidar_mmi.py`, `instagram/esquema.py` |
| Ningún porcentaje se reporta sin su denominador. | `pacs/guardas.py` |
| El mix de programa no activa ni desactiva ningún qualifier con menos de 10 operaciones con tipo identificado, o menos del 50% del lado comprador identificado. Por debajo: `[insuficiente: N de M]`. | `pacs/guardas.py` |
| El wallet share solo se calcula sobre buyside, etiquetado por unidades o por volumen. | `pacs/guardas.py` |
| Toda cifra lleva fuente, fecha, y si es medida o estimada. | `identidad/procedencia.py` |
| Ninguna variable demográfica de tract clasifica a una persona: describe dónde opera, no quién es. | revisión + `pacs/guardas.py` |
| Ninguna inferencia de nicho, idioma o mercado desde apellido, etnia u origen. | revisión de código |
| Ningún dato personal de terceros (comentaristas, compradores) se almacena individualmente. | `instagram/comentarios.py` |
| Ningún dato de contacto se versiona en git. | pre-commit `scripts/verificacion/sin_pii_versionada.py` |

---

## Dónde viven los datos

**Fuera del repo.** Los insumos traen nombre, email y teléfono de personas
reales, y este repo estuvo público en GitHub con ellos adentro hasta el
2026-09-21.

```
../ml_prospector_datos_privados/
├── insumos/          MMI Data.xlsx, realtors.csv — listas crudas
├── crm/              Calls.xlsx, Historico Realtors.xlsx — disposiciones
└── modelo_retirado/  los artefactos del XGBoost, archivados
```

El código los pide por `realtor_scraper/datos_privados.py`. La ruta base se
puede mover con la variable de entorno `ML_PROSPECTOR_DATOS`.

Antes de tu primer commit:

```bash
python scripts/verificacion/instalar_hooks.py
```

Eso instala el pre-commit que rechaza cualquier archivo con columnas de
contacto o de CRM en el índice. El `.gitignore` solo no alcanza: un `git add -f`
lo pasa por encima sin ruido.

---

## Las capas

```
                     state_licenses/          ← la llave de identidad
                     TREC · DBPR · +CA AZ NV IL
                              │
                              ▼
  MMI Data.xlsx ──────► identidad/  ──────► registro unificado
  Model Match           cascada: licencia → teléfono E.164 → email → nombre+condado
  Instagram             match_confidence por cruce · nunca sobrescribe, versiona
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
   instagram/           latino_re_engine/      modelmatch/
   captions con fecha   Census ACS + HMDA      benchmarks por condado
   comentarios          FFIEC LMI              buyside/listside
   estado del perfil    features relativas     wallet share
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
                     sábana de señales
                     con máscara de disponibilidad
                              │
                              ▼
                     motor de reglas PACS-H
                     (skill homesi-pacs-scoring)
                              │
                              ▼
                     dashboard.py — diagnóstico, no score
```

### Qué alimenta qué

| Capa | Categorías de señal PACS | Estado |
|---|---|---|
| `state_licenses/` | S7, llave de identidad | TX y FL funcionando; CA, AZ, NV, IL pendientes |
| `instagram/` | S1, S3, S4, S6, S7, S8, S9, S10 | reescrita 2026-09-21 |
| `latino_re_engine/` | S7 + capa geográfica E1-E8 | funcionando |
| `modelmatch/` | S2, S6, J-Q01 | parser listo, captura manual pendiente |
| `google_places/` | S8 | cliente listo, necesita API key |
| `realtor_com/` | S3, S8 parcial | por evaluar |

---

## Qué se intentó y no funcionó

Esta sección existe para que nadie lo repita. Las cifras están **medidas**
contra `historico_scored.csv` (5.620 filas), el dataset del modelo retirado,
archivado en `../ml_prospector_datos_privados/modelo_retirado/`.

### 1 · Zillow · bloqueado, cero salida

Módulo completo: `scraper.py`, `browser_scraper.py`, `parser.py`,
`profile_scraper.py`. Contexto persistente de Chromium, patchright para parchear
el fingerprinting de Cloudflare, calentamiento de sesión en la home, navegación
a una página aleatoria cada 2 perfiles para romper el patrón de `/profile/`
consecutivos, pausa profunda de 75-100 segundos cada 8 perfiles.

**Resultado: cero columnas de Zillow en toda la salida.** El dataset final de
5.620 filas no tiene una sola columna `zillow_*`. Ni rating, ni reviews, ni
`speaks_spanish`, ni email, ni teléfono.

Dos razones, y las dos son definitivas:

- El anti-bot de Zillow es agresivo y la escalada de evasión no terminó en
  datos, terminó en más código de evasión.
- Sus términos de uso prohíben el scraping. Aun si funcionara, no se usa.

**No se reintenta.** El reemplazo de la categoría S8 está en
[Bloque 2](docs/bloque-2-s8.md): comentarios de Instagram primero, Google Places
API después.

### 2 · El modelo XGBoost · el label no es válido

21 features, AUC en validación cruzada de 5 pliegues 0,637 ± 0,017 contra 0,822
en el set de entrenamiento.

Con una tasa base de **57,1%** (3.210 de 5.620), un AUC de 0,637 está a un paso
de no separar nada. Pero el problema de fondo no es la métrica.

**El label es incoherente.** Sale del campo `converted` del CRM. Y:

| | label=1 | de | tasa |
|---|---|---|---|
| `was_called=0` | 653 | 1.339 | **48,8%** |
| `was_called=1` | 2.557 | 4.281 | 59,7% |

**653 realtors están marcados como convertidos sin que nadie los haya
llamado.** Lo que sea que mida `converted`, no mide el resultado de nuestra
prospección. Un modelo entrenado sobre eso aprende la forma del archivo, no la
propensión de una persona.

Y hay un segundo problema, más sutil, en el que el brief original erraba el
dedo. La cifra:

| Feature | Importancia en el modelo | Correlación con el label |
|---|---|---|
| `company_is_latino_brokerage` | 0,186 | — |
| **`has_instagram`** | **0,074 (2º)** | **+0,065** |
| `company_has_spanish_name` | 0,062 | — |
| `content_lang_score` | 0,057 | +0,084 |
| `units_sold` | 0,046 | +0,007 |
| **`ig_is_private`** | **0,000** | constante |

`has_instagram` no es una fuga en el sentido clásico: correlaciona +0,065 con el
label, que es casi nada. El problema es que **el modelo la puso segunda en
importancia igual**. `has_instagram` no dice nada del realtor: dice que nuestro
scraper funcionó en esa fila. Y que funcione depende del lote, del estado y de
cuándo se cargó. El modelo estaba leyendo la historia operativa del scraper y
llamándola propensión.

`ig_is_private` con importancia exactamente **0,000** es la prueba más limpia
del problema de los nulos: la columna era constante en las 5.620 filas (ver
abajo), así que no aportó nada y nadie se dio cuenta porque el modelo no se
queja de una columna muerta.

Las features de llamada (`was_called` r=+0,094 · `call_duration_min` r=+0,164 ·
`total_calls_clip` r=+0,186 · `answer_rate` r=+0,101) no entraron como features
—no están en `features.json`— pero se usaron como **pesos de muestra**. Pesar el
ajuste con cantidades medidas después del desenlace inclina el modelo hacia los
registros con los que ya se había hablado.

`state_conversion_rate` (r=+0,203, la correlación más alta de todas las
columnas no-llamada) es un target encoding del propio set de entrenamiento:
cada fila lleva el promedio del grupo al que pertenece, incluido su propio
label. **No entró al modelo** —está calculada y reportada pero no en
`features.json`— y así tiene que seguir.

### 3 · El análisis de contenido por alt-text · medía otro idioma

`_extract_post_alt_texts` leía `article img[alt]`. El atributo `alt` de
Instagram es **texto generado automáticamente por Meta para accesibilidad**,
casi siempre en inglés sin importar el idioma del caption. Todo el análisis de
idioma, comunidad y colaboración estaba construido sobre eso.

Lo que produjo, sobre 5.620 filas:

| Señal | Resultado | Por qué es imposible o inútil |
|---|---|---|
| `ig_is_private` | **0 positivos, 5.620 negativos, 0 nulos** | Ninguna cuenta privada en 5.620 perfiles inmobiliarios. La señal no se medía: se rellenaba con `False`. |
| `ig_content_language = spanish` | 185 de 5.620 = **3,29%** | En un lote seleccionado por mercado latino. El alt-text estaba en inglés. |
| `ig_collaborates` | **33** positivos | Las `@menciones` viven en el caption, no en el alt. |
| `ig_nahrep` | **29** positivos | Misma causa. |
| `ig_posts_spanish` | 622 positivos | Derivado del mismo texto equivocado. |

Y el daño estructural: **1.075 perfiles tenían handle y ninguna bio**, y 4.557
tenían handle y ninguna señal de contenido positiva. Todos entraron al modelo
con `False` en cada señal, es decir como afirmaciones negativas que nadie midió.

El handle, además, no se verificaba. **5.516 de 5.620 handles "encontrados"
(98,1%)** vía una sola expresión regular sobre el HTML completo de los
resultados de DuckDuckGo, que devuelve el primer `instagram.com/...` que
aparezca en la página, incluidos anuncios y resultados ajenos. Un 98% de acierto
en búsqueda de handles por nombre no es creíble.

El reemplazo está en [Bloque 1](docs/bloque-1-instagram.md): captions reales con
fecha, estado explícito del perfil, y verificación de handle con
`handle_confidence`.

### 4 · El proxy de seguidores como medida de producción

`ig_followers` correlaciona con `units_sold`:

| Medida | r | n |
|---|---|---|
| Pearson, crudo | **+0,0014** | 3.234 |
| Pearson, `log1p` | +0,078 | 3.234 |
| Spearman | +0,075 | 3.234 |

Es decir: **nada**. R1 ("propensión a responder · factor social") y R3
("audiencia joven digital") se apoyaban los dos en seguidores. El engagement
real —(likes + comentarios) ÷ seguidores— se calcula en
[Bloque 1](docs/bloque-1-instagram.md) y es el que R1 debería usar.

---

## Documentos por bloque

| Bloque | Documento |
|---|---|
| 0 · Limpieza | [docs/bloque-0-limpieza.md](docs/bloque-0-limpieza.md) |
| 1 · Instagram real | [docs/bloque-1-instagram.md](docs/bloque-1-instagram.md) |
| 2 · Reemplazo de S8 | [docs/bloque-2-s8.md](docs/bloque-2-s8.md) |
| 3 · Identidad | [docs/bloque-3-identidad.md](docs/bloque-3-identidad.md) |
| 4 · Census y features relativas | [docs/bloque-4-census.md](docs/bloque-4-census.md) |
| 5 · Model Match | [docs/bloque-5-modelmatch.md](docs/bloque-5-modelmatch.md) |

---

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
python scripts/verificacion/instalar_hooks.py
```

## Uso

```bash
# Capa geográfica: Census ACS + HMDA + FFIEC por tract, con features relativas
python latino_re_engine/latino_re_engine/main.py

# Capa de identidad: licencias estatales -> registro unificado
python realtor_scraper/main.py --states TX FL

# Capa de Instagram: captions, comentarios, estado del perfil
python realtor_scraper/mmi_enricher.py

# Consolidar en la sábana de entrada del motor PACS-H
python realtor_scraper/consolidar_mmi.py

# Dashboard
streamlit run dashboard.py
```

## La frase que va en toda entrega

> Este sistema califica hipótesis, no hechos. Lo que varía entre un registro y
> otro no es si se puede producir salida — siempre se puede — sino cuánta
> confianza se declara. Una inferencia débil presentada con la autoridad de un
> hecho verificado es el único error que este sistema no puede permitirse,
> porque destruye exactamente el activo que existe para construir.
