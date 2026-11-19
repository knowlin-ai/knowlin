"""Elfmeter (seit 0.44, Fahrplan „Spiele“): fünf Schüsse vom Elfmeterpunkt auf ein Tor an der Wand.

Nur im einfachen Simulator – er legt den Ball vor jedem Schuss auf den Punkt (`ball_hinlegen`) und weiß, wo das Tor
steht (`tor_aufstellen`). Geschossen wird mit dem gezielten Schuss (`schuss.GezielterSchuss`), je Elfmeter genau ein
Versuch, auf eine zufällige Ecke (links, Mitte, rechts – aus Sicht der Schützin). Ein Tor zählt, wenn der Ball die
Torlinie zwischen den Pfosten erreicht.

Du bist im Tor: Bis der Ball liegt, kannst du in eine Ecke hechten (`hechten`). Ist es ihre Ecke, ist er gehalten.
Wie jedes Verhalten endet der Elfmeter mit dem Not-Aus sofort.
"""

from __future__ import annotations

import random
from typing import Any, Callable

from ..api import Twist
from .engine import Behavior, Command
from .schuss import GezielterSchuss

PUNKT_M = 0.8              # Elfmeterpunkt: so weit vor der Torlinie
ECKE_M = 0.22              # Zielpunkt in der Ecke: so weit neben der Tormitte
ZIELE: dict[str, tuple[str, int]] = {"links": ("die linke Ecke", 1), "mitte": ("die Mitte", 0),
                                      "rechts": ("die rechte Ecke", -1)}
LINIE_M = 0.08             # so nah an der Wand gilt der Ball als über der Linie
NACHSCHAU_S = 3.0          # so lange nach dem Schuss wird auf ein Tor gewartet
PAUSE_S = 1.5


class Elfmeter(Behavior):
    name = "elfmeter"
    channels = ("base", "head")

    def __init__(self, tor: dict[str, float], schuesse: int = 5,
                 melden: Callable[[dict[str, Any]], None] | None = None, seed: int | None = None) -> None:
        super().__init__()
        self.rng = random.Random(seed)
        self.seite = ""            # wohin sie gerade zielt
        self.gehechtet: str | None = None
        self.gehalten = 0
        self.tor = dict(tor)
        self.schuesse = max(1, min(10, int(schuesse)))
        self.melden = melden
        self.timeout = 150.0 * self.schuesse
        self.nr = 0
        self.tore = 0
        self.phase = "hinlegen"
        self._inner: Behavior | None = None
        self._getroffen = False
        self._seit = 0.0
        self.verlauf: list[bool] = []

    def _innen_links(self) -> float:
        """Richtung „links“ vom Schützen aus gesehen: Wer zur Wand bei −x schaut, hat links −y."""
        return -1.0 if self.tor["x"] < 0 else 1.0

    def hechten(self, seite: str) -> bool:
        """Torwart: in eine Ecke hechten – nur, solange der Schuss noch nicht entschieden ist, einmal je Schuss."""
        if seite not in ZIELE or self.phase != "schiessen" or self.gehechtet is not None:
            return False
        self.gehechtet = seite
        return True

    def _bericht(self, **extra: Any) -> None:
        if self.melden:
            self.melden({"schuss": self.nr, "schuesse": self.schuesse, "tore": self.tore, **extra})

    def _ball_im_tor(self) -> bool:
        lage = self.engine.backend.ball_lage() if self.engine else None
        if lage is None:
            return False
        x, y = lage[0], lage[1]
        return abs(x - self.tor["x"]) <= LINIE_M and abs(y - self.tor["y"]) <= self.tor["breite"] / 2

    def tick(self, st, dt):
        be = self.engine.backend if self.engine else None
        if be is None or not callable(getattr(be, "ball_hinlegen", None)):
            self.failed = True
            return self.finish("Elfmeter geht nur im einfachen Simulator")
        if self.phase == "hinlegen":
            richtung = -1.0 if self.tor["x"] < 0 else 1.0                       # vom Tor ins Zimmer
            ok, grund = be.ball_hinlegen(self.tor["x"] - richtung * PUNKT_M, self.tor["y"])
            if not ok:
                self.failed = True
                return self.finish(grund)
            self.seite = self.rng.choice(list(ZIELE))
            name, seite = ZIELE[self.seite]
            ziel = (self.tor["x"], self.tor["y"] + seite * ECKE_M * self._innen_links())
            self.gehechtet = None
            schuss = GezielterSchuss(ziel, name, ziel_r=None)
            schuss.VERSUCHE = 1                                                  # ein Elfmeter, ein Schuss
            schuss.engine = self.engine
            self._inner, self._getroffen, self.phase = schuss, False, "schiessen"
            self.nr += 1
            self._bericht(neu=True)                       # wohin sie zielt, verrät sie erst nach dem Schuss
        if self.phase == "schiessen":
            self._getroffen = self._getroffen or self._ball_im_tor()
            cmd = self._inner._step(st, dt) if self._inner else None
            if self._inner is None or self._inner.done:
                self.phase, self._seit = "nachschauen", 0.0
            return cmd if cmd is not None else Command(twist=Twist())
        if self.phase == "nachschauen":
            self._seit += dt
            self._getroffen = self._getroffen or self._ball_im_tor()
            if self._getroffen or self._seit >= NACHSCHAU_S:
                gehalten = self._getroffen and self.gehechtet == self.seite
                tor = self._getroffen and not gehalten
                self.tore += int(tor)
                self.gehalten += int(gehalten)
                self.verlauf.append(tor)
                self._bericht(tor=tor, gehalten=gehalten, seite=self.seite, gehechtet=self.gehechtet)
                if self.nr >= self.schuesse:
                    halten = f", {self.gehalten} gehalten" if self.gehalten else ""
                    return self.finish(f"{self.tore} von {self.schuesse} Elfmetern im Tor{halten}")
                self.phase, self._seit = "pause", 0.0
            return Command(twist=Twist())
        if self.phase == "pause":
            self._seit += dt
            if self._seit >= PAUSE_S:
                self.phase = "hinlegen"
            return Command(twist=Twist())
        return None

    def describe(self) -> str:
        return f"elfmeter ({self.nr}/{self.schuesse}, {self.tore} Tore)"
