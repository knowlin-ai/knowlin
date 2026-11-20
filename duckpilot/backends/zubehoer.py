"""Zubehör der Microduck im einfachen Simulator (seit 0.47): Rollen zum Anklemmen.

Pollens Zubehörpaket hat zwei Rollen zum Anklemmen an die Füße; mit ihnen fährt die Microduck Rollschuh (Pollens
Policies `roller` und `roller_crouch`). Das Physikmodell hat keine Rollen – deshalb gibt es sie vorerst nur im einfachen
Simulator, als gezeichnete Bewegung (Entscheidung des Maintainers: „Einfacher Simulator“):

- schneller als zu Fuß, rollt nach (bremst sanfter, als sie anfährt), kann nicht seitwärts trippeln, lenkt weicher;
- „geduckt“ (wie `roller_crouch`): tiefer und noch etwas schneller;
- mit Rollen gehen Tricks nicht, die Füße am Boden brauchen (Aufheben, Schuss, Rolle) – sie sagt das ehrlich;
- anklemmen und abnehmen nur im Stand, nicht während eines Tricks.

Sicherheit: Der Not-Aus wirkt wie immer (stromlos, sie rollt nicht weiter: `lahm()` setzt die Geschwindigkeit auf
null). Am echten Roboter kommen die Rollen erst mit Pollens Policy (ab Lieferung).
"""

from __future__ import annotations

from ..api import IntentResult, Twist

ROLLEN_FAKTOR = 1.8          # so viel schneller als zu Fuß (Höchstgeschwindigkeit des Laufens × Faktor)
ROLLEN_GEDUCKT = 2.1         # geduckt noch etwas schneller
ANFAHREN = 0.55              # m/s² – Abstoßen kostet Kraft
AUSROLLEN = 0.45             # m/s² – bremst sanfter, als sie anfährt (rollt nach)
LENKEN = 0.6                 # Drehrate gegenüber zu Fuß
DUCKEN_M = 0.02              # geduckt: so viel tiefer
ROLLEN_NICHT = frozenset({"ground_pick", "kick_left", "kick_right", "roulade"})


class ZubehoerMixin:
    """Wird in `SimBackend` gemischt: Zustand `rollen`/`rollen_geduckt`, Ziel- und Trägheitsregeln auf Rollen."""

    rollen: bool = False
    rollen_geduckt: bool = False

    def rollen_anlegen(self, an: bool, geduckt: bool | None = None) -> IntentResult:
        """Rollen anklemmen oder abnehmen (nur im Stand) – oder nur die Haltung (geduckt) wechseln."""
        if geduckt is not None and an == self.rollen:
            if not self.rollen:
                return IntentResult(False, "Erst die Rollen anklemmen")
            self.rollen_geduckt = bool(geduckt)
            self.emit("rollen", an=True, geduckt=self.rollen_geduckt,
                      message="geduckt – noch schneller" if geduckt else "aufrecht auf Rollen")
            return IntentResult(True, "geduckt" if geduckt else "aufrecht")
        if an == self.rollen:
            return IntentResult(True, "Rollen sind schon dran" if an else "Rollen sind schon ab")
        if self.skill:
            return IntentResult(False, f"'{self.skill}' läuft gerade – danach")
        if abs(self.applied.vx) > 0.02 or abs(self.applied.vyaw) > 0.1:
            return IntentResult(False, "Erst anhalten – Rollen nur im Stand an- oder abklemmen")
        self.rollen = bool(an)
        self.rollen_geduckt = bool(geduckt) if an and geduckt is not None else False
        self.requested = Twist()
        self.emit("rollen", an=self.rollen, geduckt=self.rollen_geduckt,
                  message="Rollen angeklemmt – sie fährt jetzt Rollschuh" if an else "Rollen abgenommen")
        return IntentResult(True, "Rollen dran" if an else "Rollen ab")

    def _rollen_ziel(self, target: Twist) -> Twist:
        if not self.rollen:
            return target
        f = ROLLEN_GEDUCKT if self.rollen_geduckt else ROLLEN_FAKTOR
        return Twist(target.vx * f, 0.0, target.vyaw * LENKEN)      # seitwärts trippeln geht auf Rollen nicht

    def _rollen_beschleunigung(self, attr: str, cur: float, tgt: float, normal: float) -> float:
        if not self.rollen or attr == "vyaw":
            return normal
        return AUSROLLEN if abs(tgt) < abs(cur) else ANFAHREN

    def _rollen_takt(self, speed: float) -> float:
        """Schrittfrequenz auf Rollen: langsames Abstoßen statt Trippeln."""
        return (0.8 + 0.7 * min(1.0, speed / 0.45)) * (0.8 if self.rollen_geduckt else 1.0)

    def _rollen_verboten(self, skill: str) -> str | None:
        if self.rollen and skill in ROLLEN_NICHT:
            return "Mit Rollen an den Füßen geht das nicht – erst die Rollen abnehmen"
        return None
