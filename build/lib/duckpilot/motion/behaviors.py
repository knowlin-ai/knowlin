"""Verhalten: was die Ente über Sekunden hinweg tut.

Alle arbeiten nur mit dem Zustand, den jedes Backend liefert (Odometrie,
ToF-Sektoren, Sturz, laufender Skill) – darum laufen sie im Simulator und auf
dem echten Roboter gleich. `Approach` braucht zusätzlich erkannte Objekte, die
heute nur der Simulator liefert.
"""

from __future__ import annotations

import math
import random
from typing import Any

from ..api import DuckState, Head, Pose, Twist, clamp, wrap_angle
from .choreografie import (  # noqa: F401 – Kataloge und Choreografie leben dort, hier weitergereicht
    ANTICS,
    CHARACTER,
    EMOTIONS,
    OWN,
    POLLEN,
    ROBOT_TILTS_ONLY,
    Choreography,
    Keyframe,
    concat,
    emotion,
    is_pollen,
    pick_clip,
    robot_spec,
)
from .engine import Behavior, Command
from .hilfen import DEG, _ohne_entenlaute, smoothstep  # noqa: F401 – smoothstep wird auch von außen genutzt

# ── Fortbewegung ──────────────────────────────────────────────────────────


def _welt(st: DuckState, obj: dict[str, Any]) -> tuple[float, float]:
    """Weltposition eines wahrgenommenen Dings (Entfernung/Richtung vom Kopf aus)."""
    w = st.yaw + math.radians(obj.get("richtung_grad", 0.0))
    d = obj.get("entfernung_m", 0.0) + 0.03
    return st.x + d * math.cos(w), st.y + d * math.sin(w)



class TimedMove(Behavior):
    name = "fahren"
    channels = ("base",)

    def __init__(self, twist: Twist, duration: float) -> None:
        super().__init__()
        self.twist = twist.clamped()
        self.duration = max(0.0, min(30.0, duration))
        self.timeout = self.duration + 1.0

    def tick(self, st, dt):
        if self.elapsed >= self.duration:
            return self.finish()
        return Command(twist=self.twist)

    def describe(self):
        t = self.twist
        return f"fahren vx={t.vx:.2f} vy={t.vy:.2f} vyaw={t.vyaw:.2f} für {self.duration:.1f}s"


class Walk(Behavior):
    """Eine Strecke laufen (Odometrie), Kurs halten. Negativ = rückwärts."""

    name = "laufen"
    channels = ("base",)

    def __init__(self, distance: float, speed: float = 0.15, sideways: bool = False) -> None:
        super().__init__()
        self.distance = max(-3.0, min(5.0, distance))
        self.speed = abs(speed)
        self.sideways = sideways
        limit = 0.12 if sideways else 0.25
        self.speed = min(self.speed, limit)
        self.timeout = abs(self.distance) / max(0.05, self.speed) * 2.5 + 3.0
        self._stuck_t = 0.0
        self._last_progress = 0.0

    def on_start(self, st):
        self.x0, self.y0, self.yaw0 = st.x, st.y, st.yaw

    def tick(self, st, dt):
        dx, dy = st.x - self.x0, st.y - self.y0
        ax = self.yaw0 + (math.pi / 2 if self.sideways else 0.0)
        progress = dx * math.cos(ax) + dy * math.sin(ax)
        remaining = self.distance - progress
        if abs(remaining) < 0.02:
            return self.finish(f"{progress:.2f} m gelaufen")
        # festgefahren?
        if abs(progress - self._last_progress) < 0.002:
            self._stuck_t += dt
        else:
            self._stuck_t = 0.0
        self._last_progress = progress
        if self._stuck_t > 2.0:
            return self.finish(f"blockiert nach {progress:.2f} m")
        v = math.copysign(min(self.speed, 0.05 + abs(remaining) * 1.2), remaining)
        heading_err = wrap_angle(self.yaw0 - st.yaw)
        vyaw = max(-0.5, min(0.5, 2.0 * heading_err))
        if self.sideways:
            return Command(twist=Twist(0.0, v, vyaw))
        return Command(twist=Twist(v, 0.0, vyaw))

    def target(self):
        if not self.started:
            return None
        ax = self.yaw0 + (math.pi / 2 if self.sideways else 0.0)
        return (self.x0 + self.distance * math.cos(ax), self.y0 + self.distance * math.sin(ax))

    def describe(self):
        return f"{'seitlich ' if self.sideways else ''}laufen {self.distance:+.2f} m"


