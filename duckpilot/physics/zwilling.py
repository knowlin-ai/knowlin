"""Zwilling vorbereiten (seit 0.37, Lab): Messlauf und Abgleich mit der eigenen Ente.

„Simulator heute, Zwilling ab Lieferung“: Der Physik-Simulator rechnet mit Pollens Geometrie und Pollens
Servo-Modell. Jede echte Ente weicht davon etwas ab – Spiel im Getriebe, Verzögerung, schwächere oder kräftigere
Servos, Nullpunkt-Versatz. Damit der Simulator zum Zwilling *dieser* Ente wird, misst sie sich nach der Lieferung
einmal selbst (0.37 Teil 2):

1. **Messlauf** (`MESSLAUF`): Sie sitzt, die Beine sind frei. Jedes Beingelenk fährt nacheinander einen Sprung und
   ein Sinus-Stück mit kleiner Auslenkung; aufgezeichnet werden Soll- und Ist-Winkel (robotd liefert beides).
   Kleine Auslenkungen, langsam, im Sitzen – kein Sturz möglich. Der Not-Aus gilt wie immer.
2. **Abgleich** (`abgleich`): Für jedes Gelenk wird aus Soll/Ist bestimmt, wie spät (Verzögerung), wie weit
   (Verstärkung), wo (Versatz) und wie ungenau (Restfehler) das Gelenk folgt – und ob das zum Simulator passt.
3. Das Ergebnis ist ein **Zwillingsprofil** (`profil`), das der Physik-Simulator später statt der Standardwerte nutzt.

Dieses Modul rechnet nur – es bewegt nichts. Die Messung am echten Roboter und das Einspeisen ins Physik-Backend
kommen mit 0.37 Teil 2. Das Profil enthält nur Gelenkwerte, nichts über Wohnung oder Menschen.
"""

from __future__ import annotations

import math
import time
from typing import Any

BEIN_GELENKE = ("left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
                "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle")
TAKT_S = 0.02                       # 50 Hz wie die Steuerschleife
AUSLENKUNG_RAD = 0.15               # ≈ 9° – klein, im Sitzen ungefährlich
GRENZEN = {"verzoegerung_ms": 40.0, "verstaerkung": 0.15, "versatz_grad": 3.0, "rest_grad": 2.0}


def _abschnitt(art: str, dauer_s: float, **werte: float) -> dict[str, Any]:
    return {"art": art, "dauer_s": dauer_s, **werte}


# Je Gelenk: in Ruhe, Sprung hin und zurück, Sinus bei zwei Frequenzen
MESSLAUF: list[dict[str, Any]] = [
    {"gelenk": g, "abschnitte": [
        _abschnitt("ruhe", 0.5),
        _abschnitt("sprung", 1.0, hoehe=AUSLENKUNG_RAD),
        _abschnitt("sprung", 1.0, hoehe=0.0),
        _abschnitt("sinus", 2.0, amplitude=AUSLENKUNG_RAD, hz=0.5),
        _abschnitt("sinus", 2.0, amplitude=AUSLENKUNG_RAD * 0.6, hz=1.5),
        _abschnitt("ruhe", 0.5),
    ]} for g in BEIN_GELENKE
]


def messlauf_dauer_s() -> float:
    return round(sum(a["dauer_s"] for g in MESSLAUF for a in g["abschnitte"]), 1)


def sollkurve(gelenk_plan: dict[str, Any], takt_s: float = TAKT_S) -> list[float]:
    """Sollwinkel (rad, relativ zur Sitzhaltung) eines Gelenks über den ganzen Plan, im Takt."""
    out: list[float] = []
    stand = 0.0
    for a in gelenk_plan["abschnitte"]:
        n = max(1, round(a["dauer_s"] / takt_s))
        for i in range(n):
            if a["art"] == "sprung":
                stand = a["hoehe"]
            elif a["art"] == "sinus":
                stand = a["amplitude"] * math.sin(2 * math.pi * a["hz"] * i * takt_s)
            elif a["art"] == "ruhe":
                stand = stand if out else 0.0
            out.append(stand)
        if a["art"] == "sinus":
            stand = 0.0
    return out


