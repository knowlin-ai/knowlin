"""Laserpunkt folgen: Erkenner im Kamerabild, Bodenpunkt, Simulator-Pointer, Verhalten, Werkzeug."""

import asyncio
import math

import numpy as np
from helpers import make, run_for

from duckpilot.brain.fallback import parse
from duckpilot.brain.tools import TOOLS, ToolRunner
from duckpilot.laser import detect_laser, to_floor
from duckpilot.motion import behaviors as B


def frame(w=320, h=240, base=(70, 60, 55)):
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = base
    return img


def disc(img, cx, cy, r, color):
    yy, xx = np.ogrid[: img.shape[0], : img.shape[1]]
    img[(yy - cy) ** 2 + (xx - cx) ** 2 <= r * r] = color


# ── Erkenner ──────────────────────────────────────────────────────────────
def test_small_bright_red_dot_is_found():
    img = frame()
    disc(img, 200, 150, 5, (255, 40, 30))
    disc(img, 200, 150, 1, (255, 240, 235))          # überstrahlter Kern
    spot = detect_laser(img)
    assert spot is not None
    assert abs(spot["x"] - 200) < 2 and abs(spot["y"] - 150) < 2


def test_big_red_ball_is_not_a_laser():
    img = frame()
    disc(img, 120, 140, 30, (230, 50, 40))           # der rote Ball nah vor der Kamera
    assert detect_laser(img) is None


def test_laser_beats_dull_red_object():
    img = frame()
    disc(img, 80, 120, 25, (205, 70, 60))            # Kissen: rot, aber matt
    disc(img, 250, 60, 4, (255, 30, 20))             # Laser: klein und knallig
    spot = detect_laser(img)
    assert spot is not None and abs(spot["x"] - 250) < 3


def test_no_red_no_laser():
    img = frame(base=(200, 200, 200))
    assert detect_laser(img) is None


# ── Bildpunkt → Boden ─────────────────────────────────────────────────────
def test_image_centre_projects_to_floor_by_tilt():
    obj = to_floor({"x": 160, "y": 120}, 320, 240, tilt=0.6, head_yaw=0.0)
    assert obj["art"] == "laser" and obj["richtung_grad"] == 0
    assert abs(obj["entfernung_m"] - 0.21 / math.tan(0.6)) < 0.01


def test_left_in_image_is_positive_bearing_and_head_yaw_adds():
    left = to_floor({"x": 40, "y": 200}, 320, 240, tilt=0.3, head_yaw=0.0)
    assert left["richtung_grad"] > 15
    turned = to_floor({"x": 160, "y": 200}, 320, 240, tilt=0.3, head_yaw=math.radians(-30))
    assert turned["richtung_grad"] == -30


def test_dot_above_horizon_counts_as_far():
    obj = to_floor({"x": 160, "y": 10}, 320, 240, tilt=0.0, head_yaw=0.0)
    assert obj["entfernung_m"] == 1.5


# ── Simulator ─────────────────────────────────────────────────────────────
def test_sim_sees_laser_in_front_not_behind():
    async def go():
        sim, eng = await make()
        sim.set_laser(sim.x + 0.6, sim.y)
        seen = [o for o in sim.state().perception.objects if o["art"] == "laser"]
        assert seen and abs(seen[0]["richtung_grad"]) <= 3 and 0.5 < seen[0]["entfernung_m"] < 0.6
        sim.set_laser(sim.x - 0.6, sim.y)
        assert not [o for o in sim.state().perception.objects if o["art"] == "laser"]
        sim.set_laser(None, None)
        assert sim.laser() is None
    asyncio.run(go())


def test_laser_expires_without_keepalive(monkeypatch):
    async def go():
        sim, _ = await make()
        sim.set_laser(sim.x + 0.5, sim.y)
        x, y, t = sim.world_model.laser
        sim.world_model.laser = (x, y, t - 10)
        assert sim.laser() is None
    asyncio.run(go())


def test_follow_laser_walks_to_the_dot_and_waits():
    async def go():
        sim, eng = await make()
        tx, ty = sim.x + 0.8, sim.y + 0.25
        sim.set_laser(tx, ty)
        eng.run(B.FollowLaser(60))
        reached = await run_for(sim, eng, 25, until=lambda: math.hypot(tx - sim.x, ty - sim.y) < 0.2)
        assert reached, (sim.x, sim.y)
        await run_for(sim, eng, 3)
        assert math.hypot(tx - sim.x, ty - sim.y) > 0.08          # bleibt davor stehen, tritt nicht drauf
        assert eng.current is not None and isinstance(eng.current, B.FollowLaser)
        assert eng.current.caught >= 1
    asyncio.run(go())


