"""Reachy Mini als zweites Modul (seit 0.38.1): Simulator-Körper, Werkzeuge ohne Beine, Gehirn, Daemon-Anbindung."""

import asyncio
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from helpers import run_for
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.api import Head, Twist, wrap_angle
from duckpilot.backends import build_backend
from duckpilot.backends.reachy import (
    KOERPER_GRAD,
    NICHT_OHNE_BEINE,
    ReachyMiniDaemon,
    ReachyMiniSim,
    kopf_ziel,
)
from duckpilot.backends.reachy_kinematik import geometrie
from duckpilot.brain.agent import AgentConfig, DuckAgent
from duckpilot.brain.tools import ToolRunner
from duckpilot.config import Config
from duckpilot.motion.apportieren import Apportieren
from duckpilot.motion.engine import MotionEngine
from duckpilot.motion.purzelbaum import Purzelbaum
from duckpilot.server.oberflaeche import seite, stil


def run(coro):
    return asyncio.run(coro)


async def make_reachy():
    sim = ReachyMiniSim(realtime=False, seed=1)
    sim._task = object()
    eng = MotionEngine(sim)
    await eng.stand_up()
    await run_for(sim, eng, 2.5)
    return sim, eng


def test_build_backend_waehlt_den_koerper():
    cfg = Config()
    cfg.modul = "reachy_mini"
    assert isinstance(build_backend(cfg), ReachyMiniSim)
    cfg.backend = "robotd"
    be = build_backend(cfg)
    assert isinstance(be, ReachyMiniDaemon) and be.adresse == "http://localhost:8000"


def test_steht_fest_dreht_nur_den_koerper_bis_zum_anschlag():
    async def go():
        sim, eng = await make_reachy()
        x0, y0 = sim.x, sim.y
        for _ in range(120):                     # 6 s volle Drehrate und Vorwärts – vorwärts geht nicht
            await sim.move(Twist(0.2, 0.0, 1.0))
            sim.step(0.05)
        return sim, x0, y0
    sim, x0, y0 = run(go())
    assert (sim.x, sim.y) == (x0, y0)
    assert abs(math.degrees(wrap_angle(sim.yaw - sim.yaw0))) <= KOERPER_GRAD + 0.5    # steht (0.38.10) zum Sofa gedreht
    st = sim.state()
    assert st.koerper == "reachy_mini" and len(st.antennen) == 2 and st.battery is None
    assert st.perception.tof_mm in (None, []) and not st.perception.points


def test_kopf_grenzen_und_antennen():
    z = kopf_ziel(Head(0.0, 1.1, 1.1, 0.35))
    assert abs(z["pitch"]) <= math.radians(40) and abs(z["yaw"]) <= math.radians(65) and abs(z["roll"]) <= math.radians(40)

    async def go():
        sim, eng = await make_reachy()
        r = await ToolRunner(eng).run("antennen", {"links_grad": 60, "rechts_grad": 60, "sekunden": 2})
        for _ in range(20):
            sim.step(0.05)
        return r, sim
    r, sim = run(go())
    assert r["ok"] and sim.antennen[0] < -0.8 and sim.antennen[1] > 0.8          # beide nach außen


def test_werkzeuge_ohne_beine():
    async def go():
        sim, eng = await make_reachy()
        runner = ToolRunner(eng)
        namen = {t["name"] for t in runner.tools()}
        walk = await runner.run("walk", {"distance_m": 0.3})
        turn = await runner.run("turn", {"degrees": 30})
        return namen, walk, turn
    namen, walk, turn = run(go())
    assert {"walk", "skill", "apportieren", "schiessen", "explore", "mir_folgen"}.isdisjoint(namen)
    assert {"turn", "head", "emote", "dance", "antennen", "choreography"} <= namen
    assert walk == {"ok": False, "fehler": NICHT_OHNE_BEINE}
    assert turn["ok"]