def servo_modell(soll: list[float], verzoegerung_s: float = 0.02, verstaerkung: float = 1.0, versatz: float = 0.0,
                 zeitkonstante_s: float = 0.03, spiel: float = 0.0, takt_s: float = TAKT_S) -> list[float]:
    """Einfaches Servo-Modell (Totzeit, Verzögerung 1. Ordnung, Spiel, Versatz) – so folgt ein Gelenk dem Sollwert.
    Für Tests und als Standard-Referenz, solange es keinen echten Messlauf gibt."""
    tot = max(0, round(verzoegerung_s / takt_s))
    k = 1.0 - math.exp(-takt_s / max(1e-4, zeitkonstante_s))
    ist, x, ausgang = [], 0.0, 0.0
    for i in range(len(soll)):
        ziel = verstaerkung * (soll[i - tot] if i >= tot else 0.0)
        x += k * (ziel - x)
        if abs(x - ausgang) > spiel / 2:              # Spiel: Abtrieb bewegt sich erst nach halbem Spiel
            ausgang = x - math.copysign(spiel / 2, x - ausgang)
        ist.append(ausgang + versatz)
    return ist


def _mittel(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def kennwerte(soll: list[float], ist: list[float], takt_s: float = TAKT_S, max_verzoegerung_s: float = 0.2) -> dict[str, float]:
    """Verzögerung (beste Verschiebung), Verstärkung (Ausgleichsgerade), Versatz und Restfehler eines Gelenks."""
    n = min(len(soll), len(ist))
    if n < 10:
        raise ValueError("zu wenige Messwerte")
    soll, ist = soll[:n], ist[:n]
    best = (math.inf, 0, 1.0, 0.0)
    for s in range(0, min(n // 2, round(max_verzoegerung_s / takt_s)) + 1):
        a, b = soll[:n - s], ist[s:]
        ma, mb = _mittel(a), _mittel(b)
        va = sum((x - ma) ** 2 for x in a)
        g = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / va if va > 1e-12 else 1.0
        o = mb - g * ma
        rest = math.sqrt(_mittel([(y - (g * x + o)) ** 2 for x, y in zip(a, b)]))
        if rest < best[0] - 1e-9:
            best = (rest, s, g, o)
    rest, s, g, o = best
    return {"verzoegerung_ms": round(s * takt_s * 1000, 1), "verstaerkung": round(g, 3),
            "versatz_grad": round(math.degrees(o), 2), "rest_grad": round(math.degrees(rest), 2)}


def abgleich(messung: dict[str, dict[str, list[float]]], referenz: dict[str, dict[str, float]] | None = None,
             takt_s: float = TAKT_S) -> dict[str, Any]:
    """Messung {gelenk: {soll: [...], ist: [...]}} → Kennwerte je Gelenk und wie weit sie vom Simulator abweichen.

    `referenz`: Kennwerte des Simulators je Gelenk (Standard: aus `servo_modell` mit Pollens üblichen Werten)."""
    gelenke: dict[str, Any] = {}
    for g, d in messung.items():
        if g not in BEIN_GELENKE:
            continue
        kw = kennwerte(d["soll"], d["ist"], takt_s)
        ref = (referenz or {}).get(g) or standard_referenz()
        abw = {k: round(kw[k] - ref[k], 3) for k in GRENZEN}
        auffaellig = [k for k in GRENZEN if abs(abw[k]) > GRENZEN[k]]
        gelenke[g] = {**kw, "abweichung": abw, "passt": not auffaellig, "auffaellig": auffaellig}
    passen = sum(1 for v in gelenke.values() if v["passt"])
    return {"gelenke": gelenke, "passen": passen, "gesamt": len(gelenke),
            "text": (f"{passen} von {len(gelenke)} Gelenken folgen wie im Simulator." if gelenke
                     else "Keine Beingelenke in der Messung.")}


def standard_referenz() -> dict[str, float]:
    """Kennwerte des Standard-Servo-Modells über den Messlauf – das erwartet der Simulator von jedem Gelenk."""
    soll = sollkurve(MESSLAUF[0])
    return kennwerte(soll, servo_modell(soll))


def profil(ergebnis: dict[str, Any]) -> dict[str, Any]:
    """Zwillingsprofil zum Speichern: nur Gelenkwerte – keine Namen, Orte oder Menschen."""
    return {"art": "duckpilot-zwilling", "format": 1, "erstellt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "messlauf_s": messlauf_dauer_s(),
            "gelenke": {g: {k: v[k] for k in ("verzoegerung_ms", "verstaerkung", "versatz_grad", "rest_grad")}
                        for g, v in ergebnis.get("gelenke", {}).items()},
            "passen": ergebnis.get("passen"), "gesamt": ergebnis.get("gesamt")}
