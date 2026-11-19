"""Fenster ohne Verbindung (seit 0.38.66) – Regressionstests zum Fund vom 19.11.

Nach dem Installieren blieb das Fenster bei „verbinde …“ / „getrennt“ stehen, ohne zu sagen, warum. Jetzt:
* scheitert das Start-Paket, bleibt die Verbindung offen und das Fenster bekommt den Grund,
* weist der Server ein Fenster ab, merkt er sich den Grund,
* /api/startdiagnose sagt beides auch ohne WebSocket,
* der Schleifenwächter meldet im Protokoll, wenn der Server hängt,
* der Startwächter im Fenster wählt den passenden Befund.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app
from duckpilot.server.startdiagnose import Schleifenwaechter, Startfehler

PC = {"Origin": "http://127.0.0.1:8765", "Host": "127.0.0.1:8765"}
WAECHTER = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "startwaechter.js"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    runtime = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(runtime), base_url="http://127.0.0.1:8765") as c:
        c.runtime = runtime
        yield c


def test_startfehler_kappt_die_verbindung_nicht_und_nennt_den_grund(client, monkeypatch):
    def kaputt():
        raise ValueError("settings.json: unerwarteter Wert")

    monkeypatch.setattr(client.runtime, "init_message", kaputt)
    with client.websocket_connect("/ws", headers=PC) as ws:
        arten = [json.loads(ws.receive_text())["type"] for _ in range(5)]
        assert "init" not in arten and arten[-1] == "startfehler"
        ws.send_text(json.dumps({"type": "stop"}))              # Verbindung lebt: der Not-Aus kommt noch an
    d = client.get("/api/startdiagnose").json()
    assert "ValueError" in d["startfehler"] and "unerwarteter Wert" in d["startfehler"]


def test_ohne_fehler_kein_startfehler(client):
    with client.websocket_connect("/ws", headers=PC) as ws:
        arten = [json.loads(ws.receive_text())["type"] for _ in range(5)]
    assert arten[:3] == ["init", "memory", "alltag"] and "startfehler" not in arten
    d = client.get("/api/startdiagnose").json()
    assert d["startfehler"] == "" and d["ablehnung"] == "" and d["haengt_seit"] == 0
    assert d["version"] and d["sprache"] in ("de", "en") and isinstance(d["warnungen"], list)
    assert "Users" not in json.dumps(d) and "home" not in json.dumps(d)       # kein Pfad mit Benutzernamen


def test_abgewiesene_herkunft_wird_gemerkt(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws", headers={"Origin": "http://localhost:9999", "Host": "127.0.0.1:8765"}) as ws:
            ws.receive_text()
    grund = client.get("/api/startdiagnose").json()["ablehnung"]
    assert "Herkunft" in grund and "localhost:9999" in grund


def test_weiterleiter_auf_dem_pc_wird_als_grund_genannt(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws", headers={**PC, "X-Forwarded-For": "127.0.0.1"}) as ws:
            ws.receive_text()
    assert "Proxy" in client.get("/api/startdiagnose").json()["ablehnung"]


def test_startfehler_kurz_und_loeschbar():
    f = Startfehler()
    assert f.merken(RuntimeError("x" * 1000)).startswith("RuntimeError: ") and len(f.text) <= 400
    f.loeschen()
    assert f.bericht(None) == {"startfehler": "", "ablehnung": "", "haengt_seit": 0.0}


def test_schleifenwaechter_meldet_haenger_mit_stelle(caplog):
    async def ablauf():
        w = Schleifenwaechter(asyncio.get_running_loop(), grenze=0.3, takt=0.05)
        w.start()
        await asyncio.sleep(0.2)
        time.sleep(0.8)                      # die Schleife hängt (blockierender Aufruf)
        await asyncio.sleep(0.3)
        w.stop()
        return w

    with caplog.at_level(logging.WARNING, logger="duckpilot.server.startdiagnose"):
        w = asyncio.run(ablauf())
    texte = "\n".join(r.getMessage() for r in caplog.records)
    assert "hängt seit" in texte and "time.sleep" in texte          # zeigt die Stelle, an der es hängt
    assert "antwortet wieder" in texte and w.laengste >= 0.3


def _node(code: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    vorspann = ("globalThis.window = globalThis; globalThis.addEventListener = () => {};"
                "globalThis.location = { origin: 'http://127.0.0.1:8765' }; globalThis.setTimeout = () => 0;")
    r = subprocess.run([node, "-e", vorspann + WAECHTER.read_text(encoding="utf-8") + code],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_startwaechter_waehlt_den_passenden_befund():
    out = _node("""
      const k = window.knowlinVerbindung, b = (d) => k.befund(d).art;
      const r = { ui: b(null), mime: b({ skripttyp: 'text/plain' }), uiTyp: b({ skripttyp: 'text/javascript' }) };
      k.versuch();
      r.still = b(null);
      r.block = b({ startfehler: '', ablehnung: '' });
      r.ab = b({ startfehler: '', ablehnung: 'Proxy' });
      r.start = b({ startfehler: 'ValueError: x', ablehnung: 'Proxy' });
      k.offen(); k.zu(1006); k.zu(1006);
      r.versuche = k.zustand().versuche; r.code = k.zustand().code;
      console.log(JSON.stringify(r));""")
    assert out == {"ui": "ui", "mime": "mime", "uiTyp": "ui", "still": "still", "block": "block", "ab": "ab", "start": "start", "versuche": 2,
                   "code": 1006}


def test_startwaechter_laeuft_ohne_module_und_vor_der_app():
    html = (WAECHTER.parent / "index.html").read_text(encoding="utf-8")
    assert html.index('src="/static/startwaechter.js"') < html.index('src="/static/app.js"')
    assert 'type="module" src="/static/startwaechter.js"' not in html
    assert "import " not in WAECHTER.read_text(encoding="utf-8").split("*/", 1)[1]


def test_skripte_immer_als_javascript_auch_wenn_die_registry_anderes_sagt(client):
    """Fund 19.11.: unter Windows stand .js in der Registry als text/plain – Edge lud kein Modul."""
    import mimetypes
    alt = {e: mimetypes.types_map.get(e) for e in (".js", ".css")}
    try:
        mimetypes.add_type("text/plain", ".js")
        mimetypes.add_type("text/plain", ".css")
        assert client.get("/static/app.js").headers["content-type"].startswith("text/javascript")
        assert client.get("/static/startwaechter.js").headers["content-type"].startswith("text/javascript")
        assert client.get("/static/style.css").headers["content-type"].startswith("text/css")
    finally:
        for e, t in alt.items():
            if t:
                mimetypes.add_type(t, e)


def test_etag_traegt_die_version_alte_eintraege_werden_neu_geliefert(client):
    from duckpilot import __version__
    r = client.get("/static/app.js")
    etag = r.headers["etag"]
    assert etag.endswith(f'-v{__version__}"')
    assert client.get("/static/app.js", headers={"If-None-Match": etag}).status_code == 304
    ohne = etag.split("-v")[0] + '"'                       # so fragte ein Fenster vor 0.38.66 nach
    assert client.get("/static/app.js", headers={"If-None-Match": ohne}).status_code == 200
    assert client.get("/static/app.js", headers={"If-None-Match": etag.replace(__version__, "0.0.1")}).status_code == 200