class Turn(Behavior):
    """Um einen Winkel drehen (Grad, + = links)."""

    name = "drehen"
    channels = ("base",)

    def __init__(self, degrees: float, speed: float = 0.9) -> None:
        super().__init__()
        self.angle = max(-720.0, min(720.0, degrees)) * DEG
        self.speed = min(1.0, abs(speed))
        self.timeout = abs(self.angle) / max(0.2, self.speed) * 2.5 + 3.0

    def on_start(self, st):
        self.turned = 0.0
        self.last_yaw = st.yaw

    def tick(self, st, dt):
        self.turned += wrap_angle(st.yaw - self.last_yaw)
        self.last_yaw = st.yaw
        err = self.angle - self.turned
        if abs(err) < 3 * DEG:
            return self.finish(f"{math.degrees(self.turned):.0f}° gedreht")
        vyaw = math.copysign(min(self.speed, 0.15 + abs(err) * 1.5), err)
        return Command(twist=Twist(0.0, 0.0, vyaw))

    def describe(self):
        return f"drehen {math.degrees(self.angle):+.0f}°"


class GoTo(Behavior):
    """Zu einer Odometrie-Koordinate gehen (Startrahmen, Meter)."""

    name = "hingehen"
    channels = ("base",)

    def __init__(self, x: float, y: float, speed: float = 0.18, label: str | None = None) -> None:
        super().__init__()
        self.tx, self.ty = x, y
        self.label = label
        self.speed = min(0.25, abs(speed))
        self.timeout = 60.0

    def tick(self, st, dt):
        dx, dy = self.tx - st.x, self.ty - st.y
        dist = math.hypot(dx, dy)
        if dist < 0.06:
            return self.finish("angekommen")
        # festgefahren? (8 s lang keine 1,5 cm näher) – statt bis zum Zeitlimit die Warteschlange zu blockieren.
        # 8 statt 5 s, seit sie Hindernisse umläuft (0.33): ein Umweg entfernt sie erst einmal vom Ziel.
        best = getattr(self, "_best", math.inf)
        aw = getattr(getattr(self, "engine", None), "ausweicher", None)
        if dist < best - 0.015 or (aw is not None and aw.arbeitet()):   # Umweg ums Hindernis zählt nicht als Stillstand
            self._best, self._best_t = min(dist, best), self.elapsed
        elif self.elapsed - getattr(self, "_best_t", 0.0) > 8.0:
            if dist < 0.12:
                return self.finish(f"fast angekommen ({dist:.2f} m)")
            self.failed = True
            return self.finish(f"kommt nicht weiter ({dist:.2f} m vor dem Ziel)")
        err = wrap_angle(math.atan2(dy, dx) - st.yaw)
        vyaw = max(-1.0, min(1.0, 2.2 * err))
        vx = 0.0 if abs(err) > 0.6 else min(self.speed, 0.05 + dist) * math.cos(err)
        return Command(twist=Twist(vx, 0.0, vyaw))

    def target(self):
        return (self.tx, self.ty)

    def describe(self):
        if self.label:
            return f"hingehen zu {self.label}"
        return f"hingehen zu ({self.tx:.2f}, {self.ty:.2f})"


