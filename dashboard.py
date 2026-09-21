"""
HomeSi · ML Prospector — Dashboard de diagnostico PACS-H

Que cambio el 2026-09-21
------------------------
Este dashboard mostraba un `propensity_score` de 0 a 100 y ordenaba la cola de
llamadas por ese numero. El modelo que lo producia se retiro: el label sobre el
que se entreno no es valido (653 realtors marcados como convertidos sin haber
sido llamados nunca). Ver la seccion "Que se intento y no funciono" del README.

Ahora muestra el **diagnostico PACS-H**: nivel de calificacion, dolor primario
con su intensidad, grado de evidencia y confianza declarada. Y cuando ese
diagnostico no existe todavia, lo dice en vez de mostrar un numero.

La regla que ordena la presentacion: **es mejor una celda que dice "no se pudo"
que una celda con un numero que nadie puede defender.**
"""
import re as _re
import io
import json
from pathlib import Path
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

ROOT        = Path(__file__).parent
DATA_DIR    = ROOT / "data"
OUTPUT_DIR  = ROOT / "realtor_scraper" / "output"
UPLOADS_DIR = ROOT / "realtor_scraper" / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

# ── Vocabulario PACS ──────────────────────────────────────────────────────────
#
# El orden de los niveles es el de la referencia 07 de la skill
# homesi-pacs-scoring, y es el que reemplaza al orden por score.

NIVELES = ["MQL", "PRE-MQL", "BLOQUEADO POR COBERTURA", "DESCARTADO"]

ORDEN_DE_NIVEL = {n: i for i, n in enumerate(NIVELES)}

#: Columnas que produce el motor de reglas PACS-H. Si no estan, el dashboard
#: no inventa: muestra el reporte de enriquecimiento.
COLS_PACS = [
    "nivel_de_calificacion", "motivo_si_descartado", "confianza_global",
    "sub_nicho_primario", "arquetipo_realtor",
    "pain_primario", "intensidad_primaria", "grado_evidencia", "acto_de_habla",
    "evidencia_ancla", "evidencia_regla", "gancho",
    "pregunta_de_cierre_de_brecha", "canal_recomendado",
]

#: Señales de contenido que NUNCA se rellenan con 0. Una señal ausente es
#: <NA>, y la version anterior de este archivo hacia .fillna(0).astype(int)
#: sobre estas mismas columnas: convertia 1.075 perfiles sin datos en 1.075
#: perfiles con señales negativas.
SENALES_CONTENIDO = [
    "ig_spanish_signals", "ig_posts_spanish", "ig_mentions_latino",
    "ig_nahrep", "ig_collaborates", "ig_realtor_signals", "ig_is_private",
]

#: Estas si son de la empresa y se derivan del nombre, que siempre esta.
SENALES_DE_EMPRESA = ["company_is_latino_brokerage", "company_has_spanish_name"]

SPANISH_NAME_WORDS = {
    "casa","hogar","vive","movil","buena","bueno",
    "casas","hogares","vida","sol","estrella","luna","tierra",
    "familia","unidos","latina","latino",
}
LATINO_BROKERAGES = {
    "la rosa","casa buena","movil realty","vive realty","agent trust",
    "naim real estate","home prime","casa","hogar","latin","hispano",
    "hispanic","latino","habla","bilingual","multicultural",
}

def _keyword_match(text: str, keywords: set) -> bool:
    n = text.lower()
    for w in keywords:
        if " " in w:
            if w in n:
                return True
        else:
            if _re.search(r"\b" + _re.escape(w) + r"\b", n):
                return True
    return False

STATE_ABBREV = {
    "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California",
    "CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia",
    "HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa",
    "KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland",
    "MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi",
    "MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire",
    "NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina",
    "ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania",
    "RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee",
    "TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington",
    "WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia",
}
NAME_TO_ABBR = {v: k for k, v in STATE_ABBREV.items()}

# ── Session state ──────────────────────────────────────────────────────────────
if "selected_state" not in st.session_state:
    st.session_state.selected_state = None
if "n_show" not in st.session_state:
    st.session_state.n_show = 25
if "uploaded_batches" not in st.session_state:
    st.session_state.uploaded_batches = []   # list of DataFrames scored in-browser

# ── Data loading ───────────────────────────────────────────────────────────────

_MAPA_BOOL = {
    True: True, False: False, "True": True, "False": False,
    "true": True, "false": False, 1: True, 0: False, "1": True, "0": False,
}


def _normalize_realtors(df: pd.DataFrame) -> pd.DataFrame:
    if "ig_followers" in df.columns:
        df["ig_followers"] = pd.to_numeric(df["ig_followers"], errors="coerce")
    else:
        df["ig_followers"] = np.nan

    # Señales de contenido: booleano nullable. Ausente queda <NA>, NO False.
    for col in SENALES_CONTENIDO:
        if col in df.columns:
            df[col] = df[col].map(_MAPA_BOOL).astype("boolean")
        else:
            df[col] = pd.Series(pd.NA, index=df.index, dtype="boolean")

    # Señales de empresa: se derivan del nombre, que siempre esta.
    for col in SENALES_DE_EMPRESA:
        if col in df.columns:
            df[col] = df[col].map(_MAPA_BOOL).fillna(False).astype("boolean")
        else:
            df[col] = pd.Series(False, index=df.index, dtype="boolean")

    # Columnas del diagnostico PACS. Si el motor no corrio, quedan vacias y el
    # dashboard lo dice: no se sustituye por un numero.
    for col in COLS_PACS:
        if col not in df.columns:
            df[col] = pd.NA
    df["intensidad_primaria"] = pd.to_numeric(
        df["intensidad_primaria"], errors="coerce"
    )
    df["confianza_global"] = pd.to_numeric(df["confianza_global"], errors="coerce")
    df["nivel_de_calificacion"] = (
        df["nivel_de_calificacion"].astype("string").str.strip().str.upper()
    )
    df["_orden_nivel"] = df["nivel_de_calificacion"].map(ORDEN_DE_NIVEL)

    # Confianza del handle: solo alta y media alimentan señales del motor.
    if "ig_handle_confidence" not in df.columns:
        df["ig_handle_confidence"] = pd.NA
    df["ig_handle_confidence"] = (
        df["ig_handle_confidence"].astype("string").str.strip().str.lower()
    )
    df["ig_senales_usables"] = df["ig_handle_confidence"].isin(["alta", "media"])

    def _ig_url(handle):
        if pd.isna(handle) or str(handle).strip() in ("", "nan"):
            return None
        return f"https://www.instagram.com/{str(handle).strip().lstrip('@').rstrip('/')}/"

    df["ig_link"] = df["ig_handle"].apply(_ig_url) if "ig_handle" in df.columns else None
    if "batch_name" not in df.columns:
        df["batch_name"] = "carga_original"
    df["batch_name"] = df["batch_name"].fillna("carga_original")
    return df


