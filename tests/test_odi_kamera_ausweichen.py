"""Hinweis 7.11. spätabends: „Odis Kamera kann doch Objekte erkennen und die Laufbahn berechnen – sollte doch
gehen.“ – Mit Kamera schätzt Odi die Tiefe aus dem Bild und umläuft Hindernisse; ohne Kamera bleibt es ehrlich aus."""

import asyncio
import math
import random

from helpers import run_for

from duckpilot.backends.open_duck import KAMERA_FEHLER, KAMERA_TIEFE_MAX, OpenDuckSim
from duckpilot.motion import behaviors as B
from duckpilot.motion.engine import EngineConfig, MotionEngine


async def _zum_ball_hinter_dem_tisch(extras):
    random.seed(1)                                        # Suchdrehungen im Verhalten nutzen den globalen Zufall
    s = OpenDuckSim(realtime=False, seed=1, extras=extras)
    s._task = object()
    e = MotionEngine(s, EngineConfig(seed=0))            # Leerlauf-Zufall fest – sonst hängt es von früheren Tests ab
    await e.stand_up()
    await run_for(s, e, 2.5)
    s.x, s.y, s.yaw = -0.4, 0.25, 0.0                     # Couchtisch (0,55 | 0,25) liegt genau dazwischen
    ball = next(i for i in s.world_model.items if i.kind == "ball")
    ball.x, ball.y = 1.25, 0.25
    s.step(0.025)                                         # Wahrnehmung am neuen Platz
    pts = s.state().perception.points
    e.run(B.Approach("ball"))
    await run_for(s, e, 60)
    st = s.state()
    return pts, math.hypot(ball.x - st.x, ball.y - st.y), st


def test_mit_kamera_umlaeuft_odi_den_tisch():
    pts, rest, st = asyncio.run(_zum_ball_hinter_dem_tisch(("kamera",)))
    assert pts and all(math.hypot(p[0] + 0.4, p[1] - 0.25) <= KAMERA_TIEFE_MAX * (1 + KAMERA_FEHLER) + 0.01
               for p in pts)
    assert st.perception.source == "kamera_tiefe" and not st.perception.tof_mm      # kein ToF-Bild, nur geschätzte Tiefe
    assert rest < 0.3                                                               # am Ball angekommen


def test_ohne_kamera_keine_tiefe_und_kein_umlaufen():
    pts, rest, _ = asyncio.run(_zum_ball_hinter_dem_tisch(()))
    assert pts == [] and rest > 1.0
