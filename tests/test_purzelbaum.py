"""Purzelbaum mit Platzprüfung und Zurückdrehen, Fassung der Policy, eigene Policies bleiben (seit 0.37.14)."""

import asyncio
import json
import math

from helpers import make, run_for

from duckpilot.api import DuckState
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion.purzelbaum import PLATZ_M, Purzelbaum
from duckpilot.physics.policies import PolicyStore


def run(coro):
    return asyncio.run(coro)


def test_purzelbaum_im_freien_laeuft_und_meldet_fassung():
    async def go():
        sim, eng = await make()
        res = await ToolRunner(eng).run("skill", {"name": "roulade"})
        assert res["ok"] and "Purzelbaum" in res["gestartet"]
        assert "einfacher Simulator" in res["fassung"]
        b = eng.current
        assert isinstance(b, Purzelbaum)
        await run_for(sim, eng, 8, until=lambda: b.done)
        assert b.done and not getattr(b, "failed", False), b.result
        assert b.result.startswith("Purzelbaum gelandet")
    run(go())


def test_zu_eng_dreht_sie_sich_erst_zur_freien_seite():
    async def go():
        sim, eng = await make()
        st = sim.state()
        aw = eng.ausweicher
        for i in range(-3, 4):                       # Wand 25 cm voraus, quer
            x = st.x + 0.25 * math.cos(st.yaw) - i * 0.03 * math.sin(st.yaw)
            y = st.y + 0.25 * math.sin(st.yaw) + i * 0.03 * math.cos(st.yaw)
            aw._pts[(round(x / 0.03), round(y / 0.03))] = (aw.clock, x, y)
        b = Purzelbaum()
        b.engine = eng
        assert b.freiraum(st) < PLATZ_M
        eng.run(b)
        yaw0 = st.yaw
        await run_for(sim, eng, 10, until=lambda: b.phase == "rolle")
        assert b.phase == "rolle"
        gedreht = math.degrees(math.atan2(math.sin(sim.state().yaw - yaw0), math.cos(sim.state().yaw - yaw0)))
        assert abs(abs(gedreht) - 90) < 15 and b.gedreht_vorher in (90.0, -90.0)
    run(go())


def test_nirgends_platz_lehnt_ehrlich_ab():
    async def go():
        sim, eng = await make()
        st = sim.state()
        aw = eng.ausweicher
        for k in range(36):                          # Ring 25 cm rundum
            w = math.radians(k * 10)
            x, y = st.x + 0.25 * math.cos(w), st.y + 0.25 * math.sin(w)
            aw._pts[(round(x / 0.03), round(y / 0.03))] = (aw.clock, x, y)
        b = Purzelbaum()
        eng.run(b)
        await run_for(sim, eng, 1, until=lambda: b.done)
        assert b.done and b.failed and "Zu wenig Platz" in b.result
    run(go())


def test_verdreht_gelandet_dreht_zurueck():
    b = Purzelbaum()
    b.yaw0, b.start = 0.0, (0.0, 0.0)
    st = DuckState(connected=True, x=0.3, y=0.05, yaw=math.radians(40))
    b._nachher(st)
    assert b.phase == "zurueck" and b.ergebnis["zurueckgedreht"] and b.ergebnis["verdreht_grad"] == 40
    assert math.isclose(math.degrees(b.inner.angle), -40, abs_tol=0.5)
    st2 = DuckState(connected=True, x=0.3, y=0.0, yaw=math.radians(10))
    b2 = Purzelbaum()
    b2._nachher(st2)
    assert b2.done and not b2.ergebnis["zurueckgedreht"]


def test_eigene_policy_bleibt_gemerkt(tmp_path):
    store = PolicyStore(tmp_path)
    onnx = tmp_path / "x.onnx"
    onnx.write_bytes(b"0")
    store.merke_eigen(str(onnx), "eigen_purzelbaum", "trick", "Mjlab-Roulade-Flat-MicroDuck")
    store.merke_eigen(str(onnx), "eigen_purzelbaum", "trick", "Mjlab-Roulade-Flat-MicroDuck")   # doppelt: einmal
    assert [e["name"] for e in PolicyStore(tmp_path).eigene()] == ["eigen_purzelbaum"]
    (tmp_path / "policies" / "eigene.json").write_text(json.dumps([{"name": "../böse", "pfad": str(onnx)}]))
    assert PolicyStore(tmp_path).eigene() == []      # Fremdtext: Namen werden geprüft
    onnx.unlink()
    store.merke_eigen(str(tmp_path / "weg.onnx"), "eigen_x", "trick")
    assert PolicyStore(tmp_path).eigene() == []      # Datei weg: nicht laden


def test_training_auswerten_ohne_lauf_sagt_es_ehrlich():
    async def go():
        sim, eng = await make()
        runner = ToolRunner(eng)

        class Trainer:
            def runs(self):
                return []

        runner.trainer = Trainer()
        res = await runner.run("training_auswerten", {})
        assert res["ok"] is False and "keinen Lauf" in res["fehler"]
    run(go())
