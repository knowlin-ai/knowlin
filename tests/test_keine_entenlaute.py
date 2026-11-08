"""Keine Entenlaute, wo keine Ente ist (Beobachtung aus dem Test 5.11.): Reachy quakte im Leerlauf, und bei Knowlin (ohne
Körper) schnatterte die Ente im Hintergrund weiter."""

import asyncio
from pathlib import Path

from helpers import run_for

from duckpilot.backends.reachy import ReachyMiniSim
from duckpilot.motion.behaviors import EMOTIONS
from duckpilot.motion.engine import MotionEngine
from duckpilot.motion.reachy_gesten import LEERLAUF
from duckpilot.motion.reachy_gesten import geste as reachy_geste

STATIC = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"


async def _reachy():
    sim = ReachyMiniSim(realtime=False, seed=3)
    sim._task = object()
    eng = MotionEngine(sim)
    await eng.stand_up()
    await run_for(sim, eng, 2.0)
    return sim, eng


def _laute(eng) -> list:
    return [e for e in eng.events if e.get("type") == "sound"]


def test_reachy_leerlauf_eigene_regung_ohne_laute():
    async def go():
        sim, eng = await _reachy()
        gezeigt = [eng.idle_gesture() for _ in range(6) if not await run_for(sim, eng, 2.5)]
        return eng, gezeigt

    eng, gezeigt = asyncio.run(go())
    gezeigt = [g for g in gezeigt if g]
    assert gezeigt and all(g in LEERLAUF and reachy_geste(g) for g in gezeigt)     # nie gähnen, Gefieder putzen …
    assert not _laute(eng)


def test_reachy_spielt_auch_aus_entengesten_keine_laute():
    async def go():
        sim, eng = await _reachy()
        geplaudert = []
        sim.sound = lambda tag: geplaudert.append(tag)                             # dürfte gar nicht gerufen werden
        assert any("klang" in kf for kf in EMOTIONS["freude"])                    # die Entengeste hat Aufnahmen
        assert eng.play_overlay(EMOTIONS["freude"], force=True)
        await run_for(sim, eng, 3.0)
        return eng, geplaudert

    eng, geplaudert = asyncio.run(go())
    assert not _laute(eng) and not geplaudert


def test_browser_spielt_bei_knowlin_und_reachy_keine_entenlaute():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    ereignisse = (STATIC / "ereignisse.js").read_text(encoding="utf-8")   # seit 0.38.17 eigenes Modul
    teil = ereignisse[ereignisse.index("if (ev.type === 'sound') {"):][:400]
    assert "keine-ente" in teil and "im-kopf" in teil
    assert "if (!imKopf || m.source === 'alltag') vorlesen(m);" in js                # Entenstimme nur im Körper
