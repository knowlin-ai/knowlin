"""Linie folgen (seit 0.55): eine Klebeband-Linie auf dem Boden, die die Ente mit der Kamera abläuft.

Wie in Hiwonders Studio („Autonomous line following“): Ein dunkles Band liegt als Runde auf dem Boden, die Kamera schaut
schräg nach unten, und die Ente hält die Linie in der Bildmitte. Hier steckt nur die Rechnung, ohne Server und ohne
Körper:

* `punkte()` – die Runde im Wohnzimmer des Simulators: eine glatte Schleife (Catmull-Rom) um den Couchtisch, alle 4 cm
  ein Punkt; sie beginnt gleich neben dem Startplatz der Ente. Kein Möbel und kein Ding liegt darauf (Test).
* `sicht(x, y, yaw, punkte)` – was die Kamera von der Linie sieht, als Ding wie der Laserpunkt: Versatz quer zur
  Blickrichtung ein Stück voraus (+ = links) und Winkel der Linie zur Blickrichtung (+ = nach links). Dasselbe Format
  liefert am echten Roboter `farbsicht.detect_linie()` aus dem Kamerabild.
"""

from __future__ import annotations

import math
from typing import Any

# Stützpunkte der Runde um den Couchtisch (Wohnzimmer 4 × 3 m): mindestens 15 cm Abstand zu Möbeln und gut 20 cm zu den
# Dingen am Boden, damit weder der Hindernis-Reflex noch ein Ding auf dem Band sie aus der Spur bringt (Test)
STUETZ: tuple[tuple[float, float], ...] = ((-0.35, -0.55), (1.1, -0.55), (1.3, 0.0), (1.05, 0.5), (-0.2, 0.45),
                                           (-0.55, 0.0))
SCHRITT_M = 0.04          # Abstand der Punkte auf der Linie
VORAUS_M = 0.2            # dort schaut die Kamera auf den Boden (Mitte des Bildausschnitts)
SICHT_M = 0.22            # so weit quer darf die Linie dort liegen und ist noch im Bild
BREITE_M = 0.025          # Klebeband
NAME = "Linie"


def _catmull(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    t2, t3 = t * t, t * t * t
    return tuple(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3)
                 for a, b, c, d in zip(p0, p1, p2, p3))  # type: ignore[return-value]


def punkte(stuetz: tuple[tuple[float, float], ...] = STUETZ) -> list[tuple[float, float]]:
    """Geschlossene, glatte Runde durch die Stützpunkte, gleichmäßig etwa alle `SCHRITT_M`."""
    n = len(stuetz)
    roh: list[tuple[float, float]] = []
    for i in range(n):
        p0, p1, p2, p3 = stuetz[i - 1], stuetz[i], stuetz[(i + 1) % n], stuetz[(i + 2) % n]
        laenge = math.dist(p1, p2)
        k = max(2, int(laenge / SCHRITT_M * 1.5))
        roh += [_catmull(p0, p1, p2, p3, j / k) for j in range(k)]
    out = [roh[0]]
    for p in roh[1:]:
        if math.dist(p, out[-1]) >= SCHRITT_M:
            out.append((round(p[0], 4), round(p[1], 4)))
    return out


def _naechster(px: float, py: float, pts: list[tuple[float, float]]) -> tuple[float, tuple[float, float], float]:
    """Kürzester Abstand zur geschlossenen Linie: (Abstand, Fußpunkt, Richtung des Stücks in rad)."""
    best = (math.inf, (0.0, 0.0), 0.0)
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        ll = dx * dx + dy * dy
        t = 0.0 if ll < 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
        fx, fy = ax + t * dx, ay + t * dy
        d = math.hypot(px - fx, py - fy)
        if d < best[0]:
            best = (d, (fx, fy), math.atan2(dy, dx))
    return best


def _wrap(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


def sicht(x: float, y: float, yaw: float, pts: list[tuple[float, float]] | None) -> dict[str, Any] | None:
    """Die Linie, wie sie die Kamera ein Stück voraus sieht – oder None, wenn sie nicht im Bild ist."""
    if not pts:
        return None
    vx, vy = x + VORAUS_M * math.cos(yaw), y + VORAUS_M * math.sin(yaw)
    d, (fx, fy), richtung = _naechster(vx, vy, pts)
    if d > SICHT_M:
        return None
    quer = -(fx - x) * math.sin(yaw) + (fy - y) * math.cos(yaw)       # + = links von der Blickrichtung
    winkel = _wrap(richtung - yaw)
    if abs(winkel) > math.pi / 2:                                      # die Linie hat keine Richtung: die nach vorn
        winkel = _wrap(winkel + math.pi)
    return {"name": NAME, "art": "linie", "versatz_m": round(quer, 3), "winkel_grad": round(math.degrees(winkel)),
            "entfernung_m": VORAUS_M, "richtung_grad": round(math.degrees(math.atan2(quer, VORAUS_M)))}
