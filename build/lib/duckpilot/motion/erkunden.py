"""Gründlich erkunden (seit 0.37.13, Hinweis aus dem Test „beim Kartieren ist er nicht so sehr gründlich“).

Bisher lief sie beim Erkunden frei herum und wich aus – Ecken blieben oft leer. Jetzt geht sie gezielt an die Ränder
des schon Erkundeten („Grenzen“: freie Zellen neben noch unbekannten) und sieht sich dort einmal um. Das wiederholt sich,
bis die Zeit um ist oder keine erreichbare Grenze mehr übrig ist. Wege plant sie auf dem schon Erkundeten um
Hindernisse herum (Route aus `karte.py`).
"""

from __future__ import annotations

import math
from typing import Any

from .behaviors import Turn
from .engine import Behavior, Command
from .faehigkeit import Faehigkeit
from .karte import ZELLE, Karte, Route, mitte, zelle

NACHBARN = ((1, 0), (-1, 0), (0, 1), (0, -1))


def grenzen(karte: Karte) -> list[tuple[int, int]]:
    """Freie Zellen, die an noch unbekannte grenzen – dort gibt es noch etwas zu sehen."""
    out = []
    for c in karte.zellen:
        if not karte.frei(c):
            continue
        if any((c[0] + di, c[1] + dj) not in karte.zellen for di, dj in NACHBARN):
            out.append(c)
    return out


class Erkunden(Faehigkeit):
    faehigkeit = "erkunden"
    braucht = frozenset({'tiefensensor', 'beine'})
    name = "erkunden"
    channels = ("base",)
    UMSEHEN_GRAD = 330.0       # am Anfang einmal fast ganz herum: der Tiefensensor sieht ≈ 45° auf einmal
    BLICK_GRAD = 90.0          # an jeder Grenze: Blick zur Seite (abwechselnd links/rechts – die Route schaut schon vorwärts)
    MIN_M, MAX_M = 0.35, 3.0   # so weit darf eine Grenze weg sein, damit sich der Weg lohnt
    NAH_M = 0.4                # Grenzen so nah an einer schon besuchten Stelle zählen nicht mehr
    KANDIDATEN = 25

    def __init__(self, karte: Karte, sekunden: float = 120.0) -> None:
        super().__init__()
        self.karte = karte
        self.sekunden = sekunden
        self.timeout = sekunden + 10.0
        self.inner: Behavior | None = None
        self.phase = "umsehen"
        self.t = 0.0
        self.besucht: list[tuple[float, float]] = []
        self.ziele = 0

    def _use(self, b: Behavior) -> None:
        b.engine = self.engine
        self.inner = b

    def on_start(self, st):
        self.besucht.append((st.x, st.y))
        self._use(Turn(self.UMSEHEN_GRAD, speed=0.7))

    def naechstes_ziel(self, st) -> tuple[float, float] | None:
        """Die nächste erreichbare Grenze, die nicht neben einer schon besuchten Stelle liegt."""
        kandidaten = []
        gesperrt = self.karte._gesperrt()         # zu nah an Hindernissen: dort hängt sie nur fest
        for c in grenzen(self.karte):
            if c in gesperrt or self._unbekannt_um(c) < 6:   # nur echte offene Ränder, keine Lücken an der Wand
                continue
            x, y = mitte(c)
            d = math.hypot(x - st.x, y - st.y)
            if not (self.MIN_M <= d <= self.MAX_M):
                continue
            if any(math.hypot(x - bx, y - by) < self.NAH_M for bx, by in self.besucht):
                continue
            kandidaten.append((d, x, y))
        kandidaten.sort()
        # auf eine Grenze pro Fleck ausdünnen, dann die nächsten auf Erreichbarkeit prüfen
        gewaehlt: list[tuple[float, float, float]] = []
        for k in kandidaten:
            if all(math.hypot(k[1] - g[1], k[2] - g[2]) > 0.25 for g in gewaehlt):
                gewaehlt.append(k)
            if len(gewaehlt) >= self.KANDIDATEN:
                break
        for _, x, y in gewaehlt:
            weg = self.karte.route((st.x, st.y), (x, y))
            if weg is not None:
                return (x, y)
            self.besucht.append((x, y))           # nicht erreichbar: nicht noch einmal versuchen
        return None

    def _unbekannt_um(self, c: tuple[int, int], r: int = 3) -> int:
        z = self.karte.zellen
        return sum(1 for di in range(-r, r + 1) for dj in range(-r, r + 1) if (c[0] + di, c[1] + dj) not in z)

    def tick(self, st, dt):
        self.t += dt
        if self.t > self.sekunden:
            return self.finish(f"Zeit um – {self.karte.flaeche_m2():.1f} m² erkundet".replace(".", ","))
        if self.inner is None:
            return None
        cmd = self.inner._step(st, dt)
        if not self.inner.done:
            return cmd
        if self.phase == "hin":
            self.besucht.append((st.x, st.y))
            if getattr(self.inner, "failed", False) and self.ziel is not None:
                self.besucht.append(self.ziel)
            self.phase = "umsehen"
            self._use(Turn(self.BLICK_GRAD, speed=1.0))      # am Ziel kurz zur Seite schauen
            return Command()
        ziel = self.naechstes_ziel(st)
        if ziel is None:
            return self.finish(f"Alles Erreichbare erkundet – {self.karte.flaeche_m2():.1f} m²".replace(".", ","))
        self.ziel = ziel
        self.ziele += 1
        self.phase = "hin"
        route = Route(self.karte, ziel, "zur nächsten unerkundeten Stelle")
        route.timeout = 25.0                       # hängt sie fest, lieber die nächste Stelle
        self._use(route)
        return Command()

    ziel: tuple[float, float] | None = None

    def describe(self):
        return f"erkunden ({int(self.sekunden)} s)"

    def info(self) -> dict[str, Any]:
        return {"phase": self.phase, "ziele": self.ziele, "flaeche_m2": self.karte.flaeche_m2(), "zelle_m": ZELLE,
                "start": zelle(*self.besucht[0]) if self.besucht else None}
