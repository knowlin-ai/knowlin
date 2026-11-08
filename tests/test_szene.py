"""Simulator: Ball bleibt im Zimmer, Szene zurücksetzen, Akku (seit 0.37.14, Befunde aus dem Test mit 0.37.13)."""

import asyncio

from helpers import make, run_for

from duckpilot.backends.sim import SIM_AKKU_MIN, SimBackend
from duckpilot.backends.world import World
from duckpilot.brain.fallback import parse
from duckpilot.brain.handeln import aktionen
from duckpilot.brain.tools import ToolRunner


def run(coro):
    return asyncio.run(coro)


def _ball(w):
    return next(i for i in w.items if i.kind == "ball")


def test_ball_bleibt_in_der_ecke_im_zimmer():
    """Regression: kräftiger Schuss in die Ecke – vorher steckte er halb in der Wand (nur eine Wand berücksichtigt)."""
    w = World.living_room()
    b = _ball(w)
    for ecke in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        b.x, b.y = ecke[0] * (w.width / 2 - 0.1), ecke[1] * (w.depth / 2 - 0.1)
        b.vx, b.vy = ecke[0] * 3.0, ecke[1] * 3.0
        for _ in range(200):
            w.step_items(0.02)
            assert abs(b.x) <= w.width / 2 - b.r + 1e-9 and abs(b.y) <= w.depth / 2 - b.r + 1e-9
        assert w.collide(b.x, b.y, b.r) is None


def test_schubsen_drueckt_nichts_in_die_wand():
    async def go():
        sim, eng = await make()
        w = sim.world_model
        b = _ball(w)
        b.x, b.y = w.width / 2 - b.r - 0.005, 0.0           # Ball an der Wand
        sim.x, sim.y, sim.yaw = b.x - 0.12, 0.0, 0.0          # Ente schiebt von innen
        sim._push_items()
        assert b.x <= w.width / 2 - b.r + 1e-9
    run(go())


def test_szene_zuruecksetzen_und_zuruecklegen():
    async def go():
        sim, eng = await make()
        runner = ToolRunner(eng)
        b = _ball(sim.world_model)
        start = (b.x, b.y)
        b.x, b.y = 1.4, 1.4
        res = await runner.run("szene", {"aktion": "zuruecklegen", "ding": "Ball"})
        assert res["ok"] and (b.x, b.y) == start
        b.x, b.y = -1.0, 1.0
        sim.x, sim.y = 0.8, 0.8
        res = await runner.run("szene", {"aktion": "zuruecksetzen"})
        assert res["ok"] and res["ente"] and "Ball" in res["dinge"]
        assert (b.x, b.y) == start and (sim.x, sim.y) == SimBackend.START_POSE[:2]
        assert "Dinge an ihren Platz gelegt" in res["text"]
    run(go())


def test_liegende_ente_wird_nicht_versetzt():
    async def go():
        sim, eng = await make()
        sim.fallen = True
        sim.x, sim.y = 0.5, 0.5
        res = ToolRunner(eng).szene("zuruecksetzen")
        assert res["ok"] and not res["ente"] and "bleibt, wo sie ist" in res["hinweis"]
        assert (sim.x, sim.y) == (0.5, 0.5) and sim.fallen        # nie hier aufstellen
    run(go())


def test_zuruecklegen_im_anwaehlen_menue_und_per_sprache():
    assert "zuruecklegen" in [a["id"] for a in aktionen("ball")]
    assert "zuruecklegen" in [a["id"] for a in aktionen("sock")]
    assert parse("Szene zurücksetzen") == [("szene", {"aktion": "zuruecksetzen"})]
    assert parse("leg den Ball zurück") == [("szene", {"aktion": "zuruecklegen", "ding": "ball"})]
    assert parse("bring die Socke zurück")[0][0] == "apportieren"           # heißt: bring sie mir
    assert parse("geh zurück")[0][0] == "walk"


def test_handeln_zuruecklegen():
    async def go():
        sim, eng = await make()
        b = _ball(sim.world_model)
        start = (b.x, b.y)
        b.x = 1.3
        res = await ToolRunner(eng).run("handeln", {"ding": "Ball", "aktion": "zuruecklegen"})
        assert res["ok"] and (b.x, b.y) == start
    run(go())


def test_sim_akku_wird_nie_leer():
    async def go():
        sim, eng = await make()
        sim.battery = SIM_AKKU_MIN + 0.002
        eng.run(__import__("duckpilot.motion.behaviors", fromlist=["Walk"]).Turn(720))
        await run_for(sim, eng, 30)
        assert sim.battery >= SIM_AKKU_MIN
        status = ToolRunner(eng).status()
        assert status["akku"].endswith("(simuliert)")
    run(go())
