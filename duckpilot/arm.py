"""Arm-Haltungen und -Gesten (seit 0.38.47, Etappe G5) – für Körper mit der Fähigkeit „arm“ (SO-101 und andere
LeRobot-Arme mit denselben Gelenknamen).

Winkel in Grad, „neue Kalibrierung“ des SO-101: Null ist bei jedem Gelenk die Mitte seines Bereichs – Oberarm senkrecht,
Unterarm waagerecht nach vorn. Positives `shoulder_lift` kippt den Oberarm nach vorn, positives `elbow_flex` senkt den
Unterarm, positives `wrist_flex` senkt das Handgelenk; `gripper` 0 = zu, größer = offen.

Eine **Geste** ist eine Folge von Haltungen mit Dauer; der Körper fährt sie nacheinander an (`haltung(gelenke, s)`).
Gesten sind Daten – der Aktionskatalog (`aktionen.py`) nennt sie als Umsetzung, wenn der Körper einen Arm hat.
Diese Datei gehört zur Basis und importiert nichts aus Knowlin.
"""

from __future__ import annotations

import math
from typing import Any

GELENKE = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
# Grenzen aus so101_new_calib.xml (Grad), je ein Grad Luft
GRENZEN: dict[str, tuple[float, float]] = {
    "shoulder_pan": (-109.0, 109.0), "shoulder_lift": (-99.0, 99.0), "elbow_flex": (-95.8, 95.8),
    "wrist_flex": (-94.0, 94.0), "wrist_roll": (-156.2, 161.8), "gripper": (-9.0, 99.0),
}
NAMEN = {"greifer": "gripper", "schulter": "shoulder_pan", "heben": "shoulder_lift", "ellbogen": "elbow_flex",
         "handgelenk": "wrist_flex", "drehen": "wrist_roll"}

POSEN: dict[str, dict[str, float]] = {
    "ruhe": {"shoulder_pan": 0, "shoulder_lift": -98, "elbow_flex": 95, "wrist_flex": 70, "wrist_roll": 0, "gripper": 0},
    "bereit": {"shoulder_pan": 0, "shoulder_lift": -40, "elbow_flex": 50, "wrist_flex": 60, "wrist_roll": 0,
               "gripper": 5},
    "hoch": {"shoulder_pan": 0, "shoulder_lift": -60, "elbow_flex": -30, "wrist_flex": 0, "wrist_roll": 0,
             "gripper": 10},
    "zeigen": {"shoulder_pan": 0, "shoulder_lift": 10, "elbow_flex": -15, "wrist_flex": 5, "wrist_roll": 0,
               "gripper": 0},
    "traurig": {"shoulder_pan": -15, "shoulder_lift": -96, "elbow_flex": 93, "wrist_flex": 78, "wrist_roll": 0,
                "gripper": 0},
    "staunen": {"shoulder_pan": 0, "shoulder_lift": -55, "elbow_flex": -20, "wrist_flex": -20, "wrist_roll": 0,
                "gripper": 60},
}


def _mit(basis: str, **aenderung: float) -> dict[str, float]:
    return {**POSEN[basis], **aenderung}


# Geste: [(Haltung, Sekunden), …] – jede Haltung vollständig, damit die Geste von überall gleich aussieht
GESTEN: dict[str, list[tuple[dict[str, float], float]]] = {
    "winken": [(POSEN["hoch"], 0.9), (_mit("hoch", wrist_flex=35), 0.35), (_mit("hoch", wrist_flex=-35), 0.35),
               (_mit("hoch", wrist_flex=35), 0.35), (_mit("hoch", wrist_flex=-35), 0.35), (POSEN["bereit"], 0.9)],
    "nicken": [(POSEN["bereit"], 0.6), (_mit("bereit", wrist_flex=85), 0.3), (_mit("bereit", wrist_flex=40), 0.3),
               (_mit("bereit", wrist_flex=85), 0.3), (POSEN["bereit"], 0.4)],
    "kopfschuetteln": [(POSEN["bereit"], 0.6), (_mit("bereit", wrist_roll=35), 0.3), (_mit("bereit", wrist_roll=-35), 0.4),
                       (_mit("bereit", wrist_roll=35), 0.4), (POSEN["bereit"], 0.3)],
    "freuen": [(POSEN["hoch"], 0.8), (_mit("hoch", gripper=60, wrist_roll=30), 0.3),
               (_mit("hoch", gripper=0, wrist_roll=-30), 0.3), (_mit("hoch", gripper=60, wrist_roll=30), 0.3),
               (_mit("hoch", gripper=0, wrist_roll=0), 0.3), (POSEN["bereit"], 0.9)],
    "neugierig": [(_mit("bereit", wrist_roll=30, shoulder_pan=15, wrist_flex=45), 0.8),
                  (_mit("bereit", wrist_roll=30, shoulder_pan=15, wrist_flex=45), 1.0), (POSEN["bereit"], 0.7)],
    "umsehen": [(POSEN["bereit"], 0.6), (_mit("bereit", shoulder_pan=-40), 1.0), (_mit("bereit", shoulder_pan=40), 1.6),
                (POSEN["bereit"], 0.9)],
    "traurig": [(POSEN["traurig"], 1.6)],
    "staunen": [(POSEN["staunen"], 0.6), (POSEN["staunen"], 1.0), (POSEN["bereit"], 0.9)],
    "ruhe": [(POSEN["ruhe"], 1.5)],
    "bereit": [(POSEN["bereit"], 1.0)],
    "zeigen": [(POSEN["zeigen"], 1.0)],
    "aufmerksam": [(POSEN["hoch"], 0.8), (_mit("hoch", shoulder_pan=20, wrist_flex=35), 0.35),
                   (_mit("hoch", shoulder_pan=-20, wrist_flex=-35), 0.45), (_mit("hoch", shoulder_pan=20, wrist_flex=35), 0.45),
                   (POSEN["hoch"], 0.35)],
}


