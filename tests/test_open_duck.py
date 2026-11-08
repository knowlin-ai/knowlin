"""Open Duck Mini (seit 0.38.4), Kopf zuerst, Figuren ohne Entenlaute und Raumklang der anderen Roboter."""

import asyncio
import json
import struct
from pathlib import Path

from fastapi.testclient import TestClient
from helpers import run_for
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.backends import build_backend
from duckpilot.backends.begleiter import Begleitente
from duckpilot.backends.open_duck import KEINE_POLLEN_SKILLS, OpenDuckSim
from duckpilot.config import load
from duckpilot.modell import open_duck as M
from duckpilot.motion.engine import MotionEngine
from duckpilot.motion.purzelbaum import Purzelbaum
from duckpilot.motion.schwarm import Schwarm
from duckpilot.server.app import Runtime, create_app

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def test_open_duck_backend_und_eigenschaften(tmp_settings):  # noqa: F811
    cfg = load()
    cfg.modul, cfg.backend = "open_duck_mini", "sim"
    be = build_backend(cfg)
    assert isinstance(be, OpenDuckSim)
    eig = be.eigenschaften()
    assert {"beine", "kopf", "antennen"} <= eig and not ({"schnabel", "tiefensensor"} & eig)
    assert be.skills() == ["sit_toggle", "kick_left", "kick_right"]      # Schuss nachgestellt seit 0.38.21
    r = asyncio.run(be.do("roulade"))
    assert not r.accepted and r.reason == KEINE_POLLEN_SKILLS
    assert "nachgestellt" in be.fassung("kick_left")["fassung"]
    st = be.state()
    assert st.koerper == "open_duck_mini" and len(st.antennen) == 2 and st.mouth == 0.0
    be._update_tof()
    assert be._tof == []                                        # kein Tiefensensor – mit Kamera geschätzte Tiefe (0.38.25)
    assert be.state().perception.source == ("kamera_tiefe" if "kamera" in be.extras else "sim")


def test_purzelbaum_fehlt_ehrlich():
    async def go():
        sim = OpenDuckSim(realtime=False, seed=1)
        sim._task = object()
        eng = MotionEngine(sim)
        await eng.stand_up()
        await run_for(sim, eng, 2.5)
        b = Purzelbaum()
        eng.run(b)
        await run_for(sim, eng, 1.0, until=lambda: b.done)
        return b
    b = asyncio.run(go())
    assert b.done and b.ergebnis_art == "abgelehnt" and "roulade" in b.result


def test_antennen_folgen_dem_sprechen():
    async def go():
        sim = OpenDuckSim(realtime=False, seed=2)
        sim._task = object()
        eng = MotionEngine(sim)
        await eng.stand_up()
        await run_for(sim, eng, 2.5)
        r = await sim.antennen_setzen(3.0, -3.0, 1.0)            # wird auf ±80° begrenzt
        await run_for(sim, eng, 0.8)
        return r, sim.state().antennen
    r, ant = asyncio.run(go())
    assert r.accepted and 1.2 < ant[0] <= 1.4 and -1.4 <= ant[1] < -1.2


def test_gebackenes_modell_passt_zur_umrechnung():
    b = (STATIC / "model" / "open_duck_mini.dpm").read_bytes()
    assert b[:4] == b"DPM2"
    head = json.loads(b[8:8 + struct.unpack("<I", b[4:8])[0]])
    assert head["art"] == "open_duck_mini" and head["licence"].startswith("Apache-2.0")
    assert head["joints"] == M.JOINT_NAMES and head["antennen"] == ["right_antenna", "left_antenna"]
    um = head["von_microduck"]
    assert len(um["stand"]) == len(um["ziel"]) == len(um["vorzeichen"]) == len(M.JOINT_NAMES)
    assert um["vorzeichen"] == M.VORZEICHEN and um["vorzeichen"][M.JOINT_NAMES.index("mouth")] == 0
    assert (STATIC / "model" / "LIZENZ-open-duck-mini.md").exists()
    glaeser = [t for t in head["parts"] if t["name"].startswith("head_glas")]
    assert len(glaeser) == 2 and all(t["finish"] == "glass" for t in glaeser)   # nicht in die Hülle schauen (0.38.5)


