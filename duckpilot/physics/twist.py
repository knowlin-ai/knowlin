"""Bewegungswunsch → Befehl an Pollens Geh-Policy – gemeinsam für die Physik-Ente und das Üben.

So läuft geübt genau so wie gezeigt: Übt Claude eine Choreografie, gehen die Fahrbefehle durch dieselbe Anhebung
wie später in der sichtbaren Physik.
"""

from __future__ import annotations

import math

from .core import TWIST_MAX

# Pollens Geh-Policy (VelStand) hat eine Totzone: kleine Befehle heißen „stehen bleiben“. Gemessen in duckpilot
# 0.20.4 auf PC: vx 0,10 → 0,003 m/s, 0,20 → 0,07 m/s, 0,30 → 0,08 m/s; Drehen aus dem Stand erst ab
# ≈ 0,8 rad/s (0,2 und 0,4 rad/s: gar nicht). Die Verhalten bestellen aber 5–15 cm/s. Darum hier anheben:
# jede gewollte Bewegung wird mindestens so groß, dass die Policy wirklich Schritte macht.
WALK_MIN = 0.20             # m/s – kleinster Befehl, bei dem sie losgeht
WALK_GAIN = 2.0             # gewünschte Geschwindigkeit × WALK_GAIN (die Policy läuft deutlich langsamer als befohlen)
SIDE_MIN = 0.15
TURN_MIN_STAND = 0.8        # rad/s – Drehen auf der Stelle
TURN_GAIN = 1.5
WANT = 0.01                 # darunter gilt ein Befehl als „nichts“


def shape_twist(vx: float, vy: float, vyaw: float) -> tuple[float, float, float]:
    """Gewünschte Bewegung → Befehl an Pollens Geh-Policy (Totzone überspringen, Begrenzung einhalten)."""
    def lift(v: float, lo: float, gain: float, hi: float) -> float:
        if abs(v) < WANT:
            return 0.0
        return math.copysign(min(hi, max(lo, abs(v) * gain)), v)

    walking = abs(vx) >= WANT or abs(vy) >= WANT
    sx = lift(vx, WALK_MIN, WALK_GAIN, float(TWIST_MAX[0]))
    sy = lift(vy, SIDE_MIN, WALK_GAIN, float(TWIST_MAX[1]))
    if walking:                 # beim Gehen lenkt sie auch mit kleinen Drehbefehlen
        syaw = 0.0 if abs(vyaw) < WANT else max(-float(TWIST_MAX[2]), min(float(TWIST_MAX[2]), vyaw * TURN_GAIN))
    else:
        syaw = lift(vyaw, TURN_MIN_STAND, TURN_GAIN, float(TWIST_MAX[2]))
    return sx, sy, syaw
