"""Marionette (seit 0.48, Mentor): Du führst den Kopf mit dem Handy oder mit deinem eigenen Kopf in der Quest – sie
macht es nach, und auf Wunsch merkt sie sich die Bewegung und spielt sie später allein ab.

- **Eingang:** Lage relativ zur Nullstellung beim Start, in rad: `gieren` (+ = nach links), `nicken` (+ = nach oben),
  `neigen` (+ = nach rechts). Das Handy rechnet sie aus seiner Lage (DeviceOrientation), die Brille aus der Lage des
  Kopfes (WebXR). Hierher kommen nur diese drei Zahlen – kein Bild, kein Raum.
- **Ausgang:** eine Kopfstellung (`Head`), sanft nachgeführt (`TAU`) und auf die Grenzen begrenzt. Die Laufzeit hält
  sie mit `engine.look_at` kurz fest (`HALTEN_S`) – kommt nichts mehr, schaut sie wieder selbst.
- **Aufnahme:** bis `AUFNAHME_MAX_S`, ein Punkt alle `PUNKT_S`. Gespeichert wird je Körperart in
  `<daten>/marionette.json` (Name, Dauer, Punkte) – nur Zahlen, nichts über Personen.
- **Abspielen:** `motion/nachspielen.py` (Kanal „head“), der Not-Aus beendet es wie jedes Verhalten.

Für Körper mit Kopf (`eigenschaften()` enthält „kopf“). Ein Arm folgt stattdessen deiner Hand (`mentor.py`).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .api import Head

DATEI = "marionette.json"
TAU = 0.10                    # s: so schnell folgt der Kopf (glättet Zittern des Handys)
HALTEN_S = 0.6                # so lange gilt eine Lage, wenn keine neue kommt
PUNKT_S = 0.1                 # Abstand der Punkte einer Aufnahme
AUFNAHME_MAX_S = 60.0
MAX_JE_KOERPER = 24
GRENZE = math.radians(80)     # mehr nimmt der Eingang nicht an (Handy ganz gekippt)
NAME_MAX = 40


def lage_aus(daten: Any) -> tuple[float, float, float] | None:
    """Prüft, was vom Handy oder der Brille kommt: drei endliche Zahlen (rad) – sonst None."""
    if not isinstance(daten, dict):
        return None
    out = []
    for k in ("gieren", "nicken", "neigen"):
        try:
            v = float(daten.get(k, 0.0))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(v):
            return None
        out.append(max(-GRENZE, min(GRENZE, v)))
    return out[0], out[1], out[2]


def kopf_von(gieren: float, nicken: float, neigen: float) -> Head:
    """Lage → Kopfstellung des Körpers (Kopf nickt mit positivem `head_pitch` nach unten)."""
    return Head(0.0, -nicken, gieren, neigen).clamped()


@dataclass
class Marionette:
    quelle: str = "handy"
    lage: tuple[float, float, float] | None = None
    zuletzt: float = 0.0
    aufnahme_start: float | None = None
    punkte: list[list[float]] = field(default_factory=list)

    def weiter(self, roh: tuple[float, float, float], jetzt: float) -> Head:
        if self.lage is None:
            self.lage = roh
        else:
            k = 1 - math.exp(-max(0.0, jetzt - self.zuletzt) / TAU)
            self.lage = tuple(a + (b - a) * k for a, b in zip(self.lage, roh))  # type: ignore[assignment]
        self.zuletzt = jetzt
        kopf = kopf_von(*self.lage)
        if self.aufnahme_start is not None:
            t = jetzt - self.aufnahme_start
            if t > AUFNAHME_MAX_S:
                self.aufnahme_start = None              # voll – die Laufzeit meldet es beim Stoppen
            elif not self.punkte or t - self.punkte[-1][0] >= PUNKT_S:
                self.punkte.append([round(t, 2), round(kopf.head_pitch, 3), round(kopf.head_yaw, 3),
                                    round(kopf.head_roll, 3)])
        return kopf

    def aufnehmen(self, jetzt: float) -> None:
        self.aufnahme_start, self.punkte = jetzt, []

    def aufnahme_ende(self) -> list[list[float]]:
        self.aufnahme_start = None
        pts, self.punkte = self.punkte, []
        return pts

    @property
    def nimmt_auf(self) -> bool:
        return self.aufnahme_start is not None


def name_sauber(name: str) -> str:
    n = re.sub(r"[\x00-\x1f<>]", "", str(name or "")).strip()
    return n[:NAME_MAX]


class Bewegungen:
    """Aufgenommene Kopfbewegungen je Körperart."""

    def __init__(self, ordner: Path) -> None:
        self.pfad = Path(ordner) / DATEI

    def _alle(self) -> dict[str, list[dict[str, Any]]]:
        try:
            d = json.loads(self.pfad.read_text(encoding="utf-8"))
            return {k: v for k, v in d.items() if isinstance(v, list)} if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def liste(self, koerper: str) -> list[dict[str, Any]]:
        return [{"name": b["name"], "dauer": b["dauer"], "punkte": len(b["punkte"])}
                for b in self._alle().get(koerper, []) if isinstance(b, dict) and "name" in b]

    def alle_koerper(self) -> dict[str, list[dict[str, Any]]]:
        return {k: self.liste(k) for k in self._alle() if self.liste(k)}

    def holen(self, koerper: str, name: str) -> dict[str, Any] | None:
        return next((b for b in self._alle().get(koerper, []) if b.get("name") == name), None)

    def speichern(self, koerper: str, name: str, punkte: list[list[float]]) -> tuple[bool, str]:
        name = name_sauber(name)
        if not name:
            return False, "Gib der Bewegung einen Namen."
        if len(punkte) < 5:
            return False, "Zu kurz – bewege den Kopf mindestens eine halbe Sekunde."
        d = self._alle()
        liste = [b for b in d.get(koerper, []) if b.get("name") != name]
        if len(liste) >= MAX_JE_KOERPER:
            return False, f"Schon {MAX_JE_KOERPER} Bewegungen – lösch erst eine."
        liste.append({"name": name, "dauer": punkte[-1][0], "punkte": punkte})
        d[koerper] = liste
        self._schreiben(d)
        return True, f"„{name}“ gemerkt ({punkte[-1][0]:.1f} s)".replace(".", ",")

    def loeschen(self, koerper: str, name: str) -> bool:
        d = self._alle()
        alt = d.get(koerper, [])
        neu = [b for b in alt if b.get("name") != name]
        if len(neu) == len(alt):
            return False
        d[koerper] = neu
        self._schreiben(d)
        return True

    def _schreiben(self, d: dict[str, Any]) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".teil")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.pfad)