class Approach(Behavior):
    """Zu einem gesehenen Objekt laufen und davor stehen bleiben.

    Das Ziel wird im Raum festgehalten und geglättet: In echter Physik schwankt der Rumpf beim Gehen, jede einzelne
    Messung springt ein paar Zentimeter – ohne Glättung zappelt die Zielmarke und die Steuerung jagt ihr hinterher.
    Kommt sie 5 s lang nicht näher, gibt sie auf („kommt nicht näher“) statt bis zum Zeitlimit zu treten.
    """

    name = "annähern"
    channels = ("base", "head")
    timeout = 90.0                 # mit Suchen (umsehen, zur letzten Sichtung, umherlaufen) – seit 0.38.21
    SMOOTH = 0.15              # Anteil einer neuen Messung an der geglätteten Zielposition
    STUCK_S = 5.0
    MIN_V = 0.06               # darunter macht Pollens Geh-Policy oft nur Trippelschritte auf der Stelle

    def __init__(self, target: str, stop_at: float = 0.13, bearing_tol_deg: float = 8.0,
                 vermutet: tuple[float, float] | None = None) -> None:
        super().__init__()
        self.target_name = target.lower()
        self.vermutet = vermutet               # letzte Sichtung (Weltkoordinaten), falls bekannt
        self.suche: dict[str, Any] = {}
        self.stop_at = stop_at
        self.bearing_tol = bearing_tol_deg * DEG
        self.lost_t = 0.0
        self.search_dir = 1.0
        self.goal: tuple[float, float] | None = None
        self.best = math.inf
        self.best_t = 0.0

    def _find(self, st: DuckState) -> dict[str, Any] | None:
        for obj in st.perception.objects:
            if self.target_name in obj["name"].lower() or self.target_name == obj.get("art", ""):
                return obj
        return None

    KONTAKT_R = 0.12           # Ball/Socke samt Rand: das Ziel ist kein Hindernis

    def kontakt_ziel(self, st: DuckState) -> tuple[float, float, float] | None:
        if self.goal is not None:
            return (self.goal[0], self.goal[1], self.KONTAKT_R)
        obj = self._find(st)
        return None if obj is None else (*_welt(st, obj), self.KONTAKT_R)

    def tick(self, st, dt):
        obj = self._find(st)
        if obj is None and self.goal is None:
            return self._suchen(st, dt)
        if obj is not None:
            self.lost_t = 0.0
            b = math.radians(obj["richtung_grad"])
            r = obj["entfernung_m"] + 0.03               # Entfernung wird vom Kopf (3 cm vor der Mitte) gemessen
            mx = st.x + r * math.cos(st.yaw + b)
            my = st.y + r * math.sin(st.yaw + b)
            if self.goal is None or math.hypot(mx - self.goal[0], my - self.goal[1]) > 0.25:
                self.goal = (mx, my)                 # erstes Sehen oder das Ding wurde weggerollt
                self.best, self.best_t = math.inf, self.elapsed     # neues Ziel: Fortschritt neu messen
            else:
                k = self.SMOOTH
                self.goal = (self.goal[0] + k * (mx - self.goal[0]), self.goal[1] + k * (my - self.goal[1]))
            furniture = obj.get("art") == "möbel"
        else:
            self.lost_t += dt                        # kurz aus dem Blick: auf die gemerkte Stelle weiterlaufen
            if self.lost_t > 4.0:
                self.goal = None
                return Command(twist=Twist())
            furniture = False
        # Zielmarke für die Anzeige: springt erst, wenn sich das Ziel spürbar bewegt hat (kein Zappeln)
        shown = getattr(self, "seen_at", None)
        if shown is None or math.hypot(self.goal[0] - shown[0], self.goal[1] - shown[1]) > 0.04:
            self.seen_at = self.goal
        gx, gy = self.goal
        # Abstand wie die Wahrnehmung ihn misst (vom Kopf aus, 3 cm vor der Mitte), Richtung vom Rumpf aus
        hx, hy = st.x + 0.03 * math.cos(st.yaw), st.y + 0.03 * math.sin(st.yaw)
        dist = math.hypot(gx - hx, gy - hy)
        bearing = wrap_angle(math.atan2(gy - st.y, gx - st.x) - st.yaw)
        self.search_dir = 1.0 if bearing >= 0 else -1.0
        name = obj["name"] if obj is not None else self.target_name
        if furniture:
            # Möbel: Abstand zur Mitte sagt wenig – der Tiefensensor entscheidet, wann Schluss ist.
            front = (st.perception.sectors or {}).get("mitte")
            if (front is not None and front < 0.24 and abs(bearing) < 20 * DEG) or dist < 0.25:
                return self.finish(f"vor {name} angekommen")
        elif dist <= self.stop_at and abs(bearing) < self.bearing_tol:
            return self.finish(f"vor {name} angekommen ({dist:.2f} m)")
        # festgefahren? (kein Zentimeter näher in 5 s)
        if dist < self.best - 0.015:
            self.best, self.best_t = dist, self.elapsed
        elif self.elapsed - self.best_t > self.STUCK_S:
            self.failed = True
            return self.finish(f"kommt nicht näher ({dist:.2f} m vor {name})")
        vyaw = max(-0.8, min(0.8, 2.0 * bearing))
        vx = 0.0 if abs(bearing) > 0.5 else min(0.15, max(self.MIN_V, (dist - self.stop_at) * 0.8))
        if dist <= self.stop_at:
            vx = 0.0                                 # nah genug, nur noch ausrichten
        head = Head(0.0, clamp(0.25 + 0.3 * (1 - min(1, dist)), "head_pitch"), clamp(bearing * 0.6, "head_yaw"), 0.0)
        # Hindernis-Reflex erst auf den letzten Zentimetern zu kleinen Dingen abschalten
        guard = furniture or dist > 0.45
        return Command(twist=Twist(vx, 0.0, vyaw), head=head, guard=guard)

    # Suchen (seit 0.38.21, Fund „suchen macht er nur durch Drehen … er sollte sich schon etwas bewegen und
    # erkunden“): einmal ganz umsehen; dann zur letzten Sichtung, falls bekannt; sonst ein Stück in eine neue Richtung
    # laufen (Hindernis-Reflex an) und wieder umsehen – bis zu drei Orte, dann ehrlich „nicht gefunden“.
    UMSEHEN_S = 2 * math.pi / 0.6 + 0.5
    STRECKE_M = 0.6
    ORTE = 3

    def _suchen(self, st, dt):
        s = self.suche
        s.setdefault("phase", "umsehen")
        s.setdefault("t", 0.0)
        s.setdefault("orte", 0)
        s["t"] += dt
        if s["phase"] == "umsehen":
            if s["t"] < self.UMSEHEN_S:
                return Command(twist=Twist(0.0, 0.0, 0.6 * self.search_dir),
                               head=Head(0.0, 0.2, 0.4 * self.search_dir, 0.0), guard=False)
            if s["orte"] >= self.ORTE:
                self.failed = True
                return self.finish(f"'{self.target_name}' nicht gefunden – umgesehen und an {s['orte']} Stellen gesucht")
            s["orte"] += 1
            if self.vermutet is not None and s["orte"] == 1:
                s["ziel"] = self.vermutet
            else:
                w = st.yaw + random.choice((-1, 1)) * random.uniform(1.6, 2.6)
                s["ziel"] = (st.x + self.STRECKE_M * math.cos(w), st.y + self.STRECKE_M * math.sin(w))
            s.update(phase="laufen", t=0.0, best=math.inf, best_t=0.0)
        # laufen: zum Suchziel, dann wieder umsehen; hängt sie fest (Wand, Möbel), gleich umsehen
        gx, gy = s["ziel"]
        d = math.hypot(gx - st.x, gy - st.y)
        if d < s["best"] - 0.02:
            s["best"], s["best_t"] = d, s["t"]
        if d < 0.15 or s["t"] - s["best_t"] > 3.0 or s["t"] > 15.0:
            s.update(phase="umsehen", t=0.0)
            return Command(twist=Twist())
        err = wrap_angle(math.atan2(gy - st.y, gx - st.x) - st.yaw)
        vx = 0.0 if abs(err) > 0.6 else 0.14
        return Command(twist=Twist(vx, 0.0, max(-0.9, min(0.9, 2.0 * err))), head=Head(0.0, 0.25, 0.0, 0.0), guard=True)

    def on_stop(self):
        if not self.result or not self.result.startswith("vor "):
            self.failed = True                 # nicht angekommen (abgebrochen, Zeitlimit, nicht gefunden)

    def target(self):
        return getattr(self, "seen_at", None)

    def describe(self):
        return f"annähern an {self.target_name}"


