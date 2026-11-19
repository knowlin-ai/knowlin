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

from .motion.reachy_tanz import REACHY_TANZ
from .motion.tanz import TANZGESTEN, geste_im_takt  # noqa: F401 – Tanzgesten gehören zur Motorik
from .motion.tanzstile import STILE, TanzStil
from .motion.tanzstile import stil as _stil

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



def _geste(teil: str, phrase: int, platz: int, stufe: int, st: TanzStil | None = None) -> str:
    """Welche Tanzgeste – fest je Teil und Stelle im Muster, damit jeder Refrain gleich getanzt wird."""
    liste = (st or STILE["ente"]).stufen[stufe]
    return liste[(sum(map(ord, teil)) + 3 * phrase + platz) % len(liste)]


def plane(analyse: dict[str, Any], posen: list[str] | None = None, *, max_s: float = 240.0,
          stil: str = "ente") -> dict[str, Any]:
    """Tanz aus der Analyse eines Musikstücks: {bpm, start, energie: [0..1 je Takt]} → Choreo mit Schritten und Teilen.

    Das Stück wird in Teile gegliedert (Intro, Strophe, Refrain, Drop, Breakdown, Outro); jeder Teil bekommt sein
    Bewegungsmuster, Refrains also immer denselben Tanz. An Höhepunkten eine Pose (gespeicherte Haltungen) oder eine
    Geste, im letzten Takt eine Schlusspose. Deterministisch – gleiche Musik, gleicher Tanz.

    `stil`: Tanz-Wortschatz der Bauart (`motion/tanzstile.py`, seit 0.43) – nur dessen Bewegungen (`art` trick),
    Gefühle und Posen nur, wenn die Bauart welche hat. Die Ente tanzt zusätzlich mit Schritten, Wiegen und Drehen."""
    st = _stil(stil)
    ente = "schritt" in st.arten
    bpm = max(40.0, min(220.0, float(analyse.get("bpm") or 110)))
    start = max(0.0, float(analyse.get("start") or 0.0))
    energie = [max(0.0, min(1.0, float(e))) for e in (analyse.get("energie") or [])][: int(max_s / takt_s(bpm)) + 1]
    if not energie:
        energie = [0.5] * 16
    tl = takt_s(bpm)
    posen = [p for p in (posen or []) if p][:20] if st.posen else []
    gefuehle = st.gefuehle
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
        muster = st.muster[ab["name"]]
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
                if ente and art in ("schritt", "drehen") and (stufe_phrase == 0 or (langsam and ab["name"] != "Drop")):
                    art = "wiegen"
                if art == "@":
                    schritt = hoehepunkt()
                elif art.startswith("geste"):
                    stufe = min(int(art[-1]), stufe_phrase + 1)
                    schritt = {"art": "trick", "name": _geste(ab["name"], phrase % len(muster), platz, stufe, st)}
                elif art in st.texte:
                    schritt = {"art": "trick", "name": art}
                else:
                    schritt = {"art": art}
                schritte.append({"t": round(start + takt * tl, 3), "takte": n, **schritt})
                takt += n
            phrase += 1
    # Schlusspose im letzten Takt
    letzter = schritte[-1]
    schluss = {"art": "pose", "name": posen[0]} if posen else {"art": "gefuehl", "name": st.schluss}
    if letzter["art"] not in ("pose", "gefuehl"):
        schritte = _einfuegen(schritte, {"t": round(start + (len(energie) - 1) * tl, 3), "takte": 1, **schluss}, tl)
    out = {"bpm": round(bpm, 2), "start": round(start, 3), "schritte": schritte,
           "abschnitte": [{"t": round(start + a["takt"] * tl, 3), "takte": a["takte"], "name": a["name"],
                           **({"gruppe": a["gruppe"]} if a.get("gruppe") else {})} for a in abschnitte],
           "dauer": round(start + len(energie) * tl, 2)}
    out["energie"] = [round(e, 2) for e in energie]      # zum Neuplanen einzelner Teile im Editor (ohne neue Analyse)
    if klang:                                            # Klangbild je Takt bleibt beim Tanz (seit 0.38.24): Neuplanen
        out["klang"] = _klang_sauber(klang)              # und spätere bessere Erkennung ohne die Musik erneut zu laden
    if st.key != "ente":
        out["stil"] = st.key
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
    stil = choreo.get("stil")
    if choreo.get("koerper") == "reachy_mini":            # Tänze vor 0.43 merkten sich den Körper statt der Bauart
        stil = "kopf_antennen"
    if stil in STILE and stil != "ente":                  # für eine Bauart eingeübt (seit 0.43)
        sauber["stil"] = stil
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


