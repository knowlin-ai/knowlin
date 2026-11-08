"""Kartierungsmodus: eine Rasterkarte aus dem Tiefensensor und Wege darauf (seit 0.37, Motorik).

Während des Kartierens trägt die Ente jeden Messpunkt des 8×8-ToF in ein Raster aus 5-cm-Zellen ein (Belegungskarte
mit Log-Odds, wie es Saugroboter und ROS `gmapping` machen): Die Zellen auf dem Strahl bis zum Punkt werden „frei“,
die Zelle des Punkts „belegt“, wenn er über dem Boden liegt (Bodenpunkte sind frei). Wo sie selbst stand, ist frei.

`route()` sucht mit A* einen Weg um belegte Zellen herum – mit Sicherheitsabstand (Rumpf + Luft). Unbekannte Zellen
sind erlaubt, kosten aber mehr (lieber durch Bekanntes). Der Weg wird zu wenigen Wegpunkten geglättet; `Route` läuft
sie nacheinander ab und plant neu, wenn ein Stück nicht weitergeht.

Die Karte ist Wissen über die Wohnung: Sie bleibt am PC (je Körper eine Datei) und gehört nie in ein Knowlet.
"""

from __future__ import annotations

import heapq
import json
import math
from pathlib import Path
from typing import Any

from .behaviors import GoTo
from .engine import Behavior, Command

ZELLE = 0.05
TREFFER, FREI = 0.85, -0.4
GRENZE = 4.0
BELEGT_AB, FREI_AB = 0.6, -0.4
BODEN_Z, DECKE_Z = 0.03, 0.45          # Punkte dazwischen sind Hindernisse auf Höhe der Ente
MAX_STRAHL_M = 1.8
ABSTAND_M = 0.12                       # vom Hindernis frei halten (Rumpfradius + Luft)


def zelle(x: float, y: float) -> tuple[int, int]:
    return (math.floor(x / ZELLE), math.floor(y / ZELLE))


def mitte(c: tuple[int, int]) -> tuple[float, float]:
    return ((c[0] + 0.5) * ZELLE, (c[1] + 0.5) * ZELLE)


def _strahl(a: tuple[int, int], b: tuple[int, int]):
    """Zellen von a bis vor b (Bresenham)."""
    x0, y0 = a
    x1, y1 = b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while (x0, y0) != (x1, y1):
        yield (x0, y0)
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


