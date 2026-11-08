"""Reachy Mini, Teil 2 (seit 0.38.2): Ausdruck im Gespräch, Pollens Aufnahmen, Nachladen von Modell und Bibliothek."""

import asyncio
import hashlib
import json
import math

import pytest
from helpers import run_for
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.backends import reachy as R
from duckpilot.backends.reachy import ReachyMiniSim
from duckpilot.backends.reachy_ausdruck import Aufnahme, Ausdruck, lage_aus_matrix
from duckpilot.brain.tools import ToolRunner
from duckpilot.modell import reachy as RM
from duckpilot.modell.reachy_bewegungen import ReachyBewegungen
from duckpilot.motion.engine import MotionEngine


def run(coro):
    return asyncio.run(coro)


def _matrix(roll=0.0, pitch=0.0, yaw=0.0, z=0.0):
    """Wie scipy: R = Rz(yaw)·Ry(pitch)·Rx(roll), als 4×4-Liste."""
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    return [[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, 0.0],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, 0.0],
            [-sp, cp * sr, cp * cr, z], [0, 0, 0, 1]]


def _aufnahme_json(n=11, dauer=1.0):
    return {"description": "fröhlich wippen", "time": [i * dauer / (n - 1) for i in range(n)],
            "set_target_data": [{"head": _matrix(pitch=0.3 * i / (n - 1), z=0.01), "antennas": [-1.0, 1.0],
                                 "body_yaw": 0.2} for i in range(n)]}


def test_lage_aus_matrix_wie_pollen():
    lage = lage_aus_matrix(_matrix(0.1, -0.2, 0.3, 0.02))
    assert lage["roll"] == pytest.approx(0.1) and lage["pitch"] == pytest.approx(-0.2) and lage["yaw"] == pytest.approx(0.3)
    assert lage["z"] == pytest.approx(0.02)


def test_aufnahme_abspielen_und_kopf_relativ_zum_koerper():
    a = Aufnahme.aus_json("cheerful1", _aufnahme_json(), "pollen-robotics/reachy-mini-emotions-library", "cheerful1.wav")
    assert a.dauer == pytest.approx(1.0) and a.beschreibung == "fröhlich wippen"
    lage, ant, koerper = a.bei(0.5)
    assert lage["pitch"] == pytest.approx(0.15) and ant == [-1.0, 1.0] and koerper == pytest.approx(0.2)
    assert lage["yaw"] == pytest.approx(-0.2)                  # Pollen: Welt – duckpilot: relativ zum Körper


def test_ausdruck_zuhoeren_denkt_sprechen_atmen():
    au = Ausdruck()
    ruhig = [au.schritt(0.05, 0.0)[0]["z"] for _ in range(100)]
    assert max(ruhig) - min(ruhig) > 0.003                      # atmet
    au.setze("zuhoeren", 2.0)
    zu, ant, _ = au.schritt(0.05, 0.0)
    assert zu["roll"] > 0.1 and ant is not None and abs(ant[0]) < 0.15     # Kopf geneigt, Antennen aufgestellt
    for _ in range(60):
        au.schritt(0.05, 0.0)
    assert au.zustand is None                                   # Zuhören läuft von selbst aus
    au.setze("denkt")
    assert au.schritt(0.05, 0.0)[0]["yaw"] > 0.1
    au.setze(None)
    still = [au.schritt(0.05, 0.0)[0]["pitch"] for _ in range(40)]
    sprechen = [au.schritt(0.05, 1.0)[0]["pitch"] for _ in range(40)]
    assert max(sprechen) - min(sprechen) > 2 * (max(still) - min(still))   # Kopf wippt beim Sprechen
    with pytest.raises(ValueError):
        au.setze("tanzt")


def test_sim_spielt_aufnahme_und_zeigt_gespraech():
    async def go():
        sim = ReachyMiniSim(realtime=False, seed=1)
        sim._task = object()
        eng = MotionEngine(sim)
        await eng.stand_up()
        await run_for(sim, eng, 2.5)
        eng.attention(3.0)
        sim.step(0.05)
        zuhoeren = sim.ausdruck.zustand, sim._zusatz["roll"]
        a = Aufnahme.aus_json("cheerful1", _aufnahme_json(21, 2.0), "ds")
        r = await sim.pollen_bewegung(a)
        for _ in range(20):
            sim.step(0.05)
        mitten = sim.state()
        await eng.stop_all("Test")
        return zuhoeren, r, mitten, sim
    zuhoeren, r, mitten, sim = run(go())
    assert zuhoeren[0] == "zuhoeren" and zuhoeren[1] > 0.1      # Engine meldet „hört zu“, der Kopf neigt sich
    assert r.accepted and mitten.antennen[0] < -0.5 and mitten.kopf_lage["koerper"] > 0.05
    assert not sim.ausdruck.spielt                              # Not-Aus bricht die Aufnahme ab


