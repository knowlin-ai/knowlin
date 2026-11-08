"""Ausdruck von Reachy Mini (seit 0.38.2): wie er zuhört, nachdenkt, spricht, atmet – und Pollens Aufnahmen abspielt.

Reachy Mini ist vor allem ein Gesprächsroboter. Pollens eigene Apps zeigen, was dazugehört, und duckpilot macht es
ähnlich, für Simulator und echten Reachy gleich (die Körper addieren nur, was hier herauskommt):

- **Atmen** im Leerlauf: Kopf hebt und senkt sich kaum sichtbar, Antennen schwingen langsam.
- **Zuhören** (jemand spricht ihn an): Kopf leicht geneigt und gehoben, Antennen aufgestellt.
- **Nachdenken** (das Gehirn rechnet): Blick schräg nach oben, Antennen spielen gegeneinander.
- **Sprechen**: der Kopf wippt mit der Lautstärke – wie Pollens „speech tapper“, nur aus dem Mund-Signal von
  duckpilot statt aus dem Ton –, die Antennen wackeln mit.
- **Aufnahmen** aus Pollens Bibliotheken (Emotionen, Tänze): Kopflage, Antennen und Körperdrehung über der Zeit.

Alles hier ist reine Rechnung ohne Ein- und Ausgabe. Winkel in rad, Wege in m; Kopflage relativ zum Körper.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Any

ANTENNE_RUHE = 0.1745         # Pollen: ≈ 10° auseinander
ANTENNE_SCHLAF = 3.05
# Pollens SLEEP_HEAD_POSE: Kopf 24° nach vorn gesenkt, 4,4 cm tiefer, 2 cm zurück
SCHLAF_LAGE = {"x": -0.021, "y": 0.0, "z": -0.044, "roll": 0.0, "pitch": 0.426, "yaw": 0.0}
LEER = {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
ZUSTAENDE = ("zuhoeren", "denkt")


def antennen_aus_mund(mund: float, phase: float) -> list[float]:
    """Spricht er, wackeln die Antennen leicht gegeneinander; sonst Ruhestellung. [rechts, links], rechts negativ."""
    w = max(0.0, min(1.0, mund)) * 0.5
    return [-(ANTENNE_RUHE + w * (1 + math.sin(phase)) * 0.5), ANTENNE_RUHE + w * (1 + math.cos(phase * 1.3)) * 0.5]


def lage_aus_matrix(m: list[list[float]] | list[float]) -> dict[str, float]:
    """4×4-Kopfmatrix (Pollen, Welt) → x, y, z, roll, pitch, yaw (Euler „xyz“ fest wie scipy: R = Rz·Ry·Rx)."""
    a = [list(map(float, m[i * 4:i * 4 + 4])) for i in range(4)] if len(m) == 16 else [list(map(float, r)) for r in m]
    pitch = math.asin(max(-1.0, min(1.0, -a[2][0])))
    roll = math.atan2(a[2][1], a[2][2])
    yaw = math.atan2(a[1][0], a[0][0])
    return {"x": a[0][3], "y": a[1][3], "z": a[2][3], "roll": roll, "pitch": pitch, "yaw": yaw}


@dataclass
class Aufnahme:
    """Eine von Pollens aufgenommenen Bewegungen (Format von `reachy_mini.motion.recorded_move`)."""
    name: str
    beschreibung: str
    zeiten: list[float]
    lagen: list[dict[str, float]]          # Kopflage in Pollens Welt (z ohne den Sockel-Versatz)
    antennen: list[list[float]]
    koerper: list[float]
    ton: str | None = None                 # Dateiname des Tons daneben (wav, mp3 …), falls es einen gibt
    datensatz: str = ""
    art: str = ""                          # „emotionen“ oder „taenze“

    @classmethod
    def aus_json(cls, name: str, daten: dict[str, Any], datensatz: str = "", ton: str | None = None) -> "Aufnahme":
        zeiten = [float(t) for t in daten["time"]]
        frames = daten["set_target_data"]
        if not zeiten or len(zeiten) != len(frames):
            raise ValueError(f"{name}: Zeiten und Bilder passen nicht zusammen")
        lagen = [lage_aus_matrix([v for row in f["head"] for v in row] if isinstance(f["head"][0], list) else f["head"])
                 for f in frames]
        t0 = zeiten[0]
        return cls(name=name, beschreibung=str(daten.get("description") or "")[:200], zeiten=[t - t0 for t in zeiten],
                   lagen=lagen, antennen=[[float(a) for a in f.get("antennas", [ANTENNE_RUHE * -1, ANTENNE_RUHE])][:2]
                                          for f in frames],
                   koerper=[float(f.get("body_yaw", 0.0)) for f in frames], ton=ton, datensatz=datensatz)

    @property
    def dauer(self) -> float:
        return self.zeiten[-1] if self.zeiten else 0.0

    def bei(self, t: float) -> tuple[dict[str, float], list[float], float]:
        """Kopflage (relativ zum Körper), Antennen, Körperdrehung zur Zeit t (linear zwischen den Bildern)."""
        t = max(0.0, min(self.dauer, t))
        i = max(1, min(len(self.zeiten) - 1, bisect.bisect_right(self.zeiten, t))) if len(self.zeiten) > 1 else 0
        if i == 0:
            a = b = 0
            k = 0.0
        else:
            a, b = i - 1, i
            span = self.zeiten[b] - self.zeiten[a]
            k = 0.0 if span <= 0 else (t - self.zeiten[a]) / span
        mix = lambda u, v: u + (v - u) * k                                      # noqa: E731
        koerper = mix(self.koerper[a], self.koerper[b])
        lage = {n: mix(self.lagen[a][n], self.lagen[b][n]) for n in LEER}
        lage["yaw"] -= koerper                                                 # Pollen: Kopf in der Welt
        return lage, [mix(x, y) for x, y in zip(self.antennen[a], self.antennen[b])], koerper


@dataclass
class Ausdruck:
    """Rechnet je Takt, was zum Kopf dazukommt und wohin die Antennen gehen."""
    t: float = 0.0
    zustand: str | None = None
    zustand_bis: float = 0.0
    _mund: float = 0.0                      # geglättete Lautstärke
    aufnahme: Aufnahme | None = None
    aufnahme_seit: float = 0.0
    atmen: bool = True
    _log: list[str] = field(default_factory=list)

    def setze(self, zustand: str | None, sekunden: float = 4.0) -> None:
        """„zuhoeren“ (läuft nach `sekunden` ab), „denkt“ (bis es wieder aufgehoben wird) oder None."""
        if zustand is not None and zustand not in ZUSTAENDE:
            raise ValueError(f"unbekannter Zustand {zustand!r}")
        if zustand is None and self.zustand == "zuhoeren":
            return                                                             # Zuhören läuft von selbst aus
        self.zustand = zustand
        self.zustand_bis = self.t + (max(0.5, min(30.0, sekunden)) if zustand == "zuhoeren" else 3600.0)

    def spielen(self, aufnahme: Aufnahme) -> None:
        self.aufnahme, self.aufnahme_seit = aufnahme, self.t

    def abbrechen(self) -> None:
        self.aufnahme = None

    @property
    def spielt(self) -> bool:
        return self.aufnahme is not None and self.t - self.aufnahme_seit < self.aufnahme.dauer

    def schritt(self, dt: float, mund: float, wach: bool = True) -> tuple[dict[str, float], list[float] | None,
                                                                         dict[str, float] | None]:
        """→ (Zusatz zur Kopflage, Antennen-Ziel oder None, Aufnahme-Bild oder None).

        Läuft eine Aufnahme, ist das dritte Ergebnis {lage…, antenne_r, antenne_l, koerper} und ersetzt den Kopf."""
        self.t += dt
        if self.zustand and self.t > self.zustand_bis:
            self.zustand = None
        k = min(1.0, dt / 0.15)
        self._mund += (max(0.0, min(1.0, mund)) - self._mund) * k
        if not wach:
            self.aufnahme = None
            return dict(LEER), None, None
        if self.aufnahme is not None:
            if self.spielt:
                lage, ant, koerper = self.aufnahme.bei(self.t - self.aufnahme_seit)
                return dict(LEER), ant, {**lage, "koerper": koerper, "antenne_r": ant[0], "antenne_l": ant[1]}
            self.aufnahme = None
        t = self.t
        zu = dict(LEER)
        ant: list[float] | None = None
        if self.atmen:                                                         # ~4,5 s je Atemzug
            zu["z"] += 0.0025 * math.sin(2 * math.pi * t / 4.5)
            zu["pitch"] += 0.012 * math.sin(2 * math.pi * t / 4.5 + 0.8)
        if self.zustand == "zuhoeren":
            zu["roll"] += 0.16
            zu["pitch"] -= 0.09
            zu["z"] += 0.004
            zuck = 0.06 * max(0.0, math.sin(2 * math.pi * t * 0.7)) ** 8       # ab und zu ein kurzes Zucken
            ant = [-0.02 - zuck, 0.02 + zuck]
        elif self.zustand == "denkt":
            zu["yaw"] += 0.14
            zu["pitch"] -= 0.12
            ant = [-0.45 - 0.35 * math.sin(2 * math.pi * t * 0.45), 0.45 - 0.35 * math.sin(2 * math.pi * t * 0.45 + 1.7)]
        a = self._mund
        if a > 0.02:                                                           # Kopf wippt beim Sprechen
            zu["pitch"] += a * 0.07 * math.sin(2 * math.pi * 2.1 * t)
            zu["roll"] += a * 0.05 * math.sin(2 * math.pi * 1.3 * t + 1.0)
            zu["yaw"] += a * 0.045 * math.sin(2 * math.pi * 0.8 * t + 2.0)
            zu["z"] += a * 0.003 * math.sin(2 * math.pi * 3.1 * t)
        if ant is None and self.atmen and a <= 0.02:
            s = 0.05 * math.sin(2 * math.pi * t / 6.0)
            ant = [-ANTENNE_RUHE + s, ANTENNE_RUHE + s]
        return zu, ant, None
