"""Rückblick in Ruhephasen (seit 0.38.45, Etappe G4 aus dem Konzept „Knowlins Geist“).

Wenn länger Ruhe ist, schaut Knowlin auf seine Gedankenspur zurück und leitet daraus kleine **Lehren** ab – etwa „den
Raum erkunden klappt hier gerade oft nicht“ oder „mag Tricks üben“. Eine Lehre wirkt nur auf die Gewichte der eigenen
Beschäftigungen dieser Verkörperung (Faktor `MIN_FAKTOR` … `MAX_FAKTOR`); sie schaltet nie etwas frei, und alle
Sperren und der Wertekern gelten unverändert.

Wunsch des Maintainers: „nicht erzählen, aber dokumentieren – so dass man ggf. korrigieren oder löschen kann“. Lehren
stehen in einer Liste (was, wann, woraus gelernt); jede lässt sich korrigieren („seltener“, „wie vorher“, „öfter“) oder
löschen. Knowlin erzählt sie nicht ungefragt. Lehren betreffen nie Personen – nur Arten von Beschäftigung.
Diese Datei gehört zur Basis und importiert nichts aus Knowlin.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

# Wie Beschäftigungen in einer Lehre heißen (Arten aus `motion/eigenstaendig.angebot`)
ART_TEXT = {
    "umschauen": "sich umschauen", "erkunden": "den Raum erkunden", "ding": "zu Dingen gehen",
    "anschauen": "Dinge anschauen", "gefuehl": "Gefühle zeigen", "pollen": "kleine Bewegungen von Pollen",
    "zuwenden": "sich dir zuwenden", "antennen": "mit den Antennen spielen", "sitzen": "sich hinsetzen",
    "trick": "Tricks üben", "tanzen": "tanzen", "ball": "mit dem Ball spielen", "laufen": "herumlaufen",
    "aufstehen": "aufstehen", "geste": "Gesten machen",
}
FEHLSCHLAEGE = 2           # so oft „ging nicht“ seit dem letzten Rückblick → „klappt gerade oft nicht“
GERN = 3                   # so oft gelungen → „mag …“
MIN_FAKTOR, MAX_FAKTOR = 0.3, 1.5
RICHTUNG = {"seltener": 0.5, "normal": 1.0, "oefter": 1.3}


def _uhr(t: float) -> str:
    return time.strftime("%H:%M", time.localtime(t))


def _gross(s: str) -> str:
    return s[:1].upper() + s[1:]


def ableiten(zeilen: list[dict[str, Any]], seit: float) -> list[dict[str, Any]]:
    """Aus Zeilen der Gedankenspur (`quelle` antrieb, mit `art`) seit `seit` neue Lehren vorschlagen."""
    eigene = [z for z in zeilen if z.get("quelle") == "antrieb" and z.get("art") in ART_TEXT and z["zeit"] > seit]
    fehl = Counter(z["art"] for z in eigene if z.get("ergebnis") == "ging nicht")
    gut = Counter(z["art"] for z in eigene if z.get("ergebnis") == "getan")
    lehren = []
    for art, n in fehl.items():
        if n >= FEHLSCHLAEGE:
            zeiten = sorted(z["zeit"] for z in eigene if z["art"] == art and z.get("ergebnis") == "ging nicht")
            lehren.append({"art": art, "faktor": 0.5, "was": _gross(f"{ART_TEXT[art]} klappt hier gerade oft nicht – lieber seltener"),
                           "woraus": f"{n}× nicht geklappt zwischen {_uhr(zeiten[0])} und {_uhr(zeiten[-1])}"})
    for art, n in gut.items():
        if n >= GERN and fehl.get(art, 0) == 0:
            lehren.append({"art": art, "faktor": 1.2, "was": f"Mag {ART_TEXT[art]}",
                           "woraus": f"{n}× von sich aus gemacht, jedes Mal geklappt"})
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

    def liste(self) -> list[dict[str, Any]]:
        return sorted(self.lehren, key=lambda x: -x["zeit"])

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
