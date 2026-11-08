"""Parcours: Hindernisse beschreiben, in MuJoCo aufbauen und die Ente darüber laufen lassen.

Wie in NVIDIAs Microduck-Vorführung (Parcours planen → bauen → Policy prüfen), aber ohne
Isaac Sim und ohne NVIDIA-Karte: Claude (oder das lokale Sprachmodell) beschreibt den Parcours
als Liste von Elementen, duckpilot baut daraus Geometrie in Pollens MuJoCo-Welt und lässt eine
Geh-Policy mehrere Male hindurchlaufen – auf dem Prozessor, schneller als Echtzeit, die
Versuche nebeneinander. Ergebnis: pro Element geschafft / gestürzt / steckt fest, dazu eine
Aufzeichnung, die die Oberfläche in 3D abspielt.

Die Bahn läuft entlang x, ist 50 cm breit und um den Nullpunkt zentriert. Elemente:

* rampe     – hinauf, oben eben, hinunter            (hoehe_cm, laenge_cm, plateau_cm)
* stufen    – Treppe hinauf, oben eben, hinunter    (anzahl, hoehe_cm, tiefe_cm, plateau_cm)
* schwelle  – eine Kante quer über die Bahn         (hoehe_cm, tiefe_cm)
* uneben    – Feld aus flachen Platten              (hoehe_cm, laenge_cm)
* slalom    – Stangen, abwechselnd links/rechts umrunden (anzahl, abstand_cm, versatz_cm)
* engstelle – zwei Wände, dazwischen eine Gasse     (breite_cm, laenge_cm)

Die Richtwerte, was die Policies können, sind Schätzungen aus Pollens Trainingsumgebungen
(ebener Boden bzw. „Rough“ mit Stufen und Schrägen) – darüber warnt duckpilot, baut aber.
"""

from __future__ import annotations

import concurrent.futures as cf
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .params import ROBOT_ACTION_SCALE

LANE_W = 0.5           # Bahnbreite
GAP = 0.35             # Abstand zwischen Elementen
LEAD_IN = 0.45         # Start bis erstes Element
LEAD_OUT = 0.4         # letztes Element bis Ziel
MAX_ELEMENTS = 8
MAX_LENGTH = 8.0
REPLAY_HZ = 25         # 50 Hz Regelung, jedes 2. Bild
FALL_UP = 0.45
STAND_UP = 0.85

# Parameter je Element: (Name, Minimum, Maximum, Standard)
PARAMS: dict[str, list[tuple[str, float, float, float]]] = {
    "rampe": [("hoehe_cm", 1, 10, 4), ("laenge_cm", 20, 100, 40), ("plateau_cm", 10, 60, 20)],
    "stufen": [("anzahl", 1, 4, 2), ("hoehe_cm", 0.5, 6, 2), ("tiefe_cm", 8, 30, 15), ("plateau_cm", 10, 60, 20)],
    "schwelle": [("hoehe_cm", 0.5, 4, 1.5), ("tiefe_cm", 2, 10, 4)],
    "uneben": [("hoehe_cm", 0.5, 3, 1.2), ("laenge_cm", 30, 150, 60)],
    "slalom": [("anzahl", 2, 6, 3), ("abstand_cm", 25, 80, 40), ("versatz_cm", 11, 25, 15)],
    "engstelle": [("breite_cm", 15, 40, 24), ("laenge_cm", 10, 80, 30)],
}
LABEL = {"rampe": "Rampe", "stufen": "Stufen", "schwelle": "Schwelle", "uneben": "Unebener Boden",
         "slalom": "Slalom", "engstelle": "Engstelle"}
COLOR = {"rampe": "#8a6f4f", "stufen": "#6f7f99", "schwelle": "#9a7a3d", "uneben": "#5f7f6a",
         "slalom": "#d2a106", "engstelle": "#7d6f99"}
INTS = {"anzahl"}

