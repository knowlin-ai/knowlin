"""Kollisionsmodus im Physik-Simulator: die Ente anstoßen, Ball und Würfel greifen, rollen und werfen.

Nur im Simulator mit echter Physik (MuJoCo) – am echten Roboter gibt es das nicht.

* **Anstoßen:** ein kurzer Stoß (Kraftstoß in N·s, höchstens `MAX_STOSS_NS`) an Rumpf, Kopf oder einem Bein, von
  einer Richtung aus. MuJoCo rechnet den Stoß als Kraft über `STOSS_DAUER_S` an genau dem Punkt – trifft er hoch,
  kippt sie eher, trifft er tief, rutscht sie eher.
* **Objekte:** Ball und Würfel liegen als freie Körper im Modell (`add_objects`). Solange sie nicht gebraucht
  werden, parken sie außerhalb der Wohnung. Greifen = Objekt folgt der Hand (Maus/Finger), Loslassen mit
  Geschwindigkeit = werfen, rollen = am Boden mit passendem Drall anschubsen. Jedes Objekt prallt an der Ente,
  an Möbeln und Wänden ab.
* **Hand:** eine Kugel (Radius `HAND_R`) als eigener, leichter Körper. Sie schwebt (Schwerkraft ausgeglichen) und
  folgt dem Zeiger über eine gedeckelte Feder-Dämpfer-Kraft (`_hand_kraft`): das Ziel läuft höchstens
  `HAND_MAX_MS` schnell, die Hand hängt etwa 17 ms hinterher. An der Ente stößt sie an und **geht nicht
  hindurch** – im Kontakt drückt sie mit höchstens `HAND_KRAFT_N`, schiebt die Ente also oder rutscht ab. Durch
  Objekte, Möbel, Wände und Boden geht sie hindurch (Kontaktbits), damit man an jedes Ding herankommt.
* **Greifen** nimmt das Objekt in Reichweite (`GREIF_REICHWEITE_M` von der Oberfläche) per Weld-Gleichung an die
  Hand (Schwerkraft solange ausgeglichen). Ein gehaltenes Ding stößt also auch an die Ente, statt durch sie zu
  gehen. **Loslassen** mit einer vorgegebenen Geschwindigkeit (die Oberfläche rechnet sie aus Wurfbewegung und
  Kamera und zeigt den Flugbogen vorher) oder mit dem Tempo der Hand. Keine Luftreibung: der Bogen ist ein
  reiner Wurf mit Schwerkraft.
* **Ziehen („Zug“):** wie in MuJoCos `simulate` und Gazebos „Mouse Drag“: Man fasst die Ente an einem Punkt ihrer
  Oberfläche an (höchstens `ZUG_REICHWEITE_M` daneben) und zieht. Eine Feder-Dämpfer-Kraft zieht genau diesen
  Punkt zum Ziel (die Oberfläche legt es auf eine Ebene quer zur Kamera durch den Anfasspunkt):
  F = `ZUG_K` · Abstand − `ZUG_C` · Tempo des Punkts, höchstens `ZUG_N_MAX`. Kurz zupfen lässt sie wackeln, am Kopf
  kräftig zur Seite ziehen wirft sie um; hochheben kann man sie damit nicht (6 N < ihr Gewicht 7,2 N).
* **Trainingsdaten:** Jeder Stoß, Wurf, Roll, Zug und jede Berührung mit der Hand ist eine Episode (`Episode`) – was passiert ist, Zustand vorher
  und nachher, Ausgang (steht · wackelt · fällt · steht wieder auf) und eine Zeitreihe mit 10 Hz. `EpisodenLog`
  hängt sie als JSON-Zeile an `<datenordner>/kollision/episoden.jsonl`. `stossproben()` macht daraus das
  Stoß-Profil, mit dem das Lernen am PC (`lernen.py`) übt: statt nur zufälliger kleiner Schubse auch die Stöße,
  die die Ente hier wirklich bekommen hat.

Keine personenbezogenen Daten: nur Physik (Lage, Geschwindigkeit, Gelenkwinkel, Stoß).
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


class _MujocoLazy:
    """MuJoCo erst laden, wenn wirklich gerechnet wird (seit 0.38.7): Konstanten, Grenzen und das Episodenprotokoll
    braucht die Oberfläche auch ohne installierte Physik – sonst brach `/api/kollision` ohne MuJoCo ab."""

    def __getattr__(self, name: str):
        import mujoco as _m

        return getattr(_m, name)


mujoco = _MujocoLazy()

MASSE_ENTE = 0.737                 # kg (Pollens Modell)
MAX_STOSS_NS = 0.6                 # N·s – Δv bis ≈ 0,8 m/s: reicht sicher zum Umwerfen
STOSS_DAUER_S = 0.04
MAX_WURF_MS = 6.0
MAX_ROLL_MS = 3.0
MAX_HOEHE_M = 1.2
GREIF_HOEHE_M = 0.25               # gegriffenes Objekt: Standardhöhe über dem Boden
PARK_X = 30.0                      # außerhalb jeder Wohnung (Boden ist eine unendliche Ebene)
HAND_R = 0.035                     # m – Kugel der Hand
HAND_MAX_MS = 2.5                  # m/s – schneller folgt die Hand dem Zeiger nicht (je Physikschritt begrenzt)
HAND_PARK = (PARK_X, -10.0, 1.0)   # „aus“: weit weg von allem
HAND_MASSE = 0.05                  # kg – leicht: ihr Schwung (≤ 0,13 N·s bei 2,5 m/s) ist klein gegen MAX_STOSS_NS
HAND_OMEGA = 60.0                  # 1/s – Feder-Dämpfer kritisch gedämpft: Zeitkonstante 1/60 s ≈ 17 ms, kein Schwingen
HAND_A_MAX = 300.0                 # m/s² – frei im Raum: aus 2,5 m/s auf ≈ 1 cm zum Stehen, ohne Überschwingen
#                                    (Kraft = Masse · a; mit Ding entsprechend mehr, damit auch der Klotz flink ist)
HAND_KRAFT_FREI_N = 20.0           # N – frei höchstens: ein schwerer Klotz folgt etwas träger (wie echt) und zerrt
#                                    nicht mit 200 N über ein Möbel, an dem er hängen bleibt
HAND_A_ZIEL = 200.0                # m/s² – das Ziel selbst fährt an und bremst so (auf 2,5 m/s in 12 ms), damit die
#                                    Hand beim Anhalten nicht überschwingt
HAND_KONTAKT_HALTEN_S = 0.05       # s – reißt der Kontakt kurz ab, bleibt die Kontakt-Kraftgrenze noch so lange
HAND_GLATT_MAX_S = 0.05            # zwischen zwei Zeiger-Nachrichten (30 Hz) wird das Ziel gleitend geführt
HAND_KRAFT_N = 3.0                 # N – im Kontakt mit der Ente: ≈ 40 % ihres Gewichts. Langsam drücken schiebt sie
#                                    und kann sie kippen (Kippkraft am Rumpf ≈ 1,5–2 N), ein Wisch schubst; ein
#                                    Kontakt von 0,1 s bringt höchstens 0,3 N·s + Schwung – unter MAX_STOSS_NS
HAND_ZUG_M = 0.05                  # m – weiter als das zieht die Feder nie (das Ziel darf hinter der Ente liegen)
HAND_DREH_OMEGA = 30.0             # 1/s – hält die Lage der Hand (und eines gehaltenen Dings) ruhig
HAND_SOLREF = (0.01, 1.0)          # steifer Kontakt: bei 3 N dringt die Hand nur wenige mm ein
HAND_SOLIMP = (0.95, 0.99, 0.001, 0.5, 2.0)
GRIFF_SOLREF = (0.01, 1.0)         # Weld Hand ↔ Ding: fest, ohne Federn
HAND_BIT = 2                       # Kontaktbit: Hand ↔ Ente ja, Hand ↔ Objekte/Möbel/Boden nein
GREIF_REICHWEITE_M = 0.08          # Handmittelpunkt bis Objektoberfläche
# Ziehen an der Ente. Feder 60 N/m: 10 cm Zug = 6 N – die Maus muss also nur ein Stück weit ziehen, bis die volle
# Kraft wirkt, und kleine Zitterer der Maus (1–2 mm) bleiben unter 0,1 N. Gedämpft kritisch bezogen auf 0,5 kg
# (was ein Punkt an Kopf oder Rumpf etwa „wiegt“): 2·√(60·0,5) ≈ 11 N·s/m – kein Nachschwingen.
# Höchstens 6 N: über ihrer Kippkraft (am Rumpf ≈ 1,5–2 N, am Kopf weniger), also wirft kräftiges Ziehen sie um,
# aber unter ihrem Gewicht (0,737 kg · 9,81 ≈ 7,2 N) – hochreißen oder wegschleudern lässt sie sich nicht.
ZUG_K = 60.0                       # N/m
ZUG_MASSE_EFF = 0.5                # kg
ZUG_C = 2.0 * math.sqrt(ZUG_K * ZUG_MASSE_EFF)    # N·s/m
ZUG_N_MAX = 6.0                    # N
ZUG_REICHWEITE_M = 0.03            # m – so weit neben ihrer Oberfläche darf man noch anfassen
SONDE_R = 0.001                    # m – unsichtbare Messkugel: Abstand Punkt ↔ Oberfläche (mj_geomDistance)
EPISODE_HZ = 10.0
EPISODE_MAX_S = 12.0               # Stopp-Fenster 3 s + Aufstehen
RUHIG_NACH_S = 3.0                 # ohne Sturz: so lange nach dem Stoß beobachten
WACKELT_UP = 0.95                  # Rumpf-Hochachse darunter (aber kein Sturz): wackelt
MAX_LOG_BYTES = 20 * 1024 * 1024

# Wo man sie anstoßen kann → Körper in Pollens Modell
ZIELE = {"rumpf": "trunk_base", "kopf": "yaw_roll_motion", "bein_links": "leg", "bein_rechts": "leg_2"}
ZIEL_NAMEN = {"rumpf": "Rumpf", "kopf": "Kopf", "bein_links": "linkes Bein", "bein_rechts": "rechtes Bein"}

# Objekte. groesse (m) je Form – so liest es auch die Oberfläche:
#   kugel: Radius (Zahl) · wuerfel: halbe Kante (Zahl) · zylinder: [Radius, halbe Höhe] (Achse senkrecht)
#   quader: [halbe Länge x, halbe Breite y, halbe Höhe z]
# weich: eigener Kontakt (solref) – nachgiebig (Kissen) oder federnd (Wasserball)
OBJEKTE: dict[str, dict[str, Any]] = {
    "ball": {"name": "Ball", "form": "kugel", "groesse": 0.035, "masse": 0.06, "farbe": "#f0962c"},
    "wuerfel": {"name": "Würfel", "form": "wuerfel", "groesse": 0.03, "masse": 0.08, "farbe": "#4589ff"},
    "kegel": {"name": "Kegel", "form": "zylinder", "groesse": [0.025, 0.08], "masse": 0.12, "farbe": "#42be65"},
    "wasserball": {"name": "Wasserball", "form": "kugel", "groesse": 0.10, "masse": 0.05, "farbe": "#ee5396",
                   "weich": (0.02, 0.25)},
    "kissen": {"name": "Kissen", "form": "quader", "groesse": [0.08, 0.06, 0.025], "masse": 0.15, "farbe": "#f1c21b",
               "weich": (0.08, 1.0)},
    "klotz": {"name": "Klotz", "form": "quader", "groesse": [0.05, 0.03, 0.025], "masse": 0.6, "farbe": "#8d8d8d"},
}
FORMEN = ("kugel", "wuerfel", "zylinder", "quader")


def halbachsen(key: str) -> np.ndarray:
    """Halbe Ausdehnung [x, y, z] in m (ungedreht) – z ist auch die Höhe der Mitte, wenn es am Boden liegt."""
    o = OBJEKTE[key]
    g = o["groesse"]
    if o["form"] in ("kugel", "wuerfel"):
        return np.array([float(g)] * 3)
    if o["form"] == "zylinder":
        return np.array([float(g[0]), float(g[0]), float(g[1])])
    return np.array([float(v) for v in g])


def abmessungen(key: str) -> dict[str, float]:
    """Volle Maße in m, lesbar: Kugel Durchmesser, Würfel Kante, Zylinder Durchmesser/Höhe, Quader L/B/H."""
    o, h = OBJEKTE[key], halbachsen(key)
    if o["form"] == "kugel":
        return {"durchmesser": round(2 * h[0], 4)}
    if o["form"] == "wuerfel":
        return {"kante": round(2 * h[0], 4)}
    if o["form"] == "zylinder":
        return {"durchmesser": round(2 * h[0], 4), "hoehe": round(2 * h[2], 4)}
    return {"laenge": round(2 * h[0], 4), "breite": round(2 * h[1], 4), "hoehe": round(2 * h[2], 4)}


AUSGAENGE = ("steht", "wackelt", "faellt", "steht_wieder_auf")

# Ohne Zeigegerät bedienbar (Tasten): von welcher Seite der Ente, und wie stark
SEITEN = {"vorn": 0.0, "links": 90.0, "hinten": 180.0, "rechts": -90.0}      # Lage relativ zur Blickrichtung
STUFEN = {"leicht": 0.25, "mittel": 0.5, "kraeftig": 0.85}                   # Stärke 0…1
ROLL_TEMPO = {"leicht": 0.6, "mittel": 1.2, "kraeftig": 2.2}                 # m/s


def _seite(seite: Any) -> float:
    key = str(seite or "").lower().replace("ä", "ae").replace("vorne", "vorn")
    if key not in SEITEN:
        raise KollisionsFehler(f"Seite: {', '.join(SEITEN)}")
    return SEITEN[key]


def _stufe(stufe: Any, table: dict[str, float] = STUFEN) -> float:
    key = str(stufe or "").lower().replace("ä", "ae")
    if key not in table:
        raise KollisionsFehler(f"Stufe: {', '.join(table)}")
    return table[key]


ROLL_BEIWERT = 0.1                  # Rollwiderstand der Kugeln (dimensionslos, × Radius = MuJoCo-Rollreibung)


class KollisionsFehler(ValueError):
    pass


def add_objects(spec: Any) -> None:
    """Die Objekte als freie Körper ins Modell – geparkt außerhalb der Wohnung –, dazu die Hand (Mocap)."""
    G = mujoco.mjtGeom
    typ = {"kugel": G.mjGEOM_SPHERE, "wuerfel": G.mjGEOM_BOX, "zylinder": G.mjGEOM_CYLINDER, "quader": G.mjGEOM_BOX}
    for i, (key, o) in enumerate(OBJEKTE.items()):
        h = halbachsen(key)
        size = [h[0], 0, 0] if o["form"] == "kugel" else ([h[0], h[2], 0] if o["form"] == "zylinder" else list(h))
        body = spec.worldbody.add_body(name=f"obj:{key}", pos=[PARK_X + i, 0.0, h[2]])
        body.add_freejoint(name=f"obj:{key}")
        kugel = o["form"] == "kugel"
        geom = body.add_geom(name=f"o:{key}", type=typ[o["form"]], size=size, mass=float(o["masse"]))
        # Rollreibung (MuJoCo: Länge = Rollwiderstandsbeiwert · Radius). 0,1 wie ein Ball auf dem Wohnzimmerteppich:
        # aus 1 m/s rollt der Ball 0,8 m, der Wasserball 1,4 m aus (gemessen). Vorher 0,0002 m: über 7 m.
        geom.friction = [0.8, 0.005, ROLL_BEIWERT * h[0]] if kugel else [0.9, 0.005, 0.0001]
        if kugel:
            geom.condim = 6                       # Rollreibung: der Ball rollt aus, statt ewig zu gleiten
        if o.get("weich"):
            geom.solref = list(o["weich"])
            geom.solimp = [0.6, 0.95, 0.02, 0.5, 2.0]
    # Die Hand: freier Körper, schwebt (gravcomp), stößt nur an die Ente (Kontaktbit)
    hand = spec.worldbody.add_body(name="hand", pos=list(HAND_PARK), gravcomp=1.0)
    hand.add_freejoint(name="hand")
    g = hand.add_geom(name="h:hand", type=G.mjGEOM_SPHERE, size=[HAND_R, 0, 0], mass=HAND_MASSE)
    g.contype = HAND_BIT
    g.conaffinity = HAND_BIT
    g.friction = [0.3, 0.005, 0.0001]          # glatt: drückt sie schräg, rutscht sie an der Ente ab
    g.solref = list(HAND_SOLREF)
    g.solimp = list(HAND_SOLIMP)
    g.priority = 1                              # im Kontakt mit der Ente gelten die (steiferen) Werte der Hand
    # Messkugel für „wo hat man die Ente angefasst“: ohne Kontakt, unsichtbar, nur für mj_geomDistance
    sonde = spec.worldbody.add_body(name="zug_sonde", pos=list(HAND_PARK), mocap=True)
    sg = sonde.add_geom(name="z:sonde", type=G.mjGEOM_SPHERE, size=[SONDE_R, 0, 0])
    sg.contype = 0
    sg.conaffinity = 0
    sg.group = 5
    # je Ding eine Weld-Gleichung Hand ↔ Ding, aus; Greifen schaltet sie mit der Lage des Moments ein
    for key in OBJEKTE:
        eq = spec.add_equality(name=f"griff:{key}", type=mujoco.mjtEq.mjEQ_WELD, objtype=mujoco.mjtObj.mjOBJ_BODY,
                               name1="hand", name2=f"obj:{key}", active=False)
        eq.solref = list(GRIFF_SOLREF)


def _zahl(v: Any, name: str, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise KollisionsFehler(f"{name}: eine Zahl") from None
    if not math.isfinite(x):
        raise KollisionsFehler(f"{name}: eine Zahl")
    return max(lo, min(hi, x))


def _vektor(v: Any, name: str, betrag_max: float | None = None) -> np.ndarray:
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise KollisionsFehler(f"{name}: drei Zahlen [x, y, z]")
    out = np.array([_zahl(x, name, -1e3, 1e3) for x in v], np.float64)
    if betrag_max is not None:
        n = float(np.linalg.norm(out))
        if n > betrag_max:
            out *= betrag_max / n
    return out


@dataclass
class Episode:
    """Ein Stoß, Wurf oder Roll und was danach mit der Ente passiert."""

    art: str                                  # stoss | wurf | rollen | hand | zug
    reiz: dict[str, Any]
    t0: float
    vorher: dict[str, Any]
    reihe: list[list[float]] = field(default_factory=list)
    gefallen: bool = False
    aufgestanden: bool = False
    min_up: float = 1.0
    nach: dict[str, Any] | None = None
    ende: float | None = None
    _next: float = 0.0
    _v0: tuple[float, float] = (0.0, 0.0)
    dv_rumpf: list[float] | None = None
    treffer: dict[str, Any] | None = None     # Wurf/Rollen: erster Kontakt Ding ↔ Ente (Körperteil, Tempo, Impuls)

    def sample(self, t: float, tr: dict[str, float], fallen: bool, joints: list[float]) -> bool:
        """Einen Zeitpunkt aufnehmen. → True, wenn die Episode zu Ende ist."""
        rel = t - self.t0
        self.min_up = min(self.min_up, float(tr["up"]))
        if fallen:
            self.gefallen = True
        elif self.gefallen:
            self.aufgestanden = True
        if self.dv_rumpf is None and rel >= 0.15:
            # gemessene Rumpf-Geschwindigkeitsänderung in Blickrichtung der Ente (für das Stoß-Profil)
            c, s = math.cos(self.vorher["yaw"]), math.sin(self.vorher["yaw"])
            wx = tr["vx"] * math.cos(tr["yaw"]) - tr["vy"] * math.sin(tr["yaw"]) - self._v0[0]
            wy = tr["vx"] * math.sin(tr["yaw"]) + tr["vy"] * math.cos(tr["yaw"]) - self._v0[1]
            self.dv_rumpf = [round(c * wx + s * wy, 4), round(-s * wx + c * wy, 4)]
        if rel >= self._next:
            self._next += 1.0 / EPISODE_HZ
            self.reihe.append([round(rel, 2), round(tr["x"], 4), round(tr["y"], 4), round(tr["z"], 4),
                               round(tr["roll"], 4), round(tr["pitch"], 4), round(tr["yaw"], 4), round(tr["up"], 4),
                               round(tr["vx"], 4), round(tr["vy"], 4), 1.0 if fallen else 0.0,
                               *[round(float(j), 4) for j in joints]])
        done = (rel > EPISODE_MAX_S
                or (not self.gefallen and rel > RUHIG_NACH_S)
                or (self.aufgestanden and rel > 1.0 and not fallen))
        if done:
            self.nach = zustand(tr, fallen)
            self.ende = t
        return done

    @property
    def ausgang(self) -> str:
        if self.gefallen:
            return "steht_wieder_auf" if self.aufgestanden else "faellt"
        return "wackelt" if self.min_up < WACKELT_UP else "steht"

    def to_dict(self, abgebrochen: bool = False) -> dict[str, Any]:
        return {
            "version": 1, "art": self.art, "reiz": self.reiz, "zeit": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "dauer_s": round((self.ende or self.t0) - self.t0, 2), "ausgang": self.ausgang,
            "abgebrochen": abgebrochen, "min_up": round(self.min_up, 4), "dv_rumpf": self.dv_rumpf,
            "treffer": self.treffer,
            "vorher": self.vorher, "nachher": self.nach,
            "reihe_spalten": ["t", "x", "y", "z", "roll", "pitch", "yaw", "up", "vx", "vy", "liegt",
                              *[f"gelenk_{i}" for i in range(15)]],
            "reihe": self.reihe,
        }


def zustand(tr: dict[str, float], fallen: bool) -> dict[str, Any]:
    return {k: round(float(tr[k]), 4) for k in ("x", "y", "z", "roll", "pitch", "yaw", "up", "vx", "vy")} | {
        "liegt": bool(fallen)}


class EpisodenLog:
    """Episoden als JSON-Zeilen im Datenordner (eine Datei, bei 20 MB die alte als episoden-1.jsonl)."""

    def __init__(self, root: Path) -> None:
        self.dir = Path(root) / "kollision"
        self.path = self.dir / "episoden.jsonl"
        self.zaehler: dict[str, int] = {a: 0 for a in AUSGAENGE}
        self.anzahl = 0
        self._gelesen = False

    def _lesen(self) -> None:
        if self._gelesen:
            return
        self._gelesen = True
        for ep in lade_episoden(self.dir.parent):
            self.anzahl += 1
            if ep.get("ausgang") in self.zaehler:
                self.zaehler[ep["ausgang"]] += 1

    def schreiben(self, ep: dict[str, Any]) -> None:
        self._lesen()
        self.dir.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size > MAX_LOG_BYTES:
            self.path.replace(self.dir / "episoden-1.jsonl")
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ep, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.anzahl += 1
        if ep.get("ausgang") in self.zaehler:
            self.zaehler[ep["ausgang"]] += 1

    def stats(self) -> dict[str, Any]:
        self._lesen()
        return {"anzahl": self.anzahl, "ausgaenge": dict(self.zaehler), "datei": str(self.path)}


def lade_episoden(root: Path, limit: int = 5000) -> list[dict[str, Any]]:
    d = Path(root) / "kollision"
    out: list[dict[str, Any]] = []
    for p in (d / "episoden-1.jsonl", d / "episoden.jsonl"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out[-limit:]


def stossproben(root: Path, limit: int = 500, max_ms: float = 0.8) -> list[list[float]]:
    """Gemessene Rumpf-Stöße [Δv vor, Δv links] in m/s aus den Episoden – das Stoß-Profil fürs Lernen."""
    out = []
    for ep in lade_episoden(root):
        dv = ep.get("dv_rumpf")
        if isinstance(dv, list) and len(dv) == 2 and all(isinstance(v, (int, float)) for v in dv):
            n = math.hypot(dv[0], dv[1])
            if n < 0.02:
                continue
            k = min(1.0, max_ms / n)
            out.append([round(dv[0] * k, 4), round(dv[1] * k, 4)])
    return out[-limit:]


class Kollision:
    """Stöße und Objekte in einem `PhysicsCore` (mit `add_objects` gebaut)."""

    def __init__(self, core: Any, bounds: tuple[float, float] | None = None) -> None:
        self.core = core
        m = core.model
        self.bounds = bounds                    # halbe Breite/Tiefe der Wohnung (für Positionsgrenzen)
        self.ziele = {k: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, b) for k, b in ZIELE.items()}
        self.obj: dict[str, dict[str, int]] = {}
        for i, key in enumerate(OBJEKTE):
            j = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f"obj:{key}")
            b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"obj:{key}")
            if j < 0 or b < 0:
                raise KollisionsFehler("Das Physik-Modell hat keine Objekte (add_objects fehlt)")
            g = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f"o:{key}")
            eq = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_EQUALITY, f"griff:{key}")
            self.obj[key] = {"q": int(m.jnt_qposadr[j]), "v": int(m.jnt_dofadr[j]), "body": b, "park": i, "geom": g,
                             "eq": eq}
        self.held: dict[str, np.ndarray] = {}
        self.fest: dict[str, tuple[np.ndarray, np.ndarray]] = {}   # in der Luft abgestellt: Lage, Drehung
        self.draussen: set[str] = set(OBJEKTE)  # geparkt
        self._stoss: tuple[int, np.ndarray, np.ndarray, int] | None = None   # Körper, Kraft, Punkt, Teilschritte
        # Hand: freie, schwebende Kugel. Die Ente bekommt das Hand-Bit, Objekte, Möbel und Boden nicht
        hb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "hand")
        hj = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "hand")
        if hb < 0 or hj < 0:
            raise KollisionsFehler("Das Physik-Modell hat keine Hand (add_objects fehlt)")
        self.hand_body = hb
        self.hand_q, self.hand_dof = int(m.jnt_qposadr[hj]), int(m.jnt_dofadr[hj])
        self.hand_geom = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "h:hand")
        self.hand_masse = float(m.body_mass[hb])
        self.hand_traeg = float(m.body_inertia[hb][0])
        for i in core.robot_geoms:
            if m.geom_contype[i] or m.geom_conaffinity[i]:
                m.geom_conaffinity[i] |= HAND_BIT
                # MuJoCo sortiert vorab je Körper aus (body_conaffinity, beim Kompilieren gebildet) – ohne das
                # ginge die Hand durch Hüften und Beine und stieße nur am Rumpf an
                m.body_conaffinity[m.geom_bodyid[i]] |= HAND_BIT
        self._teil = {b: k for k, b in self.ziele.items()}
        self.hand_aktiv = False
        self.hand_ziel = np.array(HAND_PARK, np.float64)     # wohin der Zeiger will
        self._ziel = np.array(HAND_PARK, np.float64)         # dorthin unterwegs, höchstens HAND_MAX_MS schnell
        # gleitend von der vorigen zur neuen Zeigerposition – sonst ruckt die Hand im Takt der Nachrichten
        self._glatt = (self._ziel.copy(), self._ziel.copy(), 0.0, 0.0)   # von, nach, ab (Sim-Zeit), Dauer
        self._ziel_v = np.zeros(3)
        self._t_nachricht = -1.0
        self.hand_v = np.zeros(3)                 # geglättet (≈ 20 ms) – das Tempo beim Loslassen
        self.hand_gehalten: str | None = None
        self._griff: tuple[np.ndarray, np.ndarray] | None = None   # Lage des Dings in der Hand (für die Weld)
        self.beruehrt = False
        self._an_ente = False                     # Hand oder gehaltenes Ding berührt gerade die Ente
        self._kontakt_bis = -1.0                  # Kraftgrenze für den Kontakt gilt bis dahin (Sim-Zeit)
        self.kraft = np.zeros(3)                  # zuletzt angelegte Kraft (N), zum Nachsehen
        # Ziehen: Messkugel, Formen der Ente mit Kontakt, Jacobi-Puffer
        sb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "zug_sonde")
        self.sonde_mocap = int(m.body_mocapid[sb]) if sb >= 0 else -1
        self.sonde_geom = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "z:sonde")
        self._ente_geoms = sorted(i for i in core.robot_geoms if m.geom_contype[i] or m.geom_conaffinity[i])
        self._jacp = np.zeros((3, m.nv))
        self.zug: dict[str, Any] | None = None    # Körper, Anfasspunkt im Körper, Ziel, Kraft
        self._xfrc_bodies: set[int] = set()       # Körper der Ente, an denen Stoß oder Zug gerade ziehen
        self._park_hand()

    # ── wird vor jedem MuJoCo-Teilschritt aufgerufen ─────────────────────
    def pre_step(self) -> None:
        d = self.core.data
        # Stoß und Zug addieren sich: erst alles vom letzten Teilschritt weg, dann neu anlegen
        for b in self._xfrc_bodies:
            d.xfrc_applied[b, :] = 0.0
        self._xfrc_bodies.clear()
        if self._stoss is not None:
            body, force, point, left = self._stoss
            self._kraft_an(body, force, point)          # genau `left` Teilschritte lang (vorher einer zu wenig: −12 %)
            left -= 1
            self._stoss = (body, force, point, left) if left > 0 else None
        if self.zug is not None:
            self._zug_kraft()
        if self.hand_aktiv:
            self._hand_kraft()
        else:
            self._park_hand()
        for key, pos in self.held.items():
            o = self.obj[key]
            d.qpos[o["q"]:o["q"] + 3] = pos
            d.qvel[o["v"]:o["v"] + 6] = 0.0
        for key, (pos, quat) in self.fest.items():     # steht still in der Luft, bis man es wieder anfasst
            o = self.obj[key]
            d.qpos[o["q"]:o["q"] + 3] = pos
            d.qpos[o["q"] + 3:o["q"] + 7] = quat
            d.qvel[o["v"]:o["v"] + 6] = 0.0

    def _kraft_an(self, body: int, force: np.ndarray, point: np.ndarray) -> None:
        """Kraft an einem Punkt eines Ente-Körpers: als Kraft und Moment um seinen Schwerpunkt."""
        d = self.core.data
        d.xfrc_applied[body, :3] += force
        d.xfrc_applied[body, 3:] += np.cross(point - d.xipos[body], force)
        self._xfrc_bodies.add(body)

    # ── Ziehen (wie MuJoCo simulate / Gazebo Mouse Drag) ──────────────────
    def _zug_kraft(self) -> None:
        z = self.zug
        assert z is not None
        m, d = self.core.model, self.core.data
        b = z["body"]
        p = d.xpos[b] + d.xmat[b].reshape(3, 3) @ z["lokal"]
        mujoco.mj_jac(m, d, self._jacp, None, p, b)
        v = self._jacp @ d.qvel
        f = ZUG_K * (z["ziel"] - p) - ZUG_C * v
        n = float(np.linalg.norm(f))
        if n > ZUG_N_MAX:
            f *= ZUG_N_MAX / n
        z["anker"], z["kraft"] = p, f
        self._kraft_an(b, f, p)

    def _abstaende(self, p: np.ndarray) -> list[tuple[float, int]]:
        """Abstand des Punkts zu jeder Form der Ente (m, negativ = innen) – mit der Messkugel und mj_geomDistance."""
        m, d = self.core.model, self.core.data
        if self.sonde_mocap < 0 or self.sonde_geom < 0:
            raise KollisionsFehler("Das Physik-Modell hat keine Messkugel (add_objects fehlt)")
        d.mocap_pos[self.sonde_mocap] = p
        mujoco.mj_kinematics(m, d)
        ft = np.zeros(6)
        out = [(float(mujoco.mj_geomDistance(m, d, self.sonde_geom, g, 0.5, ft)) + SONDE_R, g)
               for g in self._ente_geoms]
        d.mocap_pos[self.sonde_mocap] = HAND_PARK
        mujoco.mj_kinematics(m, d)
        return out

    def _teil_von(self, body: int) -> str:
        m = self.core.model
        while body not in self._teil and body > 0:
            body = int(m.body_parentid[body])
        return self._teil.get(body, "rumpf")

    def zug_start(self, x: Any, y: Any, z: Any, koerper: Any = None) -> dict[str, Any]:
        """Die Ente an diesem Punkt ihrer Oberfläche anfassen (Welt, m). `koerper` (MuJoCo-Name aus der 3D-Ansicht)
        hilft, wenn der Punkt zwischen zwei Teilen liegt; sonst zählt die nächste Form."""
        m, d = self.core.model, self.core.data
        p = np.array([_zahl(x, "x", -50, 50), _zahl(y, "y", -50, 50), _zahl(z, "z", 0.0, MAX_HOEHE_M)])
        ab = self._abstaende(p)
        if not ab:
            raise KollisionsFehler("Die Ente hat keine Formen zum Anfassen")
        best = min(ab)
        if koerper is not None and str(koerper).strip():
            bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, str(koerper))
            eigene = [a for a in ab if int(m.geom_bodyid[a[1]]) == bid]
            if eigene and min(eigene)[0] <= ZUG_REICHWEITE_M:
                best = min(eigene)
        if best[0] > ZUG_REICHWEITE_M:
            raise KollisionsFehler(f"Dort ist die Ente nicht ({best[0] * 100:.0f} cm daneben) – an ihr anfassen")
        body = int(m.geom_bodyid[best[1]])
        lokal = d.xmat[body].reshape(3, 3).T @ (p - d.xpos[body])
        self.zug = {"body": body, "lokal": lokal, "ziel": p.copy(), "anker": p.copy(), "kraft": np.zeros(3)}
        return self.zug_info() or {}

    def zug_ziel(self, x: Any, y: Any, z: Any) -> dict[str, Any]:
        """Wohin am Anfasspunkt gezogen wird (Welt, m). Das Ziel darf springen – die Kraft ist gedeckelt."""
        if self.zug is None:
            raise KollisionsFehler("Erst die Ente anfassen")
        self.zug["ziel"] = np.array([_zahl(x, "x", -50, 50), _zahl(y, "y", -50, 50), _zahl(z, "z", 0.0, MAX_HOEHE_M)])
        return self.zug_info() or {}

    def zug_ende(self) -> dict[str, Any]:
        self.zug = None
        d = self.core.data
        for b in self._xfrc_bodies:
            d.xfrc_applied[b, :] = 0.0
        self._xfrc_bodies.clear()
        return {"zug": None}

    def zug_info(self) -> dict[str, Any] | None:
        z = self.zug
        if z is None:
            return None
        teil = self._teil_von(z["body"])
        return {"aktiv": True, "koerper": mujoco.mj_id2name(self.core.model, mujoco.mjtObj.mjOBJ_BODY, z["body"]),
                "teil": teil, "teil_name": ZIEL_NAMEN[teil],
                "anker": [round(float(v), 4) for v in z["anker"]], "ziel": [round(float(v), 4) for v in z["ziel"]],
                "kraft_n": round(float(np.linalg.norm(z["kraft"])), 3)}

    # ── Anstoßen ─────────────────────────────────────────────────────────
    def stoss(self, ziel: str = "rumpf", staerke: float = 0.5, richtung_grad: float | None = 0.0,
              hoehe: float = 0.0, vektor: Any = None, punkt: Any = None, seite: Any = None,
              stufe: Any = None) -> dict[str, Any]:
        """Kraftstoß. richtung_grad: wohin der Stoß schiebt, relativ zur Blickrichtung (0 vor, 90 links, 180
        zurück, −90 rechts). Statt dessen geht `vektor` (Weltkoordinaten). hoehe −1…1: tiefer/höher am Körper.
        Für Tasten: `seite` (vorn/hinten/links/rechts = von wo die Hand kommt) und `stufe` (leicht/mittel/kraeftig)."""
        if seite is not None:
            richtung_grad = _seite(seite) + 180.0       # von links gestoßen → schiebt nach rechts
        if stufe is not None:
            staerke = _stufe(stufe)
        if ziel not in self.ziele:
            raise KollisionsFehler(f"Ziel: {', '.join(ZIELE)}")
        if self._stoss is not None:
            raise KollisionsFehler("Ein Stoß läuft noch – kurz warten")
        st = _zahl(staerke, "Stärke", 0.0, 1.0)
        impuls = st * MAX_STOSS_NS
        d = self.core.data
        body = self.ziele[ziel]
        if vektor is not None:
            v = _vektor(vektor, "Richtung")
            n = float(np.linalg.norm(v))
            if n < 1e-6:
                raise KollisionsFehler("Richtung: nicht null")
            richt = v / n
        else:
            tr = self.core.trunk()
            a = tr["yaw"] + math.radians(_zahl(richtung_grad or 0.0, "Richtung", -360, 360))
            richt = np.array([math.cos(a), math.sin(a), 0.0])
        if punkt is not None:
            p = _vektor(punkt, "Punkt")
            if float(np.linalg.norm(p - d.xipos[body])) > 0.25:
                raise KollisionsFehler("Punkt: zu weit weg von der Ente")
        else:
            p = d.xipos[body].copy()
            p[2] += _zahl(hoehe, "Höhe", -1.0, 1.0) * 0.04
        steps = max(1, round(STOSS_DAUER_S / self.core.model.opt.timestep))
        force = richt * (impuls / (steps * self.core.model.opt.timestep))
        self._stoss = (body, force, np.asarray(p, np.float64), steps)
        return {"ziel": ziel, "staerke": round(st, 3), "impuls_ns": round(impuls, 3),
                "richtung": [round(float(x), 3) for x in richt], "punkt": [round(float(x), 3) for x in p]}

    # ── Objekte ──────────────────────────────────────────────────────────
    def _key(self, name: Any) -> str:
        key = str(name or "").lower().replace("ü", "ue")
        if key not in self.obj:
            raise KollisionsFehler(f"Objekt: {', '.join(OBJEKTE)}")
        return key

    def _clamp_pos(self, key: str, pos: np.ndarray) -> np.ndarray:
        h = halbachsen(key)
        g, rand = float(h[2]), float(max(h[0], h[1]))
        out = np.asarray(pos, np.float64).copy()
        if self.bounds is not None:
            hx, hy = self.bounds
            out[0] = max(-hx + rand, min(hx - rand, out[0]))
            out[1] = max(-hy + rand, min(hy - rand, out[1]))
        out[2] = max(g, min(MAX_HOEHE_M, out[2]))
        return out

    def _set(self, key: str, pos: np.ndarray, vel: np.ndarray | None = None, spin: np.ndarray | None = None,
             quat: Any = None) -> None:
        o = self.obj[key]
        d = self.core.data
        d.qpos[o["q"]:o["q"] + 3] = pos
        d.qpos[o["q"] + 3:o["q"] + 7] = [1.0, 0.0, 0.0, 0.0] if quat is None else quat
        d.qvel[o["v"]:o["v"] + 6] = 0.0
        if vel is not None:
            d.qvel[o["v"]:o["v"] + 3] = vel
        if spin is not None:
            d.qvel[o["v"] + 3:o["v"] + 6] = spin
        self.draussen.discard(key)
        mujoco.mj_forward(self.core.model, d)

    def _vor_der_ente(self, key: str, abstand: float = 0.35, hoehe: float | None = None) -> np.ndarray:
        tr = self.core.trunk()
        g = float(halbachsen(key)[2])
        return np.array([tr["x"] + abstand * math.cos(tr["yaw"]), tr["y"] + abstand * math.sin(tr["yaw"]),
                         g if hoehe is None else hoehe])

    def setzen(self, name: Any, pos: Any = None) -> dict[str, Any]:
        """Hinstellen. pos [x, y] stellt es auf den Boden (z = halbe Höhe), [x, y, z] dorthin."""
        key = self._key(name)
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            pos = [pos[0], pos[1], float(halbachsen(key)[2])]
        p = self._clamp_pos(key, _vektor(pos, "Position") if pos is not None else self._vor_der_ente(key))
        self._frei(key)
        self._set(key, p)
        return self.objekt(key)

    def _frei(self, key: str) -> None:
        """Aus jeder Hand nehmen (HTTP-Halten oder Maus-Hand) und nicht mehr in der Luft festhalten."""
        self.held.pop(key, None)
        self.fest.pop(key, None)
        if self.hand_gehalten == key:
            self._griff_aus()

    def halten(self, name: Any, pos: Any = None) -> dict[str, Any]:
        """Greifen und bewegen: das Objekt folgt der Hand, ohne zu fallen."""
        key = self._key(name)
        if pos is None:
            cur = self.objekt(key)["pos"] if key not in self.draussen else None
            base = np.array(cur) if cur else self._vor_der_ente(key, hoehe=GREIF_HOEHE_M)
            base[2] = max(base[2], GREIF_HOEHE_M)
            p = base
        else:
            p = _vektor(pos, "Position")
        p = self._clamp_pos(key, p)
        self._frei(key)
        self.draussen.discard(key)
        self.held[key] = p
        self._set(key, p)
        return self.objekt(key)

    def loslassen(self, name: Any, geschwindigkeit: Any = None) -> dict[str, Any]:
        key = self._key(name)
        if self.hand_gehalten == key and geschwindigkeit is None:
            return self.hand_loslassen()
        if self.hand_gehalten == key:
            self._griff_aus()
        pos = self.held.pop(key, None)
        if pos is None:
            pos = np.array(self.objekt(key)["pos"])
        vel = _vektor(geschwindigkeit, "Geschwindigkeit", MAX_WURF_MS) if geschwindigkeit is not None else None
        self._set(key, self._clamp_pos(key, pos), vel)
        return self.objekt(key)

    def _seitlich(self, key: str, seite: Any, abstand: float, hoehe: float | None) -> np.ndarray:
        tr = self.core.trunk()
        a = tr["yaw"] + math.radians(_seite(seite))
        g = float(halbachsen(key)[2])
        return np.array([tr["x"] + abstand * math.cos(a), tr["y"] + abstand * math.sin(a), g if hoehe is None else hoehe])

    def werfen(self, name: Any, von: Any = None, geschwindigkeit: Any = None, staerke: float = 0.5,
               ziel: str | None = None, seite: Any = None, stufe: Any = None) -> dict[str, Any]:
        """Werfen: mit `geschwindigkeit` [vx, vy, vz] (m/s) oder auf die Ente (`ziel="ente"`, Stärke 0…1).
        Für Tasten: `seite` (von wo, 0,6 m neben ihr) und `stufe` – dann immer auf die Ente."""
        key = self._key(name)
        if stufe is not None:
            staerke = _stufe(stufe)
        if seite is not None:
            von, ziel = None, "ente"
            start = self._clamp_pos(key, self._seitlich(key, seite, 0.6, GREIF_HOEHE_M))
        else:
            start = self._clamp_pos(key, _vektor(von, "Start") if von is not None
                                    else self._vor_der_ente(key, 0.6, GREIF_HOEHE_M))
        if geschwindigkeit is not None:
            vel = _vektor(geschwindigkeit, "Geschwindigkeit", MAX_WURF_MS)
        elif ziel == "ente":
            vel = self._ballistisch(start, _zahl(staerke, "Stärke", 0.0, 1.0))
        else:
            raise KollisionsFehler("Werfen: Geschwindigkeit oder ziel=ente angeben")
        self._frei(key)
        self._set(key, start, vel)
        return {**self.objekt(key), "geschwindigkeit": [round(float(v), 3) for v in vel]}

    def _ballistisch(self, start: np.ndarray, staerke: float) -> np.ndarray:
        """Bogen von start auf die Brust der Ente; Stärke wählt das Tempo (1,5 … 6 m/s)."""
        d = self.core.data
        target = d.xipos[self.ziele["rumpf"]].copy()
        delta = target - start
        horiz = math.hypot(delta[0], delta[1])
        speed = 1.5 + 4.5 * staerke
        t = max(0.08, horiz / max(0.5, speed * 0.9))
        g = 9.81
        vz = (delta[2] + 0.5 * g * t * t) / t
        vh = horiz / t
        dirx, diry = (delta[0] / horiz, delta[1] / horiz) if horiz > 1e-6 else (1.0, 0.0)
        vel = np.array([dirx * vh, diry * vh, vz])
        n = float(np.linalg.norm(vel))
        return vel * (MAX_WURF_MS / n) if n > MAX_WURF_MS else vel

    def rollen(self, name: Any, von: Any = None, tempo: float = 1.0, richtung_grad: float | None = None,
               ziel: str | None = "ente", seite: Any = None, stufe: Any = None) -> dict[str, Any]:
        """Am Boden anschubsen: auf die Ente zu (Standard) oder in eine Richtung (Grad in der Welt).
        Für Tasten: `seite` (von wo, 0,6 m neben ihr, rollt auf sie zu) und `stufe` (leicht/mittel/kraeftig)."""
        key = self._key(name)
        g = float(halbachsen(key)[2])
        if stufe is not None:
            tempo = _stufe(stufe, ROLL_TEMPO)
        if seite is not None:
            start, richtung_grad, ziel = self._seitlich(key, seite, 0.6, None), None, "ente"
        else:
            start = _vektor(von, "Start") if von is not None else self._vor_der_ente(key, 0.6)
        start[2] = g
        start = self._clamp_pos(key, start)
        v = _zahl(tempo, "Tempo", 0.05, MAX_ROLL_MS)
        if richtung_grad is not None:
            a = math.radians(_zahl(richtung_grad, "Richtung", -360, 360))
            dx, dy = math.cos(a), math.sin(a)
        elif ziel == "ente":
            tr = self.core.trunk()
            dx, dy = tr["x"] - start[0], tr["y"] - start[1]
            n = math.hypot(dx, dy) or 1.0
            dx, dy = dx / n, dy / n
        else:
            raise KollisionsFehler("Rollen: Richtung oder ziel=ente angeben")
        vel = np.array([dx * v, dy * v, 0.0])
        spin = np.array([-dy * v / g, dx * v / g, 0.0]) if OBJEKTE[key]["form"] == "kugel" else None
        self._frei(key)
        self._set(key, start, vel, spin)
        return {**self.objekt(key), "geschwindigkeit": [round(float(x), 3) for x in vel]}

    def fallen_lassen(self, name: Any = None) -> list[str]:
        """In der Luft abgestellte Dinge wieder der Schwerkraft überlassen – eines (`name`) oder alle (seit 0.33).
        Sie fallen aus der Ruhe senkrecht nach unten. Gibt die Namen der fallenden Dinge zurück."""
        keys = [self._key(name)] if name not in (None, "", "alle") else list(self.fest)
        gefallen = []
        for key in keys:
            if self.fest.pop(key, None) is not None:
                gefallen.append(key)
        return gefallen

    def parken(self, name: Any = None) -> None:
        keys = [self._key(name)] if name is not None else list(self.obj)
        if name is None:
            self.hand_aus()
            self.zug_ende()
        for key in keys:
            self._frei(key)
            self._set(key, np.array([PARK_X + self.obj[key]["park"], 0.0, float(halbachsen(key)[2])]))
            self.draussen.add(key)

    # ── Hand (Maus/Finger) ───────────────────────────────────────────────
    @property
    def hand_pos(self) -> np.ndarray:
        return self.core.data.qpos[self.hand_q:self.hand_q + 3].copy()

    def _glatt_jetzt(self, t: float) -> np.ndarray:
        """Wo der Zeiger gerade ist: gleitend zwischen den letzten beiden Nachrichten."""
        von, nach, ab, dauer = self._glatt
        a = 1.0 if dauer <= 0 else min(1.0, max(0.0, (t - ab) / dauer))
        return von + (nach - von) * a

    def _park_hand(self) -> None:
        d = self.core.data
        d.qpos[self.hand_q:self.hand_q + 3] = HAND_PARK
        d.qpos[self.hand_q + 3:self.hand_q + 7] = [1.0, 0.0, 0.0, 0.0]
        d.qvel[self.hand_dof:self.hand_dof + 6] = 0.0
        d.xfrc_applied[self.hand_body, :] = 0.0

    def _ente_beruehrt(self) -> bool:
        """Berühren Hand oder gehaltenes Ding gerade die Ente (Kontakte des letzten Teilschritts)?"""
        d = self.core.data
        mine = {self.hand_geom}
        if self.hand_gehalten is not None:
            mine.add(self.obj[self.hand_gehalten]["geom"])
        robot = self.core.robot_geoms
        for i in range(d.ncon):
            a, b = int(d.contact[i].geom1), int(d.contact[i].geom2)
            if (a in mine and b in robot) or (b in mine and a in robot):
                return True
        return False

    def _hand_kraft(self) -> None:
        """Je Teilschritt: Ziel mit höchstens HAND_MAX_MS nachziehen, dann Feder-Dämpfer-Kraft auf die Hand.
        Gerechnet als Beschleunigung (ω² · Abstand + 2ω · Tempo-Unterschied, kritisch gedämpft) mal der Masse von
        Hand und gehaltenem Ding – so folgt ein schwerer Klotz so flink wie die leere Hand. Gedeckelt: frei auf
        HAND_A_MAX, an der Ente auf HAND_KRAFT_N. Dazu eine Drehfeder, die die Lage hält."""
        m, d = self.core.model, self.core.data
        dt = float(m.opt.timestep)
        delta = self._glatt_jetzt(float(d.time)) - self._ziel
        n = float(np.linalg.norm(delta))
        # Wunschtempo: höchstens HAND_MAX_MS, und so, dass es vor dem Ziel noch bremsen kann
        # (gebremst wird mit der halben Grenze – so reicht es trotz der 5-ms-Schritte, ohne übers Ziel zu schießen)
        soll = np.zeros(3) if n < 1e-6 else delta / n * min(HAND_MAX_MS, math.sqrt(HAND_A_ZIEL * n), n / dt)
        dv = soll - self._ziel_v
        dn = float(np.linalg.norm(dv))
        if dn > HAND_A_ZIEL * dt:
            dv *= HAND_A_ZIEL * dt / dn
        self._ziel_v = self._ziel_v + dv
        a_ziel = dv / dt                                     # Vorsteuerung: so folgt die Hand ohne Überschwingen
        v_ziel = self._ziel_v.copy()
        self._ziel = self._ziel + v_ziel * dt
        pos = d.qpos[self.hand_q:self.hand_q + 3]
        vel = d.qvel[self.hand_dof:self.hand_dof + 3].copy()
        fehler = self._ziel - pos
        n = float(np.linalg.norm(fehler))
        if n > HAND_ZUG_M:
            fehler *= HAND_ZUG_M / n
        masse, traeg = self.hand_masse, self.hand_traeg
        if self.hand_gehalten is not None and self._griff is not None:
            ob = self.obj[self.hand_gehalten]["body"]
            masse += float(m.body_mass[ob])
            traeg += float(np.max(m.body_inertia[ob])) + float(m.body_mass[ob]) * float(np.dot(self._griff[0], self._griff[0]))
        w = HAND_OMEGA
        f = masse * (a_ziel + w * w * fehler + 2.0 * w * (v_ziel - vel))
        if self._ente_beruehrt():
            self._kontakt_bis = float(d.time) + HAND_KONTAKT_HALTEN_S
        self._an_ente = float(d.time) <= self._kontakt_bis
        cap = HAND_KRAFT_N if self._an_ente else min(masse * HAND_A_MAX, HAND_KRAFT_FREI_N)
        fn = float(np.linalg.norm(f))
        if fn > cap:
            f *= cap / fn
        # Lage halten: Drehwinkel aus dem Quaternion, Winkeltempo im Körper-Rahmen → Welt
        q = d.qpos[self.hand_q + 3:self.hand_q + 7]
        rot = np.zeros(3)
        mujoco.mju_quat2Vel(rot, q, 1.0)                     # Achse · Winkel (Körper-Rahmen)
        omega_b = d.qvel[self.hand_dof + 3:self.hand_dof + 6]
        wr = HAND_DREH_OMEGA
        tau_b = -traeg * (wr * wr * rot + 2.0 * wr * omega_b)
        tau = np.zeros(3)
        mujoco.mju_rotVecQuat(tau, tau_b, q)
        d.xfrc_applied[self.hand_body, :3] = f
        d.xfrc_applied[self.hand_body, 3:] = tau
        self.kraft = f
        self.hand_v += 0.25 * (vel - self.hand_v)

    def hand(self, x: Any, y: Any, z: Any) -> dict[str, Any]:
        """Wohin die Hand soll (Welt, m). Sie folgt mit höchstens HAND_MAX_MS. Ist sie aus, erscheint sie dort –
        nur wenn sie dort in der Ente stecken würde, so weit darüber, dass sie frei ist."""
        p = np.array([_zahl(x, "x", -50, 50), _zahl(y, "y", -50, 50), _zahl(z, "z", HAND_R, MAX_HOEHE_M)])
        if self.bounds is not None:
            hx, hy = self.bounds
            p[0], p[1] = max(-hx, min(hx, p[0])), max(-hy, min(hy, p[1]))
        self.hand_ziel = p
        now = float(self.core.data.time)
        seit = now - self._t_nachricht
        if self.hand_aktiv and 0.0 < seit <= 2 * HAND_GLATT_MAX_S:
            # über den Abstand zweier Nachrichten gleiten: kostet so viel Verzug, wie Nachrichten auseinander liegen
            self._glatt = (self._glatt_jetzt(now), p.copy(), now, min(seit, HAND_GLATT_MAX_S))
        else:
            self._glatt = (p.copy(), p.copy(), now, 0.0)
        self._t_nachricht = now
        if not self.hand_aktiv:
            start = self._frei_ueber(p)
            d = self.core.data
            d.qpos[self.hand_q:self.hand_q + 3] = start
            d.qpos[self.hand_q + 3:self.hand_q + 7] = [1.0, 0.0, 0.0, 0.0]
            d.qvel[self.hand_dof:self.hand_dof + 6] = 0.0
            self._ziel = start.copy()
            self._ziel_v = np.zeros(3)
            self._glatt = (p.copy(), p.copy(), now, 0.0)
            self.hand_v[:] = 0.0
            self.hand_aktiv = True
            mujoco.mj_forward(self.core.model, d)
        return self.hand_info()

    def _frei_ueber(self, p: np.ndarray) -> np.ndarray:
        """Startpunkt der Hand: p selbst, außer die Handkugel würde dort in der Ente stecken – dann in 2-cm-Schritten
        höher, bis sie frei ist (höchstens 0,3 m). Früher galt pauschal „unter 0,2 m vom Rumpf → 0,3 m höher“; damit
        ließ sich ein Ding direkt neben der Ente nicht greifen (die Hand erschien 28 cm darüber)."""
        start = p.copy()
        try:
            for _ in range(16):
                if min(dist for dist, _g in self._abstaende(start)) >= HAND_R + 0.005:
                    return start
                start[2] = min(MAX_HOEHE_M, start[2] + 0.02)
            return start
        except KollisionsFehler:                     # Modell ohne Messkugel: die alte, grobe Regel
            if float(np.linalg.norm(p - self.core.data.xipos[self.ziele["rumpf"]])) < 0.2:
                start[2] = min(MAX_HOEHE_M, p[2] + 0.3)
            return start

    def hand_aus(self) -> dict[str, Any]:
        if self.hand_gehalten is not None:
            self.hand_loslassen()
        self._griff_aus()
        self.hand_aktiv = False
        self.beruehrt = self._an_ente = False
        self.hand_ziel = np.array(HAND_PARK, np.float64)
        self._ziel = self.hand_ziel.copy()
        self._ziel_v = np.zeros(3)
        self._park_hand()
        self.hand_v[:] = 0.0
        mujoco.mj_forward(self.core.model, self.core.data)
        return self.hand_info()

    def _griff_aus(self) -> None:
        """Alle Griffe lösen (Weld aus, Schwerkraft wieder an) – auch nach einem Zurücksetzen der Physik."""
        m, d = self.core.model, self.core.data
        for o in self.obj.values():
            if o["eq"] >= 0:
                d.eq_active[o["eq"]] = 0
            m.body_gravcomp[o["body"]] = 0.0
        self.hand_gehalten, self._griff = None, None

    def abstand(self, key: str, p: Any) -> float:
        """Abstand eines Punkts zur Oberfläche des Objekts (m, 0 = innen)."""
        d = self.core.data
        g = self.obj[key]["geom"]
        loc = d.geom_xmat[g].reshape(3, 3).T @ (np.asarray(p, np.float64) - d.geom_xpos[g])
        h = halbachsen(key)
        form = OBJEKTE[key]["form"]
        if form == "kugel":
            return max(0.0, float(np.linalg.norm(loc)) - h[0])
        if form == "zylinder":
            return float(math.hypot(max(0.0, math.hypot(loc[0], loc[1]) - h[0]), max(0.0, abs(loc[2]) - h[2])))
        return float(np.linalg.norm(np.maximum(np.abs(loc) - h, 0.0)))

    def greifen(self, name: Any = None) -> dict[str, Any]:
        """Das Objekt an der Hand nehmen (ohne Namen: das nächste). Nur bis GREIF_REICHWEITE_M von der Oberfläche."""
        if not self.hand_aktiv:
            raise KollisionsFehler("Erst die Hand in den Raum bewegen")
        hp = self.hand_pos
        if name is not None and str(name).strip():
            key = self._key(name)
            if key in self.draussen:
                raise KollisionsFehler(f"{OBJEKTE[key]['name']} liegt nicht im Raum")
            dist = self.abstand(key, hp)
            if dist > GREIF_REICHWEITE_M:
                raise KollisionsFehler(f"{OBJEKTE[key]['name']} ist {dist:.2f} m von der Hand weg – greifen geht "
                                       f"bis {GREIF_REICHWEITE_M:.2f} m")
        else:
            nah = sorted((self.abstand(k, hp), k) for k in self.obj if k not in self.draussen)
            if not nah or nah[0][0] > GREIF_REICHWEITE_M:
                raise KollisionsFehler(f"Nichts in Reichweite der Hand (bis {GREIF_REICHWEITE_M:.2f} m)")
            key = nah[0][1]
        if self.hand_gehalten not in (None, key):
            self.hand_loslassen()
        self.held.pop(key, None)
        self.fest.pop(key, None)                       # in der Luft abgestellt: Anfassen löst es wieder
        o = self.obj[key]
        m, d = self.core.model, self.core.data
        mujoco.mj_forward(m, d)
        # Lage des Dings im Rahmen der Hand – genau so hält die Weld es fest (kein Ruck beim Greifen)
        hq = d.xquat[self.hand_body]
        inv = np.zeros(4)
        mujoco.mju_negQuat(inv, hq)
        rel_p = np.zeros(3)
        mujoco.mju_rotVecQuat(rel_p, d.xpos[o["body"]] - d.xpos[self.hand_body], inv)
        rel_q = np.zeros(4)
        mujoco.mju_mulQuat(rel_q, inv, d.xquat[o["body"]])
        m.eq_data[o["eq"], :] = 0.0
        m.eq_data[o["eq"], 3:6] = rel_p
        m.eq_data[o["eq"], 6:10] = rel_q
        m.eq_data[o["eq"], 10] = 1.0                         # Drehmoment voll übertragen
        m.body_gravcomp[o["body"]] = 1.0                     # in der Hand fällt es nicht
        d.eq_active[o["eq"]] = 1
        d.qvel[o["v"]:o["v"] + 6] = 0.0
        self._griff = (rel_p, rel_q)
        self.hand_gehalten = key
        return self.objekt(key)

    def hand_loslassen(self, v: Any = None, fest: bool = False) -> dict[str, Any]:
        """Loslassen. Mit `v` [vx, vy, vz] (m/s, Welt) fliegt es genau so los – die Oberfläche rechnet v aus
        Wurfbewegung und Kamera und zeigt den Bogen vorher –, sonst mit dem Tempo der Hand. Höchstens MAX_WURF_MS,
        ohne Drall, ohne Luftreibung. Mit `fest` bleibt es genau dort in der Luft stehen (wie ein abgestelltes Teil
        im CAD) – die Ente kann dagegen laufen –, bis man es wieder anfasst oder wegräumt."""
        key = self.hand_gehalten
        if key is None:
            raise KollisionsFehler("Die Hand hält nichts")
        vel = _vektor(v, "Wurf", MAX_WURF_MS) if v is not None else self.hand_v.copy()
        n = float(np.linalg.norm(vel))
        if n > MAX_WURF_MS:
            vel *= MAX_WURF_MS / n
        o = self.obj[key]
        d = self.core.data
        pos = self._clamp_pos(key, d.qpos[o["q"]:o["q"] + 3].copy())
        quat = d.qpos[o["q"] + 3:o["q"] + 7].copy()
        self._griff_aus()
        if fest:
            self.fest[key] = (pos, quat)
            self._set(key, pos, np.zeros(3), quat=quat)
            return {**self.objekt(key), "geschwindigkeit": [0.0, 0.0, 0.0]}
        self._set(key, pos, vel, quat=quat)
        return {**self.objekt(key), "geschwindigkeit": [round(float(x), 3) for x in vel]}

    def hand_kontakt(self) -> dict[str, Any] | None:
        """Berührt die Hand (oder was sie hält) gerade die Ente? → Punkt, Körperteil – oder None."""
        if not self.hand_aktiv:
            self.beruehrt = False
            return None
        d, m = self.core.data, self.core.model
        mine = {self.hand_geom: None}
        if self.hand_gehalten is not None:
            mine[self.obj[self.hand_gehalten]["geom"]] = self.hand_gehalten
        robot = self.core.robot_geoms
        best = None
        for i in range(d.ncon):
            c = d.contact[i]
            a, b = int(c.geom1), int(c.geom2)
            for h, other in ((a, b), (b, a)):
                if h in mine and other in robot and c.dist <= 0.001 and (best is None or c.dist < best[0]):   # echt berührt, nicht nur nah
                    best = (float(c.dist), c.pos.copy(), other, mine[h])
        self.beruehrt = best is not None
        if best is None:
            return None
        body = int(m.geom_bodyid[best[2]])
        teil = self._teil_von(body)
        return {"punkt": [round(float(x), 4) for x in best[1]], "koerperteil": teil, "koerperteil_name": ZIEL_NAMEN[teil],
                "mit": best[3]}

    def objekt_kontakt(self, key: str) -> dict[str, Any] | None:
        """Berührt das Ding gerade die Ente? → Körperteil, Punkt, Tempo und Impuls (Masse · Tempo) – oder None.
        Für Wurf-/Roll-Episoden: wo und wie fest getroffen wurde (das Trainingssignal hinter dem Stoß)."""
        if key not in self.obj or key in self.draussen:
            return None
        d, m = self.core.data, self.core.model
        o = self.obj[key]
        robot = self.core.robot_geoms
        for i in range(d.ncon):
            c = d.contact[i]
            a, b = int(c.geom1), int(c.geom2)
            other = b if a == o["geom"] else a if b == o["geom"] else None
            if other is None or other not in robot or c.dist > 0.001:
                continue
            tempo = float(np.linalg.norm(d.qvel[o["v"]:o["v"] + 3]))
            teil = self._teil_von(int(m.geom_bodyid[other]))
            return {"koerperteil": teil, "koerperteil_name": ZIEL_NAMEN[teil],
                    "punkt": [round(float(x), 4) for x in c.pos], "tempo_ms": round(tempo, 3),
                    "impuls_ns": round(float(OBJEKTE[key]["masse"]) * tempo, 4)}
        return None

    def hand_info(self) -> dict[str, Any]:
        return {"pos": [round(float(x), 4) for x in self.hand_pos], "aktiv": self.hand_aktiv,
                "ziel": [round(float(x), 4) for x in (self.hand_ziel if self.hand_aktiv else self.hand_pos)],
                "gehalten": self.hand_gehalten, "beruehrt": bool(self.beruehrt),
                "tempo": round(float(np.linalg.norm(self.hand_v)), 3)}

    # ── Auslesen ─────────────────────────────────────────────────────────
    def objekt(self, key: str) -> dict[str, Any]:
        o = self.obj[key]
        d = self.core.data
        q = d.qpos[o["q"]:o["q"] + 7]
        v = d.qvel[o["v"]:o["v"] + 3]
        meta = OBJEKTE[key]
        return {"id": key, "name": meta["name"], "form": meta["form"], "groesse": meta["groesse"],
                "halbachsen": [round(float(x), 4) for x in halbachsen(key)], "abmessungen": abmessungen(key),
                "masse": meta["masse"], "weich": bool(meta.get("weich")),
                "farbe": meta["farbe"], "im_raum": key not in self.draussen,
                "pos": [round(float(x), 4) for x in q[:3]], "quat": [round(float(x), 4) for x in q[3:7]],
                "tempo": round(float(np.linalg.norm(v)), 3), "gehalten": key in self.held or key == self.hand_gehalten,
                "in_der_hand": key == self.hand_gehalten, "fest": key in self.fest}

    def objekte(self) -> list[dict[str, Any]]:
        return [self.objekt(k) for k in self.obj]

    def bewegt(self) -> bool:
        d = self.core.data
        return bool(self.held) or self.hand_gehalten is not None or self._stoss is not None or self.zug is not None or any(
            float(np.linalg.norm(d.qvel[o["v"]:o["v"] + 3])) > 0.01 for k, o in self.obj.items() if k not in self.draussen and k not in self.fest)


def grenzen() -> dict[str, Any]:
    return {"stoss_ns_max": MAX_STOSS_NS, "stoss_dauer_s": STOSS_DAUER_S, "wurf_ms_max": MAX_WURF_MS,
            "roll_ms_max": MAX_ROLL_MS, "hoehe_m_max": MAX_HOEHE_M, "ziele": ZIEL_NAMEN,
            "seiten": list(SEITEN), "stufen": STUFEN, "roll_tempo": ROLL_TEMPO, "formen": list(FORMEN),
            "hand": {"radius_m": HAND_R, "tempo_ms_max": HAND_MAX_MS, "greif_reichweite_m": GREIF_REICHWEITE_M,
                     "kraft_n_max": HAND_KRAFT_N, "zeitkonstante_s": round(1.0 / HAND_OMEGA, 4)},
            "zug": {"kraft_n_max": ZUG_N_MAX, "steifigkeit_n_m": ZUG_K, "daempfung_ns_m": round(ZUG_C, 2),
                    "reichweite_m": ZUG_REICHWEITE_M},
            "objekte": {k: {**{kk: v[kk] for kk in ("name", "form", "groesse", "masse", "farbe")},
                            "halbachsen": [float(x) for x in halbachsen(k)], "abmessungen": abmessungen(k),
                            "weich": bool(v.get("weich"))} for k, v in OBJEKTE.items()}}
