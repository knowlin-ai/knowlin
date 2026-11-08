"""Odi O1 (0.38.27): Ohne jeden Sensor merkt sie sich, wo sie angestoßen ist, und läuft beim nächsten Anlauf vorbei."""

import asyncio
import math
import random

from helpers import run_for

from duckpilot.api import DuckState, Perception, Twist
from duckpilot.backends.open_duck import OpenDuckSim
from duckpilot.motion import behaviors as B
from duckpilot.motion.ausweichen import STOSS_S, Ausweicher
from duckpilot.motion.engine import EngineConfig, MotionEngine


async def _zweimal_zum_ziel_hinter_dem_tisch(mit_gedaechtnis=True):
    random.seed(1)
    s = OpenDuckSim(realtime=False, seed=1, extras=())      # Odi ohne Kamera: keine Punkte, keine Sektoren
    s._task = object()
    e = MotionEngine(s, EngineConfig(seed=0))
    if not mit_gedaechtnis:
        e.ausweicher.stoesse = lambda: []
    await e.stand_up()
    await run_for(s, e, 2.5)
    s.x, s.y, s.yaw = -0.4, 0.25, 0.0                     # Couchtisch (0,55 | 0,25) steht im Weg
    s.step(0.025)
    e.run(B.GoTo(1.25, 0.25))                             # 1. Anlauf: läuft dagegen und fällt um
    await run_for(s, e, 20)
    nach_sturz = len(e.ausweicher.stoesse())
    e.run(B.GoTo(1.25, 0.25))                             # 2. Anlauf, nachdem sie wieder steht
    await run_for(s, e, 60)
    st = s.state()
    return nach_sturz, math.hypot(1.25 - st.x, 0.25 - st.y), st


def test_merkt_sich_den_tisch_und_kommt_beim_zweiten_mal_vorbei():
    nach_sturz, rest, st = asyncio.run(_zweimal_zum_ziel_hinter_dem_tisch())
    assert st.perception.points == [] and not st.perception.sectors         # wirklich ohne Sensor
    assert nach_sturz >= 1                                                  # die Sturzstelle ist gemerkt
    assert rest < 0.15 and not st.fallen


def test_ohne_gedaechtnis_bleibt_sie_am_tisch_haengen():
    _, rest, _ = asyncio.run(_zweimal_zum_ziel_hinter_dem_tisch(mit_gedaechtnis=False))
    assert rest > 0.5


def _st(x=0.0, y=0.0, yaw=0.0, vx=0.15, ruck=None):
    return DuckState(x=x, y=y, yaw=yaw, requested=Twist(vx, 0, 0), twist=Twist(vx, 0, 0), perception=Perception(),
                     ruck=ruck, connected=True)


def test_ruck_von_vorn_merkt_die_stelle_ruck_der_hand_nicht():
    a = Ausweicher()
    a.merken(_st(), 0.05)
    a.lenken(_st(ruck={"n": 1, "staerke": 0.5, "quelle": "Hand"}), Twist(0.15, 0, 0))
    a.lenken(_st(ruck={"n": 2, "staerke": 0.5, "quelle": "Hand"}), Twist(0.15, 0, 0))
    assert a.stoesse() == []
    e = a.lenken(_st(ruck={"n": 3, "staerke": 0.6, "quelle": "Couchtisch"}), Twist(0.15, 0, 0))
    assert e.twist.vx < 0                                                   # setzt sofort zurück
    xs = {round(p[0], 2) for p in a.stoesse()}
    assert xs == {0.13} and len(a.stoesse()) == 5                           # quer vor ihr, so breit wie sie


def test_mit_tiefenpunkten_bleibt_es_wie_bisher():
    a = Ausweicher()
    a._pts[(5, 0)] = (0.0, 0.15, 0.0)
    assert not a.angestossen(_st()) and a.stoesse() == []


def test_gemerkte_stelle_verblasst_und_ziel_zaehlt_nicht():
    a = Ausweicher()
    a.merken(_st(), 0.05)
    a._ziel = (0.2, 0.0, 0.1)                                               # sie will genau dorthin (Ball schießen)
    assert not a.angestossen(_st())
    a._ziel = None
    assert a.angestossen(_st()) and a.stoesse()
    assert not a.angestossen(_st(vx=0.0))                                   # im Stehen angestoßen: nichts merken
    a.merken(_st(), STOSS_S + 1)
    assert a.stoesse() == []
