"""Gefühle: situativ, abklingend, nie aufmerksamkeitsheischend – und der Persönlichkeitsregler."""

import asyncio

import pytest
from helpers import make, run_for

from duckpilot import settings as S
from duckpilot.brain.agent import AgentConfig, DuckAgent
from duckpilot.brain.fallback import FallbackBrain
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion import behaviors as B
from duckpilot.motion.mood import Mood


def run(coro):
    return asyncio.run(coro)


def test_success_after_struggle_is_relief_and_joy():
    m = Mood()
    m.appraise({"type": "kick_miss"})
    assert m.appraise({"type": "kick_miss"}) == "frustriert"
    assert m.feeling().name == "frustriert" and "daneben" in m.feeling().reason
    assert m.appraise({"type": "kick"}) == "begeistert"
    f = m.feeling()
    assert f.name == "begeistert" and f.reason == "endlich getroffen!"


def test_mood_fades_and_no_feelings_from_being_ignored():
    m = Mood()
    m.appraise({"type": "kick"})
    for _ in range(int(180 / 0.5)):        # drei Minuten lang passiert nichts
        m.update(0.5)
    f = m.feeling()
    assert f.name == "ausgeglichen" and f.valence > -0.05   # keine Traurigkeit wegen Ruhe


def test_text_appraisal():
    m = Mood()
    assert m.appraise_text("Ich bin heute so müde und gestresst") == "einfuehlsam" and m.empathic
    assert m.appraise_text("Super gemacht!") == "stolz"
    assert m.appraise_text("Juhu, geschafft!") in ("begeistert", None)


def test_engine_shows_feelings_but_never_steals_the_legs():
    async def go():
        sim, eng = await make()
        eng.run(B.TimedMove(B.Twist(0.1, 0, 0), 3.0))
        await run_for(sim, eng, 0.5)
        sim.emit("kick", item="Ball", message="Ball geschossen")
        assert eng.overlay is not None
        assert any(e["type"] == "gefuehl" for e in eng.events)
        await run_for(sim, eng, 0.5)
        assert eng.last_cmd.twist.vx > 0
        assert eng.describe()["gefuehl"]["name"] in ("begeistert", "fröhlich")
    run(go())


def test_no_expression_into_a_dance_and_respects_switch():
    async def go():
        sim, eng = await make()
        eng.run(B.Dance(duration=5))
        await run_for(sim, eng, 0.3)
        sim.emit("kick", item="Ball", message="Ball geschossen")
        assert eng.overlay is None                 # Tanz wird nicht überschrieben
        await eng.stop_all()
        eng.config.emotions = False
        eng._last_expression = -1e9
        sim.emit("kick", item="Ball", message="Ball geschossen")
        assert eng.overlay is None
    run(go())


def test_empathy_silences_goofy_and_fallback_is_kind():
    async def go():
        sim, eng = await make()
        eng.config.humor = 0.95
        brain = FallbackBrain(ToolRunner(eng))
        reply = await brain.handle("ich bin heute echt traurig")
        assert reply.actions == [] and "bei dir" in reply.text
        eng.hear("ich bin heute echt traurig")
        assert eng.mood.empathic
        eng._idle_for = 999
        await run_for(sim, eng, 3)
        assert not any(e["type"] == "goofy" for e in eng.events)
    run(go())


def test_personality_axes_shape_behaviour():
    async def go():
        sim, eng = await make()
        eng.config.humor, eng.config.energie = 0.2, 0.5
        assert not eng.config.goofy
        eng.config.humor = 0.55
        calm = eng.goofy_params()
        eng.config.humor, eng.config.energie = 1.0, 1.0
        wild = eng.goofy_params()
        assert eng.config.goofy and eng.config.goofy_level == "wild"
        assert wild["stumble"] > calm["stumble"] * 3 and wild["trotz"] > calm["trotz"] and wild["idle"] < calm["idle"]
        eng.config.energie = 0.0
        quiet = B.Choreography.from_spec(B.EMOTIONS["begeistert"], scale=eng.config.expressiveness)
        eng.config.energie = 1.0
        loud = B.Choreography.from_spec(B.EMOTIONS["begeistert"], scale=eng.config.expressiveness)
        assert abs(loud.kfs[1].head.head_pitch) > abs(quiet.kfs[1].head.head_pitch)
    run(go())


def test_settings_accept_axes_and_map_old_goofy_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    assert S.validate({"humor": 0.8, "energie": 0}) == {"humor": 0.8, "energie": 0.0}
    with pytest.raises(ValueError):
        S.validate({"humor": 1.5})
    with pytest.raises(ValueError):
        S.validate({"energie": True})
    assert S.validate({"goofy": True, "goofy_level": "wild"}) == {"humor": 0.95}
    assert S.validate({"goofy": False}) == {"humor": 0.25}


def test_claude_sees_feeling_and_temperament():
    async def go():
        sim, eng = await make()
        agent = DuckAgent(ToolRunner(eng), AgentConfig(api_key=None))
        eng.mood.appraise({"type": "kick"})
        assert '"gefuehl"' in agent._context("hallo")
        system = agent._system()
        assert "nicht aus Zuwendung" in system and "Temperament" in system
        eng.config.emotions = False
        assert "Gefühle:" not in agent._system()
    run(go())
