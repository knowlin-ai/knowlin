"""Tanzen im Takt (seit 0.36, eigenes Modul seit 0.36.1): einstudierte Tänze zu Musik und Tanzen nach Gehör.

Motorik-Schicht: kennt nur Takt, Bewegungen und Gesten aus Tricks – den Tanzplan (Teile des Stücks, Muster, Speichern)
macht `duckpilot/choreo.py` im Kern.
"""

from __future__ import annotations

import math
from typing import Any

from ..api import Head, Pose, Twist
from .behaviors import Choreography, emotion
from .engine import Behavior, Command

# Tanzgesten aus Tricks je Energiestufe (seit 0.36.1, Hinweis aus dem Test: „die Tanzmoves müssen anhand der Tricks
# deutlich besser und passender werden“). Sie werden im Takt gestreckt: jede Wiederholung dauert ganze Schläge.
TANZGESTEN: dict[int, tuple[str, ...]] = {
    0: ("wippen", "traellern", "haltung", "aufhorchen", "nicken"),
    1: ("hibbeln", "umherspaehen", "jep", "naeaeae", "ja"),
    2: ("begeistert", "freude", "schuetteln", "jawohl", "lachen", "ungeduldig"),
}


def geste_im_takt(laenge_s: float, bpm: float, takte: int) -> tuple[int, float]:
    """Eine Geste (Länge in s) passend in einen Schritt von `takte` Takten legen: (Schläge je Wiederholung, Tempo).

    Jede Wiederholung dauert eine ganze Zahl von Schlägen, die den Schritt glatt teilt (1, 2, 4, 8 …); das Tempo bleibt
    zwischen halb und doppelt so schnell wie im Original – so sitzt jede Wiederholung auf dem Schlag."""
    schlag = 60.0 / max(40.0, min(220.0, float(bpm)))
    gesamt = max(1, int(takte)) * 4
    teiler = [b for b in range(1, gesamt + 1) if gesamt % b == 0]
    passend = [b for b in teiler if 0.5 <= laenge_s / (b * schlag) <= 2.0]
    b = min(passend or teiler, key=lambda x: abs(math.log(max(1e-6, laenge_s / (x * schlag)))))
    return b, max(0.25, laenge_s / (b * schlag))


