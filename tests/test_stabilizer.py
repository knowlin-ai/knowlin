"""Kopf-Stabilisator: Vorzeichen gegen Pollens MJCF, Taubenruck beim Drehen, Einbindung in Simulator und Roboter."""
from __future__ import annotations

import asyncio
import math

import numpy as np
import pytest

from duckpilot.api import Head
from duckpilot.motion.stabilizer import YAW_HOLD, HeadStabilizer, euler_from_quat


def _settle(st: HeadStabilizer, roll=0.0, pitch=0.0, yaw=0.0, secs=5.0):
    for _ in range(int(secs / 0.02)):
        st.update(roll, pitch, yaw, 0.02)


def test_quick_tilt_is_cancelled_and_slow_pose_is_kept():
    st = HeadStabilizer()
    st.enabled = True
    _settle(st)
    o = st.update(0.1, 0.05, 0.0, 0.02, gyro=(0, 0, 0))   # Ruck im Rumpf (ohne Vorhalt geprüft)
    assert o.head_roll == pytest.approx(0.1, abs=0.01) and o.head_pitch == pytest.approx(-0.05, abs=0.01)
    _settle(st, 0.1, 0.05, secs=8)                 # bleibt die Haltung, gilt sie als gewollt
    assert abs(st.offset.head_roll) < 0.01 and abs(st.offset.head_pitch) < 0.01
    st.enabled = False
    assert st.update(0.3, 0.3, 0.3, 0.02) == Head()


def test_turning_holds_the_gaze_then_jumps_ahead_like_a_pigeon():
    st = HeadStabilizer()
    st.enabled = True
    _settle(st)
    yaw, offsets = 0.0, []
    for _ in range(150):                           # 1 rad/s drehen, 3 s lang
        yaw += 0.02
        offsets.append(st.update(0.0, 0.0, yaw, 0.02).head_yaw)
    assert offsets[5] < -0.05                      # Kopf bleibt zurück (Blick hält)
    assert min(offsets) >= -YAW_HOLD - 0.05        # nie weiter als die Haltegrenze
    jumps = sum(1 for a, b in zip(offsets, offsets[1:]) if b - a > 0.05)
    assert jumps >= 3                              # mehrere schnelle Rucke nach vorn
    assert max(offsets) > 0.05                     # beim Ruck schaut sie in Drehrichtung voraus


def test_signs_match_pollens_model():
    mujoco = pytest.importorskip("mujoco")
    from duckpilot.physics import core as C

    m = mujoco.MjSpec.from_file(str(C.model_xml())).compile()
    d = mujoco.MjData(m)
    fj = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "trunk_base_freejoint")
    rq = m.jnt_qposadr[fj]
    adr = {n: m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n)] for n in C.ACTUATORS}
    cam = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "head_camera")

    def head_rot(roll, pitch, yaw, off: Head):
        for i, n in enumerate(C.ACTUATORS):
            d.qpos[adr[n]] = C.DEFAULT_POSE[i]
        for n, v in zip(("neck_pitch", "head_pitch", "head_yaw", "head_roll"), off.as_list()):
            d.qpos[adr[n]] += v
        q = np.zeros(4)
        mujoco.mju_euler2Quat(q, np.array([roll, pitch, yaw]), "xyz")
        d.qpos[rq:rq + 3] = [0, 0, 0.12]
        d.qpos[rq + 3:rq + 7] = q
        mujoco.mj_kinematics(m, d)
        return d.site_xmat[cam].reshape(3, 3).copy()

    r0 = head_rot(0, 0, 0, Head())
    for tilt in ((0.12, 0, 0), (0, 0.12, 0), (0, 0, 0.3), (0.08, -0.1, 0.2)):
        st = HeadStabilizer()
        st.enabled = True
        _settle(st)
        off = st.update(*tilt, 0.02, gyro=(0, 0, 0))
        angle = lambda r: math.degrees(math.acos(max(-1, min(1, (np.trace(r @ r0.T) - 1) / 2))))
        without, with_ = angle(head_rot(*tilt, Head())), angle(head_rot(*tilt, off))
        assert with_ < 0.25 * without, (tilt, without, with_)