@st.cache_data
def load_realtors() -> pd.DataFrame:
    """Carga la sabana mas reciente.

    Prioridad: la salida del motor PACS, despues la consolidada, y al final los
    enriched crudos. `data/realtors.csv` ya NO se busca: tenia nombre, email y
    telefono de 4.249 personas y salio del repo el 2026-09-21.
    """
    candidatos = [
        *sorted(OUTPUT_DIR.glob("pacs_diagnostico_*.csv"), reverse=True),
        *sorted(OUTPUT_DIR.glob("mmi_consolidado_*.csv"), reverse=True),
        *sorted(OUTPUT_DIR.glob("mmi_enriched_*.csv"), reverse=True),
    ]
    path = next((p for p in candidatos if p.exists()), None)
    if path is None:
        st.error(
            "No encontre ninguna sabana en `realtor_scraper/output/`.\n\n"
            "El orden del pipeline es:\n"
            "1. `python realtor_scraper/mmi_enricher.py` — Instagram\n"
            "2. `python realtor_scraper/consolidar_mmi.py` — consolidar + Census\n"
            "3. el motor de reglas PACS-H sobre esa sabana\n\n"
            "`data/realtors.csv` ya no existe a proposito: traia nombre, email "
            "y telefono de 4.249 personas en un repo que estuvo publico. Los "
            "insumos viven fuera del repo, en `../ml_prospector_datos_privados/`."
        )
        st.stop()
    df = _normalize_realtors(pd.read_csv(path, low_memory=False))
    df.attrs["origen"] = path.name
    return df


