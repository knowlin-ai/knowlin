"""Gelenk-Check: Soll, Ist, Nachlauf und Last je Gelenk – und das Pflegeheft der Motoren.

Pollen kalibriert die Gelenke nicht je Roboter (nur die Knie haben einen festen Homing-Versatz). Was man am
Roboter sehen kann, liefert robotd schon im Zustand: `joints` (gemessen), `targets` (Sollwert der Policy) und
`currents_ma` (Motorstrom). Daraus wird hier je Gelenk:

* **Nachlauf** = Soll − Ist. Bleibt ein Gelenk dauerhaft hinter dem Sollwert, hakt etwas (Reibung, Spiel,
  ein müder Motor) – genau das, was beim Übertragen vom Training auf den Roboter stört.
* **Last** = Strom (Roboter) bzw. Moment (Physik) im Verhältnis zum Höchstwert des XL330.

Im Physik-Simulator kommen dieselben Werte aus MuJoCo (Sollwert des Reglers, actuator_force). Die einfache
Simulation hat keine Motoren – dort gibt es nur die Winkel.

Ampel je Gelenk (Symbol + Wort im Browser, nie nur Farbe): gut, auffällig, prüfen.
"""
from __future__ import annotations

import math
from typing import Any

from .api import JOINT_NAMES

LABELS = {
    "left_hip_yaw": "Linke Hüfte drehen", "left_hip_roll": "Linke Hüfte seitlich",
    "left_hip_pitch": "Linke Hüfte vor/zurück", "left_knee": "Linkes Knie", "left_ankle": "Linker Knöchel",
    "neck_pitch": "Nacken", "head_pitch": "Kopf nicken", "head_yaw": "Kopf drehen", "head_roll": "Kopf neigen",
    "mouth": "Schnabel",
    "right_hip_yaw": "Rechte Hüfte drehen", "right_hip_roll": "Rechte Hüfte seitlich",
    "right_hip_pitch": "Rechte Hüfte vor/zurück", "right_knee": "Rechtes Knie", "right_ankle": "Rechter Knöchel",
}

# Grenzen der Ampel – Nachlauf in rad (0,1 rad ≈ 6°), Last als Anteil vom Höchstwert
ERR_WARN, ERR_BAD = 0.10, 0.25
LOAD_WARN, LOAD_BAD = 0.70, 0.90
XL330_STALL_MA = 1800.0       # Näherung für den Blockierstrom des XL330 am 2S-Akku (Datenblatt: 1,47 A bei 5 V)


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


def grade(fehler: float | None, last: float | None) -> str:
    worst = "gut"
    if fehler is not None:
        if abs(fehler) >= ERR_BAD:
            return "pruefen"
        if abs(fehler) >= ERR_WARN:
            worst = "auffaellig"
    if last is not None:
        if last >= LOAD_BAD:
            return "pruefen"
        if last >= LOAD_WARN:
            worst = "auffaellig"
    return worst


def build(ist: list[Any], soll: list[Any] | None = None, last: list[Any] | None = None,
          strom_ma: list[Any] | None = None, *, quelle: str, aktiv: bool = True,
          hinweis: str | None = None) -> dict[str, Any]:
    """Bericht aus Listen in der Reihenfolge von JOINT_NAMES (fehlende Werte dürfen None sein)."""
    rows = []
    for i, name in enumerate(JOINT_NAMES):
        a = _num(ist[i]) if i < len(ist) else None
        s = _num(soll[i]) if soll and i < len(soll) else None
        ld = _num(last[i]) if last and i < len(last) else None
        ma = _num(strom_ma[i]) if strom_ma and i < len(strom_ma) else None
        if ld is None and ma is not None:
            ld = min(1.5, abs(ma) / XL330_STALL_MA)
        err = (s - a) if (a is not None and s is not None and name != "mouth") else None
        rows.append({
            "name": name, "label": LABELS.get(name, name),
            "ist": a, "soll": s, "fehler": err,
            "last": None if ld is None else round(ld, 3), "strom_ma": ma,
            # ohne Strom (stromlos, gestürzt) ist Nachlauf normal – dann keine Ampel daraus
            "ampel": grade(err if aktiv else None, ld if aktiv else None),
        })
    errs = [abs(r["fehler"]) for r in rows if r["fehler"] is not None]
    loads = [r["last"] for r in rows if r["last"] is not None]
    worst = max(rows, key=lambda r: ("gut", "auffaellig", "pruefen").index(r["ampel"]))
    return {
        "quelle": quelle,
        "aktiv": aktiv,
        "hinweis": hinweis,
        "gelenke": rows,
        "summe": {
            "nachlauf_mittel": round(sum(errs) / len(errs), 4) if errs else None,
            "nachlauf_max": round(max(errs), 4) if errs else None,
            "last_max": round(max(loads), 3) if loads else None,
            "ampel": worst["ampel"],
            "auffaellig": [r["label"] for r in rows if r["ampel"] != "gut"],
        },
    }