# Richtwerte, was die Geh-Policies können (Schätzung) – darüber gibt es eine Warnung
COMFORT = {"rampe": 12.0, "stufen": 2.5, "schwelle": 2.0, "uneben": 1.5, "engstelle": 20.0}

PRESETS: dict[str, dict[str, Any]] = {
    "Rampe und Stufen": {"elemente": [{"art": "rampe", "hoehe_cm": 4, "laenge_cm": 40},
                                      {"art": "stufen", "anzahl": 2, "hoehe_cm": 1.5, "tiefe_cm": 15}]},
    "Slalom": {"elemente": [{"art": "slalom", "anzahl": 4, "abstand_cm": 40, "versatz_cm": 15}]},
    "Alles einmal": {"elemente": [{"art": "schwelle", "hoehe_cm": 1}, {"art": "rampe", "hoehe_cm": 3},
                                  {"art": "slalom", "anzahl": 3}, {"art": "uneben", "hoehe_cm": 1},
                                  {"art": "engstelle", "breite_cm": 26}, {"art": "stufen", "anzahl": 1,
                                                                          "hoehe_cm": 1.5}]},
}


class CourseError(ValueError):
    pass


def _n(v: float) -> str:
    """Zahl auf Deutsch: 1,5 statt 1.5."""
    return f"{v:g}".replace(".", ",")


@dataclass
class Element:
    art: str
    p: dict[str, float]
    index: int
    x0: float = 0.0
    x1: float = 0.0
    geoms: list[dict[str, Any]] = field(default_factory=list)
    waypoints: list[tuple[float, float]] = field(default_factory=list)
    warnung: str | None = None

    @property
    def label(self) -> str:
        return f"{self.index + 1}. {LABEL[self.art]}"

    def describe(self) -> str:
        p = self.p
        if self.art == "rampe":
            return f"{_n(p['hoehe_cm'])} cm hoch, {self.angle():.0f}° steil"
        if self.art == "stufen":
            return f"{int(p['anzahl'])} × {_n(p['hoehe_cm'])} cm, {_n(p['tiefe_cm'])} cm tief"
        if self.art == "schwelle":
            return f"{_n(p['hoehe_cm'])} cm hoch"
        if self.art == "uneben":
            return f"bis {_n(p['hoehe_cm'])} cm, {_n(p['laenge_cm'])} cm lang"
        if self.art == "slalom":
            return f"{int(p['anzahl'])} Stangen, {_n(p['abstand_cm'])} cm Abstand"
        return f"{_n(p['breite_cm'])} cm breit, {_n(p['laenge_cm'])} cm lang"

    def angle(self) -> float:
        return math.degrees(math.atan2(self.p["hoehe_cm"], self.p["laenge_cm"])) if self.art == "rampe" else 0.0


@dataclass
class Course:
    name: str
    elements: list[Element]
    length: float
    start: tuple[float, float]
    goal: tuple[float, float]
    waypoints: list[tuple[float, float]]

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "elemente": [{"art": e.art, **e.p} for e in self.elements]}

    def geoms(self) -> list[dict[str, Any]]:
        return [g for e in self.elements for g in e.geoms]

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name, "laenge_m": round(self.length, 2),
            "elemente": [{"nr": e.index + 1, "art": e.art, "titel": LABEL[e.art], "kurz": e.describe(),
                          "von_m": round(e.x0, 2), "bis_m": round(e.x1, 2), "warnung": e.warnung, **e.p}
                         for e in self.elements],
            "warnungen": [f"{e.label}: {e.warnung}" for e in self.elements if e.warnung],
        }

    def world(self) -> dict[str, Any]:
        """Für die 3D-Ansicht: offene Halle, gekippte Platten als „teile“, Stangen als Zylinder."""
        teile, cyl = [], []
        for g in self.geoms():
            if g["typ"] == "box":
                (x, y, z), (hx, hy, hz) = g["pos"], g["size"]
                teile.append({"x": round(x, 4), "y": round(y, 4), "z": round(z, 4), "sx": round(2 * hx, 4),
                              "sy": round(2 * hy, 4), "sz": round(2 * hz, 4), "pitch": round(g.get("pitch", 0.0), 5),
                              "color": g["color"]})
            else:
                (x, y, _), (r, hz) = g["pos"], g["size"]
                cyl.append({"name": g["name"], "x": round(x, 4), "y": round(y, 4), "r": r, "h": 2 * hz,
                            "color": g["color"]})
        for (x, label, col) in ((self.start[0], "Start", "#24a148"), (self.goal[0], "Ziel", "#f0962c")):
            teile.append({"x": x, "y": 0.0, "z": 0.001, "sx": 0.03, "sy": LANE_W, "sz": 0.002, "pitch": 0.0,
                          "color": col, "marke": label})
        return {"width": round(self.length + 1.2, 2), "depth": 1.6, "offen": True, "boxes": [], "cylinders": cyl,
                "teile": teile, "bahn": {"von": round(self.start[0], 3), "bis": round(self.goal[0], 3), "breite": LANE_W}}


