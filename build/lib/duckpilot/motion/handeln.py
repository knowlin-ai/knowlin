"""Mit einer anderen Ente etwas tun (seit 0.37.3, „Anwählen und Handeln“): hingehen und begrüßen oder ärgern, ihr
hinterherlaufen.

Die Hauptente sieht die anderen Enten wie Dinge (Wahrnehmung, Art „ente“) und geht mit `Approach` hin. Angekommen
macht sie ihre Geste (begrüßen bzw. frech „nä-nä-nä“); im selben Moment antwortet die andere über `antwort` (der
Schwarm: zuwenden und nicken bzw. Kopf schütteln, empört quaken, zurückweichen). Ärgern ist Spiel – sie berührt die
andere nicht, Ausweichen und Körpergrenzen gelten wie immer.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from ..api import DuckState, Head, Twist, wrap_angle
from .behaviors import Approach, emotion
from .engine import Behavior, Command

GESTE = {"gruss": "begruessen", "aergern": "naeaeae"}
ABSTAND = {"gruss": 0.32, "aergern": 0.26}


class Begegnung(Behavior):
    """Zu einer anderen Ente gehen und sie begrüßen oder ärgern – die andere antwortet."""

    name = "begegnung"
    channels = ("base", "head")

    def __init__(self, ente: str, art: str = "gruss",
                 antwort: Callable[[str, str, tuple[float, float]], Any] | None = None) -> None:
        super().__init__()
        self.ente = ente
        self.art = art if art in GESTE else "gruss"
        self.antwort = antwort
        self.timeout = 50.0
        self.phase = "hin"
        self.inner: Behavior | None = None

    def _use(self, b: Behavior) -> None:
        b.engine = self.engine
        self.inner = b

    def on_start(self, st):
        self._use(Approach(self.ente, stop_at=ABSTAND[self.art], bearing_tol_deg=12.0))

    def kontakt_ziel(self, st: DuckState):
        return self.inner.kontakt_ziel(st) if self.inner is not None and self.phase == "hin" else None

    def tick(self, st, dt):
        cmd = self.inner._step(st, dt)
        if not self.inner.done:
            return cmd
        if self.phase == "hin":
            if getattr(self.inner, "failed", False) and not (self.inner.result or "").startswith("kommt nicht näher"):
                self.failed = True
                return self.finish(f"{self.ente}: {self.inner.result}")
            self.phase = "geste"
            if self.antwort is not None:
                self.antwort(self.ente, self.art, (st.x, st.y))
            self._use(emotion(GESTE[self.art]))
            return Command(twist=Twist())
        text = f"{self.ente} begrüßt" if self.art == "gruss" else f"{self.ente} geärgert"
        return self.finish(text)

    def on_stop(self):
        if self.inner is not None and not self.inner.done:
            self.inner.on_stop()

    def target(self):
        return self.inner.target() if self.inner is not None and self.phase == "hin" else None

    def describe(self):
        return f"{'begrüßen' if self.art == 'gruss' else 'ärgern'}: {self.ente}"


class Hinterher(Behavior):
    """Einer anderen Ente (oder einem Ding, das sich bewegt) mit etwa 35 cm Abstand folgen."""

    name = "hinterher"
    channels = ("base", "head")
    ABSTAND_M = 0.35

    def __init__(self, ziel: str, sekunden: float = 30.0) -> None:
        super().__init__()
        self.ziel = ziel.lower()
        self.sekunden = max(3.0, min(300.0, sekunden))
        self.timeout = self.sekunden + 2
        self.weg_seit = 0.0

    def tick(self, st, dt):
        if self.elapsed >= self.sekunden:
            return self.finish(f"{self.ziel} lange genug gefolgt")
        obj = next((o for o in st.perception.objects if self.ziel in str(o.get("name", "")).lower()), None)
        if obj is None:
            self.weg_seit += dt
            if self.weg_seit > 10.0:
                self.failed = True
                return self.finish(f"{self.ziel} aus den Augen verloren")
            return Command(twist=Twist(0.0, 0.0, 0.7), head=Head(0.0, 0.1, 0.0, 0.0))     # umschauen
        self.weg_seit = 0.0
        b = math.radians(obj["richtung_grad"])
        d = obj["entfernung_m"]
        vyaw = max(-1.0, min(1.0, 2.2 * wrap_angle(b)))
        vx = 0.0 if abs(b) > 0.7 else max(-0.06, min(0.16, (d - self.ABSTAND_M) * 0.9))
        return Command(twist=Twist(vx, 0.0, vyaw), head=Head(0.0, 0.05, max(-0.5, min(0.5, b * 0.5)), 0.0))

    def describe(self):
        return f"hinterher: {self.ziel}"
