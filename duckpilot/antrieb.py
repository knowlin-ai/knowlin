"""Antrieb: vier Bedürfnisse (seit 0.38.44, Etappe G3 aus dem Konzept „Knowlins Geist“).

Neugier, Nähe, Ruhe und Können wachsen mit der Zeit und werden durch passendes Tun gestillt. Sie entscheiden mit,
**was** Knowlin von sich aus tut – nie, **wie oft**: Das bestimmt allein der Regler „Von sich aus beschäftigen“.

Wunsch des Maintainers: Die Bedürfnisse sind „nahezu unsichtbar oder sehr dezent“ – sie wirken im Verhalten, sichtbar
höchstens als feiner Hinweis (`hinweis()`), keine eigenen Anzeigen.

Grenzen (Wertekern, `duckpilot/werte.py`): Nähe führt nie zu Drängen – sie gewichtet nur stille Zuwendung (Gefühl,
hinschauen), nie Sprechen, nie öfter. Ruhe dämpft alles, was den Körper bewegt. Keine Sicherheitsregel hängt am
Antrieb; die Sperren stehen in `motion/eigenstaendig.sperre`.
Diese Datei gehört zur Basis und importiert nichts aus Knowlin.
"""

from __future__ import annotations

from typing import Any

BEDUERFNISSE = ("neugier", "naehe", "ruhe", "koennen")
NAMEN = {"neugier": "Neugier", "naehe": "Nähe", "ruhe": "Ruhe", "koennen": "Können"}
STIMMUNG = {"neugier": "neugierig", "naehe": "anhänglich", "ruhe": "müde", "koennen": "unternehmungslustig"}
# Welche eigene Beschäftigung welches Bedürfnis stillt (Arten aus `motion/eigenstaendig.angebot`)
STILLT = {
    "umschauen": "neugier", "erkunden": "neugier", "ding": "neugier", "anschauen": "neugier",
    "gefuehl": "naehe", "pollen": "naehe", "zuwenden": "naehe", "antennen": "naehe",
    "sitzen": "ruhe",
    "trick": "koennen", "tanzen": "koennen", "ball": "koennen", "laufen": "koennen", "aufstehen": "koennen",
}
# Zuwachs je Minute (0 … 1); Neugier wächst mit der Energie des Charakters
ZUWACHS = {"neugier": 0.012, "naehe": 0.010, "koennen": 0.008}
RUHE_AKTIV = 0.04          # je Minute, solange der Körper beschäftigt ist
RUHE_ERHOLT = 0.02         # je Minute Ruhe
AKKU_KNAPP = 0.25          # darunter will er Ruhe


def _unit(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


class Antrieb:
    def __init__(self) -> None:
        self.werte: dict[str, float] = {b: 0.3 for b in BEDUERFNISSE}
        self.werte["ruhe"] = 0.1
        self._t: float | None = None

    def takt(self, jetzt: float, *, aktiv: bool, kontakt: bool, akku: float | None = None,
             energie: float = 0.5) -> None:
        """Zeit vergehen lassen. `kontakt`: der Mensch hat sich seit dem letzten Takt gemeldet."""
        dt = 0.0 if self._t is None else max(0.0, min(jetzt - self._t, 600.0)) / 60.0
        self._t = jetzt
        w = self.werte
        w["neugier"] = _unit(w["neugier"] + dt * ZUWACHS["neugier"] * (0.5 + _unit(energie)))
        w["koennen"] = _unit(w["koennen"] + dt * ZUWACHS["koennen"])
        w["naehe"] = 0.1 if kontakt else _unit(w["naehe"] + dt * ZUWACHS["naehe"])
        w["ruhe"] = _unit(w["ruhe"] + dt * (RUHE_AKTIV if aktiv else -RUHE_ERHOLT))
        if isinstance(akku, (int, float)) and akku < AKKU_KNAPP:
            w["ruhe"] = max(w["ruhe"], 0.8)

    def gestillt(self, art: str) -> None:
        """Nach einer eigenen Beschäftigung: das passende Bedürfnis sinkt; alles Bewegte macht etwas müder."""
        b = STILLT.get(art)
        if b == "ruhe":
            self.werte["ruhe"] = self.werte["ruhe"] * 0.3
            return
        if b:
            self.werte[b] = self.werte[b] * 0.3
        self.werte["ruhe"] = _unit(self.werte["ruhe"] + 0.05)

    def faktor(self, art: str, ort: bool = False) -> float:
        """Gewicht für eine Beschäftigung: 0,5 (Bedürfnis gestillt) bis 2 (drängend); Ruhe dämpft Bewegung."""
        b = STILLT.get(art)
        f = 0.5 + 1.5 * self.werte[b] if b else 1.0
        if ort and b != "ruhe":
            f *= 1.2 - self.werte["ruhe"]
        return max(0.05, f)

    def staerkstes(self) -> tuple[str, float]:
        b = max(BEDUERFNISSE, key=lambda k: self.werte[k])
        return b, self.werte[b]

    def grund(self, art: str) -> str:
        """Warum diese Beschäftigung – für die Gedankenspur."""
        b = STILLT.get(art)
        if b is None:
            return "einfach so, passend zum Charakter"
        stark = "stark" if self.werte[b] >= 0.6 else "etwas" if self.werte[b] >= 0.3 else "kaum"
        return f"{NAMEN[b]} ({stark})"

    def hinweis(self) -> str | None:
        """Feiner Hinweis für den Tooltip im Knowlin-Feld – nur, wenn ein Bedürfnis deutlich ist."""
        b, wert = self.staerkstes()
        return f"gerade eher {STIMMUNG[b]}" if wert >= 0.6 else None

    def als_dict(self) -> dict[str, Any]:
        return {"werte": {k: round(v, 2) for k, v in self.werte.items()}, "hinweis": self.hinweis()}