# ── Aufbauen ────────────────────────────────────────────────────────────
def _clean(el: dict[str, Any]) -> tuple[str, dict[str, float], list[str]]:
    art = str(el.get("art") or el.get("typ") or "").strip().lower()
    if art not in PARAMS:
        raise CourseError(f"Unbekanntes Element „{art[:20]}“ – erlaubt: {', '.join(PARAMS)}")
    p: dict[str, float] = {}
    notes = []
    for name, lo, hi, default in PARAMS[art]:
        raw = el.get(name, default)
        try:
            v = float(default if raw is None else raw)
        except (TypeError, ValueError):
            raise CourseError(f"{LABEL[art]}: {name} muss eine Zahl sein") from None
        if not math.isfinite(v):
            v = default
        if v < lo or v > hi:
            notes.append(f"{name} {_n(v)} → {_n(min(hi, max(lo, v)))} (erlaubt {_n(lo)}–{_n(hi)})")
            v = min(hi, max(lo, v))
        p[name] = float(round(v)) if name in INTS else round(v, 2)
    return art, p, notes


def _box(name, x, y, z, hx, hy, hz, color, pitch=0.0) -> dict[str, Any]:
    return {"typ": "box", "name": name, "pos": (x, y, z), "size": (hx, hy, hz), "pitch": pitch, "color": color}


def _ramp_geoms(e: Element, x0: float) -> float:
    h, run, plat = e.p["hoehe_cm"] / 100, e.p["laenge_cm"] / 100, e.p["plateau_cm"] / 100
    a = math.atan2(h, run)
    t = 0.02
    slope = math.hypot(run, h)
    col = COLOR["rampe"]
    hy = LANE_W / 2
    # rauf: Drehung um y mit −a hebt das +x-Ende; Oberkante läuft von (x0, 0) nach (x0+run, h)
    for k, (xa, sign) in enumerate(((x0, -1), (x0 + run + plat, 1))):
        theta = sign * a
        nx, nz = math.sin(theta), math.cos(theta)
        mx, mz = xa + run / 2, h / 2
        e.geoms.append(_box(f"p:{e.index}:{'auf' if k == 0 else 'ab'}", mx - nx * t / 2, 0.0, mz - nz * t / 2,
                            slope / 2, hy, t / 2, col, pitch=theta))
    e.geoms.append(_box(f"p:{e.index}:oben", x0 + run + plat / 2, 0.0, h / 2, plat / 2, hy, h / 2, col))
    return x0 + 2 * run + plat


def _stairs_geoms(e: Element, x0: float) -> float:
    n, h, d, plat = int(e.p["anzahl"]), e.p["hoehe_cm"] / 100, e.p["tiefe_cm"] / 100, e.p["plateau_cm"] / 100
    end = x0 + 2 * n * d + plat
    for i in range(1, n + 1):
        a, b = x0 + (i - 1) * d, end - (i - 1) * d
        e.geoms.append(_box(f"p:{e.index}:stufe{i}", (a + b) / 2, 0.0, i * h / 2, (b - a) / 2, LANE_W / 2, i * h / 2,
                            COLOR["stufen"]))
    return end


