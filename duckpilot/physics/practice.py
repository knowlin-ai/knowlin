"""Üben in der Physik: Claude entwirft eine Bewegung, MuJoCo prüft sie, Claude verbessert sie.

Läuft in einer eigenen, unsichtbaren MuJoCo-Welt (leerer Boden), schneller als Echtzeit –
die Ente auf dem Bildschirm (oder der echte Roboter) bewegt sich dabei nicht. Gefahren wird
die Choreografie so, wie sie später läuft: Kopf, Körperhaltung und Fahrbefehle gehen als Befehl
an Pollens VelStand-Policy, die das Gleichgewicht hält. Ergebnis sind Messwerte, aus denen
Claude lernt: ob sie umfällt, wie stark sie kippt, ob der Kopf dorthin kommt, wohin er soll.

Funktioniert ohne Grafikkarte – das ist der Trainingsweg, der auch mit einer AMD-Karte und
ganz ohne CUDA geht.
"""

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np

from ..api import Head, Pose, Twist
from .core import (
    BODY_MAX_ANGLE,
    BODY_MAX_XYZ,
    CONTROL_DT,
    HEAD_CAP,
    ROBOT_ACTION_SCALE,
    TWIST_MAX,
    Command,
    PhysicsCore,
    Policy,
)
from .policies import PolicyStore
from .twist import shape_twist

MAX_SECONDS = 30.0
POSE_TAU = 0.2            # wie die sichtbare Ente: Körperhaltung folgt mit dieser Trägheit (sim._approach)
SEEN_CM = 0.8             # so viel muss sich der Rumpf heben/senken, damit man das „Hüpfen“ sieht


def _approach(current: float, target: float, dt: float, tau: float = POSE_TAU) -> float:
    return current + (target - current) * min(1.0, dt / tau)


