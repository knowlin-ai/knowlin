"""Selbst fahren im Arena-Rennen (seit 0.47): erst hinter die Startlinie, dann Tor für Tor bis ins Ziel.

Die Zeit misst nicht dieses Verhalten, sondern der Renndienst (`server/routes/rennen.py`) aus der gemeldeten Lage –
genauso, wie wenn jemand die Microduck mit dem Steuerkreuz durch die Tore lenkt. Hier wird nur gelenkt: auf das
nächste Tor zu, in Kurven langsamer (auf Rollen rollt sie sonst hinaus). Der Not-Aus bricht ab wie jedes Verhalten.
"""

from __future__ import annotations

import math

from ..api import Twist, wrap_angle
from ..rennen import STRECKE, Zeitfahren
from .engine import Behavior, Command

ANLAUF_M = 0.35            # so weit vor der Startlinie stellt sie sich auf
TEMPO = 0.25               # angefragte Geschwindigkeit (auf Rollen wird daraus mehr)
VORAUS_M = 0.5             # so weit vor einem Tor wird vor der Kurve gebremst


class Rennfahrt(Behavior):
    name = "Rennen"
    channels = ("base",)
    timeout = 150.0

    def __init__(self, fahrt: Zeitfahren) -> None:
        super().__init__()
        self.fahrt = fahrt
        x, y, r, _ = STRECKE[0]
        self.anlauf = (x - ANLAUF_M * math.cos(r), y - ANLAUF_M * math.sin(r), r)
        self.phase = "aufstellen"

    def tick(self, st, dt):
        if self.fahrt.fertig is not None:
            return self.finish(f"im Ziel nach {self.fahrt.fertig:.1f} s")
        if self.phase == "aufstellen":
            ax, ay, ar = self.anlauf
            dx, dy = ax - st.x, ay - st.y
            if math.hypot(dx, dy) > 0.06:
                return Command(twist=self._lenken(st, ax, ay, 0.18))
            err = wrap_angle(ar - st.yaw)
            if abs(err) > 0.12:
                return Command(twist=Twist(0.0, 0.0, max(-1.0, min(1.0, 2.0 * err))))
            self.phase = "fahren"
        tx, ty = self.fahrt.ziel_punkt()
        return Command(twist=self._lenken(st, tx, ty, self._tempo(st)))

    def _tempo(self, st) -> float:
        """Vor einer scharfen Kurve vom Gas – auf Rollen rollt sie sonst ins Sofa (sie bremst nur sanft)."""
        n = self.fahrt.naechstes
        gx, gy, r, _ = STRECKE[n]
        knick = abs(wrap_angle(STRECKE[(n + 1) % len(STRECKE)][2] - r))
        rollen = bool((getattr(st, "zubehoer", None) or {}).get("rollen"))
        if rollen and math.hypot(gx - st.x, gy - st.y) < VORAUS_M and knick > 0.6:
            return TEMPO * max(0.4, 1.0 - knick / 2.5)
        return TEMPO

    @staticmethod
    def _lenken(st, tx: float, ty: float, tempo: float) -> Twist:
        err = wrap_angle(math.atan2(ty - st.y, tx - st.x) - st.yaw)
        vyaw = max(-1.2, min(1.2, 2.4 * err))
        vx = 0.0 if abs(err) > 0.9 else tempo * max(0.25, math.cos(err) ** 2)
        return Twist(vx, 0.0, vyaw)

    def describe(self):
        if self.phase == "aufstellen":
            return "stellt sich an die Startlinie"
        return f"Rennen – nächstes Tor {self.fahrt.naechstes or 'Ziel'}"
