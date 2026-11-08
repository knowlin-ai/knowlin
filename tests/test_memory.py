"""Tests fürs Gedächtnis: Datei, Werkzeuge, einfache Befehle, Claude-Kontext."""

import asyncio
import json

from helpers import make, run_for

from duckpilot.brain.agent import AgentConfig, DuckAgent
from duckpilot.brain.fallback import FallbackBrain
from duckpilot.brain.memory import Memory, mentions
from duckpilot.brain.tools import MEMORY_TOOLS, TOOLS, ToolRunner

BOW = [
    {"t": 0, "kopf": {}},
    {"t": 0.6, "kopf": {"nicken": 35, "nacken": 20}, "koerper": {"kippen": 12, "hoehe_mm": -12}, "ton": "coo"},
    {"t": 1.4, "kopf": {}, "koerper": {}},
]


def run(coro):
    return asyncio.run(coro)


async def setup(tmp_path):
    sim, eng = await make()
    mem = Memory(tmp_path / "memory.json")
    return sim, eng, mem, ToolRunner(eng, mem)


def test_mentions_tolerates_endings():
    assert mentions("verbeug dich mal", "Verbeugung")
    assert mentions("geh in die Küche", "Küche")
    assert mentions("Lauf zum Kuschelplatz", "kuschelplatz")
    assert not mentions("dreh dich", "Verbeugung")


def test_memory_persists_and_survives_restart(tmp_path):
    path = tmp_path / "m.json"
    m = Memory(path)
    m.remember_trick("Verbeugung", BOW, 1, "höflich")
    m.remember_place("Küche", "sim", 1.0, -0.5, 0.3)
    m.remember_preference("Lauf lieber langsam")
    m.remember_preference("lauf lieber langsam")  # doppelt → einmal
    again = Memory(path)
    assert "Verbeugung" in again.data["tricks"]
    assert again.places_for("sim")["Küche"]["x"] == 1.0
    assert again.places_for("robotd") == {}
    assert len(again.data["vorlieben"]) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_broken_file_is_set_aside(tmp_path):
    path = tmp_path / "m.json"
    path.write_text("{kaputt", encoding="utf-8")
    m = Memory(path)
    assert m.error and m.data["tricks"] == {}
    assert any(p.name.startswith("m.kaputt-") for p in tmp_path.iterdir())


def test_forget_single_and_all(tmp_path):
    m = Memory(tmp_path / "m.json")
    m.remember_trick("Verbeugung", BOW)
    m.remember_place("Küche", "sim", 0, 0, 0)
    pid = m.remember_preference("Quak nicht so oft")
    assert m.forget("trick", "verbeugung") == "Verbeugung"
    assert m.forget("vorliebe", pid) == "Quak nicht so oft"
    m.log_event("Sturz", "gegen Regal")
    m.forget_all()
    assert m.data == Memory._empty()


def test_context_is_small_and_relevant(tmp_path):
    m = Memory(tmp_path / "m.json")
    for i in range(30):
        m.remember_trick(f"Trick {i}", BOW)
    m.remember_place("Küche", "sim", 2, 0, 0)
    m.remember_place("Sofa-Ecke", "sim", 0.1, 0.1, 0)
    m.remember_place("Flur", "robotd", 0, 0, 0)
    ctx = m.context("sim", "mach Trick 29", 0, 0)
    assert len(ctx["tricks"]) == 20 and ctx["tricks"][0] == "Trick 29"
    assert [o["name"] for o in ctx["orte"]] == ["Sofa-Ecke", "Küche"]  # nur dieser Körper, nächster zuerst


def test_remember_last_choreography_and_replay(tmp_path):
    async def go():
        sim, eng, mem, r = await setup(tmp_path)
        assert (await r.run("choreography", {"keyframes": BOW, "title": "spontan"}))["ok"]
        await run_for(sim, eng, 2.0)
        res = await r.run("remember", {"kind": "trick", "name": "Verbeugung"})
        assert res["ok"], res
        res = await r.run("do_trick", {"name": "verbeug"})
        assert res["ok"] and "Verbeugung" in res["gestartet"]
        assert await run_for(sim, eng, 4, until=lambda: not eng.busy())
        assert mem.data["tricks"]["Verbeugung"]["benutzt"] == 1
        bad = await r.run("do_trick", {"name": "Salto"})
        assert bad["ok"] is False and bad["vorhanden"] == ["Verbeugung"]
    run(go())


