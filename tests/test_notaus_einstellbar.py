"""Verhalten nach dem Not-Aus einstellbar (seit 0.38.13, Wunsch des Maintainers „sollte anpassbar sein. per default passt dein
Vorschlag“): Sperre nur länger als die Sicherheitsregel (120 s), nie kürzer; danach „weiter“ oder „still“, bis der Mensch
die Verkörperung anspricht."""

import asyncio
import time

import pytest
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import settings as S
from duckpilot.backends.sim import SimBackend
from duckpilot.config import Config, load
from duckpilot.motion.engine import ESTOP_HOLD_S, EngineConfig, MotionEngine
from duckpilot.server.app import Runtime


@pytest.fixture()
def rt(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return Runtime(load(memory_path=str(tmp_path / "mem.json")))


def test_standard_ist_der_bisherige_vorschlag():
    c = Config()
    assert c.notaus_sperre_s == 120 and c.notaus_danach == "weiter"
    eng = MotionEngine(SimBackend(realtime=False), EngineConfig())
    assert eng.sperre_s == ESTOP_HOLD_S == 120 and not eng.notaus_gesperrt()
    eng.notaus()
    assert eng.notaus_gesperrt() and not eng.still


def test_nie_kuerzer_als_die_sicherheitsregel():
    for zu_kurz in (0, 30, 60, 119):
        with pytest.raises(ValueError):
            S.validate({"notaus_sperre_s": zu_kurz})
    S.validate({"notaus_sperre_s": 300})
    eng = MotionEngine(SimBackend(realtime=False), EngineConfig(notaus_sperre_s=10))   # selbst wenn es jemand setzt
    assert eng.sperre_s == ESTOP_HOLD_S
    eng.estop_at = time.monotonic() - 100
    assert eng.notaus_gesperrt()


def test_laenger_sperren_gilt_ueberall(rt):
    asyncio.run(rt.apply_settings({"notaus_sperre_s": 300}))
    assert rt.engine.sperre_s == 300 and rt.alltag._sperre() == 300
    rt.engine.estop_at = time.monotonic() - 200                     # 200 s her: nach 120 s wäre sie frei
    assert rt.engine.notaus_gesperrt()
    assert "Sperre" in (rt.engine._recover_blocked(rt.backend.state()) or "")


def test_still_bis_angesprochen(rt):
    asyncio.run(rt.apply_settings({"notaus_danach": "still"}))
    asyncio.run(rt.chat("Stopp", "text"))
    assert rt.engine.still and rt.engine.notaus_gesperrt()
    rt.engine._char_for = 999.0
    rt.engine._character(rt.backend.state(), 0.05)
    assert rt.engine.overlay is None                                 # still: keine Geste im Leerlauf
    asyncio.run(rt.chat("Hallo", "text"))
    assert not rt.engine.still and rt.engine.notaus_gesperrt()       # angesprochen: wieder lebendig, Sperre bleibt


def test_weiter_bleibt_wie_bisher(rt):
    asyncio.run(rt.chat("Stopp", "text"))
    assert not rt.engine.still and rt.engine.notaus_gesperrt()