def gesten(stil: str = "ente") -> list[str]:
    """Bewegungen, die im Tanz gehen. Ente: Gesten aus Tricks (Pollens Emotionen und eigene) ohne die, die sich
    hinlegen; sonst der Wortschatz der Bauart."""
    if stil in STILE and stil != "ente":
        return list(REACHY_TANZ) if stil == "kopf_antennen" else STILE[stil].bewegungen()
    from .motion.behaviors import EMOTIONS

    return [k for k, v in EMOTIONS.items() if not any("skill" in kf for kf in v)]


def gefuehle(stil: str = "ente") -> list[str]:
    """Gefühle als Akzent im Tanz. Reachys eigene Gesten ohne die traurigen und ärgerlichen; sonst die der Bauart."""
    if stil == "kopf_antennen":
        from .motion.reachy_gesten import GESTEN

        return [k for k in GESTEN if k not in ("traurig", "muede", "wuetend", "frustriert", "stolpern", "nein", "trotzig")]
    return list(_stil(stil).gefuehle)


def reachy_gesten() -> list[str]:                         # ältere Aufrufer
    return gefuehle("kopf_antennen")


def namen(stil: str) -> dict[str, str]:
    """Kurze Beschreibung je Bewegung (Editor, Sprachmodell)."""
    return dict(_stil(stil).texte)


def ki_auftrag_stil(name: str, musik: str, choreo: dict[str, Any], stil: str) -> str:
    """Der Auftrag an das KI-Gehirn für eine Bauart ohne Beine: nur ihre Bewegungen und Gefühle."""
    st = _stil(stil)
    bpm = float(choreo.get("bpm") or 110)
    tl = takt_s(bpm)
    teile_ = ", ".join(f"{a['name']} ab {a['t']:.1f} s ({a['takte']} Takte)" for a in choreo.get("abschnitte") or [])
    stufe = lambda n: ", ".join(f"{k} ({st.texte.get(k, k)})" for k in st.stufen[n])   # noqa: E731
    return (f"Studier bitte einen Tanz zum Stück „{name}“ ein (Datei {musik or 'ohne Musik'}): {bpm:.1f} BPM, "
            f"erster Schlag bei {float(choreo.get('start') or 0):.2f} s, ein Takt = {tl:.3f} s, Länge "
            f"{float(choreo.get('dauer') or 0):.0f} s. Teile: {teile_ or 'unbekannt'}. Dieser Körper {st.wie}. "
            f"Bewegungen (art trick, name genau so, im Takt gestreckt): ruhig {stufe(0)}; mittel {stufe(1)}; laut "
            f"{stufe(2)}. Gefühle als Akzent (art gefuehl): {', '.join(gefuehle(stil))}. Sonst nur art pause. Speichere "
            f"ihn mit dem Werkzeug choreo (aktion speichern, name „{name}“, musik „{musik}“, bpm, start, schritte "
            f"lückenlos auf Taktanfängen). Tanz ihn noch nicht, sag nur kurz, was du dir ausgedacht hast.")


def ki_auftrag_reachy(name: str, musik: str, choreo: dict[str, Any]) -> str:   # ältere Aufrufer
    return ki_auftrag_stil(name, musik, choreo, "kopf_antennen")


def werkzeug(tool: dict[str, Any], stil: str) -> dict[str, Any]:
    """Das Werkzeug `choreo` für eine Bauart ohne Beine: dieselben Aktionen, aber nur ihre Bewegungen im Angebot."""
    if stil not in STILE or stil == "ente":
        return tool
    st = STILE[stil]
    neu = json.loads(json.dumps(tool))
    neu["description"] = (
        "Einstudierte Tänze zu Musikstücken. aktion=liste zeigt die gespeicherten Tänze; aktion=tanzen tanzt einen davon "
        "(die Musik spielt die Oberfläche dazu); aktion=speichern legt einen Tanz an oder ersetzt ihn (name, musik, bpm, "
        "start, schritte). Ein Schritt: t (Sekunden, immer auf einem Taktanfang: start + n·240/bpm), takte, art (trick = "
        "eine Bewegung im Takt, gefuehl = kurze Geste als Akzent, pause) und name. "
        f"Dieser Körper {st.wie}. Bewegungen: {', '.join(gesten(stil))}; Gefühle: {', '.join(gefuehle(stil))}. "
        "Ruhige Teile ruhig, Refrains gleich, die großen Bewegungen für laute Teile.")
    schritt = neu["input_schema"]["properties"]["schritte"]["items"]["properties"]
    schritt["art"]["enum"] = ["trick", "gefuehl", "pause"]
    schritt["name"] = {"type": "string", "enum": [*gesten(stil), *gefuehle(stil)]}
    return neu


def reachy_werkzeug(tool: dict[str, Any]) -> dict[str, Any]:                  # ältere Aufrufer
    return werkzeug(tool, "kopf_antennen")


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
        return [{"name": k, **{f: v.get(f) for f in ("musik", "bpm", "dauer")}, "stil": pruefe(v).get("stil"),
                 "schritte": len(v.get("schritte", []))}
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
