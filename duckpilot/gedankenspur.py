"""Gedankenspur (seit 0.38.44, Etappe G3 aus dem Konzept „Knowlins Kopf“): zu jeder eigenen Handlung eine lesbare Zeile
– was, warum, wie und was daraus wurde. So bleibt durchschaubar, warum Knowlin etwas von sich aus tut.

Die Spur liegt nur im Speicher der laufenden App (höchstens `GROESSE` Zeilen) und lässt sich am PC leeren. Zeilen, die
eine Person betreffen, sieht nur der PC (Regel „Personen nur am PC“).
Diese Datei gehört zur Basis und importiert nichts aus Knowlin.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

GROESSE = 100
QUELLEN = ("antrieb", "gespraech", "reflex")


class Gedankenspur:
    def __init__(self, groesse: int = GROESSE) -> None:
        self.zeilen: deque[dict[str, Any]] = deque(maxlen=groesse)

    def merken(self, was: str, warum: str, *, quelle: str = "antrieb", wie: str | None = None,
               ergebnis: str = "getan", person: bool = False, zeit: float | None = None,
               art: str | None = None) -> dict[str, Any]:
        z = {"zeit": round(time.time() if zeit is None else zeit, 1), "quelle": quelle if quelle in QUELLEN else "antrieb",
             "was": str(was)[:160], "warum": str(warum)[:200], "wie": wie, "ergebnis": str(ergebnis)[:120],
             "person": bool(person), "art": art}
        self.zeilen.append(z)
        return z

    def liste(self, ohne_personen: bool = False) -> list[dict[str, Any]]:
        """Neueste zuerst."""
        return [z for z in reversed(self.zeilen) if not (ohne_personen and z["person"])]

    def leeren(self) -> None:
        self.zeilen.clear()
