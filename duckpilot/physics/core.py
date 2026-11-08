"""Echte Physik am PC: Pollens Microduck in MuJoCo, gesteuert von Pollens ONNX-Policies.

Nachgebaut nach `microduck_rl/scripts/infer_policy.py` (Pollen Robotics), dem Werkzeug, mit dem
Pollen Policies vor dem Aufspielen auf dem Prozessor ausprobiert:

* MuJoCo mit 200 Hz (dt 5 ms), Policy mit 50 Hz (4 Teilschritte).
* Beobachtung (61 Werte): Drehrate (3) · Schwerkraft im Rumpf (3) · Gelenkwinkel relativ zur
  Grundstellung (14) · Gelenkgeschwindigkeiten (14) · letzte Aktion (14) · Befehl (13 =
  Fahren 3 · Kopf 4 · Körper 6).
* Aktion (14): Zielwinkel = Grundstellung + Aktion × Skalierung.
* Feed-forward- und LSTM-Policies (h_in/c_in → h_out/c_out), wie robotd.

Die Motoren sind MuJoCos Positionsantriebe aus Pollens Modell („--no-bam“). Ist Rhobans
Motormodell `bam` installiert, nimmt duckpilot das – damit wurden die Policies trainiert.

Dazu kommt die Wohnung des einfachen Simulators als feste Körper: Wände, Möbel, Boden.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .params import HEAD_LOWPASS, LEGS_LOWPASS, ROBOT_ACTION_SCALE  # noqa: F401  (ROBOT_ACTION_SCALE: auch von hier)

log = logging.getLogger(__name__)

MODEL_XML = Path(__file__).with_name("microduck.xml")     # private Fassung: fertig im Paket (sonst fehlt die Datei)


def model_xml() -> Path:
    """Pollens Robotermodell für die Physik: im Datenordner geladen (duckpilot.modell), sonst aus dem Paket."""
    from ..modell import store

    path = store().physics_path()
    if path is None:
        raise FileNotFoundError("Pollens Robotermodell ist noch nicht geladen (Einstellungen → Über)")
    return path

DT = 0.005
DECIMATION = 4
CONTROL_DT = DT * DECIMATION
OBS_LEN = 61
ACT_LEN = 14
START_Z = 0.125

ACTUATORS = (
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
)
HEAD_IDX = np.array([ACTUATORS.index(n) for n in ("neck_pitch", "head_pitch", "head_yaw", "head_roll")])
# Wie robotd: Gelenkziele werden geglättet (Kopf 0,5, Beine 0,7) – ohne das zappeln Rolle und Stürze.
LOWPASS = np.full(14, LEGS_LOWPASS, np.float32)
LOWPASS[HEAD_IDX] = HEAD_LOWPASS
# Grundstellung STAND2 (wie HOME_FRAME in microduck_constants.py)
DEFAULT_POSE = np.array([
    0.0, -0.0873, -0.4579, -0.0049, 0.4530,
    0.3491, 0.3491, 0.0, 0.0,
    0.0, 0.0873, 0.4579, 0.0049, -0.4530,
], dtype=np.float32)
# Trainingsgrenzen der Befehle
HEAD_CAP = np.array([1.1, 1.1, 1.4, 0.31], dtype=np.float32)
BODY_MAX_XYZ = np.array([0.02, 0.02, 0.03], dtype=np.float32)
BODY_MAX_ANGLE = math.radians(30)
TWIST_MAX = np.array([0.3, 0.2, 1.0], dtype=np.float32)   # Drehen: trainiert und am Gamepad ±1,0 rad/s

# BAM (Rhoban, better-actuator-models) – so wie in infer_policy.py
BAM_KP_FW = 200.0
# Motorstärke als Anteil der vollen (wie robotd: gain_limp 50 / gain_pose 160 bei kp 200)
POWER_OFF_GAIN = 0.05      # stromlos in Ruhe: sackt zusammen
LIMP_FALL_GAIN = 0.25      # nach einem Sturz: weich, aber nicht kraftlos – sie liegt, ohne sich zu verkrampfen
POSE_GAIN = 0.8            # Aufrichten: weiche Rampe in die Grundstellung
POSE_S = 0.6               # Dauer der Rampe (robotd: posing_duration_ms 600)
BAM_VIN = 7.4
BAM_VIN_DROP_GAIN = 0.1
BAM_VIN_MIN = 6.0
BAM_STIFF_SOLREF_FRICTION = (-5.0e4, -2.0e2)
BAM_STIFF_SOLIMP_FRICTION = (0.99, 0.9999, 0.001, 0.5, 2.0)


class PolicyError(RuntimeError):
    pass


class Policy:
    """Eine ONNX-Policy (feed-forward oder LSTM mit explizitem Zustand)."""

    def __init__(self, path: str | Path, name: str = "", action_scale: float = 1.0) -> None:
        import onnxruntime as ort

        self.path = Path(path)
        self.name = name or self.path.stem
        self.action_scale = float(action_scale or 1.0)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(self.path), sess_options=opts, providers=["CPUExecutionProvider"])
        ins = {i.name: i for i in self.session.get_inputs()}
        outs = [o.name for o in self.session.get_outputs()]
        self.recurrent = "h_in" in ins and "c_in" in ins
        obs = ins.get("obs") or next(iter(ins.values()))
        self.obs_name = obs.name
        width = obs.shape[-1] if obs.shape else None
        if isinstance(width, int) and width != OBS_LEN:
            raise PolicyError(f"{self.name}: erwartet {width} Beobachtungswerte, die Microduck liefert {OBS_LEN}")
        if self.recurrent:
            self.action_name = "actions" if "actions" in outs else outs[0]
            shape = [d if isinstance(d, int) else 1 for d in ins["h_in"].shape]
            self.h = np.zeros(shape, dtype=np.float32)
            self.c = np.zeros(shape, dtype=np.float32)
        else:
            extra = [n for n in ins if n != self.obs_name]
            if extra:
                raise PolicyError(f"{self.name}: unbekannte Eingänge {extra}")
            self.action_name = outs[0]
        test = self.act(np.zeros(OBS_LEN, dtype=np.float32))
        if test.shape != (ACT_LEN,):
            raise PolicyError(f"{self.name}: liefert {test.shape[0]} Aktionen statt {ACT_LEN}")
        self.reset()

    def reset(self) -> None:
        if self.recurrent:
            self.h[:] = 0
            self.c[:] = 0

    def act(self, obs: np.ndarray) -> np.ndarray:
        feed: dict[str, Any] = {self.obs_name: obs.reshape(1, -1).astype(np.float32)}
        if self.recurrent:
            feed["h_in"], feed["c_in"] = self.h, self.c
            outs = self.session.run(None, feed)
            names = [o.name for o in self.session.get_outputs()]
            res = dict(zip(names, outs))
            action = np.asarray(res[self.action_name], dtype=np.float32).reshape(-1)
            if np.all(np.isfinite(action)):
                self.h = np.asarray(res.get("h_out", self.h), dtype=np.float32)
                self.c = np.asarray(res.get("c_out", self.c), dtype=np.float32)
            return action
        action = self.session.run([self.action_name], feed)[0]
        return np.asarray(action, dtype=np.float32).reshape(-1)


def quat_rotate_inverse(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    w, xyz = q[0], q[1:4]
    t = np.cross(xyz, v) * 2
    return v - w * t + np.cross(xyz, t)


def yaw_quat(yaw: float) -> list[float]:
    return [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]


@dataclass
class Command:
    twist: np.ndarray = field(default_factory=lambda: np.zeros(3, np.float32))
    head: np.ndarray = field(default_factory=lambda: np.zeros(4, np.float32))
    body: np.ndarray = field(default_factory=lambda: np.zeros(6, np.float32))   # x y z roll pitch yaw


class PhysicsCore:
    """Robotermodell + Wohnung in MuJoCo und die Policy-Schleife – ohne asyncio, ohne Oberfläche."""

    def __init__(self, world: Any | None = None, use_bam: bool | None = None, course: Any | None = None,
                 objects: bool = False) -> None:
        spec = mujoco.MjSpec.from_file(str(model_xml()))
        self.world_geoms: dict[int, str] = {}
        self._add_world(spec, world)
        if objects:                                  # Kollisionsmodus: Ball und Würfel als freie Körper
            from .kollision import add_objects

            add_objects(spec)
        if course is not None:
            from .course import add_to_spec

            add_to_spec(spec, course)
        self.bam = None
        if use_bam is not False:
            self.bam = self._bam_edit(spec) if use_bam or _has_bam() else None
        self.model = spec.compile()
        self.model.opt.timestep = DT
        self.data = mujoco.MjData(self.model)
        if self.bam is not None:
            self._bam_attach()
        m = self.model
        self.qpos_idx = [int(m.jnt_qposadr[m.actuator_trnid[i, 0]]) for i in range(m.nu)]
        self.qvel_idx = [int(m.jnt_dofadr[m.actuator_trnid[i, 0]]) for i in range(m.nu)]
        fj = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "trunk_base_freejoint")
        self.root_q = int(m.jnt_qposadr[fj])
        self.root_v = int(m.jnt_dofadr[fj])
        self.trunk_id = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
        gyro = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SENSOR, "imu_ang_vel")
        self.gyro_adr = int(m.sensor_adr[gyro])
        self.kp0 = m.actuator_gainprm[:, 0].copy()
        self.bias0 = m.actuator_biasprm[:, 1].copy()
        # nur die Ente (alles unter dem Rumpf) – nicht Ball und Würfel, die eigene freie Körper sind
        self.robot_geoms = {i for i in range(m.ngeom) if int(m.body_rootid[m.geom_bodyid[i]]) == self.trunk_id}
        self.pre_step: Any = None            # Kollisionsmodus: Stoß und gehaltene Objekte je Teilschritt
        self.last_action = np.zeros(ACT_LEN, np.float32)
        self.lowpass = True                  # Zielglättung wie am Roboter (abschaltbar für Vergleiche)
        self.prev_targets: np.ndarray | None = None
        self.policy: Policy | None = None
        self.limp = False
        self.limp_gain = POWER_OFF_GAIN
        self.gain = 1.0                      # wirksame Motorstärke (Anteil der vollen)
        self.gain_ratio = 1.0                # während eines Skills (robotd: standing_gain_ratio 0,8)
        self._pose: dict[str, Any] | None = None   # laufende Rampe in die Grundstellung (Aufstehen)
        # Kopf-Stabilisator: Kopf und Hals direkt stellen (wie robotd es am Roboter erlaubt) statt über den
        # Kopf-Befehl der Geh-Policy – die folgt ihm zu träge, der Ausgleich käme zu spät
        self.head_override: np.ndarray | None = None
        self.steps = 0
        self.reset()

    # ── Aufbau ────────────────────────────────────────────────────────────
    def _add_world(self, spec, world) -> None:
        body = spec.worldbody
        floor = body.add_geom(name="boden", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[0, 0, 0.05])
        floor.friction = [1.0, 0.005, 0.0001]
        if world is None:
            return
        hx, hy = world.width / 2, world.depth / 2
        t = 0.05
        for name, pos, size in (
            ("wand_n", [hx + t, 0, 0.25], [t, hy + 2 * t, 0.25]), ("wand_s", [-hx - t, 0, 0.25], [t, hy + 2 * t, 0.25]),
            ("wand_o", [0, -hy - t, 0.25], [hx + 2 * t, t, 0.25]), ("wand_w", [0, hy + t, 0.25], [hx + 2 * t, t, 0.25]),
        ):
            body.add_geom(name=name, type=mujoco.mjtGeom.mjGEOM_BOX, pos=pos, size=size)
        for b in world.boxes:
            body.add_geom(name=f"m:{b.name}", type=mujoco.mjtGeom.mjGEOM_BOX, pos=[b.x, b.y, b.h / 2],
                          size=[b.sx / 2, b.sy / 2, b.h / 2])
        for c in world.cylinders:
            body.add_geom(name=f"m:{c.name}", type=mujoco.mjtGeom.mjGEOM_CYLINDER, pos=[c.x, c.y, c.h / 2],
                          size=[c.r, c.h / 2, 0])

    def _bam_edit(self, spec):
        """Positionsantriebe → Drehmomentmotoren mit Rhobans BAM-Modell (wie bam.mjlab.BamActuator)."""
        try:
            from bam.model import load_model
        except Exception as exc:          # nicht installiert oder kaputt: Positionsantriebe
            log.info("BAM nicht verfügbar (%s) – nehme MuJoCo-Positionsantriebe", exc)
            return None
        bam_model = load_model(motor_name="xl330", model="m6")
        bam_model.actuator.kp = BAM_KP_FW
        bam_model.actuator.vin = BAM_VIN
        bam_model.actuator.max_current = None
        force = bam_model.actuator.vin * bam_model.kt.value / bam_model.R.value
        names = []
        for act in spec.actuators:
            tgt = act.target.name if hasattr(act.target, "name") else str(act.target)
            act.set_to_motor()
            act.forcelimited = True
            act.forcerange = (-force, force)
            act.ctrllimited = False
            act.gear = [1.0, 0, 0, 0, 0, 0]
            names.append(act.name)
            for joint in spec.joints:
                if joint.name == tgt:
                    joint.damping = np.zeros((3, 1))
                    joint.frictionloss = 0.0
                    joint.solref_friction = BAM_STIFF_SOLREF_FRICTION
                    joint.solimp_friction = BAM_STIFF_SOLIMP_FRICTION
                    break
        self._bam_names = names
        return bam_model

    def _bam_attach(self) -> None:
        from bam.mujoco import MujocoController

        self.bam_ctrl = MujocoController(self.bam, self._bam_names, self.model, self.data,
                                         vin_drop_gain=BAM_VIN_DROP_GAIN, vin_min=BAM_VIN_MIN)

    @property
    def motor_model(self) -> str:
        return "BAM (Rhoban, wie im Training)" if self.bam is not None else "MuJoCo-Positionsantriebe"

    # ── Zustand setzen ────────────────────────────────────────────────────
    def reset(self, x: float = 0.0, y: float = 0.0, yaw: float = 0.0) -> None:
        d = self.data
        mujoco.mj_resetData(self.model, d)
        d.qpos[self.root_q:self.root_q + 3] = [x, y, START_Z]
        d.qpos[self.root_q + 3:self.root_q + 7] = yaw_quat(yaw)
        for i, q in enumerate(self.qpos_idx):
            d.qpos[q] = DEFAULT_POSE[i]
        self.last_action[:] = 0
        self.prev_targets = None
        self._pose = None
        self._set_targets(DEFAULT_POSE)
        if self.bam is not None:
            self.bam_ctrl.reset(d.qpos)
            self._set_targets(DEFAULT_POSE)
        mujoco.mj_forward(self.model, d)
        if self.policy:
            self.policy.reset()

    def set_policy(self, policy: Policy | None) -> None:
        if policy is not self.policy:
            self.policy = policy
            if policy is not None:
                policy.reset()           # neues Netz: Gedächtnis von vorn (wie robotd)

    def set_limp(self, on: bool, gain: float = POWER_OFF_GAIN) -> None:
        """Motoren schwach oder wieder normal. `gain`: Anteil der vollen Stärke, solange schlaff –
        stromlos 0,05 (sackt zusammen), nach einem Sturz 0,25 (wie robotd)."""
        self.limp = on
        if on:
            self.limp_gain = float(gain)
            self._pose = None                # schlaff schlägt das Aufrichten (Not-Aus, hochgehoben, Sturz)
        self._apply_gains()

    def set_gain_ratio(self, ratio: float) -> None:
        """Motorstärke während eines Skills wie robotd: Tricks mit Befehl 0 laufen „standing tuned“ (0,8), sonst 1,0."""
        ratio = float(ratio)
        if abs(ratio - self.gain_ratio) > 1e-6:
            self.gain_ratio = ratio
            self._apply_gains()

    def _apply_gains(self) -> None:
        gain = self.limp_gain if self.limp else (POSE_GAIN if self._pose is not None else self.gain_ratio)
        self.gain = gain
        if self.bam is not None:
            self.bam.actuator.kp = BAM_KP_FW * gain
            return
        self.model.actuator_gainprm[:, 0] = self.kp0 * gain
        self.model.actuator_biasprm[:, 1] = self.bias0 * gain

    @property
    def posing(self) -> bool:
        return self._pose is not None

    def start_pose(self, seconds: float = POSE_S, ziel: np.ndarray | None = None, halten: float = 0.0) -> None:
        """Aufrichten wie robotd (Posing): von den jetzigen Winkeln gerade in die Grundstellung, Stärke 0,8,
        keine Policy. Danach Policy-Gedächtnis, letzte Aktion und Glättung von vorn.

        Seit 0.36 auch für Posen im Tanz: `ziel` (14 Gelenkwinkel) anfahren, `halten` Sekunden stehen bleiben, dann
        in derselben Zeit zurück in die Grundstellung – erst dann übernimmt die Policy wieder."""
        self.limp = False
        steps = max(1, round(seconds / CONTROL_DT))
        self._pose = {"von": self.data.qpos[self.qpos_idx].astype(np.float32).copy(), "n": steps, "i": 0,
                      "ziel": None if ziel is None else np.asarray(ziel, np.float32).copy(),
                      "halten": max(0, round(halten / CONTROL_DT)), "s": seconds}
        self.prev_targets = None
        self._apply_gains()

    def _pose_step(self) -> None:
        p = self._pose
        p["i"] += 1
        ziel = p.get("ziel")
        if ziel is not None:
            if p["i"] < p["n"]:
                self._set_targets((p["von"] + (ziel - p["von"]) * (p["i"] / p["n"])).astype(np.float32))
                return
            if p["i"] < p["n"] + p["halten"]:
                self._set_targets(ziel.copy())
                return
            # gehalten – jetzt zurück in die Grundstellung (danach übernimmt die Policy)
            self._pose = {"von": ziel.copy(), "n": p["n"], "i": 0, "ziel": None, "halten": 0, "s": p["s"]}
            return
        if p["i"] >= p["n"]:
            self._set_targets(DEFAULT_POSE.copy())
            self._pose = None
            if self.policy is not None:
                self.policy.reset()
            self.last_action = np.zeros(ACT_LEN, np.float32)
            self.prev_targets = None
            self._apply_gains()
            return
        a = p["i"] / p["n"]
        self._set_targets((p["von"] + (DEFAULT_POSE - p["von"]) * a).astype(np.float32))

    def hold_current(self) -> None:
        """Ziele = jetzige Winkel: liegt sie schlaff, gibt es keinen Schein-Nachlauf und beim Aufrichten keinen Ruck."""
        self._set_targets(self.data.qpos[self.qpos_idx].astype(np.float32))
        self.prev_targets = None

    def _set_targets(self, q: np.ndarray) -> None:
        if self.bam is not None:
            self.bam_ctrl.q_target[:] = q
        else:
            self.data.ctrl[:] = q

    # ── Beobachtung ──────────────────────────────────────────────────────
    def quat(self) -> np.ndarray:
        return self.data.xquat[self.trunk_id].astype(np.float32)

    def observation(self, cmd: Command) -> np.ndarray:
        d = self.data
        gyro = d.sensordata[self.gyro_adr:self.gyro_adr + 3].astype(np.float32)
        grav = quat_rotate_inverse(self.quat(), np.array([0, 0, -1], np.float32))
        q = d.qpos[self.qpos_idx].astype(np.float32) - DEFAULT_POSE
        dq = d.qvel[self.qvel_idx].astype(np.float32)
        command = np.concatenate([cmd.twist, cmd.head, cmd.body]).astype(np.float32)
        return np.concatenate([gyro, grav, q, dq, self.last_action, command]).astype(np.float32)

    # ── ein Regelschritt (50 Hz) ─────────────────────────────────────────
    def control_step(self, cmd: Command) -> None:
        if self._pose is not None and not self.limp:
            self._pose_step()
        elif self.policy is not None and not self.limp:
            action = self.policy.act(self.observation(cmd))
            if not np.all(np.isfinite(action)):
                action = np.zeros(ACT_LEN, np.float32)
            self.last_action = action.astype(np.float32)
            q = DEFAULT_POSE + action * self.policy.action_scale
            if self.head_override is not None:
                q = q.copy()
                q[HEAD_IDX] = DEFAULT_POSE[HEAD_IDX] + self.head_override
            if self.lowpass and getattr(self, "prev_targets", None) is not None:
                q = LOWPASS * q + (1.0 - LOWPASS) * self.prev_targets
            self.prev_targets = np.asarray(q, np.float32).copy()
            self._set_targets(q)
        for _ in range(DECIMATION):
            if self.pre_step is not None:
                self.pre_step()
            if self.bam is not None:
                self.bam_ctrl.update()
            mujoco.mj_step(self.model, self.data)
        self.steps += 1

    # ── Auslesen ─────────────────────────────────────────────────────────
    def trunk(self) -> dict[str, float]:
        d = self.data
        x, y, z = (float(v) for v in d.qpos[self.root_q:self.root_q + 3])
        w, qx, qy, qz = (float(v) for v in d.qpos[self.root_q + 3:self.root_q + 7])
        yaw = math.atan2(2 * (w * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))
        roll = math.atan2(2 * (w * qx + qy * qz), 1 - 2 * (qx * qx + qy * qy))
        pitch = math.asin(max(-1.0, min(1.0, 2 * (w * qy - qz * qx))))
        up = 1 - 2 * (qx * qx + qy * qy)          # z-Achse des Rumpfs, nach oben = 1
        v = quat_rotate_inverse(np.array([w, qx, qy, qz], np.float32),
                                d.qvel[self.root_v:self.root_v + 3].astype(np.float32))
        return {"x": x, "y": y, "z": z, "yaw": yaw, "roll": roll, "pitch": pitch, "up": up,
                "vx": float(v[0]), "vy": float(v[1]), "vyaw": float(d.qvel[self.root_v + 5])}

    def joints(self) -> dict[str, float]:
        q = self.data.qpos[self.qpos_idx]
        return {n: float(q[i]) for i, n in enumerate(ACTUATORS)}

    def joint_detail(self) -> dict[str, dict[str, float]]:
        """Je Antrieb: Ist- und Sollwinkel, Moment und Anteil vom Höchstmoment (für den Gelenk-Check)."""
        d, m = self.data, self.model
        q = d.qpos[self.qpos_idx]
        tgt = self.bam_ctrl.q_target if self.bam is not None else d.ctrl
        out = {}
        for i, n in enumerate(ACTUATORS):
            hi = float(m.actuator_forcerange[i, 1]) if m.actuator_forcelimited[i] else 0.0
            f = float(d.actuator_force[i])
            out[n] = {"ist": float(q[i]), "soll": float(tgt[i]), "moment": f,
                      "last": abs(f) / hi if hi > 0 else None}
        return out

    def contacts_with_world(self) -> set[str]:
        """Möbel und Wände, die gerade ein Teil der Ente berührt."""
        d, m = self.data, self.model
        out = set()
        for i in range(d.ncon):
            c = d.contact[i]
            a, b = int(c.geom1), int(c.geom2)
            for mine, other in ((a, b), (b, a)):
                if mine in self.robot_geoms and other not in self.robot_geoms:
                    name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, other) or ""
                    if name.startswith("m:"):
                        out.add(name[2:])
                    elif name.startswith("p:"):
                        out.add("Parcours")
                    elif name.startswith("wand"):
                        out.add("Wand")
                    elif name.startswith("o:"):
                        from .kollision import OBJEKTE

                        out.add(OBJEKTE.get(name[2:], {}).get("name", name[2:]))
        return out

    def fremdkraft(self) -> tuple[float, str | None]:
        """Wie fest etwas von außen gegen die Ente drückt (Summe der Normalkräfte, N) und was am festesten –
        Dinge, Hand, Möbel, Wände. Boden und Parcours zählen nicht (darauf läuft sie). Fürs Vibrieren am Handy."""
        d, m = self.data, self.model
        f6 = np.zeros(6)
        total, best, wer = 0.0, 0.0, None
        for i in range(d.ncon):
            c = d.contact[i]
            a, b = int(c.geom1), int(c.geom2)
            if (a in self.robot_geoms) == (b in self.robot_geoms):
                continue
            other = b if a in self.robot_geoms else a
            if int(m.geom_type[other]) == int(mujoco.mjtGeom.mjGEOM_PLANE):
                continue
            name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, other) or ""
            if name.startswith(("p:", "z:")):
                continue
            mujoco.mj_contactForce(m, d, i, f6)
            f = abs(float(f6[0]))
            total += f
            if f > best:
                best, wer = f, name
        return total, wer


def _has_bam() -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec("bam") is not None and importlib.util.find_spec("bam.mujoco") is not None
    except (ImportError, ValueError):
        return False