class FollowLaser(Behavior):
    """Dem Laserpunkt hinterherlaufen – wie eine Katze, nur mit Schnabel.

    Der Punkt wird im Raum festgehalten und etwas geglättet (er wandert, aber nicht jede Messung springt). Sie
    bleibt knapp davor stehen und schaut ihn an. Ist er weg, läuft sie noch kurz zur letzten Stelle, sucht dann
    mit dem Kopf und hört nach `LOST_S` Sekunden ohne Punkt von selbst auf. Der Hindernis-Reflex bleibt immer an:
    zeigt der Laser auf ein Möbelstück, bleibt sie davor stehen statt hineinzulaufen.
    """

    name = "laser folgen"
    channels = ("base", "head")
    SMOOTH = 0.35
    KEEP_M = 0.12              # so weit bleibt sie vor dem Punkt stehen (vom Kopf aus gemessen)
    MIN_V = 0.06
    MAX_V = 0.18
    LOST_S = 15.0

    def __init__(self, seconds: float = 120.0) -> None:
        super().__init__()
        self.duration = max(5.0, min(600.0, seconds))
        self.timeout = self.duration + 2
        self.goal: tuple[float, float] | None = None
        self.lost_t = 0.0
        self.seen_once = False
        self.caught = 0               # wie oft sie ihn „erwischt“ hat
        self.search_dir = 1.0
        self._at_dot = False

    @staticmethod
    def _dot(st: DuckState) -> dict[str, Any] | None:
        return next((o for o in st.perception.objects if o.get("art") == "laser"), None)

    def tick(self, st, dt):
        if self.elapsed >= self.duration:
            return self.finish(f"genug gespielt ({self.caught}× erwischt)")
        dot = self._dot(st)
        if dot is not None:
            self.lost_t = 0.0
            self.seen_once = True
            b = math.radians(dot["richtung_grad"])
            r = dot["entfernung_m"] + 0.03
            mx, my = st.x + r * math.cos(st.yaw + b), st.y + r * math.sin(st.yaw + b)
            if self.goal is None or math.hypot(mx - self.goal[0], my - self.goal[1]) > 0.3:
                self.goal = (mx, my)              # Punkt ist gesprungen: gleich dorthin
            else:
                k = self.SMOOTH
                self.goal = (self.goal[0] + k * (mx - self.goal[0]), self.goal[1] + k * (my - self.goal[1]))
        else:
            self.lost_t += dt
            if self.lost_t > self.LOST_S:
                return self.finish("Laserpunkt verloren" if self.seen_once else "keinen Laserpunkt gesehen")
            if self.goal is None or self.lost_t > 2.0:
                # suchen: erst mit dem Kopf hin und her schauen, dann sich langsam in die zuletzt gesehene Richtung drehen
                self.goal = None
                if self.lost_t < 4.0:
                    sweep = math.sin(self.elapsed * 1.6)
                    return Command(twist=Twist(), head=Head(0.0, 0.35, 0.7 * sweep, 0.0))
                return Command(twist=Twist(0.0, 0.0, 0.7 * self.search_dir),
                               head=Head(0.0, 0.35, 0.5 * self.search_dir, 0.0))
        gx, gy = self.goal
        hx, hy = st.x + 0.03 * math.cos(st.yaw), st.y + 0.03 * math.sin(st.yaw)
        dist = math.hypot(gx - hx, gy - hy)
        bearing = wrap_angle(math.atan2(gy - st.y, gx - st.x) - st.yaw)
        self.search_dir = 1.0 if bearing >= 0 else -1.0
        near = dist <= self.KEEP_M + 0.03
        if near and not self._at_dot:
            self.caught += 1
        self._at_dot = near
        vyaw = max(-0.9, min(0.9, 2.0 * bearing))
        if near:
            vx = 0.0
            if abs(bearing) < 0.25:
                vyaw = 0.0                        # davor und ausgerichtet: still stehen und gucken
        elif abs(bearing) > 0.6:
            vx = 0.0                              # erst hindrehen
        else:
            vx = min(self.MAX_V, max(self.MIN_V, (dist - self.KEEP_M) * 0.9))
        look_down = math.atan2(0.21, max(0.05, dist))      # Schnabel auf den Punkt am Boden
        head = Head(0.0, clamp(look_down, "head_pitch"), clamp(bearing * 0.7, "head_yaw"), 0.0)
        return Command(twist=Twist(vx, 0.0, vyaw), head=head)

    def target(self):
        return None                                # der Punkt selbst ist die Markierung

    def describe(self):
        return f"Laserpunkt folgen ({self.duration:.0f}s)"


