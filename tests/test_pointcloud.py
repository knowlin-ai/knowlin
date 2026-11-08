"""Punktwolke: das 8×8-Tiefenbild als Punkte im Raum."""

import asyncio
import math

from helpers import make, run_for

from duckpilot.api import tof_points


def test_wall_ahead_lands_in_front_of_the_duck():
    # Wand in 1 m Abstand, Blick geradeaus, Sensor 0,2 m hoch
    pts = tof_points([1000] * 64, x=0.5, y=-0.2, yaw=0.0, head_yaw=0.0, tilt=0.0, cam_h=0.2)
    assert len(pts) == 64
    xs = [p[0] for p in pts]
    assert all(1.3 < x <= 1.5 for x in xs)                      # 0,5 + cos(Winkel) · 1 m
    left = pts[0]                                                # Zeile 0, Spalte 0 = oben links
    right = pts[7]
    assert left[1] > -0.2 > right[1]                             # links = +y
    assert pts[0][2] > 0.2 > pts[63][2]                          # oben höher als unten


def test_heading_rotates_the_points():
    a = tof_points([800] * 64, x=0, y=0, yaw=math.pi / 2, head_yaw=0.0, tilt=0.0, cam_h=0.2)
    b = tof_points([800] * 64, x=0, y=0, yaw=0.0, head_yaw=math.pi / 2, tilt=0.0, cam_h=0.2)
    assert a == b                                                # Körper und Kopf drehen gleich
    assert all(p[1] > 0.7 and abs(p[0]) < 0.35 for p in a)       # Blick nach links (+y)


def test_no_hits_and_invalid_zones_are_dropped():
    frame = [2000] * 64
    frame[10] = 900
    frame[11] = 700
    status = [5] * 64
    status[11] = 255
    pts = tof_points(frame, x=0, y=0, yaw=0, head_yaw=0, tilt=0, cam_h=0.2, status=status)
    assert len(pts) == 1


def test_floor_points_lie_on_the_floor():
    # Blick nach unten: der Simulator misst den Boden, die Punkte liegen bei z ≈ 0
    tilt = 0.6
    frame = []
    for row in range(8):
        elev = (3.5 - row) / 8 * math.radians(45) - tilt
        frame.append(int(0.2 / math.sin(-elev) * 1000))
    pts = tof_points([d for d in frame for _ in range(8)], x=0, y=0, yaw=0, head_yaw=0, tilt=tilt, cam_h=0.2)
    assert pts and all(p[2] < 0.01 for p in pts)


def test_simulator_reports_points_on_obstacles():
    async def go():
        sim, eng = await make()
        await run_for(sim, eng, 1.0)
        return sim.state()

    st = asyncio.run(go())
    pts = st.perception.points
    assert pts, "der Simulator liefert Punkte"
    assert all(len(p) == 3 for p in pts)
    assert any(p[2] > 0.03 for p in pts), "auch Hindernisse, nicht nur Boden"
    # alle Punkte höchstens 2 m vom Sensor entfernt
    assert all(math.hypot(p[0] - st.x, p[1] - st.y) <= 2.01 for p in pts)
