"""Verstecken (seit 0.44, Fahrplan „Spiele“): Der Roboter versteckt sich bei einem Möbelstück, du rätst.

Reine Logik ohne Roboter: Die Route (`server/routes/spiel.py`) gibt die Möbel des Zimmers herein, schickt den Körper mit
`go_to` los (mit allen Regeln: nach einem Not-Aus läuft nichts) und fragt hier nach, ob ein Tipp stimmt.

- `verstecke()`: je Möbelstück ein freier Platz dicht daneben, auf der Seite, die von der Raummitte weg zeigt
  („hinter dem Sofa“). Plätze in Wänden oder anderen Möbeln fallen weg.
- `Verstecken`: raten mit dem Namen eines Möbelstücks; falsch → „wärmer“ oder „kälter“ (näher dran als der letzte
  Tipp oder nicht), nach fünf Fehlversuchen zeigt er sich von selbst.
"""

from __future__ import annotations

import math
import random
from typing import Any, Callable

ABSTAND_M = 0.14          # Platz neben dem Möbel: Körpermitte so weit von der Möbelkante
WAND_M = 0.12             # so weit bleibt der Platz von den Wänden weg
VERSUCHE = 5


def bei(name: str) -> str:
    """„beim Sofa“, „bei der Pflanze“ – Möbel, die auf -e enden, sind hier weiblich."""
    return f"bei der {name}" if name.lower().endswith("e") else f"beim {name}"


def verstecke(moebel: list[dict[str, Any]], breite: float, tiefe: float,
              frei: Callable[[float, float], bool]) -> list[dict[str, Any]]:
    """Möbel: {name, x, y, sx, sy} (Kasten) oder {name, x, y, r} (rund). Je Möbel höchstens ein Versteck."""
    out = []
    for m in moebel:
        kandidaten = []
        for i in range(16):
            a = i * math.tau / 16
            ca, sa = math.cos(a), math.sin(a)
            if "r" in m:
                d = float(m["r"]) + ABSTAND_M
            else:                                         # Abstand bis zur Kastenkante in dieser Richtung
                hx, hy = float(m["sx"]) / 2, float(m["sy"]) / 2
                d = min(hx / abs(ca) if abs(ca) > 1e-6 else 1e9, hy / abs(sa) if abs(sa) > 1e-6 else 1e9) + ABSTAND_M
            x, y = float(m["x"]) + d * ca, float(m["y"]) + d * sa
            if abs(x) > breite / 2 - WAND_M or abs(y) > tiefe / 2 - WAND_M or not frei(x, y):
                continue
            kandidaten.append((math.hypot(x, y), x, y))
        if kandidaten:
            _, x, y = max(kandidaten)                     # am weitesten von der Raummitte: „dahinter“
            out.append({"moebel": m["name"], "x": round(x, 3), "y": round(y, 3), "text": bei(m["name"])})
    return out


class Verstecken:
    def __init__(self, orte: list[dict[str, Any]], seed: int | None = None) -> None:
        if not orte:
            raise ValueError("Hier gibt es kein Möbelstück, hinter dem man sich verstecken könnte.")
        self.orte = orte
        self.ort = random.Random(seed).choice(orte)
        self.versuche = 0
        self._letzter_abstand: float | None = None
        self.phase = "verstecken"            # verstecken → raten → gefunden | aufgedeckt
        self.lage: tuple[float, float] = (self.ort["x"], self.ort["y"])

    def versteckt(self, x: float, y: float) -> None:
        """Wo er wirklich steht. Kam er nicht hin, gilt das nächste Versteck – ehrlich, nicht das geplante."""
        self.lage = (x, y)
        if math.hypot(x - self.ort["x"], y - self.ort["y"]) > 0.3:
            self.ort = min(self.orte, key=lambda o: math.hypot(x - o["x"], y - o["y"]))
        self.phase = "raten"

    def raten(self, moebel: str) -> dict[str, Any]:
        if self.phase != "raten":
            raise ValueError("Gerade wird nicht geraten.")
        ziel = next((o for o in self.orte if o["moebel"].lower() == str(moebel).strip().lower()), None)
        if ziel is None:
            raise ValueError(f"Kein Versteck bei „{moebel}“ – es gibt: {', '.join(o['moebel'] for o in self.orte)}.")
        self.versuche += 1
        if ziel is self.ort:
            self.phase = "gefunden"
            return {"treffer": True, "versuche": self.versuche, "ort": self.ort["text"],
                    "satz": f"Gefunden! Ich war {self.ort['text']} – nach {self.versuche} "
                            f"{'Versuch' if self.versuche == 1 else 'Versuchen'}."}
        abstand = math.hypot(ziel["x"] - self.lage[0], ziel["y"] - self.lage[1])
        if self._letzter_abstand is None:
            hinweis = "Nein, da nicht."
        else:
            hinweis = "Wärmer!" if abstand < self._letzter_abstand - 0.05 else "Kälter!" if abstand > self._letzter_abstand + 0.05 else "Nicht wärmer, nicht kälter."
        self._letzter_abstand = abstand
        if self.versuche >= VERSUCHE:
            self.phase = "aufgedeckt"
            return {"treffer": False, "versuche": self.versuche, "ort": self.ort["text"], "ende": True,
                    "satz": f"{hinweis} Hier bin ich – {self.ort['text']}!"}
        return {"treffer": False, "versuche": self.versuche, "satz": hinweis}

    def aufgeben(self) -> dict[str, Any]:
        self.phase = "aufgedeckt"
        return {"ort": self.ort["text"], "satz": f"Hier bin ich – {self.ort['text']}!"}
