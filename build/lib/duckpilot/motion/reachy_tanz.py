"""Reachys eigener Tanz (seit 0.38.13, Hinweis aus dem Test 5.11.: „der tanzmodus ist nicht auf reachy angepasst“).

Reachy Mini hat keine Beine und keinen Schnabel – die Tanzgesten der Ente (Bein zu Bein, Posen, Quaks) passen nicht.
Reachy tanzt mit **Kopf** (Stewart-Plattform: nicken, wiegen, kreisen, hoch und runter), **Antennen** (im Takt,
gegenläufig, Schläge) und **Körperdrehung** auf dem Sockel (bei Refrain und viel Energie).

`REACHY_TANZ`: Name → Keyframes im Choreografie-Format (`reachy_gesten.py`), aber `t` in **Schlägen** statt Sekunden –
`bewegung()` streckt sie auf das Tempo des Stücks. Eine Bewegung wiederholt sich, bis ihr Schritt vorbei ist; jede
Wiederholung endet, wo sie begann (gleiche Werte bei t = 0 und am Ende). Zusätzlich zum Choreografie-Format:
`koerper.drehen` = Körperdrehung in Grad gegenüber dem Platz zu Tanzbeginn (+ = links herum); die fährt der Tanz selbst
an (`ReachyMusikTanz`), nicht die Choreografie. Keine Laute (`ton`/`klang`) – Reachy ist keine Ente.

Grenzen: Die Werte bleiben in dem, was Pollens Stewart-Plattform sicher erreicht – auch ohne Pollens Modell
(`reachy_kinematik.ersatz_erreichbar`, geprüft in `tests/test_reachy_tanz.py`). Kippt der Kopf, geht er dabei etwas
hoch; was trotzdem nicht passt, nimmt `begrenzen()` im Körper zurück.

Tanzpläne für Reachy macht `choreo.plane(…, reachy=True)`; Mitwippen zu Musik oder Radio (wie Pollens App „Reachy Mini
Radio“) ist `ReachyGehoerTanz(ruhig=True)`.
"""

from __future__ import annotations

import math
from typing import Any

from ..api import Head, Pose, Twist, wrap_angle
from .behaviors import Choreography, emotion, smoothstep
from .engine import Command
from .tanz import GehoerTanz, MusikTanz

