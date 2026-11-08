"""Mehrere Enten im Simulator (0.36.3): eigene Position und Verhalten, Begegnungen, folgen, tanzen, Not-Aus."""

import asyncio
import math
import time

import pytest
from fastapi.testclient import TestClient

from duckpilot.backends.begleiter import Begleitente, stimme_aus_kennung
from duckpilot.brain.tools import ToolRunner
from duckpilot.config import load
from duckpilot.motion.schwarm import KOERPER_M, PLAETZE, Schwarm
from duckpilot.motion.tanz import MusikTanz
from duckpilot.server.app import Runtime, create_app
from tests.helpers import make, run_for


async def schwarm(n=3, seed=1):
    sim, eng = await make(zufall=seed)
    sw = Schwarm(sim, eng, lambda i, x, y, yaw: Begleitente(sim.world_model, i, x, y, yaw))
    sim.nach_schritt.append(sw.step)
    sw.anzahl(n)
    return sim, eng, sw


def test_each_duck_has_its_own_body_and_voice():
    async def go():
        sim, eng, sw = await schwarm(4)
        assert [e.ente_name for e in sw.enten] == ["Kiki", "Pip", "Lotte", "Bruno"]
        assert len({e.klang for e in sw.enten}) == 4 and stimme_aus_kennung("ente-1") == sw.enten[0].klang   # feste Stimme
        for e in sw.enten:                                   # frei und nicht in Möbeln
            assert sim.world_model.collide(e.x, e.y, 0.12) is None
        assert sw.anzahl(12) == 8 and sw.anzahl(2) == 2          # seit 0.38.24 bis zu acht Gäste (vorher vier)
    asyncio.run(go())


def test_ducks_roam_on_their_own_and_keep_their_distance():
    async def go():
        sim, eng, sw = await schwarm(3, seed=2)
        start = [(e.x, e.y, e.yaw) for e in sw.enten]
        naechster = 9.0
        for _ in range(30):
            await run_for(sim, eng, 1.0)
            pos = [(e.x, e.y) for e in sw.enten] + [(sim.x, sim.y)]
            naechster = min(naechster, min(math.dist(a, b) for i, a in enumerate(pos) for b in pos[i + 1:]))
        bewegt = [math.dist(s[:2], (e.x, e.y)) > 0.1 or abs(s[2] - e.yaw) > 0.3 for s, e in zip(start, sw.enten)]
        assert all(bewegt)                                  # jede geht ihren eigenen Weg – kein Klon
        assert len({round(e.yaw, 1) for e in sw.enten}) > 1 # und schaut in ihre eigene Richtung
        assert naechster > KOERPER_M * 0.95                 # Körper gehen nicht ineinander
        assert not any(e.fallen for e in sw.enten)
    asyncio.run(go())


def test_meeting_ducks_greet_with_their_own_voice():
    async def go():
        sim, eng, sw = await schwarm(1)
        laute = []
        sim.on_event(lambda ev: laute.append(ev) if ev["type"] in ("sound", "schwarm") else None)
        e = sw.enten[0]
        e.x, e.y = sim.x + 0.4, sim.y                        # direkt neben der Hauptente
        await run_for(sim, eng, 1.0)
        gruss = [ev for ev in laute if ev["type"] == "sound" and ev.get("ente") == "Kiki"]
        assert gruss and gruss[0]["klang"] == list(e.klang)
        assert any("begrüßt" in ev.get("message", "") for ev in laute)
        await run_for(sim, eng, 3.0)                         # höchstens einmal je Paar und Minute
        assert len([ev for ev in laute if ev.get("ente") == "Kiki"]) == 1
    asyncio.run(go())


def test_follow_dance_sit_and_emergency_stop():
    async def go():
        sim, eng, sw = await schwarm(2, seed=3)
        sw.setze_modus("folgen")
        await run_for(sim, eng, 25.0)
        for e in sw.enten:
            dx, dy = PLAETZE[e.nummer]
            c, s = math.cos(sim.yaw), math.sin(sim.yaw)
            assert math.dist((e.x, e.y), (sim.x + c * dx - s * dy, sim.y + s * dx + c * dy)) < 0.25
        # Tanzt die Hauptente, tanzen die anderen mit – an ihrem Platz, im selben Takt
        plaetze = [(e.x, e.y) for e in sw.enten]
        eng.run(MusikTanz({"bpm": 120, "start": 0.0, "dauer": 12.0, "schritte": [
            {"t": 0.0, "takte": 2, "art": "drehen"}, {"t": 4.0, "takte": 2, "art": "schritt"}]}, {}, "Test"))
        await run_for(sim, eng, 1.0)
        assert sw._takt() is not None and sw.uebersicht()[0]["tut"] == "tanzt mit"
        yaw0 = [e.yaw for e in sw.enten]
        await run_for(sim, eng, 2.0)
        assert all(abs(e.yaw - y) > 0.5 for e, y in zip(sw.enten, yaw0))          # sie drehen sich mit
        assert all(math.dist(p, (e.x, e.y)) < 0.15 for p, e in zip(plaetze, sw.enten))
        await eng.stop_all("Ende")
        sw.setze_modus("sitzen")
        await run_for(sim, eng, 3.0)
        assert all(e.sitting for e in sw.enten)
        sw.setze_modus("frei")
        eng.estop_at = time.monotonic()                     # Not-Aus gilt für alle
        await run_for(sim, eng, 4.0)
        vorher = [(e.x, e.y) for e in sw.enten]
        await run_for(sim, eng, 3.0)
        assert all(math.dist(v, (e.x, e.y)) < 0.01 for v, e in zip(vorher, sw.enten))
    asyncio.run(go())


def test_group_commands_by_voice_and_tool():
    async def go():
        sim, eng, sw = await schwarm(2)
        r = ToolRunner(eng)
        assert not (await r.run("enten", {"aktion": "status"}))["ok"]          # ohne Schwarm ehrlich „keine“
        r.schwarm = sw
        assert (await r.run("enten", {"aktion": "modus", "modus": "tanzen"}))["modus"] == "tanzen"
        from duckpilot.brain.fallback import FallbackBrain

        fb = FallbackBrain(r)
        assert (await fb.handle("alle mir nach")).text == "Alle mir nach!" and sw.modus == "folgen"
        await fb.handle("Alle hinsetzen")
        assert sw.modus == "sitzen"
    asyncio.run(go())


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        yield c, rt


def test_setting_and_routes(client):
    c, rt = client
    assert c.get("/api/enten").json() == {**c.get("/api/enten").json(), "verfuegbar": True, "anzahl": 0}
    assert c.post("/api/settings", json={"weitere_enten": 3}).json()["ok"]
    d = c.get("/api/enten").json()
    assert d["anzahl"] == 3 and [e["name"] for e in d["enten"]] == ["Kiki", "Pip", "Lotte"]
    assert c.post("/api/enten", json={"modus": "folgen"}).json()["modus"] == "folgen"
    assert c.post("/api/enten", json={"modus": "fliegen"}).status_code == 400
    assert c.post("/api/settings", json={"weitere_enten": 9}).json()["ok"] is False
