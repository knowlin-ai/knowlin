"""Charakter im Leerlauf: was die Ente tut, wenn sie gerade nichts zu tun hat.

Die Persönlichkeit ist ein Punkt auf der X/Y-Fläche (ruhig ↔ lebhaft, ernst ↔ albern) mit zwölf
Charakteren. „Ausgeglichen“ in der Mitte ist neutral: Die Ente schaut sich nur ruhig um. Jeder andere
Charakter hat
- eine eigene **Mimik und Haltung** im Leerlauf (Blickhöhe, Kopfneigung, Körperhöhe, Tempo des
  Umschauens, Schnabelzucken, Wippen) – siehe `TRAITS`, umgesetzt in `IdleLife`,
- ein eigenes **Repertoire an Gesten** (gähnen, dösen, Gefieder putzen, mustern, wippen, trällern,
  niesen …) mit Häufigkeit – siehe `REPERTOIRE`, ausgelöst von der `MotionEngine`.

Alles hier bewegt nur Kopf, Schnabel und Körperhaltung, nie die Beine. Einzige Ausnahme sind die
Albernheiten mit Drehen aus `behaviors.ANTICS` – die laufen nur im Simulator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Zeilen von ernst (unten) nach albern (oben), Spalten ruhig → lebhaft – wie personality.js
NAMES = [
    ["Gelassen", "Sachlich", "Eifrig"],
    ["Gemütlich", "Ausgeglichen", "Munter"],
    ["Verträumt", "Verschmitzt", "Quirlig"],
    ["Tollpatschig", "Goofy", "Chaos-Ente"],
]
NEUTRAL = "Ausgeglichen"


def persona(energie: float, humor: float) -> str:
    row = 0 if humor < 0.25 else 1 if humor < 0.5 else 2 if humor < 0.75 else 3
    col = 0 if energie < 0.34 else 1 if energie < 0.67 else 2
    return NAMES[row][col]


@dataclass(frozen=True)
class Traits:
    """Mimik im Leerlauf. Winkel in rad, Höhe in m; 1.0 = wie bisher."""
    gaze: float = 0.0          # Blickhöhe: < 0 = Schnabel eher hoch
    neck: float = 0.0          # < 0 = Hals vorgereckt (aufmerksam)
    roll: float = 0.0          # Kopf schief halten (Betrag, Seite wechselt)
    height: float = 0.0        # Körperhöhe
    pace: float = 1.0          # Tempo des Umschauens (größer = öfter)
    reach: float = 1.0         # wie weit sie sich umschaut
    hold: float = 1.0          # wie lange sie an einem Punkt verweilt
    chatter: float = 0.08      # Schnabel zuckt beim Umschauen
    bob: float = 0.0           # Wippen mit dem Kopf (Amplitude)
    fidget: float = 0.0        # Zappeln: kleine Körper-Rollbewegungen
    breathe: float = 1.0       # Atemtiefe


TRAITS: dict[str, Traits] = {
    "Gelassen": Traits(gaze=0.02, height=-0.003, pace=0.6, reach=0.75, hold=1.6, chatter=0.03, breathe=1.2),
    "Sachlich": Traits(gaze=0.0, neck=-0.04, pace=0.9, reach=0.9, hold=1.2, chatter=0.02),
    "Eifrig": Traits(gaze=-0.06, neck=-0.12, height=0.004, pace=1.8, reach=1.1, hold=0.7, chatter=0.1, bob=0.02),
    "Gemütlich": Traits(gaze=0.1, roll=0.06, height=-0.007, pace=0.55, reach=0.7, hold=1.8, chatter=0.05, breathe=1.4),
    "Ausgeglichen": Traits(),
    "Munter": Traits(gaze=-0.1, height=0.004, pace=1.6, reach=1.15, hold=0.8, chatter=0.2, bob=0.04),
    "Verträumt": Traits(gaze=-0.2, roll=0.12, height=-0.004, pace=0.5, reach=0.8, hold=2.2, chatter=0.06, breathe=1.3),
    "Verschmitzt": Traits(gaze=-0.04, roll=0.1, pace=1.2, reach=1.0, hold=1.0, chatter=0.3, bob=0.02),
    "Quirlig": Traits(gaze=-0.08, roll=0.08, height=0.003, pace=2.3, reach=1.25, hold=0.5, chatter=0.35, bob=0.05, fidget=0.5),
    "Tollpatschig": Traits(gaze=0.06, roll=0.1, height=-0.002, pace=0.8, reach=1.0, hold=1.3, chatter=0.2, fidget=0.2),
    "Goofy": Traits(gaze=-0.05, roll=0.12, pace=1.5, reach=1.2, hold=0.9, chatter=0.3, bob=0.03, fidget=0.3),
    "Chaos-Ente": Traits(gaze=-0.08, roll=0.14, height=0.002, pace=2.6, reach=1.35, hold=0.45, chatter=0.45, bob=0.05, fidget=0.7),
}

# Was sie im Leerlauf tut: (Geste, Gewicht). Gesten stehen in GESTURES (hier), in behaviors.EMOTIONS
# (Gefühle, auch Pollens) oder in behaviors.ANTICS (Albernheiten). Abstand in Sekunden (von, bis).
REPERTOIRE: dict[str, dict[str, Any]] = {
    "Gelassen": {"abstand": (16, 30), "gesten": [("seufzen", 3), ("mustern", 2), ("gefieder_putzen", 2), ("himmel_gucken", 1), ("nicken", 1)]},
    "Sachlich": {"abstand": (14, 26), "gesten": [("mustern", 3), ("haltung", 3), ("nicken", 2), ("aufhorchen", 1)]},
    "Eifrig": {"abstand": (7, 13), "gesten": [("aufhorchen", 3), ("umherspaehen", 3), ("mustern", 2), ("nicken", 2), ("hibbeln", 1)]},
    "Gemütlich": {"abstand": (11, 20), "gesten": [("gaehnen", 3), ("seufzen", 3), ("gefieder_putzen", 2), ("doesen", 2)]},
    "Ausgeglichen": {"abstand": None, "gesten": []},
    "Munter": {"abstand": (7, 12), "gesten": [("wippen", 3), ("traellern", 3), ("aufhorchen", 2), ("umherspaehen", 2), ("freude", 1)]},
    "Verträumt": {"abstand": (9, 16), "gesten": [("himmel_gucken", 3), ("gaehnen", 2), ("doesen", 2), ("staunen", 2),
                                                  ("traellern", 1), ("selbstgespraech", 1)]},
    "Verschmitzt": {"abstand": (8, 14), "gesten": [("selbstgespraech", 3), ("naeaeae", 2), ("wackeln", 2), ("traellern", 1),
                                                    ("trotzig", 1), ("erschrecken", 1)]},
    "Quirlig": {"abstand": (5, 9), "gesten": [("hibbeln", 3), ("wippen", 3), ("wackeln", 2), ("umherspaehen", 2), ("schluckauf", 1),
                                              ("traellern", 1), ("aufgeregt", 1)]},
    "Tollpatschig": {"abstand": (8, 14), "gesten": [("niesen", 3), ("doesen", 2), ("erschrecken", 2), ("boden_picken", 2), ("gaehnen", 1),
                                                    ("stolpern", 1)]},
    "Goofy": {"abstand": (6, 11), "gesten": [("niesen", 2), ("schluckauf", 2), ("selbstgespraech", 2), ("wackeln", 2), ("boden_picken", 2),
                                             ("schwanz_jagen", 2), ("lachen", 1), ("naeaeae", 1)]},
    "Chaos-Ente": {"abstand": (4, 7), "gesten": [("schwanz_jagen", 3), ("niesen", 2), ("schluckauf", 2), ("hibbeln", 2), ("wackeln", 2),
                                                 ("selbstgespraech", 2), ("boden_picken", 1), ("lachen", 1), ("aufgeregt", 1), ("erschrecken", 1)]},
}

# Nach diesen Gesten schüttelt sie sich gackernd – nur im Goofy-Bereich (wie bei allem Quatsch).
QUATSCH = {"niesen", "schluckauf", "erschrecken", "selbstgespraech", "wackeln", "boden_picken", "schwanz_jagen", "stolpern"}

# Was im Ticker steht
MESSAGES = {
    "gaehnen": "gähnt herzhaft", "doesen": "döst ein – und schreckt hoch", "seufzen": "seufzt zufrieden",
    "himmel_gucken": "träumt vor sich hin", "gefieder_putzen": "putzt sich das Gefieder", "wippen": "wippt im Takt",
    "aufhorchen": "horcht auf", "umherspaehen": "späht umher", "traellern": "trällert ein Liedchen",
    "hibbeln": "kann nicht stillhalten", "mustern": "mustert das Zimmer", "haltung": "richtet sich auf",
    "nicken": "nickt zufrieden", "niesen": "niest – hatschi!", "schluckauf": "hat Schluckauf", "erschrecken": "erschrickt vor nichts",
    "freude": "freut sich einfach so", "staunen": "staunt", "trotzig": "ist kurz trotzig", "naeaeae": "macht „Nänänä“",
    "aufgeregt": "ist aufgeregt", "lachen": "lacht vor sich hin", "stolpern": "stolpert über nichts",
}

# Gesten, die nur mit Schnabel Sinn ergeben (Fund 14.11. beim Website-Bild von Bello: der Hund „putzte sich das
# Gefieder“) – Körper ohne das Körperwort „schnabel“ lassen sie aus.
NUR_MIT_SCHNABEL = frozenset({"gefieder_putzen", "boden_picken"})

# ── Gesten des Leerlaufs (Grad, Millimeter – wie Choreografien). Die Laute dazu rendert
#    tools/render_gestures.py auf genau diese Takte.
GESTURES: dict[str, list[dict[str, Any]]] = {
    "gaehnen": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.5, "kopf": {"nicken": -18, "nacken": -8}, "schnabel": 0.2},
        {"t": 0.95, "kopf": {"nicken": -32, "nacken": -14, "neigen": 6}, "schnabel": 1.0, "koerper": {"hoehe_mm": 4, "kippen": -4}},
        {"t": 1.6, "kopf": {"nicken": -30, "nacken": -12, "neigen": 8}, "schnabel": 0.9},
        {"t": 2.05, "kopf": {"nicken": -4}, "schnabel": 0.0, "koerper": {}},
        {"t": 2.3, "kopf": {"drehen": 8, "neigen": 6}},
        {"t": 2.45, "kopf": {"drehen": -8, "neigen": -6}},
        {"t": 2.7, "kopf": {}},
    ],
    "doesen": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.6, "kopf": {"nicken": 10}},
        {"t": 1.6, "kopf": {"nicken": 24, "nacken": 10, "neigen": 8}, "koerper": {"hoehe_mm": -10}},
        {"t": 2.9, "kopf": {"nicken": 34, "nacken": 16, "neigen": 12}, "koerper": {"hoehe_mm": -16}},
        {"t": 3.2, "kopf": {"nicken": -16, "nacken": -8}, "schnabel": 0.6, "koerper": {"hoehe_mm": 3}},
        {"t": 3.45, "kopf": {"nicken": -10, "drehen": 22}, "schnabel": 0.1},
        {"t": 3.7, "kopf": {"nicken": -8, "drehen": -20}, "schnabel": 0.0},
        {"t": 4.1, "kopf": {}, "koerper": {}},
    ],
    "seufzen": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.65, "kopf": {"nicken": -12}, "koerper": {"hoehe_mm": 5}},
        {"t": 1.1, "kopf": {"nicken": 12, "neigen": 6}, "koerper": {"hoehe_mm": -10}, "schnabel": 0.3},
        {"t": 1.8, "kopf": {"nicken": 6, "neigen": 4}, "koerper": {"hoehe_mm": -6}, "schnabel": 0.0},
        {"t": 2.4, "kopf": {}, "koerper": {}},
    ],
    "himmel_gucken": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.8, "kopf": {"nicken": -34, "nacken": -10, "neigen": 10}, "schnabel": 0.2},
        {"t": 1.8, "kopf": {"nicken": -36, "nacken": -10, "drehen": 20, "neigen": 14}},
        {"t": 2.6, "kopf": {"nicken": -30, "drehen": -10, "neigen": 6}, "schnabel": 0.0},
        {"t": 3.4, "kopf": {}},
    ],
    "gefieder_putzen": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.7, "kopf": {"drehen": 55, "nicken": 30, "nacken": 12, "neigen": 24}},
        {"t": 0.92, "schnabel": 0.5, "kopf": {"drehen": 57, "nicken": 33, "nacken": 12, "neigen": 24}},
        {"t": 1.02, "schnabel": 0.0},
        {"t": 1.17, "schnabel": 0.5, "kopf": {"drehen": 53, "nicken": 30, "nacken": 12, "neigen": 26}},
        {"t": 1.27, "schnabel": 0.0},
        {"t": 1.47, "schnabel": 0.5, "kopf": {"drehen": 56, "nicken": 34, "nacken": 13, "neigen": 24}},
        {"t": 1.57, "schnabel": 0.0},
        {"t": 1.72, "schnabel": 0.4},
        {"t": 1.82, "schnabel": 0.0},
        {"t": 2.5, "kopf": {"drehen": -55, "nicken": 30, "nacken": 12, "neigen": -24}},
        {"t": 2.92, "schnabel": 0.5},
        {"t": 3.02, "schnabel": 0.0},
        {"t": 3.17, "schnabel": 0.5, "kopf": {"drehen": -53, "nicken": 33, "nacken": 12, "neigen": -26}},
        {"t": 3.27, "schnabel": 0.0},
        {"t": 3.42, "schnabel": 0.4},
        {"t": 3.52, "schnabel": 0.0},
        {"t": 3.95, "kopf": {"nicken": -4}},
        {"t": 4.3, "kopf": {"nicken": -8, "neigen": 6}, "schnabel": 0.15},
        {"t": 4.8, "kopf": {}, "schnabel": 0.0},
    ],
    "wippen": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.2, "kopf": {"nicken": -10, "neigen": 10}, "koerper": {"hoehe_mm": 6}, "schnabel": 0.3},
        {"t": 0.45, "kopf": {"nicken": 6}, "koerper": {"hoehe_mm": -4}, "schnabel": 0.0},
        {"t": 0.7, "kopf": {"nicken": -10, "neigen": -10}, "koerper": {"hoehe_mm": 6}, "schnabel": 0.3},
        {"t": 0.95, "kopf": {"nicken": 6}, "koerper": {"hoehe_mm": -4}, "schnabel": 0.0},
        {"t": 1.2, "kopf": {"nicken": -10, "neigen": 10}, "koerper": {"hoehe_mm": 6}, "schnabel": 0.3},
        {"t": 1.45, "kopf": {"nicken": 6}, "koerper": {"hoehe_mm": -4}, "schnabel": 0.0},
        {"t": 1.7, "kopf": {"nicken": -10, "neigen": -10}, "koerper": {"hoehe_mm": 6}, "schnabel": 0.3},
        {"t": 2.0, "kopf": {}, "koerper": {}, "schnabel": 0.0},
    ],
    "aufhorchen": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.24, "kopf": {"nicken": -20, "nacken": -12}, "koerper": {"hoehe_mm": 6}, "schnabel": 0.5},
        {"t": 0.45, "schnabel": 0.0},
        {"t": 0.7, "kopf": {"nicken": -16, "nacken": -12, "neigen": 18}},
        {"t": 1.15, "kopf": {"nicken": -14, "nacken": -10, "neigen": -14, "drehen": 10}},
        {"t": 1.3, "schnabel": 0.15},
        {"t": 1.6, "schnabel": 0.0},
        {"t": 2.1, "kopf": {}, "koerper": {}},
    ],
    "umherspaehen": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.22, "kopf": {"drehen": 40, "nicken": -8}, "schnabel": 0.35},
        {"t": 0.4, "schnabel": 0.0},
        {"t": 0.65, "kopf": {"drehen": -38, "nicken": -6}},
        {"t": 1.05, "kopf": {"drehen": -44, "nicken": -10, "neigen": 12}, "schnabel": 0.45},
        {"t": 1.25, "schnabel": 0.0},
        {"t": 1.5, "kopf": {"drehen": 15}},
        {"t": 2.0, "kopf": {}},
    ],
    "traellern": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.25, "kopf": {"nicken": -12, "neigen": 12}, "schnabel": 0.45, "koerper": {"rollen": 4}},
        {"t": 0.55, "kopf": {"nicken": -14, "neigen": -12}, "schnabel": 0.3, "koerper": {"rollen": -4}},
        {"t": 0.85, "kopf": {"nicken": -16, "neigen": 12}, "schnabel": 0.5, "koerper": {"rollen": 4}},
        {"t": 1.15, "kopf": {"nicken": -18, "neigen": -12}, "schnabel": 0.35, "koerper": {"rollen": -4}},
        {"t": 1.45, "kopf": {"nicken": -20, "neigen": 10}, "schnabel": 0.5, "koerper": {"rollen": 3}},
        {"t": 1.8, "kopf": {"nicken": -12}, "schnabel": 0.2, "koerper": {}},
        {"t": 2.2, "kopf": {}, "schnabel": 0.0},
    ],
    "hibbeln": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.22, "koerper": {"hoehe_mm": 5, "rollen": 6}, "kopf": {"drehen": 12, "neigen": 8}, "schnabel": 0.35},
        {"t": 0.35, "schnabel": 0.0},
        {"t": 0.47, "koerper": {"hoehe_mm": -3, "rollen": -6}, "kopf": {"drehen": -12, "neigen": -8}, "schnabel": 0.35},
        {"t": 0.6, "schnabel": 0.0},
        {"t": 0.72, "koerper": {"hoehe_mm": 5, "rollen": 6}, "kopf": {"drehen": 8}},
        {"t": 0.97, "koerper": {"hoehe_mm": -3, "rollen": -6}, "kopf": {"drehen": -10, "nicken": -8}, "schnabel": 0.35},
        {"t": 1.1, "schnabel": 0.0},
        {"t": 1.22, "koerper": {"hoehe_mm": 5, "rollen": 4}, "kopf": {"drehen": 6, "nicken": -10}, "schnabel": 0.35},
        {"t": 1.35, "schnabel": 0.0},
        {"t": 1.7, "kopf": {}, "koerper": {}},
    ],
    "mustern": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.6, "kopf": {"drehen": -45, "nicken": 4}},
        {"t": 1.2, "kopf": {"drehen": -45, "nicken": 6}},
        {"t": 1.8, "kopf": {"drehen": 0, "nicken": 2}},
        {"t": 2.3, "kopf": {"drehen": 42, "nicken": 4}},
        {"t": 2.68, "kopf": {"drehen": 38, "nicken": 14}, "schnabel": 0.2},
        {"t": 2.9, "kopf": {"drehen": 30, "nicken": 4}, "schnabel": 0.0},
        {"t": 3.4, "kopf": {}},
    ],
    "haltung": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.6, "kopf": {"nicken": -12, "nacken": -6}, "koerper": {"hoehe_mm": 8, "kippen": -6}},
        {"t": 1.08, "kopf": {"nicken": 10}, "schnabel": 0.3, "koerper": {"hoehe_mm": 6, "kippen": -4}},
        {"t": 1.3, "kopf": {"nicken": -2}, "schnabel": 0.0},
        {"t": 1.8, "kopf": {}, "koerper": {}},
    ],
    "nicken": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.3, "kopf": {"nicken": 18}, "schnabel": 0.3},
        {"t": 0.5, "kopf": {"nicken": -4}, "schnabel": 0.0},
        {"t": 0.9, "kopf": {}},
    ],
    "niesen": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.1, "kopf": {"nicken": -10}, "schnabel": 0.3},
        {"t": 0.4, "kopf": {"nicken": -20, "nacken": -6}, "schnabel": 0.4},
        {"t": 0.68, "kopf": {"nicken": -30, "nacken": -12}, "schnabel": 0.6, "koerper": {"hoehe_mm": 6, "kippen": -8}},
        {"t": 0.94, "kopf": {"nicken": -32, "nacken": -12}, "schnabel": 0.5, "koerper": {"hoehe_mm": 6, "kippen": -8}},
        {"t": 1.04, "kopf": {"nicken": 30, "nacken": 18}, "schnabel": 1.0, "koerper": {"hoehe_mm": -12, "kippen": 12}},
        {"t": 1.3, "kopf": {"nicken": 5}, "schnabel": 0.2, "koerper": {}},
        {"t": 1.55, "kopf": {"drehen": 15, "neigen": 10}, "schnabel": 0.0},
        {"t": 1.75, "kopf": {"drehen": -15, "neigen": -10}},
        {"t": 2.1, "kopf": {}},
    ],
    "schluckauf": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.3, "kopf": {"nicken": -12}, "koerper": {"hoehe_mm": 8, "kippen": -6}, "schnabel": 0.4},
        {"t": 0.48, "kopf": {}, "koerper": {}, "schnabel": 0.0},
        {"t": 1.2, "kopf": {"nicken": -12, "neigen": 6}, "koerper": {"hoehe_mm": 8, "kippen": -6}, "schnabel": 0.4},
        {"t": 1.38, "kopf": {"neigen": 6}, "koerper": {}, "schnabel": 0.0},
        {"t": 2.05, "kopf": {"nicken": -14, "neigen": -6}, "koerper": {"hoehe_mm": 9, "kippen": -6}, "schnabel": 0.4},
        {"t": 2.23, "kopf": {}, "koerper": {}, "schnabel": 0.0},
        {"t": 2.68, "kopf": {"neigen": 14, "nicken": 6}, "schnabel": 0.3},
        {"t": 2.9, "schnabel": 0.0},
        {"t": 3.2, "kopf": {}},
    ],
    "erschrecken": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.16, "kopf": {"drehen": 50, "nicken": -15}, "koerper": {"hoehe_mm": 8}, "schnabel": 0.8},
        {"t": 0.5, "kopf": {"drehen": 52, "nicken": -12}, "schnabel": 0.1},
        {"t": 0.9, "kopf": {"drehen": -50, "nicken": -10}, "schnabel": 0.0},
        {"t": 1.3, "kopf": {"drehen": 0}, "koerper": {}},
        {"t": 1.7, "kopf": {"nicken": 20, "neigen": 14}, "schnabel": 0.2, "koerper": {"hoehe_mm": -6}},
        {"t": 2.1, "schnabel": 0.0},
        {"t": 2.5, "kopf": {}, "koerper": {}},
    ],
}


def sits_ok(spec: list[dict[str, Any]]) -> bool:
    """Geht auch im Sitzen: nur Kopf und Schnabel, keine Körperhaltung, kein Fahren."""
    return not any("koerper" in kf or "fahren" in kf or "skill" in kf for kf in spec)