def build(spec: dict[str, Any]) -> Course:
    """Aus der Beschreibung (Name + Elemente) einen Parcours bauen. Wirft CourseError."""
    if not isinstance(spec, dict):
        raise CourseError("Der Parcours ist ein Objekt mit „elemente“.")
    raw = spec.get("elemente") or []
    if not isinstance(raw, list):
        raise CourseError("„elemente“ ist eine Liste.")
    if not raw:
        raise CourseError("Der Parcours braucht mindestens ein Element.")
    if len(raw) > MAX_ELEMENTS:
        raise CourseError(f"Höchstens {MAX_ELEMENTS} Elemente")
    name = " ".join(str(spec.get("name") or "Parcours").split())[:48] or "Parcours"
    elements: list[Element] = []
    x = LEAD_IN
    for i, el in enumerate(raw):
        if not isinstance(el, dict):
            raise CourseError("Jedes Element ist ein Objekt mit „art“")
        art, p, notes = _clean(el)
        e = Element(art, p, i)
        e.x0 = x
        if art == "rampe":
            x = _ramp_geoms(e, x)
        elif art == "stufen":
            x = _stairs_geoms(e, x)
        elif art == "schwelle":
            h, d = p["hoehe_cm"] / 100, p["tiefe_cm"] / 100
            e.geoms.append(_box(f"p:{i}:kante", x + d / 2, 0.0, h / 2, d / 2, LANE_W / 2, h / 2, COLOR["schwelle"]))
            x += d
        elif art == "uneben":
            h, length = p["hoehe_cm"] / 100, p["laenge_cm"] / 100
            rng = random.Random(1000 + i)
            tile = 0.06
            nx_, ny_ = max(1, round(length / tile)), round(LANE_W / tile)
            for a in range(nx_):
                for b in range(ny_):
                    th = h * rng.uniform(0.25, 1.0)
                    e.geoms.append(_box(f"p:{i}:platte{a}_{b}", x + (a + 0.5) * length / nx_,
                                        -LANE_W / 2 + (b + 0.5) * LANE_W / ny_, th / 2, length / nx_ / 2 * 0.98,
                                        LANE_W / ny_ / 2 * 0.98, th / 2, COLOR["uneben"]))
            x += length
        elif art == "slalom":
            n, d, off = int(p["anzahl"]), p["abstand_cm"] / 100, p["versatz_cm"] / 100
            for k in range(n):
                px = x + (k + 0.5) * d
                e.geoms.append({"typ": "cyl", "name": f"p:{i}:stange{k + 1}", "pos": (px, 0.0, 0.15),
                                "size": (0.015, 0.15), "color": COLOR["slalom"]})
                e.waypoints.append((px, off if k % 2 == 0 else -off))
            x += n * d
        elif art == "engstelle":
            w, length = p["breite_cm"] / 100, p["laenge_cm"] / 100
            for side in (1, -1):
                e.geoms.append(_box(f"p:{i}:wand{'l' if side > 0 else 'r'}", x + length / 2, side * (w / 2 + 0.01),
                                    0.06, length / 2, 0.01, 0.06, COLOR["engstelle"]))
            x += length
        e.x1 = x
        level = e.angle() if art == "rampe" else (p.get("hoehe_cm") if art in ("stufen", "schwelle", "uneben") else None)
        if art == "engstelle":
            if p["breite_cm"] < COMFORT["engstelle"]:
                e.warnung = f"nur {_n(p['breite_cm'])} cm breit – die Ente ist etwa 15 cm breit, das wird eng"
        elif level is not None and level > COMFORT[art]:
            unit = "°" if art == "rampe" else " cm"
            e.warnung = (f"{_n(round(level, 1))}{unit} liegt über dem, was die Geh-Policies vermutlich können "
                         f"(Richtwert {_n(COMFORT[art])}{unit}) – gut als Ziel fürs Training")
        if notes:
            e.warnung = "; ".join([*notes, *([e.warnung] if e.warnung else [])])
        elements.append(e)
        x += GAP
    total = x - GAP + LEAD_OUT
    if total > MAX_LENGTH:
        raise CourseError(f"Der Parcours wäre {_n(round(total, 1))} m lang – höchstens {_n(MAX_LENGTH)} m")
    shift = -total / 2
    for e in elements:
        e.x0 += shift
        e.x1 += shift
        for g in e.geoms:
            px, py, pz = g["pos"]
            g["pos"] = (px + shift, py, pz)
        e.waypoints = [(wx + shift, wy) for wx, wy in e.waypoints]
    start = (shift + 0.05, 0.0)
    goal = (total + shift - 0.05, 0.0)
    wps: list[tuple[float, float]] = []
    for e in elements:
        wps.append((e.x0 - 0.06, 0.0))
        wps.extend(e.waypoints)
        wps.append((e.x1 + 0.06, 0.0))
    wps.append(goal)
    return Course(name, elements, total, start, goal, wps)


