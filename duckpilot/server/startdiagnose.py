"""Wenn das Fenster keine Verbindung bekommt (seit 0.38.66).

Fund (Bericht eines Nutzers, 19.11.): Nach dem Installieren blieb das Fenster bei „verbinde …“ stehen, alle Knöpfe tot,
keine „Ersten Schritte“ – und nirgends stand, warum. Die Seite selbst kam an, die laufende Verbindung (WebSocket) nie.
Hier liegt, was die Oberfläche dann zeigen kann, und was ins Protokoll gehört, damit sich die Ursache finden lässt:

* **Startfehler** – scheitert das Start-Paket für das Fenster (z. B. an alten Einstellungen), bleibt die Verbindung offen,
  die Oberfläche bekommt den Grund, und `/api/startdiagnose` liefert ihn auch ohne Verbindung.
* **Schleifenwächter** – ein eigener Faden schaut jede Sekunde, ob die Ereignisschleife des Servers noch antwortet. Hängt
  sie länger als `GRENZE` Sekunden (dann nimmt der Server keine Verbindung an), schreibt er einmal ins Protokoll, woran
  sie gerade hängt (Stapel des Schleifen-Fadens), und wenn sie wieder frei ist, wie lange es dauerte.

Ins Protokoll kommen nur Code-Stellen und Fehlermeldungen, keine Gespräche.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import traceback

log = logging.getLogger(__name__)

GRENZE = 5.0          # s ohne Antwort der Schleife, bis der Wächter meldet
TAKT = 1.0            # s zwischen zwei Nachfragen


class Startfehler:
    """Der letzte Fehler beim Start-Paket für ein Fenster (leer, solange alles gut ging)."""

    def __init__(self) -> None:
        self.text = ""
        self.zeit = 0.0
        self.ablehnung = ""          # warum der Server zuletzt ein Fenster abgewiesen hat (ohne Adressen von Personen)

    def abgelehnt(self, grund: str) -> None:
        self.ablehnung = grund[:200]
        log.warning("Verbindung abgewiesen: %s", self.ablehnung)

    def merken(self, exc: BaseException) -> str:
        self.text = f"{type(exc).__name__}: {exc}"[:400]
        self.zeit = time.time()
        return self.text

    def loeschen(self) -> None:
        self.text = ""
        self.ablehnung = ""

    def bericht(self, waechter: Schleifenwaechter | None) -> dict:
        return {"startfehler": self.text, "ablehnung": self.ablehnung,
                "haengt_seit": round(waechter.haengt_seit, 1) if waechter else 0.0}


class Schleifenwaechter:
    """Meldet im Protokoll, wenn die Ereignisschleife hängt – und woran (ohne sie selbst anzufassen)."""

    def __init__(self, loop: asyncio.AbstractEventLoop, grenze: float = GRENZE, takt: float = TAKT) -> None:
        self.loop = loop
        self.grenze = grenze
        self.takt = takt
        self._antwort = time.monotonic()
        self._schleifen_faden: int | None = None
        self._halt = threading.Event()
        self._faden: threading.Thread | None = None
        self.gemeldet = False
        self.laengste = 0.0

    def start(self) -> None:
        self._schleifen_faden = threading.get_ident()      # start() läuft in der Schleife selbst
        self._antwort = time.monotonic()
        self._faden = threading.Thread(target=self._laufen, name="schleifenwaechter", daemon=True)
        self._faden.start()

    def stop(self) -> None:
        self._halt.set()

    @property
    def haengt_seit(self) -> float:
        """Sekunden seit der letzten Antwort der Schleife (0, solange sie flott antwortet)."""
        s = time.monotonic() - self._antwort
        return s if s > self.grenze else 0.0

    def _melden(self) -> None:
        self._antwort = time.monotonic()

    def _laufen(self) -> None:
        while not self._halt.wait(self.takt):
            try:
                self.loop.call_soon_threadsafe(self._melden)
            except RuntimeError:                       # Schleife ist zu – der Server endet
                return
            stille = time.monotonic() - self._antwort
            if stille > self.grenze and not self.gemeldet:
                self.gemeldet = True
                log.warning("Knowlin hängt seit %.0f s – die Oberfläche bekommt keine Verbindung. Gerade läuft:\n%s",
                            stille, self.stapel())
            elif stille <= self.takt * 2 and self.gemeldet:
                self.gemeldet = False
                log.warning("Knowlin antwortet wieder (hing %.0f s).", self.laengste)
            if self.gemeldet:
                self.laengste = max(self.laengste, stille)

    def stapel(self) -> str:
        rahmen = sys._current_frames().get(self._schleifen_faden or -1)
        if rahmen is None:
            return "(Stapel nicht verfügbar)"
        return "".join(traceback.format_stack(rahmen)[-12:]).rstrip()
