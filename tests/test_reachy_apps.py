"""Pollens Reachy-Mini-Apps aus Knowlin (seit 0.38.19): auflisten, starten, anhalten, nur aus dem Katalog installieren;
solange eine App läuft, schickt Knowlin keine Ziele; der Not-Aus hält sie an."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from test_gui import client, tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.backends.reachy import ReachyMiniDaemon
from duckpilot.backends.reachy_apps import PollenApps
from duckpilot.remote import PC_ONLY


def run(coro):
    return asyncio.run(coro)


KATALOG = [{"name": "hand_tracker", "source_kind": "hf_space", "description": "Folgt deiner Hand",
            "url": "https://huggingface.co/spaces/pollen-robotics/hand_tracker", "extra": {"likes": 12}},
           {"name": "radio", "source_kind": "hf_space", "description": "Tanzt zum Radio", "url": None, "extra": {"likes": 40}}]


class _Daemon(BaseHTTPRequestHandler):
    log: list = []
    laeuft: dict | None = None

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
        p = self.path
        if p.startswith("/api/state/full"):
            self._json({"control_mode": "enabled", "head_pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
                        "body_yaw": 0.0, "antennas_position": [-0.17, 0.17]})
        elif p == "/api/apps/current-app-status":
            self._json(_Daemon.laeuft)
        elif p == "/api/apps/list-available/installed":
            self._json([{"name": "hand_tracker", "source_kind": "installed", "description": "Folgt deiner Hand", "extra": {}}])
        elif p == "/api/apps/list-available/hf_space":
            self._json(KATALOG)
        elif p.startswith("/api/apps/job-status/"):
            self._json({"command": "install", "status": "in_progress", "logs": ["lade …", "pip install …"]})
        else:
            self._json({"state": "running"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"null") if n else None
        _Daemon.log.append((self.path, body))
        if self.path.startswith("/api/apps/start-app/"):
            _Daemon.laeuft = {"info": {"name": "hand_tracker", "source_kind": "installed"}, "state": "running", "error": None}
            self._json(_Daemon.laeuft)
        elif self.path == "/api/apps/stop-current-app":
            _Daemon.laeuft = None
            self._json(None)
        elif self.path == "/api/apps/install":
            self._json({"job_id": "j1"})
        else:
            self._json({"status": "ok"})


@pytest.fixture()
def daemon():
    srv = HTTPServer(("127.0.0.1", 0), _Daemon)
    _Daemon.log, _Daemon.laeuft = [], None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_apps_auflisten_starten_anhalten(daemon):
    async def go():
        be = ReachyMiniDaemon(daemon)
        apps = be.apps
        inst = await apps.installiert()
        kat = await apps.katalog()
        res = await apps.starten("hand_tracker")
        st = await apps.status()
        await apps.stoppen()
        return inst, kat, res, st, apps.aktiv
    inst, kat, res, st, aktiv = run(go())
    assert [a["name"] for a in inst] == ["hand_tracker"]
    assert [a["name"] for a in kat] == ["radio", "hand_tracker"]             # beliebteste zuerst
    assert res["zustand"] == "running" and st["name"] == "hand_tracker"
    assert ("/api/apps/start-app/hand_tracker", None) in _Daemon.log and aktiv is False


def test_installiert_nur_was_im_katalog_steht(daemon):
    async def go():
        apps = ReachyMiniDaemon(daemon).apps
        job = await apps.installieren("radio")
        with pytest.raises(ValueError):
            await apps.installieren("https://evil.example/space")
        return job, await apps.auftrag(job)
    job, auftrag = run(go())
    assert job == "j1" and auftrag["zustand"] == "in_progress"
    install = [b for p, b in _Daemon.log if p == "/api/apps/install"]
    assert install == [KATALOG[1]]                      # genau die Angaben aus Pollens Katalog, nichts anderes


def test_waehrend_app_keine_ziele_und_notaus_haelt_sie_an(daemon):
    async def go():
        be = ReachyMiniDaemon(daemon)
        await be.connect()
        await asyncio.sleep(0.3)
        await be.apps.starten("hand_tracker")
        await asyncio.sleep(0.3)
        n = len([1 for p, _ in _Daemon.log if p == "/api/move/set_target"])
        await asyncio.sleep(0.4)
        n2 = len([1 for p, _ in _Daemon.log if p == "/api/move/set_target"])
        r = await be.stop()
        await be.close()
        return n, n2, r
    n, n2, r = run(go())
    assert n2 == n                                       # App läuft → Knowlin funkt nicht dazwischen
    assert r.accepted and ("/api/apps/stop-current-app", None) in _Daemon.log


def test_alter_daemon_ohne_apps_stoert_nicht():
    async def rufen(m, p, b):
        return {"state": "running"}                      # kein „info“ → keine App
    apps = PollenApps(rufen)
    assert run(apps.status()) is None and apps.aktiv is False


def test_installieren_nur_am_pc():
    assert any(m == "POST" and p.match("/api/reachy/apps/installieren") for m, p in PC_ONLY)


def test_im_simulator_ehrlich_nicht_verfuegbar(client):  # noqa: F811
    o = {"Origin": "http://127.0.0.1:8765"}
    client.post("/api/settings", json={"modul": "reachy_mini", "backend": "sim", "sim_physik": False}, headers=o)
    r = client.get("/api/reachy/apps").json()
    assert r["verfuegbar"] is False and "echten Reachy" in r["fehler"]
    assert client.post("/api/reachy/apps/starten", json={"name": "x"}, headers=o).status_code == 400
