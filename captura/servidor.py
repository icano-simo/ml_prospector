"""La pantalla de captura. Un formulario local, sin deploy.

Por que local y no en Vercel
----------------------------
Escribe con la conexion directa a Postgres, o sea con credenciales que no pueden
vivir en un navegador. Y `pacs` no esta expuesto en PostgREST a proposito --
cambiar `pgrst.db_schemas` para esto seria riesgo a cambio de nada.

Local corre hoy. Un deploy corre cuando alguien lo despliegue, y la prueba de
Model Match vence el 1 de octubre.

Uso
---
    python -m captura.servidor
    -> http://127.0.0.1:8733

Dos pasos, y el segundo es el que evita el error que no se puede deshacer:

  1 · se pega el Overview. La pantalla extrae los condados EN ORDEN y los
      muestra.
  2 · la pantalla genera una caja por geografia, YA ETIQUETADA. La persona no
      escribe la etiqueta: la asigna el orden.

Asi el bloque de Alameda no se puede guardar como Solano, que es el error que
contamina la biblioteca sin que se note.
"""
from __future__ import annotations

import html
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from captura.almacen import geografias_capturadas, guardar
from captura.protocolo import ProtocoloInvalido, armar_captura, condados_del_overview

PUERTO = 8733

# Tokens de la division, no una paleta nueva.
CSS = """
:root{
  --fondo:#0f1115; --papel:#171a21; --borde:#262b36; --texto:#e8eaed;
  --tenue:#9aa3b2; --acento:#c8102e; --ok:#2e7d32; --alerta:#b26a00;
}
@media (prefers-color-scheme: light){
  :root:not([data-theme="dark"]){
    --fondo:#f6f7f9; --papel:#fff; --borde:#dfe3ea; --texto:#1b1f27;
    --tenue:#5b6472;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--fondo);color:var(--texto);
  font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:20px;margin:0 0 4px}
h2{font-size:15px;margin:28px 0 10px;color:var(--tenue);
  text-transform:uppercase;letter-spacing:.06em}
.sub{color:var(--tenue);margin:0 0 20px}
.tarjeta{background:var(--papel);border:1px solid var(--borde);
  border-radius:10px;padding:16px;margin-bottom:14px}
label{display:block;font-weight:600;margin-bottom:6px}
.pista{color:var(--tenue);font-weight:400;font-size:13px}
textarea{width:100%;min-height:150px;background:var(--fondo);
  color:var(--texto);border:1px solid var(--borde);border-radius:8px;
  padding:10px;font:13px/1.45 ui-monospace,Consolas,monospace;resize:vertical}
input[type=text]{width:100%;background:var(--fondo);color:var(--texto);
  border:1px solid var(--borde);border-radius:8px;padding:9px 10px;font:inherit}
button{background:var(--acento);color:#fff;border:0;border-radius:8px;
  padding:11px 18px;font:inherit;font-weight:600;cursor:pointer}
button.sec{background:transparent;color:var(--texto);
  border:1px solid var(--borde)}
.fila{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.error{border-left:4px solid var(--acento);background:rgba(200,16,46,.08);
  padding:12px 14px;border-radius:8px;white-space:pre-wrap;margin-bottom:14px}
.ok{border-left:4px solid var(--ok);background:rgba(46,125,50,.1);
  padding:12px 14px;border-radius:8px;margin-bottom:14px}
.aviso{border-left:4px solid var(--alerta);background:rgba(178,106,0,.1);
  padding:10px 12px;border-radius:8px;margin:8px 0;font-size:14px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--borde)}
th{color:var(--tenue);font-weight:600;font-size:12px;text-transform:uppercase}
.chip{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;
  background:var(--borde);color:var(--texto);margin:2px 4px 2px 0}
.chip.est{background:rgba(200,16,46,.18)}
code{background:var(--fondo);padding:1px 5px;border-radius:4px;font-size:12px}
"""

PROTOCOLO = """\
1 · Overview, con <b>View Counties</b> activado
2 · Market Signals con Set Location en el <b>estado</b>
3 · Market Signals por <b>cada condado</b>, en el orden de la tabla del Overview
4 · Originators, con filtro <b>Buyer</b>
5 · Lenders"""


def _pagina(cuerpo: str, titulo: str = "Captura · Model Match") -> bytes:
    return ("""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title><style>%s</style></head><body><div class="wrap">%s</div>
</body></html>""" % (html.escape(titulo), CSS, cuerpo)).encode("utf-8")