class FollowMe(Behavior):
    """„Folg mir“: hinter einem Menschen herlaufen und Abstand halten.

    Ziel ist der nächste Mensch in der Wahrnehmung (`art == "person"` – im Simulator die Verkörperung, die die Maus führt;
    am Roboter, sobald die Kamera Menschen meldet). Sie hält etwa `KEEP_M` Abstand, kommt nie näher als
    `NEAR_M` (dann weicht sie langsam zurück) und schaut hoch zum Menschen. Wer stehen bleibt, bei dem bleibt sie
    stehen. Ist der Mensch weg, schaut sie sich um und hört nach `LOST_S` Sekunden auf. Der Hindernis-Reflex bleibt an.
    Erkennung ohne Identifizierung – es wird kein Bild gespeichert.
    """

    name = "folgen"
    channels = ("base", "head")
    KEEP_M = 0.55
    NEAR_M = 0.35
    MAX_V = 0.22
    SMOOTH = 0.4
    LOST_S = 20.0

    def __init__(self, seconds: float = 300.0) -> None:
        super().__init__()
        self.duration = max(10.0, min(1800.0, seconds))
        self.timeout = self.duration + 2
        self.goal: tuple[float, float] | None = None
        self.lost_t = 0.0
        self.seen_once = False
        self.search_dir = 1.0
        self.walked = 0.0

    @staticmethod
    def _person(st: DuckState) -> dict[str, Any] | None:
        people = [o for o in st.perception.objects if o.get("art") == "person"]
        return min(people, key=lambda o: o["entfernung_m"]) if people else None

    def tick(self, st, dt):
        if self.elapsed >= self.duration:
            return self.finish(f"genug gefolgt ({self.walked:.1f} m)")
        man = self._person(st)
        if man is not None:
            self.lost_t = 0.0
            self.seen_once = True
            b = math.radians(man["richtung_grad"])
            r = man["entfernung_m"]
            mx, my = st.x + r * math.cos(st.yaw + b), st.y + r * math.sin(st.yaw + b)
            if self.goal is None or math.hypot(mx - self.goal[0], my - self.goal[1]) > 0.5:
                self.goal = (mx, my)
            else:
                k = self.SMOOTH
                self.goal = (self.goal[0] + k * (mx - self.goal[0]), self.goal[1] + k * (my - self.goal[1]))
        else:
            self.lost_t += dt
            if self.lost_t > self.LOST_S:
                return self.finish("Mensch aus den Augen verloren" if self.seen_once else "niemanden gesehen, dem ich folgen kann")
            if self.goal is None or self.lost_t > 2.5:
                self.goal = None
                if self.lost_t < 5.0:
                    sweep = math.sin(self.elapsed * 1.4)
                    return Command(twist=Twist(), head=Head(0.0, -0.25, 0.8 * sweep, 0.0))
                return Command(twist=Twist(0.0, 0.0, 0.6 * self.search_dir), head=Head(0.0, -0.25, 0.5 * self.search_dir, 0.0))
        gx, gy = self.goal
        dist = math.hypot(gx - st.x, gy - st.y)
        bearing = wrap_angle(math.atan2(gy - st.y, gx - st.x) - st.yaw)
        self.search_dir = 1.0 if bearing >= 0 else -1.0
        vyaw = max(-1.0, min(1.0, 2.2 * bearing))
        if dist < self.NEAR_M:
            vx = -0.06                            # zu nah: einen kleinen Schritt zurück
        elif dist <= self.KEEP_M:
            vx = 0.0
            if abs(bearing) < 0.2:
                vyaw = 0.0
        elif abs(bearing) > 0.7:
            vx = 0.0                              # erst hindrehen
        else:
            vx = min(self.MAX_V, max(0.06, (dist - self.KEEP_M) * 0.8))
        self.walked += max(0.0, vx) * dt
        look_up = -math.atan2(0.5, max(0.3, dist))          # zum Menschen hochschauen
        head = Head(0.0, clamp(look_up, "head_pitch"), clamp(bearing * 0.6, "head_yaw"), 0.0)
        return Command(twist=Twist(vx, 0.0, vyaw), head=head)

    def target(self):
        return None

    def describe(self):
        return f"Mensch folgen ({self.duration:.0f}s)"


