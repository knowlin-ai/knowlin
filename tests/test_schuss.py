"""Gezielt schießen (seit 0.37.9, Wunsch des Maintainers): hinter den Ball stellen, ausrichten, prüfen, Plan B."""

import asyncio
import math

from helpers import make, run_for

from duckpilot.brain.fallback import _schuss
from duckpilot.brain.handeln import aktionen, werkzeug
from duckpilot.motion.schuss import GezielterSchuss


def _ball(sim):
    return next(i for i in sim.world_model.items if i.kind == "ball")


def _schiessen(ziel, name, r):
    async def go():
        sim, eng = await make(zufall=2)
        b = GezielterSchuss(ziel, name, r)
        eng.run(b)
        await run_for(sim, eng, 150, until=lambda: b.done)
        return b, _ball(sim)
    return asyncio.run(go())


def test_ball_reaches_the_shelf_and_the_box():
    for ziel, name, r in (((1.82, -0.6), "Regal", 0.53), ((-1.1, -0.75), "Kiste", 0.28)):
        b, ball = _schiessen(ziel, name, r)
        assert b.result.startswith("Treffer"), (name, b.result, b.info())
        assert b._dmin <= r + 0.12


def test_blocked_shot_reports_honestly_instead_of_claiming_a_hit():
    """Zum Sofa liegt der Couchtisch im Weg: Richtung stimmt, aber der Ball kommt nicht an – das sagt sie so."""
    b, ball = _schiessen((0.0, 1.22), "Sofa", 0.85)
    assert b.result.startswith("Richtung stimmt") and "Sofa" in b.result, b.result
    assert not b.result.startswith("Treffer")


def test_direction_target_and_parser_and_menu():
    async def go():
        sim, eng = await make(zufall=2)
        st = sim.state()
        # „nach links“ von der Ente aus: 3 m links von ihr
        w = st.yaw + math.pi / 2
        b = GezielterSchuss((st.x + 3 * math.cos(w), st.y + 3 * math.sin(w)), "nach links", None)
        eng.run(b)
        await run_for(sim, eng, 150, until=lambda: b.done)
        return b
    b = asyncio.run(go())
    assert b.versuche >= 1 and b.result and (b.result.startswith("Treffer") or "vorbei" in b.result), b.result
    assert _schuss("schieß den ball zum sofa") == ("schiessen", {"ziel": "sofa"})
    assert _schuss("schieß nach links") == ("schiessen", {"richtung": "links"})
    assert _schuss("kick the ball to me") == ("schiessen", {"ziel": "mir"})
    assert _schuss("schieß den ball") is None                      # einfacher Schuss wie bisher
    assert aktionen("ball")[0] == {"id": "zielen", "label": "Schießen auf …"}
    assert werkzeug("Ball", "ball", "zielen") == ("schiessen", {})


def test_vollgeraeumt_umlaeuft_sie_die_anderen_dinge():
    """Regression 0.37.14 (Befund aus dem Test „ungenau, rammelt andere Objekte weg“): Socke, Klötzchen, Klemmbaustein und
    Schachfigur liegen um den Ball – sie läuft über einen Vorpunkt hinter dem Ball drumherum und trifft trotzdem."""
    unordnung = {"Socke": (0.0, -0.3), "Klötzchen": (0.35, -0.45), "Klemmbaustein": (0.55, -0.15), "Schachfigur": (0.95, -0.2)}

    async def go(ziel, name, r):
        sim, eng = await make(zufall=2)
        for it in sim.world_model.items:
            if it.name in unordnung:
                it.x, it.y = unordnung[it.name]
        vorher = {it.name: (it.x, it.y) for it in sim.world_model.items if it.kind != "ball"}
        b = GezielterSchuss(ziel, name, r)
        eng.run(b)
        await run_for(sim, eng, 150, until=lambda: b.done)
        bewegt = [it.name for it in sim.world_model.items
                  if it.name in vorher and math.hypot(it.x - vorher[it.name][0], it.y - vorher[it.name][1]) > 0.02]
        return b, bewegt
    for ziel, name, r in (((-1.1, -0.75), "Kiste", 0.28), ((1.82, -0.6), "Regal", 0.53)):
        b, bewegt = asyncio.run(go(ziel, name, r))
        assert b.result.startswith("Treffer"), (name, b.result)
        assert not bewegt, (name, bewegt)
        assert b.dinge, "die anderen Dinge hat sie gesehen und gemieden"
