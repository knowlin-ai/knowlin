"""Regression (0.52.1): Der Start wartete auf `import anthropic` – auf dem Laptop des Maintainers 40 bis 140 s.

Jetzt lädt das SDK im Hintergrund; erst ein Aufruf an Claude wartet darauf.
"""

import asyncio
import sys
import time
import types

from duckpilot.brain.claude_zugang import ClaudeZugang


def _langsames_sdk(monkeypatch, sekunden=0.6, aufrufe=None):
    """Ein `anthropic`, das beim Anlegen des Clients trödelt wie der Virenschutz beim ersten Import."""
    mod = types.ModuleType("anthropic")

    class Messages:
        async def create(self, **kw):
            (aufrufe if aufrufe is not None else []).append(kw)
            return {"ok": True, **kw}

    class AsyncAnthropic:
        def __init__(self, api_key):
            time.sleep(sekunden)
            self.api_key = api_key
            self.messages = Messages()

    mod.AsyncAnthropic = AsyncAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", mod)


def test_start_wartet_nicht_auf_das_sdk_aber_der_aufruf_schon(monkeypatch):
    aufrufe = []
    _langsames_sdk(monkeypatch, aufrufe=aufrufe)
    t0 = time.monotonic()
    zugang = ClaudeZugang("sk-test")
    assert time.monotonic() - t0 < 0.2 and not zugang.geladen        # der Start läuft sofort weiter
    res = asyncio.run(zugang.messages.create(model="m", max_tokens=5))
    assert res["model"] == "m" and aufrufe and zugang.geladen and zugang.fehler is None


def test_fehlendes_sdk_ergibt_eine_klare_meldung(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)               # import anthropic → ImportError
    zugang = ClaudeZugang("sk-test")

    async def go():
        try:
            await zugang.messages.create(model="m")
        except RuntimeError as exc:
            return str(exc)

    assert "anthropic" in asyncio.run(go())


def test_agent_legt_den_zugang_ohne_warten_an(monkeypatch, tmp_path):
    from helpers import make

    from duckpilot.brain.agent import AgentConfig, DuckAgent
    from duckpilot.brain.memory import Memory
    from duckpilot.brain.tools import ToolRunner

    _langsames_sdk(monkeypatch, sekunden=1.0)

    async def go():
        _sim, eng = await make()
        t0 = time.monotonic()
        agent = DuckAgent(ToolRunner(eng, Memory(tmp_path / "m.json")), AgentConfig(api_key="sk-test"))
        dauer = time.monotonic() - t0
        return agent, dauer

    agent, dauer = asyncio.run(go())
    assert dauer < 0.5 and isinstance(agent.client, ClaudeZugang)
