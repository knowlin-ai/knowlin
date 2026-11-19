"""Ballspiel und Zuspielen (seit 0.38.66) – Regressionstests zum Fund vom 15.11.

„Ball spielen (mir zuschießen oder mit den anderen Enten spielen) – macht er hier nicht, was ich will“, und mit dem
eigenen Sprachmodell hing ständig „Jetzt mache ich es wirklich.“ an den Antworten.
"""

import asyncio

from helpers import make, run_for

from duckpilot.backends.begleiter import Begleitente
from duckpilot.brain import zusage
from duckpilot.brain.fallback import parse
from duckpilot.brain.local import LOCAL_TOOLS
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion.schwarm import Schwarm


async def _team(n):
    sim, eng = await make()
    sw = Schwarm(sim, eng, lambda i, a, b, yaw: Begleitente(sim.world_model, i, a, b, yaw))
    sim.nach_schritt.append(sw.step)
    sw.anzahl(n)
    r = ToolRunner(eng)
    r.schwarm = sw
    return sim, eng, sw, r


def test_zuspielen_wird_verstanden():
    for satz in ("schieß mir den Ball zu", "spiel mir den Ball zu", "pass mir den Ball", "bring mir den Ball",
                 "kick the ball to me", "roll the ball to me"):
        assert parse(satz) == [("schiessen", {"ziel": "mir"})], satz
    assert parse("bring mir die Socke") == [("apportieren", {"ding": "socke"})]
    assert parse("schieß den Ball zu Kiki") == [("schiessen", {"ziel": "kiki"})]


def test_ballspiel_wird_verstanden():
    assert parse("spielt euch den Ball zu") == [("team", {"aktion": "ballspiel", "mit_mir": False})]
    assert parse("spiel mit den anderen Enten Ball") == [("team", {"aktion": "ballspiel", "mit_mir": False})]
    assert parse("play ball with the others") == [("team", {"aktion": "ballspiel", "mit_mir": False})]
    assert parse("lass uns Ball spielen") == [("team", {"aktion": "ballspiel", "mit_mir": True})]
    assert parse("spielt alle zusammen Fußball")[0][1]["aktion"] == "ballspiel"
    assert zusage.verlangt("spielt euch den Ball zu") and zusage.verlangt("schieß mir den Ball zu")


def test_eigenes_modell_hat_die_werkzeuge_fuer_ball_und_team():
    assert {"schiessen", "apportieren", "handeln", "team", "enten"} <= LOCAL_TOOLS


def test_zusage_erkennt_gleichwertige_werkzeuge_und_ehrliche_absagen():
    assert zusage.erfuellt([("skill", {"name": "roulade"})], [{"tool": "do_trick", "input": {"name": "roulade"}}])
    assert zusage.erfuellt([("team", {"aktion": "ballspiel"})], [{"tool": "enten", "input": {}}])
    assert not zusage.erfuellt([("skill", {"name": "roulade"})], [{"tool": "do_trick", "input": {"name": "winken"}}])
    for absage in ("Das kann ich als Bello leider nicht.", "Purzelbaum mache ich hier nicht.", "I cannot do that."):
        assert zusage.LEHNT_AB.search(absage), absage
    assert not zusage.LEHNT_AB.search("Klar, hier kommt er!")


def test_enten_spielen_sich_den_ball_zu():
    async def go():
        sim, eng, sw, r = await _team(3)
        res = await r.run("team", {"aktion": "ballspiel", "mitspielen": False})
        assert res["ok"] and res["mitspieler"] == ["Kiki", "Pip", "Lotte"], res
        a = sw.auftrag
        await run_for(sim, eng, 60, until=lambda: a.paesse >= 4)
        assert a.paesse >= 4, a.zustand()
        assert any("spielt" in m and " zu" in m for m in a.meldungen)
        assert {u["tut"] for u in sw.uebersicht()} <= {"spielt Ball", "ist am Ball"}
        assert (await r.run("team", {"aktion": "stopp"}))["gestoppt"] == "ballspiel" and a.fertig
    asyncio.run(go())


def test_die_ente_spielt_selbst_mit():
    async def go():
        sim, eng, sw, r = await _team(2)
        res = await r.run("team", {"aktion": "ballspiel"})
        assert res["ok"] and "die Ente selbst" in res["mitspieler"]
        a = sw.auftrag
        await run_for(sim, eng, 115, until=lambda: a.paesse >= 2 and any(m.startswith("Die Ente spielt")
                                                                          for m in a.meldungen))
        assert a.paesse >= 2 and any(m.startswith("Die Ente spielt") for m in a.meldungen), a.zustand()
        eng.notaus()                                        # Not-Aus beendet das Spiel für alle
        await run_for(sim, eng, 1)
        assert sw.auftrag is None or sw.auftrag.fertig
    asyncio.run(go())


def test_ohne_andere_enten_spielt_sie_dem_menschen_zu():
    async def go():
        sim, eng = await make()
        r = ToolRunner(eng)
        sim.world_model.set_person(-0.8, 0.6)
        res = await r.run("team", {"aktion": "ballspiel", "mit_mir": True})
        assert res.get("ok") and eng.current is not None and "dir" in eng.current.describe(), res
        res = await r.run("team", {"aktion": "ballspiel"})
        assert not res["ok"] and "Keine weiteren Enten" in res["fehler"]
    asyncio.run(go())
