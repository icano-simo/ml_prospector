"""
MMI Data Enricher
=================
Reads MMI Data.xlsx (name, company, email, phone, state, units sold, loan volume),
then enriches each realtor with Instagram: handle, followers, posts, bio,
captions with dates, comments aggregated as an audience profile, and the
availability mask for every content signal.

La capa de Zillow se retiro el 2026-09-21: produjo cero columnas en toda la
salida y sus terminos de uso prohiben el scraping. Ver la seccion "Que se
intento y no funciono" del README. No se reintenta.

El archivo de entrada vive FUERA del repo, en
../ml_prospector_datos_privados/insumos/, porque trae email y telefono de
personas reales. Se puede apuntar a otro con --input o con la variable de
entorno ML_PROSPECTOR_DATOS.

Output: realtor_scraper/output/mmi_enriched_YYYYMMDD_HHMM.csv
        (saves checkpoint after every realtor)

Usage:
  python mmi_enricher.py
  python mmi_enricher.py --limit 20          # test with first 20
  python mmi_enricher.py --state Texas       # only one state
  python mmi_enricher.py --no-headless       # show browser window
  python mmi_enricher.py --skip-instagram    # skip Instagram lookup
  python mmi_enricher.py --resume output/mmi_enriched_20240101_1200.csv
"""
import sys
import time
import random
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd
from loguru import logger
from tqdm import tqdm

try:
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent
OUTPUT_DIR  = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT))
from datos_privados import ruta_insumo  # noqa: E402
from instagram.finder import buscar_instagram  # noqa: E402
from navegador import crear_contexto  # noqa: E402

MMI_DEFECTO = "MMI Data.xlsx"

logger.remove()
logger.add(sys.stderr,
           format="<green>{time:HH:mm:ss}</green> | <level>{level:5}</level> | {message}",
           level="INFO")
logger.add(OUTPUT_DIR / "mmi_enricher.log", rotation="10 MB", level="DEBUG")

DELAY_INSTAGRAM = (3.0, 7.0)
DELAY_GOOGLE    = (4.0, 9.0)


def main():
    parser = argparse.ArgumentParser(description="Enrich MMI realtors with Instagram")
    parser.add_argument("--limit",          type=int,   default=None)
    parser.add_argument("--state",          type=str,   default=None, help="Filter by state name")
    parser.add_argument("--skip-states",    nargs="+",  default=None, help="Skip these states, process the rest")
    parser.add_argument("--no-headless",    action="store_true")
    parser.add_argument("--skip-instagram", action="store_true")
    parser.add_argument("--skip-comentarios", action="store_true",
                        help="no leer comentarios (mas rapido, pero sin S8)")
    parser.add_argument("--resume",         type=str,   default=None,
                        help="Path to existing output CSV to resume from")
    parser.add_argument("--input",          type=str,   default=None,
                        help="Path to Excel file to process (default: MMI Data.xlsx)")
    parser.add_argument("--batch-name",     type=str,   default=None,
                        help="Label for this batch (appears in output as batch_name column)")
    args = parser.parse_args()

    # ── Load MMI data ─────────────────────────────────────────────────────────
    input_path = Path(args.input) if args.input else ruta_insumo(MMI_DEFECTO)
    batch_name = args.batch_name or input_path.stem.replace(" ", "_")
    logger.info(f"Reading {input_path.name}  [batch: {batch_name}]...")
    df = pd.read_excel(input_path, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]

    # Normalize column names
    df = df.rename(columns={
        "First Name":           "first_name",
        "Last Name":            "last_name",
        "Company / Account":   "company",
        "Email":                "email_mmi",
        "Phone":                "phone_mmi",
        "State":                "state",
        "BS Sold # Units":      "units_sold",
        "Loan Volume 14 months":"loan_volume",
    })
    df["full_name"] = (df["first_name"].str.strip() + " " + df["last_name"].str.strip()).str.strip()

    if args.state:
        df = df[df["state"].str.lower() == args.state.lower()]
        logger.info(f"Filtered to state '{args.state}': {len(df)} realtors")

    if args.skip_states:
        skip_lower = [s.lower() for s in args.skip_states]
        df = df[~df["state"].str.lower().isin(skip_lower)]
        logger.info(f"Skipping {len(args.skip_states)} states | Remaining: {len(df)} realtors")

    if args.limit:
        df = df.head(args.limit)

    logger.info(f"Total realtors to process: {len(df)}")

    # ── Resume from existing output ───────────────────────────────────────────
    already_done: set[str] = set()
    resume_path = None
    if args.resume:
        resume_path = Path(args.resume)
        if resume_path.exists():
            done_df = pd.read_csv(resume_path, dtype=str)
            already_done = set(done_df["full_name"].dropna().str.strip())
            logger.info(f"Resuming — {len(already_done)} realtors already processed")

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = resume_path or (OUTPUT_DIR / f"mmi_enriched_{timestamp}.csv")

    # ── Convert DataFrame to list of dicts ────────────────────────────────────
    records = df.to_dict("records")
    enriched: list[dict] = []

    # Load already-done records if resuming
    if resume_path and resume_path.exists():
        existing = pd.read_csv(resume_path, dtype=str)
        enriched = existing.to_dict("records")

    with sync_playwright() as p:
        # Persistent context + patchright patches Cloudflare fingerprinting
        context = crear_contexto(p, headless=not args.no_headless)
        ig_page = context.new_page()   # DuckDuckGo + Instagram

        bar = tqdm(records, desc="Enriching", unit="realtor")
        for rec in bar:
            name = rec.get("full_name", "").strip()
            if not name:
                continue
            if name in already_done:
                bar.set_postfix({"skip": name[:20]})
                continue

            row = _base_record(rec)
            row["batch_name"] = batch_name

            # ── Instagram ─────────────────────────────────────────────────────
            # Devuelve SenalesInstagram, no un dict de booleanos. Cada señal
            # que puede faltar viene en None y `ig_disponibilidad` dice por que.
            # Nunca False donde corresponde null.
            if not args.skip_instagram:
                senales = buscar_instagram(
                    nombre=rec.get("first_name", ""),
                    apellido=rec.get("last_name", ""),
                    estado=rec.get("state", ""),
                    page=ig_page,
                    licencia_conocida=rec.get("license_number") or None,
                    con_comentarios=not args.skip_comentarios,
                )
                row.update(senales.a_fila())
                time.sleep(random.uniform(*DELAY_GOOGLE))

            enriched.append(row)
            already_done.add(name)
            _save(enriched, output_path)

            ig_found = sum(1 for r in enriched if r.get("ig_handle"))
            bar.set_postfix({
                "ig": ig_found,
                "last": name[:18],
            })

        context.close()

    _save(enriched, output_path)
    _summary(enriched, output_path)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_record(rec: dict) -> dict:
    return {
        "full_name":   rec.get("full_name", "").strip(),
        "first_name":  rec.get("first_name", "").strip().title(),
        "last_name":   rec.get("last_name", "").strip().title(),
        "company":     rec.get("company", "").strip(),
        "state":       rec.get("state", "").strip(),
        "email_mmi":   rec.get("email_mmi", "").strip() or None,
        "phone_mmi":   rec.get("phone_mmi", "").strip() or None,
        "units_sold":  rec.get("units_sold", "").strip() or None,
        "loan_volume": rec.get("loan_volume", "").strip() or None,
    }


