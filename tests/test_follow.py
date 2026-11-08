"""Folg mir: Menschen-Figur im Simulator, Verhalten hält Abstand, Werkzeug und Schnellbefehl."""

import asyncio
import math

from helpers import make, run_for

from duckpilot.brain.fallback import parse
from duckpilot.brain.tools import TOOLS
from duckpilot.motion import behaviors as B


def run(coro):
    return asyncio.run(coro)


def test_person_is_seen_as_person_without_identity():
    async def go():
        sim, eng = await make()
        sim.set_person(sim.x + 1.0 * math.cos(sim.yaw), sim.y + 1.0 * math.sin(sim.yaw))
        objs = [o for o in sim.state().perception.objects if o["art"] == "person"]
        assert len(objs) == 1 and objs[0]["name"] == "Mensch" and abs(objs[0]["entfernung_m"] - 1.0) < 0.15
        assert set(objs[0]) == {"name", "art", "entfernung_m", "richtung_grad"}     # kein Gesicht, keine Kennung
        sim.set_person(None, None)
        assert not [o for o in sim.state().perception.objects if o["art"] == "person"]
    run(go())


def test_duck_follows_and_keeps_distance():
    async def go():
        sim, eng = await make()
        tx, ty = sim.x + 1.4 * math.cos(sim.yaw), sim.y + 1.4 * math.sin(sim.yaw)

        def keep_person():
            sim.set_person(tx, ty)                # die Maus hält die Figur fest (Lebenszeichen)
            return False
        keep_person()
        eng.run(B.FollowMe(60))
        await run_for(sim, eng, 20, until=keep_person)
        d = math.hypot(tx - sim.x, ty - sim.y)
        assert 0.3 < d < 0.75, d                   # hingelaufen, aber nicht hineingelaufen
        assert isinstance(eng.current, B.FollowMe)
        sim.set_person(None, None)
        await run_for(sim, eng, 25)
        assert eng.current is None                  # Mensch weg → sucht kurz, hört dann auf
    run(go())


def test_tool_and_quick_command():
    assert any(t["name"] == "mir_folgen" for t in TOOLS)
    assert parse("folg mir")[0][0] == "mir_folgen"
    assert parse("komm mit")[0][0] == "mir_folgen"
    assert parse("folge mir 2 Minuten")[0] == ("mir_folgen", {"seconds": 120})
