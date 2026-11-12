"""Das gemeinsame Interface aller Backends.

Das Vokabular ist absichtlich das des echten Microduck-Daemons `robotd`
(pollen-robotics/microduck, `duck-ipc-proto`): `robot.move`, `robot.head`,
`robot.mouth`, `robot.pose`, `robot.do`, `robot.sound`, `robot.stop` …
Wer gegen dieses Interface programmiert, programmiert gegen den Roboter –
der Simulator ist nur ein anderer Körper.

Einheiten (wie in robotd): Meter, Sekunden, Radiant. vx = vorwärts,
vy = links, vyaw = Drehrate, positiv = links herum.
"""

from __future__ import annotations

import abc
import asyncio
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

# ── Grenzen ────────────────────────────────────────────────────────────────
# Bewusst konservativ: innerhalb dessen, worauf die Policies trainiert sind.
# Die Pose-Bereiche stammen direkt aus PoseParams in duck-ipc-proto.
LIMITS = {
    "vx": (-0.15, 0.25),
    "vy": (-0.12, 0.12),
    "vyaw": (-1.0, 1.0),
    "neck_pitch": (-1.1, 0.5),     # nach unten bis zur Trainingsgrenze – Pollens Emotionen brauchen das
    "head_pitch": (-1.1, 1.1),     # Pollen: „head_pitch und head_yaw folgen ±1 rad eins zu eins“
    "head_yaw": (-1.1, 1.1),
    "head_roll": (-0.35, 0.35),
    "pose_z": (-0.025, 0.010),
    "pose_roll": (-0.26, 0.26),
    "pose_pitch": (-0.26, 0.26),
    "mouth": (0.0, 1.0),
}

# Die Ton-Tags der Stimmbank (SoundTag in duck-ipc-proto).
SOUND_TAGS = ("alarm", "greet", "inquire", "peck", "chirp", "coo", "wheee")

# Skills, die eine Standard-Ente kann. `ground_pick` und `sit_toggle` treibt
# robotd selbst; die anderen sind One-Shot-Policies. Welche ein Roboter
# wirklich hat, fragt das robotd-Backend live ab (robot.policies).
DEFAULT_SKILLS = ("sit_toggle", "ground_pick", "kick_left", "kick_right", "roulade")

JOINT_NAMES = (
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
)


def clamp(value: float, key: str) -> float:
    lo, hi = LIMITS[key]
    if value is None or math.isnan(value):
        return 0.0
    return max(lo, min(hi, float(value)))


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


# Körper ohne Beine (Reachy Mini, seit 0.38.1): eine Antwort für Werkzeuge, Backend und Fähigkeiten
NICHT_OHNE_BEINE = "Reachy Mini hat keine Beine – laufen, schießen und aufheben geht nicht (mit dem Hoverboard später fahren)"

@dataclass
class Head:
    neck_pitch: float = 0.0
    head_pitch: float = 0.0
    head_yaw: float = 0.0
    head_roll: float = 0.0

    def clamped(self) -> "Head":
        return Head(
            clamp(self.neck_pitch, "neck_pitch"),
            clamp(self.head_pitch, "head_pitch"),
            clamp(self.head_yaw, "head_yaw"),
            clamp(self.head_roll, "head_roll"),
        )

    def as_list(self) -> list[float]:
        return [self.neck_pitch, self.head_pitch, self.head_yaw, self.head_roll]


@dataclass
class Pose:
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0

    def clamped(self) -> "Pose":
        return Pose(clamp(self.z, "pose_z"), clamp(self.roll, "pose_roll"), clamp(self.pitch, "pose_pitch"))


@dataclass
class Twist:
    vx: float = 0.0
    vy: float = 0.0
    vyaw: float = 0.0

    def clamped(self) -> "Twist":
        return Twist(clamp(self.vx, "vx"), clamp(self.vy, "vy"), clamp(self.vyaw, "vyaw"))

    def is_zero(self, eps: float = 1e-4) -> bool:
        return abs(self.vx) < eps and abs(self.vy) < eps and abs(self.vyaw) < eps


@dataclass
class IntentResult:
    """Wie robotd: `accepted: false` ist ein normales Ergebnis mit Begründung."""

    accepted: bool
    reason: str | None = None


