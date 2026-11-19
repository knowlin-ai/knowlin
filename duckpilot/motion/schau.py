"""„Schau mich an“ (seit 0.39, Stack-chan „wie ab Werk“): Der Kopf folgt dem Gesicht vor der Webcam.

Die Oberfläche (`static/schau.js`) findet das Gesicht im Webcam-Bild selbst (MediaPipe Face Detection, im Browser) und
schickt nur eine Blickrichtung in Grad. Hier steht nur, wie der Kopf ihr folgt:

- `SchauHaltung` ist ein Verhalten nur über den Kanal Kopf: sanft (begrenzte Drehrate) zum Ziel drehen und nicken, in
  den Grenzen, die jeder Körper ohnehin prüft (Stack-chan: `backends/stackchan.kopf_lage`, Reachy:
  `reachy_kinematik.begrenzen`). Der Körper selbst bewegt sich nicht.
- Kommt eine Weile kein Ziel mehr (Fenster zu, Webcam aus), endet es von selbst (`FRIST_S`).
- Not-Aus: `stop_all` beendet das Verhalten sofort; neue Ziele lehnt die Route während der Sperre ab.
"""

from __future__ import annotations

import math

from ..api import DuckState, Head
from .engine import Behavior, Command

YAW_MAX = math.radians(60)           # so weit dreht der Kopf höchstens zur Seite
PITCH_HOCH = math.radians(25)        # hochschauen (Nicken −)
PITCH_RUNTER = math.radians(10)      # runterschauen (Nicken +)
RATE = math.radians(120)             # rad/s – sanft, ohne Ruck
FRIST_S = 4.0


def begrenzt(wert: float, lo: float, hi: float) -> float:
    if wert is None or math.isnan(wert) or math.isinf(wert):
        return 0.0
    return max(lo, min(hi, float(wert)))


class SchauHaltung(Behavior):
    """Der Kopf schaut zum Gesicht vor der Kamera, bis nichts mehr kommt oder jemand stoppt."""

    name = "schau"
    channels = ("head",)
    timeout = 900.0                   # höchstens eine Viertelstunde am Stück

    def __init__(self, frist_s: float = FRIST_S) -> None:
        super().__init__()
        self.frist_s = frist_s
        self.ziel_yaw = 0.0
        self.ziel_pitch = 0.0
        self.yaw = 0.0
        self.pitch = 0.0
        self._seit_ziel = 0.0

    def setze(self, yaw: float, pitch: float) -> None:
        """Neues Blickziel (rad, + = links bzw. nach unten)."""
        self.ziel_yaw = begrenzt(yaw, -YAW_MAX, YAW_MAX)
        self.ziel_pitch = begrenzt(pitch, -PITCH_HOCH, PITCH_RUNTER)
        self._seit_ziel = 0.0

    def tick(self, st: DuckState, dt: float) -> Command | None:
        self._seit_ziel += dt
        if self._seit_ziel > self.frist_s:
            return self.finish("keine Ziele mehr – Schauen beendet")
        schritt = RATE * max(0.0, dt)
        self.yaw += begrenzt(self.ziel_yaw - self.yaw, -schritt, schritt)
        self.pitch += begrenzt(self.ziel_pitch - self.pitch, -schritt, schritt)
        return Command(head=Head(0.0, self.pitch, self.yaw, 0.0))

    def describe(self) -> str:
        return "schaut dich an"
