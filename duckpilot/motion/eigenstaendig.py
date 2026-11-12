"""Eigenständiges Verhalten (Wunsch des Maintainers 5.11.): Kommt eine Weile nichts vom Menschen, sucht sich die Verkörperung
selbst eine Beschäftigung – passend zu ihrem Charakter und zu dem, was ihr Körper kann.

Hier steht nur die Entscheidung (Motorik, ohne Gehirn und ohne bestimmten Körper):

- `initiative()` – Regler „Von sich aus beschäftigen“ 0 … 1 (seit 0.38.44 stufenlos; alte Stufen werden umgerechnet),
- `wartezeit()` – wie lange Ruhe sein muss (ruhig ≈ 4–6 min, lebhaft ≈ 1–2 min bei „ab und zu“; höher = kürzer),
- `angebot()` – was der Körper anbieten kann, gewichtet nach Charakter (Energie, Humor, Eigenschaften der Gestalt),
- `waehlen()` – gewichteter Zufall, nicht zweimal dasselbe hintereinander,
- `sperre()` – alle Sicherheitsregeln, die eine eigene Beschäftigung verbieten,
- `Eigenstaendig` – die Uhr: Ruhe zählen, bei jeder Sperre oder jedem Kontakt von vorn.

Ausgeführt wird in der Laufzeit (`server/runtime_eigenstaendig.py`) über dieselben Werkzeuge wie für die KI – also
mit `fehlt_dem_koerper` und allen Prüfungen dort. Was dabei startet, trägt `eigenstaendig = True` (über `EIGEN`), damit
jeder Befehl, jedes Ansprechen und der Not-Aus es sofort beenden (`MotionEngine.eigenstaendig_unterbrechen`).

Sicherheit (nie aufweichen): nichts während der Not-Aus-Sperre, nie „still bis angesprochen“, nie in Ruhe, nie
hochgehoben oder gefallen, nie während etwas läuft, gespielt, getanzt oder gesprochen wird. Am echten Roboter keine
Ortsbewegung von selbst – nur Gesten, Kopf und Antennen (`ort=True` gibt es nur im Simulator; die Engine prüft das
beim Start eines Verhaltens noch einmal).
"""

from __future__ import annotations

import contextvars
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..settings import INITIATIVE_STUFEN

HAEUFIGKEIT = ("aus", "ab_und_zu", "oft")
# Bis 0.38.43 gab es drei Stufen; seit 0.38.44 ein stufenloser Regler (Wunsch des Maintainers: „feinerer Regler“)
STUFEN = INITIATIVE_STUFEN
STANDARD = 0.4
AUS_BIS = 0.02
# Gesetzt, während die Laufzeit eine eigene Beschäftigung startet: Die Engine markiert alles, was dabei anläuft
EIGEN: contextvars.ContextVar[bool] = contextvars.ContextVar("eigenstaendig", default=False)

# Pollens Gefühle der Microduck (mit aufgenommenem Ton), nach Laune
POLLEN_VERSPIELT = ("lachen", "naeaeae", "aufgeregt", "was_was", "jep")
POLLEN_RUHIG = ("hmm", "jawohl", "jep")
# Pollens Reachy-Bibliothek: Stämme der Aufnahmen
REACHY_RUHIG = ("attentive", "curious", "serenity", "thoughtful", "inquiring", "calming")
REACHY_VERSPIELT = ("cheerful", "curious", "amazed", "enthusiastic", "laughing", "inquiring")
DINGE_NICHT = ("möbel", "laser", "person")


def ist_eigen(behavior: Any) -> bool:
    return bool(getattr(behavior, "eigenstaendig", False))


def ortsbewegung(behavior: Any) -> bool:
    """Bewegt das Verhalten den Körper von der Stelle (Laufen, Drehen, Skills wie Hinsetzen)?"""
    if "base" not in getattr(behavior, "channels", ()):
        return False
    return bool(getattr(behavior, "needs_legs", True) or getattr(behavior, "skill", None))