def _panel_cobertura() -> str:
    try:
        filas = geografias_capturadas()
    except Exception as exc:  # noqa: BLE001
        return ('<div class="aviso">No pude leer lo ya capturado: %s</div>'
                % html.escape(str(exc)[:200]))
    if not filas:
        return ('<div class="tarjeta"><h2 style="margin-top:0">Ya capturado</h2>'
                '<p class="sub" style="margin:0">Todavía nada. Este es el '
                'primero.</p></div>')
    chips = "".join(
        '<span class="chip%s">%s%s</span>'
        % (" est" if not f["condado"] else "",
           html.escape(f["estado"] or "?"),
           " · " + html.escape(f["condado"]) if f["condado"] else "")
        for f in filas
    )
    return ('<div class="tarjeta"><h2 style="margin-top:0">Ya capturado '
            '<span class="pista">(%d geografías)</span></h2>%s</div>'
            % (len(filas), chips))


def _paso1(error: str = "", datos: dict | None = None) -> bytes:
    d = datos or {}
    return _pagina("""
<h1>Captura de Model Match</h1>
<p class="sub">Paso 1 de 2 · pegar el Overview para leer los condados</p>
%s
%s
<form method="post" action="/paso2">
  <div class="tarjeta">
    <label>Realtor <span class="pista">como aparece en el perfil</span></label>
    <input type="text" name="realtor" value="%s" placeholder="Armando Ochoa">
  </div>
  <div class="tarjeta">
    <label>Estado <span class="pista">dos letras</span></label>
    <input type="text" name="estado" value="%s" placeholder="CA" maxlength="2">
  </div>
  <div class="tarjeta">
    <label>MMI Agent ID <span class="pista">obligatorio · está en el perfil de
    Model Match</span></label>
    <input type="text" name="mmi_agent_id" value="%s" placeholder="p. ej. 1234567">
    <p class="pista" style="margin:8px 0 0">Sin una llave esta captura no se
    puede pegar a ningún realtor después. El nombre no es llave: hay dos ANDREA
    SAAVEDRA en el libro.</p>
  </div>
  <div class="tarjeta">
    <label>Overview <span class="pista">con View Counties activado</span></label>
    <textarea name="overview" placeholder="Ctrl+A, Ctrl+C en la pestaña Overview y pegar acá">%s</textarea>
  </div>
  <div class="fila"><button type="submit">Leer los condados</button></div>
</form>
<div class="tarjeta" style="margin-top:22px">
  <h2 style="margin-top:0">El orden de captura</h2>
  <p class="sub" style="margin:0">%s</p>
</div>
""" % (('<div class="error">%s</div>' % html.escape(error)) if error else "",
       _panel_cobertura(),
       html.escape(d.get("realtor", "")), html.escape(d.get("estado", "")),
       html.escape(d.get("mmi_agent_id", "")),
       html.escape(d.get("overview", "")), PROTOCOLO))


def _paso2(realtor: str, estado: str, overview: str, error: str = "",
           mmi_agent_id: str = "") -> bytes:
    condados = [n for n, _ in condados_del_overview(overview)]
    unidades = {n: u for n, u in condados_del_overview(overview)}

    if not condados:
        return _paso1(
            "El Overview no trajo tabla de condados. Revisá que 'View "
            "Counties' estuviera activado antes de copiar.",
            {"realtor": realtor, "estado": estado, "overview": overview,
             "mmi_agent_id": mmi_agent_id})

    cajas = ['<div class="tarjeta"><label>Market Signals · <b>%s</b> '
             '<span class="pista">Set Location en el estado</span></label>'
             '<textarea name="ms_0"></textarea></div>'
             % html.escape(estado or "el estado")]
    for i, c in enumerate(condados, start=1):
        cajas.append(
            '<div class="tarjeta"><label>Market Signals · <b>%s</b> '
            '<span class="pista">%d unidades · bloque %d</span></label>'
            '<textarea name="ms_%d"></textarea></div>'
            % (html.escape(c), unidades.get(c, 0), i + 1, i))

    return _pagina("""
<h1>%s</h1>
<p class="sub">Paso 2 de 2 · %d condados leídos, en este orden</p>
%s
<div class="tarjeta">
  <h2 style="margin-top:0">Condados del Overview</h2>
  <table><tr><th>#</th><th>Condado</th><th>Unidades</th></tr>%s</table>
  <p class="pista" style="margin:10px 0 0">Las etiquetas las asigna este orden.
  No hay que escribirlas: así el bloque de un condado no se puede guardar como
  el de otro.</p>
</div>
<form method="post" action="/guardar">
  <input type="hidden" name="realtor" value="%s">
  <input type="hidden" name="estado" value="%s">
  <input type="hidden" name="overview" value="%s">
  <input type="hidden" name="mmi_agent_id" value="%s">
  <h2>Market Signals · %d bloques</h2>
  %s
  <h2>Perfil</h2>
  <div class="tarjeta">
    <label>Originators <span class="pista">con filtro Buyer</span></label>
    <textarea name="originators"></textarea>
  </div>
  <div class="tarjeta">
    <label>Lenders</label><textarea name="lenders"></textarea>
  </div>
  <div class="fila">
    <button type="submit">Guardar</button>
    <a href="/"><button type="button" class="sec">Volver</button></a>
  </div>
</form>
""" % (html.escape(realtor or "Captura"), len(condados),
       ('<div class="error">%s</div>' % html.escape(error)) if error else "",
       "".join("<tr><td>%d</td><td>%s</td><td>%s</td></tr>"
               % (i + 1, html.escape(c), unidades.get(c, 0))
               for i, c in enumerate(condados)),
       html.escape(realtor), html.escape(estado), html.escape(overview),
       html.escape(mmi_agent_id),
       len(condados) + 1, "".join(cajas)))