def test_bibliothek_aus_pollens_zwischenspeicher_und_von_hf(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    snap = tmp_path / "snap"
    (snap / "data").mkdir(parents=True)
    (snap / "data" / "cheerful1.json").write_text(json.dumps(_aufnahme_json()), encoding="utf-8")
    (snap / "data" / "cheerful1.wav").write_bytes(b"RIFF0000")
    geholt = []

    def fetch(url):
        geholt.append(url)
        if url.endswith("/api/datasets/pollen-robotics/reachy-mini-dances-library"):
            return json.dumps({"sha": "a" * 40, "siblings": [{"rfilename": "groovy.json"}, {"rfilename": "../boese.json"},
                                                            {"rfilename": "README.md"}]}).encode()
        if url.endswith("/groovy.json"):
            return json.dumps(_aufnahme_json()).encode()
        raise AssertionError(url)

    lib = ReachyBewegungen(tmp_path / "daten", fetch=fetch,
                           cache=lambda ds: snap if ds.endswith("emotions-library") else None)
    lib.ensure()
    namen = {x["name"]: x for x in lib.liste()}
    assert set(namen) == {"cheerful1", "groovy"} and namen["cheerful1"]["ton"] == "cheerful1.wav"
    assert namen["groovy"]["art"] == "taenze" and all("boese" not in u for u in geholt)
    assert lib.ton_pfad("emotionen", "cheerful1.wav") is not None and lib.ton_pfad("emotionen", "../x.wav") is None
    assert lib.status()["datensaetze"]["taenze"]["stand"] == "a" * 12


def test_werkzeug_pollen_bewegung():
    class Pollen:
        def liste(self):
            return [{"name": "cheerful1", "art": "emotionen"}, {"name": "groovy", "art": "taenze"}]

        async def spielen(self, name):
            return {"ok": name == "cheerful1"}

    async def go():
        sim = ReachyMiniSim(realtime=False, seed=1)
        sim._task = object()
        runner = ToolRunner(MotionEngine(sim))
        runner.pollen = Pollen()
        tool = next(t for t in runner.tools() if t["name"] == "pollen_bewegung")
        return tool, await runner.run("pollen_bewegung", {"name": "cheerful1"})
    tool, r = run(go())
    assert "Emotionen: cheerful1" in tool["description"] and "Tänze: groovy" in tool["description"] and r["ok"]


def test_modell_aus_pollens_paket_mit_pruefsumme(tmp_path, monkeypatch):
    monkeypatch.delenv("DUCKPILOT_OFFLINE", raising=False)
    paket = tmp_path / "paket"
    (paket / "assets").mkdir(parents=True)
    (paket / "reachy_mini.xml").write_bytes(b"<mujoco/>")
    (paket / "assets" / "kopf.stl").write_bytes(b"falsch")
    dateien = {"reachy_mini.xml": {"sha256": hashlib.sha256(b"<mujoco/>").hexdigest(), "bytes": 9},
               "assets/kopf.stl": {"sha256": hashlib.sha256(b"richtig").hexdigest(), "bytes": 7}}
    monkeypatch.setitem(RM.QUELLEN, "dateien", dateien)
    geholt = []
    store = RM.ReachyModellStore(tmp_path / "daten", fetch=lambda u: geholt.append(u) or b"richtig",
                                 packaged=False, paket=lambda: paket)
    assert store.view_path() is None and store.missing() is True
    store.holen()
    assert len(geholt) == 1 and geholt[0].startswith("https://media.githubusercontent.com/media/pollen-robotics/reachy_mini/")
    assert (store.src / "assets" / "kopf.stl").read_bytes() == b"richtig"     # falscher Stand im Paket → geladen
    store2 = RM.ReachyModellStore(tmp_path / "d2", fetch=lambda u: b"boese", packaged=False, paket=lambda: None)
    with pytest.raises(ValueError, match="Prüfsumme"):
        store2.holen()


def test_quellen_fester_stand_und_nicht_im_export():
    q = RM.QUELLEN
    assert len(q["commit"]) == 40 and q["stand"] == "v1.13.0" and "reachy_mini.xml" in q["dateien"]
    assert all(n.startswith("assets/") and n.endswith(".stl") for n in q["dateien"] if n != "reachy_mini.xml")
    from pathlib import Path
    export = (Path(__file__).resolve().parent.parent / "tools" / "export_public.py").read_text(encoding="utf-8")
    assert "duckpilot/server/static/model/reachy_mini.dpm" in export
    assert R.EIGENSCHAFTEN >= {"pollen_bewegungen", "antennen"}


def test_route_und_status(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        r = c.get("/api/reachy").json()
        assert r["ok"] and not r["aktiv"] and "modell" in r and "bewegungen" in r
        assert c.post("/api/reachy/bewegung", json={"name": "cheerful1"}).status_code == 400
        assert c.get("/api/reachy/ton/emotionen/..%2Fx.wav").status_code == 404
        r = c.get("/api/module").json()
        assert set(r["gemeinsam"]) >= {"wissen", "orte", "erlebnisse", "personen"}
        figuren = {m["id"]: m["figur"] for m in r["module"] if "figur" in m}
        assert figuren["duckpilot"]["aktiv"] and figuren["reachy-mini"]["name"] == "Reachy"


def test_schaut_nur_angelernte_personen_an(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    import numpy as np

    pytest.importorskip("PIL")                                  # Bilder lesen braucht Pillow (kommt mit den Augen)

    from duckpilot.augen import png_from_rgb
    from duckpilot.config import load
    from duckpilot.server.app import Runtime

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    bild = png_from_rgb(np.zeros((480, 640, 3), np.uint8))
    rt.engine.estop_at = -1e9
    rt._anschauen([{"name": "unbekannt", "box": [0, 100, 80, 80]}], bild)
    assert rt.engine.gaze.head is None                          # Unbekannte bleiben unbekannt – kein Hinschauen
    rt._anschauen([{"name": "Kim", "box": [0, 100, 80, 80]}], bild)
    assert rt.engine.gaze.head is not None and rt.engine.gaze.head.head_yaw > 0.3   # links im Bild → nach links


def test_export_laesst_arbeitsordner_von_helfern_weg():
    """Erster GitHub-Upload (0.38.13): Der Export nahm `.claude/worktrees` mit – dort liegen Kopien mit privaten Notizen."""
    import importlib.util
    from pathlib import Path

    pfad = Path(__file__).resolve().parent.parent / "tools" / "export_public.py"
    spec = importlib.util.spec_from_file_location("export_public", pfad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert ".claude" in mod.OHNE_ORDNER and ".git" in mod.OHNE_ORDNER
