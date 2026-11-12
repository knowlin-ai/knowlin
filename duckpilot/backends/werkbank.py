"""Werkbank des SO-101 (seit 0.38.48, Wunsch des Maintainers: „die Roboterarme auf einer eigenen Plattform, wo in
Reichweite auch greifbare Objekte oder Boxen sind, wo man Sachen rein- und rausmachen kann“).

Der Arm steht hinten auf einer eigenen Werkbank im Wohnzimmer. Vor ihm liegen drei Würfel, links und rechts steht je
eine offene Kiste. Alles in Metern im Rahmen des Sockels (x vorn, y links, z über der Werkbank), wie in
`duckpilot/arm_kinematik.py`.

`greifen_plan` und `ablegen_plan` rechnen eine Folge von Haltungen aus (darüber, hinab, Greifer zu, hoch …). Eine
Haltung kann eine Handlung tragen („fassen“, „loslassen“), die der Simulator beim Ankommen ausführt. Was der Arm nicht
erreicht, lehnt er mit Grund ab. Öffnet sich der Greifer, während er etwas hält, fällt es dort hin, wo die Spitze gerade
ist – auch beim Not-Aus.
"""

from __future__ import annotations

import math
from typing import Any

from .. import arm_kinematik as K
from ..arm import POSEN

WERKBANK = {"name": "Werkbank", "x": -1.6, "y": 0.25, "sx": 0.6, "sy": 0.8, "h": 0.75, "color": "#a07e5a"}
SOCKEL_VOR_KANTE = 0.08          # so weit steht der Sockel vor der hinteren Kante der Werkbank
WUERFEL = 0.03                   # Kantenlänge
KISTE = {"s": 0.08, "h": 0.05}
UEBER = 0.06                     # so hoch über einem Würfel setzt der Arm an
TRAGEN = 0.10                    # in dieser Höhe trägt er
GREIFER_AUF, GREIFER_ZU = 60.0, 8.0     # zu: die Backen liegen am Würfel an (nachgemessen)
OFFEN_LAESST_FALLEN = 35.0       # öffnet sich der Greifer weiter, fällt, was er hält


def _polar(r: float, grad: float) -> tuple[float, float]:
    return round(r * math.cos(math.radians(grad)), 4), round(r * math.sin(math.radians(grad)), 4)


def startbelegung() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dinge = [{"name": name, "farbe": farbe, "x": x, "y": y, "z": WUERFEL / 2, "in": None, "start": [x, y]}
             for name, farbe, (x, y) in (("roter Würfel", "#d94a3d", _polar(0.20, 35)),
                                         ("blauer Würfel", "#3d6fd9", _polar(0.24, 0)),
                                         ("gelber Würfel", "#e8c33a", _polar(0.21, -35)))]
    kisten = [{"name": name, "x": x, "y": y, **KISTE}
              for name, (x, y) in (("linke Kiste", _polar(0.22, 75)), ("rechte Kiste", _polar(0.22, -75)))]
    return dinge, kisten