class Karte:
    def __init__(self) -> None:
        self.zellen: dict[tuple[int, int], float] = {}
        self.messungen = 0

    # ── eintragen ────────────────────────────────────────────────────────
    def _add(self, c: tuple[int, int], d: float) -> None:
        self.zellen[c] = max(-GRENZE, min(GRENZE, self.zellen.get(c, 0.0) + d))

    def eintragen(self, x: float, y: float, punkte: list[list[float]]) -> None:
        """Eine Messung: Standort der Ente (Odometrie) und die ToF-Punkte [x, y, z] im selben Rahmen."""
        start = zelle(x, y)
        self._add(start, 2 * FREI)
        for p in punkte or []:
            px, py, pz = float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.1
            if math.hypot(px - x, py - y) > MAX_STRAHL_M or pz > DECKE_Z:
                continue
            # 1 cm zur Ente hin: Ein Treffer genau auf einer Zellgrenze (Fuß der Wand bei x = 2,000) fiel sonst in die
            # Zelle hinter der Wand – dort entstand „freier Boden“ außerhalb des Raums (gemeldet nach 0.38.32)
            weit = math.hypot(px - x, py - y)
            if weit > 0.02:
                px, py = px - (px - x) / weit * 0.01, py - (py - y) / weit * 0.01
            ziel = zelle(px, py)
            for c in _strahl(start, ziel):
                self._add(c, FREI)
            self._add(ziel, TREFFER if pz > BODEN_Z else FREI)
        self.messungen += 1

    def leeren(self) -> None:
        self.zellen.clear()
        self.messungen = 0

    # ── abfragen ─────────────────────────────────────────────────────────
    def belegt(self, c: tuple[int, int]) -> bool:
        return self.zellen.get(c, 0.0) > BELEGT_AB

    def frei(self, c: tuple[int, int]) -> bool:
        return self.zellen.get(c, 0.0) < FREI_AB

    def flaeche_m2(self) -> float:
        return round(sum(1 for v in self.zellen.values() if v < FREI_AB) * ZELLE * ZELLE, 2)

    def _gesperrt(self) -> set[tuple[int, int]]:
        r = math.ceil(ABSTAND_M / ZELLE)
        aus = set()
        for (i, j), v in self.zellen.items():
            if v > BELEGT_AB:
                for di in range(-r, r + 1):
                    for dj in range(-r, r + 1):
                        if di * di + dj * dj <= r * r:
                            aus.add((i + di, j + dj))
        return aus

    def route(self, von: tuple[float, float], nach: tuple[float, float],
              max_zellen: int = 40000, meiden: set[tuple[int, int]] | None = None) -> list[tuple[float, float]] | None:
        """A* von `von` nach `nach` (Meter). → Wegpunkte ohne den Start, oder None (kein Weg bekannt).
        `meiden`: zusätzliche Zellen, um die sie herumgeht (z. B. schon abgelegte Dinge, seit 0.37.5)."""
        s, z = zelle(*von), zelle(*nach)
        gesperrt = self._gesperrt() | (meiden or set())
        # Wo sie steht, kommt sie auch wieder weg: steht sie im Sicherheitsabstand (Ecke, nah am Möbel), ist der
        # Abstand rund um sie aufgehoben – nur wirklich belegte Zellen bleiben gesperrt
        r = math.ceil(ABSTAND_M / ZELLE) + 1
        if s in gesperrt:
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    c = (s[0] + di, s[1] + dj)
                    if c in gesperrt and not self.belegt(c):
                        gesperrt.discard(c)
        gesperrt.discard(s)
        if z in gesperrt:                      # Ziel zu nah an einem Hindernis: nächste freie Zelle davor nehmen
            frei = [c for c in _strahl(z, s) if c not in gesperrt]
            if not frei:
                return None
            z = frei[0]
        offen = [(0.0, 0.0, s)]
        herkunft: dict[tuple[int, int], tuple[int, int] | None] = {s: None}
        kosten = {s: 0.0}
        nachbarn = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                    (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
        besucht = 0
        while offen:
            _, g, c = heapq.heappop(offen)
            if c == z:
                break
            if g > kosten.get(c, math.inf):
                continue
            besucht += 1
            if besucht > max_zellen:
                return None
            for di, dj, w in nachbarn:
                n = (c[0] + di, c[1] + dj)
                if n in gesperrt:
                    continue
                if di and dj and ((c[0] + di, c[1]) in gesperrt or (c[0], c[1] + dj) in gesperrt):
                    continue                   # nicht über Ecken schneiden
                schritt = w * (1.0 if self.frei(n) else 2.5)     # Unbekanntes kostet mehr
                ng = g + schritt
                if ng < kosten.get(n, math.inf):
                    kosten[n] = ng
                    herkunft[n] = c
                    h = math.hypot(z[0] - n[0], z[1] - n[1])
                    heapq.heappush(offen, (ng + h, ng, n))
        if z not in herkunft:
            return None
        pfad = []
        c: tuple[int, int] | None = z
        while c is not None:
            pfad.append(c)
            c = herkunft[c]
        pfad.reverse()
        return [mitte(c) for c in self._glaetten(pfad, gesperrt)[1:]]

    @staticmethod
    def _glaetten(pfad: list[tuple[int, int]], gesperrt: set[tuple[int, int]]) -> list[tuple[int, int]]:
        """Nur die Wegpunkte behalten, zwischen denen die gerade Linie frei ist."""
        if len(pfad) <= 2:
            return pfad
        aus = [pfad[0]]
        i = 0
        while i < len(pfad) - 1:
            j = len(pfad) - 1
            while j > i + 1 and any(c in gesperrt for c in _strahl(pfad[i], pfad[j])):
                j -= 1
            aus.append(pfad[j])
            i = j
        return aus

    # ── speichern / anzeigen ─────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        """Kompakt für die Oberfläche und die Datei: belegte und freie Zellen als [i, j]-Listen."""
        return {"version": 1, "zelle_m": ZELLE, "messungen": self.messungen, "flaeche_m2": self.flaeche_m2(),
                "belegt": [list(c) for c, v in self.zellen.items() if v > BELEGT_AB],
                "frei": [list(c) for c, v in self.zellen.items() if v < FREI_AB]}

    def speichern(self, pfad: Path) -> None:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        roh = {"version": 1, "zelle_m": ZELLE, "messungen": self.messungen,
               "zellen": [[c[0], c[1], round(v, 2)] for c, v in self.zellen.items() if abs(v) > 0.05]}
        tmp = pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps(roh, separators=(",", ":")), encoding="utf-8")
        tmp.replace(pfad)

    @classmethod
    def laden(cls, pfad: Path) -> "Karte":
        k = cls()
        try:
            roh = json.loads(pfad.read_text(encoding="utf-8"))
            if roh.get("zelle_m") == ZELLE:
                k.zellen = {(int(i), int(j)): float(v) for i, j, v in roh.get("zellen", [])}
                k.messungen = int(roh.get("messungen", 0))
        except (OSError, ValueError, TypeError):
            pass
        return k


