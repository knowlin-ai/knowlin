"""Hinweis 7.11. abends: „Not-Aus dachte ich legt den Roboter sofort lahm – bricht aber nur die aktuelle Aufgabe
ab.“ Entschieden: sofort stromlos (wie Pollens `robot.relax`), bei jeder Verkörperung."""

import asyncio
import time

from helpers import make, run_for

from duckpilot.backends.fake_robotd import start_server
from duckpilot.backends.robotd import RobotdBackend
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion import behaviors as B
from duckpilot.server.app import STATIC


def test_not_aus_macht_die_ente_stromlos_und_sie_bleibt_liegen():
    async def go():
        sim, eng = await make()
        assert sim.state().powered
        eng.run(B.Walk(0.5))
        await run_for(sim, eng, 0.5)
        await eng.not_aus("Not-Aus")
        assert eng.current is None and not eng.queue                    # die Aufgabe ist weg …
        assert not sim.state().powered and not sim.enabled              # … und die Motoren sind aus
        assert sim.skill == "_relax"                                     # sie sackt sichtbar zusammen
        await run_for(sim, eng, 3)
        st = sim.state()
        assert not st.powered and st.skill is None                       # und steht nicht von selbst auf
        r = await ToolRunner(eng).run("walk", {"distance_m": 0.3})
        assert not r["ok"] and "Not-Aus" in r["fehler"]                  # Befehle in der Sperre: ehrlich abgelehnt
    asyncio.run(go())


def test_ohne_not_aus_bleibt_anhalten_anhalten():
    """Claudes stop-Werkzeug und interne Stopps halten nur an – stromlos macht nur der Not-Aus selbst."""
    async def go():
        sim, eng = await make()
        await eng.stop_all("intern")
        await run_for(sim, eng, 0.5)
        assert sim.state().powered
        await ToolRunner(eng).run("stop", {})
        await run_for(sim, eng, 0.5)
        assert sim.state().powered and eng.notaus_gesperrt()
    asyncio.run(go())


def test_not_aus_schickt_robot_relax_an_den_echten_roboter():
    async def go():
        server, fake = await start_server("tcp:127.0.0.1:7937")
        be = RobotdBackend("tcp:127.0.0.1:7937", tof="tcp:127.0.0.1:7937")
        await be.connect()
        from duckpilot.motion.engine import MotionEngine

        eng = MotionEngine(be)
        await eng.start()
        try:
            for _ in range(40):
                await asyncio.sleep(0.1)
                if be.state().connected:
                    break
            assert (await eng.stand_up()).accepted
            await asyncio.sleep(2.3)
            assert be.state().powered
            await eng.not_aus("Not-Aus")
            for _ in range(20):
                await asyncio.sleep(0.1)
                if not be.state().powered:
                    break
            assert not be.state().powered and eng.notaus_gesperrt()
        finally:
            await eng.close()
            await be.close()
            server.close()
    asyncio.run(go())


def test_gaeste_werden_mit_stromlos_und_stehen_nach_der_sperre_auf():
    from duckpilot.backends.begleiter import Begleitente
    from duckpilot.motion.schwarm import Schwarm

    async def go():
        sim, eng = await make()
        sw = Schwarm(sim, eng, lambda i, x, y, yaw: Begleitente(sim.world_model, i, x, y, yaw))
        sw.anzahl(1)
        gast = sw.enten[0]
        sw.step(0.05)
        assert gast.powered
        eng.notaus()
        for _ in range(20):
            sw.step(0.05)
        assert not gast.powered
        eng.estop_at = time.monotonic() - eng.sperre_s - 1                # Sperre vorbei
        for _ in range(60):
            sw.step(0.05)
        assert gast.powered
    asyncio.run(go())


def test_oberflaeche_sagt_stromlos():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "Motoren sofort aus" in html and "Not-Aus: Motoren sofort aus (Esc)" in html
