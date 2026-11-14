"""Choreografien: frei komponierte Bewegung aus Keyframes, dazu die Gesten- und Gefühlskataloge
(eigene, Charakter, Pollens 14 Emotionen, Albernheiten) – seit 0.38.17 aus behaviors.py ausgelagert.
`behaviors` reicht alles weiter, bestehende Importe gelten weiter.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from ..api import Head, Pose, Twist
from .engine import Behavior, Command
from .hilfen import DEG, _ohne_entenlaute, smoothstep
from .sounds import mouth as sound_mouth
from .sounds import with_sound

_LAST_CLIP: dict[str, str] = {}


def pick_clip(clips: list[str]) -> str:
    """Eine Variante – nie dieselbe wie beim letzten Mal."""
    key = clips[0]
    options = [c for c in clips if c != _LAST_CLIP.get(key)] or clips
    clip = random.choice(options)
    _LAST_CLIP[key] = clip
    return clip


@dataclass
class Keyframe:
    t: float
    head: Head | None = None
    mouth: float | None = None
    pose: Pose | None = None
    twist: Twist | None = None
    sound: str | None = None
    skill: str | None = None
    clip: list[str] | None = None     # aufgenommener Ton (Pollens Emotionen), spielt der PC ab
    antennen: tuple[float, float] | None = None   # Reachy Mini: [rechts, links] in Grad, + = nach außen (seit 0.38.10)


class Choreography(Behavior):
    """Frei komponierte Bewegung aus Keyframes – das Werkzeug für situative,
    dynamische Bewegungen, die Claude sich ausdenkt.

    Kopf/Schnabel/Pose werden weich (smoothstep) zwischen Keyframes
    interpoliert, Fahrbefehle gelten stufenweise bis zum nächsten Keyframe,
    Töne und Skills feuern genau zum Zeitpunkt ihres Keyframes.
    """

    name = "choreografie"
    channels = ("base", "head", "mouth", "pose")

    def __init__(self, keyframes: list[Keyframe], loops: int = 1, title: str = "") -> None:
        super().__init__()
        if not keyframes:
            raise ValueError("Choreografie ohne Keyframes")
        self.kfs = sorted(keyframes, key=lambda k: k.t)
        # nur Kopf, Schnabel, Haltung und Töne? Dann geht es auch im Sitzen (kein Aufstehen, kein Warten)
        self.needs_legs = any((k.twist is not None and not k.twist.is_zero()) or k.skill for k in self.kfs)
        if self.kfs[0].t > 0:
            self.kfs.insert(0, Keyframe(0.0))
        # Dicht abgetastete Bewegungen (Pollens Emotionen, alle 0,1 s) linear verbinden –
        # Smoothstep würde an jedem Stützpunkt kurz anhalten und ruckeln.
        gaps = [b.t - a.t for a, b in zip(self.kfs, self.kfs[1:])]
        self.linear = len(gaps) >= 8 and sorted(gaps)[len(gaps) // 2] <= 0.12
        self.length = max(0.3, self.kfs[-1].t)
        self.loops = max(1, min(20, loops))
        self.title = title
        self.timeout = self.length * self.loops + 5
        self._fired: set[tuple[int, int]] = set()
        self._voices: list[tuple[int, float, list[float]]] = []   # (Durchlauf, Start, Schnabel 10 Hz)
        self.overlay = False          # als Einlage (Engine.play_overlay): keine Skills, Beine laufen weiter

    @classmethod
    def from_spec(cls, spec: list[dict[str, Any]], loops: int = 1, title: str = "", scale: float = 1.0) -> "Choreography":
        """Keyframes in Grad/Millimetern – so schreibt Claude sie.

        `scale` macht Kopf- und Körperbewegungen kleiner (ruhiges Temperament) oder größer
        (lebhaft) – immer innerhalb der erlaubten Grenzen. Fahrbefehle bleiben unverändert.
        """
        kfs = []
        k = max(0.3, min(1.4, scale))
        for raw in spec[:240]:
            kf = Keyframe(float(raw.get("t", 0.0)))
            if "kopf" in raw or "head" in raw:
                h = raw.get("kopf") or raw.get("head") or {}
                kf.head = Head(
                    -h.get("nacken", h.get("neck", 0.0)) * DEG * k,   # nacken + = nach vorn/unten; Roboter: neck_pitch < 0
                    h.get("nicken", h.get("pitch", 0.0)) * DEG * k,
                    h.get("drehen", h.get("yaw", 0.0)) * DEG * k,
                    h.get("neigen", h.get("roll", 0.0)) * DEG * k,
                ).clamped()
            if "schnabel" in raw or "mouth" in raw:
                kf.mouth = max(0.0, min(1.0, float(raw.get("schnabel", raw.get("mouth", 0.0)))))
            if "koerper" in raw or "pose" in raw:
                p = raw.get("koerper") or raw.get("pose") or {}
                kf.pose = Pose(
                    p.get("hoehe_mm", p.get("z_mm", 0.0)) / 1000.0 * k,
                    p.get("rollen", p.get("roll", 0.0)) * DEG * k,
                    p.get("kippen", p.get("pitch", 0.0)) * DEG * k,
                ).clamped()
            if "fahren" in raw or "move" in raw:
                m = raw.get("fahren") or raw.get("move") or {}
                kf.twist = Twist(m.get("vx", 0.0), m.get("vy", 0.0), m.get("drehrate_grad", m.get("vyaw_deg", 0.0)) * DEG).clamped()
            kf.sound = raw.get("ton") or raw.get("sound")
            kf.skill = raw.get("skill")
            ant = raw.get("antennen")
            if isinstance(ant, (list, tuple)) and len(ant) == 2:
                kf.antennen = (max(-170.0, min(170.0, float(ant[0]))), max(-170.0, min(170.0, float(ant[1]))))
            clip = raw.get("klang")
            if clip:
                kf.clip = [clip] if isinstance(clip, str) else [str(c) for c in clip]
            kfs.append(kf)
        # Ton mit Verzögerung (klang_bei): an den Keyframe hängen, der dann dran ist
        for raw, kf in zip(spec, kfs):
            delay = float(raw.get("klang_bei") or 0.0)
            if kf.clip and delay > 0 and (kf.head is not None or kf.pose is not None):
                later = min((k for k in kfs if k.t >= kf.t + delay - 1e-6), key=lambda k: k.t, default=kf)
                if later is not kf:
                    later.clip, kf.clip = kf.clip, None
        return cls(kfs, loops, title)

    def _interp(self, attr: str, t: float):
        prev = nxt = None
        for kf in self.kfs:
            if getattr(kf, attr) is None:
                continue
            if kf.t <= t:
                prev = kf
            elif nxt is None:
                nxt = kf
                break
        if prev is None and nxt is None:
            return None
        if prev is None:
            prev = Keyframe(0.0, Head(), 0.0, Pose())
        a = getattr(prev, attr)
        if nxt is None:
            return a
        b = getattr(nxt, attr)
        x = (t - prev.t) / max(1e-3, nxt.t - prev.t)
        k = max(0.0, min(1.0, x)) if self.linear else smoothstep(x)
        if isinstance(a, float):
            return a + (b - a) * k
        return type(a)(*[x + (y - x) * k for x, y in zip(vars(a).values(), vars(b).values())])

    def tick(self, st, dt):
        total = self.length * self.loops
        if self.elapsed >= total:
            return self.finish("Choreografie beendet")
        loop = int(self.elapsed // self.length)
        t = self.elapsed - loop * self.length
        stumm = self.engine is not None and _ohne_entenlaute(self.engine.backend)
        for i, kf in enumerate(self.kfs):
            if kf.t <= t and (loop, i) not in self._fired:
                self._fired.add((loop, i))
                if kf.sound and self.engine and not stumm:
                    self.engine.fire(self.engine.backend.sound(kf.sound))
                if kf.skill and self.engine and not self.overlay:
                    if kf.skill == "hinsetzen":          # Pollen: Am-Boden/Tot-stellen setzen sich hin – nur wenn sie steht
                        if not st.sitting:
                            self.engine.fire(self.engine.backend.do("sit_toggle"))
                    else:
                        self.engine.fire(self.engine.backend.do(kf.skill))
                if kf.antennen is not None and self.engine:
                    self._antennen(i, kf)
                if kf.clip and self.engine and not stumm:
                    clip = pick_clip(kf.clip)
                    self.engine.note({"type": "sound", "clip": clip})
                    track = sound_mouth(clip)
                    if track:
                        self._voices.append((loop, kf.t, track))
        twist = None
        for kf in self.kfs:
            if kf.twist is not None and kf.t <= t:
                twist = kf.twist
        return Command(
            twist=twist or Twist(),
            head=self._interp("head", t),
            mouth=self._voice_mouth(loop, t, self._interp("mouth", t)),
            pose=self._interp("pose", t),
        )

    def _antennen(self, i: int, kf: Keyframe) -> None:
        """Antennen (nur Körper, die welche haben) bis zum nächsten Antennen-Keyframe halten."""
        setzen = getattr(self.engine.backend, "antennen_setzen", None)
        if setzen is None or kf.antennen is None:
            return
        weiter = next((k.t for k in self.kfs[i + 1:] if k.antennen is not None), None)
        dauer = (weiter - kf.t + 0.25) if weiter is not None else 0.6
        self.engine.fire(setzen(-math.radians(kf.antennen[0]), math.radians(kf.antennen[1]), max(0.3, dauer)))

    def _voice_mouth(self, loop: int, t: float, mouth: float | None) -> float | None:
        """Der Schnabel öffnet mit dem Laut – wie bei Pollens Emotionen (aus der Lautstärke, 10 Hz)."""
        for lp, start, track in self._voices:
            if lp != loop:
                continue
            x = (t - start) / 0.1
            i = int(x)
            if 0 <= i < len(track):
                nxt = track[i + 1] if i + 1 < len(track) else 0.0
                level = 0.85 * (track[i] + (nxt - track[i]) * (x - i))
                mouth = max(mouth or 0.0, level)
        return mouth

    def describe(self):
        label = f" '{self.title}'" if self.title else ""
        return f"choreografie{label} ({len(self.kfs)} Keyframes, {self.length:.1f}s × {self.loops})"


# Gefühle als fertige Choreografien – Claude kann sie direkt aufrufen oder als
# Vorlage für eigene nehmen.
EMOTIONS: dict[str, list[dict[str, Any]]] = {
    "freude": [
        {"t": 0.0, "kopf": {"nicken": -15}, "ton": "greet"},
        {"t": 0.3, "kopf": {"nicken": -25, "neigen": 12}, "schnabel": 0.6, "koerper": {"rollen": 8}},
        {"t": 0.6, "kopf": {"nicken": -20, "neigen": -12}, "schnabel": 0.1, "koerper": {"rollen": -8}},
        {"t": 0.9, "kopf": {"nicken": -25, "neigen": 12}, "schnabel": 0.6, "koerper": {"rollen": 8}},
        {"t": 1.2, "kopf": {"nicken": -20, "neigen": -12}, "schnabel": 0.0, "koerper": {"rollen": -8}, "ton": "chirp"},
        {"t": 1.8, "kopf": {}, "koerper": {}},
    ],
    "traurig": [
        {"t": 0.0, "kopf": {"nicken": 10}},
        {"t": 1.2, "kopf": {"nicken": 35, "nacken": 20, "neigen": 8}, "koerper": {"hoehe_mm": -20, "kippen": 8}, "ton": "coo"},
        {"t": 3.0, "kopf": {"nicken": 35, "nacken": 20, "neigen": 8}, "koerper": {"hoehe_mm": -20, "kippen": 8}},
        {"t": 4.0, "kopf": {}, "koerper": {}},
    ],
    "neugierig": [
        {"t": 0.0, "kopf": {"drehen": 0}},
        {"t": 0.5, "kopf": {"neigen": 18, "nicken": -5, "drehen": 10}, "ton": "inquire"},
        {"t": 1.3, "kopf": {"neigen": 18, "nicken": 5, "drehen": 15}},
        {"t": 1.8, "kopf": {"neigen": -15, "nicken": 0, "drehen": -10}},
        {"t": 2.6, "kopf": {}},
    ],
    "ueberrascht": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.15, "kopf": {"nicken": -30, "nacken": -15}, "schnabel": 1.0, "koerper": {"hoehe_mm": 8, "kippen": -10}, "ton": "alarm"},
        {"t": 1.0, "kopf": {"nicken": -25, "nacken": -10}, "schnabel": 0.6, "koerper": {"hoehe_mm": 8}},
        {"t": 1.8, "kopf": {}, "schnabel": 0.0, "koerper": {}},
    ],
    "muede": [
        {"t": 0.0, "kopf": {}},
        {"t": 1.0, "kopf": {"nicken": 25, "nacken": 15}, "schnabel": 0.7, "koerper": {"hoehe_mm": -18}, "ton": "coo"},
        {"t": 1.6, "kopf": {"nicken": 15}, "schnabel": 0.0},
        {"t": 2.6, "kopf": {"nicken": 35, "nacken": 22, "neigen": 10}, "koerper": {"hoehe_mm": -22}},
        {"t": 4.0, "kopf": {"nicken": 35, "nacken": 22, "neigen": 10}, "koerper": {"hoehe_mm": -22}},
        {"t": 5.0, "kopf": {}, "koerper": {}},
    ],
    "wuetend": [
        {"t": 0.0, "kopf": {"nicken": 10}, "koerper": {"kippen": 10, "hoehe_mm": -10}},
        {"t": 0.3, "kopf": {"nicken": 15, "drehen": 15}, "schnabel": 1.0, "ton": "alarm"},
        {"t": 0.5, "kopf": {"nicken": 15, "drehen": -15}, "schnabel": 0.2},
        {"t": 0.7, "kopf": {"nicken": 15, "drehen": 15}, "schnabel": 1.0},
        {"t": 0.9, "kopf": {"nicken": 15, "drehen": -15}, "schnabel": 0.0},
        {"t": 1.6, "kopf": {}, "koerper": {}},
    ],
    "ja": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.25, "kopf": {"nicken": 25}}, {"t": 0.5, "kopf": {"nicken": -10}},
        {"t": 0.75, "kopf": {"nicken": 25}}, {"t": 1.0, "kopf": {"nicken": -5}, "ton": "chirp"},
        {"t": 1.3, "kopf": {}},
    ],
    "nein": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.25, "kopf": {"drehen": 30}}, {"t": 0.55, "kopf": {"drehen": -30}},
        {"t": 0.85, "kopf": {"drehen": 30}}, {"t": 1.15, "kopf": {"drehen": -25}},
        {"t": 1.5, "kopf": {}},
    ],
    "begruessen": [
        {"t": 0.0, "kopf": {"nicken": -20, "nacken": -10}},
        {"t": 0.4, "kopf": {"nicken": -30, "neigen": 15}, "schnabel": 0.8, "ton": "greet"},
        {"t": 0.8, "kopf": {"nicken": -25, "neigen": -10}, "schnabel": 0.0, "fahren": {"drehrate_grad": 35}},
        {"t": 1.2, "kopf": {"nicken": -25, "neigen": 10}, "fahren": {"drehrate_grad": -35}},
        {"t": 1.6, "kopf": {"nicken": 20}, "koerper": {"kippen": 12, "hoehe_mm": -10}, "fahren": {}},
        {"t": 2.2, "kopf": {}, "koerper": {}},
    ],

    # ── Gefühle aus der Situation ────────────────────────────────────────
    "begeistert": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.15, "kopf": {"nicken": -28, "nacken": -12}, "koerper": {"hoehe_mm": 9, "kippen": -8}, "schnabel": 0.9, "ton": "greet"},
        {"t": 0.40, "kopf": {"nicken": -20, "neigen": 14}, "koerper": {"hoehe_mm": -6, "rollen": 9}, "schnabel": 0.3},
        {"t": 0.62, "kopf": {"nicken": -26, "neigen": -14}, "koerper": {"hoehe_mm": 8, "rollen": -9}, "schnabel": 0.9},
        {"t": 0.84, "kopf": {"nicken": -20, "neigen": 12}, "koerper": {"hoehe_mm": -6, "rollen": 8}, "schnabel": 0.2, "ton": "chirp"},
        {"t": 1.06, "kopf": {"nicken": -24}, "koerper": {"hoehe_mm": 6}, "schnabel": 0.8},
        {"t": 1.60, "kopf": {}, "koerper": {}, "schnabel": 0.0},
    ],
    "frustriert": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.3, "kopf": {"nicken": 22, "nacken": 12}, "koerper": {"hoehe_mm": -14, "kippen": 6}, "ton": "coo"},
        {"t": 0.8, "kopf": {"nicken": 22, "nacken": 12, "drehen": 18}},
        {"t": 1.1, "kopf": {"nicken": 22, "nacken": 12, "drehen": -18}},
        {"t": 1.4, "kopf": {"nicken": 22, "nacken": 12, "drehen": 12}, "koerper": {"hoehe_mm": -14, "kippen": 10}, "schnabel": 0.4, "ton": "peck"},
        {"t": 1.6, "schnabel": 0.0},
        {"t": 2.2, "kopf": {"nicken": -6}, "koerper": {"hoehe_mm": 4}},
        {"t": 2.7, "kopf": {}, "koerper": {}},
    ],
    "erleichtert": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.5, "kopf": {"nicken": -18, "nacken": -8}, "koerper": {"hoehe_mm": 8}, "schnabel": 0.5},
        {"t": 1.2, "kopf": {"nicken": 10, "neigen": 8}, "koerper": {"hoehe_mm": -12}, "schnabel": 0.2, "ton": "coo"},
        {"t": 1.8, "kopf": {"nicken": -10, "neigen": 8}, "koerper": {"hoehe_mm": 0}, "ton": "chirp"},
        {"t": 2.3, "kopf": {}, "koerper": {}, "schnabel": 0.0},
    ],
    "stolz": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.4, "kopf": {"nicken": -22, "nacken": -10, "drehen": 12}, "koerper": {"hoehe_mm": 9, "kippen": -10}, "ton": "greet"},
        {"t": 1.3, "kopf": {"nicken": -22, "nacken": -10, "drehen": -12}, "koerper": {"hoehe_mm": 9, "kippen": -10}},
        {"t": 1.7, "kopf": {"nicken": -16}, "schnabel": 0.6, "ton": "chirp"},
        {"t": 1.9, "schnabel": 0.0},
        {"t": 2.4, "kopf": {}, "koerper": {}},
    ],
    "einfuehlsam": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.9, "kopf": {"nicken": -12, "neigen": 16, "nacken": -6}, "koerper": {"hoehe_mm": -8}, "ton": "coo"},
        {"t": 2.2, "kopf": {"nicken": -14, "neigen": 18, "nacken": -6}, "koerper": {"hoehe_mm": -8}},
        {"t": 3.0, "kopf": {"nicken": -10, "neigen": 10}, "schnabel": 0.2},
        {"t": 3.8, "kopf": {"nicken": -8, "neigen": 8}, "koerper": {"hoehe_mm": -4}, "schnabel": 0.0},
    ],
    # ── Goofy-Modus ──────────────────────────────────────────────────────
    # Schütteln wie nasses Gefieder, dazu gackern – danach geht es normal weiter.
    "schuetteln": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.10, "kopf": {"drehen": 22, "neigen": 16}, "koerper": {"rollen": 13}, "schnabel": 0.8, "ton": "chirp"},
        {"t": 0.22, "kopf": {"drehen": -22, "neigen": -16}, "koerper": {"rollen": -13}, "schnabel": 0.1},
        {"t": 0.34, "kopf": {"drehen": 20, "neigen": 15}, "koerper": {"rollen": 12}, "schnabel": 0.8, "ton": "chirp"},
        {"t": 0.46, "kopf": {"drehen": -18, "neigen": -14}, "koerper": {"rollen": -11}, "schnabel": 0.1},
        {"t": 0.58, "kopf": {"drehen": 12, "neigen": 10}, "koerper": {"rollen": 7}, "schnabel": 0.7, "ton": "peck"},
        {"t": 0.70, "kopf": {"drehen": -8, "neigen": -6}, "koerper": {"rollen": -5}, "schnabel": 0.1},
        {"t": 0.80, "kopf": {"nicken": -8}, "schnabel": 0.9, "ton": "chirp"},
        {"t": 0.92, "kopf": {"nicken": -14}, "schnabel": 0.2, "ton": "chirp"},
        {"t": 1.06, "kopf": {"nicken": -18, "neigen": 8}, "schnabel": 0.8, "ton": "chirp"},
        {"t": 1.30, "kopf": {"nicken": -10, "neigen": 10}, "schnabel": 0.0},
        {"t": 1.70, "kopf": {}, "koerper": {}, "schnabel": 0.0},
    ],
    # Kopf hoch, weggedreht, kurzes „Nö“ – Trotz, nie lange.
    "trotzig": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.35, "kopf": {"drehen": 50, "nicken": -24, "neigen": -10}, "koerper": {"kippen": -9, "hoehe_mm": 6}, "ton": "peck"},
        {"t": 1.10, "kopf": {"drehen": 52, "nicken": -26, "neigen": -12}, "koerper": {"kippen": -9, "hoehe_mm": 6}, "schnabel": 0.0},
        {"t": 1.30, "kopf": {"drehen": 55, "nicken": -24}, "schnabel": 0.4, "ton": "peck"},
        {"t": 1.45, "kopf": {"drehen": 55, "nicken": -24}, "schnabel": 0.0},
        {"t": 1.90, "kopf": {"drehen": 18, "nicken": -10, "neigen": 8}},
        {"t": 2.40, "kopf": {"drehen": 18, "nicken": -10, "neigen": 8}, "ton": "inquire"},
        {"t": 2.80, "kopf": {}, "koerper": {}},
    ],
    # Gespieltes Stolpern – der Körper bleibt im trainierten Bereich, die Ente fällt nicht.
    "stolpern": [
        {"t": 0.0, "kopf": {}, "koerper": {}},
        {"t": 0.12, "kopf": {"nicken": 30, "nacken": 18}, "koerper": {"kippen": 14, "hoehe_mm": -18}, "schnabel": 1.0, "ton": "alarm"},
        {"t": 0.34, "kopf": {"neigen": 18, "drehen": 15}, "koerper": {"rollen": 14, "kippen": 4}, "schnabel": 0.6},
        {"t": 0.54, "kopf": {"neigen": -18, "drehen": -15}, "koerper": {"rollen": -14}, "schnabel": 0.8},
        {"t": 0.76, "kopf": {"neigen": 8}, "koerper": {"rollen": 6}, "schnabel": 0.2},
        {"t": 1.00, "kopf": {}, "koerper": {}, "schnabel": 0.0},
    ],
    "verlegen": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.5, "kopf": {"nicken": 25, "neigen": 18, "drehen": -15}, "koerper": {"hoehe_mm": -10}, "ton": "coo"},
        {"t": 1.4, "kopf": {"nicken": 15, "neigen": 18, "drehen": 10}},
        {"t": 1.9, "kopf": {"nicken": -5, "neigen": 10, "drehen": 5}, "schnabel": 0.3, "ton": "chirp"},
        {"t": 2.3, "kopf": {}, "koerper": {}, "schnabel": 0.0},
    ],
    "staunen": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.25, "kopf": {"nicken": -30, "nacken": -18}, "koerper": {"hoehe_mm": 8, "kippen": -10}, "schnabel": 1.0, "ton": "inquire"},
        {"t": 1.2, "kopf": {"nicken": -28, "nacken": -16, "neigen": 12}, "schnabel": 0.8},
        {"t": 1.8, "kopf": {"nicken": -28, "nacken": -16, "neigen": -12}, "schnabel": 1.0, "ton": "greet"},
        {"t": 2.5, "kopf": {}, "koerper": {}, "schnabel": 0.0},
    ],
}


# Pollens 14 Emotionen (Apache-2.0) – Bewegung und Ton zusammen entworfen, vom Roboter-Team.
def _load_pollen() -> dict[str, dict[str, Any]]:
    import json
    from pathlib import Path

    path = Path(__file__).with_name("pollen_emotions.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))["emotionen"]
    except (OSError, ValueError, KeyError):
        return {}


# Eigene Gesten mit eigenen Lauten im Stil von Pollens Emotionen (tools/render_gestures.py) –
# statt einzelner Stimmbank-Töne, die schnell eintönig klingen.
OWN = tuple(EMOTIONS)
for _name in OWN:
    EMOTIONS[_name] = with_sound(_name, EMOTIONS[_name])

# Gesten des Charakters im Leerlauf (gähnen, Gefieder putzen, niesen …) – auch einzeln abrufbar
from .character import GESTURES as _CHARACTER_GESTURES  # noqa: E402 – character braucht die Choreografie oben

CHARACTER = tuple(_CHARACTER_GESTURES)
for _name, _spec in _CHARACTER_GESTURES.items():
    EMOTIONS[_name] = with_sound(_name, _spec)

POLLEN = _load_pollen()
for _name, _e in POLLEN.items():
    EMOTIONS[_name] = _e["spec"]


# Albernheiten für den Leerlauf. "dreht" = braucht die Beine (nur auf der Stelle).
ANTICS: dict[str, dict[str, Any]] = {
    "schwanz_jagen": {"beine": True, "nachricht": "jagt den eigenen Schwanz", "spec": [
        {"t": 0.0, "kopf": {"drehen": -45, "nicken": 15, "neigen": -10}, "ton": "inquire"},
        {"t": 0.3, "fahren": {"drehrate_grad": -57}, "kopf": {"drehen": -55, "nicken": 18, "neigen": -12}},
        {"t": 1.5, "ton": "chirp", "schnabel": 0.8},
        {"t": 1.7, "schnabel": 0.0},
        {"t": 3.0, "ton": "chirp", "schnabel": 0.8},
        {"t": 3.2, "schnabel": 0.0},
        {"t": 6.6, "fahren": {}, "kopf": {"drehen": 0, "nicken": -10, "neigen": 15}, "ton": "inquire"},
        {"t": 7.4, "kopf": {}},
    ]},
    "boden_picken": {"beine": False, "nachricht": "pickt am Boden herum", "spec": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.3, "kopf": {"nicken": 35, "nacken": 22}, "schnabel": 0.5, "ton": "peck"},
        {"t": 0.5, "kopf": {"nicken": 15, "nacken": 10}, "schnabel": 0.0},
        {"t": 0.7, "kopf": {"nicken": 35, "nacken": 22, "drehen": 10}, "schnabel": 0.5, "ton": "peck"},
        {"t": 0.9, "kopf": {"nicken": 15, "nacken": 10}, "schnabel": 0.0},
        {"t": 1.1, "kopf": {"nicken": 35, "nacken": 22, "drehen": -10}, "schnabel": 0.5, "ton": "peck"},
        {"t": 1.5, "kopf": {"nicken": -15, "neigen": 15}, "schnabel": 0.0},
        {"t": 2.1, "kopf": {"nicken": -15, "neigen": 15}, "ton": "inquire"},
        {"t": 2.6, "kopf": {}},
    ]},
    "selbstgespraech": {"beine": False, "nachricht": "erzählt sich selbst etwas", "spec": [
        {"t": 0.0, "kopf": {}},
        {"t": 0.3, "kopf": {"drehen": 30, "neigen": 12}, "schnabel": 0.7, "ton": "chirp"},
        {"t": 0.5, "schnabel": 0.1},
        {"t": 0.7, "kopf": {"drehen": -30, "neigen": -12}, "schnabel": 0.7, "ton": "inquire"},
        {"t": 1.0, "schnabel": 0.1},
        {"t": 1.4, "kopf": {"drehen": 0, "nicken": 10}, "schnabel": 0.6, "ton": "coo"},
        {"t": 2.0, "kopf": {}, "schnabel": 0.0},
    ]},
    "wackeln": {"beine": False, "nachricht": "wackelt mit dem Hintern", "spec": [
        {"t": 0.0, "koerper": {}},
        {"t": 0.2, "koerper": {"rollen": 12, "kippen": 8}, "kopf": {"neigen": -10}},
        {"t": 0.4, "koerper": {"rollen": -12, "kippen": 8}, "kopf": {"neigen": 10}, "ton": "chirp"},
        {"t": 0.6, "koerper": {"rollen": 12, "kippen": 8}, "kopf": {"neigen": -10}},
        {"t": 0.8, "koerper": {"rollen": -12, "kippen": 8}, "kopf": {"neigen": 10}, "ton": "chirp"},
        {"t": 1.0, "koerper": {"rollen": 12, "kippen": 8}},
        {"t": 1.3, "koerper": {}, "kopf": {}, "ton": "greet"},
    ]}
}


for _name, _antic in ANTICS.items():
    _antic["spec"] = with_sound(_name, _antic["spec"])


def concat(*specs: list[dict[str, Any]], gap: float = 0.15) -> list[dict[str, Any]]:
    """Mehrere Keyframe-Folgen hintereinander hängen."""
    out: list[dict[str, Any]] = []
    offset = 0.0
    for spec in specs:
        for kf in spec:
            out.append({**kf, "t": round(kf["t"] + offset, 3)})
        offset = out[-1]["t"] + gap
    return out


def is_pollen(spec: list[dict[str, Any]]) -> bool:
    return any(spec is e["spec"] for e in POLLEN.values())


# Am echten Roboter nur die beiden Neigungen (Pollen, curious: „set neck and head_pitch to 0 on a real Microduck“)
ROBOT_TILTS_ONLY = ("was_was",)


def robot_spec(key: str, spec: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if key not in ROBOT_TILTS_ONLY:
        return spec
    return [{**kf, "kopf": {**kf["kopf"], "nacken": 0.0, "nicken": 0.0}} if "kopf" in kf else kf for kf in spec]


def emotion(name: str, scale: float = 1.0, robot: bool = False, reachy: bool = False) -> Choreography:
    """Gefühl als Choreografie. `reachy`: Reachy Minis eigene, vorsichtige Geste (Antennen statt Nicken), falls es eine
    gibt (seit 0.38.10, `reachy_gesten.py`)."""
    key = name.lower().replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    if key not in EMOTIONS:
        raise ValueError(f"unbekanntes Gefühl '{name}' – bekannt: {', '.join(EMOTIONS)}")
    if reachy:
        from .reachy_gesten import geste

        eigen = geste(key)
        if eigen is not None:
            return Choreography.from_spec(eigen, title=key, scale=scale)
    spec = robot_spec(key, EMOTIONS[key]) if robot else EMOTIONS[key]
    return Choreography.from_spec(spec, title=key, scale=scale)


# ── Skills & Warten ───────────────────────────────────────────────────────
# Laute zu Tricks, die selbst keinen Ton haben (Pollens Skills, Moves aus der App, Hub-Tricks):
# kurze Quaks aus der Entenstimme – beim Tanzen im Takt, bei Missgeschicken erschrocken.
