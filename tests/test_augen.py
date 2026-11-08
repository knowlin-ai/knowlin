"""Augen der Ente: Bilder für Claude (nur in der Runde, in der es gebraucht wird), PNG ohne Pillow, Bilder aus dem
Fenster, und dass Bilder/Personen nur am PC verwaltet werden."""

import asyncio
import io

import pytest
from fastapi.testclient import TestClient
from helpers import make
from test_duckpilot import FakeMessages, _msg

from duckpilot import remote as R
from duckpilot import settings as S
from duckpilot.augen import Eyes, png_from_rgb, sniff
from duckpilot.brain.agent import AgentConfig, DuckAgent
from duckpilot.brain.tools import ToolRunner
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


def test_png_writer_roundtrip():
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    rgb = (np.arange(4 * 5 * 3) % 256).astype(np.uint8).reshape(4, 5, 3)
    data = png_from_rgb(rgb)
    assert sniff(data) == "image/png"
    back = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    assert (back == rgb).all()


def test_tool_image_goes_to_claude_once_and_never_to_the_log():
    async def go():
        sim, eng = await make()
        runner = ToolRunner(eng)
        orig = runner.run

        async def run(name, args):
            if name == "alltag":
                return {"ok": True, "aufgabe": "vorlesen", "_bild": Eyes.for_claude(b"\x89PNGxx", "image/png")}
            return await orig(name, args)

        runner.run = run
        agent = DuckAgent(runner, AgentConfig(api_key=None))
        class Snap(FakeMessages):
            async def create(self, **kw):
                import copy
                return await super().create(**copy.deepcopy(kw))      # Verlauf so festhalten, wie er geschickt wurde

        fake = Snap([
            _msg([{"type": "tool_use", "id": "tu_1", "name": "alltag", "input": {"aktion": "ansehen", "aufgabe": "vorlesen"}}],
                 "tool_use"),
            _msg([{"type": "text", "text": "Da steht: Milch kaufen."}], "end_turn"),
            _msg([{"type": "text", "text": "Gern."}], "end_turn"),
        ])

        class Client:
            messages = fake

        agent.client = Client()
        seen = []
        reply = await agent.handle("Lies mir den Zettel vor", notify=seen.append)
        assert reply.text == "Da steht: Milch kaufen."
        assert "_bild" not in seen[0]["result"] and "_bild" not in str(reply.actions)
        sent = fake.calls[1]["messages"][-1]["content"][0]["content"]
        assert sent[1]["type"] == "image" and sent[1]["source"]["media_type"] == "image/png"
        await agent.handle("Danke")
        later = fake.calls[2]["messages"]
        assert "image" not in str([m for m in later if m["role"] == "user"])       # altes Bild nicht mehr mitgeschickt
    asyncio.run(go())


def test_eyes_ask_the_pc_window_for_a_picture():
    class FakeWS:
        fern_geraet = None

    class RT:
        class config:
            backend = "sim"

        clients = {FakeWS()}

        class alltag:
            class planner:
                data = {"augen": "webcam"}

        async def broadcast_local(self, msg):
            assert msg == {"type": "augen_bitte", "quelle": "webcam"}
            asyncio.get_running_loop().call_later(0.05, eyes.receive, JPEG, "webcam")

        def camera_address(self):
            return None

    eyes = Eyes(RT())

    async def go():
        data, kind, quelle = await eyes.image(timeout=2)
        assert (data, kind, quelle) == (JPEG, "image/jpeg", "webcam")
        assert eyes.fresh()                        # gleich danach: kein neues Bild nötig
    asyncio.run(go())
    with pytest.raises(ValueError):
        eyes.receive(b"<html>", "webcam")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    app = create_app(rt)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        c.runtime, c.app = rt, app
        yield c


def test_seeing_needs_the_switch_and_claude(client):
    rt = client.runtime
    H = {"Origin": "http://127.0.0.1:8765"}
    r = client.post("/api/alltag/befehl", json={"aktion": "ansehen"}, headers=H).json()
    assert not r["ok"] and "Sehen" in r["fehler"]
    assert client.post("/api/alltag/optionen", json={"sehen": True, "augen": "webcam"}, headers=H).json()["ok"]
    assert rt.alltag.planner.data["sehen"] and rt.alltag.planner.data["augen"] == "webcam"
    r = client.post("/api/alltag/befehl", json={"aktion": "ansehen"}, headers=H).json()
    assert not r["ok"] and "Claude" in r["fehler"]                 # ohne Schlüssel kein Sehen
    assert client.post("/api/alltag/optionen", json={"augen": "fernglas"}, headers=H).status_code == 400
    r = client.post("/api/alltag/befehl", json={"aktion": "wer_ist_da"}, headers=H).json()
    assert not r["ok"] and "Personen" in r["fehler"]


def test_pictures_and_people_only_from_the_pc(client):
    rt, app = client.runtime, client.app
    assert client.post("/api/augen/bild?quelle=webcam", content=JPEG, headers={"Origin": "http://127.0.0.1:8765"}).json()["ok"]
    assert rt.eyes.fresh()[2] == "webcam"
    assert client.post("/api/augen/bild", content=b"nope", headers={"Origin": "http://127.0.0.1:8765"}).status_code == 400
    p = client.get("/api/personen").json()
    assert p["personen"] == [] and "verfuegbar" in p
    r = client.post("/api/personen/anlernen", json={"name": "Anna", "bilder": [], "einverstanden": False},
                    headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code == 400
    rt.remote.set_enabled(True)
    token = rt.remote.pair(rt.remote.new_code()["code"], "Handy", None)
    phone = TestClient(app, base_url="http://192.168.1.10:8766", client=("192.168.1.20", 5))
    phone.cookies.set(R.COOKIE, token)
    O = {"Origin": "http://192.168.1.10:8766"}
    for method, path in (("get", "/api/personen"), ("post", "/api/personen/anlernen"), ("delete", "/api/personen"),
                         ("post", "/api/augen/bild")):
        kw = {"headers": O, **({"json": {}} if method == "post" else {})}
        assert getattr(phone, method)(path, **kw).status_code == 403, path
    rt.remote.set_enabled(False)
