"""Arena-Rennen mit Zeitmessung (seit 0.47, Zubehör der Microduck): eine Runde durch Tore im Wohnzimmer des Simulators.

Pollen schreibt, Rennen und Fußball hätten die Microduck im Test lebendig gemacht. Im Simulator fährt sie eine Runde um
den Couchtisch: durch die Starttor-Linie, dann durch die Tore der Reihe nach, dann wieder über die Linie. Die Zeit
läuft ab der Startlinie. Bestzeiten gibt es je Art – zu Fuß, auf Rollen, geduckt auf Rollen – und zur besten Fahrt wird
der Weg gespeichert: Beim nächsten Mal fährt die **Geisterente** mit (nur ein Punkt im Bild).

Rein rechnend, ohne Server und ohne Körper: `Zeitfahren.takt(t, x, y)` meldet, wenn ein Tor durchfahren ist. Die
Strecke liegt so, dass im Wohnzimmer kein Möbel im Weg steht (Test).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATEI = "rennen.json"
GEIST_TAKT_S = 0.1           # so oft wird der Weg für die Geisterente notiert
GEIST_MAX = 1200             # höchstens 2 min Weg
ARTEN = ("zu_fuss", "rollen", "geduckt")
ART_NAME = {"zu_fuss": "zu Fuß", "rollen": "auf Rollen", "geduckt": "geduckt auf Rollen"}

# Eine Runde um den Couchtisch (Wohnzimmer 4 × 3 m): Mitten der Tore; das erste ist Start und Ziel. Jedes Tor steht
# quer zum Weg vom vorigen Tor her – so fährt man immer gerade hindurch.
PUNKTE: tuple[tuple[float, float], ...] = ((-0.35, -0.45), (1.15, -0.4), (1.15, 0.62), (-0.25, 0.65), (-0.85, 0.0))
BREITE_M = 0.7


def _strecke() -> tuple[tuple[float, float, float, float], ...]:
    n = len(PUNKTE)
    out = []
    for i, (x, y) in enumerate(PUNKTE):
        px, py = PUNKTE[i - 1] if i else PUNKTE[n - 1]
        out.append((x, y, math.atan2(y - py, x - px), BREITE_M))
    return tuple(out)


STRECKE: tuple[tuple[float, float, float, float], ...] = _strecke()   # (x, y, Fahrtrichtung in rad, Breite in m)


def tore() -> list[dict[str, float]]:
    """Die Strecke für die Ansicht: Mitte, Richtung, Breite, Nummer (0 = Start/Ziel)."""
    return [{"nr": i, "x": x, "y": y, "richtung": r, "breite": b} for i, (x, y, r, b) in enumerate(STRECKE)]


def _seite(tor: tuple[float, float, float, float], x: float, y: float) -> float:
    """Vorzeichenbehafteter Abstand zur Torlinie in Fahrtrichtung (> 0: schon durch)."""
    tx, ty, r, _ = tor
    return (x - tx) * math.cos(r) + (y - ty) * math.sin(r)


def _quer(tor: tuple[float, float, float, float], x: float, y: float) -> float:
    tx, ty, r, _ = tor
    return -(x - tx) * math.sin(r) + (y - ty) * math.cos(r)


@dataclass
class Zeitfahren:
    """Eine Fahrt. Erst über die Startlinie, dann Tor 1 … n, dann wieder über die Startlinie."""

    art: str = "zu_fuss"
    start_t: float | None = None
    naechstes: int = 0                       # Index in STRECKE; 0 = Startlinie (am Anfang und am Ende)
    zeiten: list[float] = field(default_factory=list)
    weg: list[tuple[float, float, float]] = field(default_factory=list)    # (t seit Start, x, y)
    fertig: float | None = None
    _vorher: tuple[float, float] | None = None
    _geist_t: float = -1.0

    def takt(self, t: float, x: float, y: float) -> dict[str, Any] | None:
        """Neue Lage – gibt ein Ereignis zurück, wenn ein Tor durchfahren wurde ({"tor", "zeit", "ziel"})."""
        if self.fertig is not None:
            return None
        if self.start_t is not None and t - self._geist_t >= GEIST_TAKT_S and len(self.weg) < GEIST_MAX:
            self._geist_t = t
            self.weg.append((round(t - self.start_t, 2), round(x, 3), round(y, 3)))
        vorher, self._vorher = self._vorher, (x, y)
        if vorher is None:
            return None
        tor = STRECKE[self.naechstes]
        if not (_seite(tor, *vorher) < 0 <= _seite(tor, x, y)) or abs(_quer(tor, x, y)) > tor[3] / 2:
            return None
        if self.start_t is None:                          # über die Startlinie: Uhr läuft
            self.start_t = self._geist_t = t
            self.weg.append((0.0, round(x, 3), round(y, 3)))
            self.naechstes = 1
            return {"tor": 0, "zeit": 0.0, "ziel": False, "start": True}
        zeit = round(t - self.start_t, 2)
        if self.naechstes == 0:                           # Ziel
            self.fertig = zeit
            return {"tor": 0, "zeit": zeit, "ziel": True}
        self.zeiten.append(zeit)
        nr = self.naechstes
        self.naechstes = (self.naechstes + 1) % len(STRECKE)
        return {"tor": nr, "zeit": zeit, "ziel": False}

    def ziel_punkt(self) -> tuple[float, float]:
        """Wohin als Nächstes – für das selbst fahrende Verhalten: ein Stück hinter die Mitte des nächsten Tors."""
        x, y, r, _ = STRECKE[self.naechstes]
        return x + 0.25 * math.cos(r), y + 0.25 * math.sin(r)


class Bestzeiten:
    """Beste Zeit je Art mit dem Weg der Fahrt (für die Geisterente). In `<daten>/rennen.json`."""

    def __init__(self, ordner: Path) -> None:
        self.pfad = ordner / DATEI

    def alle(self) -> dict[str, Any]:
        try:
            d = json.loads(self.pfad.read_text(encoding="utf-8"))
            return {k: v for k, v in d.items() if k in ARTEN and isinstance(v, dict)} if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def ueberblick(self) -> dict[str, float]:
        return {k: float(v["zeit"]) for k, v in self.alle().items() if "zeit" in v}

    def geist(self, art: str) -> list[list[float]]:
        return list(self.alle().get(art, {}).get("weg") or [])

    def eintragen(self, fahrt: Zeitfahren) -> bool:
        """Neue Bestzeit? Dann mit Weg speichern und True."""
        if fahrt.fertig is None or fahrt.art not in ARTEN:
            return False
        d = self.alle()
        alt = d.get(fahrt.art, {}).get("zeit")
        if alt is not None and float(alt) <= fahrt.fertig:
            return False
        d[fahrt.art] = {"zeit": fahrt.fertig, "weg": [list(p) for p in fahrt.weg[:GEIST_MAX]]}
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".teil")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.pfad)
        return True


def art_von(zubehoer: dict[str, Any] | None) -> str:
    z = zubehoer or {}
    return "geduckt" if z.get("rollen") and z.get("geduckt") else "rollen" if z.get("rollen") else "zu_fuss"
