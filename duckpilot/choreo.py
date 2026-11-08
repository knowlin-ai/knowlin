"""Tanzen zu Musik und Choreomodus (seit 0.36).

Wunsch des Maintainers: „Choreomodus – einstudierter Tanz zu einem Musikstück, z. B. auch mit solchen tollen Posen.“

Ablauf:
1. Die Oberfläche lädt ein Musikstück (bleibt im Datenordner, nie im Netz) und analysiert es im Browser: Tempo (BPM),
   erster Schlag, Lautstärke je Takt. Dieselbe Analyse gilt am PC und am Handy.
2. `plane()` macht daraus einen Tanz: Abschnitte nach Energie (ruhig → nicken/wippen, mittel → wackeln, laut →
   drehen/Party), an Höhepunkten eine Pose oder ein Gefühl. Jeder Schritt sitzt auf einem Taktanfang.
3. Der Tanz lässt sich anpassen und als Choreo speichern (`choreos.json` im Datenordner) – Claude kann ihn mit dem
   Werkzeug `choreo` vorschlagen, ändern oder abspielen.
4. `MusikTanz` (motion/tanz) spielt ihn im Takt, während die Oberfläche die Musik abspielt.

Posen kommen aus der Akrobatik (gespeicherte Haltungen). Im Simulator mit echter Physik hält sie sie wirklich; im
einfachen Simulator und am Roboter wird daraus eine angedeutete Geste (Kopf und Haltung), weil robotd für die Beine
nur Policies annimmt.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from .motion.reachy_tanz import REACHY_GEFUEHLE, REACHY_STUFEN, REACHY_TANZ, REACHY_TANZ_TEXT
from .motion.tanz import TANZGESTEN, geste_im_takt  # noqa: F401 – Tanzgesten gehören zur Motorik

SCHRITTE = ("nicken", "wippen", "wackeln", "wiegen", "schritt", "drehen", "trick", "pose", "gefuehl", "pause")
GEFUEHLE = ("begeistert", "freude", "aufgeregt", "ja", "staunen", "stolz")   # Gesten aus Tricks für Höhepunkte
MAX_CHOREOS = 40
MAX_SCHRITTE = 400
MUSIK_ENDUNGEN = {".mp3", ".ogg", ".wav", ".m4a", ".flac", ".opus", ".webm"}
MUSIK_MAX = 40 * 1024 * 1024


def _name(text: str, laenge: int = 60) -> str:
    return " ".join(str(text or "").replace("/", " ").replace("\\", " ").split())[:laenge]


def takt_s(bpm: float) -> float:
    """Länge eines Takts (4 Schläge) in Sekunden."""
    return 4 * 60.0 / max(40.0, min(220.0, float(bpm)))


TEILE = ("Intro", "Strophe", "Refrain", "Bridge", "Drop", "Breakdown", "Outro")
PHRASE = 4          # Takte je Phrase – Teile eines Stücks beginnen fast immer auf einer Phrasengrenze


def teile(energie: list[float], klang: list[list[float]] | None = None) -> list[dict[str, Any]]:
    """Mit Klangbild je Takt (seit 0.38.23): Grenzen und Wiederholungen aus Harmonie und Klangfarbe
    (`musik_struktur.struktur`) – der wiederholte, laute Teil ist der Refrain, einmalige Teile die Bridge.
    Ohne Klangbild: die Teile eines Stücks aus der Lautstärke je Takt – wie die Phrasenerkennung der DJ-Lichtsteuerungen:
    Phrasen zu vier Takten in drei Stufen (ruhig, mittel, laut), gleiche Nachbarn verschmolzen, dann benannt:
    Intro/Outro am Rand, laut = Refrain (oder Drop direkt nach einer ruhigen Stelle), mittel = Strophe,
    ruhig mittendrin = Breakdown. Ergebnis: [{takt, takte, name, stufe}]."""
    if not energie:
        return []
    if klang:
        try:
            from .musik_struktur import struktur

            return struktur(energie, klang)
        except (ValueError, IndexError, TypeError):
            pass                                   # Klangbild unbrauchbar: nach Lautstärke wie bisher
    bloecke = []
    for k in range(0, len(energie), PHRASE):
        stueck = energie[k:k + PHRASE]
        e = sum(stueck) / len(stueck)
        bloecke.append((k, len(stueck), 0 if e < 0.35 else 1 if e < 0.7 else 2))
    roh: list[list[int]] = []                 # [takt, takte, stufe]
    for k, n, st in bloecke:
        if roh and roh[-1][2] == st:
            roh[-1][1] += n
        else:
            roh.append([k, n, st])
    hoechste = max(r[2] for r in roh)
    out = []
    for i, (k, n, st) in enumerate(roh):
        if i == 0 and st < hoechste and len(roh) > 1:
            name = "Intro"
        elif i == len(roh) - 1 and st < hoechste and len(roh) > 1:
            name = "Outro"
        elif st == 2 or st == hoechste:
            name = "Drop" if i > 0 and roh[i - 1][2] == 0 else "Refrain"
        elif st == 1:
            name = "Strophe"
        else:
            name = "Breakdown"
        out.append({"takt": k, "takte": n, "name": name, "stufe": st})
    return out


# Bewegungen je Teil, Phrase für Phrase (zu je vier Takten) – gleiche Teile tanzt sie gleich, wie ein Mensch den
# Refrain. "@" = Höhepunkt: eine gespeicherte Pose (wenn es welche gibt) oder eine Geste aus Tricks.
MUSTER: dict[str, tuple[tuple[tuple[str, int], ...], ...]] = {
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


# Reachy Mini (seit 0.38.13): gleicher Aufbau, aber nur Reachys Bewegungen (`motion/reachy_tanz`). „gesteN“ = eine
# Bewegung der Energiestufe N (fest je Teil und Stelle), Namen direkt aus REACHY_TANZ, „@“ = Gefühl am Höhepunkt.
# Refrain und Drop drehen den Körper hin und her.
MUSTER_REACHY: dict[str, tuple[tuple[tuple[str, int], ...], ...]] = {
    "Intro": ((("wiegen", 2), ("geste0", 2)), (("kopfnicken", 2), ("antennen_takt", 2))),
    "Strophe": ((("kopfnicken", 2), ("geste1", 2)), (("wiegen", 1), ("antennen_takt", 1), ("geste1", 2))),
    "Refrain": ((("@", 1), ("koerper_drehen", 2), ("geste2", 1)), (("party", 2), ("koerper_drehen", 2))),
    "Bridge": ((("umschauen", 2), ("geste1", 2)), (("wiegen", 2), ("kopfnicken", 2))),
    "Drop": ((("@", 1), ("koerper_drehen", 3)), (("antennen_wirbel", 2), ("geste2", 2))),
    "Breakdown": ((("pause", 1), ("wiegen", 3)), (("umschauen", 2), ("wippen", 2))),
    "Outro": ((("wiegen", 2), ("geste0", 2)), (("kopfnicken", 2), ("wiegen", 2))),
}


def _geste(teil: str, phrase: int, platz: int, stufe: int, reachy: bool = False) -> str:
    """Welche Tanzgeste – fest je Teil und Stelle im Muster, damit jeder Refrain gleich getanzt wird."""
    liste = REACHY_STUFEN[stufe] if reachy else TANZGESTEN[stufe]
    return liste[(sum(map(ord, teil)) + 3 * phrase + platz) % len(liste)]


def plane(analyse: dict[str, Any], posen: list[str] | None = None, *, max_s: float = 240.0,
          reachy: bool = False) -> dict[str, Any]:
    """Tanz aus der Analyse eines Musikstücks: {bpm, start, energie: [0..1 je Takt]} → Choreo mit Schritten und Teilen.

    Das Stück wird in Teile gegliedert (Intro, Strophe, Refrain, Drop, Breakdown, Outro); jeder Teil bekommt sein
    Bewegungsmuster, Refrains also immer denselben Tanz. An Höhepunkten eine Pose (gespeicherte Haltungen) oder eine
    Geste, im letzten Takt eine Schlusspose. Deterministisch – gleiche Musik, gleicher Tanz.

    `reachy`: Tanz für Reachy Mini – nur Reachys Bewegungen (`art` trick mit Namen aus `REACHY_TANZ`), Gefühle aus
    seinen eigenen Gesten, keine Posen."""
    bpm = max(40.0, min(220.0, float(analyse.get("bpm") or 110)))
    start = max(0.0, float(analyse.get("start") or 0.0))
    energie = [max(0.0, min(1.0, float(e))) for e in (analyse.get("energie") or [])][: int(max_s / takt_s(bpm)) + 1]
    if not energie:
        energie = [0.5] * 16
    tl = takt_s(bpm)
    posen = [] if reachy else [p for p in (posen or []) if p][:20]
    gefuehle = REACHY_GEFUEHLE if reachy else GEFUEHLE
    hoehe = [0]

    def hoehepunkt() -> dict[str, Any]:
        n = hoehe[0]
        hoehe[0] += 1
        if posen:
            return {"art": "pose", "name": posen[n % len(posen)]}
        return {"art": "gefuehl", "name": gefuehle[n % len(gefuehle)]}

    klang = analyse.get("klang")
    klang = klang[:len(energie)] if isinstance(klang, list) and len(klang) >= len(energie) else None
    abschnitte = _vorgabe(analyse.get("teile"), len(energie)) or teile(energie, klang)
    schritte: list[dict[str, Any]] = []
    langsam = bpm < 92                     # Balladen: wiegen statt Schritte und Drehungen (seit 0.38.23)
    for ab in abschnitte:
        muster = (MUSTER_REACHY if reachy else MUSTER)[ab["name"]]
        takt, ende, phrase = ab["takt"], ab["takt"] + ab["takte"], 0
        while takt < ende:
            # Energie dieser Phrase: leise Stellen in einem lauten Teil tanzt sie kleiner, Gesten nach der Stufe
            stueck = energie[takt:min(ende, takt + PHRASE)] or [0.5]
            e_phrase = sum(stueck) / len(stueck)
            stufe_phrase = 0 if e_phrase < 0.3 else 1 if e_phrase < 0.65 else 2
            for platz, (art, n) in enumerate(muster[phrase % len(muster)]):
                n = min(n, ende - takt)
                if n <= 0:
                    break
                if not reachy and art in ("schritt", "drehen") and (stufe_phrase == 0 or (langsam and ab["name"] != "Drop")):
                    art = "wiegen"
                if art == "@":
                    schritt = hoehepunkt()
                elif art.startswith("geste"):
                    stufe = min(int(art[-1]), stufe_phrase + 1)
                    schritt = {"art": "trick", "name": _geste(ab["name"], phrase % len(muster), platz, stufe, reachy)}
                elif reachy and art in REACHY_TANZ:
                    schritt = {"art": "trick", "name": art}
                else:
                    schritt = {"art": art}
                schritte.append({"t": round(start + takt * tl, 3), "takte": n, **schritt})
                takt += n
            phrase += 1
    # Schlusspose im letzten Takt
    letzter = schritte[-1]
    schluss = {"art": "pose", "name": posen[0]} if posen else {"art": "gefuehl", "name": "stolz"}
    if letzter["art"] not in ("pose", "gefuehl"):
        schritte = _einfuegen(schritte, {"t": round(start + (len(energie) - 1) * tl, 3), "takte": 1, **schluss}, tl)
    out = {"bpm": round(bpm, 2), "start": round(start, 3), "schritte": schritte,
           "abschnitte": [{"t": round(start + a["takt"] * tl, 3), "takte": a["takte"], "name": a["name"],
                           **({"gruppe": a["gruppe"]} if a.get("gruppe") else {})} for a in abschnitte],
           "dauer": round(start + len(energie) * tl, 2)}
    out["energie"] = [round(e, 2) for e in energie]      # zum Neuplanen einzelner Teile im Editor (ohne neue Analyse)
    if klang:                                            # Klangbild je Takt bleibt beim Tanz (seit 0.38.24): Neuplanen
        out["klang"] = _klang_sauber(klang)              # und spätere bessere Erkennung ohne die Musik erneut zu laden
    if reachy:
        out["koerper"] = "reachy_mini"
    return out


def _vorgabe(roh: Any, n: int) -> list[dict[str, Any]] | None:
    """Teile, die man im Tanzeditor selbst benannt hat (seit 0.38.23): [{takt, takte, name, gruppe?}] lückenlos über
    alle Takte – sonst None (dann erkennt `teile` sie neu)."""
    if not isinstance(roh, list) or not roh or len(roh) > 128:
        return None
    out, takt = [], 0
    for a in roh:
        if not isinstance(a, dict) or a.get("name") not in TEILE:
            return None
        try:
            k, m = int(a["takt"]), int(a["takte"])
        except (KeyError, TypeError, ValueError):
            return None
        if k != takt or m < 1:
            return None
        teil = {"takt": k, "takte": m, "name": a["name"], "stufe": 1}
        if isinstance(a.get("gruppe"), str) and len(a["gruppe"]) == 1 and a["gruppe"].isalpha():
            teil["gruppe"] = a["gruppe"].upper()
        out.append(teil)
        takt += m
    if takt != n:
        return None
    return out


def _einfuegen(schritte: list[dict[str, Any]], neu: dict[str, Any], tl: float) -> list[dict[str, Any]]:
    """Einen Ein-Takt-Schritt einsetzen; der Abschnitt, in den er fällt, wird geteilt."""
    out: list[dict[str, Any]] = []
    for s in schritte:
        ende = s["t"] + s["takte"] * tl
        if s["t"] <= neu["t"] < ende - 1e-6:
            vor = round((neu["t"] - s["t"]) / tl)
            nach = s["takte"] - vor - neu["takte"]
            if vor > 0:
                out.append({**s, "takte": vor})
            out.append(neu)
            if nach > 0:
                out.append({**s, "t": round(neu["t"] + neu["takte"] * tl, 3), "takte": nach})
        else:
            out.append(s)
    return out


def pruefe(choreo: dict[str, Any]) -> dict[str, Any]:
    """Eine Choreo von außen (Oberfläche, Claude, Knowlet) säubern – unbekannte Schritte fliegen raus."""
    bpm = max(40.0, min(220.0, float(choreo.get("bpm") or 110)))
    out = []
    for s in (choreo.get("schritte") or [])[:MAX_SCHRITTE]:
        if not isinstance(s, dict) or s.get("art") not in SCHRITTE:
            continue
        try:
            t = max(0.0, min(900.0, float(s.get("t", 0))))
            takte = max(1, min(64, int(s.get("takte", 1))))
        except (TypeError, ValueError):
            continue
        neu: dict[str, Any] = {"t": round(t, 3), "takte": takte, "art": s["art"]}
        if s["art"] in ("pose", "gefuehl", "trick"):
            neu["name"] = _name(s.get("name", ""), 40)
            if not neu["name"]:
                continue
        out.append(neu)
    out.sort(key=lambda s: s["t"])
    teile_ = []
    for a in (choreo.get("abschnitte") or [])[:64]:
        if isinstance(a, dict) and a.get("name") in TEILE:
            try:
                teil = {"t": round(max(0.0, float(a["t"])), 3), "takte": max(1, min(256, int(a["takte"]))),
                        "name": a["name"]}
                if isinstance(a.get("gruppe"), str) and len(a["gruppe"]) == 1 and a["gruppe"].isalpha():
                    teil["gruppe"] = a["gruppe"].upper()      # wiederholte Teile tragen denselben Buchstaben
                teile_.append(teil)
            except (KeyError, TypeError, ValueError):
                continue
    sauber = {"bpm": round(bpm, 2), "start": round(max(0.0, float(choreo.get("start") or 0.0)), 3), "schritte": out,
              "abschnitte": teile_, "dauer": round(max([s["t"] + s["takte"] * takt_s(bpm) for s in out] or [0.0]), 2)}
    energie = choreo.get("energie")
    if isinstance(energie, list) and 0 < len(energie) <= 600 and all(isinstance(e, (int, float)) for e in energie):
        sauber["energie"] = [round(max(0.0, min(1.0, float(e))), 2) for e in energie]
    klang = _klang_sauber(choreo.get("klang"))
    if klang and len(klang) == len(sauber.get("energie", [])):
        sauber["klang"] = klang
    if choreo.get("koerper") == "reachy_mini":            # für Reachy eingeübt (seit 0.38.13)
        sauber["koerper"] = "reachy_mini"
    return sauber


def _klang_sauber(klang: Any) -> list[list[float]] | None:
    """Klangbild je Takt (Tonklassen und Bänder) prüfen: Liste aus höchstens 600 Takten mit je 12–24 Zahlen."""
    if not isinstance(klang, list) or not 0 < len(klang) <= 600:
        return None
    out = []
    for z in klang:
        if not isinstance(z, list) or not 12 <= len(z) <= 24 or not all(isinstance(v, (int, float)) for v in z):
            return None
        out.append([round(float(v), 2) for v in z])
    return out


def gesten() -> list[str]:
    """Gesten aus Tricks, die im Tanz gehen (Pollens Emotionen und eigene) – ohne die, die sich hinlegen."""
    from .motion.behaviors import EMOTIONS

    return [k for k, v in EMOTIONS.items() if not any("skill" in kf for kf in v)]


def reachy_gesten() -> list[str]:
    """Reachys eigene Gesten zu Gefühlen (für Höhepunkte im Tanz) – ohne die traurigen und ärgerlichen."""
    from .motion.reachy_gesten import GESTEN

    return [k for k in GESTEN if k not in ("traurig", "muede", "wuetend", "frustriert", "stolpern", "nein", "trotzig")]


def ki_auftrag_reachy(name: str, musik: str, choreo: dict[str, Any]) -> str:
    """Der Auftrag an das KI-Gehirn für Reachy Mini: nur Reachys Bewegungen (Kopf, Antennen, Körperdrehung)."""
    bpm = float(choreo.get("bpm") or 110)
    tl = takt_s(bpm)
    teile_ = ", ".join(f"{a['name']} ab {a['t']:.1f} s ({a['takte']} Takte)" for a in choreo.get("abschnitte") or [])
    stufe = lambda n: ", ".join(f"{k} ({REACHY_TANZ_TEXT[k]})" for k in REACHY_STUFEN[n])   # noqa: E731
    return (f"Studier bitte einen Tanz für Reachy Mini zum Stück „{name}“ ein (Datei {musik or 'ohne Musik'}): {bpm:.1f} BPM, "
            f"erster Schlag bei {float(choreo.get('start') or 0):.2f} s, ein Takt = {tl:.3f} s, Länge "
            f"{float(choreo.get('dauer') or 0):.0f} s. Teile: {teile_ or 'unbekannt'}. Reachy hat keine Beine und keinen "
            f"Schnabel – er tanzt mit Kopf, Antennen und Körperdrehung. Bewegungen (art trick, name genau so, im Takt "
            f"gestreckt): ruhig {stufe(0)}; mittel {stufe(1)}; laut {stufe(2)}. Gefühle als Akzent (art gefuehl): "
            f"{', '.join(reachy_gesten())}. Sonst nur art pause. Speichere ihn mit dem Werkzeug choreo (aktion speichern, "
            f"name „{name}“, musik „{musik}“, bpm, start, schritte lückenlos auf Taktanfängen). Tanz ihn noch nicht, sag "
            f"nur kurz, was du dir ausgedacht hast.")


def reachy_werkzeug(tool: dict[str, Any]) -> dict[str, Any]:
    """Das Werkzeug `choreo` für Reachy Mini: dieselben Aktionen, aber nur Reachys Bewegungen im Angebot an die KI."""
    neu = json.loads(json.dumps(tool))
    neu["description"] = (
        "Einstudierte Tänze zu Musikstücken für Reachy Mini. aktion=liste zeigt die gespeicherten Tänze; aktion=tanzen "
        "tanzt einen davon (die Musik spielt die Oberfläche dazu); aktion=speichern legt einen Tanz an oder ersetzt ihn "
        "(name, musik, bpm, start, schritte). Ein Schritt: t (Sekunden, immer auf einem Taktanfang: start + n·240/bpm), "
        "takte, art (trick = eine Bewegung von Reachy im Takt, gefuehl = kurze Geste als Akzent, pause) und name. "
        f"Bewegungen: {', '.join(REACHY_TANZ)}; Gefühle: {', '.join(reachy_gesten())}. Reachy tanzt mit Kopf, Antennen "
        "und Körperdrehung – ruhige Teile ruhig, Refrains gleich, Körper drehen (koerper_drehen, party) für laute Teile.")
    schritt = neu["input_schema"]["properties"]["schritte"]["items"]["properties"]
    schritt["art"]["enum"] = ["trick", "gefuehl", "pause"]
    schritt["name"] = {"type": "string", "enum": [*REACHY_TANZ, *reachy_gesten()]}
    return neu


def ki_auftrag(name: str, musik: str, choreo: dict[str, Any], posen: list[str]) -> str:
    """Der Auftrag an das KI-Gehirn: das Stück in Teilen, was sie kann – und wie sie den Tanz speichert."""
    bpm = float(choreo.get("bpm") or 110)
    tl = takt_s(bpm)
    teile_ = ", ".join(f"{a['name']} ab {a['t']:.1f} s ({a['takte']} Takte)" for a in choreo.get("abschnitte") or [])
    return (f"Studier bitte einen Tanz zum Stück „{name}“ ein (Datei {musik or 'ohne Musik'}): {bpm:.1f} BPM, erster "
            f"Schlag bei {float(choreo.get('start') or 0):.2f} s, ein Takt = {tl:.3f} s, Länge {float(choreo.get('dauer') or 0):.0f} s. "
            f"Teile: {teile_ or 'unbekannt'}. Bewegungen: schritt (Bein zu Bein, Seitschritt je Schlag), wiegen (Gewicht "
            f"verlagern), drehen (ganze Drehung, Richtung wechselt), nicken, wippen, wackeln, pause; Tanzgesten (art trick, "
            f"im Takt gestreckt): ruhig {', '.join(TANZGESTEN[0])}, mittel {', '.join(TANZGESTEN[1])}, laut {', '.join(TANZGESTEN[2])}; "
            f"Posen: {', '.join(posen) or 'keine gespeichert'}; Gesten aus Tricks: {', '.join(gesten())}. "
            f"Speichere ihn mit dem Werkzeug choreo (aktion speichern, name „{name}“, musik „{musik}“, bpm, start, schritte "
            f"lückenlos auf Taktanfängen). Tanz ihn noch nicht, sag nur kurz, was du dir ausgedacht hast.")


class ChoreoBuch:
    """Gespeicherte Tänze und die Musikstücke dazu – nur im Datenordner, nie in OneDrive oder im Netz."""

    def __init__(self, root: Path) -> None:
        self.path = root / "choreos.json"
        self.musik = root / "musik"
        self._lock = threading.Lock()

    def _lesen(self) -> dict[str, Any]:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def liste(self) -> list[dict[str, Any]]:
        return [{"name": k, **{f: v.get(f) for f in ("musik", "bpm", "dauer", "koerper")}, "schritte": len(v.get("schritte", []))}
                for k, v in sorted(self._lesen().items())]

    def hole(self, name: str) -> dict[str, Any] | None:
        return self._lesen().get(_name(name))

    def speichere(self, name: str, choreo: dict[str, Any], musik: str = "") -> dict[str, Any]:
        name = _name(name)
        if not name:
            raise ValueError("Bitte einen Namen für den Tanz angeben.")
        sauber = pruefe(choreo)
        if not sauber["schritte"]:
            raise ValueError("Der Tanz hat keine Schritte.")
        sauber["musik"] = musik if musik and (self.musik / musik).is_file() else ""
        with self._lock:
            d = self._lesen()
            if name not in d and len(d) >= MAX_CHOREOS:
                raise ValueError(f"Höchstens {MAX_CHOREOS} Tänze – erst einen löschen.")
            d[name] = sauber
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        return {"name": name, **sauber}

    def loesche(self, name: str) -> bool:
        with self._lock:
            d = self._lesen()
            if d.pop(_name(name), None) is None:
                return False
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        return True

    def musik_ablegen(self, dateiname: str, daten: bytes) -> str:
        """Ein Musikstück in den Datenordner legen; zurück kommt der sichere Dateiname."""
        stamm = Path(dateiname or "musik").stem
        endung = Path(dateiname or "").suffix.lower()
        if endung not in MUSIK_ENDUNGEN:
            raise ValueError("Nur Musikdateien (mp3, ogg, wav, m4a, flac, opus, webm).")
        if not daten or len(daten) > MUSIK_MAX:
            raise ValueError("Die Datei ist leer oder größer als 40 MB.")
        sicher = re.sub(r"[^\w.-]+", "_", stamm, flags=re.UNICODE).strip("._")[:60] or "musik"
        self.musik.mkdir(parents=True, exist_ok=True)
        ziel = self.musik / f"{sicher}{endung}"
        ziel.write_bytes(daten)
        return ziel.name

    def musik_pfad(self, name: str) -> Path | None:
        if not name or "/" in name or "\\" in name or name.startswith("."):
            return None
        p = self.musik / name
        return p if p.is_file() and p.suffix.lower() in MUSIK_ENDUNGEN else None