def test_follow_laser_turns_to_a_dot_at_the_side_and_follows_when_it_moves():
    async def go():
        sim, eng = await make()
        sim.set_laser(sim.x + 0.1, sim.y + 0.5)                   # links neben ihr
        eng.run(B.FollowLaser(60))
        ok = await run_for(sim, eng, 12, until=lambda: math.hypot(sim.world_model.laser[0] - sim.x,
                                                                   sim.world_model.laser[1] - sim.y) < 0.2)
        assert ok
        x0, y0 = sim.x, sim.y
        sim.set_laser(x0 + 0.5, y0 - 0.1)                          # Punkt springt hinter ihre Schulter
        ok = await run_for(sim, eng, 20, until=lambda: math.hypot(x0 + 0.5 - sim.x, y0 - 0.1 - sim.y) < 0.2)
        assert ok
    asyncio.run(go())


def test_follow_laser_gives_up_when_dot_stays_away():
    async def go():
        sim, eng = await make()
        sim.set_laser(None, None)
        b = B.FollowLaser(60)
        eng.run(b)
        await run_for(sim, eng, 18, until=lambda: b.done)
        assert b.done and b.result == "keinen Laserpunkt gesehen"
        assert not getattr(b, "failed", False)
    asyncio.run(go())


def test_follow_laser_keeps_obstacle_reflex_on():
    async def go():
        sim, eng = await make()
        b = B.FollowLaser(30)
        sim.set_laser(sim.x + 0.5, sim.y)
        eng.run(b)
        await run_for(sim, eng, 1)
        cmd = b.tick(sim.state(), 0.05)
        assert cmd.guard is True
    asyncio.run(go())


# ── Werkzeug, Sprache ohne Claude ─────────────────────────────────────────
def test_tool_and_fallback():
    assert any(t["name"] == "laser_folgen" for t in TOOLS)
    assert parse("Folge dem Laser") == [("laser_folgen", {"seconds": 120})]

    async def go():
        sim, eng = await make()
        r = await ToolRunner(eng).run("laser_folgen", {"seconds": 30})
        assert r.get("ok") is not False, r
        assert isinstance(eng.current, B.FollowLaser)
    asyncio.run(go())


def test_stop_ends_following():
    async def go():
        sim, eng = await make()
        sim.set_laser(sim.x + 0.6, sim.y)
        runner = ToolRunner(eng)
        await runner.run("laser_folgen", {})
        await run_for(sim, eng, 1)
        await runner.run("stop", {})
        assert eng.current is None
    asyncio.run(go())


# ── echter Roboter: Kamera-Dinge kommen in die Wahrnehmung ────────────────
def test_robotd_reports_fresh_camera_objects_only():
    import time

    from duckpilot.backends.robotd import RobotdBackend

    be = RobotdBackend("127.0.0.1:1")
    be.see_objects([{"name": "Laserpunkt", "art": "laser", "entfernung_m": 0.4, "richtung_grad": 5}])
    assert be.state().perception.objects[0]["art"] == "laser"
    be._seen_at = time.monotonic() - 5
    assert be.state().perception.objects == []
    tilt, yaw = be.gaze()
    assert tilt == 0 and yaw == 0


# ── Oberfläche → Server ───────────────────────────────────────────────────
def test_runtime_laser_messages(tmp_path, monkeypatch):
    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))

    async def go():
        rt._laser_message({"type": "laser", "x": 0.4, "y": 0.1, "z": 0.3})
        assert rt.backend.laser() == {"x": 0.4, "y": 0.1, "z": 0.3}
        rt.engine.run(B.FollowLaser(30))
        rt._laser_message({"type": "laser", "x": None, "y": "kaputt"})       # kaputter Punkt: nichts ausschalten
        assert rt.backend.laser() is not None and isinstance(rt.engine.current, B.FollowLaser)
        rt._laser_message({"type": "laser", "aus": True})
        assert rt.backend.laser() is None and rt.engine.current is None
        await asyncio.sleep(0)
    asyncio.run(go())
