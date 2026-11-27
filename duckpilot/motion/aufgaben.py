"""Selbstständige Aufgaben (seit 0.55): Linie folgen und Farbe folgen – wie in Hiwonders Studio für die WonderDuck.

Beide laufen mit allem, was Beine und eine Kamera hat (Microduck, WonderDuck, Open Duck): Die Dinge kommen aus der
Wahrnehmung – im Simulator gerechnet (`linie.sicht`, Farbe der Dinge), am echten Roboter aus dem Kamerabild
(`farbsicht.AufgabenSicht`). Der Hindernis-Reflex der Engine bleibt an, der Not-Aus beendet sofort.

* `LinieFolgen` hält die Linie in der Bildmitte: zielt auf den Punkt der Linie voraus und richtet sich ein wenig nach
  ihrer Richtung aus, langsamer in Kurven. Ist die Linie weg, bleibt sie stehen, dreht sich langsam zur Seite, wo sie zuletzt war, und hört
  nach `WEG_S` Sekunden ohne Linie auf.
* `FarbeFolgen` läuft dem nächsten Ding der gewählten Farbe nach und bleibt `ABSTAND_M` davor stehen (Hiwonders
  „Object tracking“ mit Zielfläche); Kopf schaut darauf. Ist die Farbe weg, sucht sie mit dem Kopf, dann im Kreis.
"""

from __future__ import annotations

import math
from typing import Any

from ..api import DuckState, Head, Twist, clamp, wrap_angle
from .engine import Behavior, Command

FARBEN = ("rot", "gelb", "gruen", "blau")


class LinieFolgen(Behavior):
    name = "linie folgen"
    channels = ("base", "head")
    K_ZIELEN = 2.2            # rad/s je rad Richtung zum Punkt der Linie voraus
    K_WINKEL = 0.5            # rad/s je rad Winkel der Linie
    WEG_S = 8.0

    def __init__(self, seconds: float = 120.0, tempo: float = 0.1) -> None:
        super().__init__()
        self.duration = max(5.0, min(600.0, seconds))
        self.timeout = self.duration + 2
        self.tempo = max(0.05, min(0.16, abs(tempo)))
        self.weg_t = 0.0
        self.gesehen = False
        self.seite = 1.0
        self.strecke = 0.0
        self._letzt: tuple[float, float] | None = None

    @staticmethod
    def _linie(st: DuckState) -> dict[str, Any] | None:
        return next((o for o in st.perception.objects if o.get("art") == "linie"), None)

    def tick(self, st, dt):
        if self._letzt is not None:
            self.strecke += math.hypot(st.x - self._letzt[0], st.y - self._letzt[1])
        self._letzt = (st.x, st.y)
        if self.elapsed >= self.duration:
            return self.finish(f"Linie gefolgt ({self.strecke:.1f} m)".replace(".", ","))
        blick = Head(0.0, clamp(0.55, "head_pitch"), 0.0, 0.0)          # schräg nach unten auf den Boden voraus
        lin = self._linie(st)
        if lin is None:
            self.weg_t += dt
            if self.weg_t > self.WEG_S:
                return self.finish("Linie verloren" if self.gesehen else "keine Linie gesehen")
            return Command(twist=Twist(0.0, 0.0, 0.5 * self.seite), head=blick)
        self.weg_t = 0.0
        self.gesehen = True
        versatz, winkel = float(lin["versatz_m"]), math.radians(float(lin["winkel_grad"]))
        voraus = max(0.08, float(lin.get("entfernung_m", 0.2)))
        self.seite = 1.0 if (versatz + 0.1 * winkel) >= 0 else -1.0
        # auf den Punkt der Linie voraus zielen (wie „pure pursuit“), dazu ein wenig nach ihrer Richtung ausrichten
        zielen = math.atan2(versatz, voraus)
        vyaw = max(-1.0, min(1.0, self.K_ZIELEN * zielen + self.K_WINKEL * winkel))
        vx = self.tempo * max(0.3, 1.0 - 1.1 * abs(zielen) - 0.6 * abs(winkel))
        return Command(twist=Twist(vx, 0.0, vyaw), head=blick)

    def target(self):
        return None


