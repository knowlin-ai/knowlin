"""Gefühle für Reachy Mini (seit 0.38.10): eigene, vorsichtige Gesten statt der Enten-Choreografien.

Die Gesten der Ente (`behaviors.EMOTIONS`) nicken und neigen kräftig und gehen mit dem ganzen Körper in die Knie –
auf Reachys Stewart-Plattform tauchte der Kopf dabei in den Körper (Beobachtung aus dem Test bei „freu dich“). Reachy zeigt
Gefühle vor allem mit den **Antennen** und kleinen Kopfbewegungen, wie in Pollens eigenen Aufnahmen: Freude = Kopf
leicht hoch, Antennen nach außen und zurück; Trauer = Antennen hängen, Kopf etwas gesenkt. Nie stark kippen, nie
tiefer (z < 0) und gleichzeitig kippen – was trotzdem nicht passt, nimmt `reachy_kinematik.begrenzen` zurück.

Format wie die Choreografien (Grad, Millimeter), dazu `antennen: [rechts, links]` in Grad, 0 = senkrecht,
+ = nach außen (wie das Werkzeug `antennen`). Für Reachy heißt `kopf.nicken` −  = Kopf hoch, `kopf.neigen` = zur
Seite, `kopf.drehen` = zur Seite schauen, `koerper.hoehe_mm` = Kopf hoch/runter. Keine Entenlaute (`ton`).

Hat Pollens Bibliothek (`pollen_bewegung`) eine passende Aufnahme, nimmt Reachy manchmal die (`POLLEN`, Stämme der
Namen wie „cheerful1“).
"""

from __future__ import annotations

from typing import Any