class MusikTanz(Behavior):
    """Einstudierter Tanz zu einem Musikstück (Choreomodus, seit 0.36): Schritte aus `choreo.plane()` im Takt.

    Die Oberfläche spielt die Musik; dieser Tanz läuft ab dem Start im selben Takt mit (Schlag = 60/BPM s ab
    `start`). Posen fährt die echte Physik wirklich an (`backend.haltung`); kann der Körper das nicht (einfacher
    Simulator, Roboter), wird daraus eine angedeutete Geste mit Kopf und Haltung."""

    name = "choreo"
    channels = ("base", "head", "mouth", "pose")

    def __init__(self, choreo: dict[str, Any], posen: dict[str, dict[str, float]] | None = None, titel: str = "",
                 ab: float = 0.0) -> None:
        super().__init__()
        self.ab = max(0.0, float(ab or 0.0))     # Startmarke: ab dieser Stelle im Stück (Musik springt mit)
        self.bpm = max(40.0, min(220.0, float(choreo.get("bpm") or 110)))
        self.start = max(0.0, float(choreo.get("start") or 0.0))
        self.schritte = sorted(choreo.get("schritte") or [], key=lambda s: s["t"])
        self.dauer = max(2.0, float(choreo.get("dauer") or 0.0) or (self.schritte[-1]["t"] + 8 if self.schritte else 2.0))
        self.timeout = self.dauer - self.ab + 3
        self.posen = posen or {}
        self.titel = titel
        self._aktiv = -1
        self._angedeutet = False
        self._last_beat = -1
        self._geste: Choreography | None = None   # Geste aus Tricks im Schritt „gefuehl“ oder „trick“
        self._geste_t = 0.0
        self._tempo = 1.0

    def _schritt(self, t: float) -> tuple[int, dict[str, Any] | None]:
        tl = 4 * 60.0 / self.bpm
        for i in range(len(self.schritte) - 1, -1, -1):
            s = self.schritte[i]
            if s["t"] <= t < s["t"] + s["takte"] * tl:
                return i, s
            if s["t"] <= t:
                break
        return -1, None

    def tick(self, st, dt):
        return self._am_platz(st, self._takt(st, dt))

    def _takt(self, st, dt):
        t = self.elapsed + self.ab
        if t >= self.dauer:
            return self.finish("Tanz beendet")
        i, s = self._schritt(t)
        beat = max(0.0, (t - self.start) * self.bpm / 60.0)
        b = int(beat)
        mouth = 0.5 if (beat % 1.0) < 0.2 and b % 2 == 0 else 0.0
        art = s["art"] if s else "pause"
        if b != self._last_beat and t >= self.start:
            self._last_beat = b
            if b % 8 == 0 and self.engine and s is not None and s["art"] not in ("pause", "pose"):
                self.engine.fire(self.engine.backend.sound("chirp"))
            self._antennen_im_takt(b, art)
        if i != self._aktiv:
            self._aktiv = i
            self._angedeutet = False
            if s and art == "pose" and self.engine:
                gelenke = self.posen.get(s.get("name", ""))
                tl = 4 * 60.0 / self.bpm
                if gelenke:
                    self.engine.fire(self._pose_an(gelenke, max(0.3, s["takte"] * tl - 1.3)))
                else:
                    self._angedeutet = True
            self._geste = None
            self._tempo = 1.0
            if s and art in ("gefuehl", "trick") and self.engine:
                try:                     # die echte Geste aus Tricks (Pollens Emotionen, eigene Gesten)
                    self._geste = emotion(str(s.get("name", "")), robot=st.backend == "robotd")
                    self._geste.engine = self.engine
                    self._geste.overlay = True          # keine Skills (hinsetzen o. ä.) mitten im Tanz
                    self._geste_t = s["t"] if art == "trick" else t
                    if art == "trick":                  # Tanzgeste: im Takt gestreckt, Wiederholung auf dem Schlag
                        schlaege, self._tempo = geste_im_takt(self._geste.length, self.bpm, int(s["takte"]))
                        self._geste.loops = max(1, int(s["takte"]) * 4 // schlaege)
                except ValueError:
                    self.engine.fire(self.engine.backend.sound("greet"))
        if art == "pose":
            if self._angedeutet:      # angedeutete Pose: Kopf hoch, Gewicht zur Seite – mit den Mitteln von robotd
                return Command(twist=Twist(), head=Head(-0.2, -0.35, 0.3, 0.25), pose=Pose(-0.01, 0.25, 0.1), mouth=0.0)
            return Command(twist=Twist(), mouth=0.0)
        if art in ("gefuehl", "trick") and self._geste is not None and not self._geste.done:
            self._geste.elapsed = (t - self._geste_t) * self._tempo
            cmd = self._geste.tick(st, dt)
            if cmd is not None:
                cmd.twist = Twist()                     # Gesten im Tanz am Platz
                return cmd
        return self._bewegung(art, beat, mouth, richtung=1.0 if i % 2 == 0 else -1.0, takte=int(s["takte"]) if s else 2)

    def on_start(self, st) -> None:
        self._platz = (st.x, st.y)                 # hier wird getanzt – sie bleibt an ihrem Platz

    PLATZ_TOLERANZ_M = 0.03
    PLATZ_MAX_MS = 0.06

    def _am_platz(self, st, cmd: Command | None) -> Command | None:
        """Gegen das Wegdriften (Hinweis aus dem Test: „die Ente geht beim Tanzen immer weiter rückwärts“): Die Geh-Policy
        rutscht bei Gewichtsverlagerung und Kopfbewegung langsam weg. Weicht sie mehr als 3 cm vom Startplatz ab,
        kommt ein kleiner Fahrbefehl zurück zur Mitte dazu (höchstens 6 cm/s, im Körper-Rahmen)."""
        platz = getattr(self, "_platz", None)
        if cmd is None or platz is None or st is None or cmd.twist is None:
            return cmd
        dx, dy = platz[0] - st.x, platz[1] - st.y
        if math.hypot(dx, dy) < self.PLATZ_TOLERANZ_M:
            return cmd
        c, s = math.cos(st.yaw), math.sin(st.yaw)
        ex, ey = c * dx + s * dy, -s * dx + c * dy
        k, m = 0.8, self.PLATZ_MAX_MS
        cmd.twist = Twist(cmd.twist.vx + max(-m, min(m, k * ex)), cmd.twist.vy + max(-m, min(m, k * ey)), cmd.twist.vyaw)
        return cmd

    def _bewegung(self, art: str, beat: float, mouth: float, richtung: float = 1.0, takte: int = 2) -> Command:
        """Die einfachen Tanzbewegungen im Takt (auch für das Tanzen nach Gehör)."""
        ph = 2 * math.pi * beat
        b = int(beat)
        if art in ("gefuehl", "trick"):
            bob = math.sin(ph)
            return Command(twist=Twist(), head=Head(-0.2 * bob, -0.3 + 0.25 * bob, 0.25 * math.sin(ph / 2), 0.0),
                           pose=Pose(-0.012 + 0.01 * bob, 0.0, 0.1 * bob), mouth=0.6 if (beat % 1.0) < 0.3 else 0.1)
        if art == "pause":
            return Command(twist=Twist(), head=Head(0.0, 0.1, 0.0, 0.0), pose=Pose(), mouth=0.0)
        if art == "wippen":
            bob = math.sin(ph)
            return Command(twist=Twist(), head=Head(0.0, 0.1 * bob, 0.0, 0.0),
                           pose=Pose(-0.015 + 0.012 * bob, 0.0, 0.0), mouth=mouth)
        if art == "nicken":
            bob = math.sin(ph)
            return Command(twist=Twist(), head=Head(-0.15 * bob, 0.35 * bob, 0.15 * math.sin(ph / 4), 0.0),
                           pose=Pose(-0.012 + 0.01 * bob, 0.0, 0.12 * bob), mouth=mouth)
        if art == "wackeln":
            sway = math.sin(ph / 2)
            return Command(twist=Twist(0.0, 0.0, 0.5 * sway), head=Head(0.0, 0.1, -0.3 * sway, -0.3 * sway),
                           pose=Pose(-0.008, 0.2 * sway, 0.0), mouth=mouth)
        if art == "schritt":
            # Bein zu Bein: je Schlag ein kleiner Seitschritt, abwechselnd links und rechts – Gewicht aufs Standbein
            seite = 1.0 if b % 2 == 0 else -1.0
            hub = math.sin(math.pi * (beat % 1.0))
            return Command(twist=Twist(0.0, 0.09 * seite * hub, 0.0), head=Head(0.0, 0.05, -0.15 * seite, -0.25 * seite * hub),
                           pose=Pose(-0.008, 0.16 * seite * hub, 0.0), mouth=mouth)
        if art == "wiegen":
            # Gewicht von Bein zu Bein verlagern, ohne zu treten – ein Wiegen über zwei Schläge
            w = math.sin(ph / 2)
            return Command(twist=Twist(), head=Head(0.0, 0.08, -0.12 * w, -0.3 * w), pose=Pose(-0.01, 0.22 * w, 0.0), mouth=mouth)
        # drehen: eine ganze Drehung über den Schritt (so schnell sie darf), die Richtung wechselt von Schritt zu Schritt
        tempo = min(1.0, 2 * math.pi / max(0.5, takte * 4 * 60.0 / self.bpm))
        return Command(twist=Twist(0.0, 0.0, tempo * richtung), head=Head(0.0, -0.1, 0.35 * richtung, 0.2 * math.sin(ph)),
                       pose=Pose(-0.005, 0.12 * richtung, 0.0), mouth=mouth)

    def _antennen_im_takt(self, b: int, art: str) -> None:
        """Enten mit Antennen (Open Duck Mini, seit 0.38.13): die Antennen schlagen im Wechsel auf jeden Schlag mit –
        weit bei Schritten, Drehungen und Gesten, klein bei ruhigen Bewegungen. Reachy tanzt mit eigenen Bewegungen
        (`reachy_tanz`), die Microduck hat keine Antennen."""
        if self.engine is None or art in ("pause", "pose"):
            return
        be = self.engine.backend
        setzen = getattr(be, "antennen_setzen", None)
        if setzen is None or getattr(be, "koerper_art", "") == "reachy_mini" or "antennen" not in be.eigenschaften():
            return
        weit = 50.0 if art in ("schritt", "drehen", "trick", "gefuehl", "wackeln") else 25.0
        r, l = (weit, 5.0) if b % 2 == 0 else (5.0, weit)
        self.engine.fire(setzen(-math.radians(r), math.radians(l), 60.0 / self.bpm + 0.15))

    def takt(self) -> tuple[float, float, str] | None:
        """Für die anderen Enten (Schwarm): Tempo, Schlag seit Beginn und die Bewegung gerade."""
        t = self.elapsed + self.ab
        _, s = self._schritt(t)
        return self.bpm, max(0.0, (t - self.start) * self.bpm / 60.0), (s or {}).get("art", "wiegen")

    async def _pose_an(self, gelenke: dict[str, float], sekunden: float) -> None:
        res = await self.engine.backend.haltung(gelenke, sekunden)
        if not res.accepted:
            self._angedeutet = True

    def describe(self):
        return f"choreo ({self.titel or 'Tanz'}, {self.bpm:.0f} bpm, {self.dauer:.0f}s)"


class GehoerTanz(MusikTanz):
    """Tanzen nach Gehör (seit 0.36.1): Musik aus dem Raum – Radio, Spotify, YouTube.

    Die Oberfläche hört übers Mikrofon mit (das Audio bleibt im Browser) und schickt nur Zahlen: Tempo, wo der letzte
    Schlag war, Lautstärke 0..1. Daraus tanzt sie live: alle zwei Takte ein neuer Schritt, passend zur Lautstärke – ruhig
    wippen und nicken, laut wackeln und drehen, dazwischen Tanzgesten aus Tricks im Takt. Hört sie nichts mehr (6 s ohne
    Meldung oder 8 s Stille), hört sie auf."""

    name = "gehoer"
    STILLE_S = 8.0
    OHNE_MELDUNG_S = 6.0
    # Je Lautstärke vier Abschnitte à zwei Takte, reihum. Auch leise Musik: Bein zu Bein und eine Drehung (# Hinweis 1.11.: „bewegt sich gar nicht, sondern wackelt nur“)
    MUSTER = {0: ("schritt", "trick", "wiegen", "drehen"), 1: ("schritt", "drehen", "trick", "schritt"),
              2: ("schritt", "drehen", "trick", "drehen")}

    def __init__(self) -> None:
        super().__init__({"bpm": 110, "schritte": [], "dauer": 900.0}, {}, "nach Gehör")
        self.timeout = 15 * 60
        self.anker: float | None = None      # Zeitpunkt eines Schlags (in elapsed-Sekunden)
        self.energie = 0.0
        self._gemeldet = 0.0
        self._leise_seit: float | None = None
        self._segment = -1
        self._art = "wippen"
        # Fortlaufender Schlagzähler. Bis 0.36.3 wurde er mit jeder Messung (alle 1,5 s) auf den letzten Schlag
        # zurückgesetzt – der Abschnitt blieb so immer der erste: nie gedreht, keine Tanzgesten, leise nur Wiegen.
        # Jetzt läuft er weiter; eine Messung verschiebt nur sanft die Phase (wie eine PLL).
        self._schlag: float | None = None
        self._korrektur = 0.0

    def hoeren(self, bpm: float, schlag_vor_s: float, energie: float) -> None:
        """Neue Messung aus der Oberfläche: Tempo, Sekunden seit dem letzten Schlag, Lautstärke 0..1."""
        self.bpm = max(60.0, min(200.0, float(bpm)))
        self.anker = self.elapsed - max(0.0, min(2.0, float(schlag_vor_s)))
        phase = ((self.elapsed - self.anker) * self.bpm / 60.0) % 1.0
        if self._schlag is None:
            self._schlag = phase
        else:                                     # kürzester Weg zur gemessenen Phase, −0,5 … +0,5 Schlag
            self._korrektur = ((phase - self._schlag % 1.0 + 0.5) % 1.0) - 0.5
        self.energie = max(0.0, min(1.0, float(energie)))
        self._gemeldet = self.elapsed
        if self.energie < 0.08:
            self._leise_seit = self._leise_seit if self._leise_seit is not None else self.elapsed
        else:
            self._leise_seit = None

    def takt(self) -> tuple[float, float, str] | None:
        if self._schlag is None:
            return None
        return self.bpm, self._schlag, self._art

    def stufe(self) -> int:
        return 0 if self.energie < 0.35 else 1 if self.energie < 0.7 else 2

    def _takt(self, st, dt):
        t = self.elapsed
        if t - self._gemeldet > self.OHNE_MELDUNG_S:
            return self.finish("Keine Musik mehr gehört")
        if self._leise_seit is not None and t - self._leise_seit > self.STILLE_S:
            return self.finish("Die Musik ist aus")
        if self._schlag is None:                    # hört noch zu: Kopf leicht schief
            return Command(twist=Twist(), head=Head(0.0, 0.1, 0.0, 0.2), pose=Pose(), mouth=0.0)
        k = min(1.0, 2.0 * dt)                      # Phasenfehler in ≈ 0,5 s ausgleichen, ohne zu springen
        self._schlag += dt * self.bpm / 60.0 + self._korrektur * k
        self._korrektur -= self._korrektur * k
        beat = max(0.0, self._schlag)
        segment = int(beat // 8)                    # alle zwei Takte ein neuer Schritt
        if segment != self._segment:
            self._segment = segment
            stufe = self.stufe()
            self._art = self.MUSTER[stufe][segment % 4]
            self._geste = None
            if self._art == "trick" and self.engine:
                liste = TANZGESTEN[stufe]
                try:
                    self._geste = emotion(liste[(segment // 4) % len(liste)], robot=st.backend == "robotd")
                    self._geste.engine = self.engine
                    self._geste.overlay = True
                    schlaege, self._tempo = geste_im_takt(self._geste.length, self.bpm, 2)
                    self._geste.loops = max(1, 8 // schlaege)
                    self._geste_t = t
                except ValueError:
                    self._geste = None
            if segment % 4 == 0 and self.engine and stufe > 0:
                self.engine.fire(self.engine.backend.sound("chirp"))
        if int(beat) != self._last_beat:
            self._last_beat = int(beat)
            self._antennen_im_takt(int(beat), self._art)
        if self._art == "trick" and self._geste is not None and not self._geste.done:
            self._geste.elapsed = (t - self._geste_t) * self._tempo
            cmd = self._geste.tick(st, dt)
            if cmd is not None:
                cmd.twist = Twist()
                return cmd
        mouth = 0.5 if (beat % 1.0) < 0.2 and int(beat) % 2 == 0 else 0.0
        return self._bewegung("wiegen" if self._art == "trick" else self._art, beat, mouth,
                              richtung=1.0 if (segment // 2) % 2 == 0 else -1.0, takte=2)

    def describe(self):
        return f"nach Gehör tanzen ({self.bpm:.0f} bpm)"
