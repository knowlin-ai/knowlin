"""Die Bewegungs-Engine: entscheidet 20-mal pro Sekunde, was die Ente tut.

Schichten, von oben nach unten (die höhere gewinnt je Kanal):

  1. Reflexe      – Sturz, Hochheben, Hindernis direkt voraus. Schnell, ohne Claude.
  2. Handsteuerung – Tastatur/Gamepad im Browser, solange Tasten gedrückt sind.
  3. Verhalten    – das, was Claude (oder ein Knopf) angestoßen hat; mit Warteschlange.
  4. Leerlauf     – kleine Lebenszeichen: umschauen, atmen, neugierig hingucken.

Kanäle: base (Laufen), head, mouth, pose. Ein Verhalten beansprucht nur die
Kanäle, die es braucht – so kann der Leerlauf den Kopf bewegen, während ein
Lauf-Verhalten nur die Beine steuert.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..aio import spawn
from ..api import LIMITS, DuckBackend, DuckState, Head, IntentResult, Pose, Twist
from .ausweichen import Ausweicher
from .eigenstaendig import EIGEN, ist_eigen, ortsbewegung

log = logging.getLogger(__name__)

ENGINE_HZ = 20
CHANNELS = ("base", "head", "mouth", "pose")
ESTOP_HOLD_S = 120.0     # nach einem Not-Aus steht oder setzt sich so lange nichts von selbst (Standard)
ESTOP_MIN_S = 15.0       # kürzeste wählbare Sperre (seit 0.38.34, Entscheidung des Maintainers: „überall kürzer wählbar“)
RECOVER_RETRY_S = 10.0   # kommt sie nach einem Aufsteh-Versuch nicht hoch: neuer Versuch (mit Stopp-Fenster)
RECOVER_TRIES = 3


@dataclass
class Command:
    """Teilbefehl einer Schicht. None = keine Meinung zu diesem Kanal."""

    twist: Twist | None = None
    head: Head | None = None
    mouth: float | None = None
    pose: Pose | None = None
    # Hindernis-Reflex aktiv? Aus nur, wenn ein Verhalten bewusst nah heran will
    # (z. B. an den Ball zum Kicken).
    guard: bool = True


class Behavior:
    """Basisklasse. Unterklassen überschreiben `tick` (und ggf. `on_start`)."""

    name = "verhalten"
    channels: tuple[str, ...] = CHANNELS
    timeout: float | None = 120.0

    def __init__(self) -> None:
        self.engine: "MotionEngine | None" = None
        self.elapsed = 0.0
        self.done = False
        self.result: str = ""
        self.started = False
        self.waited = 0.0
        self.needs_legs = True   # False für Verhalten, die auch im Sitzen sinnvoll sind

    def kontakt_ziel(self, st: DuckState) -> tuple[float, float, float] | None:
        """Ding, zu dem sie absichtlich hin will (x, y in Weltkoordinaten, Radius in m) – z. B. der Ball beim Schießen.
        Das Ausweichen sieht es nicht als Hindernis (Hinweis aus dem Test 1.11.: „Da wo Kontakt Teil der Aufgabe ist, sollte
        die Ente das wissen“). Standard: keins."""
        return None

    # Hilfen für Unterklassen
    def finish(self, result: str = "fertig") -> Command | None:
        self.done = True
        self.result = result
        return None

    def on_start(self, st: DuckState) -> None:
        pass

    def tick(self, st: DuckState, dt: float) -> Command | None:
        raise NotImplementedError

    def on_stop(self) -> None:
        pass

    def describe(self) -> str:
        return self.name

    def target(self) -> tuple[float, float] | None:
        """Wohin dieses Verhalten will (Odometrie-Rahmen), für die 3D-Zielmarke. Standard: nirgends."""
        return None

    def _step(self, st: DuckState, dt: float) -> Command | None:
        # Beine noch nicht bereit (fährt gerade hoch, z. B. aus der Ruhe geweckt)? Bis zu 8 s warten, bevor die Uhr läuft.
        legs_ready = st.powered and st.enabled and not st.fallen and not st.sitting
        if "base" in self.channels and not legs_ready and self.needs_legs:
            if self.waited < 8.0:
                self.waited += dt
                return None
            # nicht „blind“ weiterlaufen und am Ende Erfolg melden: ehrlich sagen, dass sie nicht steht
            self.failed = True
            return self.finish(f"nicht ausgeführt – die Ente steht nicht ({st.summary()})")
        if not self.started:
            self.started = True
            self.on_start(st)
        self.elapsed += dt
        if self.timeout is not None and self.elapsed > self.timeout:
            return self.finish("Zeitlimit erreicht")
        return self.tick(st, dt)


@dataclass
class EngineConfig:
    idle_life: bool = True          # Leerlauf-Animationen
    obstacle_guard: bool = True     # Hindernis-Reflex
    ausweichen: bool = True         # Hindernissen ausweichen und sie umlaufen (aus = nur bremsen, wie bis 0.32)
    stop_distance: float = 0.16     # m – darunter kein Vorwärts mehr
    slow_distance: float = 0.45     # m – ab hier wird gebremst
    auto_recover: bool = True       # nach Sturz selbst aufstehen (robot.init) – Projektregel seit 0.28
    recover_delay: float = 3.0      # Stopp-Fenster: so lange hört sie nach einem Sturz zu, „Stopp“ hält sie liegen
    # Persönlichkeit als Punkt im X/Y-Regler, je 0 … 1
    energie: float = 0.55           # X: ruhig (0) ↔ lebhaft (1)
    humor: float = 0.25             # Y: ernst (0) ↔ albern (1); ab 0,5 Goofy-Modus
    emotions: bool = True           # Gefühle zeigen
    # Nach dem Not-Aus (seit 0.38.13 einstellbar, Wunsch des Maintainers): Sperre nie unter ESTOP_HOLD_S (Sicherheitsregel),
    # auf Wunsch länger; danach „weiter“ wie vorher oder „still“, bis der Mensch die Verkörperung anspricht
    notaus_sperre_s: float = 120.0
    notaus_danach: str = "weiter"
    seed: int | None = None         # nur für Tests: reproduzierbarer Zufall

    # Goofy ist kein eigener Schalter mehr, sondern die obere Hälfte des Humor-Reglers.
    @property
    def goofy(self) -> bool:
        return self.humor >= 0.5

    @goofy.setter
    def goofy(self, on: bool) -> None:
        self.humor = max(self.humor, 0.75) if on else min(self.humor, 0.25)

    # Einstellung stopp_fenster_s = Wartezeit vor dem Selbst-Aufstehen
    @property
    def stopp_fenster_s(self) -> float:
        return self.recover_delay

    @stopp_fenster_s.setter
    def stopp_fenster_s(self, s: float) -> None:
        self.recover_delay = float(s)

    @property
    def goofy_level(self) -> str:
        return "sanft" if self.humor < 0.67 else ("mittel" if self.humor < 0.85 else "wild")

    @goofy_level.setter
    def goofy_level(self, level: str) -> None:
        self.humor = GOOFY_HUMOR.get(level, self.humor)

    @property
    def expressiveness(self) -> float:
        """Wie groß Gesten ausfallen: 0,65 (ruhig) … 1,15 (lebhaft)."""
        return 0.65 + 0.5 * self.energie


GOOFY_HUMOR = {"sanft": 0.6, "mittel": 0.75, "wild": 0.95}


@dataclass
class _Manual:
    twist: Twist = field(default_factory=Twist)
    head: Head | None = None
    until: float = 0.0


@dataclass
class _Gaze:
    """Blick von Hand (Klick oder Ziehen in der 3D-Ansicht): feste Kopfstellung oder ein Punkt im Raum,
    dem der Kopf auch beim Laufen folgt. Nur der Kopf – Beine und Verhalten bleiben frei."""
    head: Head | None = None
    point: tuple[float, float, float] | None = None
    until: float = 0.0


LIMIT_YAW = LIMITS["head_yaw"][1]
EYE = (0.064, 0.0, 0.126)        # Kopfkamera über dem Rumpfursprung in Grundstellung (Pollens MJCF)
TRUNK_H = 0.12                   # Rumpfursprung über dem Boden


def head_towards(st: DuckState, point: tuple[float, float, float]) -> tuple[Head, float]:
    """Kopfstellung, die vom Körper aus auf einen Weltpunkt schaut, plus Richtung zum Punkt (rad, + = links)."""
    dx, dy = point[0] - st.x, point[1] - st.y
    c, s = math.cos(-st.yaw), math.sin(-st.yaw)
    fx, fy = c * dx - s * dy, s * dx + c * dy
    bearing = math.atan2(fy, fx)
    ex, ez = fx - EYE[0], point[2] - (st.stand_z or 0.0) - TRUNK_H - EYE[2]   # Reachy auf dem Tisch: höher
    pitch = -math.atan2(ez, max(0.05, math.hypot(ex, fy)))
    return Head(0.0, pitch, bearing, 0.0).clamped(), bearing


class MotionEngine:
    def __init__(self, backend: DuckBackend, config: EngineConfig | None = None) -> None:
        self.backend = backend
        self.config = config or EngineConfig()
        self.current: Behavior | None = None
        self.queue: collections.deque[Behavior] = collections.deque()
        self.events: collections.deque[dict[str, Any]] = collections.deque(maxlen=40)
        self.listeners: list[Callable[[dict[str, Any]], None]] = []
        self.idle = IdleLife(self.config.seed)   # Saat aus der Konfiguration: Tests laufen reproduzierbar
        self.idle.engine = self
        self.manual = _Manual()
        self.gaze = _Gaze()
        self.stopped_at = 0.0
        self.estop_at = -1e9          # letzter Not-Aus (Knopf, Esc, „Stopp“, stop-Werkzeug) – nicht bei internen Stopps
        self.still = False            # nach dem Not-Aus still bleiben, bis der Mensch etwas sagt (notaus_danach = still)
        self.kontakt_at = time.monotonic()   # letzter Kontakt mit dem Menschen (eigenständiges Verhalten wartet danach)
        self.eigen_extern_bis = 0.0   # bis dahin spielt der Körper eine eigene Beschäftigung selbst ab (Reachys Aufnahmen)
        self.last_state: DuckState = backend.state()
        self.last_cmd = Command(Twist(), Head(), 0.0, Pose())
        self.reflex_note: str | None = None
        self.ausweicher = Ausweicher(self.config.stop_distance, self.config.slow_distance)
        self._ausweich_note_at = 0.0
        self._task: asyncio.Task | None = None
        self._was_fallen = False
        self._fallen_since: float | None = None
        self._recover_sent = False
        self._recover_at = 0.0
        self._recover_tries = 0
        self._window_open = False
        self._pending: set[asyncio.Task] = set()
        self._last_head_send = 0.0
        self.powering_until = 0.0
        # Goofy-Modus
        import random

        self.rng = random.Random(self.config.seed)
        self.overlay: Behavior | None = None   # Kopf/Schnabel/Körper-Einlage über allem, nie die Beine
        self._idle_for = 0.0
        self._next_antic: float | None = None
        self._char_for = 0.0                     # Leerlauf-Uhr für die Charakter-Gesten
        self._char_next: float | None = None
        self._last_gesture: str | None = None
        self._overlay_cooldown = 0.0
        self._recover_shake_at: float | None = None
        # Gefühle
        from .mood import Mood

        self.mood = Mood()
        self._last_expression = -1e9
        self._clock = 0.0
        # Sprechen: Schnabelspur (0…1 alle 0,1 s) der gerade gesprochenen Stimme
        self._speech: list[float] = []
        self._speech_t = 0.0
        backend.on_event(self._on_backend_event)

    # ── Ereignisse ────────────────────────────────────────────────────────
    def _on_backend_event(self, event: dict[str, Any]) -> None:
        self.note(event)
        # Odi O1 (0.38.27): woran sie im Gehen stieß oder fiel, merkt sie sich als Hindernis – auch ganz ohne Sensor
        if event.get("type") == "bump" or (event.get("type") == "fall" and "gegen" in str(event.get("message", ""))):
            self.ausweicher.angestossen(self.last_state)
        if event.get("type") == "bump" and self.config.goofy and not event.get("kollision"):   # Spiel ≠ Ärger
            from .behaviors import EMOTIONS, concat

            empoert = EMOTIONS["wer_sagt_das"] if "wer_sagt_das" in EMOTIONS and self.rng.random() < 0.5 \
                else EMOTIONS["trotzig"][:4]
            self.play_overlay(concat(empoert, EMOTIONS["schuetteln"]),
                              f"ist empört über {event.get('what', 'das Hindernis')} – und schüttelt sich")

    # ── Gefühle zeigen ────────────────────────────────────────────────────
    EXPRESSIVE = ("Choreography", "Dance", "LookAround", "HoldHead")
    NEGATIVE = ("frustriert", "verlegen", "erschrocken")
    # Manchmal Pollens Original statt der eigenen Choreografie – mit aufgenommenem Ton
    POLLEN_ALT = {"begeistert": ("aufgeregt",), "frustriert": ("ungeduldig",), "verlegen": ("hmm",)}
    POLLEN_ALT_GOOFY = {"freude": ("lachen",), "stolz": ("lachen",), "frustriert": ("grummelig", "ungeduldig")}

    def express(self, name: str, force: bool = False) -> bool:
        """Ein Gefühl kurz mit Kopf, Schnabel und Haltung zeigen – nie mit den Beinen."""
        from .behaviors import EMOTIONS, concat

        if not self.config.emotions or name not in EMOTIONS:
            return False
        st = self.last_state
        if st.fallen or not st.powered or st.skill:
            return False
        # Nicht in etwas hineinfuhrwerken, das selbst schon Ausdruck ist (Tanz, Gefühl, Choreografie)
        busy = [self.current, *self.queue]
        if any(type(b).__name__ in self.EXPRESSIVE for b in busy if b is not None) and not force:
            return False
        gap = 9.0 - 5.0 * self.config.energie       # ruhig: seltener, lebhaft: öfter
        if self._clock - self._last_expression < gap and not force:
            return False
        feeling = self.mood.feeling()
        from .reachy_gesten import ist_reachy

        if ist_reachy(self.backend):
            return self._reachy_express(name, feeling, force)
        spec = EMOTIONS[name]
        alts = (self.POLLEN_ALT_GOOFY if self.config.goofy else {}).get(name) or self.POLLEN_ALT.get(name, ())
        alts = [a for a in alts if a in EMOTIONS]
        # Pollens Emotionen sind fürs Stehen gemacht („the sticks must not walk it“) – im Laufen die eigene Geste
        standing = self.last_cmd.twist is None or self.last_cmd.twist.is_zero()
        if alts and standing and self.rng.random() < 0.4:
            spec = EMOTIONS[self.rng.choice(alts)]
        if self.config.goofy and name in self.NEGATIVE:
            spec = concat(spec, EMOTIONS["schuetteln"])  # Goofy: abschütteln, gackern, weiter
        if self.play_overlay(spec, force=force):
            self._last_expression = self._clock
            self.note({"type": "gefuehl", "message": f"{feeling.name}{' – ' + feeling.reason if feeling.reason else ''}",
                       "name": feeling.name})
            return True
        return False

    # Vom Server gesetzt (Reachy Mini): Stämme → passende Aufnahme aus Pollens Bibliothek abspielen; True = läuft
    pollen_gefuehl: Callable[[tuple[str, ...]], bool] | None = None

    def _reachy_express(self, name: str, feeling: Any, force: bool) -> bool:
        """Reachy Mini (seit 0.38.10): eigene Geste mit Antennen statt der Entenchoreografie – oder manchmal Pollens
        aufgenommene Emotion, wenn die Bibliothek da ist. Kein Gackern, kein Schütteln."""
        from .behaviors import EMOTIONS
        from .reachy_gesten import POLLEN, geste

        staemme = POLLEN.get(name, ())
        if staemme and self.pollen_gefuehl is not None and self.overlay is None and self.rng.random() < 0.4:
            try:
                gespielt = self.pollen_gefuehl(staemme)
            except Exception:  # noqa: BLE001 – dann eben die eigene Geste
                gespielt = False
            if gespielt:
                self._last_expression = self._clock
                self.note({"type": "gefuehl", "message": feeling.name, "name": feeling.name})
                return True
        if self.play_overlay(geste(name) or EMOTIONS[name], force=force):
            self._last_expression = self._clock
            self.note({"type": "gefuehl", "message": f"{feeling.name}{' – ' + feeling.reason if feeling.reason else ''}",
                       "name": feeling.name})
            return True
        return False

    def speak(self, track: list[float] | None) -> None:
        """Der Schnabel spricht mit: Spur 0…1 alle 0,1 s (leer/None = Schluss)."""
        self._speech = [max(0.0, min(1.0, float(v))) for v in (track or [])][:1200]
        self._speech_t = 0.0

    def _speech_mouth(self, dt: float) -> float | None:
        if not self._speech:
            return None
        self._speech_t += dt
        x = self._speech_t / 0.1
        i = int(x)
        if i >= len(self._speech):
            self._speech = []
            return None
        nxt = self._speech[i + 1] if i + 1 < len(self._speech) else 0.0
        return 0.8 * (self._speech[i] + (nxt - self._speech[i]) * (x - i))

    def hear(self, text: str, show: bool = True) -> None:
        """Was der Mensch sagt, färbt die Stimmung (Lob, Freude, Kummer, Kritik)."""
        expression = self.mood.appraise_text(text)
        if expression and show:
            self.express(expression, force=expression == "einfuehlsam")

    # ── Goofy-Modus ───────────────────────────────────────────────────────
    def goofy_params(self) -> dict[str, float]:
        """Stufenlos aus dem Humor-Regler: knapp über der Mitte sanft, ganz oben wild."""
        g = max(0.0, min(1.0, (self.config.humor - 0.5) / 0.5))
        e = self.config.energie
        return {
            "stumble": (1 / 45 + g * (1 / 9 - 1 / 45)) * (0.7 + 0.6 * e),   # pro Sekunde Laufen
            "idle": (80.0 - g * 62.0) * (1.3 - 0.6 * e),                     # s Leerlauf bis zum Unsinn
            "trotz": 0.12 + g * 0.3,
        }

    def play_overlay(self, spec: list[dict[str, Any]], message: str | None = None, force: bool = False) -> bool:
        """Kurze Einlage für Kopf, Schnabel und Körperhaltung – die Beine laufen normal weiter."""
        from .behaviors import Choreography

        if self.overlay is not None and not force:
            return False
        if self._overlay_cooldown > 0 and not force:
            return False
        from .behaviors import is_pollen

        # Pollens Emotionen in Originalgröße – sie sind auf die Policies abgestimmt; eigene Gesten nach Temperament
        ch = Choreography.from_spec(spec, title="goofy", scale=1.0 if is_pollen(spec) else self.config.expressiveness)
        ch.engine = self
        ch.overlay = True                      # Einlage: Beine und Skills bleiben unberührt
        ch.eigenstaendig = EIGEN.get()         # von sich aus gezeigt: Ansprechen beendet es sofort
        self.overlay = ch
        self._overlay_cooldown = 4.0
        if message:
            self.note({"type": "goofy", "message": message})
        return True

    def _goofy(self, st: DuckState, dt: float) -> None:
        from .behaviors import EMOTIONS, concat

        self._overlay_cooldown = max(0.0, self._overlay_cooldown - dt)
        if not self.config.goofy or self.mood.empathic or self.still:  # traurig oder still: kein Quatsch
            self._idle_for = 0.0
            return
        p = self.goofy_params()
        ready = st.powered and st.enabled and not st.fallen and not st.sitting and not st.skill
        # Nach dem Aufstehen: erst mal schütteln, als wäre nichts gewesen
        if self._recover_shake_at is not None and ready:
            self._recover_shake_at -= dt
            if self._recover_shake_at <= 0:
                self._recover_shake_at = None
                self.play_overlay(EMOTIONS["schuetteln"], "schüttelt sich – als wäre nichts gewesen", force=True)
        if not ready:
            self._idle_for = 0.0
            return
        # Tollpatschig beim Laufen
        from . import behaviors as B

        walking = abs(st.twist.vx) > 0.06 or abs(st.twist.vy) > 0.05
        plain = self.current is None or isinstance(self.current, (B.Walk, B.Turn, B.GoTo, B.TimedMove, B.Explore, B.Approach))
        if walking and plain and self.overlay is None and self.rng.random() < dt * p["stumble"]:
            self.play_overlay(concat(EMOTIONS["stolpern"], EMOTIONS["schuetteln"]), "stolpert – hoppla! – und gackert")

    # ── Charakter im Leerlauf ─────────────────────────────────────────────
    @property
    def persona(self) -> str:
        from .character import persona

        return persona(self.config.energie, self.config.humor)

    def _idle_now(self, st: DuckState) -> bool:
        return (self.current is None and not self.queue and time.monotonic() >= self.manual.until
                and self.overlay is None and st.powered and st.enabled and not st.fallen and not st.skill
                and not st.picked_up and self.idle.elapsed >= self.idle.attend_until)

    def _character(self, st: DuckState, dt: float) -> None:
        """Wer nicht ausgeglichen ist, tut im Leerlauf, was zu ihm passt – gähnen, wippen, niesen …"""
        from .character import REPERTOIRE

        name = self.persona
        rep = REPERTOIRE.get(name) or {}
        if not self.config.idle_life or self.still or not rep.get("gesten") or self.mood.empathic or not self._idle_now(st):
            self._char_for = 0.0
            self._char_next = None
            return
        self._char_for += dt
        if self._char_next is None:
            lo, hi = rep["abstand"]
            self._char_next = self.rng.uniform(lo, hi)
        if self._char_for < self._char_next:
            return
        self._char_for = 0.0
        self._char_next = None
        self.idle_gesture(st, name)

    def idle_gesture(self, st: DuckState | None = None, persona: str | None = None) -> str | None:
        """Eine Geste aus dem Repertoire des Charakters zeigen. Gibt ihren Namen zurück."""
        from .behaviors import ANTICS, EMOTIONS, Choreography, concat
        from .character import GESTURES, MESSAGES, NUR_MIT_SCHNABEL, QUATSCH, REPERTOIRE, sits_ok

        st = st or self.last_state
        from .reachy_gesten import ist_reachy

        if ist_reachy(self.backend):
            return self._reachy_leerlauf()
        eig = self.backend.eigenschaften()
        if "kopf" not in eig:                                   # ohne Kopf (SO-101) keine Kopf- und Entengesten
            return None
        rep = REPERTOIRE.get(persona or self.persona) or {}
        legs_ok = st.backend == "sim" and not st.sitting        # am echten Roboter nie ungefragt losdrehen
        options: list[tuple[str, list[dict[str, Any]], bool, str]] = []
        for gname, weight in rep.get("gesten", []):
            if gname in NUR_MIT_SCHNABEL and "schnabel" not in eig:   # Stacki und Bello putzen kein Gefieder
                continue
            if gname in GESTURES:
                spec, legs, msg = EMOTIONS.get(gname, GESTURES[gname]), False, MESSAGES.get(gname, gname)
            elif gname in ANTICS:
                spec, legs, msg = ANTICS[gname]["spec"], ANTICS[gname]["beine"], ANTICS[gname]["nachricht"]
            elif gname in EMOTIONS:
                spec, legs, msg = EMOTIONS[gname], False, MESSAGES.get(gname, gname)
            else:
                continue
            if legs and not legs_ok:
                continue
            if st.sitting and not sits_ok(spec):
                continue
            options += [(gname, spec, legs, msg)] * int(weight)
        if len({o[0] for o in options}) > 1:          # nicht zweimal hintereinander dasselbe
            options = [o for o in options if o[0] != self._last_gesture]
        if not options:
            return None
        gname, spec, legs, msg = self.rng.choice(options)
        self._last_gesture = gname
        if gname in QUATSCH and self.config.goofy:
            spec = concat(spec, EMOTIONS["schuetteln"])          # Goofy: danach schütteln und gackern
        if legs:
            self.run(Choreography.from_spec(spec, title=gname.replace("_", " "), scale=self.config.expressiveness))
        elif not self.play_overlay(spec):
            return None
        self.note({"type": "charakter", "message": msg, "geste": gname, **({"eigenstaendig": True} if EIGEN.get() else {})})
        return gname

    def _reachy_leerlauf(self) -> str | None:
        """Reachy Mini im Leerlauf: eine ruhige eigene Regung mit Antennen – keine Entengeste, kein Quaken."""
        from .reachy_gesten import LEERLAUF, geste

        namen = [n for n in LEERLAUF if n != self._last_gesture and geste(n)]
        if not namen:
            return None
        name = self.rng.choice(namen)
        if not self.play_overlay(geste(name) or []):
            return None
        self._last_gesture = name
        self.note({"type": "charakter", "message": LEERLAUF[name], "geste": name,
                   **({"eigenstaendig": True} if EIGEN.get() else {})})
        return name

    def note(self, event: dict[str, Any]) -> None:
        if event.get("type") not in ("gefuehl", "goofy", "charakter", "state"):
            expression = self.mood.appraise(event)
            if expression:
                self.express(expression)
        event = {"t": round(time.time(), 2), **event}
        if event["type"] not in ("state",):
            self.events.append(event)
        for fn in list(self.listeners):
            try:
                fn(event)
            except Exception:
                log.exception("Event-Listener")

    def recent_events(self, seconds: float = 30.0) -> list[dict[str, Any]]:
        now = time.time()
        return [e for e in self.events if now - e["t"] <= seconds and e["type"] != "sound"]

    # ── Steuerung von außen ───────────────────────────────────────────────
    def run(self, behavior: Behavior, then: bool = False) -> Behavior:
        """Verhalten starten. then=True hängt es hinten an die Warteschlange."""
        behavior.engine = self
        if EIGEN.get():                           # von sich aus (eigenständiges Verhalten)
            behavior.eigenstaendig = True
            if self.last_state.backend != "sim" and ortsbewegung(behavior):
                # Sicherheitsregel: am echten Roboter nie ungefragt von der Stelle – nur Gesten, Kopf, Antennen
                behavior.done, behavior.failed, behavior.result = True, True, "abgelehnt: am echten Roboter nicht von selbst"
                self.note({"type": "reflex", "message": f"Nicht von selbst am echten Roboter: {behavior.describe()}"})
                return behavior
        elif then:
            self.eigenstaendig_unterbrechen("Befehl")   # ein Befehl wartet nie hinter einer eigenen Beschäftigung
        if then and (self.current is not None or self.queue):
            self.queue.append(behavior)
            self.note({"type": "queued", "behavior": behavior.describe()})
        else:
            self._cancel_all(f"ersetzt durch {behavior.describe()}")
            self._activate(behavior)
        return behavior

    def _activate(self, behavior: Behavior) -> None:
        self.current = behavior
        self.note({"type": "behavior_start", "behavior": behavior.describe()})

    def cancel_current(self, why: str) -> None:
        """Nur das laufende Verhalten beenden (die Warteschlange rückt nach)."""
        if self.current is not None:
            self.current.on_stop()
            self.note({"type": "behavior_end", "behavior": self.current.describe(), "result": why})
            self.current = None

    def _cancel_all(self, why: str) -> None:
        if self.current is not None:
            self.current.on_stop()
            self.note({"type": "behavior_end", "behavior": self.current.describe(), "result": f"abgebrochen: {why}"})
        self.current = None
        self.queue.clear()

    @property
    def sperre_s(self) -> float:
        """Sperre nach dem Not-Aus: Standard ESTOP_HOLD_S, wählbar ab ESTOP_MIN_S (seit 0.38.34; vorher nie unter 120 s)."""
        return max(ESTOP_MIN_S, float(getattr(self.config, "notaus_sperre_s", ESTOP_HOLD_S) or ESTOP_HOLD_S))

    def notaus_gesperrt(self) -> bool:
        """Gilt die Sperre nach dem letzten Not-Aus noch? Dann steht oder setzt sich nichts von selbst."""
        return time.monotonic() - self.estop_at < self.sperre_s

    def notaus(self) -> None:
        """Der Mensch hat den Not-Aus ausgelöst (Knopf, Esc, „Stopp“, stop-Werkzeug): Zeit merken, ggf. still bleiben."""
        self.estop_at = time.monotonic()
        self.still = getattr(self.config, "notaus_danach", "weiter") == "still"

    async def not_aus(self, why: str) -> None:
        """Der Not-Aus (Knopf, Esc, Controller, „Stopp“): alles abbrechen und sofort stromlos – wie ein echter Not-Aus
        (seit 0.38.24, vorher blieb sie stehen). Schlägt das Abschalten fehl, ist trotzdem alles angehalten."""
        self.notaus()
        await self.stop_all(why)
        try:
            res = await self.backend.relax()
            if not res.accepted:
                self.note({"type": "reflex", "message": f"Not-Aus: angehalten, aber nicht stromlos – {res.reason}"})
        except Exception as exc:  # noqa: BLE001
            self.note({"type": "reflex", "message": f"Not-Aus: angehalten, aber nicht stromlos – {exc}"})

    def angesprochen(self) -> None:
        """Der Mensch wendet sich der Verkörperung zu – „still bis angesprochen“ endet (die Sperre bleibt)."""
        self.still = False
        self.kontakt("angesprochen")

    def kontakt(self, why: str) -> None:
        """Der Mensch ist da (spricht, steuert, schaut, gibt Befehle): eigene Beschäftigungen enden sofort, die Uhr fürs
        eigenständige Verhalten beginnt von vorn."""
        self.kontakt_at = time.monotonic()
        self.eigenstaendig_unterbrechen(why)

    def eigenstaendig_unterbrechen(self, why: str) -> bool:
        """Alles beenden, was sie von sich aus tut (Verhalten, Warteschlange, Einlage, Aufnahme im Körper)."""
        hit = False
        if any(ist_eigen(b) for b in self.queue):
            self.queue = collections.deque(b for b in self.queue if not ist_eigen(b))
            hit = True
        if ist_eigen(self.current):
            self.cancel_current(f"unterbrochen: {why}")
            hit = True
        if ist_eigen(self.overlay):
            self.overlay = None
            hit = True
        if time.monotonic() < self.eigen_extern_bis:
            self.eigen_extern_bis = 0.0
            self.fire(self.backend.stop())
            hit = True
        return hit

    async def stop_all(self, why: str = "Stopp") -> None:
        self._cancel_all(why)
        self.powering_until = 0.0              # ein laufendes Aufstehen gilt nicht mehr
        self.gaze = _Gaze()
        self.stopped_at = time.monotonic()
        self.kontakt_at = self.stopped_at
        self.eigen_extern_bis = 0.0
        self.overlay = None
        self._speech = []
        self._idle_for = 0.0
        self._char_for = 0.0
        self.manual = _Manual()
        await self.backend.stop()
        await self.backend.move(Twist())

    def look_at(self, *, head: Head | None = None, point: tuple[float, float, float] | None = None,
                seconds: float = 8.0) -> dict[str, Any]:
        """Blick von Hand halten: feste Kopfstellung (Ziehen) oder Weltpunkt (Klick). seconds ≤ 0 gibt frei."""
        seconds = max(0.0, min(60.0, float(seconds)))
        self.kontakt("Blick von Hand")
        if seconds <= 0 or (head is None and point is None):
            self.gaze = _Gaze()
            return {"ok": True, "blick": None}
        self.gaze = _Gaze(head.clamped() if head else None, point, time.monotonic() + seconds)
        out: dict[str, Any] = {"ok": True}
        if point is not None:
            _, bearing = head_towards(self.last_state, point)
            out["richtung_grad"] = round(math.degrees(bearing))
            out["kopf_reicht"] = abs(bearing) <= LIMIT_YAW
        return out

    def manual_drive(self, twist: Twist, head: Head | None = None, hold: float = 0.35) -> None:
        """Handsteuerung; verfällt nach `hold` s, wenn nichts nachkommt."""
        self.kontakt("Handsteuerung")
        self.manual = _Manual(twist.clamped(), head.clamped() if head else None, time.monotonic() + hold)

    def attention(self, seconds: float = 3.0) -> None:
        """Jemand spricht mit der Ente – sie schaut hoch zum Menschen (Reachy Mini: neigt den Kopf, stellt die Antennen)."""
        self.idle.attend(seconds)
        self.kontakt("hört zu")
        self.backend.gespraech("zuhoeren", seconds)

    def denkt(self, an: bool) -> None:
        """Das Gehirn rechnet an einer Antwort (seit 0.38.2) – Körper mit eigenem Ausdruck zeigen das."""
        self.backend.gespraech("denkt" if an else None)

    def fire(self, coro) -> asyncio.Task:
        """Diskreten Befehl aus einem Verhalten heraus abschicken."""
        task = spawn(coro)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    def busy(self) -> bool:
        return self.current is not None or bool(self.queue)

    def describe(self) -> dict[str, Any]:
        return {
            "gefuehl": self.mood.snapshot(),
            "aktuell": self.current.describe() if self.current else None,
            "laufzeit_s": round(self.current.elapsed, 1) if self.current else None,
            "warteschlange": [b.describe() for b in self.queue],
            "reflex": self.reflex_note,
            "ziel": self._target(),
            # was der Kopf soll (ohne Stabilisator-Ausgleich) – Startpunkt fürs Umschauen per Ziehen
            "kopf_soll": {"yaw": round(self.last_cmd.head.head_yaw, 3), "pitch": round(self.last_cmd.head.head_pitch, 3)}
            if self.last_cmd.head else None,
        }

    def _target(self) -> list[float] | None:
        try:
            t = self.current.target() if self.current else None
        except Exception:
            t = None
        return [round(t[0], 3), round(t[1], 3)] if t else None

    # ── Schleife ──────────────────────────────────────────────────────────
    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="motion-engine")

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        dt = 1.0 / ENGINE_HZ
        next_t = time.perf_counter()
        while True:
            try:
                await self.tick(dt)
            except Exception:
                log.exception("Fehler im Engine-Tick")
            next_t += dt
            delay = next_t - time.perf_counter()
            if delay < -0.5:
                next_t = time.perf_counter()
            await asyncio.sleep(max(0.0, delay))

    async def tick(self, dt: float) -> Command:
        st = self.backend.state()
        self.last_state = st
        self._clock += dt
        self.mood.update(dt)
        self._reflexes(st)

        # Verhalten weiterschalten
        layer_behavior: Command | None = None
        behavior_channels: tuple[str, ...] = ()
        if self.current is None and self.queue:
            self._activate(self.queue.popleft())
        if self.current is not None:
            try:
                layer_behavior = self.current._step(st, dt)
            except Exception as exc:  # ein kaputtes Verhalten darf die Engine nicht töten
                log.exception("Verhalten %s", self.current.name)
                self.current.finish(f"Fehler: {exc}")
            behavior_channels = self.current.channels
            if self.current.done:
                ende = {"type": "behavior_end", "behavior": self.current.describe(), "result": self.current.result}
                if callable(getattr(self.current, "bericht", None)):      # Fähigkeit (seit 0.38): einheitlicher Bericht
                    ende["bericht"] = self.current.bericht()
                self.note(ende)
                self.current.on_stop()
                failed = getattr(self.current, "failed", False)
                self.current = None
                if failed and self.queue and getattr(self.queue[0], "needs_target", False):
                    skipped = self.queue.popleft()      # nicht ins Leere treten, wenn sie gar nicht am Ball ist
                    self.note({"type": "behavior_end", "behavior": skipped.describe(),
                               "result": "ausgelassen – nicht am Ziel angekommen"})
                if self.queue:
                    self._activate(self.queue.popleft())

        manual_active = time.monotonic() < self.manual.until
        idle_cmd = self.idle._step(st, dt) if (self.config.idle_life and not self.still and not st.fallen) else None

        cmd = Command()
        guard = True
        # unten anfangen, oben überschreiben
        if idle_cmd:
            cmd.head, cmd.mouth, cmd.pose = idle_cmd.head, idle_cmd.mouth, idle_cmd.pose
        if layer_behavior:
            guard = layer_behavior.guard
            for ch, attr in (("base", "twist"), ("head", "head"), ("mouth", "mouth"), ("pose", "pose")):
                if ch in behavior_channels and getattr(layer_behavior, attr) is not None:
                    setattr(cmd, attr, getattr(layer_behavior, attr))
        if self.gaze.point is not None and math.hypot(self.gaze.point[0] - st.x, self.gaze.point[1] - st.y) < 0.25:
            self.gaze = _Gaze()                 # angekommen – nicht auf die eigenen Füße starren
        point_gaze = time.monotonic() < self.gaze.until and self.gaze.point is not None
        stab = getattr(self.backend, "stabilizer", None)
        if stab is not None:
            stab.yaw_hold = not point_gaze           # Blick auf einen Punkt gleicht das Drehen schon selbst aus
        if time.monotonic() < self.gaze.until and not st.fallen:
            if self.gaze.point is not None:
                cmd.head = head_towards(st, self.gaze.point)[0]
            elif self.gaze.head is not None:
                cmd.head = self.gaze.head
        if manual_active:
            cmd.twist = self.manual.twist
            if self.manual.head is not None:
                cmd.head = self.manual.head

        # Goofy-Einlage: Kopf, Schnabel, Haltung – nie die Beine
        if self.overlay is not None:
            if st.fallen or not st.powered:
                self.overlay = None
            else:
                oc = self.overlay._step(st, dt)
                if self.overlay.done or oc is None:
                    self.overlay = None
                else:
                    cmd.head = oc.head or cmd.head
                    cmd.mouth = oc.mouth if oc.mouth is not None else cmd.mouth
                    cmd.pose = oc.pose or cmd.pose
        self._goofy(st, dt)
        self._character(st, dt)

        twist = cmd.twist or Twist()
        self.ausweicher.merken(st, dt)
        ziel = None if manual_active or self.current is None else self.current.kontakt_ziel(st)
        twist = self._obstacle_reflex(st, twist, guard and self.config.obstacle_guard, hand=manual_active, ziel=ziel)
        # Beim Umlaufen in die Kurve schauen (der ToF sieht nur ±22,5°) – nur, wenn niemand sonst den Kopf führt
        kopf_frei = not (layer_behavior and "head" in behavior_channels and layer_behavior.head is not None)
        if (kopf_frei and not manual_active and time.monotonic() >= self.gaze.until and not st.fallen
                and self.ausweicher.umlauf_aktiv()):
            vorhalt = max(-0.7, min(0.7, 0.7 * twist.vyaw))
            base = cmd.head or Head()
            cmd.head = Head(base.neck_pitch, base.head_pitch, vorhalt, base.head_roll)
        if st.fallen or st.picked_up:
            twist = Twist()

        self.backend.expressing = self.overlay is not None or type(self.current).__name__ in ("Choreography", "Dance")
        await self.backend.move(twist)
        head = cmd.head or self.last_cmd.head or Head()
        mouth = cmd.mouth if cmd.mouth is not None else 0.0
        talking = self._speech_mouth(dt)
        if talking is not None and not st.fallen:
            mouth = max(mouth, talking)
        # Mit vollem Schnabel spricht man nicht (seit 0.38.25, Frage „wenn sie was im Mund hat, kann sie den Mund
        # nicht bewegen zum Reden, oder?“): Hält sie etwas, bleibt der Schnabel zu – sonst fiele es herunter. Nur das
        # Ablegen selbst (ground_pick) öffnet ihn.
        if st.holding and st.skill != "ground_pick":
            mouth = 0.0
        pose = cmd.pose or Pose()
        now = time.monotonic()
        changed = (head != self.last_cmd.head or mouth != self.last_cmd.mouth or pose != self.last_cmd.pose)
        if changed or now - self._last_head_send > 0.25:
            self._last_head_send = now
            await self.backend.head(head)
            await self.backend.mouth(mouth)
            await self.backend.pose(pose, active=True)
        self.last_cmd = Command(twist, head, mouth, pose)
        return self.last_cmd

    # ── Reflexe ───────────────────────────────────────────────────────────
    def _recover_blocked(self, st: DuckState) -> str | None:
        """Warum sie gerade nicht von selbst aufstehen darf – oder None."""
        if not self.config.auto_recover:
            return "Selbst-Aufstehen ist ausgeschaltet"
        if time.monotonic() - self.estop_at <= self.sperre_s:
            return "Not-Aus – die Sperre danach läuft noch"
        if st.picked_up:
            return "hochgehoben"
        if not st.powered:
            return "in Ruhe (Motoren aus)"
        return None

    def _close_window(self, why: str) -> None:
        if self._window_open:
            self._window_open = False
            self.note({"type": "stopp_fenster_ende", "grund": why, "message": f"Stopp-Fenster zu: {why}"})

    def _reflexes(self, st: DuckState) -> None:
        now = st.t if st.t > 0 else time.monotonic()  # Körperzeit: im Test schneller als die Uhr
        if st.fallen and not self._was_fallen:
            self._fallen_since = now
            self._recover_sent = False
            self._recover_tries = 0
            self._cancel_all("umgefallen")
            self.note({"type": "reflex", "message": "Umgefallen – alle Verhalten gestoppt"})
            self._open_window(st)
        if not st.fallen:
            if self._was_fallen:
                self._close_window("steht wieder")
            self._fallen_since = None
            if self._was_fallen and self.config.goofy:
                self._recover_shake_at = 0.6
        self._was_fallen = st.fallen
        if st.fallen and self._fallen_since is not None:
            blocked = self._recover_blocked(st)
            if blocked and self._window_open:
                self._close_window("bleibt liegen – " + ("Stopp" if "Not-Aus" in blocked else blocked))
            # Selbst aufstehen nach einem Sturz (Projektregel): erst das Stopp-Fenster, dann aufstehen – nie nach
            # einem Not-Aus (2 min, auch „Stopp“ im Fenster), nie hochgehoben, nie stromlos (Ruhe)
            if (not self._recover_sent and not blocked and now - self._fallen_since > self.config.recover_delay):
                self._recover_sent = True
                self._recover_at = now
                self._recover_tries += 1
                self._close_window("steht auf")
                self.note({"type": "reflex", "message": "Steht selbst wieder auf"})
                self.fire(self.backend.init())
            elif self._recover_sent and not blocked and now - self._recover_at > RECOVER_RETRY_S:
                if self._recover_tries < RECOVER_TRIES:
                    self._recover_sent = False             # noch ein Versuch – wieder mit Stopp-Fenster
                    self._fallen_since = now
                    self._open_window(st)
                elif self._recover_tries == RECOVER_TRIES:
                    self._recover_tries += 1
                    self.note({"type": "reflex", "message": "Kommt nicht hoch – braucht Hilfe"})
        if st.picked_up and self.current is not None:
            self._cancel_all("hochgehoben")
            self.note({"type": "reflex", "message": "Hochgehoben – Bewegung gestoppt"})

    def _open_window(self, st: DuckState) -> None:
        """Vor dem Aufstehen: kurz zuhören. Die Oberfläche öffnet dafür das Mikrofon; „Stopp“ wirkt wie der Not-Aus."""
        blocked = self._recover_blocked(st)
        if blocked:
            self.note({"type": "reflex", "message": f"Bleibt liegen ({blocked})"})
            return
        self._window_open = True
        self.note({"type": "stopp_fenster", "dauer": round(self.config.recover_delay, 1),
                   "message": f"Gestürzt – hört {self.config.recover_delay:.0f} s zu: „Stopp“ hält sie liegen, "
                              "sonst steht sie selbst auf"})

    def _obstacle_reflex(self, st: DuckState, twist: Twist, guard: bool, *, hand: bool = False,
                         ziel: tuple[float, float, float] | None = None) -> Twist:
        """Hindernissen ausweichen und sie umlaufen (seit 0.33, vorher nur bremsen) – in allen Modi."""
        self.reflex_note = None
        if not guard:
            return twist
        aw = self.ausweicher
        aw.stop, aw.look = self.config.stop_distance, self.config.slow_distance
        e = aw.lenken(st, twist, hand=hand, ziel=ziel) if self.config.ausweichen else aw.bremsen(st, twist, ziel=ziel)
        self.reflex_note = e.note
        if e.note and e.seite and time.monotonic() - self._ausweich_note_at > 5.0:
            self._ausweich_note_at = time.monotonic()
            self.note({"type": "reflex", "message": e.note})
        return e.twist

    # ── direkte diskrete Befehle (für Tools/Knöpfe) ───────────────────────
    async def stand_up(self) -> IntentResult:
        t0 = time.monotonic()
        self.powering_until = t0 + 4.0
        st = self.backend.state()

        async def overtaken() -> bool:
            # Not-Aus während des Aufstehens? Dann gewinnt der Not-Aus: nichts weiter einschalten
            if self.estop_at >= t0:
                self.powering_until = 0.0
                await self.backend.stop()
                return True
            return False

        if st.sitting and st.powered and st.enabled:
            return await self.backend.do("sit_toggle")
        res = await self.backend.init()
        if await overtaken():
            return IntentResult(False, "Not-Aus – Aufstehen abgebrochen")
        if res.accepted and not self.backend.state().fallen:     # gestürzt: init steht selbst auf, enable lehnt ab
            await asyncio.sleep(0.1)
            if await overtaken():
                return IntentResult(False, "Not-Aus – Aufstehen abgebrochen")
            res2 = await self.backend.enable(True)
            if not res2.accepted:
                return res2
        return res


class IdleLife(Behavior):
    """Lebendigkeit im Leerlauf – nur Kopf, Schnabel und Pose, nie die Beine."""

    name = "leerlauf"
    channels = ("head", "mouth", "pose")
    timeout = None

    def __init__(self, seed: int | None = None) -> None:
        super().__init__()
        import random

        self.rng = random.Random(None if seed is None else seed + 1)
        self.target = Head()
        self.next_saccade = 1.5
        self.attend_until = 0.0
        self.glance_until = 0.0
        self.seen: dict[str, float] = {}
        self.mouth_until = 0.0
        self.mouth_open = 0.25

    def attend(self, seconds: float) -> None:
        self.attend_until = self.elapsed + seconds

    def tick(self, st: DuckState, dt: float) -> Command | None:
        if not (st.powered and st.enabled) or st.skill:
            return None
        from .character import TRAITS, Traits

        mood = self.engine.mood if self.engine else None
        energie = self.engine.config.energie if self.engine else 0.5
        tr = TRAITS.get(self.engine.persona, Traits()) if self.engine else Traits()
        joy = mood.joy if mood else 0.0
        frust = mood.frust if mood else 0.0
        calm = bool(mood and mood.empathic)
        t = self.elapsed
        breathe = 0.003 * tr.breathe * math.sin(t * 2 * math.pi * (0.18 if calm else 0.22 + 0.1 * energie))
        # froh: etwas aufrechter, frustriert/mitfühlend: etwas tiefer; dazu die Haltung des Charakters
        z = -0.004 + breathe + 0.006 * joy - 0.006 * frust - (0.004 if calm else 0.0) + (0.0 if calm else tr.height)
        # Zappeln (quirlige Charaktere): kleine, unregelmäßige Gewichtsverlagerung
        fidget = 0.0 if calm else tr.fidget * 0.045 * (math.sin(t * 5.3) * 0.6 + math.sin(t * 8.9 + 1.3) * 0.4)
        pose = Pose(z=z, roll=fidget).clamped()
        mouth = self.mouth_open if t < self.mouth_until else 0.0

        if self.elapsed < self.attend_until or calm:
            # zum Menschen hochschauen (der steht vor/über der Ente); mitfühlend: Kopf sanft schief
            tilt = 0.22 if calm else 0.08 * math.sin(self.elapsed * 3)
            return Command(head=Head(-0.15, -0.3 if calm else -0.35, 0.0, tilt), mouth=mouth, pose=pose)

        # Neugier: neu aufgetauchtes Objekt kurz anschauen
        for obj in st.perception.objects:
            if obj.get("art") == "möbel":
                continue
            name = obj["name"]
            last = self.seen.get(name)
            self.seen[name] = self.elapsed
            if last is None or self.elapsed - last > 8.0:
                if obj["entfernung_m"] < 1.5:
                    yaw = math.radians(obj["richtung_grad"])
                    self.target = Head(0.0, 0.25, yaw, 0.15 if yaw > 0 else -0.15).clamped()
                    self.glance_until = self.elapsed + 1.6
                    self.next_saccade = self.elapsed + 2.5
                    if self.engine:
                        self.engine.note({"type": "curious", "message": f"schaut neugierig zu: {name}"})
                    break

        if self.elapsed >= self.next_saccade and self.elapsed >= self.glance_until:
            lift = 0.12 * joy - 0.15 * frust            # froh: Blick eher nach oben
            side = self.rng.choice((-1.0, 1.0))
            self.target = Head(
                self.rng.uniform(-0.1, 0.1) + tr.neck,
                self.rng.uniform(-0.25, 0.2) - lift + tr.gaze,
                self.rng.uniform(-0.6, 0.6) * (0.6 + 0.6 * energie) * tr.reach,
                self.rng.uniform(-0.12, 0.12) + side * tr.roll,
            ).clamped()
            pace = (1.6 - 1.0 * energie - 0.3 * joy) / tr.pace     # lebhaft/froh: öfter umschauen
            self.next_saccade = self.elapsed + self.rng.uniform(1.8, 5.0) * max(0.25, pace) * tr.hold
            if self.rng.random() < max(0.12, tr.chatter):
                self.mouth_until = self.elapsed + self.rng.uniform(0.15, 0.35)
                self.mouth_open = self.rng.uniform(0.2, 0.45)
        head = self.target
        if tr.bob and not calm:
            # lebhaft: der Kopf wippt leicht mit, als liefe Musik
            bob = tr.bob * math.sin(t * 2 * math.pi * (1.6 + 0.8 * energie))
            head = Head(head.neck_pitch, head.head_pitch + bob, head.head_yaw, head.head_roll).clamped()
        return Command(head=head, mouth=mouth, pose=pose)