class FarbeFolgen(Behavior):
    name = "farbe folgen"
    channels = ("base", "head")
    ABSTAND_M = 0.25
    MAX_V = 0.16
    WEG_S = 12.0

    def __init__(self, farbe: str = "rot", seconds: float = 120.0) -> None:
        super().__init__()
        self.farbe = farbe if farbe in FARBEN else "rot"
        self.duration = max(5.0, min(600.0, seconds))
        self.timeout = self.duration + 2
        self.weg_t = 0.0
        self.gesehen = False
        self.seite = 1.0
        self.da = 0                       # wie oft sie angekommen ist
        self._war_da = False

    def _ziel(self, st: DuckState) -> dict[str, Any] | None:
        passend = [o for o in st.perception.objects if o.get("farbe") == self.farbe and o.get("art") != "möbel"]
        return min(passend, key=lambda o: o.get("entfernung_m", 9.0), default=None)

    def tick(self, st, dt):
        if self.elapsed >= self.duration:
            return self.finish(f"genug gefolgt ({self.da}× angekommen)")
        ding = self._ziel(st)
        if ding is None:
            self.weg_t += dt
            if self.weg_t > self.WEG_S:
                return self.finish("Farbe verloren" if self.gesehen else "nichts in dieser Farbe gesehen")
            if self.weg_t < 3.0:
                return Command(twist=Twist(), head=Head(0.0, 0.3, 0.7 * math.sin(self.elapsed * 1.6), 0.0))
            return Command(twist=Twist(0.0, 0.0, 0.6 * self.seite), head=Head(0.0, 0.3, 0.4 * self.seite, 0.0))
        self.weg_t = 0.0
        self.gesehen = True
        dist = float(ding.get("entfernung_m", 1.0))
        richtung = wrap_angle(math.radians(float(ding.get("richtung_grad", 0.0))))
        self.seite = 1.0 if richtung >= 0 else -1.0
        nah = dist <= self.ABSTAND_M + 0.04
        vyaw = max(-0.9, min(0.9, 2.0 * richtung))
        if nah:
            vx = 0.0
            if abs(richtung) < 0.25:
                vyaw = 0.0
                if not self._war_da:
                    self.da += 1
                self._war_da = True
        else:
            self._war_da = False
            vx = 0.0 if abs(richtung) > 0.6 else min(self.MAX_V, max(0.05, (dist - self.ABSTAND_M) * 0.8))
        runter = math.atan2(0.2, max(0.05, dist))
        return Command(twist=Twist(vx, 0.0, vyaw),
                       head=Head(0.0, clamp(runter, "head_pitch"), clamp(richtung * 0.7, "head_yaw"), 0.0))

    def target(self):
        return None


# Werkzeuge fürs Sprachmodell (in `brain/tools.py` eingereiht)
WERKZEUGE: list[dict[str, Any]] = [
    {"name": "linie_folgen",
     "description": "Einer Klebeband-Linie auf dem Boden folgen (wie Hiwonders „Line following“), bis die Zeit um ist oder "
                    "die Linie 8 s lang weg ist. Im Simulator legt der Mensch die Linie unter Steuern → Aufgaben.",
     "input_schema": {"type": "object", "properties": {
         "seconds": {"type": "number", "description": "wie lange höchstens (5–600, Standard 120)"},
         "tempo": {"type": "number", "description": "m/s, 0.05–0.16 (Standard 0.1)"}}}},
    {"name": "farbe_folgen",
     "description": "Dem nächsten Ding in einer Farbe nachlaufen und davor stehen bleiben (wie Hiwonders „Object "
                    "tracking“): rot, gelb, gruen oder blau. Endet nach der Zeit oder wenn 12 s nichts in der Farbe da ist.",
     "input_schema": {"type": "object", "properties": {
         "farbe": {"type": "string", "enum": list(FARBEN)},
         "seconds": {"type": "number", "description": "wie lange höchstens (5–600, Standard 120)"}},
         "required": ["farbe"]}},
]