def _unit(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def initiative(wert: Any) -> float:
    """Regler 0 (nur auf Ansprache) … 1 (lebendig); alte Stufen „aus“, „ab_und_zu“, „oft“ werden umgerechnet."""
    if isinstance(wert, str):                      # Unbekanntes schaltet aus – lieber still als ungefragt aktiv
        return STUFEN.get(wert, 0.0)
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        return STANDARD
    return _unit(wert)


def an(wert: Any) -> bool:
    return initiative(wert) > AUS_BIS


def wartezeit(energie: float, humor: float, haeufigkeit: Any, rng: random.Random | None = None) -> float | None:
    """Sekunden Ruhe bis zur nächsten eigenen Beschäftigung – None = aus. Bei 0,4 („ab und zu“): ruhig 4–6 min,
    lebhaft 1–2 min; jede 0,4 mehr halbiert die Zeit (0,8 = früher „oft“)."""
    i = initiative(haeufigkeit)
    if i <= AUS_BIS:
        return None
    rng = rng or random.Random()
    lebhaft = _unit(0.75 * _unit(energie) + 0.25 * _unit(humor))
    s = rng.uniform(240.0 - 180.0 * lebhaft, 360.0 - 240.0 * lebhaft)
    return s * 2.0 ** ((STANDARD - i) / 0.4)


@dataclass
class Lage:
    """Was die Entscheidung über den Körper und das Zimmer wissen muss."""
    koerper: str = "microduck"                 # microduck | open_duck_mini | reachy_mini
    echt: bool = False                         # echter Roboter (robotd, Reachys Daemon): keine Ortsbewegung von selbst
    eigenschaften: frozenset[str] = frozenset()
    skills: tuple[str, ...] = ()
    sitzt: bool = False
    tricks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)   # Name → Keyframes (Gedächtnis)
    dinge: list[dict[str, Any]] = field(default_factory=list)            # {name, art, entfernung_m, richtung_grad}
    pollen: tuple[str, ...] = ()               # Reachy: Namen der geladenen Emotionen aus Pollens Bibliothek
    gestalt: tuple[str, ...] = ()              # gewählte Eigenschaften der Gestalt (neugier, tollpatsch, antennen …)
    fehlt: Callable[[str], str | None] = lambda name: None   # brain/tools.fehlt_dem_koerper, von der Laufzeit


@dataclass
class Beschaeftigung:
    art: str                                   # trick, gefuehl, geste, erkunden, ding, ball, tanzen, sitzen …
    nachricht: str                             # was im Ereignis-Ticker steht
    gewicht: float
    werkzeug: str | None = None                # Werkzeug des Gehirns (gleiche Prüfungen wie für die KI) – oder None
    args: dict[str, Any] = field(default_factory=dict)
    ort: bool = False                          # Ortsbewegung oder Haltungswechsel – nur im Simulator
    satz: str | None = None                    # i18n-Schlüssel eines kurzen Satzes (nur bei verspielten Charakteren)


def _trick_ohne_ort(keyframes: list[dict[str, Any]]) -> bool:
    return not any("fahren" in kf or "move" in kf or "skill" in kf for kf in keyframes)


def _stamm(name: str) -> str:
    return name.rstrip("0123456789").rstrip("_")


