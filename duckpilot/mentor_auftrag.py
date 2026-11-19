"""Mentor 2 (seit 0.41): Vorgemachtes als Auftrag merken.

Beim Vormachen führt deine Hand Ari (`mentor.py`). Dabei schaut dieser Beobachter auf die Werkbank: Greift Ari einen
Würfel und lässt ihn woanders los, ist das ein Schritt – „roter Würfel → linke Kiste“, „gelber Würfel → auf den blauen
Würfel“, „blauer Würfel → Platz“ oder eine freie Stelle („stelle:0.21,-0.08“). Aus den Schritten wird ein Auftrag mit der
Regel „schritte“ (`werkbank_auftrag.py`) – nur Daten, teilbar als Knowlet. Ausgeführt wird er danach vom Planer mit allen
Wegprüfungen, nicht als Nachahmung deiner Handbewegung: Was du einmal ungefähr vorgemacht hast, macht Ari danach sauber.

Hochheben und an derselben Stelle wieder hinlegen zählt nicht (Zögern). Reine Rechnung, kein Körper, kein Netz.
"""

from __future__ import annotations

import math
from typing import Any

from .werkbank_auftrag import GROESSTE_LISTE

GEWACKELT_M = 0.012           # so wenig bewegt gilt als „wieder hingelegt“


def _ziel(d: dict[str, Any]) -> str:
    """Wohin ein losgelassener Würfel gekommen ist – in der Sprache der Aufträge."""
    if d.get("in"):
        return str(d["in"])
    if d.get("auf"):
        return str(d["auf"])
    if math.hypot(d["x"] - d["start"][0], d["y"] - d["start"][1]) < 0.01:
        return "platz"
    return f"stelle:{d['x']:.2f},{d['y']:.2f}"


def beschreiben(schritt: dict[str, str]) -> str:
    """„roter Würfel → linke Kiste“, „… → auf blauer Würfel“, „… → an seinen Platz“, „… → Stelle 21 cm vor, 8 cm rechts“."""
    z = schritt["ziel"]
    if z == "platz":
        wohin = "an seinen Platz"
    elif z.startswith("stelle:"):
        x, y = (float(v) for v in z[7:].split(","))
        wohin = f"Stelle {round(x * 100)} cm vor, {abs(round(y * 100))} cm {'links' if y > 0 else 'rechts'}"
    elif "kiste" in z.lower():
        wohin = z
    else:
        wohin = f"auf {z}"
    return f"{schritt['ding']} → {wohin}"


class Beobachter:
    """Liest aus aufeinanderfolgenden Ständen der Werkbank die vorgemachten Schritte."""

    def __init__(self) -> None:
        self.schritte: list[dict[str, str]] = []
        self._haelt: str | None = None
        self._von: tuple[float, float] | None = None

    def leeren(self) -> None:
        self.schritte, self._haelt, self._von = [], None, None

    def schauen(self, wb: Any) -> dict[str, str] | None:
        """Neuer Stand der Werkbank → der gerade fertig gewordene Schritt (oder None)."""
        haelt = getattr(wb, "haelt", None)
        neu = None
        if haelt and haelt != self._haelt:                 # gegriffen
            d = wb.ding(haelt)
            self._von = (d["x"], d["y"]) if d else None
        elif self._haelt and not haelt:                    # losgelassen
            d = wb.ding(self._haelt)
            if d is not None:
                bewegt = self._von is None or math.hypot(d["x"] - self._von[0], d["y"] - self._von[1]) > GEWACKELT_M
                if bewegt or d.get("in") or d.get("auf"):
                    neu = {"ding": d["name"], "ziel": _ziel(d)}
                    if len(self.schritte) < GROESSTE_LISTE:
                        self.schritte.append(neu)
            self._von = None
        self._haelt = haelt
        return neu

    def auftrag(self, titel: str) -> dict[str, Any] | None:
        if not self.schritte:
            return None
        titel = " ".join(str(titel or "").split())[:40] or "Vorgemacht"
        return {"titel": titel, "beschreibung": "; ".join(beschreiben(s) for s in self.schritte)[:200],
                "regel": "schritte", "schritte": [dict(s) for s in self.schritte], "von": "vorgemacht"}
