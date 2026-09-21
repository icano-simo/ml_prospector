"""Contexto de navegador compartido.

Vivia dentro de zillow/profile_scraper.py, que se retiro del repo el 2026-09-21
(ver la seccion "Que se intento y no funciono" del README). El unico pedazo que
valia la pena de ese modulo era la fabrica de contexto persistente, asi que se
extrajo aca sin nada especifico de Zillow.

El perfil es persistente a proposito: las cookies se acumulan entre corridas y
eso reduce la cantidad de desafios anti-bot que hay que resolver.
"""
from __future__ import annotations

import random
import time

from loguru import logger

from config import OUTPUT_DIR

PERFIL_DIR = OUTPUT_DIR / "browser_profile"
PERFIL_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def crear_contexto(playwright_instance, headless: bool = True):
    """Contexto persistente de Chromium. Con patchright si esta instalado."""
    return playwright_instance.chromium.launch_persistent_context(
        user_data_dir=str(PERFIL_DIR),
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
        ],
        viewport={"width": 1366, "height": 768},
        user_agent=USER_AGENT,
        locale="en-US",
        timezone_id="America/Chicago",
    )


def pausa(rango: tuple[float, float]) -> None:
    """Pausa aleatoria dentro de un rango. Existe para no repetir el random."""
    time.sleep(random.uniform(*rango))


def calentar(page, url: str, timeout_ms: int = 30_000) -> bool:
    """Visita una home antes de pedir paginas internas, y hace scroll.

    Devuelve True si cargo. No levanta: que falle el calentamiento no es motivo
    para abortar el lote.
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        pausa((2.5, 4.5))
        page.mouse.move(400 + random.randint(-50, 50), 300 + random.randint(-30, 30))
        for y in (300, 600, 0):
            page.evaluate("window.scrollTo(0, %d)" % y)
            pausa((0.6, 1.6))
        return True
    except Exception as exc:  # noqa: BLE001 - el calentamiento nunca es fatal
        logger.debug("Calentamiento de %s fallo (no fatal): %s", url, exc)
        return False