# ── Bewegungen (t in Schlägen) ────────────────────────────────────────────────────────────────────────────────────
REACHY_TANZ: dict[str, list[dict[str, Any]]] = {
    # ruhig
    "kopfnicken": [        # nickt auf jeden Schlag, Antennen atmen mit
        {"t": 0.0, "kopf": {"nicken": 6}, "koerper": {"hoehe_mm": 3}, "antennen": [15, 15]},
        {"t": 0.5, "kopf": {"nicken": -2}, "koerper": {"hoehe_mm": 5}, "antennen": [30, 30]},
        {"t": 1.0, "kopf": {"nicken": 6}, "koerper": {"hoehe_mm": 3}},
    ],
    "wiegen": [            # Kopf wiegt seitlich über zwei Schläge, Antennen kippen mit
        {"t": 0.0, "kopf": {"neigen": 5, "drehen": 4}, "koerper": {"hoehe_mm": 4}, "antennen": [35, 5]},
        {"t": 1.0, "kopf": {"neigen": -5, "drehen": -4}, "koerper": {"hoehe_mm": 4}, "antennen": [5, 35]},
        {"t": 2.0, "kopf": {"neigen": 5, "drehen": 4}, "koerper": {"hoehe_mm": 4}},
    ],
    "wippen": [            # hoch und runter im Takt, wie leises Mitwippen
        {"t": 0.0, "kopf": {"nicken": 2}, "koerper": {"hoehe_mm": 0}, "antennen": [10, 10]},
        {"t": 0.5, "kopf": {"nicken": -3}, "koerper": {"hoehe_mm": 7}, "antennen": [25, 25]},
        {"t": 1.0, "kopf": {"nicken": 2}, "koerper": {"hoehe_mm": 0}},
    ],
    "antennen_takt": [     # Antennen gegenläufig je Schlag, der Kopf nickt leicht
        {"t": 0.0, "kopf": {"nicken": 3}, "koerper": {"hoehe_mm": 3}, "antennen": [45, -5]},
        {"t": 0.5, "kopf": {"nicken": -1}, "koerper": {"hoehe_mm": 4}},
        {"t": 1.0, "kopf": {"nicken": 3}, "koerper": {"hoehe_mm": 3}, "antennen": [-5, 45]},
        {"t": 1.5, "kopf": {"nicken": -1}, "koerper": {"hoehe_mm": 4}},
        {"t": 2.0, "kopf": {"nicken": 3}, "koerper": {"hoehe_mm": 3}},
    ],
    "umschauen": [         # schaut im Takt nach links und rechts
        {"t": 0.0, "kopf": {"nicken": -3}, "koerper": {"hoehe_mm": 5}, "antennen": [20, 20]},
        {"t": 1.0, "kopf": {"nicken": -3, "drehen": 14}, "koerper": {"hoehe_mm": 5}, "antennen": [35, 10]},
        {"t": 2.0, "kopf": {"nicken": -3}, "koerper": {"hoehe_mm": 5}, "antennen": [20, 20]},
        {"t": 3.0, "kopf": {"nicken": -3, "drehen": -14}, "koerper": {"hoehe_mm": 5}, "antennen": [10, 35]},
        {"t": 4.0, "kopf": {"nicken": -3}, "koerper": {"hoehe_mm": 5}},
    ],
    # mittel
    "kopfkreisen": [       # Kopf kreist über einen Takt
        {"t": 0.0, "kopf": {"nicken": -6}, "koerper": {"hoehe_mm": 5}, "antennen": [40, 40]},
        {"t": 1.0, "kopf": {"neigen": 6}, "koerper": {"hoehe_mm": 5}, "antennen": [50, 10]},
        {"t": 2.0, "kopf": {"nicken": 6}, "koerper": {"hoehe_mm": 5}, "antennen": [15, 15]},
        {"t": 3.0, "kopf": {"neigen": -6}, "koerper": {"hoehe_mm": 5}, "antennen": [10, 50]},
        {"t": 4.0, "kopf": {"nicken": -6}, "koerper": {"hoehe_mm": 5}},
    ],
    "antennen_schlag": [   # beide Antennen schlagen auf jeden Schlag nach außen
        {"t": 0.0, "kopf": {"nicken": 4}, "koerper": {"hoehe_mm": 3}, "antennen": [75, 75]},
        {"t": 0.35, "kopf": {"nicken": -2}, "koerper": {"hoehe_mm": 5}, "antennen": [10, 10]},
        {"t": 1.0, "kopf": {"nicken": 4}, "koerper": {"hoehe_mm": 3}},
    ],
    "hochrunter": [        # über zwei Schläge hoch – Antennen auf – und wieder runter
        {"t": 0.0, "kopf": {"nicken": 3}, "koerper": {"hoehe_mm": 0}, "antennen": [15, 15]},
        {"t": 1.0, "kopf": {"nicken": -6}, "koerper": {"hoehe_mm": 8}, "antennen": [60, 60]},
        {"t": 2.0, "kopf": {"nicken": 3}, "koerper": {"hoehe_mm": 0}},
    ],
    "seitblick": [         # Blick zur Seite auf Schlag 1, zur anderen auf Schlag 3
        {"t": 0.0, "kopf": {}, "koerper": {"hoehe_mm": 6}, "antennen": [20, 20]},
        {"t": 0.5, "kopf": {"drehen": 22, "neigen": 4}, "koerper": {"hoehe_mm": 6}, "antennen": [60, 15]},
        {"t": 1.5, "kopf": {"drehen": 22, "neigen": 4}, "koerper": {"hoehe_mm": 6}},
        {"t": 2.0, "kopf": {}, "koerper": {"hoehe_mm": 6}, "antennen": [20, 20]},
        {"t": 2.5, "kopf": {"drehen": -22, "neigen": -4}, "koerper": {"hoehe_mm": 6}, "antennen": [15, 60]},
        {"t": 3.5, "kopf": {"drehen": -22, "neigen": -4}, "koerper": {"hoehe_mm": 6}},
        {"t": 4.0, "kopf": {}, "koerper": {"hoehe_mm": 6}},
    ],
    # laut
    "koerper_drehen": [    # der ganze Körper dreht hin und her (zwei Takte), Kopf nickt, Antennen im Wechsel
        {"t": 0.0, "kopf": {"nicken": 4}, "koerper": {"hoehe_mm": 6, "drehen": 0}, "antennen": [60, 20]},
        {"t": 1.0, "kopf": {"nicken": -3, "drehen": -6}, "koerper": {"hoehe_mm": 6}, "antennen": [20, 60]},
        {"t": 2.0, "kopf": {"nicken": 4, "drehen": -8}, "koerper": {"hoehe_mm": 6, "drehen": 25}, "antennen": [60, 20]},
        {"t": 3.0, "kopf": {"nicken": -3, "drehen": -6}, "koerper": {"hoehe_mm": 6}, "antennen": [20, 60]},
        {"t": 4.0, "kopf": {"nicken": 4}, "koerper": {"hoehe_mm": 6, "drehen": 0}, "antennen": [60, 20]},
        {"t": 5.0, "kopf": {"nicken": -3, "drehen": 6}, "koerper": {"hoehe_mm": 6}, "antennen": [20, 60]},
        {"t": 6.0, "kopf": {"nicken": 4, "drehen": 8}, "koerper": {"hoehe_mm": 6, "drehen": -25}, "antennen": [60, 20]},
        {"t": 7.0, "kopf": {"nicken": -3, "drehen": 6}, "koerper": {"hoehe_mm": 6}, "antennen": [20, 60]},
        {"t": 8.0, "kopf": {"nicken": 4}, "koerper": {"hoehe_mm": 6, "drehen": 0}},
    ],
    "party": [             # nicken, Antennen schlagen, Körper schwingt mit
        {"t": 0.0, "kopf": {"nicken": 5}, "koerper": {"hoehe_mm": 4, "drehen": 0}, "antennen": [80, 80]},
        {"t": 0.4, "kopf": {"nicken": -4}, "koerper": {"hoehe_mm": 7}, "antennen": [15, 15]},
        {"t": 1.0, "kopf": {"nicken": 5}, "koerper": {"hoehe_mm": 4, "drehen": 12}, "antennen": [80, 80]},
        {"t": 1.4, "kopf": {"nicken": -4}, "koerper": {"hoehe_mm": 7}, "antennen": [15, 15]},
        {"t": 2.0, "kopf": {"nicken": 5}, "koerper": {"hoehe_mm": 4, "drehen": 0}, "antennen": [80, 80]},
        {"t": 2.4, "kopf": {"nicken": -4}, "koerper": {"hoehe_mm": 7}, "antennen": [15, 15]},
        {"t": 3.0, "kopf": {"nicken": 5}, "koerper": {"hoehe_mm": 4, "drehen": -12}, "antennen": [80, 80]},
        {"t": 3.4, "kopf": {"nicken": -4}, "koerper": {"hoehe_mm": 7}, "antennen": [15, 15]},
        {"t": 4.0, "kopf": {"nicken": 5}, "koerper": {"hoehe_mm": 4, "drehen": 0}},
    ],
    "antennen_wirbel": [   # Antennen wirbeln im halben Schlag gegeneinander, der Kopf hüpft
        {"t": 0.0, "kopf": {"nicken": -4}, "koerper": {"hoehe_mm": 2}, "antennen": [80, 0]},
        {"t": 0.5, "kopf": {"nicken": -4}, "koerper": {"hoehe_mm": 7}, "antennen": [0, 80]},
        {"t": 1.0, "kopf": {"nicken": -4}, "koerper": {"hoehe_mm": 2}},
    ],
    "kreisen_drehen": [    # Kopf kreist, der Körper dreht dabei langsam hin und her
        {"t": 0.0, "kopf": {"nicken": -6}, "koerper": {"hoehe_mm": 6, "drehen": 0}, "antennen": [50, 50]},
        {"t": 1.0, "kopf": {"neigen": 6}, "koerper": {"hoehe_mm": 6, "drehen": 15}, "antennen": [70, 15]},
        {"t": 2.0, "kopf": {"nicken": 6}, "koerper": {"hoehe_mm": 6, "drehen": 0}, "antennen": [20, 20]},
        {"t": 3.0, "kopf": {"neigen": -6}, "koerper": {"hoehe_mm": 6, "drehen": -15}, "antennen": [15, 70]},
        {"t": 4.0, "kopf": {"nicken": -6}, "koerper": {"hoehe_mm": 6, "drehen": 0}},
    ],
}

