"""Werkbank des SO-101 (seit 0.38.48, Wunsch des Maintainers: „die Roboterarme auf einer eigenen Plattform, wo in
Reichweite auch greifbare Objekte oder Boxen sind, wo man Sachen rein- und rausmachen kann“).

Der Arm steht hinten auf einer eigenen Werkbank im Wohnzimmer. Vor ihm liegen drei Würfel, links und rechts steht je
eine offene Kiste. Alles in Metern im Rahmen des Sockels (x vorn, y links, z über der Werkbank), wie in
`duckpilot/arm_kinematik.py`.

`greifen_plan` und `ablegen_plan` rechnen eine Folge von Haltungen aus (darüber, hinab, Greifer zu, hoch …). Eine
Haltung kann eine Handlung tragen („fassen“, „loslassen“), die der Simulator beim Ankommen ausführt. Was der Arm nicht
erreicht, lehnt er mit Grund ab. Öffnet sich der Greifer, während er etwas hält, fällt es dort hin, wo die Spitze gerade
ist – auch beim Not-Aus.

Seit 0.38.55 prüft jeder Plan seinen Weg (`werkbank_weg.py`): Stieße der Greifer unterwegs an einen Würfel, eine Kiste
oder die Werkbank, versucht der Planer das Handgelenk gedreht und den Greifer weniger weit offen; sonst lehnt er ab.
Ruht der Arm danach, wählt er eine Haltung, in der nichts im Greifer steckt („bereit“ oder darüber).
"""

from __future__ import annotations

import math
from typing import Any

from .. import arm_kinematik as K
from ..arm import POSEN
from . import werkbank_weg as W

WERKBANK = {"name": "Werkbank", "x": -1.6, "y": 0.25, "sx": 0.6, "sy": 0.8, "h": 0.75, "color": "#a07e5a"}
SOCKEL_VOR_KANTE = 0.08          # so weit steht der Sockel vor der hinteren Kante der Werkbank
WUERFEL = 0.03                   # Kantenlänge
KISTE = {"s": 0.15, "h": 0.05}     # seit 0.38.55 breiter: neben jedem Würfel passt eine Backe (sonst 5 mm)
KISTE_VERSATZ = 0.033            # m: vier Plätze in der Kiste, so weit von der Mitte
UEBER = 0.06                     # so hoch über einem Würfel setzt der Arm an
TRAGEN = 0.10                    # in dieser Höhe trägt er
TRAGEN_FLACH = 0.075             # … nah am Sockel reicht die Spitze nicht so hoch: dort flacher (über flachen Steinen)
GREIFER_AUF, GREIFER_ZU = 60.0, 8.0     # zu: die Backen liegen am Würfel an (nachgemessen)
HOECHSTE_SPITZE = 0.105          # so hoch erreicht die Spitze senkrecht von oben (vor dem Sockel, nachgemessen)
HOECHSTER_STAPEL = 0.09          # Mitte des obersten Würfels höchstens hier: drei Würfel
OFFEN_LAESST_FALLEN = 35.0       # öffnet sich der Greifer weiter, fällt, was er hält
# Handgelenk: erst so, dass die Backen zum Sockel hin öffnen, sonst quer oder schräg (Tic-Tac-Toe: Nachbarn ringsum)
DREHUNGEN = (0.0, 90.0, -90.0, 45.0, -45.0, 135.0, -135.0)
WEITEN = (GREIFER_AUF, 45.0, 40.0, 30.0)  # so weit öffnet er, wenn daneben wenig Platz ist (Loslassen: ab 40°)
# Ruhehaltungen nach dem Ablegen: „bereit“, und wenn dort etwas steht (ein Turm), darüber – der Greifer schaut von oben
PARKEN = (dict(POSEN["bereit"]), {**POSEN["bereit"], "shoulder_lift": -60, "elbow_flex": 40, "wrist_flex": 70})


def _farbwort(name: str) -> str:
    w = name.split()[0].lower()
    return w[:-2] if w.endswith("er") else w                       # „roter Würfel“ → „rot“, „oranger“ → „orang“


def _polar(r: float, grad: float) -> tuple[float, float]:
    return round(r * math.cos(math.radians(grad)), 4), round(r * math.sin(math.radians(grad)), 4)


