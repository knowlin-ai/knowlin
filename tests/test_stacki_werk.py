"""Stack-chan „wie ab Werk“ (0.39): Schau mich an, Tanz mit Licht, Avatare."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckpilot.api import DuckState
from duckpilot.backends.stackchan import AVATARE, FARBEN, TANZ_FARBEN, StackChanSim
from duckpilot.brain.fallback import parse
from duckpilot.brain.tools import ToolRunner
from duckpilot.modell import gesicht as G
from duckpilot.motion.engine import MotionEngine
from duckpilot.motion.schau import PITCH_HOCH, YAW_MAX, SchauHaltung
from duckpilot.server.routes.schau import blick_aus_bild

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def _laufen(sim: StackChanSim, s: float) -> None:
    for _ in range(int(s / 0.02)):
        sim.step(0.02)


def test_licht_und_lichttanz_und_not_aus_macht_dunkel():
    async def go():
        sim = StackChanSim(realtime=False)
        assert not sim.licht("rot").accepted                              # stromlos: kein Licht
        await sim.init()
        _laufen(sim, 3.0)
        assert sim.licht("rot", 1.0).accepted and sim.state().gesicht["led"] == "rot"
        assert not sim.licht("pink").accepted
        _laufen(sim, 1.5)
        assert sim.state().gesicht["led"] is None                          # Zeit um: wieder nach Zustand
        assert sim.lichttanz(4.0, 120).accepted
        farben = set()
        for _ in range(8):                                                 # 2 Schläge je Sekunde
            _laufen(sim, 0.5)
            farben.add(sim.state().gesicht["led"])
        assert len(farben) >= 4 and farben <= set(TANZ_FARBEN)
        sim.lichttanz(30.0)
        await sim.relax()                                                  # Not-Aus: dunkel und kein Weitertanzen
        assert sim.state().gesicht["led"] is None
        await sim.init()
        _laufen(sim, 3.0)
        assert sim.state().gesicht["led"] is None
        assert set(TANZ_FARBEN) <= set(FARBEN)
    asyncio.run(go())


def test_licht_werkzeug_tanzt_mit_kopf_und_einfache_saetze():
    async def go():
        sim = StackChanSim(realtime=False)
        eng = MotionEngine(sim)
        await sim.init()
        _laufen(sim, 3.0)
        eng.last_state = sim.state()
        runner = ToolRunner(eng)
        assert "licht" in {t["name"] for t in runner.tools()}
        r = await runner.run("licht", {"tanz": True, "sekunden": 6})
        assert r["ok"] and r["kopf"] and sim.state().gesicht["led"] in TANZ_FARBEN
        assert (await runner.run("licht", {"farbe": "blau"}))["ok"] and sim.state().gesicht["led"] == "blau"
        assert (await runner.run("licht", {"farbe": "aus"}))["ok"] and sim.state().gesicht["led"] is None
        assert not (await runner.run("licht", {"farbe": "pink"}))["ok"]
    asyncio.run(go())
    k = frozenset({"led", "kopf"})
    assert parse("Tanz mit Licht!", k) == [("licht", {"tanz": True, "sekunden": 12})]
    assert parse("mach dein Licht rot", k) == [("licht", {"farbe": "rot"})]
    assert parse("turn your lights green", k) == [("licht", {"farbe": "gruen"})]
    assert parse("Tanz mit Licht!", frozenset({"kopf"})) != [("licht", {"tanz": True, "sekunden": 12})]


def test_licht_nur_fuer_koerper_mit_leds():
    from duckpilot.backends.sim import SimBackend

    eng = MotionEngine(SimBackend(realtime=False))
    assert "licht" not in {t["name"] for t in ToolRunner(eng).tools()}


def test_schau_haltung_dreht_sanft_in_grenzen_und_endet_ohne_ziele():
    h = SchauHaltung(frist_s=2.0)
    h.setze(math.radians(170), math.radians(-80))
    st = DuckState()
    cmd = None
    for _ in range(50):
        cmd = h.tick(st, 0.02)
    assert cmd is not None and cmd.head is not None
    assert math.isclose(cmd.head.head_yaw, YAW_MAX, abs_tol=1e-6) and math.isclose(cmd.head.head_pitch, -PITCH_HOCH, abs_tol=1e-6)
    h2 = SchauHaltung(frist_s=1.0)
    h2.setze(math.radians(40), 0.0)
    erst = h2.tick(st, 0.02)
    assert erst is not None and erst.head.head_yaw < math.radians(5)        # kein Ruck
    for _ in range(60):
        h2.tick(st, 0.02)
    assert h2.done
    assert blick_aus_bild(0.5, 0.5) == (0.0, 0.0)
    yaw, pitch = blick_aus_bild(0.1, 0.2)
    assert yaw > 0 and pitch < 0                                           # links im Bild → links drehen, oben → hoch


def _fake_paket(tmp_path: Path, monkeypatch) -> bytes:
    """Ein kleines Paket mit denselben Dateinamen – Prüfsummen passend gesetzt."""
    buf = io.BytesIO()
    dateien = {}
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for i, name in enumerate(G.DATEIEN):
            inhalt = f"// {name} {i}".encode() if not name.endswith(".data") else b""
            info = tarfile.TarInfo(f"package/{name}")
            info.size = len(inhalt)
            tar.addfile(info, io.BytesIO(inhalt))
            dateien[name] = {"im_paket": f"package/{name}", "sha256": hashlib.sha256(inhalt).hexdigest(), "bytes": len(inhalt)}
    data = buf.getvalue()
    paket = {**G.PAKET, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "dateien": dateien}
    monkeypatch.setattr(G, "PAKET", paket)
    monkeypatch.setattr(G, "DATEIEN", dateien)
    monkeypatch.setattr(G, "offline", lambda: False)                     # die Tests laufen sonst offline
    return data


def test_gesichtserkennung_feste_quelle_und_pruefsummen(tmp_path, monkeypatch):
    q = json.loads((Path(G.__file__).parent / "gesicht_quellen.json").read_text(encoding="utf-8"))
    assert q["lizenz"] == "Apache-2.0" and q["laufzeit"]["url"].startswith("https://registry.npmjs.org/@mediapipe/face_detection/-/")
    assert all(len(m["sha256"]) == 64 for m in q["laufzeit"]["dateien"].values())
    assert "face_detection_short_range.tflite" in q["laufzeit"]["dateien"]
    data = _fake_paket(tmp_path, monkeypatch)
    kaputt = G.GesichtStore(tmp_path / "a", fetch=lambda *_: data[:-3] + b"xyz")
    with pytest.raises(ValueError):
        kaputt.ensure()
    assert not (tmp_path / "a" / "gesichtserkennung").exists()             # nichts gespeichert
    st = G.GesichtStore(tmp_path / "b", fetch=lambda *_: data)
    assert st.datei("face_detection.js") is None and not st.bereit()
    assert st.ensure()["geladen"] == ["paket"] and st.bereit()
    assert st.datei("face_detection.js") is not None and st.datei("../settings.json") is None
    p = st.dir / "face_detection.js"
    p.write_bytes(b"x" * p.stat().st_size)                                 # gleiche Größe, anderer Inhalt
    assert not st.bereit()
    assert G.medientyp("x.wasm") == "application/wasm" and G.medientyp("a.js") == "text/javascript"


@pytest.mark.filterwarnings("ignore:coroutine 'Runtime.broadcast' was never awaited")   # Sim hier von Hand getaktet
def test_schau_route_avatar_und_nur_am_pc(tmp_path, monkeypatch):
    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "s.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    data = _fake_paket(tmp_path, monkeypatch)
    cfg = load(memory_path=str(tmp_path / "m.json"))
    cfg.modul, cfg.avatar = "stackchan", "katze"
    rt = Runtime(cfg)
    assert rt.backend.koerper_art == "stackchan" and rt.backend.state().gesicht["avatar"] == "katze"
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        s = c.get("/api/schau").json()
        assert s["bereit"] is False and s["laeuft"] is False
        assert c.post("/api/schau/start").status_code == 409                # erst laden
        assert c.get("/api/schau/dateien/face_detection.js").status_code == 404
        assert c.get("/api/schau", headers={"X-Forwarded-For": "192.168.1.20"}).status_code in (401, 403)
        rt.gesicht.fetch = lambda *_: data
        rt.gesicht.ensure()
        assert c.get("/api/schau/dateien/face_detection.js").headers["content-type"].startswith("text/javascript")
        asyncio.run(rt.backend.init())
        for _ in range(150):
            rt.backend.step(0.02)
        r = c.post("/api/schau/start")
        assert r.status_code == 200, r.text
        b = c.post("/api/schau/blick", json={"x": 0.2, "y": 0.5, "gesicht": True}).json()
        assert b["ok"] and b["yaw"] > 0
        assert rt.backend.state().gesicht["ausdruck"] == "froh"            # freut sich, wenn er dich sieht
        rt.engine.notaus()                                                   # Not-Aus beendet das Schauen
        assert c.post("/api/schau/blick", json={"x": 0.5, "y": 0.5, "gesicht": True}).json()["ok"] is False
        assert c.post("/api/schau/start").status_code == 409
        r = c.post("/api/settings", json={"avatar": "pixel"})
        assert r.status_code == 200 and rt.backend.state().gesicht["avatar"] == "pixel"


def test_oberflaeche():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="schau-start"' in html and "/static/schau.js" in html and "/static/stacki_avatar.js" in html
    assert '"tanz":true' in html and 'id="aussehen-gesicht"' in html
    for a in AVATARE:
        assert f'value="{a}" data-set="avatar"' in html
    js = (STATIC / "schau.js").read_text(encoding="utf-8")
    assert "/api/schau/dateien/" in js and "https://" not in js and "googleapis" not in js
    gesichter = (STATIC / "stackchan_gesichter.js").read_text(encoding="utf-8")
    assert all(f"{a}," in gesichter or f"{a} }}" in gesichter for a in AVATARE[1:])
    s3d = (STATIC / "stackchan3d.js").read_text(encoding="utf-8")
    assert all(f"{f}:" in s3d for f in FARBEN)