class Route(Behavior):
    """Wegpunkte nacheinander ablaufen (aus `Karte.route`). Hängt ein Stück, plant sie einmal neu."""

    name = "route"
    channels = ("base",)

    def __init__(self, karte: Karte, ziel: tuple[float, float], label: str | None = None) -> None:
        super().__init__()
        self.karte = karte
        self.ziel = ziel
        self.label = label
        self.timeout = 120.0
        self.punkte: list[tuple[float, float]] = []
        self.inner: GoTo | None = None
        self.neu_geplant = 0

    def _planen(self, st) -> bool:
        weg = self.karte.route((st.x, st.y), self.ziel)
        if weg is None:
            return False
        self.punkte = weg or [self.ziel]
        if math.hypot(self.punkte[-1][0] - self.ziel[0], self.punkte[-1][1] - self.ziel[1]) > 0.02:
            self.punkte.append(self.ziel)        # die letzte Zelle ist nur ungefähr – genau aufs Ziel
        return True

    def _naechster(self) -> None:
        x, y = self.punkte.pop(0)
        self.inner = GoTo(x, y, label=self.label)
        self.inner.engine = self.engine

    def on_start(self, st):
        if not self._planen(st):
            self.failed = True
            self.finish("kein Weg auf der Karte")
            return
        self._naechster()

    def tick(self, st, dt):
        if self.inner is None:
            return None
        # unterwegs dazulernen: was der Tiefensensor sieht, kommt in die Karte (z. B. ein Hocker, den der
        # Rundgang verpasst hat) – ein Neuplanen kennt ihn dann schon
        self._takte = getattr(self, "_takte", 0) + 1
        if self._takte % 4 == 0 and st.perception.points:
            self.karte.eintragen(st.x, st.y, st.perception.points)
        cmd = self.inner._step(st, dt)
        if not self.inner.done:
            return cmd
        if getattr(self.inner, "failed", False):
            if self.neu_geplant < 3 and self._planen(st):
                self.neu_geplant += 1
                self._naechster()
                return Command()
            self.failed = True
            return self.finish(f"kommt nicht weiter: {self.inner.result}")
        if not self.punkte:
            return self.finish("angekommen")
        self._naechster()
        return Command()

    def on_stop(self):
        if self.result != "angekommen":
            self.failed = True

    def target(self):
        return self.ziel

    def wegpunkte(self) -> list[tuple[float, float]]:
        return list(self.punkte)

    def describe(self):
        return f"route zu {self.label}" if self.label else f"route zu ({self.ziel[0]:.2f}, {self.ziel[1]:.2f})"