def test_place_round_trip(tmp_path):
    async def go():
        sim, eng, mem, r = await setup(tmp_path)
        sim.x, sim.y = 0.2, -0.9
        assert (await r.run("remember", {"kind": "ort", "name": "Küche"}))["ok"]
        sim.x, sim.y = -1.2, 0.3
        assert (await r.run("go_to_place", {"name": "küche"}))["ok"]
        await run_for(sim, eng, 30, until=lambda: not eng.busy())
        assert abs(sim.x - 0.2) < 0.1 and abs(sim.y + 0.9) < 0.1
    run(go())


def test_failures_land_in_protocol(tmp_path):
    async def go():
        sim, eng, mem, r = await setup(tmp_path)
        await r.run("skill", {"name": "gibtsnicht"})
        await run_for(sim, eng, 1.0)
        eng.note({"type": "fall", "message": "Umgefallen (gegen Regal gelaufen)"})
        kinds = [e["art"] for e in mem.data["protokoll"]]
        # seit 0.38.13 lehnt das Werkzeug eine Bewegung, die der Körper nicht hat, gleich ehrlich ab („Abgelehnt“)
        assert "Sturz" in kinds and "Abgelehnt" in kinds
    run(go())


def test_fallback_memory_commands(tmp_path):
    async def go():
        sim, eng, mem, r = await setup(tmp_path)
        brain = FallbackBrain(r)
        await brain.handle("zeig mir, wie du dich freust")
        await run_for(sim, eng, 2.5)
        reply = await brain.handle("Merk dir das als Jubel")
        assert "Gemerkt" in reply.text and "Jubel" in mem.data["tricks"]
        reply = await brain.handle("Jubel!")
        assert reply.actions[0]["tool"] == "do_trick"
        await run_for(sim, eng, 3)
        sim.x, sim.y = 1.0, -1.0
        await brain.handle("Das hier ist die Küche")
        assert "Küche" in mem.places_for("sim")
        sim.x, sim.y = -1.0, 0.2
        reply = await brain.handle("Geh in die Küche")
        assert reply.actions[0]["tool"] == "go_to_place"
        await brain.handle("Merk dir: lauf lieber langsam")
        assert mem.data["vorlieben"][0]["text"] == "lauf lieber langsam"
        reply = await brain.handle("Was hast du dir gemerkt?")
        assert "Jubel" in reply.text and "Küche" in reply.text
        reply = await brain.handle("Vergiss die Küche")
        assert "vergessen" in reply.text and "Küche" not in mem.places_for("sim")
        reply = await brain.handle("das ist mir egal")  # kein Ort!
        assert mem.places_for("sim") == {}
    run(go())


def test_agent_sends_memory_context_and_tools(tmp_path):
    async def go():
        sim, eng, mem, r = await setup(tmp_path)
        mem.remember_preference("Lauf lieber langsam")
        mem.remember_trick("Verbeugung", BOW)
        agent = DuckAgent(r, AgentConfig(api_key=None))
        calls = []

        class Messages:
            async def create(self, **kw):
                import anthropic

                calls.append(kw)
                return anthropic.types.Message.model_validate({
                    "id": "m", "type": "message", "role": "assistant", "model": "x",
                    "content": [{"type": "text", "text": "Gern."}], "stop_reason": "end_turn",
                    "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})

        class Client:
            messages = Messages()

        agent.client = Client()
        await agent.handle("mach die Verbeugung")
        text = calls[0]["messages"][0]["content"][0]["text"]
        assert "Lauf lieber langsam" in text and "Verbeugung" in text
        names = {t["name"] for t in calls[0]["tools"]}
        assert {"remember", "do_trick", "forget"} <= names
        assert "Gedächtnis" in calls[0]["system"][0]["text"]
        # ohne Gedächtnis: keine Gedächtnis-Werkzeuge
        assert len(ToolRunner(eng).tools()) == len(TOOLS) - len(MEMORY_TOOLS)
    run(go())
