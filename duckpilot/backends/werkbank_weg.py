"""Freier Weg an der Werkbank (seit 0.38.55, Maintainer: „der Greifer ragt in den Turm“).

Zwischen zwei Haltungen fährt der Arm alle Gelenke gleichmäßig (eine gerade Linie im Gelenkraum, `so101.py`). Hier wird
diese Linie in kleinen Schritten abgetastet: Fühlpunkte auf Greifer und beweglicher Backe (`duckpilot/arm_huelle.py`,
aus dem Modell) und – solange er etwas hält – auf dem gehaltenen Würfel. Liegt ein Punkt in einem Würfel, in der Wand
einer Kiste oder unter der Werkbank, gilt der Weg als versperrt. Der Planer probiert dann eine andere Drehung des
Handgelenks und eine kleinere Öffnung; geht nichts, lehnt der Arm mit Grund ab, statt hindurchzufahren.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .. import arm_kinematik as K
from ..arm_huelle import huelle

SPIEL = 0.0015            # m: so viel dürfen Fühlpunkte eine Fläche streifen (Backen liegen am Würfel an)
WAND = 0.004              # m: Brettstärke der Kisten (wie in arm3d.js)
SCHRITT_GRAD = 3.0        # so fein wird zwischen zwei Haltungen abgetastet
_GITTER = np.array([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)], dtype=float)


def hindernisse(dinge: list[dict[str, Any]], kisten: list[dict[str, Any]], wuerfel: float,
                ohne: set[str]) -> list[tuple[str, str, np.ndarray, np.ndarray]]:
    """(Art, Name im Akkusativ, Mitte, halbe Größe) – Würfel aus `ohne` (gegriffen, gehalten) zählen nicht."""
    out = []
    for d in dinge:
        if d["name"] not in ohne:
            out.append(("wuerfel", d.get("akk") or d["name"], np.array([d["x"], d["y"], d["z"]], dtype=float),
                        np.full(3, wuerfel / 2 - SPIEL)))
    for k in kisten:
        out.append(("kiste", f"die {k['name']}", np.array([k["x"], k["y"], k["h"] / 2], dtype=float),
                    np.array([k["s"] / 2, k["s"] / 2, k["h"] / 2])))
    return out


def _punkte(gelenke: dict[str, float], traegt: bool, wuerfel: float) -> np.ndarray:
    p = huelle(gelenke)
    if traegt:
        mitte, _ = K.spitze(gelenke)
        p = np.vstack([p, mitte + _GITTER * (wuerfel / 2 - SPIEL)])
    return p


def beruehrt(gelenke: dict[str, float], hin: list, traegt: bool, wuerfel: float) -> str | None:
    """Name dessen, was der Greifer in dieser Haltung träfe – oder None."""
    p = _punkte(gelenke, traegt, wuerfel)
    if (p[:, 2] < -SPIEL).any():
        return "die Werkbank"
    for art, name, mitte, halb in hin:
        d = np.abs(p - mitte)
        drin = (d < halb).all(axis=1)
        if art == "kiste":                                   # nur die Bretter, nicht der Raum darin
            innen = (d[:, 0] < halb[0] - WAND) & (d[:, 1] < halb[1] - WAND) & (p[:, 2] > WAND)
            drin &= ~innen
        if drin.any():
            return name
    return None


def weg(von: dict[str, float], nach: dict[str, float], hin: list, traegt: bool, wuerfel: float) -> str | None:
    """Tastet die gerade Linie im Gelenkraum ab; gibt zurück, was dabei im Weg wäre."""
    namen = [g for g in nach if g in von]
    weit = max((abs(float(nach[g]) - float(von[g])) for g in namen), default=0.0)
    n = max(2, int(weit / SCHRITT_GRAD) + 1)
    for t in np.linspace(0.0, 1.0, n)[1:]:
        g = {k: float(von.get(k, 0.0)) + (float(nach.get(k, 0.0)) - float(von.get(k, 0.0))) * t
             for k in set(von) | set(nach)}
        if (hit := beruehrt(g, hin, traegt, wuerfel)) is not None:
            return hit
    return None