def test_faehigkeiten_lehnen_sauber_ab():
    async def go():
        sim, eng = await make_reachy()
        out = []
        for b in (Purzelbaum(), Apportieren("socke")):
            eng.run(b)
            await run_for(sim, eng, 0.5, until=lambda b=b: b.done)
            out.append(b)
        return out
    for b in run(go()):
        assert b.done and b.failed and "fehlt: beine" in b.result


def test_gehirn_weiss_welcher_koerper():
    async def go():
        sim, eng = await make_reachy()
        return DuckAgent(ToolRunner(eng), AgentConfig(api_key=None))._system()
    text = run(go())
    assert "Reachy Mini" in text and "KEINE Beine" in text and "Microduck: ein 25 cm" not in text


def test_schlafen_und_aufwachen():
    async def go():
        sim, eng = await make_reachy()
        await sim.rest()
        for _ in range(60):
            sim.step(0.05)
        schlaf = list(sim.antennen), sim.state().head.head_pitch
        await sim.init()
        for _ in range(80):
            sim.step(0.05)
        return schlaf, sim
    (ant, nicken), sim = run(go())
    assert abs(ant[0]) > 2.5 and abs(ant[1]) > 2.5 and nicken > 0.3        # eingeklappt, Kopf gesenkt
    assert sim.powered and abs(sim.antennen[1]) < 0.6


