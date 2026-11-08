"""Raumwissen der Laufzeit (seit 0.37): Sichtungen („Wo zuletzt gesehen?“) und die Karte aus dem Kartierungsmodus.

Die Laufzeit ruft `tick()` fünfmal pro Sekunde mit dem aktuellen Zustand auf. Sichtungen laufen immer mit (nur Dinge
und Möbel), die Karte nur während eines Kartierungslaufs. Beides wird je Körper gespeichert – Simulator, Physik und
echte Wohnung haben verschiedene Koordinaten – unter `<daten>/raum/`. Nichts davon verlässt den PC.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from ..motion.karte import Karte
from ..sichtungen import Sichtungen

log = logging.getLogger(__name__)
SPEICHERN_S = 15.0


class Raum:
    def __init__(self, root: Path, koerper: str) -> None:
        self.root = Path(root) / "raum"
        self.koerper = koerper
        self.sichtungen = Sichtungen(self.root / f"sichtungen-{koerper}.json")
        self.karte = Karte.laden(self.root / f"karte-{koerper}.json")
        self._lauf: Any = None            # laufendes Kartier-Verhalten
        self._gespeichert = time.monotonic()
        self.geaendert_karte = False
        self.punkte_bisher = 0

    @property
    def kartiert(self) -> bool:
        return self._lauf is not None

    def tick(self, st: Any) -> None:
        self.sichtungen.beobachte(st)
        self._pose = (round(st.x, 3), round(st.y, 3), round(st.yaw, 3))   # für die 2D-Vorschau (seit 0.37.11)
        if self._lauf is not None:
            if self._lauf.done:
                self.kartieren_stopp()
            elif st.connected and not st.fallen and not getattr(st, "picked_up", False):
                self.karte.eintragen(st.x, st.y, st.perception.points)
                self.geaendert_karte = True
        if time.monotonic() - self._gespeichert > SPEICHERN_S:
            self.speichern()

    def kartieren(self, verhalten: Any) -> None:
        self._lauf = verhalten

    def kartieren_stopp(self) -> dict[str, Any]:
        lauf, self._lauf = self._lauf, None
        if lauf is not None and not lauf.done and lauf.engine is not None and lauf.engine.current is lauf:
            lauf.engine.cancel_current("Kartieren beendet")
        self.speichern()
        return self.status()

    def leeren(self) -> None:
        self.karte.leeren()
        self.geaendert_karte = True
        self.speichern()

    def speichern(self) -> None:
        self._gespeichert = time.monotonic()
        try:
            self.sichtungen.speichern()
            if self.geaendert_karte:
                self.karte.speichern(self.root / f"karte-{self.koerper}.json")
                self.geaendert_karte = False
        except OSError:
            log.warning("Raumwissen konnte nicht gespeichert werden", exc_info=True)

    def status(self) -> dict[str, Any]:
        return {"kartiert": self.kartiert, "koerper": self.koerper, "flaeche_m2": self.karte.flaeche_m2(),
                "messungen": self.karte.messungen, "dinge": len(self.sichtungen.liste())}

    def anzeige(self) -> dict[str, Any]:
        """Für die Oberfläche: Karte (Zellen) und gemerkte Dinge."""
        pose = getattr(self, "_pose", None)
        ente = {"x": pose[0], "y": pose[1], "yaw": pose[2]} if pose else None
        return {**self.status(), "karte": self.karte.to_dict(), "sichtungen": self.sichtungen.fuer_anzeige(),
                "ente": ente}
