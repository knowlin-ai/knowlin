"""Funde 7.11.: „Open Duck ist zweimal auf Befehl nicht richtig zum Ball gelaufen“, „um den Tisch läuft er auch
nicht – er läuft einfach ein bisschen nach vorn“, „schießen kann er auch nicht wie die Microduck?“.
Ursache: Die einfachen Befehle kannten „lauf zum …“ und „lauf um …“ nicht und machten daraus 40 cm geradeaus."""

import asyncio
import math

import pytest
from helpers import run_for

from duckpilot.backends.open_duck import OpenDuckSim
from duckpilot.backends.sim import SimBackend
from duckpilot.brain.fallback import parse
from duckpilot.motion import behaviors as B
from duckpilot.motion.engine import MotionEngine
from duckpilot.motion.umrunden import Umrunden, rundweg


@pytest.mark.parametrize("satz, erwartet", [
    ("lauf zum Ball", ("approach", {"target": "ball"})),
    ("geh mal zur Socke", ("approach", {"target": "socke"})),
    ("walk to the ball", ("approach", {"target": "ball"})),
    ("lauf um den Tisch", ("umrunden", {"target": "couchtisch", "richtung": "links"})),
    ("lauf rechts herum um das Sofa", ("umrunden", {"target": "sofa", "richtung": "rechts"})),
    ("umrunde die Kiste", ("umrunden", {"target": "kiste", "richtung": "links"})),
    ("walk around the table", ("umrunden", {"target": "couchtisch", "richtung": "links"})),
])
def test_einfache_befehle_kennen_hin_und_herum(satz, erwartet):
    assert parse(satz) == [erwartet]


def test_bisherige_befehle_bleiben():
    assert parse("lauf vor") == [("walk", {"distance_m": 0.4})]
    assert parse("lauf zum Ball und schieß ihn") == [("_kick", {"side": "kick_left"})]
    assert parse("lauf zur Socke und bring sie mir") == [("apportieren", {"ding": "socke"})]
    assert parse("lauf herum")[0][0] == "explore" and parse("walk around")[0][0] == "explore"


def test_rundweg_um_kasten_mit_abstand():
    punkte = rundweg(0.0, 0.0, (0.5, 0.5), None, abstand=0.2)
    assert len(punkte) == 12
    assert min(max(abs(x), abs(y)) for x, y in punkte) >= 0.25 + 0.2 - 1e-6 or all(math.hypot(x, y) >= 0.44 for x, y in punkte)


async def _bereit(cls):
    sim = cls(realtime=False, seed=1)
    sim._task = object()
    eng = MotionEngine(sim)
    await eng.stand_up()
    await run_for(sim, eng, 2.5)
    return sim, eng


@pytest.mark.parametrize("cls", [OpenDuckSim, SimBackend])
def test_laeuft_wirklich_zum_ball(cls):
    async def go():
        sim, eng = await _bereit(cls)
        b = B.Approach("ball")
        eng.run(b)
        await run_for(sim, eng, 40, until=lambda: b.done)
        ball = next(i for i in sim.world_model.items if i.kind == "ball")
        return b, math.hypot(ball.x - sim.x, ball.y - sim.y)
    b, abstand = asyncio.run(go())
    assert b.result.startswith("vor Ball") and abstand < 0.25


@pytest.mark.parametrize("cls", [OpenDuckSim, SimBackend])
def test_einmal_um_den_couchtisch(cls):
    async def go():
        sim, eng = await _bereit(cls)
        b = Umrunden("couchtisch")
        eng.run(b)
        tisch = next(o for o in sim.world_model.boxes if o.name == "Couchtisch")
        winkel, alt, naechst = 0.0, None, 9.0
        for _ in range(100):
            await run_for(sim, eng, 1.0)
            a = math.atan2(sim.y - tisch.y, sim.x - tisch.x)
            if alt is not None:
                winkel += math.atan2(math.sin(a - alt), math.cos(a - alt))
            alt, naechst = a, min(naechst, math.hypot(sim.x - tisch.x, sim.y - tisch.y))
            if b.done:
                break
        return b, winkel, naechst
    b, winkel, naechst = asyncio.run(go())
    assert b.result.startswith("einmal um Couchtisch") and math.degrees(winkel) > 320 and naechst > 0.25


def test_an_der_wand_ehrlich_soweit_platz_ist():
    async def go():
        sim, eng = await _bereit(OpenDuckSim)
        b = Umrunden("sofa")
        eng.run(b)
        await run_for(sim, eng, 150, until=lambda: b.done)
        return b
    b = asyncio.run(go())
    assert "soweit Platz ist" in b.result and not getattr(b, "failed", False)


def test_odi_schiesst_im_simulator():
    async def go():
        sim, eng = await _bereit(OpenDuckSim)
        ball = next(i for i in sim.world_model.items if i.kind == "ball")
        start = (ball.x, ball.y)
        b = B.KickBall("kick_left") if hasattr(B, "KickBall") else None
        eng.run(b)
        await run_for(sim, eng, 60, until=lambda: b.done)
        await run_for(sim, eng, 1.5)
        return math.hypot(ball.x - start[0], ball.y - start[1]), b
    weg, b = asyncio.run(go())
    assert weg > 0.2, b.result


def test_bring_es_zum_ball_legt_daneben():
    """Fund 7.11.: „sammle alle Objekte und bring sie zum Ball“ → „Keinen Ort namens 'Ball'“. Jetzt: neben den Ball."""
    from duckpilot.brain.tools import ToolRunner

    async def go():
        sim, eng = await _bereit(SimBackend)
        r = ToolRunner(eng)
        ball = next(i for i in sim.world_model.items if i.kind == "ball")
        # Ball ins Blickfeld drehen, damit er „gerade gesehen“ ist
        while not any(o["art"] == "ball" for o in sim.state().perception.objects):
            sim.yaw += 0.2
            sim.step(0.05)
        res = await r.run("apportieren", {"ding": "socke", "zu": "Ball"})
        b = eng.current or (eng.queue[0] if getattr(eng, "queue", None) else None)
        return res, b, ball
    res, b, ball = asyncio.run(go())
    assert res.get("ok", True) is not False, res
    assert b is not None and b.zu_name == "neben Ball" and math.hypot(b.zu[0] - ball.x, b.zu[1] - ball.y) < 0.3