class Explore(Behavior):
    """Herumstreifen, Hindernissen ausweichen, sich umschauen."""

    name = "erkunden"
    channels = ("base", "head")

    def __init__(self, duration: float = 60.0, speed: float = 0.14) -> None:
        super().__init__()
        self.duration = max(3.0, min(600.0, duration))
        self.timeout = self.duration + 2
        self.speed = min(0.22, abs(speed))
        self.rng = random.Random()
        self.mode = "go"
        self.mode_t = 0.0
        self.turn_dir = 1.0
        self.drift = 0.0
        self.last_bumps = 0

    def tick(self, st, dt):
        if self.elapsed >= self.duration:
            return self.finish("genug erkundet")
        self.mode_t += dt
        s = st.perception.sectors or {}
        left, mid, right = s.get("links"), s.get("mitte"), s.get("rechts")
        far = 3.0

        def d(v):
            return far if v is None else v

        bumped = False
        if self.engine:
            bumps = sum(1 for e in self.engine.events if e["type"] == "bump")
            bumped = bumps > self.last_bumps
            self.last_bumps = bumps
        scan = Head(0.0, 0.15, 0.5 * math.sin(self.elapsed * 0.9), 0.0)

        if self.mode == "go":
            if bumped or d(mid) < 0.38 or min(d(left), d(right)) < 0.16:
                self.mode, self.mode_t = ("back" if bumped else "turn"), 0.0
                self.turn_dir = 1.0 if d(left) > d(right) else -1.0
                return Command(twist=Twist(), head=scan)
            if self.mode_t > 1.5 and self.rng.random() < 0.02:
                self.drift = self.rng.uniform(-0.4, 0.4)
            steer = self.drift + 0.6 * (min(d(left), 1.0) - min(d(right), 1.0))
            return Command(twist=Twist(self.speed, 0.0, max(-0.7, min(0.7, steer))), head=scan)
        if self.mode == "back":
            if self.mode_t > 0.8:
                self.mode, self.mode_t = "turn", 0.0
            return Command(twist=Twist(-0.08, 0.0, 0.0), head=scan, guard=False)
        # turn
        if self.mode_t > 0.6 and d(mid) > 0.65:
            self.mode, self.mode_t, self.drift = "go", 0.0, 0.0
        if self.mode_t > 4.0:  # in einer Ecke? andere Richtung
            self.turn_dir *= -1
            self.mode_t = 0.0
        return Command(twist=Twist(0.0, 0.0, 0.8 * self.turn_dir),
                       head=Head(0.0, 0.1, 0.5 * self.turn_dir, 0.0))

    def describe(self):
        return f"erkunden ({self.duration:.0f}s)"


# ── Kopf & Ausdruck ───────────────────────────────────────────────────────
class HoldHead(Behavior):
    name = "kopf"
    channels = ("head",)

    def __init__(self, head: Head, seconds: float = 3.0) -> None:
        super().__init__()
        self.head_target = head.clamped()
        self.seconds = max(0.2, min(60.0, seconds))
        self.timeout = self.seconds + 1

    def tick(self, st, dt):
        if self.elapsed >= self.seconds:
            return self.finish()
        return Command(head=self.head_target)

    def describe(self):
        h = self.head_target
        return f"Kopf halten yaw={math.degrees(h.head_yaw):.0f}° pitch={math.degrees(h.head_pitch):.0f}°"


class LookAround(Behavior):
    name = "umschauen"
    channels = ("head",)

    def __init__(self, duration: float = 6.0) -> None:
        super().__init__()
        self.duration = max(1.0, min(60.0, duration))
        self.timeout = self.duration + 1
        self.points = [(-0.9, 0.1), (-0.4, -0.3), (0.3, 0.25), (0.9, -0.1), (0.0, -0.4), (0.0, 0.1)]

    def tick(self, st, dt):
        if self.elapsed >= self.duration:
            return self.finish("umgeschaut")
        seg = 1.1
        i = int(self.elapsed / seg)
        a = self.points[i % len(self.points)]
        b = self.points[(i + 1) % len(self.points)]
        k = smoothstep((self.elapsed % seg) / seg * 1.6)
        yaw = a[0] + (b[0] - a[0]) * k
        pitch = a[1] + (b[1] - a[1]) * k
        return Command(head=Head(0.0, pitch, yaw, -0.15 * yaw))