def _sample(ch, t: float) -> tuple[Head, Pose, Twist]:
    loop = min(ch.loops - 1, int(t // ch.length))
    local = t - loop * ch.length
    head = ch._interp("head", local) or Head()
    pose = ch._interp("pose", local) or Pose()
    twist = Twist()
    for kf in ch.kfs:
        if kf.twist is not None and kf.t <= local:
            twist = kf.twist
    return head, pose, twist


def rehearse(store: PolicyStore, keyframes: list[dict[str, Any]], loops: int = 1, settle: float = 1.0,
             core: PhysicsCore | None = None) -> dict[str, Any]:
    """Die Choreografie einmal in der Physik durchspielen und bewerten."""
    from ..motion.behaviors import Choreography

    ch = Choreography.from_spec(list(keyframes), loops)
    total = ch.length * ch.loops
    if total > MAX_SECONDS:
        raise ValueError(f"höchstens {MAX_SECONDS:.0f} Sekunden am Stück üben")
    roles = store.roles()
    if "walk" not in roles:
        raise ValueError("Pollens Geh-Policy fehlt – erst unter Einstellungen → Körper laden.")
    core = core or PhysicsCore(None)
    core.reset()
    core.set_policy(Policy(roles["walk"]["pfad"], "walk", ROBOT_ACTION_SCALE))
    # erst kurz stehen, damit die Policy sicher steht
    for _ in range(int(0.6 / CONTROL_DT)):
        core.control_step(Command())
    start = core.trunk()
    t0 = time.perf_counter()
    tilt_max = 0.0
    z_min = start["z"]
    fell_at = None
    head_err: list[float] = []
    smooth = Pose()
    planned_z: list[float] = []
    moved_z: list[float] = []
    yaw_total = 0.0
    last_yaw = start["yaw"]
    steps = int((total + settle) / CONTROL_DT)
    for i in range(steps):
        t = i * CONTROL_DT
        if t < total:
            head, pose, twist = _sample(ch, t)
        else:
            head, pose, twist = Head(), Pose(), Twist()
        cmd = Command()
        # genau wie die sichtbare Physik-Ente: Fahrbefehle über die Totzone gehoben, Haltung mit Trägheit
        cmd.twist[:] = np.clip(shape_twist(twist.vx, twist.vy, twist.vyaw), -TWIST_MAX, TWIST_MAX)
        cmd.head[:] = np.clip([head.neck_pitch, head.head_pitch, head.head_yaw, head.head_roll], -HEAD_CAP, HEAD_CAP)
        pose = pose.clamped()
        smooth = Pose(_approach(smooth.z, pose.z, CONTROL_DT), _approach(smooth.roll, pose.roll, CONTROL_DT),
                      _approach(smooth.pitch, pose.pitch, CONTROL_DT))
        cmd.body[2] = float(np.clip(smooth.z, -BODY_MAX_XYZ[2], BODY_MAX_XYZ[2]))
        cmd.body[3] = float(np.clip(smooth.roll, -BODY_MAX_ANGLE, BODY_MAX_ANGLE))
        cmd.body[4] = float(np.clip(smooth.pitch, -BODY_MAX_ANGLE, BODY_MAX_ANGLE))
        core.control_step(cmd)
        tr = core.trunk()
        if t < total:
            planned_z.append(pose.z)
            moved_z.append(tr["z"])
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, tr["up"]))))
        tilt_max = max(tilt_max, tilt)
        z_min = min(z_min, tr["z"])
        d = (tr["yaw"] - last_yaw + math.pi) % (2 * math.pi) - math.pi
        yaw_total += d
        last_yaw = tr["yaw"]
        if fell_at is None and tr["up"] < 0.45:
            fell_at = t
        if t < total and i % 5 == 0:
            j = core.joints()
            actual = np.array([j["neck_pitch"] - 0.3491, j["head_pitch"] - 0.3491, j["head_yaw"], j["head_roll"]])
            head_err.append(float(np.max(np.abs(actual - cmd.head))))
    end = core.trunk()
    dist = math.hypot(end["x"] - start["x"], end["y"] - start["y"])
    err = math.degrees(float(np.mean(head_err))) if head_err else 0.0
    if fell_at is not None:
        verdict = "fällt um"
    elif tilt_max > 25:
        verdict = "wackelig"
    else:
        verdict = "sicher"
    hints = []
    if fell_at is not None:
        hints.append(f"Bei {fell_at:.1f} s umgefallen – Bewegung dort langsamer oder kleiner machen.")
    elif tilt_max > 25:
        hints.append("Kippt stark – Körperneigung oder Tempo verringern.")
    if err > 12:
        hints.append("Der Kopf kommt nicht ganz hinterher – Keyframes weiter auseinander legen.")
    plan_cm = (max(planned_z) - min(planned_z)) * 100 if planned_z else 0.0
    seen_cm = (max(moved_z) - min(moved_z)) * 100 if moved_z else 0.0
    faint = plan_cm >= 1.5 and seen_cm < max(SEEN_CM, 0.4 * plan_cm)
    if faint and fell_at is None:
        hints.append(f"Das Auf und Ab kommt kaum an (geplant {plan_cm:.1f} cm, der Rumpf bewegt sich nur "
                     f"{seen_cm:.1f} cm) – so sieht man es nicht. Wechsel langsamer (≥ 0,4 s) und deutlicher machen.")
    if not hints:
        hints.append("Läuft sauber.")
    return {
        "urteil": verdict,
        "umgefallen_bei_s": round(fell_at, 2) if fell_at is not None else None,
        "max_neigung_grad": round(tilt_max, 1),
        "tiefster_rumpf_cm": round(z_min * 100, 1),
        "strecke_m": round(dist, 2),
        "drehung_grad": round(math.degrees(yaw_total)),
        "kopf_abweichung_grad": round(err, 1),
        "rumpf_auf_ab_cm": {"geplant": round(plan_cm, 1), "sichtbar": round(seen_cm, 1)},
        "sichtbar": "kaum" if faint else "ja",
        "dauer_s": round(total, 2),
        "rechenzeit_s": round(time.perf_counter() - t0, 2),
        "motor": core.motor_model,
        "hinweise": hints,
    }


