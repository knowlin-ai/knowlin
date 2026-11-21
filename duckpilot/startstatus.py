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

Seit 0.49.1 (Maintainer: „das In-App-Update führt dazu, dass er sich nicht neu verbinden kann“ – der Aufbau stand nach
dem Update 100 s auf „Körper, Stimme und Gedächtnis werden aufgebaut“): Ein Beobachter schaut alle zwei Sekunden, in
welchem Teil der Start gerade steckt („gerade: Stimme“), und schreibt bei langen Starts die Stelle ins Protokoll. Nach
30 s sagt die Seite, dass der erste Start nach einem Update dauern kann und man nicht neu starten soll.
"""

from __future__ import annotations

import html
import json
import logging
import os
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
        self.teil = ""
        self._beobachten = False

    def stand(self) -> dict:
        # "app": ein zweiter Doppelklick erkennt das startende Knowlin und öffnet nur ein Fenster dazu
        return {"app": "duckpilot", "startet": True, "version_neu": self.version, "schritt": self.schritt,
                "teil": self.teil, "seit_s": round(time.monotonic() - self.t0, 1)}

    def setzen(self, schritt: str) -> None:
        self.schritt = schritt

    def beobachten(self, faden: int | None = None, takt_s: float = 2.0, protokoll_s: float = 15.0) -> None:
        """Wo steckt der Start gerade? Schaut in den Startfaden (Standard: Hauptfaden) und setzt `teil`; was länger
        als `protokoll_s` dauert, kommt mit Datei und Zeile ins Protokoll – damit ein langsamer Start sich finden lässt."""
        faden = faden if faden is not None else threading.main_thread().ident
        self._beobachten = True

        def schauen() -> None:
            naechstes = protokoll_s
            while self._beobachten:
                time.sleep(takt_s)
                stelle = startstelle(sys._current_frames().get(faden))
                if stelle is None:
                    continue
                self.teil = teil_von(stelle[0])
                seit = time.monotonic() - self.t0
                if seit >= naechstes:
                    naechstes = seit + protokoll_s
                    log.info("Start nach %.0f s noch bei „%s“: %s:%s in %s", seit, self.schritt, *stelle)

        threading.Thread(target=schauen, name="startbeobachter", daemon=True).start()

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
        self._beobachten = False
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


# Teile des Programms, wie man sie im Fenster nennt (erster Ordner unter duckpilot/ bzw. Dateiname)
TEILE = (("voice", "Stimme"), ("speech", "Stimme"), ("physics", "Physik"), ("acrobatics", "Physik"),
         ("kollision", "Physik"), ("memory", "Gedächtnis"), ("erfahrung", "Gedächtnis"), ("brain", "Denken"),
         ("backends", "Körper"), ("koerper", "Körper"), ("modell", "Körper"), ("haus", "Smart Home"),
         ("alltag", "Alltag"), ("kalender", "Alltag"), ("skills", "Tricks"), ("hub", "Tricks"), ("motion", "Bewegung"))


def startstelle(frame) -> tuple[str, int, str] | None:
    """Tiefster Rahmen im duckpilot-Paket (Datei relativ zum Paket, Zeile, Funktion); sonst der tiefste überhaupt."""
    paket = os.path.dirname(os.path.abspath(__file__))
    tiefster = None
    eigener = None
    while frame is not None:
        datei = frame.f_code.co_filename
        if tiefster is None:
            tiefster = (os.path.basename(datei), frame.f_lineno, frame.f_code.co_name)
        if eigener is None and os.path.abspath(datei).startswith(paket):
            eigener = (os.path.relpath(datei, paket).replace(os.sep, "/"), frame.f_lineno, frame.f_code.co_name)
        frame = frame.f_back
    return eigener or tiefster


def teil_von(datei: str) -> str:
    teile = datei.replace("\\", "/").lower().split("/")
    for schluessel, name in TEILE:
        if any(t == schluessel or t.startswith(schluessel) for t in teile):
            return name
    return "Programmteile"


SEITE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Knowlin startet …</title>
<style>body{{margin:0;display:grid;place-items:center;min-height:100vh;background:#161616;color:#f4f4f4;
font:16px/1.5 system-ui,sans-serif;text-align:center;padding:16px}}p{{color:#c6c6c6;margin:.25rem 0}}
.bar{{height:4px;width:min(20rem,80vw);margin:1.5rem auto 0;background:#393939;border-radius:2px;overflow:hidden}}
.bar i{{display:block;height:100%;width:30%;background:#f1c21b;animation:l 1.6s ease-in-out infinite}}
@keyframes l{{from{{transform:translateX(-100%)}}to{{transform:translateX(340%)}}}}
@media (prefers-reduced-motion:reduce){{.bar i{{animation:none;width:100%;opacity:.5}}}}</style></head>
<body><main><h1>Knowlin startet …</h1><p id="schritt">{schritt}</p><p id="zeit"></p>
<p id="geduld" hidden>Der erste Start nach einem Update dauert manchmal zwei, drei Minuten – Windows prüft die neuen
Dateien. Bitte nicht neu starten, das Fenster lädt sich von selbst.</p>
<div class="bar" role="progressbar" aria-label="Knowlin startet"><i></i></div></main>
<script>
// Kein Neuladen per Meta-Refresh: In der kurzen Lücke, bis der eigentliche Server den Port übernimmt, zeigte der Browser
// sonst seine Fehlerseite und bliebe dort. Stattdessen nachfragen und erst neu laden, wenn Knowlin wirklich bereit ist.
async function frag() {{
  try {{
    const p = await (await fetch('/api/ping', {{ cache: 'no-store' }})).json();
    if (p.version) {{ location.reload(); return; }}
    if (p.schritt) document.getElementById('schritt').textContent = p.schritt;
    if (p.seit_s != null) document.getElementById('zeit').textContent = (p.teil ? 'gerade: ' + p.teil + ' · ' : '')
      + 'seit ' + Math.round(p.seit_s) + ' s';
    document.getElementById('geduld').hidden = !(p.seit_s > 30);
  }} catch (e) {{ /* kurz nicht erreichbar – gleich noch einmal */ }}
  setTimeout(frag, 1000);
}}
setTimeout(frag, 1000);
</script></body></html>"""
