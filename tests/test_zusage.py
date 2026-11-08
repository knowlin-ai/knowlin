"""Zusagen einhalten (seit 0.37.14): Befund aus dem Test „mehrmals den Befehl für Purzelbaum gegeben, er hat immer nur
geantwortet, aber nicht ausgeführt“."""

import asyncio

from helpers import make
from test_duckpilot import FakeMessages, _msg

from duckpilot.brain import zusage
from duckpilot.brain.agent import AgentConfig, DuckAgent
from duckpilot.brain.tools import ToolRunner


def run(coro):
    return asyncio.run(coro)


def _agent(eng, script):
    agent = DuckAgent(ToolRunner(eng), AgentConfig(api_key=None, schnellbefehle=False))
    fake = FakeMessages(script)

    class Client:
        messages = fake

    agent.client = Client()
    return agent, fake


def test_verlangt_nur_eindeutige_befehle():
    assert zusage.verlangt("Mach bitte noch einmal den Purzelbaum") == [("skill", {"name": "roulade"})]
    assert zusage.verlangt("Ja, nicht nur reden, vorführen") == []
    assert zusage.verlangt("Kannst du einen Purzelbaum?") == []
    assert zusage.verlangt("mach keinen Purzelbaum") == []
    assert zusage.verlangt("lauf 30 cm vor") == []                       # Gehen zählt nicht als Vorführung
    assert zusage.verlangt("schieß den Ball zum Sofa")[0][0] == "schiessen"


def test_leere_ankuendigung():
    assert zusage.leere_ankuendigung("Hier kommt die neue Fassung. Ich rolle ab.", [])
    assert not zusage.leere_ankuendigung("Hier kommt die neue Fassung.", [{"tool": "skill"}])
    assert not zusage.leere_ankuendigung("Das geht gerade nicht, ich liege noch.", [])
    assert not zusage.leere_ankuendigung("Schön, dass es dir gefällt!", [])


def test_nur_text_wird_nachgefragt_und_dann_ausgefuehrt():
    """Modell antwortet zweimal nur mit Text → duckpilot fragt einmal nach und führt danach selbst aus."""
    async def go():
        sim, eng = await make()
        agent, fake = _agent(eng, [
            _msg([{"type": "text", "text": "Hier kommt die neue Fassung. Ich rolle ab und stehe wieder auf."}], "end_turn"),
            _msg([{"type": "text", "text": "Jetzt läuft es wirklich."}], "end_turn"),
        ])
        seen = []
        reply = await agent.handle("Mach den Purzelbaum nochmal", notify=seen.append)
        assert len(fake.calls) == 2                                      # genau eine Nachfrage
        nachfrage = fake.calls[1]["messages"][-1]["content"][0]["text"]
        assert nachfrage.startswith("[duckpilot]") and "roulade" in nachfrage
        assert [a["tool"] for a in reply.actions] == ["skill"]
        assert reply.actions[0]["input"]["name"] == "roulade"
        assert any(s.get("tool") == "skill" for s in seen)               # im Chat sichtbar
        assert "wirklich" in reply.text
    run(go())


def test_nachfrage_reicht_wenn_modell_dann_ausfuehrt():
    async def go():
        sim, eng = await make()
        agent, fake = _agent(eng, [
            _msg([{"type": "text", "text": "Ich mache den Purzelbaum!"}], "end_turn"),
            _msg([{"type": "tool_use", "id": "tu_1", "name": "skill", "input": {"name": "roulade"}}], "tool_use"),
            _msg([{"type": "text", "text": "Purzelbaum läuft."}], "end_turn"),
        ])
        reply = await agent.handle("Mach einen Purzelbaum für mich")
        assert len(fake.calls) == 3
        assert [a["tool"] for a in reply.actions] == ["skill"]           # nicht doppelt
        assert reply.text == "Purzelbaum läuft."
    run(go())


def test_choreografie_ist_kein_purzelbaum():
    """Nur eine Choreografie statt des Skills (Verlauf aus dem Test) zählt nicht als ausgeführt."""
    async def go():
        sim, eng = await make()
        kf = [{"t": 0.5, "head_pitch": 20}, {"t": 1.0, "head_pitch": 0}]
        agent, fake = _agent(eng, [
            _msg([{"type": "tool_use", "id": "tu_1", "name": "choreography",
                   "input": {"keyframes": kf, "title": "Schwung holen"}}], "tool_use"),
            _msg([{"type": "text", "text": "Ich hole Schwung und rolle ab."}], "end_turn"),
            _msg([{"type": "tool_use", "id": "tu_2", "name": "skill", "input": {"name": "roulade", "then": True}}],
                 "tool_use"),
            _msg([{"type": "text", "text": "Jetzt die Rolle."}], "end_turn"),
        ])
        reply = await agent.handle("Zeig mir den Purzelbaum")
        assert [a["tool"] for a in reply.actions] == ["choreography", "skill"]
    run(go())


def test_ehrliche_ablehnung_wird_respektiert():
    async def go():
        sim, eng = await make()
        agent, fake = _agent(eng, [
            _msg([{"type": "text", "text": "Ich mache gleich einen Purzelbaum."}], "end_turn"),
            _msg([{"type": "text", "text": "Das geht gerade nicht, ich muss erst aufstehen."}], "end_turn"),
        ])
        reply = await agent.handle("Mach einen Purzelbaum")
        assert reply.actions == []
        assert "geht gerade nicht" in reply.text
    run(go())


def test_frage_loest_nichts_aus():
    async def go():
        sim, eng = await make()
        agent, fake = _agent(eng, [
            _msg([{"type": "text", "text": "Ja, Purzelbäume kann ich! Sag einfach Bescheid."}], "end_turn"),
        ])
        reply = await agent.handle("Kannst du eigentlich einen Purzelbaum?")
        assert len(fake.calls) == 1 and reply.actions == []
    run(go())
