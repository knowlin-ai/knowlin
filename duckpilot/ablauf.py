"""Ablauf-Baukasten und Duck Cards (seit 0.49): eine Reihe von Schritten, die jeder Körper abspielt, soweit er kann.

Maintainer: „ja, sonst verlinken wir die Karten einfach evtl. bzw. zusätzlich“ – Knowlin liest die freien Duck Cards von
Microduck Studio (Format `duck-cards/0`, CC BY 4.0, ein unabhängiges Projekt, nicht von Pollen): Jede Karte trägt ein
AprilTag (Familie tag36h11), dessen Nummer die Karte ist. Der Browser erkennt die Tags (vendor/aruco36h11.js) und schickt
nur Nummer und Lage – kein Bild. Hier wird daraus ein Ablauf, wie es das Format beschreibt:

- Gelesen wird von links nach rechts; Start und Ende begrenzen (optional).
- Gehen, Tricks und Laute sind je ein Schritt. Tempo- und Blick-Karten direkt **unter** einer Karte gehören zu ihr; wo
  sie nicht passen, werden sie übergangen und genannt.
- Wiederholen … Ende-Wiederholen klammert (auch verschachtelt). Die Zahl steht handschriftlich auf der Karte – die liest
  Knowlin nicht, sie wird im Baukasten eingestellt (Standard 2).
- „Wenn sie fällt“ beginnt eine zweite Reihe: Fällt sie, endet die erste; steht sie wieder, läuft die zweite, dann Ende.
- Eine unbekannte Karte beendet das Lesen dort, mit ihrem Namen.

Derselbe Ablauf entsteht auch im Baukasten zum Ziehen (ohne Karten). Ein Ablauf ist nur Daten: Schritte mit festen
Arten und Grenzen (`pruefen`) – nichts wird als Code ausgeführt.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any

FORMAT = "duck-cards/0"
DATEI = "ablaeufe.json"
MAX_SCHRITTE = 60
MAX_TIEFE = 3
MAX_MAL = 10
MAX_ABLAEUFE = 40
NAME_MAX = 40
QUELLE = "https://microduckstudio.com/cards/"
DRUCK = "https://microduckstudio.com/cards/print/"

# Karten der Starter-Deck-Nummern (duck-cards/0) → Schritt oder Zusatz
KARTEN: dict[int, tuple[str, str]] = {
    0: ("walk_forward", "Vorwärts gehen"), 1: ("walk_backward", "Rückwärts gehen"), 2: ("turn_left", "Links drehen"),
    3: ("turn_right", "Rechts drehen"), 4: ("stop", "Anhalten"),
    20: ("slow", "Langsam"), 21: ("fast", "Schnell"), 22: ("normal", "Normal"),
    40: ("look_left", "Nach links schauen"), 41: ("look_right", "Nach rechts schauen"), 42: ("look_up", "Nach oben schauen"),
    43: ("look_down", "Nach unten schauen"), 44: ("straight", "Geradeaus schauen"),
    60: ("kick_left", "Schuss links"), 61: ("kick_right", "Schuss rechts"), 62: ("sit_or_stand", "Hinsetzen oder aufstehen"),
    63: ("roll", "Rolle"), 64: ("peck_ground", "Am Boden picken"),
    80: ("greet", "Hallo"), 81: ("chirp", "Zwitschern"), 82: ("coo", "Gurren"), 83: ("alarm", "Alarm"), 84: ("wheee", "Juhu"),
    100: ("start", "Start"), 101: ("end", "Ende"), 102: ("repeat", "Wiederholen"), 103: ("end_repeat", "Ende wiederholen"),
    120: ("when_falls", "Wenn sie fällt"),
}
GEHEN = {0: "vor", 1: "zurueck"}
DREHEN = {2: "links", 3: "rechts"}
TEMPO = {20: "langsam", 21: "schnell", 22: "normal"}
SCHAUEN = {40: "links", 41: "rechts", 42: "hoch", 43: "runter", 44: "gerade"}
TRICKS = {60: "kick_left", 61: "kick_right", 62: "sit_toggle", 63: "roulade", 64: "ground_pick"}
LAUTE = {80: "greet", 81: "chirp", 82: "coo", 83: "alarm", 84: "wheee"}

ARTEN = ("gehen", "drehen", "stopp", "schauen", "trick", "laut", "wiederholen")
RICHTUNG = {"gehen": ("vor", "zurueck"), "drehen": ("links", "rechts"),
            "schauen": ("links", "rechts", "hoch", "runter", "gerade")}
TEMPI = ("langsam", "normal", "schnell")


def kartenname(tag: int) -> str:
    k = KARTEN.get(tag)
    if k:
        return k[1]
    if 200 <= tag <= 299:
        return f"eigene Karte {tag}"
    return f"Karte {tag}"


# ── Prüfen (für Baukasten, Ablage und Karten) ─────────────────────────────
def _schritt(s: Any, tiefe: int, zaehler: list[int]) -> dict[str, Any] | None:
    if not isinstance(s, dict) or s.get("art") not in ARTEN:
        return None
    zaehler[0] += 1
    if zaehler[0] > MAX_SCHRITTE:
        return None
    art = s["art"]
    out: dict[str, Any] = {"art": art}
    if art in RICHTUNG:
        if s.get("richtung") not in RICHTUNG[art]:
            return None
        out["richtung"] = s["richtung"]
    if art in ("gehen", "drehen") and s.get("tempo") in TEMPI:
        out["tempo"] = s["tempo"]
    if art in ("gehen", "drehen", "stopp") and s.get("schauen") in RICHTUNG["schauen"]:
        out["schauen"] = s["schauen"]
    if art == "trick":
        if s.get("name") not in TRICKS.values():
            return None
        out["name"] = s["name"]
    if art == "laut":
        if s.get("name") not in LAUTE.values():
            return None
        out["name"] = s["name"]
    if art == "wiederholen":
        if tiefe >= MAX_TIEFE:
            return None
        try:
            mal = int(s.get("mal", 2))
        except (TypeError, ValueError):
            return None
        out["mal"] = max(1, min(MAX_MAL, mal))
        innen = [_schritt(x, tiefe + 1, zaehler) for x in s.get("schritte") or []]
        if any(x is None for x in innen):
            return None
        out["schritte"] = innen
    return out


def pruefen(ablauf: Any) -> tuple[dict[str, Any] | None, str]:
    """Nur bekannte Arten und Werte, höchstens 60 Schritte, 3 Ebenen Wiederholung, 10-mal."""
    if not isinstance(ablauf, dict):
        return None, "Kein Ablauf."
    zaehler = [0]
    reihen = {}
    for k in ("schritte", "bei_sturz"):
        roh = ablauf.get(k) or []
        if not isinstance(roh, list):
            return None, "Schritte müssen eine Liste sein."
        r = [_schritt(s, 0, zaehler) for s in roh]
        if any(x is None for x in r):
            return None, ("Zu viele Schritte (höchstens 60)." if zaehler[0] > MAX_SCHRITTE
                          else "Ein Schritt ist unbekannt oder unvollständig.")
        reihen[k] = r
    if not reihen["schritte"]:
        return None, "Der Ablauf ist leer."
    name = re.sub(r"[\x00-\x1f<>]", "", str(ablauf.get("name") or "")).strip()[:NAME_MAX]
    return {"name": name, "schritte": reihen["schritte"], "bei_sturz": reihen["bei_sturz"]}, ""


def anzahl(schritte: list[dict[str, Any]]) -> int:
    """Wie viele Schritte tatsächlich laufen (Wiederholungen ausgerollt)."""
    n = 0
    for s in schritte:
        n += s["mal"] * anzahl(s["schritte"]) if s["art"] == "wiederholen" else 1
    return n


# ── Duck Cards lesen ─────────────────────────────────────────────────────
def _zeilen(tags: list[dict[str, float]]) -> list[list[dict[str, float]]]:
    groesse = statistics.median([max(1e-6, float(t.get("w", 1))) for t in tags])
    zeilen: list[list[dict[str, float]]] = []
    for t in sorted(tags, key=lambda t: t["y"]):
        if zeilen and abs(t["y"] - statistics.mean(x["y"] for x in zeilen[-1])) < 0.6 * groesse:
            zeilen[-1].append(t)
        else:
            zeilen.append([t])
    return [sorted(z, key=lambda t: t["x"]) for z in zeilen]


def aus_karten(tags: list[dict[str, Any]], mal: int = 2) -> dict[str, Any]:
    """Erkannte Tags ({id, x, y, w} in Bildpunkten) → Ablauf plus Meldungen. Nur Nummern und Lagen, kein Bild."""
    meldungen: list[str] = []
    sauber = []
    for t in tags[:80]:
        try:
            sauber.append({"id": int(t["id"]), "x": float(t["x"]), "y": float(t["y"]), "w": float(t.get("w", 1))})
        except (KeyError, TypeError, ValueError):
            continue
    if not sauber:
        return {"ok": False, "fehler": "Keine Karte erkannt.", "meldungen": []}
    groesse = statistics.median(t["w"] for t in sauber)
    zeilen = _zeilen(sauber)
    zusatz = lambda t: 20 <= t["id"] <= 59                                  # noqa: E731 – Tempo und Blick
    haupt: list[list[dict[str, Any]]] = []
    for z in zeilen:
        oben = haupt[-1] if haupt else []                      # Zusatzkarten gehören zur Karte direkt darüber
        for m in (t for t in z if zusatz(t)):
            ziel = min(oben, key=lambda k: abs(k["x"] - m["x"])) if oben else None
            if ziel is None or abs(ziel["x"] - m["x"]) > 0.7 * groesse:
                meldungen.append(f"„{kartenname(m['id'])}“ liegt unter keiner Karte – übergangen.")
            else:
                ziel["unter"].append(m["id"])
        karten = [{**t, "unter": []} for t in z if not zusatz(t)]
        if karten:
            haupt.append(karten)
    erste: list[dict[str, Any]] = []
    sturz: list[dict[str, Any]] = []
    for z in haupt:
        if z[0]["id"] == 120 and not sturz:
            sturz = z[1:]
        elif sturz:
            sturz += z
        else:
            erste += z
    ids = [k["id"] for k in erste]
    if 100 in ids:
        erste = erste[ids.index(100) + 1:]
        ids = [k["id"] for k in erste]
    if 101 in ids:
        erste = erste[:ids.index(101)]
    schritte, ok = _reihe(erste, mal, meldungen)
    bei_sturz, ok2 = _reihe(sturz, mal, meldungen) if ok else ([], True)
    ablauf, grund = pruefen({"name": "", "schritte": schritte, "bei_sturz": bei_sturz})
    if ablauf is None:
        return {"ok": False, "fehler": grund, "meldungen": meldungen, "karten": [k["id"] for k in erste]}
    return {"ok": True, "ablauf": ablauf, "meldungen": meldungen, "karten": [k["id"] for k in erste],
            "vollstaendig": ok and ok2, "quelle": QUELLE}


def _reihe(karten: list[dict[str, Any]], mal: int, meldungen: list[str]) -> tuple[list[dict[str, Any]], bool]:
    stapel: list[list[dict[str, Any]]] = [[]]
    for k in karten:
        t, unter = k["id"], k.get("unter") or []
        if t == 102:
            neu = {"art": "wiederholen", "mal": mal, "schritte": []}
            stapel[-1].append(neu)
            stapel.append(neu["schritte"])
            continue
        if t == 103:
            if len(stapel) > 1:
                stapel.pop()
            else:
                meldungen.append("„Ende wiederholen“ ohne „Wiederholen“ – übergangen.")
            continue
        if t in (100, 101, 120):
            continue
        s = _karte(t)
        if s is None:
            meldungen.append(f"„{kartenname(t)}“ kennt Knowlin nicht – hier endet das Lesen.")
            return stapel[0], False
        for u in unter:
            if u in TEMPO and s["art"] in ("gehen", "drehen"):
                s["tempo"] = TEMPO[u]
            elif u in SCHAUEN and s["art"] in ("gehen", "drehen", "stopp"):
                s["schauen"] = SCHAUEN[u]
            else:
                meldungen.append(f"„{kartenname(u)}“ passt nicht unter „{kartenname(t)}“ – übergangen.")
        stapel[-1].append(s)
    if len(stapel) > 1:
        meldungen.append("„Wiederholen“ ohne Ende – bis zum Schluss wiederholt.")
    return stapel[0], True


def _karte(t: int) -> dict[str, Any] | None:
    if t in GEHEN:
        return {"art": "gehen", "richtung": GEHEN[t]}
    if t in DREHEN:
        return {"art": "drehen", "richtung": DREHEN[t]}
    if t == 4:
        return {"art": "stopp"}
    if t in SCHAUEN:
        return {"art": "schauen", "richtung": SCHAUEN[t]}
    if t in TRICKS:
        return {"art": "trick", "name": TRICKS[t]}
    if t in LAUTE:
        return {"art": "laut", "name": LAUTE[t]}
    return None


def als_karten(schritte: list[dict[str, Any]]) -> list[list[int]]:
    """Umgekehrt: welche Duck Cards man für diesen Ablauf hinlegt (je Karte die Nummern darunter)."""
    rueck_gehen = {v: k for k, v in GEHEN.items()}
    rueck_drehen = {v: k for k, v in DREHEN.items()}
    rueck_tempo = {v: k for k, v in TEMPO.items()}
    rueck_schauen = {v: k for k, v in SCHAUEN.items()}
    out: list[list[int]] = []
    for s in schritte:
        art = s["art"]
        if art == "wiederholen":
            out.append([102])
            out += als_karten(s["schritte"])
            out.append([103])
            continue
        tag = {"gehen": rueck_gehen.get(s.get("richtung", "")), "drehen": rueck_drehen.get(s.get("richtung", "")),
               "stopp": 4, "schauen": rueck_schauen.get(s.get("richtung", "")),
               "trick": {v: k for k, v in TRICKS.items()}.get(s.get("name", "")),
               "laut": {v: k for k, v in LAUTE.items()}.get(s.get("name", ""))}[art]
        unter = [x for x in (rueck_tempo.get(s.get("tempo", "")), rueck_schauen.get(s.get("schauen", ""))) if x is not None]
        out.append([tag, *unter])
    return out


# ── Ablage ───────────────────────────────────────────────────────────────
class Ablaeufe:
    def __init__(self, ordner: Path) -> None:
        self.pfad = Path(ordner) / DATEI

    def alle(self) -> dict[str, dict[str, Any]]:
        try:
            d = json.loads(self.pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        out = {}
        for k, v in (d.items() if isinstance(d, dict) else []):
            a, _ = pruefen(v)
            if a is not None:
                out[k] = a
        return out

    def speichern(self, ablauf: dict[str, Any]) -> tuple[str | None, str]:
        a, grund = pruefen(ablauf)
        if a is None:
            return None, grund
        if not a["name"]:
            return None, "Gib dem Ablauf einen Namen."
        d = self.alle()
        if a["name"] not in d and len(d) >= MAX_ABLAEUFE:
            return None, f"Schon {MAX_ABLAEUFE} Abläufe – lösch erst einen."
        d[a["name"]] = a
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".teil")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.pfad)
        return a["name"], ""

    def loeschen(self, name: str) -> bool:
        d = self.alle()
        if name not in d:
            return False
        del d[name]
        tmp = self.pfad.with_suffix(".teil")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.pfad)
        return True
