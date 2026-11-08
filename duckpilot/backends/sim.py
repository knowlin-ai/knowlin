"""Lite-Simulator: eine kinematische Microduck mit 50-Hz-Schleife.

Kein Physik-Zwilling – der offizielle Weg dafür ist Pollens `scripts/duck-sim`
(echtes robotd gegen einen MuJoCo-Körper, Linux/macOS). Dieser Simulator läuft
überall, auch unter Windows, und bildet nach, was für Verhalten und
Sprachsteuerung zählt:

* dieselbe Befehlssemantik wie robotd (Totmann 500 ms, Skills, die abgelehnt
  werden können, Sitzen als Zustand, init/enable/rest),
* Trägheit, Kollisionen, Stürze bei zu schnellem Anrempeln,
* ein 8×8-ToF-Tiefenbild vom Kopf aus, wie `tof.frame`,
* Ball zum Kicken, Socke und Klötzchen zum Aufheben.
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from typing import Any

from ..api import (
    DEFAULT_SKILLS,
    SOUND_TAGS,
    DuckBackend,
    DuckState,
    Head,
    IntentResult,
    Perception,
    Pose,
    Twist,
    tof_points,
    wrap_angle,
)
from .world import World

TICK_HZ = 50
DEADMAN_S = 0.5
DUCK_RADIUS = 0.085
HEAD_HEIGHT = 0.21
FALL_SPEED = 0.17           # Anrempeln schneller als das → umfallen
HEAD_TAU = 0.22             # s, Kopf folgt dem Befehl (Zeitkonstante)
HEAD_TAU_NECK = 0.3
TOF_FOV = math.radians(45)
TOF_MAX = 2.0

# Dauer der Skills im Simulator (Sekunden) – ähnlich der echten Policies.
SKILL_DURATION = {
    "sit_toggle": 1.6,
    "ground_pick": 4.0,
    "kick_left": 1.6,
    "kick_right": 1.6,
    "roulade": 2.6,
    "_init": 1.8,
    "_recover": 3.0,
    "_rest": 2.4,
    "_relax": 0.35,          # Not-Aus: stromlos – nur fürs Bild, so schnell sackt sie zusammen
}


def _approach(current: float, target: float, dt: float, tau: float) -> float:
    if tau <= 0:
        return target
    return current + (target - current) * min(1.0, dt / tau)


SIM_AKKU_MIN = 0.25         # so leer wird der simulierte Akku höchstens


class SimBackend(DuckBackend):
    name = "sim"

    def __init__(self, world: World | None = None, realtime: bool = True, seed: int | None = None) -> None:
        super().__init__()
        self.world_model = world or World.living_room()
        self._dinge_start = {i.name: (i.x, i.y) for i in self.world_model.items}   # für „Szene zurücksetzen“
        self.realtime = realtime
        self.rng = random.Random(seed)
        self._task: asyncio.Task | None = None
        self.t = 0.0
        # Rumpf
        self.x = -0.6
        self.y = -0.2
        self.yaw = 0.0
        self.applied = Twist()
        self.requested = Twist()
        self._last_move = -1e9
        self.limited_by: list[str] = []
        # Kopf, Schnabel, Pose
        self.head_target = Head()
        self.head_now = Head()
        self.head_out = Head()          # was der Kopf wirklich zeigt: geglättet plus Stabilisator-Ausgleich
        self.mouth_target = 0.0
        self.mouth_now = 0.0
        self.pose_target = Pose()
        self.pose_now = Pose()
        # Zustand
        self.powered = False
        self.enabled = False
        self.sitting = False
        self.fallen = False
        self.fall_side = 1.0
        self.skill: str | None = None
        self.skill_t = 0.0
        self.extra_skills: dict[str, float] = {}   # nur für den Test-Roboter (fake_robotd): geladene Tricks
        self.slots: dict[str, str | None] = {}      # nur für den Test-Roboter: per robot.loadPolicy getauschte Plätze
        self.skill_done_action = False
        self.holding: str | None = None
        # weitere Enten (Schwarm, seit 0.37.3): [(Name, x, y)] – sie sieht sie wie Dinge (Art „ente“)
        self.weitere_koerper: Any = None
        self.gait_phase = 0.0
        self.battery = 1.0
        self._last_bump = -1e9
        self._tof: list[int] = [TOF_MAX * 1000] * 64
        self._points: list[list[float]] = []
        self._sectors: dict[str, float | None] = {}
        self._tof_age = 1e9
        self.nach_schritt: list = []      # z. B. die weiteren Enten (motion/schwarm.py) – im selben Takt

    # ── Lebenszyklus ──────────────────────────────────────────────────────
    async def connect(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="sim-loop")

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        dt = 1.0 / TICK_HZ
        next_t = time.perf_counter()
        while True:
            self.step(dt)
            if self.realtime:
                next_t += dt
                delay = next_t - time.perf_counter()
                if delay < -0.5:  # zu weit hinterher (Laptop schlief) – neu ansetzen
                    next_t = time.perf_counter()
                await asyncio.sleep(max(0.0, delay))
            else:
                await asyncio.sleep(0)

    # ── die Simulation ────────────────────────────────────────────────────
    def step(self, dt: float) -> None:
        self.t += dt
        # Simulierter Akku (seit 0.37.14 sanfter, Befund aus dem Test „Akku zeigt im Simulator 0 %“): leert sich nur beim
        # Laufen und Tricksen, nie unter SIM_AKKU_MIN – im Simulator soll niemand wegen eines leeren Akkus aufhören
        # müssen. Im Stehen, Sitzen und in Ruhe lädt er wieder.
        bewegt = self.powered and (self.skill is not None or math.hypot(self.applied.vx, self.applied.vy) > 0.01
                                   or abs(self.applied.vyaw) > 0.08)
        if bewegt:
            self.battery = max(SIM_AKKU_MIN, self.battery - dt / 3600.0)   # ~1 h Laufzeit beim Laufen
        elif self.battery < 1.0:
            laden = 1800.0 if not self.powered else 3600.0                 # in Ruhe ~30 min, im Stehen ~1 h bis voll
            self.battery = min(1.0, self.battery + dt / laden)
        self._step_skill(dt)
        self._step_base(dt)
        self._step_actuators(dt)
        self.world_model.step_items(dt)
        self._tof_age += dt
        if self._tof_age >= 0.1:  # ToF mit 10 Hz wie ein VL53L5CX
            self._tof_age = 0.0
            self._update_tof()
        for f in self.nach_schritt:
            f(dt)

    def _can_drive(self) -> bool:
        return self.powered and self.enabled and not self.fallen and not self.sitting and self.skill is None

    def _step_base(self, dt: float) -> None:
        self.limited_by = []
        if self.t - self._last_move > DEADMAN_S and not self.requested.is_zero():
            self.requested = Twist()
            self.limited_by.append("Totmann – kein Intent in den letzten 500 ms")
        target = self.requested.clamped() if self._can_drive() else Twist()
        if not self._can_drive() and not self.requested.is_zero():
            self.limited_by.append(self._why_not_driving())
        if self.skill == "roulade":
            progress = self.skill_t / SKILL_DURATION["roulade"]
            target = Twist(0.22 if 0.15 < progress < 0.75 else 0.0, 0.0, 0.0)
        # Trägheit: Beschleunigung begrenzt
        a_lin, a_yaw = 0.8, 4.0
        for attr, acc in (("vx", a_lin), ("vy", a_lin), ("vyaw", a_yaw)):
            cur, tgt = getattr(self.applied, attr), getattr(target, attr)
            delta = max(-acc * dt, min(acc * dt, tgt - cur))
            setattr(self.applied, attr, cur + delta)

        v = self.applied
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        nx = self.x + (v.vx * c - v.vy * s) * dt
        ny = self.y + (v.vx * s + v.vy * c) * dt
        self.yaw = wrap_angle(self.yaw + v.vyaw * dt)
        hit = self.world_model.collide(nx, ny, DUCK_RADIUS)
        if hit:
            px, py, what = hit
            nx += px
            ny += py
            speed = math.hypot(v.vx, v.vy)
            if speed > FALL_SPEED and not self.fallen and self.skill != "roulade":
                self._fall(f"gegen {what} gelaufen")
            elif speed > 0.02 and self.t - self._last_bump > 1.0:
                self._last_bump = self.t
                self.emit("bump", what=what, message=f"Angestoßen: {what}")
            self.applied = Twist(0.0, 0.0, v.vyaw)
        self.x, self.y = nx, ny
        self._push_items()

        # Gangphase: Schritte beim Laufen und beim Drehen auf der Stelle
        moving = math.hypot(v.vx, v.vy) > 0.01 or abs(v.vyaw) > 0.08
        if moving and self._can_drive():
            freq = 2.0 + 2.0 * min(1.0, math.hypot(v.vx, v.vy) / 0.25)
            self.gait_phase = (self.gait_phase + 2 * math.pi * freq * dt) % (2 * math.pi)
        else:
            # Füße kommen zur Ruhe
            target_phase = 0.0 if self.gait_phase < math.pi else 2 * math.pi
            self.gait_phase = _approach(self.gait_phase, target_phase, dt, 0.15) % (2 * math.pi)

    def _push_items(self) -> None:
        for item in self.world_model.items:
            if item.held:
                continue
            dx, dy = item.x - self.x, item.y - self.y
            d = math.hypot(dx, dy)
            reach = DUCK_RADIUS + item.r
            if d < reach and d > 1e-6:
                item.x = self.x + dx / d * reach
                item.y = self.y + dy / d * reach
                speed = math.hypot(self.applied.vx, self.applied.vy)
                if item.kind == "ball":
                    item.vx += dx / d * speed * 0.8
                    item.vy += dy / d * speed * 0.8
                self.world_model.loesen(item)          # nicht in die Wand oder ins Möbel drücken (seit 0.37.14)

    def _gait_sway(self) -> tuple[float, float]:
        """Rumpfwackeln beim Gehen (nur der einfache Simulator zeichnet es nach): Rollen pro Schritt, Kippen doppelt so oft."""
        speed = math.hypot(self.applied.vx, self.applied.vy) + 0.05 * abs(self.applied.vyaw)
        if speed < 0.01 or self.sitting or self.fallen or not self.powered:
            return 0.0, 0.0
        k = min(1.0, speed / 0.15)
        return 0.05 * k * math.sin(self.gait_phase), 0.025 * k * math.sin(2 * self.gait_phase + 0.5)

    def _trunk_attitude(self) -> tuple[float, float, float]:
        """Rumpflage für den Kopf-Stabilisator: Rollen, Kippen, Gieren."""
        sway_r, sway_p = self._gait_sway()
        return self.pose_now.roll + sway_r, self.pose_now.pitch + sway_p, self.yaw

    def _trunk_extra(self) -> dict[str, float]:
        """Rumpfposition für das Vor und Zurück – der einfache Simulator schiebt nicht, also nichts."""
        return {}

    def _step_actuators(self, dt: float) -> None:
        override = self._skill_head_override()
        h = override or self.head_target.clamped()
        if not self.powered or self.fallen:
            h = Head(-0.3, 0.4, self.head_now.head_yaw, 0.0) if self.fallen else Head(-0.45, 0.35, 0.0, 0.0)
        # So träge wie am echten Roboter: die Policies folgen einem Kopfbefehl erst nach ≈ 0,25–0,4 s
        # (Pollen: deshalb beginnen die Emotions-Töne mit etwas Stille). Zu flink lief der Kopf dem Ton voraus.
        self.head_now = Head(
            _approach(self.head_now.neck_pitch, h.neck_pitch, dt, HEAD_TAU_NECK),
            _approach(self.head_now.head_pitch, h.head_pitch, dt, HEAD_TAU),
            _approach(self.head_now.head_yaw, h.head_yaw, dt, HEAD_TAU),
            _approach(self.head_now.head_roll, h.head_roll, dt, HEAD_TAU),
        )
        # Kopf-Stabilisator nach der Glättung: der Ausgleich muss sofort wirken, nicht 0,1 s später
        self.stabilizer.update(*self._trunk_attitude(), dt, **self._trunk_extra())
        steady = override is None and self.powered and not self.fallen and not self.expressing
        self.head_out = self.stabilizer.apply(self.head_now).clamped() if steady else self.head_now
        mouth = self._skill_mouth_override()
        mouth = self.mouth_target if mouth is None else mouth
        self.mouth_now = _approach(self.mouth_now, max(0.0, min(1.0, mouth)), dt, 0.06)
        pose = self.pose_target.clamped() if self._can_drive() or self.skill == "_init" else Pose()
        self.pose_now = Pose(
            _approach(self.pose_now.z, pose.z, dt, 0.2),
            _approach(self.pose_now.roll, pose.roll, dt, 0.2),
            _approach(self.pose_now.pitch, pose.pitch, dt, 0.2),
        )

    # ── Skills ────────────────────────────────────────────────────────────
    def _start_skill(self, name: str) -> None:
        self.skill = name
        self.skill_t = 0.0
        self.skill_done_action = False
        self.emit("skill_start", skill=name)

    def _step_skill(self, dt: float) -> None:
        if self.skill is None:
            if self.fallen:
                self.skill_t += dt  # Zeit am Boden, für die Darstellung
            return
        self.skill_t += dt
        name, p = self.skill, self.skill_t / self._skill_len(self.skill)
        if not self.skill_done_action:
            if name == "ground_pick" and p >= 0.5:
                self.skill_done_action = True
                self._pick_or_drop()
            elif name in ("kick_left", "kick_right") and p >= 0.4:
                self.skill_done_action = True
                self._kick(left=name == "kick_left")
        if p >= 1.0:
            self.skill = None
            if name == "sit_toggle":
                self.sitting = not self.sitting
            elif name == "_init":
                self.powered = True
                self.sitting = False
            elif name == "_recover":
                self.fallen = False
                self.powered = True
                self.sitting = False
            elif name in ("_rest", "_relax"):
                self.powered = False
                self.enabled = False
                self.sitting = False
            self.emit("skill_end", skill=name)

    def _skill_progress(self) -> float:
        if self.skill is None:
            return 0.0
        return min(1.0, self.skill_t / self._skill_len(self.skill))

    def _skill_head_override(self) -> Head | None:
        if self.skill == "ground_pick":
            p = self._skill_progress()
            dip = math.sin(math.pi * min(1.0, p * 1.15))
            return Head(-0.5 * dip, 0.7 * dip, 0.0, 0.0)
        return None

    def _skill_mouth_override(self) -> float | None:
        if self.skill == "ground_pick":
            p = self._skill_progress()
            return 1.0 if 0.2 < p < 0.5 else 0.0
        return None

    def _front(self, dist: float) -> tuple[float, float]:
        return self.x + math.cos(self.yaw) * dist, self.y + math.sin(self.yaw) * dist

    def _pick_or_drop(self) -> None:
        items = self.world_model.items
        if self.holding:
            item = next(i for i in items if i.name == self.holding)
            item.held, item.traeger = False, ""
            item.x, item.y = self._front(DUCK_RADIUS + item.r + 0.03)
            self.emit("drop", item=item.name, message=f"{item.name} abgelegt")
            self.holding = None
            return
        fx, fy = self._front(DUCK_RADIUS + 0.06)
        candidates = [
            i for i in items if i.pickable and not i.held and math.hypot(i.x - fx, i.y - fy) < 0.11
        ]
        if candidates:
            item = min(candidates, key=lambda i: math.hypot(i.x - fx, i.y - fy))
            item.held = True
            item.traeger = getattr(self, "kennung", "haupt")
            self.holding = item.name
            self.emit("pick", item=item.name, message=f"{item.name} aufgehoben")
        else:
            self.emit("pick_miss", message="Nichts zum Aufheben vor dem Schnabel")

    def _kick(self, left: bool) -> None:
        for item in self.world_model.items:
            if item.kind != "ball" or item.held:
                continue
            dx, dy = item.x - self.x, item.y - self.y
            d = math.hypot(dx, dy)
            bearing = wrap_angle(math.atan2(dy, dx) - self.yaw)
            if d < DUCK_RADIUS + item.r + 0.1 and abs(bearing) < math.radians(60):
                spread = -0.25 if left else 0.25  # linker Fuß schießt leicht nach rechts
                ang = self.yaw + spread * 0.5
                item.vx = math.cos(ang) * 1.3
                item.vy = math.sin(ang) * 1.3
                self.emit("kick", item=item.name, message=f"{item.name} geschossen")
                return
        self.emit("kick_miss", message="Ins Leere getreten")

    def _fall(self, why: str) -> None:
        self.fallen = True
        self.skill = None
        self.skill_t = 0.0
        self.fall_side = self.rng.choice((-1.0, 1.0))
        self.applied = Twist()
        if self.holding:
            item = next(i for i in self.world_model.items if i.name == self.holding)
            item.held, item.traeger = False, ""
            item.x, item.y = self._front(0.15)
            self.holding = None
        self.emit("fall", message=f"Umgefallen ({why})")

    def _why_not_driving(self) -> str:
        if self.fallen:
            return "umgefallen"
        if not self.powered:
            return "Motoren aus – erst aufstehen (init)"
        if not self.enabled:
            return "Policy aus"
        if self.sitting:
            return "sitzt"
        if self.skill:
            return f"Skill {self.skill} läuft"
        return "?"

    # ── Wahrnehmung ───────────────────────────────────────────────────────
    def _height_of(self, name: str) -> float:
        if name == "Wand":
            return 2.5
        for o in [*self.world_model.boxes, *self.world_model.cylinders]:
            if o.name == name:
                return o.h
        for i in self.world_model.items:
            if i.name == name:
                return i.r * 2
        return 0.5

    def _update_tof(self) -> None:
        h = self.head_out
        head_yaw = self.yaw + h.head_yaw
        # Konvention des Roboters: head_pitch > 0 = Schnabel runter, neck_pitch < 0 = Hals nach vorn/unten
        tilt = h.head_pitch - h.neck_pitch
        cam_h = HEAD_HEIGHT + self.pose_now.z - (0.08 if self.sitting else 0.0)
        frame: list[int] = []
        cols: list[float | None] = [None] * 8
        for row in range(8):
            elev = (3.5 - row) / 8 * TOF_FOV - tilt  # oben → unten
            for col in range(8):
                az = head_yaw + (3.5 - col) / 8 * TOF_FOV  # Spalte 0 = links
                dist = TOF_MAX
                hit = self.world_model.raycast(self.x, self.y, az, TOF_MAX)
                if hit:
                    horiz, name = hit
                    z = cam_h + horiz * math.tan(elev)
                    if 0.0 <= z <= self._height_of(name):
                        dist = horiz / max(0.2, math.cos(elev))
                        if row <= 5:
                            prev = cols[col]
                            cols[col] = horiz if prev is None else min(prev, horiz)
                if elev < 0:  # Boden
                    floor = cam_h / math.sin(-elev)
                    dist = min(dist, floor)
                frame.append(int(min(dist, TOF_MAX) * 1000))
        self._tof = frame
        self._points = tof_points(frame, x=self.x, y=self.y, yaw=self.yaw, head_yaw=h.head_yaw,
                                  tilt=tilt, cam_h=cam_h, max_mm=int(TOF_MAX * 1000))
        self._sectors = {
            "links": _min_or_none(cols[0:3]),
            "mitte": _min_or_none(cols[3:5]),
            "rechts": _min_or_none(cols[5:8]),
        }

    def _visible_objects(self) -> list[dict[str, Any]]:
        out = []
        gaze = self.yaw + self.head_out.head_yaw
        hx, hy = self._front(0.03)
        # Größe (seit 0.38.21, fürs Umrunden): Möbel als Kasten (volle Breite in x und y, Raum-Achsen) oder Kreis
        groesse: dict[str, dict[str, Any]] = {b.name: {"ausdehnung_m": [round(b.sx, 2), round(b.sy, 2)]} for b in self.world_model.boxes}
        groesse.update({c.name: {"radius_m": round(c.r, 2)} for c in self.world_model.cylinders})
        things = [(i.name, i.kind, i.x, i.y) for i in self.world_model.items if not i.held]
        things += [(b.name, "möbel", b.x, b.y) for b in self.world_model.boxes]
        things += [(c.name, "möbel", c.x, c.y) for c in self.world_model.cylinders]
        if self.weitere_koerper is not None:
            things += [(n, "ente", x, y) for n, x, y in self.weitere_koerper()]
        for name, kind, ox, oy in things:
            d = math.hypot(ox - hx, oy - hy)
            bearing = wrap_angle(math.atan2(oy - hy, ox - hx) - gaze)
            if d < 2.5 and abs(bearing) < math.radians(55):
                if kind != "möbel" and not self.world_model.line_of_sight(hx, hy, ox, oy):
                    continue
                rel = wrap_angle(math.atan2(oy - self.y, ox - self.x) - self.yaw)
                out.append({
                    "name": name,
                    "art": kind,
                    "entfernung_m": round(d, 2),
                    "richtung_grad": round(math.degrees(rel)),  # relativ zum Rumpf, + = links
                    **(groesse.get(name, {}) if kind == "möbel" else {}),
                })
        dot = self.world_model.laser_point()
        if dot is not None:                       # Laserpunkt: hell, auch weiter weg und schräg gut zu sehen
            d = math.hypot(dot[0] - hx, dot[1] - hy)
            bearing = wrap_angle(math.atan2(dot[1] - hy, dot[0] - hx) - gaze)
            if d < 3.0 and abs(bearing) < math.radians(60) and self.world_model.line_of_sight(hx, hy, *dot):
                rel = wrap_angle(math.atan2(dot[1] - self.y, dot[0] - self.x) - self.yaw)
                out.append({"name": "Laserpunkt", "art": "laser", "entfernung_m": round(d, 2),
                            "richtung_grad": round(math.degrees(rel))})
        man = self.world_model.person_point()
        if man is not None:                       # Mensch: groß, gut zu sehen – Beine auf Augenhöhe der Ente
            d = math.hypot(man[0] - hx, man[1] - hy)
            bearing = wrap_angle(math.atan2(man[1] - hy, man[0] - hx) - gaze)
            if d < 4.0 and abs(bearing) < math.radians(70) and self.world_model.line_of_sight(hx, hy, *man):
                rel = wrap_angle(math.atan2(man[1] - self.y, man[0] - self.x) - self.yaw)
                out.append({"name": "Mensch", "art": "person", "entfernung_m": round(d, 2),
                            "richtung_grad": round(math.degrees(rel))})
        out.sort(key=lambda o: o["entfernung_m"])
        return out

    def person(self) -> dict[str, float] | None:
        man = self.world_model.person_point()
        return {"x": round(man[0], 3), "y": round(man[1], 3)} if man else None

    def set_person(self, x: float | None, y: float | None) -> None:
        self.world_model.set_person(x, y)

    def laser(self) -> dict[str, float] | None:
        dot = self.world_model.laser_point()
        return {"x": round(dot[0], 3), "y": round(dot[1], 3), "z": round(self.world_model.laser_z, 3)} if dot else None

    def set_laser(self, x: float | None, y: float | None, z: float = 0.0) -> None:
        self.world_model.set_laser(x, y, z)

    # ── Zustand ───────────────────────────────────────────────────────────
    def state(self) -> DuckState:
        return DuckState(
            t=self.t,
            connected=self._task is not None,
            backend="sim",
            kopf_stabil=self.stabilizer.enabled,
            x=self.x,
            y=self.y,
            yaw=self.yaw,
            twist=Twist(self.applied.vx, self.applied.vy, self.applied.vyaw),
            requested=Twist(self.requested.vx, self.requested.vy, self.requested.vyaw),
            limited_by=list(self.limited_by),
            head=Head(**vars(self.head_out)),
            mouth=self.mouth_now,
            pose=self._shown_pose(),
            powered=self.powered,
            enabled=self.enabled,
            sitting=self.sitting,
            fallen=self.fallen,
            skill=self.skill,
            skill_progress=self._skill_progress(),
            fall_side=self.fall_side,
            holding=self.holding,
            gait_phase=self.gait_phase,
            battery=self.battery,
            perception=Perception(
                tof_mm=list(self._tof),
                sectors=dict(self._sectors),
                objects=self._visible_objects(),
                source="sim",
                points=list(self._points),
            ),
            joints=(j := self._joints()),
            display_joints=j,
        )

    def _shown_pose(self) -> Pose:
        sway_r, sway_p = self._gait_sway()
        return Pose(self.pose_now.z, self.pose_now.roll + sway_r, self.pose_now.pitch + sway_p)

    def skill_progress(self) -> float:
        return self._skill_progress()

    def world(self) -> dict[str, Any]:
        return self.world_model.to_dict()

    def items(self) -> list[dict[str, Any]]:
        return self.world_model.items_dict()

    def _joints(self) -> list[float]:
        return display_joints(
            sitting=self.sitting, skill=self.skill, progress=self._skill_progress(), powered=self.powered,
            fallen=self.fallen, twist=self.applied, phase=self.gait_phase, head=self.head_out, mouth=self.mouth_now,
            crouch=-self.pose_now.z / 0.025,
        )

    # ── Intents ───────────────────────────────────────────────────────────
    async def move(self, twist: Twist) -> None:
        self.requested = twist.clamped()
        self._last_move = self.t

    async def head(self, head: Head) -> None:
        self.head_target = head.clamped()

    async def mouth(self, open_: float) -> None:
        self.mouth_target = max(0.0, min(1.0, float(open_)))

    async def pose(self, pose: Pose, active: bool = True) -> None:
        self.pose_target = pose.clamped() if active else Pose()
        if not active:
            self.pose_now = Pose()

    # ── diskrete Befehle ──────────────────────────────────────────────────
    async def init(self) -> IntentResult:
        if self.skill:
            return IntentResult(False, f"{self.skill} läuft gerade")
        if self.fallen:
            self._start_skill("_recover")
            self.emit("recover", message="Steht wieder auf")
            return IntentResult(True, "steht auf")
        if self.powered and not self.sitting:
            return IntentResult(True, "steht schon")
        self._start_skill("_init")
        return IntentResult(True)

    async def enable(self, on: bool) -> IntentResult:
        if on and self.fallen:
            return IntentResult(False, "umgefallen – erst aufstehen")
        self.enabled = on
        if on and not self.powered and self.skill is None:
            self._start_skill("_init")
        if not on:
            self.requested = Twist()
        return IntentResult(True)

    async def stop(self) -> IntentResult:
        self.requested = Twist()
        return IntentResult(True)

    def _skill_len(self, name: str) -> float:
        return SKILL_DURATION.get(name) or self.extra_skills.get(name, 2.0)

    # ── Szene zurücksetzen (seit 0.37.14, Wunsch des Maintainers: „Für den Simulator wäre ein Reset sinnvoll“) ──
    START_POSE = (-0.6, -0.2, 0.0)

    def zuruecklegen(self, name: str) -> tuple[bool, str]:
        """Ein Ding an seinen Startplatz legen (z. B. den Ball aus der Ecke)."""
        n = str(name or "").strip().lower()
        item = next((i for i in self.world_model.items if i.name.lower() == n or i.kind == n), None)
        if item is None:
            return False, f"Kenne kein Ding namens „{name}“"
        if item.name not in self._dinge_start:
            return False, f"{item.name} hat keinen Startplatz"
        if item.held:
            if item.traeger not in ("", "haupt"):
                return False, f"{item.name} hat gerade eine andere Ente im Schnabel"
            item.held, item.traeger = False, ""
            self.holding = None
        item.x, item.y = self._dinge_start[item.name]
        item.vx = item.vy = 0.0
        return True, f"{item.name} liegt wieder an seinem Platz"

    def szene_zuruecksetzen(self, ente: bool = True) -> dict[str, Any]:
        """Alle Dinge auf ihre Startplätze, die Ente zurück in die Ausgangsstellung – nur wenn sie steht (liegt sie
        oder ist der Not-Aus aktiv, bleibt sie, wo sie ist; aufgestellt wird sie hier nie)."""
        gelegt = [i.name for i in self.world_model.items if self.zuruecklegen(i.name)[0]]
        out: dict[str, Any] = {"ok": True, "dinge": gelegt, "ente": False}
        if ente:
            if self.fallen or not self.powered or self.skill is not None:
                out["hinweis"] = "Die Ente bleibt, wo sie ist – sie liegt, ruht oder macht gerade einen Trick."
            else:
                self._ente_setzen(*self.START_POSE)
                out["ente"] = True
        return out

    def _ente_setzen(self, x: float, y: float, yaw: float) -> None:
        self.x, self.y, self.yaw = x, y, yaw
        self.applied = Twist()
        self.requested = Twist()

    def eigenschaften(self) -> frozenset[str]:
        return frozenset({"beine", "kopf", "schnabel", "tiefensensor", "simulator", "zuruecksetzen", "stimmbank"})

    def fassung(self, skill: str) -> dict[str, str]:
        """Welche Fassung läuft? Im einfachen Simulator keine Policy, nur eine gezeichnete Bewegung (seit 0.37.14)."""
        return {"fassung": "einfacher Simulator – gezeichnete Bewegung ohne Policy (echte Policies: Physik-Simulator)"}

    async def do(self, skill: str) -> IntentResult:
        if skill not in DEFAULT_SKILLS and skill not in self.extra_skills:
            known = [*DEFAULT_SKILLS, *self.extra_skills]
            return IntentResult(False, f"keinen Skill namens '{skill}' – vorhanden: {', '.join(known)}")
        if self.fallen:
            return IntentResult(False, "umgefallen")
        if not (self.powered and self.enabled):
            return IntentResult(False, "Motoren/Policy aus – erst aufstehen")
        if self.skill:
            return IntentResult(False, f"'{self.skill}' hält die Ente gerade")
        if self.sitting and skill != "sit_toggle":
            return IntentResult(False, "sitzt – erst aufstehen (sit_toggle)")
        self.requested = Twist()
        self.applied = Twist()
        self._start_skill(skill)
        return IntentResult(True)

    async def sound(self, tag: str) -> IntentResult:
        if tag not in SOUND_TAGS:
            return IntentResult(False, f"unbekannter Ton '{tag}'")
        self.emit("sound", tag=tag)
        return IntentResult(True)

    def lahm(self) -> None:
        """Not-Aus: Motoren sofort aus. Aus dem Stand sackt sie zusammen (0,35 s, nur fürs Bild); aufstehen erst auf Befehl."""
        self.requested = Twist()
        self.enabled = False
        stand = self.powered and not self.fallen and not self.sitting
        self.skill = None
        self.powered = False
        if stand:
            self._start_skill("_relax")
        else:
            self.sitting = False

    async def relax(self) -> IntentResult:
        self.lahm()
        return IntentResult(True, "stromlos")

    async def rest(self) -> IntentResult:
        if self.skill in ("_init", "_recover"):
            self.skill = None                     # Aufstehen abbrechen – Ruhe gewinnt (wie robot.rest)
        if self.fallen or not self.powered:
            self.powered = False
            self.enabled = False
            return IntentResult(True, "ist schon aus")
        self.skill = None
        self._start_skill("_rest")
        return IntentResult(True)


def _min_or_none(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(min(vals), 3) if vals else None


# Posen aus Pollens MJCF (scene.xml), linkes Bein; das rechte ist gespiegelt (alle Vorzeichen).
STAND_LEG = (0.0, -0.0873, -0.4579, -0.0049, 0.4530)   # hip_yaw, hip_roll, hip_pitch, knee, ankle
SIT_LEG = (0.0, 0.0, -0.5236, 1.0472, 0.0)
HOME_NECK, HOME_HEAD = 0.3491, 0.3491                   # robot.head schickt Abweichungen hiervon
REST_NECK, REST_HEAD = 0.5, 1.6                         # Kopf, wenn die Ente stromlos sitzt


def display_joints(*, sitting: bool, skill: str | None, progress: float, powered: bool, fallen: bool,
                   twist: Twist, phase: float, head: Head, mouth: float, crouch: float = 0.0) -> list[float]:
    """Gelenkwinkel für die 3D-Ansicht – absolut, in der Konvention des echten Roboters
    (MJCF von Pollen, Reihenfolge JOINT_NAMES). Der Simulator kennt keine echten Beine;
    die Winkel sind aus Haltung, Gangphase und Geschwindigkeit abgeleitet.
    """
    fold = 0.0
    if skill == "sit_toggle":
        fold = 1.0 - progress if sitting else progress
    elif skill in ("_rest", "_relax"):
        fold = progress
    elif skill in ("_init", "_recover"):
        fold = 1.0 - progress
    elif sitting or (not powered and not fallen):
        fold = 1.0
    if fallen:
        fold = 0.35
    base = [a + (b - a) * fold for a, b in zip(STAND_LEG, SIT_LEG)]
    c = max(0.0, min(1.0, crouch)) * (1.0 - fold)
    base[2] -= 0.30 * c
    base[3] += 0.25 * c
    base[4] += 0.10 * c
    stride = max(-1.0, min(1.0, twist.vx / 0.25))
    turn = max(-1.0, min(1.0, twist.vyaw / 1.0))
    moving = 0.0 if fallen or fold > 0.5 else 1.0
    lift = moving * min(1.0, abs(stride) + abs(turn) * 0.6 + abs(twist.vy) * 4)
    legs = []
    for side, ph in ((1.0, phase), (-1.0, phase + math.pi)):
        swing = math.sin(ph)
        up = max(0.0, math.sin(ph)) * lift
        yaw = base[0] + 0.16 * turn * swing * side
        roll = base[1] + 0.05 * math.cos(ph) * lift
        hip = base[2] + 0.22 * stride * swing * moving
        knee = base[3] + 0.70 * up
        ankle = base[4] + 0.30 * up - 0.18 * stride * swing * moving
        legs.append([yaw, roll, hip, knee, ankle])
    if skill in ("kick_left", "kick_right"):
        k = math.sin(math.pi * min(1.0, max(0.0, (progress - 0.2) / 0.5))) if 0.2 < progress < 0.7 else 0.0
        leg = legs[0 if skill == "kick_left" else 1]
        leg[2] -= 0.55 * k
        leg[3] += 0.35 * k * (1.0 - k) * 4 - 0.2 * k
        leg[4] -= 0.25 * k
    if not powered and skill in (None, "_relax") and not fallen:
        neck, pitch, yaw, roll = REST_NECK, REST_HEAD, 0.0, 0.0
    else:
        neck = HOME_NECK + head.neck_pitch
        pitch = HOME_HEAD + head.head_pitch
        yaw, roll = head.head_yaw, head.head_roll
    left, right = legs[0], [-v for v in legs[1]]
    return [*left, neck, pitch, yaw, roll, max(0.0, min(1.0, mouth)), *right]
