"""Verbindungstest vor dem ersten Start am echten Roboter (seit 0.38.16): nur lesend, klare Befunde, nur am PC."""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fastapi.testclient import TestClient
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import remote as R
from duckpilot import verbindungstest as V
from duckpilot.backends.fake_robotd import start_server
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app


def _stand(ergebnis):
    return {s["was"]: s["stand"] for s in ergebnis["schritte"]}


def _microduck(port, akku=None):
    async def go():
        server, fake = await start_server(f"tcp:127.0.0.1:{port}")
        if akku is not None:
            fake.sim.battery = akku
        gerufen = []
        original = fake.dispatch

        async def merken(method, p):
            gerufen.append(method)
            return await original(method, p)

        fake.dispatch = merken
        try:
            return await V.pruefe_microduck(f"tcp:127.0.0.1:{port}"), gerufen
        finally:
            server.close()
            await server.wait_closed()
    return asyncio.run(go())


def test_microduck_erreichbar_mit_version_und_akku_ohne_bewegung():
    erg, gerufen = _microduck(7951)
    assert erg["ok"] and _stand(erg) == {"Adresse": "ok", "Erreichbar": "ok", "Version": "ok", "Akku": "ok"}
    assert erg["api_version"] == V.API_VERSION
    assert set(gerufen) == {"hello", "robot.health"}          # nur lesen – nichts bewegt sich


def test_microduck_schwacher_akku_ist_ein_hinweis():
    erg, _ = _microduck(7952, akku=0.1)
    assert erg["ok"] and _stand(erg)["Akku"] == "hinweis" and "laden" in erg["schritte"][-1]["text"]


def test_microduck_nicht_erreichbar_und_falsche_adresse():
    erg = asyncio.run(V.pruefe_microduck("tcp:127.0.0.1:7959", warten=1.0))
    assert not erg["ok"] and _stand(erg)["Erreichbar"] == "fehler" and "Tunnel" in erg["schritte"][-1]["text"]
    assert erg["schritte"][-1]["text"].startswith("Verbindung abgelehnt")
    erg = asyncio.run(V.pruefe_microduck("irgendwas"))
    assert not erg["ok"] and _stand(erg) == {"Adresse": "fehler"}


def test_reachy_daemon_nur_lesend():
    methoden = []

    class Daemon(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            methoden.append(("GET", self.path))
            daten = {"/api/daemon/status": {"state": "running", "version": "1.2.3"},
                     "/api/state/full": {"head_pose": {}}}.get(self.path)
            self.send_response(200 if daten is not None else 404)
            self.end_headers()
            self.wfile.write(json.dumps(daten).encode())

        def do_POST(self):  # noqa: N802
            methoden.append(("POST", self.path))
            self.send_response(500)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Daemon)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        erg = asyncio.run(V.pruefe_reachy(f"http://127.0.0.1:{srv.server_port}/"))
    finally:
        srv.shutdown()
    assert erg["ok"] and erg["dienst"] == "1.2.3"
    assert _stand(erg) == {"Adresse": "ok", "Erreichbar": "ok", "Version": "ok", "Kopf": "ok"}
    assert all(m == "GET" for m, _ in methoden)


def test_reachy_adresse_muss_http_sein_und_open_duck_noch_nicht():
    assert _stand(asyncio.run(V.pruefe_reachy("file:///etc/passwd"))) == {"Adresse": "fehler"}
    erg = asyncio.run(V.pruefen("open_duck_mini", "egal"))
    assert not erg["ok"] and "noch nicht unterstützt" in erg["schritte"][0]["text"]


def test_api_nur_am_pc(tmp_settings, vault, tmp_path):  # noqa: F811
    assert R.pc_only("POST", "/api/verbindungstest")
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        r = c.post("/api/verbindungstest", json={"koerper": "microduck", "adresse": "kaputt"}).json()
        assert r["ok"] is False and r["schritte"][0]["was"] == "Adresse"
        assert c.post("/api/verbindungstest", json={"koerper": "toaster"}).status_code == 400