def add_to_spec(mjspec, course: Course) -> None:
    """Die Geometrie in eine MjSpec setzen (fest mit der Welt verbunden)."""
    import mujoco

    body = mjspec.worldbody
    for g in course.geoms():
        if g["typ"] == "box":
            pitch = g.get("pitch", 0.0)
            geom = body.add_geom(name=g["name"], type=mujoco.mjtGeom.mjGEOM_BOX, pos=list(g["pos"]),
                                 size=list(g["size"]), quat=[math.cos(pitch / 2), 0.0, math.sin(pitch / 2), 0.0])
        else:
            r, hz = g["size"]
            geom = body.add_geom(name=g["name"], type=mujoco.mjtGeom.mjGEOM_CYLINDER, pos=list(g["pos"]),
                                 size=[r, hz, 0])
        geom.friction = [1.0, 0.005, 0.0001]


# ── Durchlaufen ─────────────────────────────────────────────────────────
@dataclass
class Attempt:
    nr: int
    elemente: list[str]
    ziel: bool
    zeit_s: float
    stuerze: list[dict[str, Any]]
    max_neigung_grad: float
    ende: str
    bahn: list[tuple[float, float]]
    reibung: float
    replay: list[list[float]] | None = None


def _drive(target: tuple[float, float], tr: dict[str, float]) -> tuple[float, float]:
    """Einfacher Wegfolger: zur nächsten Marke drehen und gehen (Vorwärts, Drehrate)."""
    dx, dy = target[0] - tr["x"], target[1] - tr["y"]
    err = (math.atan2(dy, dx) - tr["yaw"] + math.pi) % (2 * math.pi) - math.pi
    vyaw = max(-1.2, min(1.2, 2.2 * err))
    vx = 0.24 * max(0.0, math.cos(err)) ** 2
    if abs(err) > 0.9:
        vx = 0.03
    return vx, vyaw


