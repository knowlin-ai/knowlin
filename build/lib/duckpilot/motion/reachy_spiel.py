"""Spiele mit der Webcam für Reachy Mini (seit 0.38.13): „Rotes Licht, grünes Licht“, „Hand folgen“, seit 0.38.14
auch „Mach mir nach“ und „Schere, Stein, Papier“ (Ablauf und Punkte in `server/routes/spiele.py`).

Wie in Pollens Reachy-Apps – aber ohne Bilder auf dem Server: Die Oberfläche (`static/kamera_spiele.js`) misst die
Bewegung im Webcam-Bild selbst und schickt nur Zahlen (Blickrichtung in Grad, Stärke 0 … 1). Hier steht nur, wie Reachy
sich dazu bewegt:

- `SpielHaltung` ist ein Verhalten über die Kanäle Körper (Drehung auf dem Sockel) und Kopf. Es hält einen
  Gesamtblick (`blick_yaw`, relativ zur Grundrichtung des Sockels, + = links) und ein Ziel für die Körperdrehung; der Kopf
  nimmt jeweils den Rest gegen den gerade gemessenen Körper (höchstens `KOPF_YAW_MAX`). Gesten (`play_overlay`) und
  der Not-Aus gehen wie immer darüber – `stop_all` beendet das Verhalten sofort.
- Kommt eine Weile kein neues Ziel (Fenster zu, Browser weg), endet es von selbst (`frist_s`).
- `aufteilen` verteilt einen Blick auf Körper und Kopf: kleine Winkel nur mit dem Kopf, große auch mit dem Körper.

Grenzen: Kopf ±50° gegen den Körper, nicken ±22°, Körper ±150° (Pollen: ±160°, Kopf/Körper höchstens 65° auseinander);
`reachy_kinematik.begrenzen` prüft die Kopflage danach noch einmal zentral.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from ..api import DuckState, Head, Twist
from .engine import Behavior, Command

KOPF_YAW_MAX = math.radians(50)      # Kopf gegen Körper
KOPF_PITCH_MAX = math.radians(22)    # nicken (+ = nach unten)
KOERPER_MAX = math.radians(150)      # Körperdrehung auf dem Sockel
NUR_KOPF = math.radians(30)          # bis hierhin dreht nur der Kopf, darüber hilft der Körper
DREH_RATE = 0.9                      # rad/s – höchstens so schnell dreht der Körper (sanft)
DREH_GAIN = 2.2                      # Regler: Drehrate je rad Abweichung
TOTZONE = math.radians(1.5)          # so nah am Ziel ruht der Körper


def begrenzt(wert: float, grenze: float) -> float:
    if wert is None or math.isnan(wert):
        return 0.0
    return max(-grenze, min(grenze, float(wert)))


def aufteilen(blick_yaw: float) -> float:
    """Ziel der Körperdrehung zu einem Gesamtblick (rad): bis `NUR_KOPF` bleibt der Körper gerade, darüber dreht er den
    Überschuss mit – der Kopf schaut dann immer etwa `NUR_KOPF` weiter."""
    rest = abs(blick_yaw) - NUR_KOPF
    return 0.0 if rest <= 0 else begrenzt(math.copysign(rest, blick_yaw), KOERPER_MAX)


class SpielHaltung(Behavior):
    """Reachy hält beim Spielen einen Blick und eine Körperdrehung, bis das Spiel endet oder nichts mehr kommt."""

    name = "spiel"
    channels = ("base", "head")
    timeout = 900.0                   # höchstens eine Viertelstunde am Stück

    def __init__(self, art: str, frist_s: float = 5.0, beendet: Callable[[str], Any] | None = None) -> None:
        super().__init__()
        self.art = art
        self.frist_s = frist_s
        self.beendet = beendet
        self.blick_yaw = 0.0
        self.pitch = 0.0
        self.koerper_ziel = 0.0
        self._seit_ziel = 0.0

    def setze(self, blick_yaw: float, pitch: float = 0.0, koerper: float | None = None) -> None:
        """Neues Ziel (rad). Ohne `koerper` verteilt `aufteilen` den Blick auf Körper und Kopf."""
        self.blick_yaw = begrenzt(blick_yaw, KOERPER_MAX + KOPF_YAW_MAX)
        self.pitch = begrenzt(pitch, KOPF_PITCH_MAX)
        self.koerper_ziel = aufteilen(self.blick_yaw) if koerper is None else begrenzt(koerper, KOERPER_MAX)
        self._seit_ziel = 0.0

    def lebt(self) -> None:
        """Das Spiel läuft noch (z. B. lange grüne Phase ohne neues Ziel)."""
        self._seit_ziel = 0.0

    @staticmethod
    def koerper_jetzt(st: DuckState) -> float:
        lage = getattr(st, "kopf_lage", None) or {}
        return float(lage.get("koerper", 0.0) or 0.0)

    def tick(self, st: DuckState, dt: float) -> Command | None:
        self._seit_ziel += dt
        if self._seit_ziel > self.frist_s:
            return self.finish("keine Ziele mehr – Spiel beendet")
        k = self.koerper_jetzt(st)
        fehler = self.koerper_ziel - k
        vyaw = 0.0 if abs(fehler) < TOTZONE else max(-DREH_RATE, min(DREH_RATE, DREH_GAIN * fehler))
        kopf_yaw = begrenzt(self.blick_yaw - k, KOPF_YAW_MAX)
        return Command(twist=Twist(0.0, 0.0, vyaw), head=Head(0.0, self.pitch, kopf_yaw, 0.0))

    def describe(self) -> str:
        return {"ampel": "spielt „Rotes Licht, grünes Licht“", "folgen": "folgt deiner Hand vor der Kamera",
                "spiegel": "spielt „Mach mir nach“", "ssp": "spielt „Schere, Stein, Papier“"}.get(self.art, "spielt")

    def on_stop(self) -> None:
        if self.beendet is not None:
            cb, self.beendet = self.beendet, None
            cb(self.result or "abgebrochen")
