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

#: Perfil SEPARADO para la cuenta dedicada de Instagram.
#:
#: Separado a proposito, y no por orden: esta sesion acumula las cookies de una
#: cuenta de Instagram que se va a usar para leer ~1.200 perfiles seguidos. Si
#: comparte el directorio con la navegacion general, un bloqueo de Instagram se
#: lleva puesta la otra sesion, y peor: si alguien inicia sesion con su cuenta
#: personal en el perfil general, el lote sale a nombre de esa persona.
PERFIL_IG_DIR = OUTPUT_DIR / "browser_profile_instagram"
PERFIL_IG_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def crear_contexto(playwright_instance, headless: bool = True,
                   perfil_dir=None):
    """Contexto persistente de Chromium. Con patchright si esta instalado."""
    return playwright_instance.chromium.launch_persistent_context(
        user_data_dir=str(perfil_dir or PERFIL_DIR),
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
        logger.debug("Calentamiento de {} fallo (no fatal): {}", url, exc)
        return False


# ── Sesion de Instagram ───────────────────────────────────────────────────────

IG_HOME = "https://www.instagram.com/"

#: LAS cookies que significan "hay sesion". No son heuristicas: son el token de
#: autenticacion que emite Instagram al iniciar sesion.
#:
#: Antes esta comprobacion se hacia por selectores del DOM y **daba falso
#: positivo**: `a[href^='/explore/']` existe tambien en la pagina sin sesion,
#: asi que el lote arrancaba creyendo que estaba autenticado. Medido el
#: 2026-09-21: DOM decia "sesion detectada", y el endpoint JSON devolvia 401
#: con `require_login: true` y cero cookies de sesion.
#:
#: Es el mismo error que este proyecto viene corrigiendo en todas las capas: una
#: señal indirecta leida como si fuera el hecho.
COOKIES_DE_SESION = ("sessionid", "ds_user_id")

#: Señales de DOM. Sirven como evidencia SECUNDARIA para el mensaje de error,
#: nunca como prueba de que hay sesion.
_SELECTORES_DE_SESION_REAL = (
    "nav a[href='/direct/inbox/']",
    "svg[aria-label='New post']",
    "svg[aria-label='Crear']",
    "img[alt*='profile picture']",
)
_SELECTORES_SIN_SESION = (
    "input[name='username']",
    "form#loginForm",
    "a[href^='/accounts/login']",
)


def sesion_de_instagram_iniciada(page, *, ir_a_home: bool = True) -> tuple[bool, str]:
    """(hay sesion, evidencia). No levanta.

    **El veredicto lo dan las cookies, no el DOM.** `sessionid` y `ds_user_id`
    son el token que emite Instagram al autenticar; si no estan, no hay sesion,
    cualquiera sea lo que muestre la pagina.

    Se comprueba **antes** de empezar el lote. Sin sesion, Instagram sirve una
    version recortada del perfil: se leen la bio y los contadores del meta, pero
    no los posts ni los comentarios. Y eso no produce un error: produce un lote
    entero de perfiles que parecen no tener contenido.
    """
    try:
        if ir_a_home:
            page.goto(IG_HOME, wait_until="domcontentloaded", timeout=30_000)
            pausa((2.0, 3.5))

        try:
            cookies = page.context.cookies(IG_HOME)
        except Exception as exc:  # noqa: BLE001
            return False, "no pude leer las cookies del contexto: %s" % exc

        presentes = {c["name"] for c in cookies if (c.get("value") or "").strip()}
        faltan = [c for c in COOKIES_DE_SESION if c not in presentes]

        if faltan:
            dom = [s for s in _SELECTORES_DE_SESION_REAL if page.query_selector(s)]
            login = [s for s in _SELECTORES_SIN_SESION if page.query_selector(s)]
            return False, (
                "faltan las cookies de sesion %s. Hay %d cookies pero son "
                "anonimas (%s). %s%sSin `sessionid` no hay sesion, aunque la "
                "pagina se vea normal."
                % (faltan, len(cookies), ", ".join(sorted(presentes)) or "ninguna",
                   "Se ve el formulario de login. " if login else "",
                   "El DOM muestra %s, que en la pagina sin sesion tambien "
                   "aparece. " % dom if dom else "")
            )

        return True, (
            "cookies de sesion presentes (%s) sobre %d cookies"
            % (", ".join(COOKIES_DE_SESION), len(cookies))
        )
    except Exception as exc:  # noqa: BLE001
        return False, "no se pudo comprobar la sesion: %s" % exc


def confirmar_acceso_a_la_api(page) -> tuple[bool, str]:
    """Segunda comprobacion: el endpoint JSON responde de verdad?

    Las cookies pueden estar y la cuenta tener un desafio pendiente. Esto lo
    detecta pidiendo un perfil publico conocido antes de gastar el lote.
    """
    url = (IG_HOME + "api/v1/users/web_profile_info/?username=instagram")
    try:
        respuesta = page.request.get(url, headers={
            "X-IG-App-ID": "936619743392459",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": IG_HOME,
            "Accept": "*/*",
        }, timeout=30_000)
    except Exception as exc:  # noqa: BLE001
        return False, "la peticion al endpoint fallo: %s" % exc

    if respuesta.status != 200:
        cuerpo = ""
        try:
            cuerpo = respuesta.text()[:200].replace("\n", " ")
        except Exception:  # noqa: BLE001
            pass
        return False, (
            "el endpoint JSON devolvio HTTP %d. %s%s"
            % (respuesta.status, cuerpo,
               " · `require_login: true` significa que Instagram no reconoce la "
               "sesion." if "require_login" in cuerpo else "")
        )

    try:
        datos = respuesta.json()
    except Exception as exc:  # noqa: BLE001
        return False, "el endpoint respondio 200 pero no era JSON: %s" % exc

    usuario = ((datos or {}).get("data") or {}).get("user")
    if not usuario:
        return False, "el endpoint respondio 200 pero sin datos de usuario"

    bordes = ((usuario.get("edge_owner_to_timeline_media") or {}).get("edges") or [])
    return True, (
        "el endpoint responde: @%s con %d posts en la primera pagina"
        % (usuario.get("username"), len(bordes))
    )


def iniciar_sesion_instagram(playwright_instance, *, timeout_min: int = 10) -> bool:
    """Abre el navegador con ventana para que una PERSONA inicie sesion una vez.

    No automatiza el login, y es deliberado: automatizar el ingreso de
    credenciales significa guardarlas en algun lado, y la cuenta dedicada de
    Instagram es exactamente la credencial que no conviene tener en un archivo.

    La sesion queda en PERFIL_IG_DIR y se reutiliza en las corridas siguientes.

        python -m instagram.finder --iniciar-sesion
    """
    print("")
    print("=" * 70)
    print("INICIO DE SESION EN INSTAGRAM · una sola vez")
    print("=" * 70)
    print("")
    print("Se va a abrir una ventana de Chromium. Inicia sesion ahi con la")
    print("**cuenta dedicada** de Instagram.")
    print("")
    print("  NO la cuenta personal de nadie.")
    print("  NO la cuenta de la empresa.")
    print("")
    print("Motivo: leer ~1.200 perfiles seguidos puede terminar en un desafio")
    print("o en una suspension. Eso tiene que pasarle a una cuenta que exista")
    print("para esto, no a la cuenta con la que la division le habla a sus")
    print("realtors.")
    print("")
    print("La sesion queda guardada en:")
    print("  %s" % PERFIL_IG_DIR)
    print("")
    print("Cuando termines de iniciar sesion, cierra la ventana.")
    print("")

    contexto = crear_contexto(playwright_instance, headless=False,
                              perfil_dir=PERFIL_IG_DIR)
    page = contexto.new_page()
    try:
        page.goto(IG_HOME + "accounts/login/", wait_until="domcontentloaded",
                  timeout=60_000)
    except Exception as exc:  # noqa: BLE001
        logger.warning("no se pudo abrir la pagina de login: {}", exc)

    limite = time.time() + timeout_min * 60
    ok = False
    ultimo_aviso = 0.0
    while time.time() < limite:
        try:
            if page.is_closed():
                break
        except Exception:  # noqa: BLE001
            break
        hay, evidencia = sesion_de_instagram_iniciada(page, ir_a_home=False)
        if hay:
            ok = True
            print("")
            print("Cookies de sesion detectadas: %s" % evidencia)
            break
        if time.time() - ultimo_aviso > 20:
            ultimo_aviso = time.time()
            print("   esperando... (%s)" % evidencia[:90])
        time.sleep(3)

    if not ok:
        # La ventana pudo cerrarse despues de iniciar sesion; se re-comprueba.
        try:
            page2 = contexto.new_page()
            ok, evidencia = sesion_de_instagram_iniciada(page2)
            page = page2
            if ok:
                print("Cookies de sesion detectadas: %s" % evidencia)
            else:
                print("")
                print("NO hay sesion: %s" % evidencia)
        except Exception as exc:  # noqa: BLE001
            print("NO se pudo confirmar la sesion: %s" % exc)

    # Segunda comprobacion, la que de verdad importa: que el endpoint responda.
    # Las cookies pueden estar y la cuenta tener un desafio pendiente.
    if ok:
        try:
            api_ok, api_evidencia = confirmar_acceso_a_la_api(page)
            print("Endpoint JSON: %s" % api_evidencia)
            if not api_ok:
                print("")
                print("Las cookies estan pero el endpoint no responde. Suele ser")
                print("un desafio pendiente en la cuenta: abri Instagram a mano")
                print("con esa cuenta y resolvelo antes de correr el lote.")
                ok = False
        except Exception as exc:  # noqa: BLE001
            print("No se pudo comprobar el endpoint: %s" % exc)

    try:
        contexto.close()
    except Exception:  # noqa: BLE001
        pass

    print("")
    print("RESULTADO: %s" % ("sesion lista" if ok else "SIN sesion utilizable"))
    return ok