def angebot(lage: Lage, energie: float, humor: float, rng: random.Random | None = None) -> list[Beschaeftigung]:
    """Alles, was dieser Körper jetzt von sich aus tun kann – mit Gewichten nach Charakter. Nichts, was der Körper nicht
    hat (`lage.fehlt`), am echten Roboter nichts mit Ortsbewegung, im Sitzen nur Kopf und Aufstehen."""
    rng = rng or random.Random()
    e, h = _unit(energie), _unit(humor)
    ruhig = 1.0 - e
    neugier = 0.6 if ("neugier" in lage.gestalt or "beobachter" in lage.gestalt) else 0.0
    eig = lage.eigenschaften
    reachy = lage.koerper == "reachy_mini"
    microduck = lage.koerper == "microduck"
    beine = "beine" in eig
    out: list[Beschaeftigung] = []
    add = out.append

    # Gesten des eigenen Charakters (Reachy: eigene Regungen mit Antennen, nie Entengesten)
    add(Beschaeftigung("geste", "zeigt von sich aus eine kleine Geste", 1.0 + 0.4 * h))
    add(Beschaeftigung("umschauen", "schaut sich von sich aus um", 0.8 + 0.5 * ruhig + neugier, "look_around",
                       {"seconds": round(5 + 3 * ruhig, 1)}))
    # Gelernte Tricks aus dem Gedächtnis (am echten Roboter nur solche ohne Laufen und Skills)
    if lage.tricks and not reachy:
        namen = [n for n, kf in lage.tricks.items() if not lage.echt or _trick_ohne_ort(kf)]
        if namen:
            n = rng.choice(sorted(namen))
            add(Beschaeftigung("trick", f"führt von sich aus „{n}“ vor", 1.0 + 1.5 * h + 0.5 * e, "do_trick",
                               {"name": n}, ort=not _trick_ohne_ort(lage.tricks[n]), satz="eigenstaendig.satz.trick"))
    # Pollens Gefühle – nur die Microduck hat sie (die Open Duck keine Pollen-Skills)
    if microduck:
        g = rng.choice(POLLEN_VERSPIELT if h >= 0.5 else POLLEN_RUHIG)
        add(Beschaeftigung("gefuehl", "zeigt von sich aus ein Gefühl", 0.8 + h, "emote", {"emotion": g}))
    if reachy and lage.pollen:
        staemme = REACHY_VERSPIELT if h >= 0.4 or e >= 0.6 else REACHY_RUHIG
        namen = [n for n in lage.pollen if _stamm(n) in staemme]
        if namen:
            add(Beschaeftigung("pollen", "spielt von sich aus eine Regung aus Pollens Bibliothek", 1.0 + 0.6 * h,
                               args={"name": rng.choice(sorted(namen))}))
    if "antennen" in eig:
        a = 25 + 40 * e
        add(Beschaeftigung("antennen", "spielt mit den Antennen", 0.5 + h + (0.5 if "antennen" in lage.gestalt else 0.0),
                           "antennen", {"links_grad": round(a), "rechts_grad": round(a * (0.4 + 0.6 * rng.random())),
                                        "sekunden": 1.2}))

    if lage.sitzt:
        if beine and (not lage.skills or "sit_toggle" in lage.skills):
            add(Beschaeftigung("aufstehen", "steht von sich aus wieder auf", 0.6 + 2.0 * e, "skill",
                               {"name": "sit_toggle"}, ort=True))
        return _filtern([b for b in out if b.art in ("geste", "umschauen", "aufstehen", "antennen")], lage)

    # Ortsbewegung – nur im Simulator
    if beine:
        add(Beschaeftigung("erkunden", "erkundet von sich aus das Zimmer", 0.5 + 2.0 * e + neugier, "explore",
                           {"seconds": round(20 + 25 * e), "speed": round(0.08 + 0.08 * e, 3)}, ort=True,
                           satz="eigenstaendig.satz.erkunden"))
        dinge = [d for d in lage.dinge if d.get("art") not in DINGE_NICHT and d.get("art") != "ente"
                 and float(d.get("entfernung_m", 9)) < 3.0]
        if dinge and microduck:
            d = rng.choice(dinge)
            add(Beschaeftigung("ding", f"geht von sich aus zu {d['name']} und schaut es sich an", 0.6 + 1.2 * e + neugier,
                               "handeln", {"ding": d["name"], "aktion": "hinlaufen"}, ort=True, satz="eigenstaendig.satz.ding"))
        if any(d.get("art") == "ball" for d in dinge):
            add(Beschaeftigung("ball", "schießt von sich aus den Ball", 0.4 + 1.2 * h + 0.8 * e, "schiessen", {},
                               ort=True, satz="eigenstaendig.satz.ball"))
        if lage.koerper == "open_duck_mini":
            grad = rng.choice((-1, 1)) * round(30 + 60 * rng.random())
            add(Beschaeftigung("laufen", "dreht von sich aus eine kleine Runde", 0.6 + 1.5 * e, "drive",
                               {"vx": round(0.06 + 0.06 * e, 3), "turn_deg_s": round(grad / 4), "seconds": 4.0}, ort=True,
                               satz="eigenstaendig.satz.laufen"))
        if (not lage.skills or "sit_toggle" in lage.skills) and e < 0.5:
            add(Beschaeftigung("sitzen", "setzt sich von sich aus hin und ruht sich aus", 1.6 * ruhig * (1.0 - 0.5 * h),
                               "skill", {"name": "sit_toggle"}, ort=True))
    # Kurz tanzen (am echten Roboter nur nicken – ohne Schritte)
    if not reachy:
        stil = "nicken" if lage.echt else rng.choice(("wackeln", "party", "nicken"))
        add(Beschaeftigung("tanzen", "tanzt von sich aus ein bisschen", 0.3 + 1.2 * h * e + 0.5 * e, "dance",
                           {"style": stil, "seconds": round(6 + 4 * e), "bpm": round(90 + 50 * e)}, ort=stil != "nicken",
                           satz="eigenstaendig.satz.tanzen"))
    else:
        add(Beschaeftigung("tanzen", "tanzt von sich aus ein bisschen", 0.3 + 1.2 * h * e + 0.4 * e, "dance",
                           {"seconds": 8, "bpm": round(90 + 40 * e)}, ort=True, satz="eigenstaendig.satz.tanzen"))
        # Körper zu Dingen oder Menschen drehen (Simulator); am echten Reachy nur den Kopf
        ziele = [d for d in lage.dinge if d.get("art") not in ("laser",) and float(d.get("entfernung_m", 9)) < 4.0]
        if ziele:
            d = rng.choice(ziele)
            richtung = max(-160, min(160, round(float(d.get("richtung_grad", 0)))))
            wem = "dir" if d.get("art") == "person" else str(d["name"])
            if lage.echt:
                add(Beschaeftigung("anschauen", f"schaut von sich aus zu {wem}", 0.6 + neugier, "head",
                                   {"yaw_deg": max(-60, min(60, richtung)), "pitch_deg": -5, "roll_deg": 8, "seconds": 3}))
            else:
                add(Beschaeftigung("zuwenden", f"dreht sich von sich aus zu {wem}", 0.6 + 0.8 * e + neugier, "turn",
                                   {"degrees": richtung}, ort=True, satz="eigenstaendig.satz.zuwenden"))
    return _filtern(out, lage)


