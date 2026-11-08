"""Aufstehen nach einem Sturz wie Pollens robotd: weich liegen (0,25), Rampe in die Grundstellung (0,6 s, 0,8),
Policy von vorn, Stand-Policy mit Befehl 0 – und nach 6 s ohne Erfolg wieder weich liegen."""

import asyncio
import dataclasses
import time

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from test_physics import make_store  # noqa: E402

from duckpilot.physics import core as C  # noqa: E402


class FakePolicy:
    action_scale = 1.0
    name = "fake"

    def __init__(self):
        self.resets = 0
        self.calls = 0

    def reset(self):
        self.resets += 1

    def act(self, obs):
        self.calls += 1
        return np.full(C.ACT_LEN, 0.05, np.float32)


def physics(tmp_path):
    from duckpilot.backends.physics import PhysicsBackend

    b = PhysicsBackend(make_store(tmp_path), realtime=False, use_bam=False)
    b._task = object()
    return b


def steps(b, n):
    for _ in range(n):
        b.step(0.02)


def test_limp_gains_fall_and_power_off_are_different():
    core = C.PhysicsCore(use_bam=False)
    core.set_limp(True, C.LIMP_FALL_GAIN)
    assert np.allclose(core.model.actuator_gainprm[:, 0], core.kp0 * 0.25) and core.gain == 0.25
    core.set_limp(True)                                                  # stromlos in Ruhe: weiter 0,05
    assert np.allclose(core.model.actuator_gainprm[:, 0], core.kp0 * 0.05)
    core.set_limp(False)
    assert np.allclose(core.model.actuator_gainprm[:, 0], core.kp0) and core.gain == 1.0


def test_pose_ramp_is_linear_ends_exactly_at_default_and_resets_the_policy():
    core = C.PhysicsCore(use_bam=False)
    pol = FakePolicy()
    core.set_policy(pol)
    resets0 = pol.resets
    bent = C.DEFAULT_POSE + np.linspace(-0.4, 0.4, 14).astype(np.float32)
    core.data.qpos[core.qpos_idx] = bent
    mujoco.mj_forward(core.model, core.data)
    core.last_action[:] = 0.3
    core.prev_targets = np.ones(14, np.float32)
    core.start_pose(C.POSE_S)
    von = core._pose["von"].copy()
    n = core._pose["n"]
    assert n == 30                                                       # 0,6 s bei 50 Hz
    assert core.posing and core.gain == C.POSE_GAIN
    assert np.allclose(core.model.actuator_gainprm[:, 0], core.kp0 * 0.8)
    core.set_limp(False)                                                 # wie _step_base jeden Takt: bleibt 0,8
    assert core.gain == C.POSE_GAIN
    for k in range(1, n):
        core.control_step(C.Command())
        assert np.allclose(core.data.ctrl, von + (C.DEFAULT_POSE - von) * k / n, atol=1e-6)
        assert core.gain == C.POSE_GAIN
    assert pol.calls == 0                                                # keine Policy während der Rampe
    core.control_step(C.Command())
    assert np.array_equal(core.data.ctrl.astype(np.float32), C.DEFAULT_POSE)   # genau die Grundstellung
    assert not core.posing and core.gain == 1.0
    assert pol.resets == resets0 + 1 and not core.last_action.any() and core.prev_targets is None
    core.control_step(C.Command())
    assert pol.calls == 1                                                # danach übernimmt die Policy


def test_limp_cancels_the_ramp():
    core = C.PhysicsCore(use_bam=False)
    core.start_pose()
    core.set_limp(True, C.LIMP_FALL_GAIN)
    assert not core.posing and core.gain == 0.25


def test_backend_lies_soft_then_poses_then_hands_over_and_relimps_after_timeout(tmp_path):
    from duckpilot.backends import physics as P

    b = physics(tmp_path)
    events = []
    orig_emit = b.emit
    b.emit = lambda kind, **d: (events.append({"type": kind, **d}), orig_emit(kind, **d))
    steps(b, 200)                                                        # Null-Policy: sie fällt wirklich
    assert b.fallen
    b.step(0.02)
    assert b.core.limp and b.core.gain == P.LIMP_FALL_GAIN               # liegt weich, nicht kraftlos
    res = asyncio.run(b.init())
    assert res.accepted
    b.step(0.02)
    assert b.core.posing and not b.core.limp and b.core.gain == C.POSE_GAIN
    walk = b.policies["walk"]
    assert b._command()[0] is walk                                       # ohne „stand“: VelStand, Befehl 0
    assert not b._command()[1].twist.any()
    steps(b, 35)
    assert not b.core.posing and b.core.gain == 1.0 and b.core.policy is walk
    steps(b, int(P.RECOVER_TIMEOUT_S / 0.02))                            # Null-Policy bringt sie nicht hoch
    assert b.fallen and not b._recover_ok and b.core.limp and b.core.gain == P.LIMP_FALL_GAIN
    assert any(e["type"] == "recover_fail" for e in events)
    assert asyncio.run(b.init()).accepted                                # der nächste Versuch geht wieder
    b.step(0.02)
    assert b.core.posing


