"""Aufmerksamkeit suchen (seit 0.50): nach langer Stille kommt sie vorsichtig näher und schaut zu dir hoch.

Maintainer (Plan 0.50): „Wenn lange niemand mit ihr spricht, kommt sie vorsichtig näher und macht auf sich aufmerksam.“
Grenzen aus dem Wertekern (Nähe drängt nie): langsam (8 cm/s), bleibt mit Abstand stehen, spricht nicht – höchstens ein
leiser Laut, wenn Entenlaute an sind –, und nur einmal je langer Stille (die Laufzeit zählt). Nur im Simulator (wie jede
Ortsbewegung von selbst), nie in der Sperre nach dem Not-Aus (das prüft `eigenstaendig.sperre`).
"""

from __future__ import annotations

import math

from ..api import Head
from .behaviors import GoTo
from .engine import Command

SPEED = 0.08                 # m/s – vorsichtig
SCHAUEN_S = 6.0              # so lange schaut sie danach zu dir hoch
HOCH = Head(0.0, -0.32, 0.0, 0.12)     # Kopf hoch (Pitch − = nach oben), leicht schief gelegt


def haltepunkt(von: tuple[float, float], zu: tuple[float, float], abstand: float = 0.5) -> tuple[float, float]:
    """Punkt `abstand` m vor dem Ziel auf der Linie von ihr zu dir."""
    dx, dy = zu[0] - von[0], zu[1] - von[1]
    d = math.hypot(dx, dy)
    if d <= abstand or d == 0:
        return von
    k = (d - abstand) / d
    return von[0] + dx * k, von[1] + dy * k


class AufmerksamkeitSuchen(GoTo):
    name = "aufmerksamkeit"
    channels = ("base", "head")

    def __init__(self, ziel: tuple[float, float], laut: bool = True) -> None:
        super().__init__(ziel[0], ziel[1], speed=SPEED, label="dir")
        self.laut = laut
        self.phase = "gehen"
        self._schauen_ab = 0.0
        self.timeout = 90.0

    def tick(self, st, dt):
        if self.phase == "gehen":
            cmd = super().tick(st, dt)
            if not self.done:
                return cmd
            if getattr(self, "failed", False):
                return None                               # kam nicht hin – fertig, ohne Laut
            self.done, self.phase, self._schauen_ab = False, "schauen", self.elapsed
            if self.laut and self.engine is not None:
                try:
                    self.engine.fire(self.engine.backend.sound("coo"))
                except Exception:  # noqa: BLE001 – ein fehlender Laut ist kein Fehler
                    pass
        if self.elapsed - self._schauen_ab >= SCHAUEN_S:
            return self.finish("schaut zu dir hoch")
        return Command(head=HOCH)

    def describe(self):
        return "kommt vorsichtig zu dir" if self.phase == "gehen" else "schaut zu dir hoch"
