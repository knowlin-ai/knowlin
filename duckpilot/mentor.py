"""Mentor: Handpunkte → Bewegung für den Arm (seit 0.38.57, erster Schritt zum Mentor aus 0.44).

Maintainer: „dann bin ich sozusagen die Körperschnittstelle“ – du machst vor, Knowlin schaut zu. Die Handerkennung läuft
im Browser (MediaPipe, Apache-2.0) und schickt nur 21 Handpunkte, nie ein Bild. Hier werden sie zu einer Lage der
Greiferspitze über der Werkbank: wie in einem Spiegel, aus deiner Sicht (du sitzt Ari gegenüber, links ist deine
linke Seite). Handmitte links/rechts → Ari links/rechts, hoch/runter → höher/tiefer, Hand näher an der Kamera (größer)
→ weiter vor zu dir. Daumen und Zeigefinger zusammen → Greifer zu, auseinander → auf.

Webcam, Handy und VR-Brille (WebXR-Hand-Tracking) liefern dieselben 21 Punkte – der Rest merkt keinen Unterschied.
Diese Datei gehört zur Basis: reine Rechnung, kein Körper, kein Netz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

PUNKTE = 21
HANDGELENK, DAUMEN_SPITZE, ZEIGE_ANSATZ, ZEIGE_SPITZE, MITTEL_ANSATZ, KLEIN_ANSATZ = 0, 4, 5, 8, 9, 17

# Arbeitsraum über der Werkbank (m, Rahmen des Sockels) – innerhalb dessen, was der Planer erreicht
BEREICH_X = (0.15, 0.28)          # nah am Sockel … vorn bei dir
BEREICH_Y = (-0.14, 0.14)         # deine linke … deine rechte Seite
BEREICH_Z = (0.025, 0.12)         # knapp über der Werkbank … hoch
GREIFER_AUF, GREIFER_ZU = 45.0, 8.0
ZANGE_ZU, ZANGE_AUF = 0.45, 0.85  # Abstand Daumen–Zeigefinger je Handgröße; dazwischen bleibt es, wie es war
TAU = 0.12                        # s: so schnell folgt das Ziel der Hand (glättet Zittern der Erkennung)


@dataclass
class Hand:
    punkte: list[tuple[float, float, float]]
    seite: str = ""


def hand_aus(daten: Any) -> Hand | None:
    """Prüft, was vom Browser kommt: genau 21 Punkte mit x, y (0…1 im Bild) und z – sonst None."""
    if not isinstance(daten, dict):
        return None
    roh = daten.get("punkte")
    if not isinstance(roh, list) or len(roh) != PUNKTE:
        return None
    punkte = []
    for p in roh:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return None
        try:
            x, y, z = float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(v) for v in (x, y, z)) or not (-0.5 <= x <= 1.5 and -0.5 <= y <= 1.5):
            return None
        punkte.append((x, y, z))
    seite = str(daten.get("seite") or "")[:10]
    return Hand(punkte, seite)


def _abstand(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def groesse(h: Hand) -> float:
    """Handgröße im Bild: Handgelenk bis Ansatz des Mittelfingers (unabhängig davon, ob die Finger gestreckt sind)."""
    return _abstand(h.punkte[HANDGELENK], h.punkte[MITTEL_ANSATZ])


def mitte(h: Hand) -> tuple[float, float]:
    """Mitte der Handfläche (0…1 im Bild)."""
    pts = [h.punkte[i] for i in (HANDGELENK, ZEIGE_ANSATZ, MITTEL_ANSATZ, KLEIN_ANSATZ)]
    return sum(p[0] for p in pts) / 4, sum(p[1] for p in pts) / 4


def zange(h: Hand) -> float:
    """Abstand Daumen- zu Zeigefingerspitze, bezogen auf die Handgröße (≈ 0,2 zusammen, > 1 weit auf)."""
    g = groesse(h)
    return _abstand(h.punkte[DAUMEN_SPITZE], h.punkte[ZEIGE_SPITZE]) / g if g > 1e-6 else 1.0


def _zwischen(wert: float, von: float, bis: float, ziel: tuple[float, float]) -> float:
    t = max(0.0, min(1.0, (wert - von) / (bis - von)))
    return ziel[0] + t * (ziel[1] - ziel[0])


@dataclass
class Nachmacher:
    """Macht aus aufeinanderfolgenden Händen ein ruhiges Ziel für die Greiferspitze. Die erste Hand legt die Mitte und
    die Größe fest („Hand ruhig in die Mitte halten“) – danach zählt nur, wie weit sie sich davon bewegt."""

    bezug: tuple[float, float, float] | None = None       # Mitte x, y und Größe der ersten Hand
    ziel: dict[str, float] | None = None
    zu: bool = False
    zuletzt: float = 0.0
    zaehler: int = field(default=0)

    def neu(self) -> None:
        self.bezug, self.ziel, self.zu, self.zaehler = None, None, False, 0

    def weiter(self, h: Hand, jetzt: float) -> dict[str, float]:
        mx, my = mitte(h)
        g = groesse(h)
        if self.bezug is None:
            self.bezug = (mx, my, max(g, 1e-3))
        bx, by, bg = self.bezug
        # Spiegel: deine rechte Hand nach rechts → im Bild nach links (Kamera schaut dich an) → Ari zu deiner Rechten (+y)
        y = _zwischen(bx - mx, -0.3, 0.3, BEREICH_Y)
        z = _zwischen(by - my, -0.25, 0.25, BEREICH_Z)
        x = _zwischen(g / bg, 0.75, 1.35, BEREICH_X)
        wert = zange(h)
        if wert < ZANGE_ZU:
            self.zu = True
        elif wert > ZANGE_AUF:
            self.zu = False
        roh = {"x": x, "y": y, "z": z}
        if self.ziel is None:
            self.ziel = roh
        else:
            k = 1 - math.exp(-max(0.0, jetzt - self.zuletzt) / TAU)
            self.ziel = {a: self.ziel[a] + (roh[a] - self.ziel[a]) * k for a in roh}
        self.zuletzt = jetzt
        self.zaehler += 1
        return {**{a: round(v, 4) for a, v in self.ziel.items()}, "greifer": GREIFER_ZU if self.zu else GREIFER_AUF}
