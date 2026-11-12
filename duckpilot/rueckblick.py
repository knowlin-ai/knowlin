"""Rückblick in Ruhephasen (seit 0.38.45, Etappe G4 aus dem Konzept „Knowlins Geist“).

Wenn länger Ruhe ist, schaut Knowlin auf seine Gedankenspur zurück und leitet daraus kleine **Lehren** ab – etwa „den
Raum erkunden klappt hier gerade oft nicht“ oder „mag Tricks üben“. Eine Lehre wirkt nur auf die Gewichte der eigenen
Beschäftigungen dieser Verkörperung (Faktor `MIN_FAKTOR` … `MAX_FAKTOR`); sie schaltet nie etwas frei, und alle
Sperren und der Wertekern gelten unverändert.

Wunsch des Maintainers: „nicht erzählen, aber dokumentieren – so dass man ggf. korrigieren oder löschen kann“. Lehren
stehen in einer Liste (was, wann, woraus gelernt); jede lässt sich korrigieren („seltener“, „wie vorher“, „öfter“) oder
löschen. Knowlin erzählt sie nicht ungefragt. Lehren betreffen nie Personen – nur Arten von Beschäftigung; gespeichert wird die Struktur, der Text entsteht je
Sprache beim Anzeigen (`in_worten`).
Diese Datei gehört zur Basis und importiert nichts aus Knowlin.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

# Wie Beschäftigungen in einer Lehre heißen (Arten aus `motion/eigenstaendig.angebot`): (deutsch, englisch)
ARTEN: dict[str, tuple[str, str]] = {
    "umschauen": ("sich umschauen", "looking around"), "erkunden": ("den Raum erkunden", "exploring the room"),
    "ding": ("zu Dingen gehen", "going to things"), "anschauen": ("Dinge anschauen", "looking at things"),
    "gefuehl": ("Gefühle zeigen", "showing feelings"), "pollen": ("kleine Bewegungen von Pollen", "Pollen's small moves"),
    "zuwenden": ("sich dir zuwenden", "turning to you"), "antennen": ("mit den Antennen spielen", "playing with the antennas"),
    "sitzen": ("sich hinsetzen", "sitting down"), "trick": ("Tricks üben", "practising tricks"),
    "tanzen": ("tanzen", "dancing"), "ball": ("mit dem Ball spielen", "playing with the ball"),
    "laufen": ("herumlaufen", "walking around"), "aufstehen": ("aufstehen", "standing up"),
    "geste": ("Gesten machen", "making gestures"), "armgeste": ("den Arm bewegen", "moving the arm"),
}
ART_TEXT = {k: v[0] for k, v in ARTEN.items()}
FEHLSCHLAEGE = 2           # so oft „ging nicht“ seit dem letzten Rückblick → „klappt gerade oft nicht“
GERN = 3                   # so oft gelungen → „mag …“
MIN_FAKTOR, MAX_FAKTOR = 0.3, 1.5
RICHTUNG = {"seltener": 0.5, "normal": 1.0, "oefter": 1.3}


def _uhr(t: float) -> str:
    return time.strftime("%H:%M", time.localtime(t))


def _gross(s: str) -> str:
    return s[:1].upper() + s[1:]


def in_worten(lehre: dict[str, Any], sprache: str = "de") -> dict[str, str]:
    """Was gelernt wurde und woraus – in der Sprache der Oberfläche (gespeichert wird nur die Struktur)."""
    if "typ" not in lehre:                          # aus 0.38.45: Text war gespeichert
        return {"was": str(lehre.get("was", "")), "woraus": str(lehre.get("woraus", ""))}
    en = sprache == "en"
    name = ARTEN.get(lehre.get("art", ""), (lehre.get("art", ""),) * 2)[1 if en else 0]
    n = lehre.get("n", 0)
    if lehre.get("typ") == "selten":
        von, bis = _uhr(lehre.get("von", 0)), _uhr(lehre.get("bis", 0))
        return ({"was": _gross(f"{name} often doesn't work here right now – less often"),
                 "woraus": f"failed {n}× between {von} and {bis}"} if en else
                {"was": _gross(f"{name} klappt hier gerade oft nicht – lieber seltener"),
                 "woraus": f"{n}× nicht geklappt zwischen {von} und {bis}"})
    return ({"was": f"Likes {name}", "woraus": f"did it {n}× on his own, worked every time"} if en else
            {"was": f"Mag {name}", "woraus": f"{n}× von sich aus gemacht, jedes Mal geklappt"})


def ableiten(zeilen: list[dict[str, Any]], seit: float) -> list[dict[str, Any]]:
    """Aus Zeilen der Gedankenspur (`quelle` antrieb, mit `art`) seit `seit` neue Lehren vorschlagen."""
    eigene = [z for z in zeilen if z.get("quelle") == "antrieb" and z.get("art") in ART_TEXT and z["zeit"] > seit]
    fehl = Counter(z["art"] for z in eigene if z.get("ergebnis") == "ging nicht")
    gut = Counter(z["art"] for z in eigene if z.get("ergebnis") == "getan")
    lehren = []
    for art, n in fehl.items():
        if n >= FEHLSCHLAEGE:
            zeiten = sorted(z["zeit"] for z in eigene if z["art"] == art and z.get("ergebnis") == "ging nicht")
            lehren.append({"art": art, "typ": "selten", "faktor": 0.5, "n": n, "von": zeiten[0], "bis": zeiten[-1]})
    for art, n in gut.items():
        if n >= GERN and fehl.get(art, 0) == 0:
            lehren.append({"art": art, "typ": "gern", "faktor": 1.2, "n": n})
    return lehren


class Lehrbuch:
    """Die dokumentierten Lehren je Verkörperung – in `rueckblick.json` im Datenordner."""

    def __init__(self, pfad: Path) -> None:
        self.pfad = pfad
        try:
            roh = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            roh = {}
        self.lehren: list[dict[str, Any]] = [x for x in roh.get("lehren", []) if isinstance(x, dict) and x.get("id")]
        self.zuletzt: float = float(roh.get("zuletzt") or 0.0)

    def _speichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps({"zuletzt": self.zuletzt, "lehren": self.lehren}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(self.pfad)

    def zurueckblicken(self, zeilen: list[dict[str, Any]], koerper: str, jetzt: float | None = None) -> list[dict]:
        """Neue Lehren ablegen; eine schon vorhandene zur selben Art wird aufgefrischt statt verdoppelt –
        außer der Mensch hat sie korrigiert: Dann bleibt seine Fassung."""
        jetzt = time.time() if jetzt is None else jetzt
        neu = []
        for vorschlag in ableiten(zeilen, self.zuletzt):
            alt = next((x for x in self.lehren if x["koerper"] == koerper and x["art"] == vorschlag["art"]), None)
            if alt is not None:
                if not alt.get("korrigiert"):
                    alt.update(vorschlag, zeit=jetzt)
                continue
            eintrag = {"id": uuid.uuid4().hex[:10], "zeit": jetzt, "koerper": koerper, "korrigiert": None, **vorschlag}
            self.lehren.append(eintrag)
            neu.append(eintrag)
        self.zuletzt = jetzt
        self._speichern()
        return neu

    def liste(self, sprache: str = "de") -> list[dict[str, Any]]:
        """Neueste zuerst, mit `was` und `woraus` in der Sprache der Oberfläche."""
        return [{**x, **in_worten(x, sprache)} for x in sorted(self.lehren, key=lambda x: -x["zeit"])]

    def faktor(self, koerper: str, art: str) -> float:
        for x in self.lehren:
            if x["koerper"] == koerper and x["art"] == art:
                return max(MIN_FAKTOR, min(MAX_FAKTOR, float(x["faktor"])))
        return 1.0

    def korrigieren(self, lid: str, richtung: str) -> dict[str, Any] | None:
        if richtung not in RICHTUNG:
            raise ValueError("richtung: seltener, normal oder oefter")
        x = next((x for x in self.lehren if x["id"] == lid), None)
        if x is None:
            return None
        x["faktor"] = RICHTUNG[richtung]
        x["korrigiert"] = richtung
        self._speichern()
        return x

    def loeschen(self, lid: str) -> bool:
        vorher = len(self.lehren)
        self.lehren = [x for x in self.lehren if x["id"] != lid]
        if len(self.lehren) != vorher:
            self._speichern()
            return True
        return False