GESTEN: dict[str, list[dict[str, Any]]] = {
    "freude": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.3, "kopf": {"nicken": -10}, "koerper": {"hoehe_mm": 6}, "antennen": [70, 70]},
        {"t": 0.6, "kopf": {"nicken": -8}, "koerper": {"hoehe_mm": 6}, "antennen": [20, 20]},
        {"t": 0.9, "kopf": {"nicken": -12}, "koerper": {"hoehe_mm": 8}, "antennen": [70, 70]},
        {"t": 1.2, "kopf": {"nicken": -8}, "koerper": {"hoehe_mm": 6}, "antennen": [20, 20]},
        {"t": 1.8, "kopf": {}, "koerper": {}, "antennen": [10, 10]},
    ],
    "begeistert": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.2, "kopf": {"nicken": -12}, "koerper": {"hoehe_mm": 10}, "antennen": [85, 85]},
        {"t": 0.45, "kopf": {"nicken": -10, "neigen": 4}, "koerper": {"hoehe_mm": 8}, "antennen": [25, 60]},
        {"t": 0.7, "kopf": {"nicken": -10, "neigen": -4}, "koerper": {"hoehe_mm": 8}, "antennen": [60, 25]},
        {"t": 0.95, "kopf": {"nicken": -12}, "koerper": {"hoehe_mm": 10}, "antennen": [85, 85]},
        {"t": 1.3, "kopf": {"nicken": -6}, "koerper": {"hoehe_mm": 4}, "antennen": [20, 20]},
        {"t": 1.8, "kopf": {}, "koerper": {}, "antennen": [10, 10]},
    ],
    "traurig": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 1.2, "kopf": {"nicken": 12, "drehen": -6}, "antennen": [130, 130]},
        {"t": 3.0, "kopf": {"nicken": 14, "drehen": -8}, "antennen": [140, 140]},
        {"t": 4.0, "kopf": {}, "antennen": [10, 10]},
    ],
    "neugierig": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.5, "kopf": {"neigen": 8, "nicken": -5, "drehen": 12}, "koerper": {"hoehe_mm": 5}, "antennen": [0, 50]},
        {"t": 1.3, "kopf": {"neigen": 8, "nicken": -3, "drehen": 15}, "koerper": {"hoehe_mm": 5}, "antennen": [0, 50]},
        {"t": 1.8, "kopf": {"neigen": -6, "drehen": -10}, "koerper": {"hoehe_mm": 4}, "antennen": [50, 0]},
        {"t": 2.6, "kopf": {}, "koerper": {}, "antennen": [10, 10]},
    ],
    "ueberrascht": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.15, "kopf": {"nicken": -12}, "koerper": {"hoehe_mm": 12}, "antennen": [0, 0]},
        {"t": 0.6, "kopf": {"nicken": -10}, "koerper": {"hoehe_mm": 10}, "antennen": [60, 60]},
        {"t": 1.0, "kopf": {"nicken": -8}, "koerper": {"hoehe_mm": 8}, "antennen": [0, 0]},
        {"t": 1.8, "kopf": {}, "koerper": {}, "antennen": [10, 10]},
    ],
    "staunen": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.25, "kopf": {"nicken": -14}, "koerper": {"hoehe_mm": 12}, "antennen": [0, 0]},
        {"t": 1.2, "kopf": {"nicken": -12, "neigen": 5}, "koerper": {"hoehe_mm": 10}, "antennen": [40, 40]},
        {"t": 1.8, "kopf": {"nicken": -12, "neigen": -5}, "koerper": {"hoehe_mm": 10}, "antennen": [5, 5]},
        {"t": 2.5, "kopf": {}, "koerper": {}, "antennen": [10, 10]},
    ],
    "muede": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 1.0, "kopf": {"nicken": 8}, "antennen": [70, 70]},
        {"t": 1.6, "kopf": {"nicken": 4}, "antennen": [50, 50]},
        {"t": 2.6, "kopf": {"nicken": 12, "neigen": 4}, "antennen": [110, 110]},
        {"t": 4.0, "kopf": {"nicken": 12, "neigen": 4}, "antennen": [110, 110]},
        {"t": 5.0, "kopf": {}, "antennen": [10, 10]},
    ],
    "wuetend": [
        {"t": 0.0, "kopf": {"nicken": 6}, "antennen": [90, 90]},
        {"t": 0.3, "kopf": {"nicken": 8, "drehen": 10}, "antennen": [95, 95]},
        {"t": 0.5, "kopf": {"nicken": 8, "drehen": -10}, "antennen": [85, 85]},
        {"t": 0.7, "kopf": {"nicken": 8, "drehen": 10}, "antennen": [95, 95]},
        {"t": 0.9, "kopf": {"nicken": 8, "drehen": -10}, "antennen": [85, 85]},
        {"t": 1.6, "kopf": {}, "antennen": [10, 10]},
    ],
    "frustriert": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.3, "kopf": {"nicken": 10}, "antennen": [100, 100]},
        {"t": 0.8, "kopf": {"nicken": 10, "drehen": 12}, "antennen": [100, 100]},
        {"t": 1.1, "kopf": {"nicken": 10, "drehen": -12}, "antennen": [110, 110]},
        {"t": 1.4, "kopf": {"nicken": 8, "drehen": 6}, "antennen": [100, 100]},
        {"t": 2.2, "kopf": {"nicken": -4}, "koerper": {"hoehe_mm": 4}, "antennen": [30, 30]},
        {"t": 2.7, "kopf": {}, "koerper": {}, "antennen": [10, 10]},
    ],
    "erleichtert": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.5, "kopf": {"nicken": -8}, "koerper": {"hoehe_mm": 8}, "antennen": [60, 60]},
        {"t": 1.2, "kopf": {"nicken": 5, "neigen": 4}, "koerper": {"hoehe_mm": 0}, "antennen": [30, 30]},
        {"t": 1.8, "kopf": {"nicken": -5, "neigen": 4}, "koerper": {"hoehe_mm": 2}, "antennen": [15, 15]},
        {"t": 2.3, "kopf": {}, "koerper": {}, "antennen": [10, 10]},
    ],
    "stolz": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.4, "kopf": {"nicken": -12, "drehen": 10}, "koerper": {"hoehe_mm": 10}, "antennen": [5, 5]},
        {"t": 1.3, "kopf": {"nicken": -12, "drehen": -10}, "koerper": {"hoehe_mm": 10}, "antennen": [5, 5]},
        {"t": 1.7, "kopf": {"nicken": -8}, "koerper": {"hoehe_mm": 8}, "antennen": [40, 40]},
        {"t": 2.4, "kopf": {}, "koerper": {}, "antennen": [10, 10]},
    ],
    "einfuehlsam": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.9, "kopf": {"nicken": 4, "neigen": 7}, "antennen": [40, 40]},
        {"t": 2.2, "kopf": {"nicken": 5, "neigen": 8}, "antennen": [45, 45]},
        {"t": 3.0, "kopf": {"nicken": 2, "neigen": 5}, "antennen": [25, 25]},
        {"t": 3.8, "kopf": {}, "antennen": [10, 10]},
    ],
    "verlegen": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.5, "kopf": {"nicken": 8, "neigen": 5, "drehen": -15}, "antennen": [100, 40]},
        {"t": 1.4, "kopf": {"nicken": 6, "neigen": 5, "drehen": 8}, "antennen": [40, 100]},
        {"t": 1.9, "kopf": {"nicken": -3, "neigen": 3}, "antennen": [20, 20]},
        {"t": 2.3, "kopf": {}, "antennen": [10, 10]},
    ],
    "ja": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.25, "kopf": {"nicken": 10}, "antennen": [30, 30]}, {"t": 0.5, "kopf": {"nicken": -6}},
        {"t": 0.75, "kopf": {"nicken": 10}}, {"t": 1.0, "kopf": {"nicken": -4}, "antennen": [10, 10]},
        {"t": 1.3, "kopf": {}},
    ],
    "nein": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.25, "kopf": {"drehen": 20}}, {"t": 0.55, "kopf": {"drehen": -20}},
        {"t": 0.85, "kopf": {"drehen": 20}}, {"t": 1.15, "kopf": {"drehen": -15}},
        {"t": 1.5, "kopf": {}},
    ],
    "begruessen": [
        {"t": 0.0, "kopf": {"nicken": -6}, "koerper": {"hoehe_mm": 6}, "antennen": [10, 10]},
        {"t": 0.4, "kopf": {"nicken": -8, "neigen": 4}, "koerper": {"hoehe_mm": 8}, "antennen": [70, 15]},
        {"t": 0.8, "kopf": {"nicken": -8, "neigen": -4}, "koerper": {"hoehe_mm": 8}, "antennen": [15, 70]},
        {"t": 1.2, "kopf": {"nicken": -6}, "koerper": {"hoehe_mm": 6}, "antennen": [70, 15]},
        {"t": 1.6, "kopf": {"nicken": 6}, "antennen": [10, 10]},
        {"t": 2.2, "kopf": {}, "koerper": {}},
    ],
    "trotzig": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.35, "kopf": {"drehen": 30, "nicken": -8}, "koerper": {"hoehe_mm": 6}, "antennen": [80, 80]},
        {"t": 1.4, "kopf": {"drehen": 32, "nicken": -8}, "koerper": {"hoehe_mm": 6}, "antennen": [80, 80]},
        {"t": 1.9, "kopf": {"drehen": 10, "nicken": -4}, "koerper": {"hoehe_mm": 2}, "antennen": [30, 30]},
        {"t": 2.6, "kopf": {}, "koerper": {}, "antennen": [10, 10]},
    ],
    "schuetteln": [
        {"t": 0.0, "kopf": {}, "antennen": [10, 10]},
        {"t": 0.12, "kopf": {"drehen": 12}, "antennen": [60, 20]},
        {"t": 0.26, "kopf": {"drehen": -12}, "antennen": [20, 60]},
        {"t": 0.40, "kopf": {"drehen": 10}, "antennen": [60, 20]},
        {"t": 0.54, "kopf": {"drehen": -8}, "antennen": [20, 60]},
        {"t": 0.9, "kopf": {}, "antennen": [10, 10]},
    ],
}
GESTEN["stolpern"] = GESTEN["ueberrascht"]          # Reachy stolpert nicht – er erschrickt kurz

