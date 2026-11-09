"""Knowlin Link: zeigt, wie Reachy Mini mit Knowlin verbunden wird, und nennt die Adresse (auch als /api/knowlin).

Die App bewegt den Roboter nicht. Knowlin steuert Reachy über Pollens Daemon (HTTP, Port 8000) und hält laufende Apps
an, sobald es übernimmt – deshalb darf hier nichts um die Motoren konkurrieren.
"""

from __future__ import annotations

import socket
import threading
import time

from reachy_mini import ReachyMini, ReachyMiniApp

from . import __version__


def adresse() -> str:
    """Die Adresse, die man in Knowlin einträgt (Wireless: reachy-mini.local, Lite: localhost)."""
    name = socket.gethostname() or "reachy-mini"
    return "http://localhost:8000" if name in ("localhost",) else f"http://{name}.local:8000"


class KnowlinLink(ReachyMiniApp):
    custom_app_url: str | None = "http://0.0.0.0:8042"

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        gestartet = time.time()

        @self.settings_app.get("/api/knowlin")
        def knowlin_status() -> dict:
            """Ob die App läuft und welche Adresse in Knowlin einzutragen ist (für die Seite und spätere Abfragen)."""
            return {"app": "knowlin_link", "version": __version__, "daemon": adresse(),
                    "laeuft_seit_s": round(time.time() - gestartet)}

        while not stop_event.is_set():
            time.sleep(0.2)


if __name__ == "__main__":
    app = KnowlinLink()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