def test_sim_and_robot_use_it():
    from duckpilot.backends.sim import SimBackend

    sim = SimBackend(realtime=False) if "realtime" in SimBackend.__init__.__code__.co_varnames else SimBackend()
    sim.set_stabilize(True)
    assert sim.state().kopf_stabil
    sim.powered = True
    sim.pose_target = sim.pose_target.__class__(0.0, 0.0, 0.0)
    sim.yaw = 0.0
    for _ in range(100):
        sim._step_actuators(0.02)
    sim.yaw = 0.3                                   # Rumpf dreht sich schnell weiter
    for _ in range(5):
        sim._step_actuators(0.02)
    assert sim.head_out.head_yaw < -0.1             # Kopf bleibt zurück

    from duckpilot.backends.robotd import RobotdBackend

    rb = RobotdBackend.__new__(RobotdBackend)
    from duckpilot.api import DuckBackend

    DuckBackend.__init__(rb)
    sent = []

    async def notify(method, params):
        sent.append(params)

    rb._notify = notify
    rb.head_signs = [1.0, 1.0, 1.0, 1.0]
    rb.set_stabilize(True)
    for _ in range(100):
        rb.stabilizer.update(0, 0, 0, 0.02)
    asyncio.run(rb.head(Head(0, 0.2, 0, 0)))
    q = [math.cos(0.05), math.sin(0.05), 0, 0]      # 0,1 rad gerollt
    rb.stabilizer.update(*euler_from_quat(*q), 0.02, gyro=(0, 0, 0))
    asyncio.run(rb.head(Head(0, 0.2, 0, 0)))
    assert sent[-1]["head_roll"] == pytest.approx(0.1, abs=0.02) and sent[-1]["head_pitch"] == pytest.approx(0.2, abs=0.02)


def test_click_and_look_messages(tmp_path, monkeypatch):
    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.motion.engine import head_towards
    from duckpilot.server.app import Runtime

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)

    async def go():
        rt = Runtime(load(memory_path=str(tmp_path / "m.json")))
        await rt.start()
        await rt.koerper_betreten()          # seit 0.38.4 startet Knowlin im Kopf – erst das Betreten weckt die Ente
        await asyncio.sleep(1.2)
        st = rt.backend.state()
        # Punkt links vor der Ente: Kopf dreht nach links und schaut nach unten
        ahead = (st.x + 0.6 * math.cos(st.yaw + 0.4), st.y + 0.6 * math.sin(st.yaw + 0.4), 0.0)
        head, bearing = head_towards(st, ahead)
        assert bearing == pytest.approx(0.4, abs=0.01) and head.head_yaw > 0.3 and head.head_pitch > 0.1
        await rt.handle_client_message({"type": "blick", "x": ahead[0], "y": ahead[1], "z": 0, "sekunden": 5})
        await asyncio.sleep(1.2)                     # der Kopf folgt wie am Roboter verzögert (≈ 0,25 s Zeitkonstante)
        assert rt.engine.gaze.point is not None and rt.backend.state().head.head_yaw > 0.2
        # Ziehen im Entenblick: feste Kopfstellung, beschnitten auf die Gelenkgrenzen
        await rt.handle_client_message({"type": "blick", "yaw": -9, "pitch": 0.2, "sekunden": 5})
        assert rt.engine.gaze.head.head_yaw == pytest.approx(-1.1) and rt.engine.gaze.point is None
        await rt.handle_client_message({"type": "blick"})
        assert rt.engine.gaze.head is None and rt.engine.gaze.point is None
        # Unsinn wird ignoriert, ohne die Verbindung zu stören
        await rt.handle_client_message({"type": "blick", "x": "nan", "y": None})
        # Doppelklick: hinlaufen
        target = (st.x + 0.5 * math.cos(st.yaw), st.y + 0.5 * math.sin(st.yaw))
        await rt.handle_client_message({"type": "hingehen", "x": target[0], "y": target[1]})
        assert rt.engine.describe()["ziel"] == [pytest.approx(target[0], abs=1e-3), pytest.approx(target[1], abs=1e-3)]
        await rt.engine.stop_all("Test")
        assert rt.engine.gaze.point is None
        await rt.stop()

    asyncio.run(go())


def test_gaze_recenters_and_point_gaze_disables_yaw_hold():
    st = HeadStabilizer()
    st.enabled = True
    _settle(st)
    for i in range(15):                              # kurze Drehung um 0,3 rad
        st.update(0, 0, 0.02 * (i + 1), 0.02)
    assert st.offset.head_yaw < -0.2
    _settle(st, yaw=0.3, secs=8)                     # Rumpf steht: Blick wandert zur Mitte zurück
    assert abs(st.offset.head_yaw) < 0.03
    st.yaw_hold = False
    assert st.update(0, 0, 0.9, 0.02).head_yaw == 0.0


def test_robot_stabilizer_stays_off_when_fallen_or_skill():
    from duckpilot.api import DuckBackend
    from duckpilot.backends.robotd import RobotdBackend

    rb = RobotdBackend.__new__(RobotdBackend)
    DuckBackend.__init__(rb)
    rb.set_stabilize(True)
    rb._head_wanted = Head(0, 0.1, 0, 0)
    q = [math.cos(0.1), math.sin(0.1), 0, 0]
    for params in ({"safety": {"fallen": True, "limp": False}, "policy": "walk", "imu": {"quat": q}},
                   {"safety": {"fallen": False, "limp": False}, "policy": "roulade", "imu": {"quat": q}},
                   {"safety": {"fallen": False, "limp": True}, "policy": "walk", "imu": {"quat": q}}):
        rb._stabilize_from(params, 0.02)
        assert rb.stabilizer.offset == Head() and getattr(rb, "_stab_task", None) is None