# ── Fremde Tricks prüfen, bevor sie auf die echte Ente dürfen ────────────────
TRICK_SETTLE_S = 2.5        # nach dem Trick: so lange darf Pollens Geh-Policy sie wieder fangen
UPRIGHT = 0.85              # Rumpf-Hochachse: darüber steht sie
DOWN = 0.45                 # darunter liegt sie / ist kopfüber


def rehearse_trick(store: PolicyStore, policy_path: str, seconds: float = 3.0, idle: list[float] | None = None,
                   action_scale: float = ROBOT_ACTION_SCALE, core: PhysicsCore | None = None) -> dict[str, Any]:
    """Einen Trick (One-Shot-Policy) unsichtbar in der Physik durchspielen: steht sie danach wieder?

    Urteil: „sicher“ (bleibt aufrecht), „akrobatisch“ (geht kopfüber oder zu Boden, steht aber wieder),
    „bleibt liegen“ (steht nach dem Trick nicht mehr auf – am echten Roboter nur mit Hilfe)."""
    seconds = max(0.5, min(MAX_SECONDS, float(seconds or 3.0)))
    roles = store.roles()
    if "walk" not in roles:
        raise ValueError("Pollens Geh-Policy fehlt – erst unter Einstellungen → Körper laden.")
    core = core or PhysicsCore(None)
    core.reset()
    walk = Policy(roles["walk"]["pfad"], "walk", ROBOT_ACTION_SCALE)
    trick = Policy(policy_path, "trick", float(action_scale or ROBOT_ACTION_SCALE))
    core.set_policy(walk)
    for _ in range(int(0.6 / CONTROL_DT)):
        core.control_step(Command())
    start = core.trunk()
    t0 = time.perf_counter()
    core.set_policy(trick)
    cmd = Command()
    if idle:
        cmd.twist[:] = np.clip(np.asarray(list(idle)[:3], np.float32), -TWIST_MAX, TWIST_MAX)
    lowest_up, z_min, inverted_at = 1.0, start["z"], None
    for i in range(int(seconds / CONTROL_DT)):
        core.control_step(cmd)
        tr = core.trunk()
        lowest_up = min(lowest_up, tr["up"])
        z_min = min(z_min, tr["z"])
        if inverted_at is None and tr["up"] < DOWN:
            inverted_at = i * CONTROL_DT
    core.set_policy(walk)
    upright_after = None
    for i in range(int(TRICK_SETTLE_S / CONTROL_DT)):
        core.control_step(Command())
        tr = core.trunk()
        if upright_after is None and tr["up"] > UPRIGHT and tr["z"] > 0.09:
            upright_after = i * CONTROL_DT
    end = core.trunk()
    stands = end["up"] > UPRIGHT and end["z"] > 0.09
    if stands and inverted_at is None:
        verdict, hint = "sicher", "Bleibt die ganze Zeit aufrecht."
    elif stands:
        verdict, hint = "akrobatisch", (f"Geht nach {inverted_at:.1f} s kopfüber oder zu Boden und steht danach wieder – "
                                        "am echten Roboter mit Platz drumherum und weichem Boden.")
    else:
        verdict, hint = "bleibt liegen", ("Steht nach dem Trick nicht wieder auf – am echten Roboter nur, wenn du "
                                          "daneben stehst und ihr hilfst.")
    return {
        "urteil": verdict, "hinweis": hint,
        "kopfueber_bei_s": round(inverted_at, 2) if inverted_at is not None else None,
        "steht_danach": bool(stands),
        "tiefste_neigung": round(math.degrees(math.acos(max(-1.0, min(1.0, lowest_up)))), 1),
        "tiefster_rumpf_cm": round(z_min * 100, 1),
        "strecke_m": round(math.hypot(end["x"] - start["x"], end["y"] - start["y"]), 2),
        "dauer_s": round(seconds, 2),
        "rechenzeit_s": round(time.perf_counter() - t0, 2),
        "motor": core.motor_model,
    }