def test_loecher_findet_runde_durchbrueche():
    import numpy as np

    # Platte, 3 mm dick, mit rundem Loch (r = 6 mm); außen ein Quadrat (kein Kreis) – als Dreiecke wie aus einer STL
    seg, r, d = 32, 0.006, 0.003
    w = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    innen = [np.array([0.0, r * np.cos(x), r * np.sin(x)]) for x in w]
    aussen = [np.array([0.0, np.cos(x), np.sin(x)]) * 0.02 / max(abs(np.cos(x)), abs(np.sin(x))) for x in w]
    tris = []
    for x0, s in ((0.0, -1), (d, 1)):                            # Rückseite (Normale −x) und Vorderseite (+x)
        o = np.array([x0, 0, 0])
        for k in range(seg):
            a, b = innen[k] + o, innen[(k + 1) % seg] + o
            c, e = aussen[k] + o, aussen[(k + 1) % seg] + o
            q = [[a, c, e], [a, e, b]]
            tris += q if s > 0 else [[t[0], t[2], t[1]] for t in q]
    found = M.loecher(np.array(tris))
    vorn = [f for f in found if f["normale"][0] > 0.99]
    assert len(vorn) == 1 and abs(vorn[0]["r"] - r) < 1e-4 and abs(vorn[0]["dicke"] - d) < 1e-6
    assert all(f["r"] < 0.01 for f in found)                     # der quadratische Rand ist kein Loch
    g = M.glas(vorn[0])
    assert g.shape[1:] == (3, 3) and g[:, :, 0].max() < d        # Glas sitzt zurückgesetzt in der Wand


def test_kopf_zuerst_und_figur_odi(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        assert rt.im_koerper is False
        assert not rt.backend.state().powered                   # niemand steht auf, solange Knowlin im Kopf ist
        assert rt.schwarm.enten == [] if getattr(rt, "schwarm", None) else True
        r = c.post("/api/settings", json={"modul": "open_duck_mini", "backend": "sim", "sim_physik": False}).json()
        assert r["ok"] and isinstance(rt.backend, OpenDuckSim)
        assert rt.config.duck_name == "Odi" and rt.config.wake_word == "odi"
        assert not rt.backend.state().powered                   # auch der Körperwechsel weckt nicht
        text = rt.agent._system()
        assert "Open Duck Mini" in text and "Quacki (Microduck)" in text
        gesagt = []

        async def sagt(t, *a, **k):
            gesagt.append(t)
        rt._duck_says = sagt
        asyncio.run(rt.koerper_betreten())
        assert rt.im_koerper and gesagt and "Odi" in gesagt[0]
        asyncio.run(rt.koerper_betreten())                      # zweimal betreten grüßt nicht zweimal
        assert len(gesagt) == 1


def test_reachy_quakt_nicht(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    assert rt._ohne_ente("*quak* Hallo!") == "*quak* Hallo!"    # Quacki ist eine Ente
    rt.config.modul = "reachy_mini"
    assert rt._ohne_ente("*quak* Hallo! Quak quak, wie geht's?") == "Hallo! wie geht's?"
    assert rt._ohne_ente("Quak!") == "Okay."


def test_laute_anderer_roboter_haben_einen_ort():
    """Raumklang (seit 0.38.4): jeder Laut einer anderen Figur sagt, wo sie steht – die Oberfläche hört ihn von dort."""
    async def go():
        from helpers import make
        sim, eng = await make()
        sw = Schwarm(sim, eng, lambda i, a, b, yaw: Begleitente(sim.world_model, i, a, b, yaw))
        sim.nach_schritt.append(sw.step)
        sw.anzahl(1)
        e = sw.enten[0]
        sw.reagiere(e.ente_name, "gruss", (sim.x, sim.y))
        return [ev for ev in eng.events if ev.get("type") == "sound"], e
    laute, e = asyncio.run(go())
    assert laute and all(isinstance(ev.get("x"), float) and isinstance(ev.get("y"), float) for ev in laute)
    assert abs(laute[-1]["x"] - e.x) < 0.01
    js = (STATIC / "voice.js").read_text(encoding="utf-8")
    assert "createPanner" in js and "HRTF" in js