REACHY_TANZ_TEXT: dict[str, str] = {
    "kopfnicken": "Kopfnicken", "wiegen": "Wiegen", "wippen": "Hoch und runter wippen",
    "antennen_takt": "Antennen im Takt", "umschauen": "Umschauen", "kopfkreisen": "Kopfkreisen",
    "antennen_schlag": "Antennen-Schlag", "hochrunter": "Hoch und runter", "seitblick": "Seitenblick",
    "koerper_drehen": "Körper drehen", "party": "Party", "antennen_wirbel": "Antennen-Wirbel",
    "kreisen_drehen": "Kreisen und drehen",
}

# Je Energiestufe wie `TANZGESTEN` der Ente: ruhig, mittel, laut
REACHY_STUFEN: dict[int, tuple[str, ...]] = {
    0: ("kopfnicken", "wiegen", "wippen", "antennen_takt", "umschauen"),
    1: ("kopfkreisen", "antennen_schlag", "hochrunter", "seitblick", "wiegen"),
    2: ("koerper_drehen", "party", "antennen_wirbel", "kreisen_drehen"),
}
# Gefühle aus Reachys eigenen Gesten (`reachy_gesten.GESTEN`) für Höhepunkte und Schluss
REACHY_GEFUEHLE = ("begeistert", "freude", "staunen", "stolz", "ueberrascht")
# Schritte der Ente in Reachy-Bewegungen übersetzt (ältere Tänze, Claude, Knowlets)
AUS_ENTE = {"nicken": "kopfnicken", "wippen": "wippen", "wackeln": "wiegen", "wiegen": "wiegen",
            "schritt": "antennen_takt", "drehen": "koerper_drehen"}