# Gefühl → Stämme passender Aufnahmen in Pollens Reachy-Bibliothek (pollen-robotics/reachy-mini-emotions-library)
POLLEN: dict[str, tuple[str, ...]] = {
    "freude": ("cheerful", "laughing", "success"), "begeistert": ("enthusiastic", "electric"),
    "traurig": ("sad", "downcast"), "neugierig": ("curious", "inquiring"), "ueberrascht": ("surprised", "amazed"),
    "staunen": ("amazed",), "muede": ("tired", "exhausted"), "wuetend": ("furious", "irritated"),
    "frustriert": ("frustrated", "impatient"), "erleichtert": ("relief",), "stolz": ("proud",),
    "einfuehlsam": ("understanding", "loving"), "verlegen": ("shy",), "ja": ("yes",), "nein": ("no",),
    "begruessen": ("welcoming",),
}


def ist_reachy(backend: Any) -> bool:
    return getattr(backend, "koerper_art", "") == "reachy_mini"


# Leerlauf (Beobachtung aus dem Test 5.11.: „nur im ‚leerlauf‘ kommen die entenartigen Laute“): statt der Enten-Gesten des
# Charakters (gähnen, Gefieder putzen, niesen … mit Quaken) ruhige eigene Regungen – Name → Meldung im Ticker
LEERLAUF: dict[str, str] = {
    "neugierig": "schaut neugierig umher",
    "staunen": "staunt still vor sich hin",
    "ja": "nickt nachdenklich",
    "erleichtert": "atmet sichtbar durch",
    "muede": "lässt die Antennen kurz hängen",
}


def geste(name: str) -> list[dict[str, Any]] | None:
    """Reachys eigene Geste zu einem Gefühl – None, wenn es keine gibt (dann bleibt die allgemeine, begrenzte)."""
    return GESTEN.get(name)