class Werkbank:
    def __init__(self) -> None:
        self.dinge, self.kisten = startbelegung()
        self.haelt: str | None = None

    # ── Namen ────────────────────────────────────────────────────────────
    def _finden(self, liste: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
        n = str(name or "").strip().lower()
        for e in liste:
            if e["name"].lower() == n:
                return e
        treffer = [e for e in liste if all(w in e["name"].lower() for w in n.split())] if n else []
        return treffer[0] if len(treffer) == 1 else None

    def ding(self, name: str) -> dict[str, Any] | None:
        return self._finden(self.dinge, name)

    def namen(self) -> dict[str, list[str]]:
        return {"dinge": [d["name"] for d in self.dinge], "kisten": [k["name"] for k in self.kisten]}

    # ── Pläne ────────────────────────────────────────────────────────────
    @staticmethod
    def _ik(x: float, y: float, z: float, greifer: float) -> dict[str, float] | None:
        return K.greifhaltung(x, y, z, greifer)

    def greifen_plan(self, name: str) -> tuple[list[tuple[dict[str, float], float, str | None]] | None, str]:
        if self.haelt:
            return None, f"Ich halte schon {self.haelt} – erst ablegen."
        d = self.ding(name)
        if d is None:
            return None, f"Kenne „{name}“ nicht – auf der Werkbank: {', '.join(self.namen()['dinge'])}."
        x, y, z = d["x"], d["y"], d["z"]
        schritte = [(x, y, z + UEBER, GREIFER_AUF, 1.2, None), (x, y, z, GREIFER_AUF, 0.7, None),
                    (x, y, z, GREIFER_ZU, 0.5, f"fassen:{d['name']}"), (x, y, TRAGEN, GREIFER_ZU, 0.7, None)]
        return self._plan(schritte, f"Da komme ich nicht hin – {d['name']} liegt außerhalb meiner Reichweite.")

    def ablegen_plan(self, ziel: str) -> tuple[list[tuple[dict[str, float], float, str | None]] | None, str]:
        if not self.haelt:
            return None, "Ich halte gerade nichts."
        d = self.ding(self.haelt)
        assert d is not None
        k = self._finden(self.kisten, ziel)
        if k is not None:
            platz = self._platz_in(k)
            x, y, z = k["x"] + platz[0], k["y"] + platz[1], k["h"] + 0.02
            text = k["name"]
        elif str(ziel or "").strip().lower() in ("", "zurück", "zurueck", "platz", "werkbank", "tisch"):
            (x, y), z, text = d["start"], WUERFEL / 2, "seinen Platz"
        else:
            return None, f"Kenne „{ziel}“ nicht – Ziele: {', '.join(self.namen()['kisten'])} oder „Platz“."
        schritte = [(x, y, TRAGEN, GREIFER_ZU, 1.2, None), (x, y, z, GREIFER_ZU, 0.6, None),
                    (x, y, z, GREIFER_AUF, 0.4, f"loslassen:{k['name'] if k else ''}"), (x, y, TRAGEN, GREIFER_AUF, 0.6, None)]
        plan, grund = self._plan(schritte, f"Da komme ich nicht hin – {text} ist außerhalb meiner Reichweite.")
        if plan is not None:
            plan.append((dict(POSEN["bereit"]), 1.0, None))
        return plan, grund

    def _plan(self, schritte, grund_weit: str):
        plan = []
        for x, y, z, greifer, s, aktion in schritte:
            g = self._ik(x, y, z, greifer)
            if g is None:
                return None, grund_weit
            plan.append((g, s, aktion))
        return plan, ""

    def _platz_in(self, k: dict[str, Any]) -> tuple[float, float]:
        """Freier Platz in der Kiste: bis zu vier Würfel nebeneinander."""
        belegt = sum(1 for d in self.dinge if d["in"] == k["name"])
        versatz = k["s"] / 4
        return [(-versatz, -versatz), (versatz, versatz), (-versatz, versatz), (versatz, -versatz)][belegt % 4]

    # ── Handlungen beim Ankommen ─────────────────────────────────────────
    def ausfuehren(self, aktion: str, gelenke: dict[str, float]) -> None:
        art, _, name = aktion.partition(":")
        if art == "fassen":
            d = self.ding(name)
            if d is not None and self.haelt is None:
                self.haelt = d["name"]
                d["in"] = None
        elif art == "loslassen":
            self.fallen_lassen(gelenke, kiste=name or None)

    def fallen_lassen(self, gelenke: dict[str, float], kiste: str | None = None) -> str | None:
        """Was der Greifer hält, landet unter der Spitze: in einer Kiste, wenn es über ihr ist, sonst auf der Werkbank."""
        if not self.haelt:
            return None
        d = self.ding(self.haelt)
        self.haelt = None
        if d is None:
            return None
        p, _ = K.spitze(gelenke)
        x, y = float(p[0]), float(p[1])
        unter = next((k for k in self.kisten if (kiste and k["name"] == kiste)
                      or (abs(x - k["x"]) <= k["s"] / 2 and abs(y - k["y"]) <= k["s"] / 2)), None)
        if unter is not None:
            d["x"], d["y"], d["z"], d["in"] = round(x, 4), round(y, 4), 0.004 + WUERFEL / 2, unter["name"]
        elif math.hypot(x - d["start"][0], y - d["start"][1]) < 0.01:      # zurück an seinen Platz
            d["x"], d["y"], d["z"], d["in"] = d["start"][0], d["start"][1], WUERFEL / 2, None
        else:
            halb_x, halb_y = WERKBANK["sx"] - SOCKEL_VOR_KANTE, WERKBANK["sy"] / 2 - WUERFEL
            d["x"] = round(max(0.06, min(halb_x, x)), 4)
            d["y"] = round(max(-halb_y, min(halb_y, y)), 4)
            d["z"], d["in"] = WUERFEL / 2, None
        return d["name"]

    def zuruecksetzen(self) -> None:
        self.dinge, self.kisten = startbelegung()
        self.haelt = None

    def als_dict(self) -> dict[str, Any]:
        return {"dinge": [{k: v for k, v in d.items() if k != "start"} for d in self.dinge],
                "kisten": self.kisten, "haelt": self.haelt, "wuerfel": WUERFEL}
