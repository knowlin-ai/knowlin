"""Tanzen für jede Bauart (seit 0.43, Fahrplan „Choreografie für jeden Körper“).

`musik_tanz()` und `gehoer_tanz()` geben je Tanzstil (`tanzstile.py`) das passende Verhalten: die Ente und Reachy
behalten ihre eigenen Tänze (`tanz.py`, `reachy_tanz.py`), alle übrigen tanzen hier:

- **Kopf** (Bauart `kopf`): Drehen und Nicken fährt der Tanz selbst im Takt (`tanzstile.KOPF`). Gefühle zeigt das
  Gesicht, hat der Körper LEDs, laufen die beim einstudierten Tanz als Lichttanz mit (nach Gehör frischt die Route
  `/api/gehoer` sie mit jeder Messung auf).
- **Arm, Hund** (`arm`, `vierbeiner`): Jeder Schritt geht als `tanz_schritt(name, sekunden, bpm)` an den Körper – der
  Arm fährt seine Haltungen oberhalb der Werkbank, der Hund macht seine Tricks am Platz. Ein Körper ohne
  `tanz_schritt` bleibt einfach stehen.

Es gelten dieselben Regeln wie überall: Der Not-Aus beendet den Tanz sofort (und `tanz_ende()` hält Arm, Hund und
Licht an), getanzt wird am Platz, nie mit Fahren.
"""

from __future__ import annotations

from typing import Any

from ..api import Head, Twist
from .behaviors import Behavior
from .engine import Command
from .reachy_tanz import ReachyGehoerTanz, ReachyMusikTanz
from .tanz import GehoerTanz, MusikTanz
from .tanzstile import TanzStil, kopf_lage, stil


def _kopf_befehl(name: str, beat: float, skala: float) -> Command:
    drehen, nicken = kopf_lage(name, beat, skala)
    rad = 3.14159265 / 180.0
    return Command(twist=Twist(), head=Head(0.0, -nicken * rad, drehen * rad, 0.0), mouth=0.0)


class _KoerperTakt:
    """Gemeinsames: Schritt an den Körper geben, Kopf im Takt, Licht dazu, am Ende alles anhalten."""

    def _koerper_init(self, st: TanzStil) -> None:
        self.stil = st
        self._bew = ""
        self._bew_beat0 = 0.0
        self.skala = 1.0

    def _hat(self, name: str) -> bool:
        return bool(self.engine and callable(getattr(self.engine.backend, name, None)))

    def _schritt_an_koerper(self, name: str, sekunden: float) -> None:
        if self._hat("tanz_schritt"):
            self.engine.fire(self.engine.backend.tanz_schritt(name, sekunden, self.bpm))

    def _licht(self, sekunden: float, schlag_in_s: float | None) -> None:
        if self._hat("lichttanz") and "led" in self.engine.backend.eigenschaften():
            self.engine.backend.lichttanz(sekunden, self.bpm, schlag_in_s)

    def _bewegen(self, beat: float) -> Command:
        if self.stil.key == "kopf" and self._bew:
            return _kopf_befehl(self._bew, max(0.0, beat - self._bew_beat0), self.skala)
        return Command(twist=Twist(), mouth=0.0)

    def on_stop(self) -> None:
        if self._hat("tanz_ende"):
            self.engine.backend.tanz_ende()