def _filtern(out: list[Beschaeftigung], lage: Lage) -> list[Beschaeftigung]:
    gut = []
    for b in out:
        if b.gewicht <= 0:
            continue
        if b.ort and lage.echt:                    # am echten Roboter nie ungefragt von der Stelle
            continue
        if b.werkzeug and lage.fehlt(b.werkzeug):  # nichts anbieten, was der Körper nicht hat
            continue
        gut.append(b)
    return gut


def waehlen(angebote: list[Beschaeftigung], rng: random.Random | None = None,
            zuletzt: str | None = None) -> Beschaeftigung | None:
    """Gewichteter Zufall – nicht zweimal hintereinander dasselbe, wenn es anderes gibt."""
    rng = rng or random.Random()
    wahl = [b for b in angebote if b.art != zuletzt] or list(angebote)
    if not wahl:
        return None
    summe = sum(b.gewicht for b in wahl)
    x = rng.uniform(0.0, summe)
    for b in wahl:
        x -= b.gewicht
        if x <= 0:
            return b
    return wahl[-1]


def sperre(engine: Any, *, haeufigkeit: Any, im_koerper: bool = True, ruhe: bool = False, spiel: bool = False,
           gespraech: bool = False) -> str | None:
    """Warum jetzt keine eigene Beschäftigung – oder None. Jede Sperre setzt die Uhr zurück."""
    if not an(haeufigkeit):
        return "ausgeschaltet"
    if not im_koerper:
        return "Knowlin ist im Kopf – kein Körper wach"
    if engine.notaus_gesperrt():
        return "Not-Aus – die Sperre danach läuft noch"
    if engine.still:
        return "still, bis der Mensch sie anspricht"
    if ruhe:
        return "Ruhemodus"
    st = engine.last_state
    if st.picked_up:
        return "hochgehoben"
    if st.fallen:
        return "gefallen"
    if not st.powered:
        return "in Ruhe (Motoren aus)"
    if st.skill:
        return "eine gelernte Bewegung läuft"
    if engine.busy():
        return "beschäftigt"
    if spiel:
        return "ein Spiel läuft"
    if gespraech or getattr(engine, "_speech", None):
        return "im Gespräch"
    if engine.mood.empathic:
        return "mitfühlend"
    jetzt = time.monotonic()
    if jetzt < engine.manual.until or jetzt < engine.gaze.until:
        return "der Mensch steuert"
    if engine.idle.elapsed < engine.idle.attend_until:
        return "hört zu"
    return None


class Eigenstaendig:
    """Die Uhr: zählt Ruhe; jede Sperre und jeder Kontakt mit dem Menschen setzt sie zurück. Kurze Gesten des
    Leerlaufs (`warten`) halten sie nur an."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.ruhig_seit: float | None = None
        self.warte_s: float | None = None
        self.zuletzt: str | None = None
        self.grund: str | None = None              # letzte Sperre (für Tests und Status)

    def takt(self, jetzt: float, gesperrt: str | None, *, warten: bool, energie: float, humor: float,
             haeufigkeit: Any, kontakt_at: float = 0.0) -> bool:
        """True = jetzt etwas tun."""
        self.grund = gesperrt
        if gesperrt:
            self.ruhig_seit, self.warte_s = None, None
            return False
        if self.ruhig_seit is None or kontakt_at > self.ruhig_seit:
            self.ruhig_seit = max(jetzt, kontakt_at) if self.ruhig_seit is None else kontakt_at
        if self.warte_s is None:
            self.warte_s = wartezeit(energie, humor, haeufigkeit, self.rng)
            if self.warte_s is None:
                return False
        if warten or jetzt - self.ruhig_seit < self.warte_s:
            return False
        self.ruhig_seit, self.warte_s = None, None
        return True

    def status(self, jetzt: float | None = None) -> dict[str, Any]:
        jetzt = time.monotonic() if jetzt is None else jetzt
        rest = None if self.ruhig_seit is None or self.warte_s is None else max(0.0, self.warte_s - (jetzt - self.ruhig_seit))
        return {"gesperrt": self.grund, "in_s": None if rest is None else round(rest), "zuletzt": self.zuletzt}