def startbelegung() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # `akk`: wie das Ding nach „hält …“ heißt – „hält den roten Würfel“, nicht „hält roter Würfel“
    # seit 0.38.54 fünf Würfel (grün und orange dazu) – fürs Sortieren nach Farben; `auf`: liegt auf diesem Würfel
    dinge = [{"name": name, "akk": akk, "farbe": farbe, "x": x, "y": y, "z": WUERFEL / 2, "in": None, "auf": None,
              "start": [x, y]}
             for name, akk, farbe, (x, y) in (("roter Würfel", "den roten Würfel", "#d94a3d", _polar(0.20, 35)),
                                              ("blauer Würfel", "den blauen Würfel", "#3d6fd9", _polar(0.28, 0)),
                                              ("gelber Würfel", "den gelben Würfel", "#e8c33a", _polar(0.21, -35)),
                                              ("grüner Würfel", "den grünen Würfel", "#3fa45b", _polar(0.24, 18)),
                                              ("oranger Würfel", "den orangen Würfel", "#ee8a2c", _polar(0.24, -18)))]
    kisten = [{"name": name, "x": x, "y": y, **KISTE}
              for name, (x, y) in (("linke Kiste", _polar(0.24, 75)), ("rechte Kiste", _polar(0.24, -75)))]
    return dinge, kisten


