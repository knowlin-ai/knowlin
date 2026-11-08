"""Tokenverbrauch: Cache-Marken, gekürzte Werkzeug-Ergebnisse, Zähler, Kurzbefehle ohne Claude."""

import asyncio
import json

from helpers import make
from test_duckpilot import FakeMessages, _msg

from duckpilot.brain.agent import AgentConfig, DuckAgent, clip, with_cache_mark
from duckpilot.brain.fallback import quick_command
from duckpilot.brain.tools import ToolRunner
from duckpilot.brain.usage import UsageMeter


def _agent(eng, script, **cfg):
    agent = DuckAgent(ToolRunner(eng), AgentConfig(api_key=None, **cfg))
    fake = FakeMessages(script)

    class Client:
        messages = fake

    agent.client = Client()
    return agent, fake


def test_cache_marks_tools_system_and_last_message_only_in_request():
    async def go():
        sim, eng = await make()
        agent, fake = _agent(eng, [
            _msg([{"type": "tool_use", "id": "tu_1", "name": "get_status", "input": {}}], "tool_use"),
            _msg([{"type": "text", "text": "Alles gut."}], "end_turn"),
        ])
        agent.usage = UsageMeter(None)
        await agent.handle("Wie geht es dir heute so, kleine Ente?")
        for call in fake.calls:
            assert call["tools"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
            assert all("cache_control" not in t for t in call["tools"][:-1])
            assert call["system"][0]["cache_control"]["ttl"] == "1h"
            marks = [b for m in call["messages"] for b in (m["content"] if isinstance(m["content"], list) else [])
                     if isinstance(b, dict) and "cache_control" in b]
            assert len(marks) == 1 and marks[0] is call["messages"][-1]["content"][-1]
        # der gespeicherte Verlauf bleibt ohne Marken
        assert "cache_control" not in json.dumps(agent.history)
        assert agent.usage.summary()["heute"]["anfragen"] == 2
    asyncio.run(go())


def test_with_cache_mark_handles_string_content_and_empty():
    assert with_cache_mark([]) == []
    h = [{"role": "user", "content": "hallo"}]
    out = with_cache_mark(h)
    assert out[0]["content"][0] == {"type": "text", "text": "hallo", "cache_control": {"type": "ephemeral"}}
    assert h[0]["content"] == "hallo"


def test_long_tool_results_are_clipped():
    assert clip("x" * 100, 200) == "x" * 100
    out = clip("y" * 5000, 2500)
    assert len(out) <= 2500 and "gekürzt, 5000 Zeichen" in out


def test_usage_meter_sums_and_persists(tmp_path):
    m = UsageMeter(tmp_path / "verbrauch.json")
    m.add({"input_tokens": 100, "cache_creation_input_tokens": 9000, "cache_read_input_tokens": 0, "output_tokens": 50})
    m.add({"input_tokens": 120, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 9000, "output_tokens": 40})
    m.local()
    m.save()
    again = UsageMeter(tmp_path / "verbrauch.json")
    s = again.summary()
    assert s["summe"]["anfragen"] == 2 and s["summe"]["ohne_claude"] == 1
    assert s["cache_anteil"] == round(9000 / 18220, 3)
    assert s["pro_anfrage"] == (18220 + 90) // 2


def test_quick_command_detection():
    for t in ("Setz dich!", "tanz", "dreh dich nach links", "steh auf", "schieß den Ball", "folge dem Laser"):
        assert quick_command(t), t
    for t in ("Kannst du tanzen?", "was siehst du", "tanz nicht", "Hallo", "wie spät ist es",
              "lauf vor und erzähl mir dann einen Witz", "merk dir das Sofa", "wenn der Ball da ist, schieß"):
        assert not quick_command(t), t


def test_quick_command_skips_claude_and_counts():
    async def go():
        sim, eng = await make()
        agent, fake = _agent(eng, [])
        agent.usage = UsageMeter(None)
        reply = await agent.handle("tanz")
        assert reply.source == "einfach" and not fake.calls
        assert agent.usage.summary()["heute"]["ohne_claude"] == 1
        agent.config.schnellbefehle = False
        fake.script += [_msg([{"type": "tool_use", "id": "tu_d", "name": "dance", "input": {"style": "party"}}], "tool_use"),
                        _msg([{"type": "text", "text": "Ich tanze!"}], "end_turn")]
        reply = await agent.handle("tanz")
        assert reply.source == "claude" and len(fake.calls) == 2
    asyncio.run(go())


# ── Verlauf heil halten (Fehler 400 „tool_use ohne tool_result“) ──────────
def test_truncated_tool_call_gets_results_and_conversation_continues():
    async def go():
        sim, eng = await make()
        cut = _msg([{"type": "tool_use", "id": "tu_cut", "name": "choreography", "input": {"keyframes": []}}], "max_tokens")
        kurz = _msg([{"type": "tool_use", "id": "tu_kurz", "name": "dance", "input": {"style": "party"}}], "tool_use")
        agent, fake = _agent(eng, [cut, kurz, _msg([{"type": "text", "text": "Kürzer: los geht's."}], "end_turn"),
                                   _msg([{"type": "text", "text": "Nochmal!"}], "end_turn")])
        reply = await agent.handle("Tanz einen langen irischen Steptanz für mich")
        assert reply.text == "Kürzer: los geht's."
        res = fake.calls[1]["messages"][-1]["content"][0]
        assert res["type"] == "tool_result" and res["tool_use_id"] == "tu_cut" and res["is_error"]
        await agent.handle("Und jetzt bitte noch einmal ganz genauso")     # darf keinen 400 auslösen
        assert len(fake.calls) == 4
    asyncio.run(go())


def test_broken_history_from_older_version_is_repaired():
    async def go():
        sim, eng = await make()
        agent, fake = _agent(eng, [_msg([{"type": "text", "text": "Klar."}], "end_turn")])
        agent.history = [
            {"role": "user", "content": [{"type": "text", "text": "tanz"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "tu_x", "name": "dance", "input": {}}]},
            {"role": "user", "content": [{"type": "text", "text": "? hab ich nicht gesehen"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Quak!"}]},
        ]
        await agent.handle("Wiederhole bitte den Tanz von eben")
        msgs = fake.calls[0]["messages"]
        assert msgs[2]["content"][0] == {"type": "tool_result", "tool_use_id": "tu_x", "is_error": True,
                                         "content": "nicht ausgeführt"}
    asyncio.run(go())


def test_wiederhole_is_not_fetch_and_repeats_last_choreography():
    from duckpilot.brain.fallback import parse

    assert parse("wiederhole den Steptanz") == [("_repeat", {})]
    assert parse("hol die Socke")[0][0] == "_pick"

    async def go():
        sim, eng = await make()
        agent, _ = _agent(eng, [])
        agent.client = None                                   # ohne Claude: einfache Steuerung
        r = await agent.handle("wiederhole den Steptanz")
        assert "nichts vorgeführt" in r.text
        await agent.runner.run("choreography", {"keyframes": [{"t": 0}, {"t": 0.4, "kopf": {"nicken": 10}}],
                                                "title": "Steptanz"})
        r = await agent.handle("wiederhole den Steptanz")
        assert [a["tool"] for a in r.actions] == ["choreography"]
    asyncio.run(go())


def test_dance_sings_with_quacks_not_siren():
    from duckpilot.motion import behaviors as B
    from duckpilot.voice.speech import tag_for

    assert tag_for("quaaak", "!") == "greet"
    assert '"ton": "wheee"' not in open(B.__file__, encoding="utf-8").read()

    async def go():
        from helpers import run_for
        sim, eng = await make()
        sounds = []
        orig = sim.sound

        async def spy(tag):
            sounds.append(tag)
            return await orig(tag)
        sim.sound = spy
        eng.run(B.Dance("party", 8))
        await run_for(sim, eng, 8)
        assert sounds and "wheee" not in sounds and set(sounds) <= {"greet", "chirp"}
    asyncio.run(go())


# ── Denkblöcke (thinking) und abgelehnter Verlauf ─────────────────────────
def test_old_thinking_blocks_are_dropped_current_ones_kept():
    async def go():
        sim, eng = await make()
        think = {"type": "thinking", "thinking": "Hm, ein Ball.", "signature": "sig-1"}
        agent, fake = _agent(eng, [
            _msg([think, {"type": "tool_use", "id": "tu_a", "name": "get_status", "input": {}}], "tool_use"),
            _msg([{"type": "text", "text": "Fertig."}], "end_turn"),
        ])
        agent.history = [
            {"role": "user", "content": [{"type": "text", "text": "Hallo"}]},
            {"role": "assistant", "content": [{"type": "thinking", "thinking": "alt", "signature": "sig-alt"},
                                              {"type": "text", "text": "Quak!"}]},
        ]
        await agent.handle("Wie weit ist der Ball von dir weg?")
        first, second = fake.calls
        assert "sig-alt" not in json.dumps(first["messages"])            # alte Runde: weg
        assert "sig-1" in json.dumps(second["messages"][-2])             # laufende Werkzeugschleife: bleibt
        assert first["system"][0]["text"] == second["system"][0]["text"]
    asyncio.run(go())


def test_rejected_history_is_cleaned_and_retried():
    class Rejected(Exception):
        status_code = 400

    async def go():
        sim, eng = await make()
        agent, fake = _agent(eng, [_msg([{"type": "text", "text": "Ich verstecke mich hinter dem Sofa."}], "end_turn")])
        real = fake.create
        calls = {"n": 0}

        async def flaky(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise Rejected("Invalid `signature` in `thinking` block")
            return await real(**kw)
        fake.create = flaky
        agent.history = [{"role": "user", "content": [{"type": "text", "text": "Hallo"}]},
                         {"role": "assistant", "content": [{"type": "text", "text": "Quak!"}]}]
        reply = await agent.handle("versteck dich bitte irgendwo im Wohnzimmer")
        assert reply.source == "claude" and "Sofa" in reply.text and calls["n"] == 2
        assert agent.last_error is None
    asyncio.run(go())


# ── Tricks mit Lauten ──────────────────────────────────────────────────────
def test_tricks_without_own_sound_get_duck_voices():
    from duckpilot.motion import behaviors as B
    from duckpilot.skills.talent import TalentShow

    async def go():
        from helpers import run_for
        sim, eng = await make()
        heard = []
        orig = sim.sound

        async def spy(tag):
            heard.append(tag)
            return await orig(tag)
        sim.sound = spy
        eng.run(B.SkillRun("roulade"))
        await run_for(sim, eng, 6, until=lambda: not eng.busy())
        assert heard and heard[0] == "chirp", heard
        heard.clear()
        eng.run(B.SkillRun("roulade", voice="panne"))
        await run_for(sim, eng, 6, until=lambda: not eng.busy())
        assert heard[:1] == ["alarm"]
        heard.clear()
        show = TalentShow({"keyframes": [{"t": 0.0, "sit": False, "head": [0, 0.2, 0, 0]}], "dauer": 5.0}, "Test")
        eng.run(show)
        await run_for(sim, eng, 6, until=lambda: not eng.busy())
        assert heard[0] == "greet" and len(heard) >= 3 and set(heard) <= {"greet", "chirp"}, heard
    asyncio.run(go())