@st.cache_data
def load_census() -> pd.DataFrame:
    for p in [DATA_DIR / "state_census_summary.csv",
              OUTPUT_DIR / "state_census_summary.csv"]:
        if p.exists():
            df = pd.read_csv(p)
            for col in ["total_population", "hispanic_pop", "hispanic_pct"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            return df
    return pd.DataFrame(columns=["state","state_abbr","total_population","hispanic_pop","hispanic_pct"])


def preparar_excel_subido(file_bytes: bytes, batch_label: str) -> pd.DataFrame:
    """Normaliza un Excel subido. **NO lo puntua.**

    Hasta el 2026-09-21 esta funcion cargaba el modelo XGBoost y devolvia un
    propensity_score calculado con todas las señales de Instagram en cero, con
    un aviso de "score parcial". Eso era peor que no dar nada: un numero
    calculado sobre catorce columnas vacias, presentado como score.

    Lo que queda es lo que se puede afirmar sin scraping ni modelo: los datos
    del archivo, el estado normalizado y los dos flags de brokerage, que salen
    del nombre de la empresa. Todo lo demas queda en <NA> y el dashboard lo
    declara como pendiente de enriquecimiento.
    """
    df = pd.read_excel(io.BytesIO(file_bytes), dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={
        "First Name":           "first_name",
        "Last Name":            "last_name",
        "Company / Account":    "company",
        "Email":                "email_mmi",
        "Phone":                "phone_mmi",
        "State":                "state",
        "BS Sold # Units":      "units_sold",
    })
    if "first_name" in df.columns and "last_name" in df.columns:
        df["full_name"] = (df["first_name"].str.strip() + " " + df["last_name"].str.strip()).str.strip()
    if "full_name" not in df.columns:
        return None

    # Normalize state to full name
    df["state_clean"] = df["state"].str.strip()
    df.loc[df["state_clean"].str.len() == 2, "state_clean"] = (
        df.loc[df["state_clean"].str.len() == 2, "state_clean"]
        .str.upper().map(STATE_ABBREV)
    )
    state_abbr_map = {v: k for k, v in STATE_ABBREV.items()}
    df["state_abbr"] = df["state_clean"].map(state_abbr_map)

    # Lo unico derivable del archivo: los flags de brokerage, que salen del
    # nombre de la empresa y no necesitan ni scraping ni modelo.
    df["company_has_spanish_name"]    = df["company"].fillna("").apply(lambda n: _keyword_match(n, SPANISH_NAME_WORDS))
    df["company_is_latino_brokerage"] = df["company"].fillna("").apply(lambda n: _keyword_match(n, LATINO_BROKERAGES))

    # Las señales de Instagram NO se rellenan con cero: quedan ausentes.
    for col in SENALES_CONTENIDO:
        df[col] = pd.NA
    df["ig_handle"] = pd.NA
    df["ig_handle_confidence"] = pd.NA

    df["batch_name"] = batch_label
    df["ig_link"]    = None
    df["state"]      = df["state_clean"]
    df["nivel_de_calificacion"] = "PRE-MQL"
    df["motivo_si_descartado"] = (
        "sin enriquecer: solo estan los datos del archivo. No paso por "
        "Instagram ni por el motor de reglas PACS-H."
    )
    return _normalize_realtors(df)


def _es_positiva(row, col: str) -> bool:
    """True solo si la señal se midio Y es verdadera. Ausente NO es positiva.

    `if row.get(col, 0):` sobre un booleano nullable levanta
    "boolean value of NA is ambiguous", y si se le pone .fillna(False) antes se
    vuelve el bug original: tratar lo ausente como negativo. Esta funcion es la
    unica forma de leer una señal de contenido en este archivo.
    """
    valor = row.get(col)
    return valor is True or valor == 1


def _se_midio(row, col: str) -> bool:
    valor = row.get(col)
    return valor is not None and pd.notna(valor)


def build_signal_description(row) -> str:
    parts = []
    handle = row.get("ig_handle", "")
    has_ig = pd.notna(handle) and str(handle).strip() not in ("", "nan")
    lang   = str(row.get("ig_content_language", "") or "").lower()

    # El estado del perfil manda sobre todo lo demas: si no se leyo, no se
    # describe lo que no se vio.
    estado_perfil = str(row.get("ig_estado_perfil", "") or "").strip()
    confianza_handle = str(row.get("ig_handle_confidence", "") or "").strip().lower()

    if confianza_handle == "baja":
        return (
            "Handle de Instagram SIN VERIFICAR (confianza baja): sus señales de "
            "contenido no se usan. %s"
            % str(row.get("ig_razon_confianza", "") or "").strip()
        ).strip()

    if estado_perfil and estado_perfil != "publico_leido":
        traduccion = {
            "privado": "cuenta privada: se leen la bio y los contadores, no los posts",
            "no_encontrado": "el handle no existe en Instagram",
            "bloqueado": "Instagram bloqueo el acceso: es un dato sobre nuestro "
                         "acceso, no sobre la persona. Conviene reintentar",
            "handle_equivocado": "el perfil cargo pero no se pudo verificar que "
                                 "sea de esta persona",
            "sin_handle": "no se encontro ningun handle candidato",
        }
        return "Sin señales de contenido — %s." % traduccion.get(
            estado_perfil, estado_perfil
        )

    if has_ig:
        raw_fol = row.get("ig_followers", None)
        fol_str = f"{int(raw_fol):,} seguidores" if pd.notna(raw_fol) and raw_fol > 0 else "sin conteo de seguidores"
        if lang == "spanish":
            parts.append(f"Publica exclusivamente en espanol en Instagram ({fol_str})")
        elif lang == "mixed":
            parts.append(f"Publica contenido bilingue —espanol e ingles— en Instagram ({fol_str})")
        elif lang == "english":
            parts.append(f"Instagram activo, publica en ingles ({fol_str})")
        else:
            parts.append(f"Tiene Instagram ({fol_str})")
    else:
        parts.append("No se detecto Instagram")

    co = str(row.get("company", "")).strip()
    if _es_positiva(row, "company_is_latino_brokerage"):
        parts.append(f'Trabaja en "{co}", empresa especializada en el mercado latino o hispano')
    elif _es_positiva(row, "company_has_spanish_name"):
        parts.append(f'Su empresa tiene nombre en espanol ("{co}")')

    sigs = []
    if _es_positiva(row, "ig_mentions_latino"):
        sigs.append("menciona explicitamente la comunidad latina en su perfil")
    if _es_positiva(row, "ig_nahrep"):
        sigs.append("es miembro de NAHREP o lo referencia en su contenido")
    if _es_positiva(row, "ig_posts_spanish") and lang not in ("spanish", "mixed", "es"):
        sigs.append("incluye posts en espanol aunque su idioma principal sea otro")
    if _es_positiva(row, "ig_spanish_signals") and lang in ("english", "en"):
        sigs.append("usa palabras o hashtags en espanol en bio o publicaciones")
    if _es_positiva(row, "ig_collaborates"):
        sigs.append("hace colaboraciones frecuentes en Instagram")
    if sigs:
        parts.append("Ademas: " + " y ".join(sigs))

    # `ig_community_type` se retiro con el analisis por alt-text. Lo reemplaza
    # `ig_programas`, que trae el programa, su qualifier, el conteo de posts y
    # el fragmento literal del caption.
    programas = row.get("ig_programas")
    if programas and pd.notna(programas):
        try:
            datos = json.loads(programas) if isinstance(programas, str) else programas
        except (json.JSONDecodeError, TypeError):
            datos = None
        if isinstance(datos, dict) and datos:
            listado = sorted(
                datos.items(),
                key=lambda kv: -(kv[1].get("n_posts", 0) if isinstance(kv[1], dict) else 0),
            )
            piezas = []
            for nombre, d in listado[:4]:
                n = d.get("n_posts") if isinstance(d, dict) else None
                q = d.get("qualifier") if isinstance(d, dict) else None
                piezas.append(
                    "%s%s%s" % (
                        nombre,
                        " en %d posts" % n if n else "",
                        " [%s]" % q if q else "",
                    )
                )
            parts.append("Programas que menciona: " + ", ".join(piezas))

    # Señales de ausencia declaradas. Van en la descripcion porque "no se pudo"
    # es un dato para el BD, no ruido a esconder.
    no_medidas = [c for c in SENALES_CONTENIDO if not _se_midio(row, c)]
    if no_medidas and has_ig:
        parts.append(
            "Sin medir (%d señales): %s"
            % (len(no_medidas), ", ".join(c.replace("ig_", "") for c in no_medidas[:4]))
        )

    try:
        u = int(float(str(row.get("units_sold", "")).strip()))
        if u > 0:
            parts.append(f"{u} unidades vendidas registradas")
    except Exception:
        pass

    return ". ".join(parts) + "." if parts else "Sin senales especificas detectadas."


def nivel_info(nivel) -> tuple[str, str, str]:
    """Color y etiqueta segun el NIVEL DE CALIFICACION, no segun un score.

    El nivel viene del motor de reglas y su orden esta en la referencia 07 de
    la skill. Cuando no hay nivel, se dice: no se sustituye por un tier.
    """
    n = str(nivel or "").strip().upper()
    if n == "MQL":
        return "#1a7a4a", "#d4efdf", "MQL"
    if n == "PRE-MQL":
        return "#1565c0", "#dce8fb", "pre-MQL · falta un dato"
    if n.startswith("BLOQUEADO"):
        return "#c07a00", "#fef3cd", "bloqueado por cobertura"
    if n == "DESCARTADO":
        return "#8a8a8a", "#f2f3f4", "descartado"
    return "#9a6b00", "#fff4e0", "sin diagnosticar"


def render_card(row) -> str:
    sc, bg, lbl = nivel_info(row.get("nivel_de_calificacion"))

    name    = str(row.get("full_name", "—")).title()
    company = str(row.get("company", "")).strip()
    state   = str(row.get("state", "")).strip()
    phone   = str(row.get("phone_mmi", "")).strip()
    ig_link = row.get("ig_link", None)
    handle  = str(row.get("ig_handle", "")).strip().lstrip("@")
    signal  = str(row.get("_signal", ""))

    phone_html = (
        f'<span style="color:#555;">&#x260E; {phone}</span>'
        if phone and phone != "nan" else ""
    )
    ig_html = (
        f'<a href="{ig_link}" target="_blank" '
        f'style="color:#1B4F72;font-weight:600;text-decoration:none;">'
        f'@{handle} &#8599;</a>'
        if ig_link else
        '<span style="color:#bbb;">sin Instagram</span>'
    )
    co_html = f"<b>{company}</b>" if company and company != "nan" else ""

    # La barra ya no representa un score: representa la INTENSIDAD del dolor
    # primario, que va de 0 a 3 y tiene su techo por grado de evidencia.
    intensidad = row.get("intensidad_primaria")
    if pd.notna(intensidad):
        ancho = int(float(intensidad) / 3 * 100)
        marca = "%d/3" % int(float(intensidad))
        barra = (
            f'<div style="height:4px;background:#e0e0e0;border-radius:2px;margin-top:6px;">'
            f'<div style="height:4px;width:{ancho}%;background:{sc};border-radius:2px;"></div></div>'
        )
    else:
        marca = "—"
        barra = (
            '<div style="height:4px;background:#e0e0e0;border-radius:2px;'
            'margin-top:6px;"></div>'
        )

    grado = str(row.get("grado_evidencia") or "").strip()
    conf = row.get("confianza_global")
    conf_txt = ("%.0f%%" % (float(conf) * 100)) if pd.notna(conf) else "[sin dato]"

    return (
        f'<div style="background:#fff;border:1px solid #e8ecf0;border-radius:14px;'
        f'padding:18px 20px 14px 20px;margin-bottom:10px;border-left:5px solid {sc};'
        f'box-shadow:0 1px 5px rgba(0,0,0,0.06);font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;">'
        f'<div style="display:flex;align-items:flex-start;gap:16px;">'
        f'<div style="min-width:78px;text-align:center;background:{bg};border-radius:10px;padding:8px 6px;">'
        f'<div style="font-size:1.35rem;font-weight:800;color:{sc};line-height:1;">{marca}</div>'
        f'<div style="font-size:0.6rem;color:{sc};font-weight:600;margin-top:2px;letter-spacing:.3px;">{lbl.upper()}</div>'
        f'{barra}'
        f'<div style="font-size:0.58rem;color:{sc};margin-top:5px;">'
        f'{grado or "—"} · conf {conf_txt}</div>'
        f'</div>'
        f'<div style="flex:1;min-width:0;">'
        f'<div style="font-size:1.05rem;font-weight:700;color:#1B4F72;margin-bottom:4px;">{name}</div>'
        f'<div style="font-size:0.85rem;color:#444;margin-bottom:6px;display:flex;flex-wrap:wrap;gap:6px 14px;">'
        f'{co_html}<span style="color:#888;">{state}</span>{phone_html}{ig_html}'
        f'</div>'
        f'<div style="font-size:0.82rem;color:#333;line-height:1.55;background:#f7f9fc;'
        f'border-radius:8px;padding:9px 13px;border-left:3px solid #aec6e8;">'
        f'{signal}'
        f'</div>'
        f'</div>'
        f'</div>'
        f'</div>'
    )


# ── App layout ─────────────────────────────────────────────────────────────────

st.set_page_config(page_title="HomeSi Prospector", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* Fuente global */
html, body, [class*="css"], [data-testid="stSidebar"] * {
    font-family: 'Inter', sans-serif !important;
}

/* Sidebar base */
[data-testid="stSidebar"] {
    background: linear-gradient(160deg, #1a3f5c 0%, #1B4F72 60%, #1a5276 100%) !important;
}
[data-testid="stSidebar"] * { color: white !important; }

/* Titulo del sidebar */
[data-testid="stSidebar"] h2 {
    font-size: 1.45rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.3px !important;
    color: white !important;
    margin-bottom: 2px !important;
}

/* Labels de filtros */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stMultiSelect label {
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px !important;
    text-transform: uppercase !important;
    color: rgba(255,255,255,0.7) !important;
}

/* Texto de caption */
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] small {
    color: rgba(255,255,255,0.55) !important;
    font-size: 0.74rem !important;
    line-height: 1.5 !important;
}

/* Inputs y selectbox */
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.1) !important;
    border: 1px solid rgba(255,255,255,0.25) !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
}
[data-testid="stSidebar"] .stMultiSelect > div > div {
    background: rgba(255,255,255,0.1) !important;
    border: 1px solid rgba(255,255,255,0.25) !important;
    border-radius: 8px !important;
}

