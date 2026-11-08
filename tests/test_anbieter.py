"""Andere KI-Modelle als Gehirn (0.35): OpenAI-kompatible Schnittstelle, Schlüssel im Tresor, Rückfall, nur am PC."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from duckpilot import remote as R
from duckpilot import settings as S
from duckpilot.brain import anbieter as A
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app


class Tresor:
    def __init__(self):
        self.d = {}

    def get_password(self, s, u):
        return self.d.get((s, u))

    def set_password(self, s, u, p):
        self.d[(s, u)] = p

    def delete_password(self, s, u):
        self.d.pop((s, u), None)


@pytest.fixture()
def rt(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tresor = Tresor()
    monkeypatch.setattr(S, "_keyring", lambda: tresor)
    return Runtime(load(memory_path=str(tmp_path / "mem.json")))


def _fake(monkeypatch, antworten, seen):
    """httpx gegen einen gespielten Anbieter tauschen."""
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-x"}, {"id": "models/gemini-y"}]})
        a = antworten.pop(0)
        return a if isinstance(a, httpx.Response) else httpx.Response(200, json=a)

    real = httpx.AsyncClient

    class Client(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **k)

    monkeypatch.setattr(httpx, "AsyncClient", Client)


def test_addresses_keys_and_settings():
    assert A.adresse("gemini") == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert A.adresse("lmstudio") == "http://127.0.0.1:1234/v1" and A.adresse("eigen", "https://x.example/v1/") == "https://x.example/v1"
    assert not A.braucht_schluessel("lmstudio") and A.braucht_schluessel("openai")
    assert S.validate({"anbieter_adresse": "http://192.168.1.20:1234/v1"})["anbieter_adresse"]
    assert S.validate({"anbieter_adresse": "https://llm.example.org/v1"})["anbieter_adresse"]
    with pytest.raises(ValueError):
        S.validate({"anbieter_adresse": "http://llm.example.org/v1"})        # Schlüssel nie unverschlüsselt ins Netz
    with pytest.raises(ValueError):
        S.validate({"anbieter": "irgendwas"})
    assert S.validate({"gehirn": "anbieter"})["gehirn"] == "anbieter"


def test_phone_can_neither_set_keys_nor_switch_the_brain():
    assert R.pc_only("POST", "/api/anbieter/schluessel") and R.pc_only("GET", "/api/anbieter")
    assert {"anbieter", "anbieter_modell", "anbieter_adresse", "gehirn"} <= R.PC_ONLY_SETTINGS


def test_other_model_moves_the_duck_through_the_same_tools(rt, monkeypatch):
    S.set_anbieter_key("openai", "sk-test-1234567890")
    rt.config.gehirn, rt.config.anbieter, rt.config.anbieter_modell = "anbieter", "openai", "gpt-x"
    rt.config.schnellbefehle = False
    rt._new_agent()
    seen = []
    _fake(monkeypatch, [
        {"choices": [{"message": {"content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "walk", "arguments": json.dumps({"distance_m": 0.3})}}]}}]},
        {"choices": [{"message": {"content": "Quak, ich laufe!"}}]},
    ], seen)
    reply = asyncio.run(rt.agent.handle("lauf ein Stück nach vorn"))
    assert reply.source == "anbieter" and reply.text == "Quak, ich laufe!"
    assert [a["tool"] for a in reply.actions] == ["walk"] and reply.actions[0]["result"].get("ok", True)
    body = json.loads(seen[0].content)
    assert seen[0].headers["authorization"] == "Bearer sk-test-1234567890"
    assert body["model"] == "gpt-x" and any(t["function"]["name"] == "stop" for t in body["tools"])
    tool_msg = json.loads(seen[1].content)["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"


def test_provider_failure_falls_back_to_simple_commands(rt, monkeypatch):
    S.set_anbieter_key("mistral", "sk-test-1234567890")
    rt.config.gehirn, rt.config.anbieter, rt.config.anbieter_modell = "anbieter", "mistral", "m"
    rt.config.schnellbefehle = False
    rt._new_agent()
    _fake(monkeypatch, [httpx.Response(401, json={"error": "nope"})], [])
    reply = asyncio.run(rt.agent.handle("tanz"))
    assert reply.source == "einfach" and "nicht erreichbar" in reply.text
    assert "abgelehnt" in (rt.agent.anbieter.last_error or "")


def test_stop_never_needs_the_model(rt, monkeypatch):
    S.set_anbieter_key("openai", "sk-test-1234567890")
    rt.config.gehirn, rt.config.anbieter_modell = "anbieter", "gpt-x"
    rt._new_agent()
    _fake(monkeypatch, [], [])                       # jede Anfrage an den Anbieter würde hier scheitern
    assert asyncio.run(rt.agent.handle("stopp")).source == "einfach"


def test_routes_key_status_and_model_list(rt, monkeypatch):
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        st = c.get("/api/anbieter").json()
        assert {a["id"] for a in st["anbieter"]} >= {"openai", "gemini", "mistral", "openrouter", "lmstudio", "eigen"}
        assert not next(a for a in st["anbieter"] if a["id"] == "gemini")["hat_schluessel"]
        assert c.post("/api/anbieter/schluessel", json={"anbieter": "gemini", "schluessel": "AIza-test-123456"}).json()["ok"]
        st = c.get("/api/anbieter").json()
        assert next(a for a in st["anbieter"] if a["id"] == "gemini")["hat_schluessel"]
        assert "AIza" not in json.dumps(st)                        # der Schlüssel selbst kommt nie zurück
        seen = []
        _fake(monkeypatch, [], seen)
        r = c.post("/api/anbieter/modelle", json={"anbieter": "gemini"}).json()
        assert r["ok"] and r["modelle"] == ["gemini-y", "gpt-x"]
        assert str(seen[-1].url).startswith("https://generativelanguage.googleapis.com/v1beta/openai/models")
        assert c.request("DELETE", "/api/anbieter/schluessel", json={"anbieter": "gemini"}).json()["ok"]
        assert S.get_anbieter_key("gemini") is None
