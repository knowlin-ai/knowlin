"""duckpilot als MCP-Server: nur am PC, nur mit Schlüssel, nur eingeschaltet – und nur ausgewählte Werkzeuge."""

import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from duckpilot import mcp_server as M
from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app

PC = "http://127.0.0.1:8765"


@pytest.fixture()
def vault(monkeypatch):
    store = {}

    class FakeKeyring:
        def get_password(self, s, u): return store.get((s, u))
        def set_password(self, s, u, p): store[(s, u)] = p
        def delete_password(self, s, u): store.pop((s, u), None)

    monkeypatch.setattr(S, "_keyring", lambda: FakeKeyring())
    return store


@pytest.fixture()
def client(tmp_path, monkeypatch, vault):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url=PC) as c:
        c.runtime = rt
        yield c


def rpc(c, method, params=None, mid=1, token=None, **kw):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    headers.update(kw.pop("headers", {}))
    return c.post("/mcp", json={"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}},
                  headers=headers, **kw)


def test_off_by_default_and_needs_key(client):
    assert rpc(client, "initialize").status_code == 404                    # aus
    client.runtime.config.mcp = True
    assert rpc(client, "initialize").status_code == 401                    # kein Schlüssel
    assert rpc(client, "initialize", token="falsch").status_code == 401
    token = M.ensure_token()
    r = rpc(client, "initialize", {"protocolVersion": "2025-06-18"}, token=token)
    assert r.status_code == 200 and r.json()["result"]["protocolVersion"] == "2025-06-18"
    assert r.headers.get("mcp-session-id")
    assert r.json()["result"]["serverInfo"]["name"] == "duckpilot"


def test_tools_are_a_safe_subset_and_calls_move_the_duck(client):
    client.runtime.config.mcp = True
    token = M.ensure_token()
    names = {t["name"] for t in rpc(client, "tools/list", token=token).json()["result"]["tools"]}
    assert {"walk", "stop", "emote", "laser_folgen", "get_status"} <= names
    assert not names & {"remember", "forget", "alltag", "training_vorschlagen", "training_kostenlos", "set_goofy"}
    r = rpc(client, "tools/call", {"name": "emote", "arguments": {"emotion": "freude"}}, token=token).json()["result"]
    assert r["isError"] is False and "gestartet" in r["content"][0]["text"]
    r = rpc(client, "tools/call", {"name": "remember", "arguments": {"kind": "wissen", "text": "x"}}, token=token).json()
    assert r["result"]["isError"] is True
    assert any(e["type"] == "mcp" for e in client.runtime.engine.events)


def test_notifications_get_202_and_unknown_methods_an_error(client):
    client.runtime.config.mcp = True
    token = M.ensure_token()
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202
    assert rpc(client, "resources/list", token=token).json()["error"]["code"] == -32601
    assert rpc(client, "ping", token=token).json()["result"] == {}


def test_only_on_this_pc_and_not_from_foreign_pages(client):
    client.runtime.config.mcp = True
    token = M.ensure_token()
    evil = rpc(client, "initialize", token=token, headers={"Origin": "http://evil.example"})
    assert evil.status_code == 403                                         # DNS-Rebinding / fremde Webseite
    phone = TestClient(client.app, base_url="http://192.168.1.10:8766", client=("192.168.1.20", 5))
    assert rpc(phone, "initialize", token=token).status_code in (401, 403)  # nie vom Handy


def test_settings_page_info_and_new_key(client):
    h = {"Origin": PC}
    info = client.get("/api/mcp").json()
    assert info["adresse"].endswith("/mcp") and "duckpilot.mcp_bridge" in info["claude_desktop"]
    r = client.post("/api/mcp/schluessel", headers=h).json()
    assert r["ok"] and r["neuer_schluessel"].startswith("dp_") and r["neuer_schluessel"] in r["claude_code"]
    assert client.get("/api/mcp").json()["neuer_schluessel"] is None          # nur einmal sichtbar


def test_bridge_relays_lines_and_explains_when_duckpilot_is_off():
    from duckpilot import mcp_bridge as Br

    sent = []

    def post(body):
        sent.append(body)
        return 200, json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

    assert json.loads(Br.relay('{"jsonrpc":"2.0","id":1,"method":"ping"}', post)) == {
        "jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    assert Br.relay('{"jsonrpc":"2.0","method":"notifications/initialized"}', lambda b: (202, "")) is None

    def down(body):
        raise OSError("Verbindung abgelehnt")

    err = json.loads(Br.relay('{"jsonrpc":"2.0","id":7,"method":"tools/list"}', down))
    assert err["id"] == 7 and "duckpilot läuft nicht" in err["error"]["message"]


def test_bridge_module_starts():
    r = subprocess.run([sys.executable, "-m", "duckpilot.mcp_bridge", "--hilfe"], capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 0 and "MCP" in r.stdout