class _FakeDaemon(BaseHTTPRequestHandler):
    """Antwortet wie Pollens Daemon (geprüft gegen reachy-mini-daemon --mockup-sim 1.13)."""
    log: list = []

    def log_message(self, *a):
        pass

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state/full"):
            self._json({"control_mode": "enabled", "head_pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0.1, "yaw": 0.2},
                        "body_yaw": 0.3, "antennas_position": [-0.17, 0.17]})
        else:
            self._json({"state": "running"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"null") if n else None
        _FakeDaemon.log.append((self.path, body))
        self._json({"status": "ok"})


@pytest.fixture()
def daemon():
    srv = HTTPServer(("127.0.0.1", 0), _FakeDaemon)
    _FakeDaemon.log = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_daemon_backend_spricht_pollens_rest(daemon):
    async def go():
        be = ReachyMiniDaemon(daemon)
        await be.connect()
        await be.head(Head(0.0, 0.3, 0.4, 0.0))
        await be.move(Twist(0.0, 0.0, 0.5))
        await asyncio.sleep(0.4)
        st = be.state()
        r = await be.rest()
        await be.close()
        return st, r
    st, r = run(go())
    assert st.connected and st.koerper == "reachy_mini" and st.yaw == 0.3 and st.antennen == [-0.17, 0.17]
    ziele = [b for p, b in _FakeDaemon.log if p == "/api/move/set_target"]
    assert ziele and set(ziele[-1]) == {"target_head_pose", "target_antennas", "target_body_yaw"}
    # Ausdruck (Atmen) kommt dazu; Kopfdrehung geht in Pollens Welt (Körperdrehung + Kopf relativ)
    z = ziele[-1]
    # Mit Pollens Modell geht die Neigung durch; ohne (öffentliche Fassung vor dem Nachladen) nimmt die enge
    # Ersatzgrenze sie zurück – aber nie über das Ziel hinaus und nie in die Gegenrichtung
    if geometrie() is not None:
        assert z["target_head_pose"]["pitch"] == pytest.approx(0.3, abs=0.03)
    else:
        assert 0 < z["target_head_pose"]["pitch"] <= 0.33
    assert z["target_body_yaw"] > 0
    assert z["target_head_pose"]["yaw"] == pytest.approx(0.4 + z["target_body_yaw"], abs=0.02)
    assert st.kopf_lage["yaw"] == pytest.approx(0.2 - 0.3) and st.kopf_lage["koerper"] == 0.3
    assert r.accepted and ("/api/move/play/goto_sleep", None) in _FakeDaemon.log


def test_settings_reachy_adresse():
    from duckpilot import settings as S
    assert S.validate({"reachy_adresse": "http://reachy-mini.local:8000"})["reachy_adresse"] == "http://reachy-mini.local:8000"
    assert S.validate({"modul": "reachy_mini"})["modul"] == "reachy_mini"
    with pytest.raises(ValueError):
        S.validate({"reachy_adresse": "http://example.com:8000"})


def test_koerperwechsel_ueber_die_einstellungen(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    """Startseiten-Kachel „Öffnen“ und Körper-Menü schicken {modul: reachy_mini, backend: sim} – der Körper wechselt."""
    from fastapi.testclient import TestClient

    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        r = c.post("/api/settings", json={"modul": "reachy_mini", "backend": "sim", "sim_physik": False}).json()
        assert r["ok"] and isinstance(rt.backend, ReachyMiniSim) and rt.koerper() == "reachy_sim"
        ms = c.get("/api/module").json()["module"]
        assert next(m for m in ms if m["id"] == "reachy-mini")["aktiv"] and not ms[0]["aktiv"]
        st = rt.backend.state().to_dict()
        assert st["koerper"] == "reachy_mini" and set(st["kopf_lage"]) == {"x", "y", "z", "roll", "pitch", "yaw", "koerper"}
        c.post("/api/settings", json={"modul": "duckpilot"})
        assert not isinstance(rt.backend, ReachyMiniSim)


def test_oberflaeche_blendet_beine_aus():
    """Körpermodus (seit 0.38.4 für alle Körper gleich): Klassen nach Eigenschaft und Körper, nicht je Roboter verdrahtet."""
    from pathlib import Path
    static = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"
    html = seite()
    zeile = lambda knopf: next(z for z in html.splitlines() if knopf in z)          # noqa: E731
    assert "braucht-beine" in zeile('id="laser-btn"') and "braucht-beine" in zeile('id="follow-btn"')
    assert "braucht-beine" in zeile('id="ctl-btn"') and "nur-microduck" in zeile('id="kol-btn"')
    assert "braucht-tiefensensor" in zeile('data-tool="explore"')
    assert '<div class="quick nur-reachy"' in html and '<div class="quick braucht-beine"' in html
    assert 'data-koerper="reachy_sim"' in html and 'data-set="reachy_adresse"' in html and 'id="rail-lernen"' in html
    modul = (static / "modul.js").read_text(encoding="utf-8")
    assert "'tricks/team'" in modul and "'training'" in modul and "ohne-${e}" in modul
    css = stil()
    assert "body:not(.im-kopf).ohne-beine .braucht-beine" in css and "body:not(.koerper-reachy) .nur-reachy" in css
    assert "body.keine-ente .nur-ente" in css                     # Entensachen nur bei Enten (seit 0.38.6)
    d3 = (static / "duck3d.js").read_text(encoding="utf-8")
    assert "from './reachy3d.js'" in d3 and "'reachy_mini'" in d3 and "'open_duck_mini'" in d3


def test_verworfenes_ziel_wird_erneut_geschickt():
    """Abgleich mit Pollens Daemon (6.11.2026): Läuft dort eine eigene Bewegung, antwortet set_target mit
    {"status": "ignored", "reason": "move_running"}. Das Ziel darf dann nicht als gesendet gelten – sonst bliebe der
    Kopf nach dem Aufwachen stehen, bis sich das Ziel zufällig ändert."""
    gesendet = []

    async def go():
        be = ReachyMiniDaemon("http://127.0.0.1:9")
        be._wach = True
        antworten = iter([{"status": "ignored", "reason": "move_running"}, {"status": "ok"}])

        async def rufen(methode, pfad, body=None):
            if pfad == "/api/move/set_target":
                gesendet.append(body)
                return next(antworten)
            return {}
        be._rufen = rufen
        await be._senden()
        nach_verworfen = be._gesendet
        await be._senden()                     # gleiches Ziel – wird erneut geschickt, diesmal angenommen
        return nach_verworfen, be._gesendet
    nach_verworfen, danach = run(go())
    assert nach_verworfen is None and len(gesendet) == 2 and danach == gesendet[-1]