class KoerperMusikTanz(_KoerperTakt, MusikTanz):
    """Einstudierter Tanz zu Musik für Kopf, Arm und Hund: dieselben Schritte (`choreo`), ihr eigener Wortschatz."""

    name = "choreo"

    def __init__(self, choreo: dict[str, Any], st: TanzStil, titel: str = "", ab: float = 0.0) -> None:
        super().__init__(choreo, {}, titel, ab)
        self._koerper_init(st)

    def on_start(self, st) -> None:
        super().on_start(st)
        self._licht(self.dauer - self.ab, max(0.0, self.start - self.ab) if self.start > self.ab else None)

    def _takt(self, st, dt):
        t = self.elapsed + self.ab
        if t >= self.dauer:
            return self.finish("Tanz beendet")
        i, s = self._schritt(t)
        beat = max(0.0, (t - self.start) * self.bpm / 60.0)
        if i != self._aktiv:
            self._aktiv = i
            self._bew = ""
            art = s["art"] if s else "pause"
            if s and art != "pause":
                rest = max(0.5, s["t"] + int(s["takte"]) * 4 * 60.0 / self.bpm - t)
                if art in ("gefuehl", "pose"):
                    name = str(s.get("name", "")) if art == "gefuehl" else self.stil.schluss
                    self._schritt_an_koerper(name if name in self.stil.gefuehle else self.stil.schluss, rest)
                else:
                    stufe = 2 if art == "drehen" else 1
                    self._bew = self.stil.aufloesen(str(s.get("name") or art) if art == "trick" else art, stufe)
                    self._bew_beat0 = max(0.0, (s["t"] - self.start) * self.bpm / 60.0)
                    self._schritt_an_koerper(self._bew, rest)
        return self._bewegen(beat)

    def describe(self):
        return f"choreo ({self.titel or 'Tanz'}, {self.stil.key}, {self.bpm:.0f} bpm, {self.dauer:.0f}s)"


class KoerperGehoerTanz(_KoerperTakt, GehoerTanz):
    """Nach Gehör für Kopf, Arm und Hund: alle zwei Takte eine neue Bewegung passend zur Lautstärke; `ruhig` nur die
    ruhigen (Mitwippen zu Musik oder Radio)."""

    name = "gehoer"

    def __init__(self, st: TanzStil, ruhig: bool = False) -> None:
        super().__init__()
        self._koerper_init(st)
        self.ruhig = bool(ruhig)
        self.skala = 0.7 if self.ruhig else 1.0
        if self.ruhig:
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
        if self._schlag is None:                    # hört noch zu
            return Command(twist=Twist(), mouth=0.0)
        k = min(1.0, 2.0 * dt)
        self._schlag += dt * self.bpm / 60.0 + self._korrektur * k
        self._korrektur -= self._korrektur * k
        beat = max(0.0, self._schlag)
        segment = int(beat // 8)                    # alle zwei Takte eine neue Bewegung
        if segment != self._segment:
            self._segment = segment
            liste = self.stil.stufen[self.stufe()]
            self._art = self._bew = liste[segment % len(liste)]
            self._bew_beat0 = segment * 8.0
            self._schritt_an_koerper(self._bew, 8 * 60.0 / self.bpm)
        return self._bewegen(beat)

    def describe(self):
        return f"{'mitwippen' if self.ruhig else 'nach Gehör tanzen'} ({self.stil.key}, {self.bpm:.0f} bpm)"


TANZ_KLASSEN: tuple[type[Behavior], ...] = (MusikTanz, GehoerTanz, ReachyMusikTanz, ReachyGehoerTanz,
                                            KoerperMusikTanz, KoerperGehoerTanz)


def musik_tanz(stil_key: str, choreo: dict[str, Any], posen: dict[str, dict[str, float]] | None = None,
               titel: str = "", ab: float = 0.0) -> Behavior:
    """Der einstudierte Tanz in der Art der Bauart."""
    if stil_key == "kopf_antennen":
        return ReachyMusikTanz(choreo, titel, ab=ab)
    st = stil(stil_key)
    if st.key == "ente":
        return MusikTanz(choreo, posen or {}, titel, ab=ab)
    return KoerperMusikTanz(choreo, st, titel, ab=ab)


def gehoer_tanz(stil_key: str, ruhig: bool = False) -> GehoerTanz:
    """Tanzen nach Gehör in der Art der Bauart. Die Ente kennt kein ruhiges Mitwippen."""
    if stil_key == "kopf_antennen":
        return ReachyGehoerTanz(ruhig=ruhig)
    st = stil(stil_key)
    if st.key == "ente":
        return GehoerTanz()
    return KoerperGehoerTanz(st, ruhig=ruhig)