# Wie weit die Bewegungen ausschlagen, je Energiestufe (ruhige Musik: kleiner)
SKALA = {0: 0.85, 1: 1.0, 2: 1.1}
KOERPER_MAX_GRAD = 30.0      # Körperdrehung beim Tanzen höchstens (Pollen erlaubt ±160°)
KOERPER_K = 3.0              # Regelung der Körperdrehung (1/s)


def laenge(name: str) -> float:
    """Länge einer Bewegung in Schlägen."""
    return float(REACHY_TANZ[name][-1]["t"])


def aufloesen(name: str, stufe: int = 1) -> str:
    """Name eines Tanzschritts → eine Bewegung von Reachy (Entenschritte und Unbekanntes werden übersetzt)."""
    if name in REACHY_TANZ:
        return name
    if name in AUS_ENTE:
        return AUS_ENTE[name]
    liste = REACHY_STUFEN[max(0, min(2, stufe))]
    return liste[sum(map(ord, str(name))) % len(liste)]


def bewegung(name: str, bpm: float, schlaege: float, scale: float = 1.0) -> Choreography:
    """Eine Reachy-Bewegung im Takt: Keyframes von Schlägen auf Sekunden gestreckt, so oft wiederholt, wie in
    `schlaege` hineinpasst (mindestens einmal). Keine Laute."""
    spec = REACHY_TANZ[aufloesen(name)]
    schlag = 60.0 / max(40.0, min(220.0, float(bpm)))
    n = laenge(aufloesen(name))
    sekunden = [{k: v for k, v in kf.items() if k not in ("ton", "sound", "klang")} | {"t": kf["t"] * schlag}
                for kf in spec]
    ch = Choreography.from_spec(sekunden, max(1, int(round(float(schlaege) / n)) or 1), aufloesen(name), scale=scale)
    ch.overlay = True
    return ch