def _walk_jitter(make):
    """Synthetisches Gehen (2 Schritte/s, Rollen ±3,4°, Kippen ±2°, Gieren ±2,3°, Schub ±6 mm) – Kopfkamera per
    Vorwärtskinematik aus Pollens MJCF, Gelenke mit 40 ms Regler und einem Takt Verzug. Ergebnis: Drehzittern
    der Kamera (rad/s, RMS) und Vor/Zurück-Zittern (mm)."""
    mujoco = pytest.importorskip("mujoco")
    from duckpilot.physics import core as C

    m = mujoco.MjSpec.from_file(str(C.model_xml())).compile()
    d = mujoco.MjData(m)
    rq = m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "trunk_base_freejoint")]
    adr = {n: m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n)] for n in C.ACTUATORS}
    cam = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "head_camera")
    st, dt = make(), 0.02
    actual, queue = np.zeros(4), [np.zeros(4)]
    prev, rates, xs = None, [], []
    for k in range(400):
        t = k * dt
        w = 2 * math.pi * 2.0
        roll, pitch, yaw = 0.06 * math.sin(w * t), 0.035 * math.sin(2 * w * t + 0.6), 0.04 * math.sin(w * t + 1.2)
        s = 0.12 * t + 0.006 * math.sin(2 * w * t + 0.3)
        x, y, z = s * math.cos(yaw), s * math.sin(yaw), 0.12 + 0.004 * math.sin(2 * w * t + 1.0)
        cmd = np.array(st.update(roll, pitch, yaw, dt, x=x, y=y).as_list()) if st else np.zeros(4)
        queue.append(cmd)
        actual += (queue.pop(0) - actual) * (dt / 0.04 if dt < 0.04 else 1)
        for i, n in enumerate(C.ACTUATORS):
            d.qpos[adr[n]] = C.DEFAULT_POSE[i]
        for n, v in zip(("neck_pitch", "head_pitch", "head_yaw", "head_roll"), actual):
            d.qpos[adr[n]] += v
        q = np.zeros(4)
        mujoco.mju_euler2Quat(q, np.array([roll, pitch, yaw]), "xyz")
        d.qpos[rq:rq + 3] = [x, y, z]
        d.qpos[rq + 3:rq + 7] = q
        mujoco.mj_kinematics(m, d)
        r = d.site_xmat[cam].reshape(3, 3).copy()
        if prev is not None and t > 2:
            rates.append(math.acos(max(-1, min(1, (np.trace(r @ prev.T) - 1) / 2))) / dt)
            xs.append(d.site_xpos[cam][0])
        prev = r
    xs = np.array(xs)
    tt = np.arange(len(xs))
    return float(np.sqrt(np.mean(np.square(rates)))), float(np.std(xs - np.polyval(np.polyfit(tt, xs, 1), tt)) * 1000)


def test_walking_head_is_much_steadier():
    def on():
        s = HeadStabilizer()
        s.enabled = True
        return s
    rot0, surge0 = _walk_jitter(lambda: None)
    rot1, surge1 = _walk_jitter(on)
    assert rot1 < 0.5 * rot0, (rot0, rot1)          # Drehzittern mindestens halbiert
    assert surge1 < 0.75 * surge0, (surge0, surge1)  # Vor und zurück spürbar weniger


def test_surge_ignores_yaw_sway_far_from_the_start():
    """Weit vom Startpunkt: Gieren allein ist kein Vor-und-Zurück (früher nickte der Hals bis an den Anschlag)."""
    import math as _m

    from duckpilot.motion.stabilizer import HeadStabilizer

    s = HeadStabilizer()
    s.enabled = True
    necks = []
    for k in range(400):
        t = k * 0.02
        s.update(0.0, 0.0, 0.1 * _m.sin(2 * _m.pi * 2 * t), 0.02, x=3.0, y=2.5)   # steht still, Rumpf giert
        necks.append(abs(s.offset.neck_pitch))
    assert max(necks[50:]) < 0.01, max(necks)


def test_physics_uses_servo_tuning():
    from duckpilot.motion.stabilizer import SERVO_VORHALT, HeadStabilizer

    s = HeadStabilizer()
    s.use_servo_tuning()
    assert s.gain_pitch == 0.0 and s.vorhalt == SERVO_VORHALT