def _save(records: list[dict], path: Path):
    """Guarda el checkpoint. El orden de columnas no esta hardcodeado.

    La version anterior listaba a mano las dieciseis columnas `ig_*`, asi que
    agregar una señal nueva la dejaba fuera del CSV en silencio. Ahora las
    columnas de MMI van primero en su orden y todas las `ig_*` despues,
    alfabeticas: una señal nueva aparece sin tocar esta funcion.
    """
    if not records:
        return
    df = pd.DataFrame(records)
    df = df.drop_duplicates(subset=["full_name"], keep="last")

    orden_mmi = [
        "full_name", "first_name", "last_name", "company", "state",
        "email_mmi", "phone_mmi", "units_sold", "loan_volume", "batch_name",
    ]
    primeras = [c for c in orden_mmi if c in df.columns]
    # Las de identidad y estado del perfil van al frente de las ig_*, porque
    # son las que hay que mirar antes de creerle a cualquier otra.
    cabecera_ig = [
        c for c in ("ig_handle", "ig_url", "ig_estado_perfil",
                    "ig_handle_confidence", "ig_motivo_estado",
                    "ig_razon_confianza")
        if c in df.columns
    ]
    resto_ig = sorted(
        c for c in df.columns
        if c.startswith("ig_") and c not in cabecera_ig
    )
    otras = [c for c in df.columns
             if c not in primeras + cabecera_ig + resto_ig]
    df[primeras + cabecera_ig + resto_ig + otras].to_csv(path, index=False)


def _summary(records: list[dict], path: Path):
    df = pd.DataFrame(records)
    total = len(df)
    if total == 0:
        logger.warning("No records processed.")
        return

    def pct(n): return f"{n} ({n/total*100:.0f}%)"

    ig_found  = int(df["ig_handle"].notna().sum()) if "ig_handle" in df.columns else 0
    email_mmi = int(df["email_mmi"].notna().sum()) if "email_mmi" in df.columns else 0

    logger.info("=" * 62)
    logger.info(f"Total realtors procesados : {total:,}")
    logger.info(f"Handle candidato          : {pct(ig_found)}")
    logger.info(f"Email MMI                 : {pct(email_mmi)}")

    # El reporte de lote. 'Encontrado' no es 'verificado', y la version anterior
    # reportaba 98,1% de handles encontrados sin verificar ninguno.
    if "ig_handle_confidence" in df.columns:
        logger.info("-" * 62)
        logger.info("Confianza del handle (solo alta y media alimentan señales):")
        for nivel in ("alta", "media", "baja"):
            n = int(df["ig_handle_confidence"].eq(nivel).sum())
            logger.info(f"  {nivel:6}: {pct(n)}")

    if "ig_estado_perfil" in df.columns:
        logger.info("-" * 62)
        logger.info("Estado del perfil:")
        for estado, n in df["ig_estado_perfil"].value_counts().items():
            logger.info(f"  {str(estado):20}: {pct(int(n))}")

    if "ig_intensidad_pq14" in df.columns:
        medidos = int(df["ig_intensidad_pq14"].notna().sum())
        logger.info("-" * 62)
        logger.info(f"P-Q14 (barrera de idioma) medido en: {pct(medidos)}")
        logger.info("  El resto queda en null, NO en 0. Un 0 significaria "
                    "'operacion integramente en ingles', que es una afirmacion.")

    logger.info("-" * 62)
    logger.info(f"Guardado en: {path}")
    logger.info("=" * 62)


if __name__ == "__main__":
    main()