def koerper_winkel(name: str, beat: float) -> float | None:
    """Körperdrehung (Grad) einer Bewegung beim Schlag `beat` seit ihrem Beginn – None, wenn sie den Körper nicht dreht."""
    kfs = [(float(k["t"]), float(k["koerper"]["drehen"])) for k in REACHY_TANZ[aufloesen(name)]
           if "drehen" in (k.get("koerper") or {})]
    if not kfs:
        return None
    t = beat % laenge(aufloesen(name))
    for (ta, a), (tb, b) in zip(kfs, kfs[1:]):
        if ta <= t <= tb:
            return a + (b - a) * smoothstep((t - ta) / max(1e-6, tb - ta))
    return kfs[-1][1]


class _ReachyTakt:
    """Gemeinsames für Reachys Tänze: Bewegung im Takt abspielen, Körperdrehung regeln, nie Laute, nie Fahren."""

    def _reachy_init(self) -> None:
        self._yaw0: float | None = None
        self._bew: Choreography | None = None
        self._bew_name = ""
        self._bew_beat0 = 0.0
        self._ziel_grad = 0.0
        self._drehung = True

    def on_start(self, st) -> None:
        self._yaw0 = st.yaw                         # hier steht er – die Körperdrehung pendelt um diesen Platz

    def _am_platz(self, st, cmd):                   # Reachy steht fest: kein Zurückfahren zur Mitte
        return cmd

    def _neu(self, name: str, beat0: float, schlaege: float, stufe: int) -> None:
        self._bew_name = aufloesen(name, stufe)
        self._bew = bewegung(self._bew_name, self.bpm, schlaege, SKALA.get(stufe, 1.0) * getattr(self, "skala", 1.0))
        self._bew.engine = self.engine
        self._bew_beat0 = beat0

    def _spiele(self, st, dt, beat: float) -> Command:
        """Den Befehl im Takt: Kopf und Höhe aus der Bewegung, Antennen feuert die Choreografie, Körper dreht der Tanz."""
        cmd = None
        ziel = 0.0
        if self._bew is not None and not self._bew.done:
            seit = max(0.0, beat - self._bew_beat0)
            self._bew.elapsed = seit * 60.0 / self.bpm
            cmd = self._bew.tick(st, dt)
            w = koerper_winkel(self._bew_name, seit) if self._drehung else None
            ziel = 0.0 if w is None else max(-KOERPER_MAX_GRAD, min(KOERPER_MAX_GRAD, w))
        if cmd is None:
            cmd = Command(head=Head(0.0, -0.03, 0.0, 0.0), pose=Pose(0.004, 0.0, 0.0))
        cmd.mouth = 0.0
        cmd.twist = Twist(0.0, 0.0, self._koerper(st, dt, ziel))
        return cmd

    def _koerper(self, st, dt: float, ziel_grad: float) -> float:
        """Drehrate für die Körperdrehung: Vorsteuerung aus der Änderung des Ziels plus Regelung zum Ziel."""
        if self._yaw0 is None or st is None:
            return 0.0
        vor = (ziel_grad - self._ziel_grad) / max(1e-3, dt)
        self._ziel_grad = ziel_grad
        ist = wrap_angle(st.yaw - self._yaw0)
        rate = math.radians(vor) + KOERPER_K * (math.radians(ziel_grad) - ist)
        return max(-1.0, min(1.0, rate))