def run_attempt(course: Course, policy_path: str, nr: int = 0, action_scale: float = ROBOT_ACTION_SCALE, seed: int = 0,
                record: bool = False, max_seconds: float | None = None, use_bam: bool | None = None,
                cancel: Callable[[], bool] | None = None) -> Attempt:
    from .core import CONTROL_DT, Command, PhysicsCore, Policy

    rng = random.Random(seed * 7919 + nr)
    core = PhysicsCore(None, use_bam=use_bam, course=course)
    friction = 1.0 if nr == 0 else rng.uniform(0.7, 1.15)        # Versuch 1 ohne Abweichung
    core.model.geom_friction[:, 0] *= friction
    pol = Policy(policy_path, "parcours", action_scale)
    core.set_policy(pol)
    sy = 0.0 if nr == 0 else rng.uniform(-0.02, 0.02)
    syaw = 0.0 if nr == 0 else math.radians(rng.uniform(-4, 4))
    core.reset(course.start[0], sy, syaw)
    for _ in range(int(0.6 / CONTROL_DT)):
        core.control_step(Command())
    limit = max_seconds or min(150.0, 25.0 + course.length / 0.1)
    n_el = len(course.elements)
    status = ["nicht erreicht"] * n_el
    entered = [False] * n_el
    wp = 0
    t = 0.0
    falls: list[dict[str, Any]] = []
    fallen_since: float | None = None
    best_x, best_t = course.start[0], 0.0
    tilt_max = 0.0
    path: list[tuple[float, float]] = []
    frames: list[list[float]] | None = [] if record else None
    end = "Zeit abgelaufen"
    every = max(1, round(1 / (REPLAY_HZ * CONTROL_DT)))
    step = 0
    slalom_hit: dict[int, set[int]] = {}

    def element_at(x: float) -> int | None:
        for i, e in enumerate(course.elements):
            if e.x0 - 0.08 <= x <= e.x1 + 0.08:
                return i
        return None

    while t < limit:
        if cancel and cancel():
            end = "abgebrochen"
            break
        tr = core.trunk()
        cmd = Command()
        upright = tr["up"] > FALL_UP
        if upright and fallen_since is None:
            while wp < len(course.waypoints) and (
                    math.hypot(course.waypoints[wp][0] - tr["x"], course.waypoints[wp][1] - tr["y"]) < 0.07
                    or course.waypoints[wp][0] < tr["x"] - 0.1):          # schon vorbei: nicht umkehren
                wp += 1
            if wp >= len(course.waypoints) or tr["x"] >= course.goal[0]:
                end = "im Ziel"
                break
            vx, vyaw = _drive(course.waypoints[wp], tr)
            cmd.twist[:] = [vx, 0.0, vyaw]
        core.control_step(cmd)
        t += CONTROL_DT
        step += 1
        tr = core.trunk()
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, tr["up"]))))
        tilt_max = max(tilt_max, tilt)
        here = element_at(tr["x"])
        if here is not None:
            entered[here] = True
            e = course.elements[here]
            if e.art == "slalom":
                hit = slalom_hit.setdefault(here, set())
                for k, (px, py) in enumerate(e.waypoints):
                    if abs(tr["x"] - px) < 0.06 and (tr["y"] - 0.0) * py > 0:
                        hit.add(k)
        for i, e in enumerate(course.elements):
            if status[i] == "nicht erreicht" and tr["x"] > e.x1 + 0.03 and tr["up"] > STAND_UP:
                if e.art == "slalom" and len(slalom_hit.get(i, ())) < len(e.waypoints):
                    status[i] = "Stange ausgelassen"
                else:
                    status[i] = "geschafft"
        # Sturz und Aufstehen
        if tr["up"] < FALL_UP and fallen_since is None:
            fallen_since = t
            falls.append({"t": round(t, 2), "x": round(tr["x"], 3), "y": round(tr["y"], 3),
                          "element": course.elements[here].label if here is not None else None})
            if here is not None and status[here] == "nicht erreicht":
                status[here] = "gestürzt"
        elif fallen_since is not None:
            if tr["up"] > STAND_UP and tr["z"] > 0.07:
                fallen_since = None
            elif t - fallen_since > 4.0:
                end = "liegt und kommt nicht hoch"
                break
        if len(falls) >= 3 and fallen_since is not None:
            end = "dreimal gestürzt"
            break
        # Fortschritt
        if tr["x"] > best_x + 0.03:
            best_x, best_t = tr["x"], t
        elif t - best_t > 10.0 and fallen_since is None:
            end = "steckt fest"
            if here is not None and status[here] == "nicht erreicht":
                status[here] = "steckt fest"
            break
        if step % every == 0:
            path.append((round(tr["x"], 3), round(tr["y"], 3)))
            if frames is not None:
                j = core.joints()
                frames.append([round(t, 2), round(tr["x"], 4), round(tr["y"], 4), round(tr["yaw"], 4),
                               round(tr["z"], 4), round(tr["roll"], 4), round(tr["pitch"], 4),
                               *(round(j[n], 3) for n in ("left_hip_yaw", "left_hip_roll", "left_hip_pitch",
                                                          "left_knee", "left_ankle", "neck_pitch", "head_pitch",
                                                          "head_yaw", "head_roll")), 0.0,
                               *(round(j[n], 3) for n in ("right_hip_yaw", "right_hip_roll", "right_hip_pitch",
                                                          "right_knee", "right_ankle"))])
    for i, _e in enumerate(course.elements):
        if status[i] == "nicht erreicht" and entered[i] and end == "Zeit abgelaufen":
            status[i] = "zu langsam"
    return Attempt(nr + 1, status, end == "im Ziel", round(t, 1), falls, round(tilt_max, 1), end, path,
                   round(friction, 2), frames)


