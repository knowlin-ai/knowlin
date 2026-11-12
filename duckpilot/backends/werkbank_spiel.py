"""Tic-Tac-Toe an Aris Werkbank (seit 0.38.54, nach dem Vorbild „LeX-O“ aus der SO-101-Gemeinde).

Vor Ari liegt ein Spielfeld mit 3 × 3 Feldern, links seine fünf blauen Steine. Du setzt per Klick (oder „Feld 5“) –
dein roter Stein erscheint auf dem Feld, du hast im Simulator ja keine Hand. Dann greift Ari einen Stein und legt ihn
auf sein Feld; jede Bewegung wird wie sonst geprüft, der Not-Aus beendet den Zug. Die Wahl des Feldes braucht kein
Sprachmodell: gewinnen, wenn es geht, sonst verhindern, sonst Mitte, Ecke, Rand – gut, aber zu schlagen.
"""

from __future__ import annotations

import math
import random
from typing import Any

from .werkbank import WUERFEL

REIHEN = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))
# Felder 1–9 aus deiner Sicht (du sitzt Ari gegenüber): 1 2 3 hinten bei Ari, 7 8 9 vorn bei dir; links ist links
REIHE_X = (0.17, 0.215, 0.26)            # m vor dem Sockel – alles in Reichweite (nachgemessen)
SPALTE_Y = (-0.045, 0.0, 0.045)          # deine linke Spalte liegt rechts von Ari
STEINE = 5
VORRAT = [(0.22 * math.cos(math.radians(g)), 0.22 * math.sin(math.radians(g))) for g in (50, 60, 70, 80, 90)]
DU, ARI = "du", "ari"


def felder() -> list[dict[str, Any]]:
    """Die 9 Felder mit Lage (x, y) auf der Werkbank – Reihe 1 nah am Sockel."""
    out = []
    for r, x in enumerate(REIHE_X):
        for s, y in enumerate(SPALTE_Y):
            out.append({"name": f"Feld {r * 3 + s + 1}", "nr": r * 3 + s + 1, "x": x, "y": y})
    return out


def gewinner(brett: list[str | None]) -> str | None:
    for a, b, c in REIHEN:
        if brett[a] and brett[a] == brett[b] == brett[c]:
            return brett[a]
    return None


def ari_waehlt(brett: list[str | None], zufall: random.Random | None = None) -> int:
    """Index 0–8: gewinnen, sonst verhindern, sonst Mitte, eine Ecke, ein Rand."""
    z = zufall or random.Random()
    frei = [i for i, f in enumerate(brett) if f is None]
    for wer in (ARI, DU):
        for i in frei:
            probe = list(brett)
            probe[i] = wer
            if gewinner(probe) == wer:
                return i
    if 4 in frei:
        return 4
    for gruppe in ([0, 2, 6, 8], [1, 3, 5, 7]):
        moeglich = [i for i in gruppe if i in frei]
        if moeglich:
            return z.choice(moeglich)
    raise ValueError("Das Feld ist voll")


class TicTacToe:
    def __init__(self, wb: Any, zufall: random.Random | None = None) -> None:
        self.wb = wb
        self.zufall = zufall or random.Random()
        self.brett: list[str | None] = [None] * 9
        self.dran: str | None = DU
        self.ergebnis: str | None = None
        wb.dinge = [{"name": f"Aris Stein {i + 1}", "akk": "seinen Stein", "farbe": "#3d6fd9", "x": round(x, 4),
                     "y": round(y, 4), "z": WUERFEL / 2, "in": None, "auf": None, "start": [round(x, 4), round(y, 4)]}
                    for i, (x, y) in enumerate(VORRAT)]
        wb.kisten = []
        wb.felder = felder()
        wb.haelt = None

    def _ende(self) -> None:
        w = gewinner(self.brett)
        if w == DU:
            self.ergebnis, self.dran = "Du gewinnst – gut gespielt!", None
        elif w == ARI:
            self.ergebnis, self.dran = "Ari gewinnt diese Runde.", None
        elif all(self.brett):
            self.ergebnis, self.dran = "Unentschieden.", None

    def zug_mensch(self, nr: int) -> tuple[int | None, str]:
        """Dein Stein auf Feld `nr` (1–9). Gibt Aris Feld (1–9) zurück oder None, wenn das Spiel aus ist."""
        if self.dran != DU:
            return None, self.ergebnis or "Ari ist gerade dran."
        if not 1 <= nr <= 9 or self.brett[nr - 1] is not None:
            return None, "Das Feld ist schon belegt." if 1 <= nr <= 9 else "Felder gehen von 1 bis 9."
        self.brett[nr - 1] = DU
        f = self.wb.felder[nr - 1]
        self.wb.dinge.append({"name": f"dein Stein {sum(1 for x in self.brett if x == DU)}", "akk": "deinen Stein",
                              "farbe": "#d94a3d", "x": f["x"], "y": f["y"], "z": WUERFEL / 2, "in": None,
                              "auf": None, "start": [f["x"], f["y"]], "fest": True})
        self._ende()
        if self.ergebnis:
            return None, self.ergebnis
        self.dran = ARI
        return ari_waehlt(self.brett, self.zufall) + 1, f"Du: Feld {nr}."

    def stein_fuer_ari(self) -> str | None:
        return next((d["name"] for d in self.wb.dinge if d["name"].startswith("Aris") and not d.get("feld")), None)

    def ari_gesetzt(self, nr: int, ok: bool) -> str:
        """Nach Aris Bewegung: Stein liegt auf dem Feld (oder der Zug ging schief)."""
        if not ok:
            self.dran, self.ergebnis = None, "Mein Zug ging schief – das Spiel ist abgebrochen."
            return self.ergebnis
        self.brett[nr - 1] = ARI
        self.dran = DU
        self._ende()
        return self.ergebnis or f"Ari: Feld {nr}. Du bist dran."

    def als_dict(self) -> dict[str, Any]:
        return {"brett": self.brett, "dran": self.dran, "ergebnis": self.ergebnis}
