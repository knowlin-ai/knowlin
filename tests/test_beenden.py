"""Beenden wie bei Windows: ganz, im Hintergrund oder neu starten – nur am PC."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from duckpilot import remote as R
from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app

PC = {"Origin": "http://127.0.0.1:8765"}


@pytest.fixture()
def rt(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    r = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    r.config.app_mode = True
    r.exits = []
    r.on_idle_exit = lambda: r.exits.append(1)
    return r


def test_quit_choices(rt):
    app = create_app(rt)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        info = c.get("/api/beenden").json()
        assert info["kann"] and info["version"] and info["laeuft"] == []
        r = c.post("/api/beenden", json={"art": "hintergrund"}, headers=PC).json()
        assert r["ok"] and rt.keep_open and r["hintergrund"]
        assert rt.alltag.mode == "ruhe"                     # die Ente ruht, solange niemand schaut
        assert c.post("/api/beenden", json={"art": "quatsch"}, headers=PC).status_code == 400
        r = c.post("/api/beenden", json={"art": "neustart"}, headers=PC).json()
        assert r["ok"] and r["neustart"] and rt.restart
        import time
        time.sleep(0.8)
        assert rt.exits == [1]


def test_only_in_app_window_and_never_from_the_phone(rt):
    app = create_app(rt)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        rt.remote.set_enabled(True)
        token = rt.remote.pair(rt.remote.new_code()["code"], "Handy", None)
        phone = TestClient(app, base_url="http://192.168.1.10:8766", client=("192.168.1.20", 5))
        phone.cookies.set(R.COOKIE, token)
        assert phone.post("/api/beenden", json={"art": "ganz"}, headers={"Origin": "http://192.168.1.10:8766"}).status_code == 403
        rt.remote.set_enabled(False)
        rt.config.app_mode = False
        assert c.post("/api/beenden", json={"art": "ganz"}, headers=PC).status_code == 400
        assert rt.exits == []


def test_new_version_on_disk_is_offered(rt, monkeypatch):
    import duckpilot.server.runtime as A

    sent = []

    async def go():
        async def bl(msg):
            sent.append(msg)
        rt.broadcast_local = bl
        monkeypatch.setattr(A, "__version__", "0.0.1")      # „läuft noch die alte“
        real_sleep = asyncio.sleep
        monkeypatch.setattr(A.asyncio, "sleep", lambda s: real_sleep(0))
        task = asyncio.ensure_future(rt._watch_update())
        for _ in range(20):
            await real_sleep(0)
            if sent:
                break
        task.cancel()
    asyncio.run(go())
    assert sent and sent[0]["type"] == "beenden" and sent[0]["neu"] and sent[0]["neu"] != "0.0.1"


@pytest.mark.parametrize("keep", [True, False])
def test_background_choice_survives_closing_the_window(rt, keep):
    async def go():
        rt._had_client = True
        rt.keep_open = keep
        rt.clients = set()
        rt._empty_since = None
        task = asyncio.ensure_future(rt._watch_clients())
        await asyncio.sleep(1.5)
        task.cancel()
    asyncio.run(go())
    # mit „Im Hintergrund“ zählt die Uhr bis zum Beenden gar nicht erst los
    assert (rt._empty_since is None) == keep


def test_restart_keeps_the_start_options():
    import sys

    from duckpilot.__main__ import restart_command

    cmd = restart_command(["--port", "8771", "--app", "--hintergrund", "--memory", "x.json"])
    assert cmd[:3] == [sys.executable, "-m", "duckpilot"]
    assert cmd[3:] == ["--port", "8771", "--memory", "x.json", "--app", "--neustart"]


def test_restart_survives_a_cp1252_console():
    """Neustart unter Windows: Ausgabe ist eine Datei in cp1252 – die Startmeldung mit 🦆 darf nicht abstürzen."""
    import subprocess
    import sys

    code = ("import io, sys; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding='cp1252'); "
            "from duckpilot.__main__ import _safe_console; _safe_console(); print('  🦆 duckpilot'); "
            "sys.stdout.flush(); sys.__stdout__.write('ok')")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.endswith("ok"), r.stderr[-500:]