def vetbook_summary(raw: Any) -> dict[str, Any] | None:
    """Pollens Pflegeheft (robot.vetbook) knapp: je Motor Laufzeit, Weg, heißeste Temperatur, Auslöser."""
    if not isinstance(raw, dict):
        return None
    motors = []
    for m in raw.get("motors") if isinstance(raw.get("motors"), list) else []:
        if not isinstance(m, dict):
            continue
        wear = m.get("wear") if isinstance(m.get("wear"), dict) else {}
        trips = wear.get("trips") if isinstance(wear.get("trips"), dict) else {}
        trip_sum = sum(int(v) for v in trips.values() if isinstance(v, (int, float)))
        motors.append({
            "id": m.get("id"),
            "gelenk": m.get("joint"),
            "label": LABELS.get(str(m.get("joint")), str(m.get("joint") or m.get("id"))),
            "stunden_unter_strom": round((_num(wear.get("torqued_s")) or 0.0) / 3600, 1),
            "weg_umdrehungen": round((_num(wear.get("travel_rad")) or 0.0) / (2 * math.pi), 1),
            "heissester_c": _num(wear.get("hottest_c")),
            "heiss_min": round((_num(wear.get("hot_s")) or 0.0) / 60, 1),
            "ausloeser": {k: int(v) for k, v in trips.items() if isinstance(v, (int, float))},
            "ausloeser_summe": trip_sum,
            "eingebaut": m.get("installed"),
            "ausgemustert": bool(m.get("retired")),
        })
    events = []
    events_raw = raw.get("events") if isinstance(raw.get("events"), list) else []
    for e in events_raw[-12:]:
        if isinstance(e, dict):
            events.append({"wann": e.get("at"), "art": str(e.get("kind", "")), "text": str(e.get("text", ""))})
    worn = sorted((m for m in motors if not m["ausgemustert"]),
                  key=lambda m: (m["ausloeser_summe"], m["stunden_unter_strom"]), reverse=True)
    return {"motoren": motors, "ereignisse": events,
            "zuerst_ansehen": [m["label"] for m in worn[:3] if m["ausloeser_summe"] > 0]}


# Abgleich Training ↔ Roboter: was Pollens Training annimmt und was robotd am Roboter einstellt.
# Quelle: microduck-Repos (robotd-params, mjlab-Aufgabe, BAM-Aktuator) – Stand der Recherche Okt. 2026.
ALIGNMENT = [
    {"thema": "Regler-Steifigkeit (kP)", "training": "200 (BAM xl330, m6)", "roboter": "policy.gain = 200",
     "stand": "gleich", "tipp": "Nicht ändern – die Policy ist genau auf diesen Wert trainiert."},
    {"thema": "Aktionsskala", "training": "1,0", "roboter": "action_scale = 0,9",
     "stand": "abweichend", "tipp": "Der Roboter dämpft die Bewegungen um 10 %. Lernt eine eigene Gangart zu wackelig "
                                     "oder zu zaghaft, mit robotctl configure testweise angleichen."},
    {"thema": "Glättung Kopf/Beine", "training": "keine (ungefiltert)", "roboter": "lowpass 0,5 / 0,7",
     "stand": "abweichend", "tipp": "Am Roboter laufen die Sollwerte durch einen Tiefpass – das wirkt wie Verzögerung. "
                                    "Training mit Verzögerung (BAM-Lag 3–6 Takte) gleicht das aus."},
    {"thema": "Akkuspannung", "training": "6,5–8,2 V zufällig", "roboter": "voltage_adapt an",
     "stand": "abgedeckt", "tipp": "Passt – das Training kennt leere und volle Akkus."},
    {"thema": "Gelenk-Nullpunkte", "training": "± 0,015 rad zufällig (ENCODER_BIAS)", "roboter": "keine Kalibrierung je Roboter",
     "stand": "abgedeckt", "tipp": "Kleine Fehler bis ≈ 1° fängt das Training ab. Größere Nachläufe im Gelenk-Check "
                                   "deuten auf Mechanik (Schraube, Horn) – nicht auf Software."},
    {"thema": "Spiel in den Getrieben", "training": "nur in der Variante „Backlash“", "roboter": "ältere Servos haben Spiel",
     "stand": "wählbar", "tipp": "Für den echten Roboter die Trainingsvariante mit Spiel (Backlash) nehmen."},
]