class ReachyMusikTanz(_ReachyTakt, MusikTanz):
    """Einstudierter Tanz zu Musik für Reachy Mini: dieselben Schritte (`choreo`), aber Reachys Bewegungen.

    Schritte `trick` mit Namen aus `REACHY_TANZ` laufen im Takt; Entenschritte (nicken, schritt, drehen …) werden
    übersetzt (`AUS_ENTE`); `gefuehl` spielt Reachys eigene Geste (`reachy_gesten`); `pose` wird zu „stolz“."""

    name = "choreo"

    def __init__(self, choreo: dict[str, Any], titel: str = "", ab: float = 0.0) -> None:
        super().__init__(choreo, {}, titel, ab)
        self._reachy_init()
        self.skala = 1.0

    def _takt(self, st, dt):
        t = self.elapsed + self.ab
        if t >= self.dauer:
            return self.finish("Tanz beendet")
        i, s = self._schritt(t)
        beat = max(0.0, (t - self.start) * self.bpm / 60.0)
        if i != self._aktiv:
            self._aktiv = i
            self._bew = None
            self._geste = None
            art = s["art"] if s else "pause"
            if s and art in ("gefuehl", "pose"):
                self._geste = _reachy_gefuehl(str(s.get("name", "")) if art == "gefuehl" else "stolz")
                self._geste.engine = self.engine
                self._geste_t = t
            elif s and art != "pause":
                stufe = 2 if art == "drehen" else 1
                beat0 = max(0.0, (s["t"] - self.start) * self.bpm / 60.0)
                self._neu(str(s.get("name") or art) if art in ("trick",) else art, beat0, int(s["takte"]) * 4, stufe)
        if self._geste is not None and not self._geste.done:
            self._geste.elapsed = t - self._geste_t
            cmd = self._geste.tick(st, dt)
            if cmd is not None:
                cmd.mouth = 0.0
                cmd.twist = Twist(0.0, 0.0, self._koerper(st, dt, 0.0))
                return cmd
        return self._spiele(st, dt, beat)

    def describe(self):
        return f"choreo ({self.titel or 'Tanz'}, Reachy, {self.bpm:.0f} bpm, {self.dauer:.0f}s)"