def evaluate(course: Course, policy_path: str, attempts: int = 3, action_scale: float = ROBOT_ACTION_SCALE, label: str = "",
             progress: Callable[[str], None] | None = None, workers: int | None = None,
             max_seconds: float | None = None, use_bam: bool | None = None,
             cancel: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Mehrere Versuche (Versuch 1 genau, die übrigen mit etwas anderer Reibung und Startlage)."""
    attempts = max(1, min(5, int(attempts)))
    t0 = time.perf_counter()
    workers = workers or min(attempts, 4)
    results: list[Attempt] = []
    done = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(run_attempt, course, policy_path, i, action_scale, 0, i == 0, max_seconds, use_bam, cancel)
                for i in range(attempts)]
        for fut in cf.as_completed(futs):
            results.append(fut.result())
            done += 1
            if progress:
                progress(f"{done} von {attempts} Versuchen gerechnet")
    results.sort(key=lambda a: a.nr)
    per_el = []
    for i, e in enumerate(course.elements):
        st = [a.elemente[i] for a in results]
        ok = sum(s == "geschafft" for s in st)
        per_el.append({"nr": i + 1, "titel": LABEL[e.art], "kurz": e.describe(), "geschafft": ok, "von": len(results),
                       "ergebnisse": st})
    full = sum(a.ziel for a in results)
    weakest = min(per_el, key=lambda r: r["geschafft"]) if per_el else None
    hints = []
    early = [a for a in results if a.stuerze and a.stuerze[0].get("element") is None
             and all(x == "nicht erreicht" for x in a.elemente)]
    if full == len(results):
        hints.append("Alle Versuche im Ziel.")
    elif len(early) == len(results):
        hints.append("Schon auf der Anlaufstrecke gestürzt, noch vor dem ersten Element – die Policy hält die Ente "
                     "nicht einmal auf ebenem Boden. Passt sie zur Microduck (61 Beobachtungen, 14 Gelenke)?")
    elif weakest and weakest["geschafft"] < weakest["von"]:
        hints.append(f"Schwächstes Element: {weakest['nr']}. {weakest['titel']} ({weakest['kurz']}) – "
                     f"{weakest['geschafft']} von {weakest['von']} geschafft.")
    falls = [{**f, "versuch": a.nr} for a in results for f in a.stuerze]
    return {
        "policy": label or "Policy", "versuche": len(results), "im_ziel": full,
        "urteil": "sicher" if full == len(results) else ("teilweise" if full else "nicht geschafft"),
        "elemente": per_el, "stuerze": len(falls),
        "max_neigung_grad": max((a.max_neigung_grad for a in results), default=0.0),
        "zeit_s": [a.zeit_s for a in results], "ende": [a.ende for a in results],
        "reibung": [a.reibung for a in results], "bahnen": [a.bahn for a in results],
        "sturzstellen": falls, "hinweise": hints, "rechenzeit_s": round(time.perf_counter() - t0, 1),
        "wiederholung": results[0].replay if results else None,
    }
