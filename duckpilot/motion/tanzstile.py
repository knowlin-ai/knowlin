"""Tanz-Wortschatz je Bauart (seit 0.43, Fahrplan „Choreografie für jeden Körper“).

Bis 0.42 kannte der Tanz zwei Wege – die Ente und Reachy – und unterschied sie über den Namen des Körpers. Jetzt bringt
jede **Bauart** ihren Wortschatz mit; welcher gilt, folgt aus dem Profil (Familie und Fähigkeiten,
`koerper.tanzstil`), nie aus dem Namen:

- `ente` – laufende Enten (Microduck, Open Duck): Bein zu Bein, wiegen, drehen, Tanzgesten aus Tricks, Posen aus der
  Akrobatik (nur mit Trainingshalle).
- `kopf_antennen` – Kopf auf einer Plattform, Antennen, Körperdrehung (`reachy_tanz.py`).
- `kopf` – nur ein Kopf mit zwei Gelenken (drehen, nicken); hat er ein Gesicht, zeigt es die Gefühle, hat er LEDs,
  tanzen die im Takt mit.
- `arm` – ein Greifarm: schwingen, wiegen, Greifer im Takt (Haltungen in `arm.TANZ`, oberhalb der Werkbank).
- `vierbeiner` – ein Hund: Tanzschritte sind seine Tricks am Platz (nicken, Pfote, Boxen, Jubeln …).

Ein Stil sagt, **was** es gibt (Bewegungen je Energiestufe, Gefühle, Muster je Teil eines Stücks); **wie** es sich
bewegt, entscheidet der Körper: Kopfbewegungen fährt der Tanz selbst (`KOPF`), Arm und Hund spielen ihren Schritt im
Backend (`tanz_schritt`). Was ein Körper nicht kann, kommt gar nicht erst vor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .reachy_tanz import AUS_ENTE, REACHY_GEFUEHLE, REACHY_STUFEN, REACHY_TANZ_TEXT
from .tanz import TANZGESTEN

Muster = dict[str, tuple[tuple[tuple[str, int], ...], ...]]

# Muster je Teil eines Stücks. „gesteN“ = eine Bewegung der Energiestufe N (fest je Teil und Stelle, damit jeder
# Refrain gleich getanzt wird), „@“ = Höhepunkt (Pose oder Gefühl), sonst ein Schritt oder eine benannte Bewegung.
MUSTER_ENTE: Muster = {
    # seit 0.36.2 mehr von Bein zu Bein (schritt, wiegen) und mehr Drehungen (Hinweis aus dem Test)
    "Intro": ((("wiegen", 2), ("geste0", 2)), (("schritt", 2), ("geste0", 2))),
    "Strophe": ((("schritt", 2), ("geste1", 2)), (("wiegen", 1), ("schritt", 1), ("drehen", 2))),
    # seit 0.38.23 beginnt jeder Refrain mit dem Höhepunkt – der Einsatz ist der Moment, den man sieht
    "Refrain": ((("@", 1), ("schritt", 1), ("geste2", 1), ("drehen", 1)), (("drehen", 2), ("geste2", 1), ("schritt", 1))),
    "Bridge": ((("wiegen", 2), ("geste1", 2)), (("drehen", 2), ("wiegen", 2))),
    "Drop": ((("@", 1), ("drehen", 3)), (("schritt", 2), ("geste2", 2))),
    "Breakdown": ((("pause", 1), ("wiegen", 3)), (("geste0", 2), ("wiegen", 2))),
    "Outro": ((("schritt", 2), ("geste0", 2)), (("drehen", 2), ("wiegen", 2))),
}
MUSTER_KOPF_ANTENNEN: Muster = {
    "Intro": ((("wiegen", 2), ("geste0", 2)), (("kopfnicken", 2), ("antennen_takt", 2))),
    "Strophe": ((("kopfnicken", 2), ("geste1", 2)), (("wiegen", 1), ("antennen_takt", 1), ("geste1", 2))),
    "Refrain": ((("@", 1), ("koerper_drehen", 2), ("geste2", 1)), (("party", 2), ("koerper_drehen", 2))),
    "Bridge": ((("umschauen", 2), ("geste1", 2)), (("wiegen", 2), ("kopfnicken", 2))),
    "Drop": ((("@", 1), ("koerper_drehen", 3)), (("antennen_wirbel", 2), ("geste2", 2))),
    "Breakdown": ((("pause", 1), ("wiegen", 3)), (("umschauen", 2), ("wippen", 2))),
    "Outro": ((("wiegen", 2), ("geste0", 2)), (("kopfnicken", 2), ("wiegen", 2))),
}
# Für alle übrigen Bauarten: nur Bewegungen der Stufen, Höhepunkte und Pausen
MUSTER_ALLGEMEIN: Muster = {
    "Intro": ((("geste0", 2), ("geste0", 2)), (("geste0", 2), ("geste1", 2))),
    "Strophe": ((("geste1", 2), ("geste1", 2)), (("geste0", 2), ("geste1", 2))),
    "Refrain": ((("@", 1), ("geste2", 2), ("geste1", 1)), (("geste2", 2), ("geste2", 2))),
    "Bridge": ((("geste1", 2), ("geste0", 2)), (("geste1", 2), ("geste1", 2))),
    "Drop": ((("@", 1), ("geste2", 3)), (("geste2", 2), ("geste2", 2))),
    "Breakdown": ((("pause", 1), ("geste0", 3)), (("geste0", 2), ("geste0", 2))),
    "Outro": ((("geste1", 2), ("geste0", 2)), (("geste0", 2), ("geste0", 2))),
}

# Kopfbewegungen (Bauart „kopf“): Name → [(Schlag, drehen °, nicken °)], nicken + = nach oben. Jede endet, wo sie
# begann; die Werte bleiben weit in den Grenzen kleiner Schreibtisch-Roboter (drehen ±170°, nicken 80° hoch, 10° runter).
KOPF: dict[str, list[tuple[float, float, float]]] = {
    "nicken": [(0.0, 0.0, 4.0), (0.5, 0.0, -4.0), (1.0, 0.0, 4.0)],
    "wiegen": [(0.0, -12.0, 3.0), (1.0, 12.0, 3.0), (2.0, -12.0, 3.0)],
    "wippen": [(0.0, 0.0, 0.0), (0.5, 0.0, 9.0), (1.0, 0.0, 0.0)],
    "umschauen": [(0.0, 0.0, 6.0), (1.0, 30.0, 6.0), (2.0, 0.0, 6.0), (3.0, -30.0, 6.0), (4.0, 0.0, 6.0)],
    "kreisen": [(0.0, 0.0, 14.0), (1.0, 14.0, 6.0), (2.0, 0.0, -4.0), (3.0, -14.0, 6.0), (4.0, 0.0, 14.0)],
    "hochrunter": [(0.0, 0.0, -4.0), (1.0, 0.0, 22.0), (2.0, 0.0, -4.0)],
    "schuetteln": [(0.0, -20.0, 10.0), (0.5, 20.0, 10.0), (1.0, -20.0, 10.0)],
    "party": [(0.0, -35.0, 18.0), (1.0, 35.0, 4.0), (2.0, -35.0, 18.0)],
}


@dataclass(frozen=True)
class TanzStil:
    """Was eine Bauart beim Tanzen kann. `stufen`: Bewegungen je Energiestufe (0 ruhig … 2 laut), `texte`: kurze
    Beschreibung je Bewegung (für Editor und Sprachmodell), `gefuehle`: Akzente an Höhepunkten, `arten`: Schrittarten
    im Editor, `posen`: gespeicherte Haltungen möglich (nur mit Trainingshalle), `wie`: ein Satz fürs Sprachmodell."""

    key: str
    stufen: dict[int, tuple[str, ...]]
    texte: dict[str, str]
    gefuehle: tuple[str, ...]
    muster: Muster
    arten: tuple[str, ...] = ("trick", "gefuehl", "pause")
    posen: bool = False
    wie: str = ""
    schluss: str = "stolz"
    aus_ente: dict[str, str] = field(default_factory=dict)   # ältere Entenschritte → eigene Bewegung

    def bewegungen(self) -> list[str]:
        seen: list[str] = []
        for n in (0, 1, 2):
            seen += [b for b in self.stufen.get(n, ()) if b not in seen]
        return seen

    def aufloesen(self, name: str, stufe: int = 1) -> str:
        """Name eines Schritts → eine eigene Bewegung (Entenschritte und Unbekanntes werden übersetzt)."""
        if name in self.texte:
            return name
        if name in self.aus_ente:
            return self.aus_ente[name]
        liste = self.stufen[max(0, min(2, stufe))]
        return liste[sum(map(ord, name)) % len(liste)]


_AUS_ENTE_STUFEN = {"nicken": 0, "wippen": 0, "wackeln": 1, "wiegen": 1, "schritt": 2, "drehen": 2}

STILE: dict[str, TanzStil] = {
    "ente": TanzStil(
        "ente", TANZGESTEN, {}, ("begeistert", "freude", "aufgeregt", "ja", "staunen", "stolz"), MUSTER_ENTE,
        arten=("schritt", "wiegen", "drehen", "nicken", "wippen", "wackeln", "trick", "pose", "gefuehl", "pause"),
        posen=True, wie="tanzt mit den Beinen: Bein zu Bein, wiegen, drehen, dazu Tanzgesten aus Tricks"),
    "kopf_antennen": TanzStil(
        "kopf_antennen", REACHY_STUFEN, REACHY_TANZ_TEXT, REACHY_GEFUEHLE, MUSTER_KOPF_ANTENNEN,
        wie="hat keine Beine und keinen Schnabel – tanzt mit Kopf, Antennen und Körperdrehung", aus_ente=dict(AUS_ENTE)),
    "kopf": TanzStil(
        "kopf", {0: ("nicken", "wiegen", "wippen"), 1: ("umschauen", "kreisen", "hochrunter"),
                 2: ("schuetteln", "party", "kreisen")},
        {"nicken": "Nicken im Takt", "wiegen": "Kopf wiegt zur Seite", "wippen": "Kopf wippt hoch",
         "umschauen": "Umschauen im Takt", "kreisen": "Kopf kreist", "hochrunter": "Weit hoch und runter",
         "schuetteln": "Kopf schütteln", "party": "Große Party-Bewegung"},
        ("freude", "begeistert", "ueberrascht", "staunen", "stolz"), MUSTER_ALLGEMEIN,
        wie="hat nur einen Kopf mit zwei Gelenken – tanzt mit Drehen und Nicken, Gefühle zeigt das Gesicht",
        aus_ente={"nicken": "nicken", "wippen": "wippen", "wackeln": "wiegen", "wiegen": "wiegen", "schritt": "umschauen",
                  "drehen": "party"}),
    "arm": TanzStil(
        "arm", {0: ("wiegen", "nicken"), 1: ("greifer_takt", "kreisen", "wiegen"), 2: ("schwingen", "winken", "jubeln")},
        {"wiegen": "Arm wiegt hin und her", "nicken": "Handgelenk nickt im Takt", "greifer_takt": "Greifer klatscht im Takt",
         "kreisen": "Handgelenk dreht hin und her", "schwingen": "Arm schwingt hoch und runter",
         "winken": "Winken im Takt", "jubeln": "Großer Jubel oben"},
        ("freuen", "staunen", "neugierig", "aufmerksam"), MUSTER_ALLGEMEIN, schluss="freuen",
        wie="ist ein Greifarm – tanzt oben über der Werkbank mit Schulter, Handgelenk und Greifer"),
    "vierbeiner": TanzStil(
        "vierbeiner", {0: ("nicken", "umschauen", "schnueffeln"), 1: ("auf_der_stelle", "verbeugen", "boxen"),
                       2: ("jubeln", "high_five", "springen")},
        {"nicken": "Nicken", "umschauen": "Umschauen", "schnueffeln": "Schnüffeln", "auf_der_stelle": "Traben auf der Stelle",
         "verbeugen": "Verbeugen", "boxen": "Boxen", "jubeln": "Jubeln", "high_five": "High five", "springen": "Springen"},
        ("pfote", "maennchen", "jubeln", "verbeugen"), MUSTER_ALLGEMEIN, schluss="maennchen",
        wie="ist ein Hund – tanzt mit seinen Tricks am Platz (nicken, boxen, jubeln, springen)"),
}
for _s in (STILE["arm"], STILE["vierbeiner"]):
    _s.aus_ente.update({k: _s.stufen[n][0] for k, n in _AUS_ENTE_STUFEN.items()})


def stil(key: str) -> TanzStil:
    """Unbekannte Stile tanzen wie die Ente – das ist der älteste und breiteste Wortschatz."""
    return STILE.get(key) or STILE["ente"]


def kopf_lage(name: str, beat: float, skala: float = 1.0) -> tuple[float, float]:
    """Kopf (drehen °, nicken °) einer Kopfbewegung beim Schlag `beat` seit ihrem Beginn, weich dazwischen."""
    kfs = KOPF.get(name) or KOPF["nicken"]
    t = beat % kfs[-1][0]
    for (ta, ya, pa), (tb, yb, pb) in zip(kfs, kfs[1:]):
        if ta <= t <= tb:
            u = (t - ta) / max(1e-6, tb - ta)
            u = u * u * (3 - 2 * u)
            return (ya + (yb - ya) * u) * skala, (pa + (pb - pa) * u) * skala
    return kfs[-1][1] * skala, kfs[-1][2] * skala