@dataclass
class Perception:
    """Was die Ente über ihre Umgebung weiß.

    `tof_mm` ist das 8×8-Tiefenbild des Kopf-ToF (Zeilen oben → unten), wie
    `tof.frame` es liefert. `sectors` fasst es zu links/mitte/rechts zusammen
    (Meter, None = nichts in Reichweite). `objects` gibt es nur im Simulator –
    der echte Roboter hat dafür Kamera und Objekterkennung (mediad), die hier
    noch nicht angebunden sind.
    """

    tof_mm: list[int] | None = None
    sectors: dict[str, float | None] = field(default_factory=dict)
    objects: list[dict[str, Any]] = field(default_factory=list)
    source: str = "none"
    # Die gültigen Messpunkte des ToF als [x, y, z] in Metern im selben Rahmen wie DuckState.x/y
    # (Odometrie), z über dem Boden. Für die Punktwolke in der Oberfläche; siehe tof_points().
    points: list[list[float]] = field(default_factory=list)


TOF_FOV = math.radians(45)   # Öffnungswinkel des 8×8-ToF (VL53L5CX)


def tof_points(tof_mm: list[int] | None, *, x: float, y: float, yaw: float, head_yaw: float,
               tilt: float, cam_h: float, status: list[int] | None = None,
               max_mm: int = 2000) -> list[list[float]]:
    """Rechnet das 8×8-Tiefenbild in Punkte im Raum um.

    Zeile 0 = oben, Spalte 0 = links (wie tof.frame). `yaw` + `head_yaw` = Blickrichtung,
    `tilt` = Blickneigung (+ = nach unten), `cam_h` = Höhe des Sensors über dem Boden.
    Zonen ohne Treffer (Reichweite erreicht) und ungültige Zonen (Status ≠ 5/9) fallen weg.
    """
    if not tof_mm or len(tof_mm) < 64:
        return []
    pts: list[list[float]] = []
    for row in range(8):
        elev = (3.5 - row) / 8 * TOF_FOV - tilt
        ce, se = math.cos(elev), math.sin(elev)
        for col in range(8):
            i = row * 8 + col
            d = tof_mm[i]
            if not 40 < d < max_mm - 20:
                continue
            if status and len(status) > i and status[i] not in (5, 9):
                continue
            m = d / 1000.0
            az = yaw + head_yaw + (3.5 - col) / 8 * TOF_FOV
            horiz = m * ce
            pts.append([round(x + horiz * math.cos(az), 3), round(y + horiz * math.sin(az), 3),
                        round(max(0.0, cam_h + m * se), 3)])
    return pts


@dataclass
class DuckState:
    t: float = 0.0
    connected: bool = False
    backend: str = ""
    # Odometrie: Position im Startrahmen
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    twist: Twist = field(default_factory=Twist)        # tatsächlich angewendet
    requested: Twist = field(default_factory=Twist)    # angefordert
    limited_by: list[str] = field(default_factory=list)
    head: Head = field(default_factory=Head)
    mouth: float = 0.0
    pose: Pose = field(default_factory=Pose)
    # Zustand
    powered: bool = False       # Motoren unter Strom (nicht limp)
    enabled: bool = False       # Policy läuft
    sitting: bool = False
    fallen: bool = False
    picked_up: bool = False
    skill: str | None = None    # laufender One-Shot
    skill_progress: float = 0.0
    fall_side: float = 1.0
    holding: str | None = None  # was im Schnabel ist (nur Simulator)
    gait_phase: float = 0.0
    battery: float | None = None
    perception: Perception = field(default_factory=Perception)
    joints: list[float] = field(default_factory=list)          # gemessen (robotd) bzw. simuliert
    display_joints: list[float] = field(default_factory=list)  # für den 3D-Viewer
    body: list[float] = field(default_factory=list)      # Physik: Rumpfhöhe (m), Rollen, Kippen (rad)
    body_q: list[float] = field(default_factory=list)    # Physik: Lage des Rumpfs als Quaternion (w, x, y, z), Welt
    physik: dict[str, Any] | None = None                 # Physik: Motormodell, laufende Policy
    kopf_stabil: bool = False                            # Kopf-Stabilisator an (Kopf bleibt ruhig wie beim Huhn)
    ruck: dict[str, Any] | None = None                   # letzte Erschütterung von außen {n, staerke 0…1, quelle} – Vibrieren
    koerper: str = "microduck"                           # welcher Körper (seit 0.38.1: „reachy_mini“)
    antennen: list[float] = field(default_factory=list)  # Reachy Mini: Antennen [rechts, links] in rad
    kopf_lage: dict[str, float] = field(default_factory=dict)  # Reachy Mini: Kopflage {z, roll, pitch, yaw} relativ zum Körper
    stand_z: float = 0.0                                 # Höhe der Standfläche über dem Boden (m) – Reachy auf dem Tisch
    werkbank: dict[str, Any] = field(default_factory=dict)  # SO-101: Würfel und Kisten im Sockelrahmen (seit 0.38.48)
    standflaeche: str = ""                               # worauf er steht („“ = Boden)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        """Ein Satz für Logs und für Claude."""
        if not self.connected:
            return "nicht verbunden"
        if self.fallen:
            posture = "umgefallen"
        elif not self.powered:
            posture = "stromlos (limp)"
        elif self.sitting:
            posture = "sitzt"
        else:
            posture = "steht" if self.twist.is_zero(0.02) else "läuft"
        parts = [posture]
        if self.skill:
            parts.append(f"führt '{self.skill}' aus")
        if self.holding:
            parts.append(f"hält {self.holding} im Schnabel")
        return ", ".join(parts)