def test_stand_policy_is_used_if_the_manifest_has_one(tmp_path):
    from duckpilot.physics.policies import role_of

    assert role_of({"file": "standup.onnx"}) == "stand"
    assert role_of({"file": "x.onnx", "slot": "stand"}) == "stand"
    assert role_of({"file": "velstand.onnx"}) == "walk"
    b = physics(tmp_path)
    b.policies["stand"] = stand = FakePolicy()
    b.fallen = True
    assert b._command()[0] is stand


def test_estop_and_power_off_still_block_standing_up(tmp_path):
    b = physics(tmp_path)
    steps(b, 200)
    assert b.fallen
    asyncio.run(b.init())
    b.step(0.02)
    assert b.core.posing
    asyncio.run(b.stop())                                                # Not-Aus mitten im Aufrichten
    b.step(0.02)
    assert b.core.limp and not b.core.posing and not b._recover_ok
    b.powered = False                                                    # stromlos: init richtet nicht auf
    assert not asyncio.run(b.init()).accepted
    b.step(0.02)
    assert b.core.limp and b.core.gain == 0.05 and not b.core.posing


def test_engine_never_poses_while_picked_up_or_after_estop(tmp_path):
    from helpers import run_for

    from duckpilot.motion.engine import MotionEngine

    for case in ("estop", "picked"):
        b = physics(tmp_path / case)
        eng = MotionEngine(b)
        eng.powering_until = 0
        eng.config.recover_delay = 2.0
        if case == "estop":
            eng.estop_at = time.monotonic()
        else:
            orig = b.state
            b.state = lambda orig=orig: dataclasses.replace(orig(), picked_up=True)
        posed = []

        async def go(b=b, eng=eng, posed=posed):
            for _ in range(10):
                await run_for(b, eng, 1.0)
                posed.append(b.core.posing or b._recover_ok)

        steps(b, 200)
        assert b.fallen
        asyncio.run(go())
        assert b.fallen and not any(posed) and b.core.limp


def test_roll_landing_without_head_stabilizer_until_upright(tmp_path):
    """Regression 0.33 („Rolle vorwärts – Kopf stört die Landung“): Nach dem Purzelbaum übernimmt die Geh-Policy
    mitten in der Rolle (wie robotd). Mit Kopf ruhig glich der Stabilisator dort mit bis zu 0,7 rad aus und warf sie
    wieder um (gemessen mit Pollens Policies). Jetzt: Landephase ohne Stabilisator und ohne Kopfbefehle, bis sie
    0,3 s aufrecht steht – erst dann ist der Kopf wieder dran."""
    from duckpilot.api import Head
    from duckpilot.backends import physics as P

    b = physics(tmp_path)
    real = b.core.trunk
    lage = {"up": 1.0, "z": 0.12}                    # die Ersatz-Policy kann nicht stehen – Lage vorgeben
    b.core.trunk = lambda: {**real(), **lage}
    asyncio.run(b.init())
    steps(b, 60)
    b.stabilizer.enabled = True
    b.head_target = Head(0.3, -0.3, 0.5, 0.0)
    steps(b, 2)
    assert not b.fallen and b.core.head_override is not None and b._head_cmd().any()   # vorher: Kopf ruhig an
    assert asyncio.run(b.do("roulade")).accepted
    lage.update(up=-0.9, z=0.18)                     # kopfüber, wie mitten in der Rolle
    steps(b, 2)
    assert b._landing() and b.core.head_override is None and not b._head_cmd().any()
    while b.skill == "roulade":                       # Rolle zu Ende, sie liegt aber noch kopfüber
        b.step(0.02)
    steps(b, 5)
    assert not b.fallen and b._landing(), "kopfüber nach dem Trick ist Landen, kein Sturz"
    assert b.core.head_override is None and not b._head_cmd().any(), "beim Landen keine Kopfbefehle"
    lage.update(up=1.0, z=0.12)                      # aufgerichtet
    steps(b, int(P.LANDED_HOLD_S / 0.02) - 2)
    assert b._landing(), "erst nach LANDED_HOLD_S aufrecht gilt sie als gelandet"
    steps(b, 4)
    assert not b._landing() and b._head_cmd().any(), "gelandet: Kopfbefehle wieder an"
    steps(b, 1)
    assert b.core.head_override is not None, "gelandet: Kopf ruhig wieder an"


def test_physics_state_sends_trunk_quaternion(tmp_path):
    """Regression 0.33 („Rolle sieht komisch aus“): Die 3D-Ansicht bekam nur Euler-Winkel – kopfüber springen Rollen
    und Gieren um 180°, und die Ente klappte mitten im Purzelbaum sichtbar um. Jetzt kommt die Lage als Quaternion."""
    b = physics(tmp_path)
    asyncio.run(b.init())
    steps(b, 5)
    q = b.state().body_q
    assert len(q) == 4 and abs(sum(v * v for v in q) - 1.0) < 1e-3
    w, x, y, z = q
    up = 1 - 2 * (x * x + y * y)
    assert abs(up - b.core.trunk()["up"]) < 1e-3
