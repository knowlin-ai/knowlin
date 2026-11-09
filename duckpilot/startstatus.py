"""Knowlin meldet sich beim Start sofort (seit 0.38.38).

Hinweis nach dem Update auf 0.38.37: „man sieht immer nicht, was gerade passiert oder ob es hängt“. Der erste
Start nach einem Update dauerte bei ihm zwei Minuten, ein normaler Start gut eine halbe Minute – und so lange war das
Fenster leer oder wartete still. Jetzt belegt das startende Knowlin (Programmfenster) den Port sofort mit einem kleinen
Statusdienst:

* `GET /api/ping` → `{"app": "duckpilot", "startet": true, "version_neu": "…", "schritt": "…", "seit_s": …}` – ohne
  `version`, damit ein offenes Fenster nicht zu früh neu lädt. Das Fenster zeigt den Schritt live an.
* Jede andere Adresse bekommt die Seite „Knowlin startet …“ mit dem Schritt; sie fragt jede Sekunde nach und lädt
  neu, sobald Knowlin bereit ist.

Kurz bevor der eigentliche Server startet, gibt der Statusdienst den Port wieder frei. Nur lesend, dieselbe Adresse wie
der Server, keine Daten über dich.
"""

from __future__ import annotations

import html
import json
import logging
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)


class _Dienst(ThreadingHTTPServer):
    # Unter Windows hieße SO_REUSEADDR: ein zweiter Dienst dürfte sich auf einen belegten Port setzen – dort aus.
    # Unter Linux/macOS an, wie bei uvicorn: sonst blockieren abgeschlossene Verbindungen (TIME_WAIT) den Port kurz.
    allow_reuse_address = sys.platform != "win32"
    daemon_threads = True


class StartStatus:
    def __init__(self, version: str) -> None:
        self.version = version
        self.schritt = "Programm wird geladen"
        self.t0 = time.monotonic()
        self._server: _Dienst | None = None

    def stand(self) -> dict:
        # "app": ein zweiter Doppelklick erkennt das startende Knowlin und öffnet nur ein Fenster dazu
        return {"app": "duckpilot", "startet": True, "version_neu": self.version, "schritt": self.schritt,
                "seit_s": round(time.monotonic() - self.t0, 1)}

    def setzen(self, schritt: str) -> None:
        self.schritt = schritt

    def starten(self, host: str, port: int) -> bool:
        """Port belegen und antworten; False, wenn der Port (noch) nicht frei ist – dann ohne Statusdienst."""
        status = self

        class Antwort(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 – Name von http.server vorgegeben
                if self.path.split("?")[0] == "/api/ping":
                    body = json.dumps(status.stand(), ensure_ascii=False).encode()
                    typ = "application/json"
                else:
                    body = SEITE.format(schritt=html.escape(status.schritt)).encode()
                    typ = "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", typ)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args) -> None:   # leise – sonst landet jede Anfrage im Protokoll
                pass

        try:
            self._server = _Dienst((host, port), Antwort)
        except OSError as exc:
            log.info("Startstatus: Port %s nicht frei (%s)", port, exc)
            return False
        threading.Thread(target=self._server.serve_forever, name="startstatus", daemon=True).start()
        return True

    def beenden(self) -> None:
        """Port freigeben – kurz bevor der eigentliche Server ihn braucht."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


SEITE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Knowlin startet …</title>
<style>body{{margin:0;display:grid;place-items:center;min-height:100vh;background:#161616;color:#f4f4f4;
font:16px/1.5 system-ui,sans-serif;text-align:center;padding:16px}}p{{color:#c6c6c6;margin:.25rem 0}}
.bar{{height:4px;width:min(20rem,80vw);margin:1.5rem auto 0;background:#393939;border-radius:2px;overflow:hidden}}
.bar i{{display:block;height:100%;width:30%;background:#f1c21b;animation:l 1.6s ease-in-out infinite}}
@keyframes l{{from{{transform:translateX(-100%)}}to{{transform:translateX(340%)}}}}
@media (prefers-reduced-motion:reduce){{.bar i{{animation:none;width:100%;opacity:.5}}}}</style></head>
<body><main><h1>Knowlin startet …</h1><p id="schritt">{schritt}</p><p id="zeit"></p>
<div class="bar" role="progressbar" aria-label="Knowlin startet"><i></i></div></main>
<script>
// Kein Neuladen per Meta-Refresh: In der kurzen Lücke, bis der eigentliche Server den Port übernimmt, zeigte der Browser
// sonst seine Fehlerseite und bliebe dort. Stattdessen nachfragen und erst neu laden, wenn Knowlin wirklich bereit ist.
async function frag() {{
  try {{
    const p = await (await fetch('/api/ping', {{ cache: 'no-store' }})).json();
    if (p.version) {{ location.reload(); return; }}
    if (p.schritt) document.getElementById('schritt').textContent = p.schritt;
    if (p.seit_s != null) document.getElementById('zeit').textContent = 'seit ' + Math.round(p.seit_s) + ' s';
  }} catch (e) {{ /* kurz nicht erreichbar – gleich noch einmal */ }}
  setTimeout(frag, 1000);
}}
setTimeout(frag, 1000);
</script></body></html>"""