# Tanz (seit 0.43, Bauart „arm“ in motion/tanzstile.py): Name → [(Haltung, Schläge)] – jede Bewegung beginnt und endet
# in „hoch“, damit sie sich ohne Ruck wiederholt. Alles bleibt oben über der Werkbank; ob unterwegs etwas im Weg ist,
# prüft der Körper vor dem Tanzen (werkbank_weg).
TANZ: dict[str, list[tuple[dict[str, float], float]]] = {
    "wiegen": [(_mit("hoch", shoulder_pan=-22, wrist_roll=-15), 1.0), (_mit("hoch", shoulder_pan=22, wrist_roll=15), 1.0)],
    "nicken": [(_mit("hoch", wrist_flex=30), 0.5), (_mit("hoch", wrist_flex=-20), 0.5)],
    "greifer_takt": [(_mit("hoch", gripper=55), 0.5), (_mit("hoch", gripper=5), 0.5)],
    "kreisen": [(_mit("hoch", wrist_roll=60), 1.0), (_mit("hoch", wrist_roll=-60), 1.0)],
    "schwingen": [(_mit("hoch", shoulder_lift=-80, elbow_flex=-55), 1.0), (_mit("hoch", shoulder_lift=-45, elbow_flex=-10), 1.0)],
    "winken": [(_mit("hoch", wrist_flex=35), 0.5), (_mit("hoch", wrist_flex=-35), 0.5)],
    "jubeln": [(_mit("hoch", shoulder_pan=-30, gripper=60, wrist_roll=40), 1.0),
               (_mit("hoch", shoulder_pan=30, gripper=0, wrist_roll=-40), 1.0)],
}


def tanz_folge(name: str, sekunden: float, bpm: float) -> list[tuple[dict[str, float], float]]:
    """Eine Tanzbewegung im Takt, so oft wiederholt, wie in `sekunden` passt (mindestens einmal). Erst nach „hoch“."""
    schlag = 60.0 / max(40.0, min(220.0, float(bpm)))
    eine = [(h, max(0.15, n * schlag)) for h, n in TANZ[name]]
    laenge = sum(s for _, s in eine)
    mal = max(1, int(max(0.0, float(sekunden) - 0.6) // laenge))
    return [(POSEN["hoch"], 0.6), *eine * mal]


def begrenzen(gelenke: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
    """Namen übersetzen (auch deutsch), Grenzen einhalten. Rückgabe: (Haltung in Grad, unbekannte Namen)."""
    out: dict[str, float] = {}
    unbekannt: list[str] = []
    for name, wert in (gelenke or {}).items():
        g = NAMEN.get(str(name).lower(), str(name))
        if g not in GRENZEN or not isinstance(wert, (int, float)) or isinstance(wert, bool) or not math.isfinite(wert):
            unbekannt.append(str(name))
            continue
        lo, hi = GRENZEN[g]
        out[g] = max(lo, min(hi, float(wert)))
    return out, unbekannt


# Was die Tricks-Seite zeigt (seit 0.38.55, Maintainer: „wieso hat Ari noch fremde Tricks?“) – Haltungen wie „ruhe“
# und „bereit“ stehen schon als Knöpfe im Cockpit
TITEL = {"winken": "Winken", "freuen": "Freuen", "nicken": "Ja (nicken)", "kopfschuetteln": "Nein (Greifer schütteln)",
         "neugierig": "Neugierig", "aufmerksam": "Aufmerksam", "umsehen": "Umsehen", "staunen": "Staunen",
         "zeigen": "Zeigen", "traurig": "Traurig"}


def dauer(geste: str) -> float:
    return sum(s for _, s in GESTEN.get(geste, []))