class Dance(Behavior):
    """Tanzen im Takt. Stile: wackeln, nicken, drehen, party."""

    name = "tanzen"
    channels = ("base", "head", "mouth", "pose")
    STYLES = ("wackeln", "nicken", "drehen", "party")

    def __init__(self, style: str = "party", duration: float = 12.0, bpm: float = 110) -> None:
        super().__init__()
        self.style = style if style in self.STYLES else "party"
        self.needs_legs = self.style != "nicken"      # nur nicken geht auch im Sitzen
        self.duration = max(2.0, min(120.0, duration))
        self.timeout = self.duration + 1
        self.bpm = max(60.0, min(160.0, bpm))
        self._last_beat = -1

    def tick(self, st, dt):
        if self.elapsed >= self.duration:
            return self.finish("Tanz beendet")
        beat_len = 60.0 / self.bpm
        beat = self.elapsed / beat_len
        b = int(beat)
        ph = 2 * math.pi * beat
        bar = b // 4
        if b != self._last_beat:
            self._last_beat = b
            # mitsingen wie eine Ente: kurze Quaks im Takt (jeder 4. Schlag, am Taktanfang ein kräftiges), kein Jauchzen
            if b % 4 == 0 and self.engine:
                self.engine.fire(self.engine.backend.sound("greet" if b % 8 == 0 else "chirp"))
        mouth = 0.5 if (beat % 1.0) < 0.2 and b % 2 == 0 else 0.0
        style = self.style
        if style == "party":
            style = ("wackeln", "nicken", "drehen")[bar % 3]
        if style == "wackeln":
            sway = math.sin(ph / 2)
            return Command(twist=Twist(0.0, 0.0, 0.5 * sway),
                           head=Head(0.0, 0.1, -0.3 * sway, -0.3 * sway),
                           pose=Pose(-0.008, 0.2 * sway, 0.0), mouth=mouth)
        if style == "nicken":
            bob = math.sin(ph)
            return Command(twist=Twist(),
                           head=Head(-0.15 * bob, 0.35 * bob, 0.15 * math.sin(ph / 4), 0.0),
                           pose=Pose(-0.012 + 0.01 * bob, 0.0, 0.12 * bob), mouth=mouth)
        # drehen: zwei Takte links, zwei rechts
        direction = 1.0 if (bar % 2 == 0) else -1.0
        return Command(twist=Twist(0.0, 0.0, 0.9 * direction),
                       head=Head(0.0, -0.1, 0.5 * direction, 0.2 * math.sin(ph)),
                       pose=Pose(-0.005, 0.1 * math.sin(ph), 0.0), mouth=mouth)

    def describe(self):
        return f"tanzen ({self.style}, {self.bpm:.0f} bpm, {self.duration:.0f}s)"


SKILL_VOICE = {"kick_left": "kick", "kick_right": "kick", "roulade": "albern", "ground_pick": "picken",
               "sit_toggle": None}
VOICES: dict[str, dict[str, Any]] = {
    "tanz": {"start": "greet", "takt": 1.6, "folge": ("chirp", "greet")},
    "albern": {"start": "chirp", "takt": 2.4, "folge": ("chirp", "inquire")},
    "panne": {"start": "alarm", "takt": 0.0, "folge": ()},
    "gehen": {"start": "chirp", "takt": 3.0, "folge": ("chirp",)},
    "alltag": {"start": "coo", "takt": 0.0, "folge": ()},
    "kick": {"start": "greet", "takt": 0.0, "folge": ()},
    "picken": {"start": "peck", "takt": 0.0, "folge": ()},
}


class TrickVoice:
    """Spielt zu einem laufenden Trick passende Laute: einen zum Start, dann (optional) im Takt."""

    def __init__(self, style: str | None) -> None:
        self.plan = VOICES.get(style or "") if style else None
        self.next_t = 0.0
        self.i = 0

    def tick(self, behavior: Behavior, elapsed: float) -> None:
        if not self.plan or behavior.engine is None:
            return
        if self.i == 0:
            tag = self.plan["start"]
            self.next_t = elapsed + (self.plan["takt"] or 1e9)
        elif elapsed >= self.next_t and self.plan["folge"]:
            tag = self.plan["folge"][(self.i - 1) % len(self.plan["folge"])]
            self.next_t = elapsed + self.plan["takt"]
        else:
            return
        self.i += 1
        behavior.engine.fire(behavior.engine.backend.sound(tag))


class SkillRun(Behavior):
    """robot.do ausführen und warten, bis er fertig ist – mit passenden Lauten (`voice`, Standard je Skill)."""

    name = "skill"
    channels = ("base",)

    def __init__(self, skill: str, voice: str | None = "auto") -> None:
        super().__init__()
        self.skill = skill
        self.voice = TrickVoice(SKILL_VOICE.get(skill, "albern") if voice == "auto" else voice)
        self.timeout = 15.0
        self.needs_legs = skill != "sit_toggle"
        # Treten und Aufheben ergeben nur Sinn, wenn das Annähern davor geklappt hat
        self.needs_target = skill in ("kick_left", "kick_right", "ground_pick")
        self._task = None
        self._seen_running = False

    def on_start(self, st):
        if self.engine:
            self._task = self.engine.fire(self.engine.backend.do(self.skill))

    def tick(self, st, dt):
        if self._task is None:
            return self.finish("kein Backend")
        if not self._task.done():
            return Command(twist=Twist())
        res = self._task.result()
        if not res.accepted:
            return self.finish(f"abgelehnt: {res.reason}")
        if st.skill:
            self._seen_running = True
            self.voice.tick(self, self.elapsed)
        elif self._seen_running or self.elapsed > 1.0:
            return self.finish(f"{self.skill} ausgeführt")
        return Command(twist=Twist())

    def describe(self):
        return f"skill {self.skill}"