/* Checkbox */
[data-testid="stSidebar"] .stCheckbox label span { color: white !important; font-size: 0.86rem !important; }

/* Boton */
[data-testid="stSidebar"] .stButton button {
    background: #F39C12; color: #000 !important; border: none;
    border-radius: 8px; width: 100%; font-weight: 700;
    padding: 9px 0; font-size: 0.88rem; letter-spacing: 0.2px;
    transition: background 0.2s;
}
[data-testid="stSidebar"] .stButton button:hover { background: #e67e22; }

/* Icono de ayuda */
[data-testid="stSidebar"] [data-testid="stTooltipIcon"] svg { fill:#F39C12 !important; }
[data-testid="stSidebar"] [data-testid="stTooltipIcon"]:hover svg { fill:#f8c471 !important; }

/* Ocultar texto del boton de colapsar sidebar */
[data-testid="stSidebar"] button[kind="header"] span { display: none !important; }
[data-testid="collapsedControl"] { font-size: 0 !important; }
[data-testid="stSidebarCollapseButton"] span { font-size: 0 !important; color: transparent !important; }
button[data-testid="stBaseButton-headerNoPadding"] span { display: none !important; }

/* Divider */
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.15) !important; margin: 12px 0 !important; }

/* Main */
.main .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
.metric-card { background: #f0f5fb; border-radius: 12px; padding: 14px 18px; text-align: center; }
.metric-num  { font-size: 1.8rem; font-weight: 800; color: #1B4F72; line-height: 1; }
.metric-lbl  { font-size: .76rem; color: #666; margin-top: 5px; font-weight: 500; }
h3 { color: #1B4F72 !important; }
</style>
""", unsafe_allow_html=True)

df_all  = load_realtors()
_origen = df_all.attrs.get("origen", "?")
if st.session_state.uploaded_batches:
    df_all = pd.concat([df_all] + st.session_state.uploaded_batches, ignore_index=True)
    # concat pierde los attrs y vuelve a introducir NaN donde una de las dos
    # partes no tenia la columna. Se re-normaliza para que las señales de
    # contenido queden en <NA> y no en NaN flotante.
    df_all = _normalize_realtors(df_all)

# De donde salio la sabana, arriba y visible. Si alguien mira un diagnostico,
# tiene que poder decir sobre que archivo se calculo.
st.caption("Sabana: `%s`" % _origen)
census  = load_census()
states_available = sorted(df_all["state"].dropna().unique().tolist())
all_states_opts  = ["Todos los estados"] + states_available

# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
<div style='padding:4px 0 18px 0;'>
  <div style='font-size:1.45rem;font-weight:800;letter-spacing:-0.3px;line-height:1.2;'>HomeSi Prospector</div>
  <div style='font-size:0.8rem;color:rgba(255,255,255,0.6);margin-top:6px;font-weight:400;'>
    Selecciona un estado en el <b style="color:white;">mapa</b> o filtra aqui abajo
  </div>
</div>
""", unsafe_allow_html=True)

    # State search/select — synced with map click
    current = st.session_state.selected_state or "Todos los estados"
    idx     = all_states_opts.index(current) if current in all_states_opts else 0
    sidebar_state = st.selectbox("Estado", all_states_opts, index=idx)
    if sidebar_state != current:
        st.session_state.selected_state = None if sidebar_state == "Todos los estados" else sidebar_state
        st.session_state.n_show = 25
        st.rerun()

    st.markdown("---")
    niveles_sel = st.multiselect(
        "Nivel de calificacion",
        NIVELES,
        default=[],
        help=(
            "MQL: pasa las tres compuertas y tiene un dolor a intensidad >=2. "
            "Pre-MQL: le falta un DATO, no es un rechazo. "
            "Bloqueado por cobertura: califica pero hoy no podemos originarle. "
            "Vacio = todos."
        ),
    )
    intensidad_min = st.slider(
        "Intensidad minima del dolor primario", 0, 3, 0,
        help=(
            "0 a 3, con techo por grado de evidencia: E3 nunca pasa de 1, "
            "E2 de 2, y solo E0 (texto propio de la persona) llega a 3."
        ),
    )
    solo_handle_verificado = st.checkbox(
        "Solo con handle de Instagram verificado",
        value=False,
        help=(
            "Deja fuera los de handle_confidence baja. Sus señales de contenido "
            "no se usan: un handle equivocado no produce un error, produce "
            "catorce señales sobre la persona equivocada."
        ),
    )

    lang_opts = st.multiselect(
        "Contenido Instagram",
        ["spanish", "mixed", "english"],
        default=[],
        format_func=lambda x: {
            "spanish": "Espanol (exclusivo)",
            "mixed":   "Bilingue (mixto)",
            "english": "Solo ingles",
        }.get(x, x),
    )
    only_latino_co = st.checkbox("Solo empresas latinas / hispanas", value=False)
    only_ig        = st.checkbox("Solo con Instagram detectado",     value=False)

    st.markdown("---")
    all_batches = sorted(df_all["batch_name"].unique().tolist())
    batch_filter = st.multiselect(
        "Filtrar por subida",
        all_batches,
        default=[],
        help="Muestra solo realtors de una carga especifica. Vacio = todas las cargas.",
    )

    st.markdown("---")
    st.caption(
        "Este dashboard ya no muestra un score. Muestra el diagnostico del "
        "motor de reglas PACS-H: nivel de calificacion, dolor primario con su "
        "intensidad, grado de evidencia y confianza declarada. "
        "La confianza mide cuantas ventanas distintas tuvimos al mismo sujeto, "
        "no que tan alto salio un numero."
    )

# ── Map ────────────────────────────────────────────────────────────────────────
#
# El color del mapa era el score promedio del estado. Ahora es el porcentaje de
# MQL sobre los realtors diagnosticados de ese estado, con su denominador en el
# tooltip: un 100% sobre 3 realtors no es lo mismo que un 40% sobre 500.

realtor_stats = df_all.groupby("state").agg(
    n_realtors     = ("full_name", "count"),
    n_diagnosticado= ("nivel_de_calificacion", lambda s: int(s.notna().sum())),
    n_mql          = ("nivel_de_calificacion", lambda s: int((s == "MQL").sum())),
    n_bloqueado    = ("nivel_de_calificacion",
                      lambda s: int(s.astype("string").str.startswith("BLOQUEADO").fillna(False).sum())),
).reset_index()

map_df = census.merge(realtor_stats, on="state", how="outer")
map_df["state_abbr"]       = map_df["state"].map(NAME_TO_ABBR)
map_df["hispanic_pct_pct"] = (map_df["hispanic_pct"] * 100).round(1)
for col in ("n_realtors", "n_diagnosticado", "n_mql", "n_bloqueado"):
    map_df[col] = map_df[col].fillna(0).astype(int)
map_df["pct_mql"] = np.where(
    map_df["n_diagnosticado"] > 0,
    (map_df["n_mql"] / map_df["n_diagnosticado"] * 100).round(1),
    np.nan,
)
map_df["hispanic_pop"]     = map_df["hispanic_pop"].fillna(0)
map_df = map_df[map_df["state_abbr"].notna()].copy()

sel = st.session_state.selected_state
fig = go.Figure()

fig.add_trace(go.Choropleth(
    locations    = map_df["state_abbr"],
    z            = map_df["hispanic_pct_pct"],
    locationmode = "USA-states",
    colorscale   = [[0,"#e8f4f8"],[0.15,"#aed6f1"],[0.4,"#2e86c1"],[1,"#1b2a6b"]],
    zmin=0, zmax=50,
    colorbar     = dict(title="% Hispano", thickness=12, len=0.42, x=1.01, xanchor="left", y=0.82, yanchor="top", ticksuffix="%"),
    hovertemplate=(
        "<b>%{text}</b><br>"
        "Hispanohablantes: <b>%{customdata[0]:,.0f}</b><br>"
        "Porcentaje: <b>%{z:.1f}%</b><extra></extra>"
    ),
    text       = map_df["state"],
    customdata = map_df[["hispanic_pop"]].values,
    marker     = dict(line=dict(color="white", width=0.8)),
))

if sel:
    sel_row = map_df[map_df["state"] == sel]
    if len(sel_row):
        fig.add_trace(go.Choropleth(
            locations=sel_row["state_abbr"], z=[1],
            locationmode="USA-states",
            colorscale=[[0,"rgba(0,0,0,0)"],[1,"rgba(0,0,0,0)"]],
            showscale=False,
            marker=dict(line=dict(color="#F39C12", width=3.5)),
            hoverinfo="skip",
        ))

fig.add_trace(go.Scattergeo(
    locations    = map_df["state_abbr"],
    locationmode = "USA-states",
    mode         = "markers",
    marker=dict(
        size       = np.sqrt(map_df["n_realtors"].clip(1)) * 3.2,
        color      = map_df["pct_mql"],
        cmin=0, cmax=60,
        colorscale = [[0,"#f9ebea"],[0.45,"#f39c12"],[1,"#1a7a4a"]],
        colorbar   = dict(title="% MQL<br>de los<br>diagnosticados",
                          thickness=12, len=0.42, x=1.01, xanchor="left",
                          y=0.3, yanchor="top", ticksuffix="%"),
        line=dict(width=1.5, color="white"),
        opacity=0.88,
    ),
    text       = map_df["state"],
    customdata = map_df[["n_realtors", "n_mql", "n_diagnosticado",
                         "hispanic_pop", "hispanic_pct_pct",
                         "n_bloqueado"]].values,
    # El porcentaje NUNCA va sin su denominador, ni en un tooltip.
    hovertemplate=(
        "<b>%{text}</b><br>"
        "Hispanohablantes: <b>%{customdata[3]:,.0f}</b> (%{customdata[4]:.1f}%)<br>"
        "Realtors en el lote: <b>%{customdata[0]}</b><br>"
        "MQL: <b>%{customdata[1]}</b> de %{customdata[2]} diagnosticados<br>"
        "Bloqueados por cobertura: %{customdata[5]}<br>"
        "<i>Click para filtrar lista</i><extra></extra>"
    ),
    showlegend=False,
))

fig.update_layout(
    geo=dict(
        scope="usa", showlakes=False, showland=True,
        landcolor="#f0f0eb", bgcolor="rgba(0,0,0,0)",
        projection_type="albers usa",
    ),
    margin=dict(l=0, r=0, t=0, b=0),
    height=345,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor ="rgba(0,0,0,0)",
)

st.markdown("### Hispanohablantes por Estado")
st.markdown("""
<div style="display:flex;gap:24px;flex-wrap:wrap;align-items:center;
            font-size:0.78rem;color:#555;margin-bottom:6px;line-height:1.6;">
  <span>
    <span style="display:inline-block;width:52px;height:10px;border-radius:4px;
                 background:linear-gradient(to right,#e8f4f8,#2e86c1,#1b2a6b);
                 vertical-align:middle;margin-right:5px;"></span>
    Color del estado = % poblacion hispanohablante &nbsp;<b style="color:#1b2a6b;">azul oscuro = mas hispanos</b>
  </span>
  <span>
    <span style="display:inline-flex;gap:4px;align-items:center;vertical-align:middle;margin-right:5px;">
      <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#888;opacity:.5;"></span>
      <span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:#888;opacity:.7;"></span>
      <span style="display:inline-block;width:20px;height:20px;border-radius:50%;background:#888;"></span>
    </span>
    Tamano del circulo = cantidad de realtors en ese estado
  </span>
  <span>
    <span style="display:inline-block;width:12px;height:12px;border-radius:50%;
                 background:linear-gradient(135deg,#f9ebea,#f39c12,#1a7a4a);
                 vertical-align:middle;margin-right:5px;"></span>
    Color del circulo = % de MQL sobre los diagnosticados &nbsp;<b style="color:#1a7a4a;">verde = mas MQL</b>
  </span>
  <span style="color:#1B4F72;font-weight:600;">
    Click en un circulo para ver los realtors de ese estado
  </span>
</div>
""", unsafe_allow_html=True)

chart_event = st.plotly_chart(
    fig, use_container_width=True, key="map_chart",
    on_select="rerun", config={"displayModeBar": False},
)

if chart_event and chart_event.selection and chart_event.selection.points:
    for pt in chart_event.selection.points:
        clicked = pt.get("text", "")
        if clicked and clicked in states_available:
            if clicked != st.session_state.selected_state:
                st.session_state.selected_state = clicked
                st.session_state.n_show = 25
                st.rerun()
            break

# ── Filter ─────────────────────────────────────────────────────────────────────

df = df_all.copy()
if st.session_state.selected_state:
    df = df[df["state"] == st.session_state.selected_state]
if niveles_sel:
    df = df[df["nivel_de_calificacion"].isin(niveles_sel)]
if intensidad_min > 0:
    df = df[df["intensidad_primaria"].fillna(-1) >= intensidad_min]
if solo_handle_verificado:
    df = df[df["ig_senales_usables"]]
if lang_opts:
    df = df[df["ig_content_language"].astype("string").str.lower().isin(lang_opts)]
if only_latino_co:
    df = df[df["company_is_latino_brokerage"].fillna(False)]
if only_ig:
    df = df[df["ig_handle"].notna()]
if batch_filter:
    df = df[df["batch_name"].isin(batch_filter)]

# El orden ya no es por score. Es el de la metodologia: nivel de calificacion
# primero, despues intensidad del dolor primario, despues confianza declarada.
# Los sin diagnosticar van al final, no al medio: no compiten con los MQL.
df = df.sort_values(
    ["_orden_nivel", "intensidad_primaria", "confianza_global"],
    ascending=[True, False, False],
    na_position="last",
).reset_index(drop=True)
df["_signal"] = df.apply(build_signal_description, axis=1)

# ── Header ─────────────────────────────────────────────────────────────────────

st.markdown("---")

if st.session_state.selected_state:
    c_row = census[census["state"] == st.session_state.selected_state]
    if len(c_row):
        hp   = int(c_row["hispanic_pop"].values[0])
        hpct = c_row["hispanic_pct"].values[0] * 100
        tot  = int(c_row["total_population"].values[0])
        st.markdown(f"### {st.session_state.selected_state}")
        st.caption(
            f"**{hp:,} hispanohablantes** · {hpct:.1f}% de {tot:,} habitantes  ·  "
            f"**{len(df):,} realtors** con filtros actuales"
        )
    else:
        st.markdown(f"### {st.session_state.selected_state} — {len(df):,} realtors")
else:
    total_hisp = int(census["hispanic_pop"].sum()) if len(census) else 0
    st.markdown("### Todos los estados")
    st.caption(
        f"**{total_hisp:,} hispanohablantes** en EE.UU. (Census ACS 2024)  ·  "
        f"**{len(df):,} realtors** con filtros actuales"
    )

# ── KPIs ───────────────────────────────────────────────────────────────────────

# Los KPIs llevan denominador. Un "38 MQL" sin decir de cuantos no significa
# nada, y el denominador que importa no es el total sino los DIAGNOSTICADOS:
# los que el motor no pudo diagnosticar no son un no.
n_diag  = int(df["nivel_de_calificacion"].notna().sum())
n_mql   = int((df["nivel_de_calificacion"] == "MQL").sum())
n_bloq  = int(df["nivel_de_calificacion"].astype("string")
              .str.startswith("BLOQUEADO").fillna(False).sum())
n_usable = int(df["ig_senales_usables"].sum())

kpi_mql = "%d / %d" % (n_mql, n_diag) if n_diag else "— / 0"

cols = st.columns(4)
for col, num, lbl in [
    (cols[0], f"{len(df):,}",   "realtors en el lote"),
    (cols[1], kpi_mql,          "MQL de los diagnosticados"),
    (cols[2], f"{n_bloq:,}",    "bloqueados por cobertura"),
    (cols[3], f"{n_usable:,}",  "handle IG verificado"),
]:
    col.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-num">{num}</div>'
        f'<div class="metric-lbl">{lbl}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown("")

# ── Realtor table ──────────────────────────────────────────────────────────────

df["Senales"]    = df["_signal"]
df["Seguidores"] = df["ig_followers"].apply(
    lambda x: f"{int(x):,}" if pd.notna(x) and x > 0 else ""
)

df["Nivel"]      = df["nivel_de_calificacion"].fillna("sin diagnosticar")
df["Dolor"]      = df["pain_primario"].fillna("—")
df["Int"]        = df["intensidad_primaria"]
df["Evid"]       = df["grado_evidencia"].fillna("—")
df["Confianza"]  = df["confianza_global"]
df["Habla"]      = df["acto_de_habla"].fillna("—")
df["Gancho"]     = df["gancho"].fillna(
    df["pregunta_de_cierre_de_brecha"].fillna("—")
)

display = df.rename(columns={
    "full_name":  "Nombre",
    "company":    "Empresa",
    "state":      "Estado",
    "batch_name": "Carga",
    "ig_link":    "Instagram",
})[["Nivel", "Dolor", "Int", "Evid", "Confianza", "Habla",
    "Nombre", "Empresa", "Estado", "Carga", "Instagram", "Gancho"]].head(500)

st.dataframe(
    display,
    use_container_width=True,
    height=560,
    column_config={
        "Nivel": st.column_config.TextColumn("Nivel", width="small"),
        "Dolor": st.column_config.TextColumn("Dolor primario", width="small"),
        # La barra va de 0 a 3, que es la escala real de la matriz.
        "Int": st.column_config.ProgressColumn(
            "Intensidad", min_value=0, max_value=3, format="%d", width="small",
        ),
        "Evid": st.column_config.TextColumn(
            "Evidencia", width="small",
            help=("E0 lo verbalizo con su texto · E1 consta en un registro · "
                  "E2 se deduce de su estructura · E3 es plausible por su "
                  "mercado. E3 nunca pasa de intensidad 1."),
        ),
        "Confianza": st.column_config.NumberColumn(
            "Confianza", format="%.0f%%", width="small",
            help=("mide cuantas ventanas distintas tuvimos al mismo sujeto, "
                  "no que tan alto salio un numero"),
        ),
        "Habla": st.column_config.TextColumn(
            "Acto de habla", width="small",
            help="AFIRMA solo con intensidad 3 y evidencia E0. Todo lo demas PREGUNTA.",
        ),
        "Gancho": st.column_config.TextColumn(
            "Gancho conversacional", width="large",
            help=("literal del corpus PACS. Se copia tal cual: no se reescribe "
                  "'mejor'."),
        ),
        "Instagram": st.column_config.LinkColumn(
            "Instagram",
            display_text=r"instagram\.com/([^/]+)",
            width="medium",
        ),
        "Nombre":  st.column_config.TextColumn("Nombre",  width="medium"),
        "Empresa": st.column_config.TextColumn("Empresa", width="medium"),
        "Estado":  st.column_config.TextColumn("Estado",   width="small"),
        "Carga":   st.column_config.TextColumn("Carga",    width="small"),
    },
    hide_index=True,
)

if len(df) > 500:
    st.caption(f"Primeros 500 de {len(df):,}. Descarga el CSV para ver todos.")

# ── El reporte de lote ─────────────────────────────────────────────────────────
#
# La referencia 12 de la skill lo dice: el punto mas valioso del entregable es
# "el dato mas barato que subiria todo el lote", y el segundo es "lo que NO
# pudiste hacer". Los dos viven aca y no en un apendice.

with st.expander("Reporte de lote · que se pudo acreditar y que no", expanded=False):
    n_total = len(df)
    st.markdown("**Cobertura de las señales de contenido**")
    filas_cob = []
    for col in SENALES_CONTENIDO:
        medidas = int(df[col].notna().sum())
        filas_cob.append({
            "señal": col,
            "medida en": "%d de %d" % (medidas, n_total),
            "%": round(medidas / n_total * 100, 1) if n_total else 0.0,
        })
    st.dataframe(pd.DataFrame(filas_cob), hide_index=True,
                 use_container_width=True)
    st.caption(
        "Lo que falta esta en null, no en 0. Un 0 en `ig_is_private` "
        "significaria 'esta cuenta no es privada', que es una afirmacion: en el "
        "dataset viejo esa columna estaba en 0 en las 5.620 filas, lo cual es "
        "imposible, y el modelo le dio importancia 0,000 sin que nadie lo notara."
    )

    st.markdown("**Handle de Instagram**")
    conf = df["ig_handle_confidence"].value_counts(dropna=False)
    st.dataframe(
        pd.DataFrame({
            "confianza": [str(k) for k in conf.index],
            "realtors": conf.values,
        }),
        hide_index=True, use_container_width=True,
    )
    st.caption(
        "Solo **alta** y **media** alimentan señales del motor. Un handle de "
        "confianza baja no produce un error: produce catorce señales sobre la "
        "persona equivocada."
    )

    sin_diag = n_total - n_diag
    if sin_diag:
        st.warning(
            "**%d de %d realtors no tienen diagnostico PACS.** No es un no: es "
            "que el motor de reglas todavia no corrio sobre esta sabana, o que "
            "les falta un dato. Los pre-MQL son cola de re-enriquecimiento, no "
            "descarte." % (sin_diag, n_total)
        )

# ── Downloads ──────────────────────────────────────────────────────────────────

st.markdown("---")
_SKIP_COLS = {
    "_signal", "ig_link", "state_abbr", "_hisp_abs", "Senales", "Seguidores",
    "_orden_nivel", "Nivel", "Dolor", "Int", "Evid", "Confianza", "Habla",
    "Gancho",
}
export_cols  = [c for c in df_all.columns if c not in _SKIP_COLS]

col_dl1, col_dl2, _ = st.columns([1, 1, 2])

with col_dl1:
    _df_export = df[[c for c in export_cols if c in df.columns]]
    st.download_button(
        "⬇ Descargar con filtros activos (CSV)",
        _df_export.to_csv(index=False).encode("utf-8"),
        f"realtors_{(st.session_state.selected_state or 'todos').replace(' ','_').lower()}.csv",
        "text/csv",
        help="Exporta exactamente lo que ves: estado, score minimo, idioma y carga seleccionados",
    )
with col_dl2:
    _all_cols = [c for c in df_all.columns if c not in _SKIP_COLS]
    st.download_button(
        "⬇ Todos los realtors — sin filtros (CSV)",
        df_all[_all_cols].to_csv(index=False).encode("utf-8"),
        "realtors_todos.csv",
        "text/csv",
        help="Lista completa sin aplicar ningun filtro, con toda la informacion de Instagram y demas",
    )

# ── Nueva Carga ────────────────────────────────────────────────────────────────

st.markdown("---")
with st.expander("Subir nueva lista de realtors", expanded=False):
    st.markdown(
        "Sube un Excel con las columnas: "
        "**First Name, Last Name, Company / Account, Email, Phone, State, "
        "BS Sold # Units**\n\n"
        "El archivo se normaliza y entra a la sesion como **pre-MQL sin "
        "enriquecer**. No se puntua: no hay score, y hasta que no pase por el "
        "enriquecimiento y por el motor de reglas PACS-H no hay diagnostico. "
        "Un numero calculado sobre catorce columnas vacias es peor que una "
        "celda que dice que falta el dato."
    )

    uploaded = st.file_uploader(
        "Selecciona el archivo Excel",
        type=["xlsx", "xls"],
        key="new_batch",
    )
    batch_label_up = st.text_input(
        "Nombre para esta carga",
        placeholder="julio_2026",
        key="batch_label_up",
    )

    if uploaded:
        file_stem = uploaded.name.rsplit(".", 1)[0]
        label     = batch_label_up.strip() or _re.sub(r"[^a-zA-Z0-9_-]", "_", file_stem)

        already_loaded = any(
            b["batch_name"].iloc[0] == label
            for b in st.session_state.uploaded_batches
            if len(b)
        )

        if not already_loaded:
            with st.spinner(f"Normalizando {label}…"):
                preparado = preparar_excel_subido(uploaded.getvalue(), label)
            if preparado is not None and len(preparado):
                st.session_state.uploaded_batches.append(preparado)
                st.success(
                    f"{len(preparado):,} realtors normalizados y añadidos con "
                    f"etiqueta **{label}**. Puedes filtrarlos en el sidebar con "
                    "'Filtrar por subida'."
                )
                st.warning(
                    "**Sin enriquecer y sin diagnostico.** Entraron como "
                    "pre-MQL con lo unico que se puede afirmar del archivo: los "
                    "datos de MMI, el estado y los dos flags de brokerage. "
                    "Las señales de Instagram quedan en null, no en cero. "
                    "El paso a paso esta abajo."
                )
                st.rerun()
            else:
                st.error("No se pudo procesar el archivo. Verifica que tenga las columnas correctas.")
        else:
            st.info(f"La carga **{label}** ya está en la sesión actual.")

st.markdown("---")
with st.expander("Como obtener el diagnostico PACS (paso a paso)", expanded=False):
    st.markdown("""
### Lo que ves al subir el Excel no es un diagnostico

Es el archivo normalizado. Sin captions de Instagram no se sabe si el realtor
publica en español, ni que programas menciona, ni que le preguntan sus clientes.
Y sin eso el motor de reglas PACS-H no tiene con que activar un qualifier.

**Ya no hay un score que rellene ese hueco.** El modelo que lo producia se
retiro el 2026-09-21: su label no era valido. 653 realtors estaban marcados como
convertidos sin haber sido llamados nunca.

---

### El pipeline, en orden

| Paso | Script | Que hace |
|---|---|---|
| 1 | `realtor_scraper/mmi_enricher.py` | Busca y **verifica** el handle, lee los captions con fecha, los comentarios y el estado del perfil |
| 2 | `realtor_scraper/consolidar_mmi.py` | Junta los enriched y agrega Census por estado |
| 3 | el motor de reglas PACS-H | Produce el diagnostico: nivel, dolor primario, intensidad, evidencia, gancho |
| 4 | recargar esta pagina | Toma el CSV mas reciente de `realtor_scraper/output/` |

El motor de reglas vive en la skill `homesi-pacs-scoring`, no en este repo:
este repo produce sus **insumos**.

---

### Cuanto tarda

Entre 3 y 8 segundos por realtor solo para la busqueda y el perfil. Con
comentarios son unos **3 minutos por realtor**, porque cada post es una
navegacion aparte.

Para un lote grande conviene:

- `--skip-comentarios` en el barrido amplio, y comentarios solo para los que
  pasen las compuertas;
- `--state Texas` para acotar;
- `--limit 5 --no-headless` la primera vez, mirando la pantalla: los selectores
  de Instagram cambian y hay que confirmar que siguen andando.

---

### Lo que hay que mirar antes de creerle a una fila

1. **`ig_handle_confidence`.** Si es `baja`, sus señales de contenido no se usan.
   El sistema anterior decia haber encontrado el 98,1% de los handles sin
   verificar ninguno.
2. **`ig_estado_perfil`.** Un perfil `privado` o `bloqueado` no es un perfil sin
   señales: es un perfil que no se pudo leer, y la diferencia esta declarada.
3. **`grado_evidencia`.** E3 es plausibilidad de mercado y nunca pasa de
   intensidad 1. Solo E0 —texto propio de la persona— llega a 3, y solo ahi el
   copy AFIRMA.
""")