class ReachyGehoerTanz(_ReachyTakt, GehoerTanz):
    """Reachy tanzt nach Gehör – oder wippt nur mit (`ruhig`, Abschnitt „Mitwippen“ wie Pollens App „Reachy Mini
    Radio“): Die Oberfläche spielt ein Stück vom PC oder ein Webradio und schickt nur Tempo, letzten Schlag und
    Lautstärke. Alle zwei Takte eine neue Bewegung aus `REACHY_STUFEN` passend zur Lautstärke; ruhig nur die ruhigen,
    kleiner und ohne Körperdrehung."""

    name = "gehoer"

    def __init__(self, ruhig: bool = False) -> None:
        super().__init__()
        self._reachy_init()
        self.ruhig = bool(ruhig)
        self.skala = 0.8 if self.ruhig else 1.0
        self._drehung = not self.ruhig
        if self.ruhig:                  # Radio läuft länger, puffert mal, und leise Stellen sind kein Ende
            self.timeout = 60 * 60
            self.STILLE_S = 20.0
            self.OHNE_MELDUNG_S = 12.0

    def stufe(self) -> int:
        return 0 if self.ruhig else super().stufe()

    def _takt(self, st, dt):
        t = self.elapsed
        if t - self._gemeldet > self.OHNE_MELDUNG_S:
            return self.finish("Keine Musik mehr gehört")
        if self._leise_seit is not None and t - self._leise_seit > self.STILLE_S:
            return self.finish("Die Musik ist aus")
        if self._schlag is None:                    # hört noch zu: Kopf leicht schief, Antennen neugierig
            return Command(twist=Twist(), head=Head(0.0, -0.05, 0.0, 0.08), pose=Pose(0.004, 0.0, 0.0), mouth=0.0)
        k = min(1.0, 2.0 * dt)
        self._schlag += dt * self.bpm / 60.0 + self._korrektur * k
        self._korrektur -= self._korrektur * k
        beat = max(0.0, self._schlag)
        segment = int(beat // 8)                    # alle zwei Takte eine neue Bewegung
        if segment != self._segment:
            self._segment = segment
            stufe = self.stufe()
            liste = REACHY_STUFEN[stufe]
            self._art = liste[segment % len(liste)]
            self._neu(self._art, segment * 8.0, 8, stufe)
        return self._spiele(st, dt, beat)

    def describe(self):
        return f"{'mitwippen' if self.ruhig else 'nach Gehör tanzen'} (Reachy, {self.bpm:.0f} bpm)"


def _reachy_gefuehl(name: str) -> Choreography:
    """Reachys eigene Geste zu einem Gefühl (Höhepunkt im Tanz) – Unbekanntes wird „freude“. Nie Entengesten."""
    from .reachy_gesten import GESTEN

    key = name if name in GESTEN else "freude"
    ch = emotion(key, reachy=True)
    ch.overlay = True
    return ch


# Begrüßung beim Aufwecken (wie Pollens App „Reachy Mini Greetings“): Antennen hoch, Kopf heben, nicken, kurz zur
# Seite und wieder nach vorn – nur Kopf und Antennen, keine Körperdrehung (Choreografie-Format, Sekunden)
BEGRUESSUNG: list[dict[str, Any]] = [
    {"t": 0.0, "kopf": {"nicken": 6}, "koerper": {"hoehe_mm": 0}, "antennen": [100, 100]},
    {"t": 0.5, "kopf": {"nicken": -8}, "koerper": {"hoehe_mm": 7}, "antennen": [5, 5]},
    {"t": 1.0, "kopf": {"nicken": 4}, "koerper": {"hoehe_mm": 5}, "antennen": [40, 40]},
    {"t": 1.3, "kopf": {"nicken": -6}, "koerper": {"hoehe_mm": 7}, "antennen": [5, 5]},
    {"t": 1.6, "kopf": {"nicken": 3}, "koerper": {"hoehe_mm": 5}},
    {"t": 2.1, "kopf": {"nicken": -4, "drehen": 12, "neigen": 4}, "koerper": {"hoehe_mm": 6}, "antennen": [60, 15]},
    {"t": 2.7, "kopf": {"nicken": -4, "drehen": 12, "neigen": 4}, "koerper": {"hoehe_mm": 6}},
    {"t": 3.2, "kopf": {"nicken": -3}, "koerper": {"hoehe_mm": 4}, "antennen": [15, 15]},
    {"t": 3.8, "kopf": {}, "koerper": {}},
]


def begruessung() -> Choreography:
    """Reachys kurze Begrüßungsgeste beim Aufwecken (ohne Laute, ohne Körperdrehung – geht auch ohne „Beine“)."""
    return Choreography.from_spec(BEGRUESSUNG, title="begruessung")


def begruessung_text(name: str, nutzer: str, stunde: int, t: Any = None) -> str:
    """Der kurze Satz zur Begrüßung: Tageszeit, ggf. der Name des Menschen, der Name der Verkörperung.
    `t`: Übersetzer (i18n.t) – ohne ihn Deutsch."""
    teil = "morgen" if 5 <= stunde < 11 else "tag" if 11 <= stunde < 17 else "abend" if 17 <= stunde < 23 else "nacht"
    deutsch = {"morgen": "Guten Morgen", "tag": "Guten Tag", "abend": "Guten Abend", "nacht": "Hallo"}
    gruss = t(f"begruessung.{teil}") if t else deutsch[teil]
    an = f", {nutzer.strip()}" if nutzer and nutzer.strip() else ""
    name = (name or "Reachy").strip() or "Reachy"
    if t:
        return t("begruessung.satz", gruss=gruss, an=an, name=name)
    return f"{gruss}{an}! Ich bin {name}."
