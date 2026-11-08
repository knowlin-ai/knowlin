"""Kopf-Stabilisator wie bei Huhn und Taube.

Der Rumpf wackelt beim Gehen und Drehen – der Kopf soll ruhig bleiben. Dafür gleichen die Kopfgelenke die
schnellen Lageänderungen des Rumpfs aus:

- **Rollen und Kippen:** Abweichung von der mittleren Lage (gleitender Mittelwert, ~1 s) wird mit Kopfrollen
  und Kopfnicken zurückgedreht. Langsame, gewollte Haltungen (Verbeugung, Gefühle) bleiben erhalten.
- **Gieren wie eine Taube:** Der Blick hält seine Richtung, während der Rumpf sich weiterdreht. Ist der Kopf
  zu weit verdreht, springt der Blick ruckartig in Drehrichtung voraus – und hält dann wieder still.

- **Vorhalt:** Die Gelenke folgen mit Verzögerung (Regler, ein Takt). Darum rechnet der Ausgleich die Drehrate
  des Rumpfs (Gyro am Roboter, sonst aus der Lage) um VORHALT Sekunden voraus.
- **Vor und zurück wie eine Taube:** Schiebt der Rumpf pro Schritt vor und zurück, gleichen Hals und Kopfnicken
  gemeinsam aus (gleich viel – die Blickrichtung bleibt): der Kopf hält seine Bahn, soweit der Hals reicht.

Die Vorzeichen stammen aus Pollens MJCF (Jacobi-Matrix am Kopf-Sensor, siehe Test): Kopfrollen = +Rumpfrollen,
Kopfnicken = −Rumpfkippen, Kopfgieren = −Rumpfgieren; Hals und Kopf gleich weit nicken verschiebt den Kopf um
−4,7 cm je rad nach vorn. Die Höhe gleicht der kurze Hals kaum aus (≈ 60 rad je Meter) – das bleibt weg.
Gemessen mit tests/test_stabilizer.py (synthetisches Gehen, Kopfkamera per Vorwärtskinematik): Drehzittern der
Kopfkamera −60 %, Vor/Zurück-Zittern −35 %.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..api import Head

TAU_LEVEL = 1.0          # s – langsamer als das Wackeln eines Schritts (~0,25 s), schneller als Gesten
YAW_RECENTER = 1.5       # s – steht der Rumpf still, wandert der Blick zurück zur Körpermitte (IMU-Drift)
YAW_HOLD = 0.45          # rad – so weit darf der Kopf hinter dem Rumpf herhängen, dann folgt der Ruck
YAW_LEAD = 0.25          # rad – um so viel schaut sie beim Ruck in Drehrichtung voraus
SACCADE_S = 0.12         # s – Dauer des Rucks
VORHALT = 0.03           # s – so weit rechnet der Ausgleich die Drehrate voraus (Regler- und Taktverzug)
RATE_GLATT = 0.6         # Glättung der aus der Lage gerechneten Drehrate (0 = aus, 1 = roh)
SURGE_M_PER_RAD = 0.047  # m – Kopfweg je rad, wenn Hals und Kopf gleich weit nicken
SURGE_A, SURGE_B = 0.08, 0.02   # Alpha-Beta-Filter der gleichmäßigen Vorwärtsbahn
LIMIT = Head(0.35, 0.5, 0.7, 0.3)  # höchstens so viel Ausgleich je Gelenk
# Echte Servos (Physik, Roboter): das Kopfnicken kommt beim Schritt-Nicken (≈ 4 Hz) nicht mit – ein verspäteter
# Ausgleich machte es schlimmer; Gieren und Rollen brauchen mehr Vorhalt (MuJoCo-Messung 0.20.4: Gieren −54 %)
SERVO_GAIN_PITCH, SERVO_VORHALT = 0.0, 0.07


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def euler_from_quat(w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
    """Rumpf→Welt-Quaternion (w zuerst) → Rollen, Kippen, Gieren (rad)."""
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


@dataclass
class _Saccade:
    start: float
    goal: float
    t: float = 0.0


class HeadStabilizer:
    """Rechnet aus der Rumpflage einen Ausgleich für die Kopfgelenke (als Head-Versatz)."""

    def __init__(self) -> None:
        self.enabled = False
        self.gain_pitch = 1.0        # Anteil des Nick-Ausgleichs (echte Servos: siehe use_servo_tuning)
        self.vorhalt = VORHALT
        self.yaw_hold = True          # aus, solange die Ente gezielt auf einen Punkt schaut (der Blick rechnet selbst)
        self.reset()

    def use_servo_tuning(self) -> None:
        """Für echte Servos (MuJoCo-Physik, Roboter): kein Nick-Ausgleich, mehr Vorhalt."""
        self.gain_pitch, self.vorhalt = SERVO_GAIN_PITCH, SERVO_VORHALT

    def reset(self) -> None:
        self._roll_avg: float | None = None
        self._pitch_avg: float | None = None
        self._gaze: float | None = None        # Blickrichtung in der Welt (Gieren)
        self._saccade: _Saccade | None = None
        self._last_yaw: float | None = None
        self._last_att: tuple[float, float] | None = None
        self._rates = [0.0, 0.0, 0.0]
        self._path: float | None = None        # glatte Vorwärtsbahn (Taube)
        self._path_v = 0.0
        self._last_fwd: float | None = None
        self._last_xy: tuple[float, float] | None = None
        self.offset = Head()

    def update(self, roll: float, pitch: float, yaw: float, dt: float, *, x: float | None = None,
               y: float | None = None, gyro: tuple[float, float, float] | None = None) -> Head:
        """Rumpflage (rad), optional Rumpfposition (m, für das Vor und Zurück) und Gyro (rad/s, Rumpfrahmen)."""
        if not self.enabled or not all(math.isfinite(v) for v in (roll, pitch, yaw)):
            self.reset()
            return self.offset
        dt = max(1e-3, min(0.2, dt))
        # Drehraten: vom Gyro, sonst aus der Lage (leicht geglättet)
        if gyro is not None and all(math.isfinite(g) for g in gyro):
            self._rates = [float(g) for g in gyro]
        elif self._last_att is not None and self._last_yaw is not None:
            raw = [(roll - self._last_att[0]) / dt, (pitch - self._last_att[1]) / dt, _wrap(yaw - self._last_yaw) / dt]
            self._rates = [a + (b - a) * RATE_GLATT for a, b in zip(self._rates, raw)]
        self._last_att = (roll, pitch)
        a = 1 - math.exp(-dt / TAU_LEVEL)
        self._roll_avg = roll if self._roll_avg is None else self._roll_avg + (roll - self._roll_avg) * a
        self._pitch_avg = pitch if self._pitch_avg is None else self._pitch_avg + (pitch - self._pitch_avg) * a
        d_roll = roll - self._roll_avg
        d_pitch = pitch - self._pitch_avg

        rate = self._rates[2]
        self._last_yaw = yaw
        if self._gaze is None or not self.yaw_hold:
            self._gaze = yaw
            self._saccade = None
        elif self._saccade is None and abs(rate) < 0.3:
            self._gaze += _wrap(yaw - self._gaze) * (1 - math.exp(-dt / YAW_RECENTER))
        lag = _wrap(yaw - self._gaze)            # wie weit der Rumpf am Blick vorbeigedreht ist
        if self._saccade is None and abs(lag) > YAW_HOLD:
            goal = yaw + math.copysign(YAW_LEAD, lag)
            self._saccade = _Saccade(self._gaze, goal)
        if self._saccade is not None:
            s = self._saccade
            s.t += dt
            k = min(1.0, s.t / SACCADE_S)
            k = k * k * (3 - 2 * k)                  # weich ein- und auslaufen, aber schnell
            self._gaze = s.start + _wrap(s.goal - s.start) * k
            if k >= 1.0:
                self._saccade = None
        d_yaw = _wrap(yaw - self._gaze)
        # Vorhalt gegen den Verzug der Gelenke (beim Gieren nur, solange der Blick hält – nicht im Ruck)
        d_roll += self._rates[0] * self.vorhalt
        d_pitch += self._rates[1] * self.vorhalt
        if self.yaw_hold and self._saccade is None:
            d_yaw += rate * self.vorhalt

        neck = self._surge(x, y, yaw, dt)

        def lim(v: float, m: float) -> float:
            return max(-m, min(m, v))

        self.offset = Head(neck, lim(-d_pitch * self.gain_pitch + neck, LIMIT.head_pitch), lim(-d_yaw, LIMIT.head_yaw),
                           lim(d_roll, LIMIT.head_roll))
        return self.offset

    def _surge(self, x: float | None, y: float | None, yaw: float, dt: float) -> float:
        """Vor und zurück pro Schritt: Hals und Kopf gleich weit nicken, damit der Kopf auf der glatten Bahn bleibt."""
        if x is None or y is None or not (math.isfinite(x) and math.isfinite(y)):
            return 0.0
        # Weg entlang der Blickrichtung aufsummieren – nicht die absolute Position projizieren: weit vom Ursprung
        # entfernt sähe sonst jedes kleine Gieren wie ein Ruck nach vorn aus (|Position| × Gierwinkel)
        last = getattr(self, "_last_xy", None)
        self._last_xy = (x, y)
        if last is None or self._last_fwd is None:
            fwd = 0.0
        else:
            dx, dy = x - last[0], y - last[1]
            if math.hypot(dx, dy) > 0.1:            # Sprung (zurückgesetzt, hochgehoben): neu anfangen
                self._path = None
                fwd = 0.0
            else:
                fwd = self._last_fwd + dx * math.cos(yaw) + dy * math.sin(yaw)
        if self._path is None or self._last_fwd is None:
            self._path, self._path_v = fwd, 0.0
        self._last_fwd = fwd
        pred = self._path + self._path_v * dt
        res = fwd - pred
        self._path = pred + SURGE_A * res
        self._path_v += SURGE_B * res / dt
        ahead = fwd - self._path                    # Rumpf ist der glatten Bahn so weit voraus
        return max(-LIMIT.neck_pitch, min(LIMIT.neck_pitch, ahead / SURGE_M_PER_RAD))

    def apply(self, head: Head) -> Head:
        """Gewünschte Kopfstellung plus Ausgleich (nicht beschnitten – das macht `clamped()` beim Senden)."""
        if not self.enabled:
            return head
        o = self.offset
        return Head(head.neck_pitch + o.neck_pitch, head.head_pitch + o.head_pitch,
                    head.head_yaw + o.head_yaw, head.head_roll + o.head_roll)