class Werkbank:
    def __init__(self) -> None:
        self.haelt: str | None = None
        self.zuruecksetzen()

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
    def _ik(x: float, y: float, z: float, greifer: float, drehung: float = 0.0) -> dict[str, float] | None:
        return K.greifhaltung(x, y, z, greifer, drehung)

    def greifen_plan(self, name: str, von: dict[str, float] | None = None
                     ) -> tuple[list[tuple[dict[str, float], float, str | None]] | None, str]:
        if self.haelt:
            h = self.ding(self.haelt)
            return None, f"Ich halte schon {h['akk'] if h else self.haelt} – erst ablegen."
        d = self.ding(name)
        if d is None:
            return None, f"Kenne „{name}“ nicht – auf der Werkbank: {', '.join(self.namen()['dinge'])}."
        if d.get("fest") or d.get("feld"):                       # Tic-Tac-Toe: gesetzte Steine bleiben liegen
            return None, "Der liegt im Spiel – den lasse ich liegen."
        oben = next((x for x in self.dinge if x.get("auf") == d["name"]), None)
        if oben is not None:
            return None, f"Darauf liegt noch etwas ({oben['name']}) – erst den oberen nehmen."
        x, y, z = d["x"], d["y"], d["z"]
        anfahrt = max(z + 0.03, min(z + UEBER, HOECHSTE_SPITZE))     # oben auf dem Turm: flacher anfahren
        schritte = [(x, y, anfahrt, GREIFER_AUF, 1.2, None), (x, y, z, GREIFER_AUF, 0.7, None),
                    (x, y, z, GREIFER_ZU, 0.5, f"fassen:{d['name']}"), (x, y, TRAGEN, GREIFER_ZU, 0.7, None)]
        return self._plan(schritte, f"Da komme ich nicht hin – {d['name']} liegt außerhalb meiner Reichweite.", von,
                          d["name"])

    def ablegen_plan(self, ziel: str, von: dict[str, float] | None = None
                     ) -> tuple[list[tuple[dict[str, float], float, str | None]] | None, str]:
        if not self.haelt:
            return None, "Ich halte gerade nichts."
        d = self.ding(self.haelt)
        assert d is not None
        k = self._finden(self.kisten, ziel)
        feld = self._finden(self.felder, ziel) if self.felder and k is None else None
        if feld is not None:                                     # Tic-Tac-Toe (seit 0.38.54)
            x, y, z = feld["x"], feld["y"], WUERFEL / 2
            schritte = [(x, y, TRAGEN, GREIFER_ZU, 1.2, None), (x, y, z, GREIFER_ZU, 0.6, None),
                        (x, y, z, GREIFER_AUF, 0.4, f"loslassen:feld:{feld['nr']}"), (x, y, TRAGEN, GREIFER_AUF, 0.6, None)]
            return self._plan(schritte, f"Da komme ich nicht hin – {feld['name']} ist außerhalb meiner Reichweite.",
                              von, None, parken=True)
        unten = None if k is not None else self._stapelziel(ziel, d)
        if isinstance(unten, str):
            return None, unten
        if unten is not None:                                    # darauf stapeln (seit 0.38.54)
            x, y, z = unten["x"], unten["y"], unten["z"] + WUERFEL + 0.002
            text = unten["name"]
        elif k is not None:
            platz = self._platz_in(k)
            x, y, z = k["x"] + platz[0], k["y"] + platz[1], k["h"] + 0.02
            text = k["name"]
        elif str(ziel or "").strip().lower() in ("", "zurück", "zurueck", "platz", "werkbank", "tisch"):
            (x, y), z, text = d["start"], WUERFEL / 2, "seinen Platz"
        else:
            return None, f"Kenne „{ziel}“ nicht – Ziele: {', '.join(self.namen()['kisten'])} oder „Platz“."
        schritte = [(x, y, TRAGEN, GREIFER_ZU, 1.2, None), (x, y, z, GREIFER_ZU, 0.6, None),
                    (x, y, z, GREIFER_AUF, 0.4, f"loslassen:{k['name'] if k else ('auf:' + unten['name']) if unten else ''}"),
                    (x, y, TRAGEN, GREIFER_AUF, 0.6, None)]
        return self._plan(schritte, f"Da komme ich nicht hin – {text} ist außerhalb meiner Reichweite.", von, None,
                          parken=True)

    def _stapelziel(self, ziel: str, haelt: dict[str, Any]) -> dict[str, Any] | str | None:
        """„auf den blauen Würfel“ / „blauer Würfel“ → der Würfel, auf den gestapelt wird; Text = Grund, warum nicht."""
        n = str(ziel or "").strip().lower()
        for vorn in ("auf den ", "auf dem ", "auf die ", "auf "):
            n = n.removeprefix(vorn)
        kandidaten = [x for x in self.dinge if x["name"] != haelt["name"]                 # „roten“ passt zu „rot…“
                      and (x["name"].lower() == n or any(w.startswith(_farbwort(x["name"])) for w in n.split()))]
        if not kandidaten:
            return None
        u = kandidaten[0]
        if u.get("in"):
            return f"{u['name']} liegt in der {u['in']} – darin staple ich nicht."
        if any(x.get("auf") == u["name"] for x in self.dinge):
            return f"Auf dem Würfel liegt schon etwas ({u['name']} ist belegt)."
        if u["z"] + WUERFEL > HOECHSTER_STAPEL:
            return "Höher reicht mein Arm nicht – drei Würfel sind mein Turm."
        return u

    def _haltungen(self, schritte, drehung: float):
        plan = []
        for x, y, z, greifer, s, aktion in schritte:
            g = self._ik(x, y, z, greifer, drehung)
            if g is None and z == TRAGEN:                  # nah am Sockel: flacher tragen (seit 0.38.54, Spielfeld)
                g = self._ik(x, y, TRAGEN_FLACH, greifer, drehung)
            if g is None:
                return None
            plan.append((g, s, aktion))
        return plan

    def _plan(self, schritte, grund_weit: str, von: dict[str, float] | None = None, ziel: str | None = None,
              parken: bool = False):
        """Haltungen zu den Schritten – mit einem Weg, auf dem der Greifer nichts trifft (seit 0.38.55)."""
        loslassen = any(a and a.startswith("loslassen") for *_, a in schritte)
        weiten = [w for w in WEITEN if not loslassen or w >= OFFEN_LAESST_FALLEN + 5]
        anstoss = None
        for drehung in DREHUNGEN:
            haltungen = self._haltungen(schritte, drehung)
            if haltungen is None:
                continue
            for weite in weiten:
                plan = [({**g, "gripper": weite if g["gripper"] == GREIFER_AUF else g["gripper"]}, s, a)
                        for g, s, a in haltungen]
                for ruhe in (PARKEN if parken else (None,)):
                    voll, hit = self._weg(plan + [(dict(ruhe), 1.0, None)] if ruhe else plan, von, ziel)
                    if voll is not None:
                        return voll, ""
                    anstoss = anstoss or hit
        if anstoss is None:
            return None, grund_weit
        return None, f"Dabei würde ich an {anstoss} stoßen – mach mir bitte erst Platz."

    @staticmethod
    def _ueberfahrt(a: dict[str, float], b: dict[str, float]) -> list[dict[str, float]]:
        """Umweg über die Werkbank: hoch (Greifer schaut von oben), hinüberschwenken – danach hinab zu `b`."""
        hoch = PARKEN[1]
        return [{**hoch, "shoulder_pan": p["shoulder_pan"], "wrist_roll": p.get("wrist_roll", 0.0),
                 "gripper": a.get("gripper", 0.0)} for p in (a, b)]

    def _weg(self, plan, von: dict[str, float] | None, ziel: str | None):
        """Der Plan mit einem Weg, auf dem der Greifer nichts trifft – wo nötig mit Überfahrt. Sonst (None, was im Weg
        wäre). Gegriffenes und Gehaltenes zählt nicht als Hindernis."""
        hin = W.hindernisse(self.dinge, self.kisten, WUERFEL, {n for n in (ziel, self.haelt) if n})
        vorher = dict(von or POSEN["bereit"])
        traegt = self.haelt is not None
        out = []
        for g, s, aktion in plan:
            loslassen = bool(aktion and aktion.startswith("loslassen"))
            mit = traegt and not loslassen
            hit = W.weg(vorher, g, hin, mit, WUERFEL)
            if hit is not None:
                um = self._ueberfahrt(vorher, g)
                if aktion or vorher.get("gripper") != g.get("gripper") or any(W.weg(x, y, hin, mit, WUERFEL) is not None for x, y in zip([vorher, *um], [*um, g])):
                    return None, hit
                out += [(u, 0.8, None) for u in um]
            out.append((g, s, aktion))
            if aktion and aktion.startswith("fassen"):
                traegt = True
            elif loslassen:
                traegt = False
            vorher = g
        return out, None

    def _platz_in(self, k: dict[str, Any]) -> tuple[float, float]:
        """Freier Platz in der Kiste: bis zu vier Würfel nebeneinander."""
        belegt = sum(1 for d in self.dinge if d["in"] == k["name"])
        versatz = KISTE_VERSATZ
        return [(-versatz, -versatz), (versatz, versatz), (-versatz, versatz), (versatz, -versatz)][belegt % 4]

    # ── Handlungen beim Ankommen ─────────────────────────────────────────
    def ausfuehren(self, aktion: str, gelenke: dict[str, float]) -> None:
        art, _, name = aktion.partition(":")
        if art == "fassen":
            d = self.ding(name)
            if d is not None and self.haelt is None:
                self.haelt = d["name"]
                d["in"] = d["auf"] = None
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
        d["auf"] = None
        # Tic-Tac-Toe: aufs Feld, das gemeint ist – oder auf das, über dem die Spitze gerade ist (der Greifer öffnet
        # sich schon im Anflug, `OFFEN_LAESST_FALLEN`)
        f = next((f for f in self.felder if kiste == f"feld:{f['nr']}" or math.hypot(x - f["x"], y - f["y"]) < 0.02), None)
        if f is not None:
            d["x"], d["y"], d["z"], d["in"], d["feld"] = f["x"], f["y"], WUERFEL / 2, None, f["nr"]
            return d["name"]
        stapel = self.ding(kiste[4:]) if kiste and kiste.startswith("auf:") else None
        if stapel is None:                                       # knapp über einem freien Würfel: landet darauf
            stapel = next((u for u in self.dinge if u is not d and not u.get("in")
                           and math.hypot(x - u["x"], y - u["y"]) < WUERFEL / 2
                           and not any(o.get("auf") == u["name"] for o in self.dinge if o is not d)), None)
        unter = None if stapel is not None else next(
            (k for k in self.kisten if (kiste and k["name"] == kiste)
             or (abs(x - k["x"]) <= k["s"] / 2 and abs(y - k["y"]) <= k["s"] / 2)), None)
        if stapel is not None:
            d["x"], d["y"], d["z"], d["in"], d["auf"] = stapel["x"], stapel["y"], stapel["z"] + WUERFEL, None, stapel["name"]
        elif unter is not None:
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
        self.felder: list[dict[str, Any]] = []                  # Tic-Tac-Toe-Felder, solange ein Spiel läuft
        self.spiel: Any = None

    def als_dict(self) -> dict[str, Any]:
        return {"dinge": [{k: v for k, v in d.items() if k != "start"} for d in self.dinge],
                "kisten": self.kisten, "haelt": self.haelt, "wuerfel": WUERFEL, "felder": self.felder,
                "spiel": self.spiel.als_dict() if self.spiel is not None else None}