class KickBall(Behavior):
    """Ball schießen: ist er außer Reichweite des Fußes, erst hin, dann treten.

    Der Fuß trifft, wenn der Ball höchstens ≈ 19 cm vor dem Kopf und grob geradeaus liegt. Sobald das beim
    Hingehen erreicht ist, tritt sie – sie muss nicht erst „genau angekommen“ sein (in echter Physik schafft
    der Gang die letzten Zentimeter und Grad oft nicht sauber).
    """

    name = "schießen"
    channels = ("base", "head")
    REACH_M = 0.19            # gemessene Entfernung (vom Kopf), bis zu der der Tritt trifft
    ANGLE_DEG = 20.0

    def __init__(self, skill: str = "kick_left") -> None:
        super().__init__()
        self.skill = skill if skill in ("kick_left", "kick_right") else "kick_left"
        self.needs_target = True
        self.timeout = 70.0                       # Annähern (≤ 40 s) + Tritt (≤ 15 s) + Luft
        self.phase = "tritt"
        self.inner: Behavior | None = None

    @staticmethod
    def _ball(st: DuckState) -> dict[str, Any] | None:
        return next((o for o in st.perception.objects if o.get("art") == "ball"), None)

    def kontakt_ziel(self, st: DuckState) -> tuple[float, float, float] | None:
        """Den Ball soll sie treffen – beim Hingehen wie beim Tritt."""
        if self.inner is not None:
            z = self.inner.kontakt_ziel(st)
            if z:
                return z
        b = self._ball(st)
        return None if b is None else (*_welt(st, b), Approach.KONTAKT_R)

    def _in_reach(self, st: DuckState) -> bool:
        goal = getattr(self.inner, "goal", None) if self.phase == "hin" else None
        if goal is not None:                     # geglättete Position aus dem Annähern (ruhiger als eine Messung)
            hx, hy = st.x + 0.03 * math.cos(st.yaw), st.y + 0.03 * math.sin(st.yaw)
            d = math.hypot(goal[0] - hx, goal[1] - hy)
            bearing = abs(math.degrees(wrap_angle(math.atan2(goal[1] - st.y, goal[0] - st.x) - st.yaw)))
            return d <= self.REACH_M - 0.01 and bearing <= self.ANGLE_DEG
        b = self._ball(st)
        return bool(b) and b["entfernung_m"] <= self.REACH_M and abs(b["richtung_grad"]) <= self.ANGLE_DEG

    def _use(self, b: Behavior) -> None:
        b.engine = self.engine
        self.inner = b

    def _kick(self) -> None:
        if self.engine is not None:
            have = self.engine.backend.skills()
            other = "kick_right" if self.skill == "kick_left" else "kick_left"
            if have and self.skill not in have and other in have:
                self.skill = other              # z. B. nur Pollens Linksschuss geladen
        self.phase = "tritt"
        self._use(SkillRun(self.skill))

    def on_start(self, st):
        if not self._in_reach(st):               # außer Reichweite oder gar nicht im Blick: erst hin (sucht auch)
            self.phase = "hin"
            self._use(Approach("ball", stop_at=self.REACH_M - 0.03, bearing_tol_deg=12.0))
        else:
            self._kick()

    def tick(self, st, dt):
        if self.phase == "hin" and self._in_reach(st):
            self.inner.on_stop()
            self._kick()                          # nah genug: gleich treten
            return Command(twist=Twist())
        cmd = self.inner._step(st, dt)
        if not self.inner.done:
            return cmd
        if self.phase == "hin":
            if self._in_reach(st) or (self.inner.result or "").startswith("vor "):
                self._kick()
                return Command(twist=Twist())
            self.failed = True
            return self.finish(f"nicht am Ball: {self.inner.result}")
        return self.finish(self.inner.result)

    def on_stop(self):
        if self.inner is not None and not self.inner.done:
            self.inner.on_stop()

    def target(self):
        return self.inner.target() if self.inner is not None and self.phase == "hin" else None

    def describe(self):
        return f"Ball schießen ({'links' if self.skill == 'kick_left' else 'rechts'})"

class Pause(Behavior):
    name = "pause"
    channels = ("base",)

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self.needs_legs = False              # warten geht auch im Sitzen
        self.seconds = max(0.0, min(60.0, seconds))
        self.timeout = self.seconds + 1

    def tick(self, st, dt):
        if self.elapsed >= self.seconds:
            return self.finish()
        return Command(twist=Twist())

    def describe(self):
        return f"pause {self.seconds:.1f}s"
