"""Selbst aufstehen nach dem Stopp-Fenster (Projektregel), Kollisionsmodus nur im Simulator, Spiel ist kein Ärger."""

import asyncio
import dataclasses
import time
from types import SimpleNamespace

from helpers import make, run_for


# ── Gemüt: Spiel ist kein Ärger ─────────────────────────────────────────
def test_play_falls_do_not_change_the_mood_memory_or_experience():
    from duckpilot.brain.tools import ToolRunner
    from duckpilot.erfahrung_service import ErfahrungService
    from duckpilot.motion.mood import Mood

    m = Mood()
    for _ in range(5):
        m.appraise({"type": "fall", "kollision": True, "message": "Umgefallen"})
        m.appraise({"type": "bump", "kollision": True, "what": "Ball"})
    assert m.frust == 0 and m.reason == ""
    m.update(15.0)
    assert m.feeling().name == "ausgeglichen"                         # der kurze Schreck ist schnell weg
    ernst = Mood()
    ernst.appraise({"type": "fall"})
    assert ernst.frust > 0                                             # ohne Kollisionsmodus wie bisher

    erlebt = []
    svc = ErfahrungService.__new__(ErfahrungService)
    svc.rt = SimpleNamespace(memory=object())
    svc.netz = SimpleNamespace(erleben=lambda *a, **k: erlebt.append(a))
    svc.on_event({"type": "fall", "kollision": True})
    assert erlebt == []
    svc.on_event({"type": "fall"})
    assert erlebt

    logged = []
    runner = ToolRunner.__new__(ToolRunner)
    runner.memory = SimpleNamespace(log_event=lambda *a: logged.append(a))
    runner._log_event({"type": "fall", "kollision": True, "message": "x"})
    assert logged == []


# ── Stopp-Fenster und Selbst-Aufstehen (Projektregel) ──────────────────
def test_she_stands_up_by_herself_after_the_stop_window():
    async def go():
        sim, eng = await make()
        eng.powering_until = 0
        sim._fall("Test")
        await run_for(sim, eng, 0.5)
        win = [e for e in eng.events if e["type"] == "stopp_fenster"]
        assert win and win[-1]["dauer"] == eng.config.recover_delay == 3.0
        assert sim.fallen                                              # im Fenster liegt sie noch
        stood = await run_for(sim, eng, 8, until=lambda: not sim.fallen)
        assert stood
        ends = [e["grund"] for e in eng.events if e["type"] == "stopp_fenster_ende"]
        assert ends and ends[0] == "steht auf"
    asyncio.run(go())


def test_stop_in_the_window_keeps_her_down():
    async def go():
        sim, eng = await make()
        eng.powering_until = 0
        sim._fall("Test")
        await run_for(sim, eng, 1.0)
        eng.estop_at = time.monotonic()                               # „Stopp“ per Sprache = Not-Aus
        await run_for(sim, eng, 12)
        assert sim.fallen
        ends = [e["grund"] for e in eng.events if e["type"] == "stopp_fenster_ende"]
        assert ends and "Stopp" in ends[0]
    asyncio.run(go())


def test_no_standing_up_after_estop_or_while_picked_up():
    async def go(prepare):
        sim, eng = await make()
        eng.powering_until = 0
        prepare(sim, eng)
        sim._fall("Test")
        await run_for(sim, eng, 10)
        return sim, eng

    def estop(sim, eng):
        eng.estop_at = time.monotonic()

    def picked(sim, eng):
        orig = sim.state
        sim.state = lambda: dataclasses.replace(orig(), picked_up=True)

    sim, eng = asyncio.run(go(estop))
    assert sim.fallen and not any(e["type"] == "stopp_fenster" for e in eng.events)
    sim, eng = asyncio.run(go(picked))
    assert sim.fallen
    assert any("hochgehoben" in str(e.get("message")) for e in eng.events if e["type"] == "reflex")


def test_collision_mode_is_simulator_only():
    from duckpilot.kollision_service import BRAUCHT_PHYSIK, NUR_SIM, KollisionService

    eng = SimpleNamespace(config=SimpleNamespace(auto_recover=True, recover_delay=3.0))
    robot = KollisionService(SimpleNamespace(config=SimpleNamespace(backend="robot"), backend=object(), engine=eng))
    assert robot.grund() == NUR_SIM
    res = asyncio.run(robot.tun("stoss", {"staerke": 1}))
    assert not res["ok"] and res["fehler"] == NUR_SIM
    simple = KollisionService(SimpleNamespace(config=SimpleNamespace(backend="sim"), backend=object(), engine=eng))
    assert simple.grund() == BRAUCHT_PHYSIK


def test_stop_window_is_a_setting_from_2_to_10_seconds(tmp_path, monkeypatch):
    """WCAG 2.2.1: die Zeit, „Stopp“ zu rufen, ist einstellbar – und die Nachricht nennt die echte Dauer."""
    import pytest

    from duckpilot import settings as S
    from duckpilot.motion.engine import EngineConfig

    assert S.validate({"stopp_fenster_s": 6})["stopp_fenster_s"] == 6.0
    for bad in (1, 11, "drei", True):
        with pytest.raises(ValueError):
            S.validate({"stopp_fenster_s": bad})
    cfg = EngineConfig()
    cfg.stopp_fenster_s = 6
    assert cfg.recover_delay == 6.0

    async def go():
        sim, eng = await make()
        eng.powering_until = 0
        eng.config.stopp_fenster_s = 5
        sim._fall("Test")
        await run_for(sim, eng, 4.0)
        assert sim.fallen                                         # nach 4 s liegt sie noch (Fenster 5 s)
        win = [e for e in eng.events if e["type"] == "stopp_fenster"]
        assert win[-1]["dauer"] == 5.0 and "5 s" in win[-1]["message"]
    asyncio.run(go())


def test_collision_routes_answer_without_physics(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json"), backend="sim"))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        st = c.get("/api/kollision").json()
        assert st["ok"] and st["verfuegbar"] is False and st["grund"]
        assert st["stopp_fenster_s"] == rt.engine.config.recover_delay
        r = c.post("/api/kollision/stoss", json={"seite": "links", "stufe": "kraeftig"},
                   headers={"Origin": "http://127.0.0.1:8765"})
        assert r.status_code == 400 and r.json()["fehler"]
