"""Schneller antworten und flüssiger zeichnen (0.46.2, Hinweis des Maintainers: „Die App läuft teilweise träge. Auch das
Sprechen ist super langsam“) – und keine Enten-Wörter mehr bei Robotern ohne Entengestalt („Enten-‚Rückstände‘“)."""

import asyncio
import json

from helpers import make

from duckpilot.brain.agent import AgentConfig, DuckAgent
from duckpilot.brain.local import KEEP_ALIVE, OPTIONEN
from duckpilot.brain.tools import ToolRunner
from duckpilot.server.oberflaeche import STATIC


def _agent_mit_ollama(antworten):
    async def go():
        sim, eng = await make()
        agent = DuckAgent(ToolRunner(eng), AgentConfig(lokal_modell="qwen3.5:9b"))
        gesendet = []
        it = iter(antworten)

        async def fake_post(path, body, timeout=180.0):
            gesendet.append(json.loads(json.dumps(body)))
            return next(it)
        agent.local._post = fake_post
        return agent, gesendet
    return asyncio.run(go())


def test_modell_bleibt_geladen_und_optionen_bleiben_gleich():
    async def go():
        sim, eng = await make()
        agent = DuckAgent(ToolRunner(eng), AgentConfig(lokal_modell="qwen3.5:9b"))
        gesendet = []
        antworten = iter([
            {"message": {"content": ""}, "load_duration": 4e9, "prompt_eval_count": 5000, "prompt_eval_duration": 6e9},
            {"message": {"content": "Hallo!"}, "prompt_eval_count": 30, "prompt_eval_duration": 2e8,
             "eval_count": 5, "eval_duration": 5e8},
        ])

        async def fake_post(path, body, timeout=180.0):
            gesendet.append(json.loads(json.dumps(body)))
            return next(antworten)
        agent.local._post = fake_post
        assert await agent.local.vorwaermen() is not None
        assert await agent.local.vorwaermen() == 0.0                 # gleicher Systemtext: nicht noch einmal
        reply = await agent.handle("Wie geht's?")
        assert reply.text == "Hallo!" and len(gesendet) == 2
        warm, echt = gesendet
        assert warm["keep_alive"] == echt["keep_alive"] == KEEP_ALIVE
        assert warm["options"]["num_predict"] == 1
        assert warm["options"]["num_ctx"] == echt["options"]["num_ctx"] == OPTIONEN["num_ctx"]   # kein Neuladen
        assert warm["messages"][0] == echt["messages"][0] and warm["tools"] == echt["tools"]     # gleicher Anfang
        assert agent.local.zeiten["lesen_token"] == 30 and agent.local.zeiten["schreiben_s"] == 0.5
    asyncio.run(go())


def test_vorwaermen_ohne_ollama_stoert_nicht():
    async def go():
        sim, eng = await make()
        agent = DuckAgent(ToolRunner(eng), AgentConfig(lokal_modell="qwen3.5:9b"))

        async def weg(path, body, timeout=180.0):
            raise OSError("Ollama läuft nicht")
        agent.local._post = weg
        assert await agent.local.vorwaermen() is None
        leer = DuckAgent(ToolRunner(eng), AgentConfig())
        assert await leer.local.vorwaermen() is None                   # kein Modell gewählt
    asyncio.run(go())


def test_3d_hoechstens_60_bilder_und_langsamer_beim_nachdenken():
    duck3d = (STATIC / "duck3d.js").read_text(encoding="utf-8")
    assert "this.bildabstand = 1000 / 60" in duck3d and "document.hidden" in duck3d
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "scene.bildabstand = on || scene.quality === 'sparsam' ? 33" in app        # sparsam (0.47): immer 30


def test_charaktere_ohne_ente_bei_anderen_robotern():
    js = (STATIC / "personality.js").read_text(encoding="utf-8")
    assert "'Chaos-Ente': 'Wirbelwind'" in js and "keine-ente" in js
    assert "lesbar(nameIn(this.namen" not in js or "lesbar(intern)" in js


def test_leistungsmodus_sparsam():
    """0.47: Darstellung „Sparsam“ – 30 Bilder/s, ohne Schatten und Verdeckung, Gehirn-Bild seltener, Body-Klasse."""
    d3 = (STATIC / "duck3d.js").read_text(encoding="utf-8")
    assert "this.bildabstand = sp ? 33" in d3 and "shadowMap.enabled = !sp" in d3
    assert 'value="sparsam"' in (STATIC / "index.html").read_text(encoding="utf-8")
    assert "'sparsam'" in (STATIC / "leistung.js").read_text(encoding="utf-8")
    assert "sparsam') ? 66 : 30" in (STATIC / "hirn.js").read_text(encoding="utf-8")


def test_zustand_nach_quittung():
    """0.47: Fenster quittieren jeden Zustand; der Server schickt den nächsten erst danach (spätestens nach 2 s) – sonst
    stauten sich bei langsamen Rechnern Zustände, und Laute und Antworten kamen bis zu 50 s zu spät."""
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "send({ type: 'state_ok' })" in app
    rt = (STATIC.parents[0] / "runtime.py").read_text(encoding="utf-8")
    assert 'getattr(ws, "state_quittiert", False) and tick - getattr(ws, "state_tick", 0) < 40' in rt
    vb = (STATIC.parents[0] / "routes" / "verbindung.py").read_text(encoding="utf-8")
    assert 'msg.get("type") == "state_ok"' in vb