EventListener = Callable[[dict[str, Any]], None]


class DuckBackend(abc.ABC):
    """Ein Körper für die Ente: simuliert oder echt.

    Kontinuierliche Intents (move, head, mouth, pose) müssen laufend neu
    gesendet werden – robotd nullt die Geschwindigkeit nach 500 ms ohne Intent
    (Totmann). Das erledigt die MotionEngine mit 20 Hz.
    """

    runs_policies = False        # kann Policies vom Hub ausführen (echter Roboter, Physik-Simulator)
    expressing = False           # läuft gerade ein Ausdruck (Gefühl, Tanz, Choreografie)? Setzt die MotionEngine.

    name = "abstract"

    def __init__(self) -> None:
        from .motion.stabilizer import HeadStabilizer

        self._listeners: list[EventListener] = []
        self.stabilizer = HeadStabilizer()

    def eigenschaften(self) -> frozenset[str]:
        """Was dieser Körper kann (seit 0.38, statt hier und da `hasattr`): Fähigkeiten prüfen damit ihre Vorbedingung.
        beine, kopf, schnabel, tiefensensor, policies, simulator, zuruecksetzen …"""
        return frozenset({"beine", "kopf", "schnabel", "stimmbank"})

    def gespraech(self, zustand: str | None, sekunden: float = 4.0) -> None:
        """Wo das Gespräch steht (seit 0.38.2): „zuhoeren“, „denkt“ oder None. Körper mit eigenem Ausdruck (Reachy Mini)
        zeigen es; die Microduck macht das über die Engine (Aufschauen beim Zuhören) und überhört es hier."""
        return None

    def set_stabilize(self, on: bool) -> None:
        """Kopf-Stabilisator an/aus – die Kopfgelenke gleichen Wackeln und Drehen des Rumpfs aus."""
        self.stabilizer.enabled = bool(on)
        self.stabilizer.reset()

    # ── Ereignisse (Töne, Stürze, Kollisionen …) ──────────────────────────
    def on_event(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def emit(self, kind: str, **data: Any) -> None:
        event = {"type": kind, **data}
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:  # ein kaputter Zuhörer darf die Ente nicht stoppen
                pass

    # ── Lebenszyklus ──────────────────────────────────────────────────────
    @abc.abstractmethod
    async def connect(self) -> None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    @abc.abstractmethod
    def state(self) -> DuckState: ...

    def world(self) -> dict[str, Any] | None:
        """Geometrie der Umgebung für den Viewer, falls bekannt."""
        return None

    def skills(self) -> list[str]:
        return list(DEFAULT_SKILLS)

    def joint_report(self) -> dict[str, Any]:
        """Gelenk-Check (siehe joints.py). Standard: nur die Winkel, ohne Soll und Last."""
        from .joints import build

        st = self.state()
        return build(st.joints or st.display_joints, quelle=self.name, aktiv=st.powered and not st.fallen,
                     hinweis="Dieser Körper meldet nur Winkel – Nachlauf und Last gibt es im Physik-Simulator "
                             "und am echten Roboter.")

    # ── kontinuierliche Intents ───────────────────────────────────────────
    @abc.abstractmethod
    async def move(self, twist: Twist) -> None: ...

    @abc.abstractmethod
    async def head(self, head: Head) -> None: ...

    @abc.abstractmethod
    async def mouth(self, open_: float) -> None: ...

    @abc.abstractmethod
    async def pose(self, pose: Pose, active: bool = True) -> None: ...

    # ── diskrete Befehle ──────────────────────────────────────────────────
    @abc.abstractmethod
    async def init(self) -> IntentResult:
        """Motoren an, in die Grundstellung fahren (robot.init)."""

    @abc.abstractmethod
    async def enable(self, on: bool) -> IntentResult:
        """Policy an/aus (robot.enable)."""

    @abc.abstractmethod
    async def stop(self) -> IntentResult:
        """Geschwindigkeit null – nicht 'schlapp werden' (robot.stop)."""

    @abc.abstractmethod
    async def do(self, skill: str) -> IntentResult:
        """One-Shot-Skill oder sit_toggle (robot.do)."""

    async def haltung(self, gelenke: dict[str, float], sekunden: float) -> IntentResult:
        """Eine Haltung der Beine kurz einnehmen und halten (Posen im Tanz, seit 0.36). Nur die echte Physik kann das;
        am Roboter nimmt robotd für die Beine nur Policies an."""
        return IntentResult(False, "Posen der Beine gehen nur im Simulator mit echter Physik "
                                   "(am Roboter erst mit einer trainierten Policy)")

    @abc.abstractmethod
    async def sound(self, tag: str) -> IntentResult: ...

    @abc.abstractmethod
    async def rest(self) -> IntentResult:
        """Hinsetzen und Motoren aus (robot.rest)."""

    async def relax(self) -> IntentResult:
        """Not-Aus: sofort stromlos (robot.relax) – die Gelenke lassen los, sie sackt zusammen. Seit 0.38.24 (Hinweis: „Not-Aus dachte ich legt den Roboter sofort lahm – bricht aber nur die aktuelle Aufgabe ab“).
        Körper ohne eigenes „stromlos“ legen sich so schnell wie möglich schlafen."""
        return await self.rest()

    async def add_trick(self, repo: str, name: str | None = None, seconds: float | None = None,
                        file: str | None = None) -> IntentResult:
        """Eine Policy vom Hugging Face Hub als Skill auf den Roboter laden (nur echter Roboter)."""
        return IntentResult(False, "Tricks vom Hub laufen nur auf dem echten Roboter – im Simulator gibt es "
                                   "keine neuronalen Policies. Ich merke ihn mir für später.")

    async def load_gait(self, repo: str, slot: str = "walk", file: str | None = None) -> IntentResult:
        """Eine Gangart vom Hub in einen festen Platz laden (robot.loadPolicy) – nur echter Roboter."""
        return IntentResult(False, "Gangarten tauschen geht nur am echten Roboter – der Simulator läuft mit seiner eingebauten.")

    async def reset_gait(self, slot: str = "walk") -> IntentResult:
        """Den Platz wieder auf Pollens Standard setzen."""
        return IntentResult(False, "Im Simulator gibt es nur die eingebaute Gangart.")

    async def look(self, x: float, y: float, z: float) -> Head:
        """Auf einen Punkt im Rumpf-Rahmen schauen. Standard: einfache Geometrie."""
        yaw = math.atan2(y, max(1e-3, x))
        pitch = -math.atan2(z, math.hypot(x, y))
        target = Head(0.0, pitch, yaw, 0.0).clamped()
        await self.head(target)
        return target


async def sleep_until(predicate: Callable[[], bool], timeout: float, step: float = 0.05) -> bool:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if predicate():
            return True
        await asyncio.sleep(step)
    return predicate()