def _guardado(res: dict) -> bytes:
    avisos = "".join('<div class="aviso">%s</div>' % html.escape(a)
                     for a in res.get("advertencias", []))
    return _pagina("""
<h1>Guardado</h1>
<div class="ok"><b>%d bloques</b> · lote <code>%s</code></div>
%s
<div class="tarjeta">
  <h2 style="margin-top:0">Qué se guardó</h2>
  <p class="sub" style="margin:0 0 8px">El texto crudo íntegro, con su etiqueta
  geográfica, en <code>pacs.capturas_modelmatch</code>.</p>
  <p class="pista" style="margin:0">La biblioteca <code>pacs.mercados</code> se
  puebla cuando corra el parser. Una fila ahí sin métricas haría que el motor de
  contrastes crea que ese mercado existe.</p>
</div>
%s
<div class="fila"><a href="/"><button>Capturar otro</button></a></div>
""" % (res["bloques"], html.escape(res["upload_batch_id"]), avisos,
       _panel_cobertura()))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, formato, *args):  # noqa: A003
        pass

    def _responder(self, cuerpo: bytes, codigo: int = 200) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _form(self) -> dict:
        largo = int(self.headers.get("Content-Length") or 0)
        crudo = self.rfile.read(largo).decode("utf-8")
        d = urllib.parse.parse_qs(crudo, keep_blank_values=True)
        return {k: v[0] for k, v in d.items()}

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._responder(_paso1())
        else:
            self._responder(_pagina("<h1>404</h1>"), 404)

    def do_POST(self):  # noqa: N802
        f = self._form()
        if self.path == "/paso2":
            self._responder(_paso2(f.get("realtor", ""), f.get("estado", ""),
                                   f.get("overview", ""), "",
                                   f.get("mmi_agent_id", "")))
            return
        if self.path != "/guardar":
            self._responder(_pagina("<h1>404</h1>"), 404)
            return

        overview = f.get("overview", "")
        ms = []
        i = 0
        while "ms_%d" % i in f:
            ms.append(f["ms_%d" % i])
            i += 1

        vacios = [n for n, t in enumerate(ms) if not t.strip()]
        if vacios:
            self._responder(_paso2(
                f.get("realtor", ""), f.get("estado", ""), overview,
                "Faltan %d bloques de Market Signals por pegar (posiciones %s). "
                "No se guarda nada: un bloque vacío desalinea las etiquetas de "
                "todos los que vienen después."
                % (len(vacios), ", ".join(str(v + 1) for v in vacios)),
                f.get("mmi_agent_id", "")))
            return

        try:
            cap = armar_captura(
                overview=overview, market_signals=ms,
                originators=f.get("originators") or None,
                lenders=f.get("lenders") or None,
                realtor=f.get("realtor") or None,
                estado=(f.get("estado") or "").upper() or None,
                mmi_agent_id=(f.get("mmi_agent_id") or "").strip() or None,
            )
            res = guardar(cap, archivo="pantalla de captura")
            res["advertencias"] = cap.advertencias
        except ProtocoloInvalido as exc:
            self._responder(_paso2(f.get("realtor", ""), f.get("estado", ""),
                                   overview, str(exc),
                                   f.get("mmi_agent_id", "")))
            return
        except Exception as exc:  # noqa: BLE001
            self._responder(_paso2(f.get("realtor", ""), f.get("estado", ""),
                                   overview,
                                   "No se guardó nada. %s" % str(exc)[:400],
                                   f.get("mmi_agent_id", "")))
            return

        self._responder(_guardado(res))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    srv = HTTPServer(("127.0.0.1", PUERTO), Handler)
    print("Captura de Model Match")
    print("  http://127.0.0.1:%d" % PUERTO)
    print("")
    print("Ctrl+C para parar.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("parado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
