"""T2 (0.38.28): Koppeln ohne Hürde – kurzer Code zum Eintippen, knowlin.local im Heimnetz, Karte auf der Startseite."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckpilot import mdns
from duckpilot import remote as R
from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app
from duckpilot.server.oberflaeche import seite
from duckpilot.server.security import _host_ok

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
PC = {"Origin": "http://127.0.0.1:8765"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def test_kurzer_code_lesbar_und_tolerant(tmp_path):
    ra = R.RemoteAccess(tmp_path / "fern.json")
    ra.set_enabled(True)
    c = ra.new_code()
    assert len(c["kurz"]) == R.KURZ_LAENGE and set(c["kurz"]) <= set(R.KURZ_ZEICHEN)
    assert not set("01OI") & set(R.KURZ_ZEICHEN)
    getippt = f" {c['kurz'][:3].lower()}-{c['kurz'][3:].lower()} "
    assert ra.code_valid(getippt) and ra.code_valid(c["code"])
    assert not ra.code_valid("ABCDE") and not ra.code_valid("")
    token = ra.pair(getippt, "Tablet", "192.168.1.30")
    assert token and ra.code_state() is None                                   # einmal verwendbar


def test_falsche_kurze_codes_verbrauchen_den_code(tmp_path):
    ra = R.RemoteAccess(tmp_path / "fern.json")
    ra.set_enabled(True)
    c = ra.new_code()
    falsch = "ZZZZZZ" if c["kurz"] != "ZZZZZZ" else "YYYYYY"
    for _ in range(R.MAX_TRIES):
        with pytest.raises(PermissionError):
            ra.pair(falsch, "x", None)
    with pytest.raises(PermissionError):
        ra.pair(c["kurz"], "x", None)                                          # nach 5 Fehlversuchen verbraucht


def test_name_als_host_nur_solange_angesagt():
    assert not _host_ok("knowlin.local:8766") and not _host_ok("boese.local") and not _host_ok("knowlin.local.evil.com")
    mdns._angesagt.add("knowlin.local")
    try:
        assert _host_ok("knowlin.local:8766") and _host_ok("knowlin.local")
        assert not _host_ok("anderer.local:8766")
    finally:
        mdns._angesagt.discard("knowlin.local")
    assert not _host_ok("knowlin.local:8766")


def test_ansage_nur_mit_privaten_adressen():
    assert mdns._privat_v4("192.168.1.5") and mdns._privat_v4("http://10.0.0.7:8766")
    assert not mdns._privat_v4("8.8.8.8") and not mdns._privat_v4("127.0.0.1") and not mdns._privat_v4("fe80::1")
    a = mdns.Ansage()
    assert asyncio.run(a.start(8766, ["8.8.8.8"])) is None and a.name is None


def test_ansage_mit_zeroconf():
    pytest.importorskip("zeroconf")

    async def lauf():
        a = mdns.Ansage()
        name = await a.start(8766, ["192.168.1.50"])
        if name is None:                                                       # kein Multicast in dieser Umgebung
            return None, None
        da = mdns.name_erlaubt("knowlin.local")
        await a.stop()
        return da, mdns.name_erlaubt("knowlin.local")

    da, danach = asyncio.run(lauf())
    if da is None:
        pytest.skip("Multicast hier nicht möglich")
    assert da and not danach


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.setattr(R, "lan_addresses", lambda: ["192.168.1.10"])
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    a = create_app(rt)
    a.runtime = rt
    return a


def test_koppeln_mit_eingetipptem_code(app):
    with TestClient(app, base_url="http://127.0.0.1:8765") as pc:
        rt = app.runtime
        rt.remote.set_enabled(True)
        phone = TestClient(app, base_url="http://192.168.1.10:8766", client=("192.168.1.20", 5000), follow_redirects=False)
        r = phone.get("/")
        assert r.status_code == 401 and 'href="/koppeln"' in r.text and "Code eintippen" in r.text
        seite = phone.get("/koppeln")
        assert seite.status_code == 200 and 'id="c"' in seite.text and 'autocomplete="one-time-code"' in seite.text
        kurz = pc.post("/api/fernzugang/code", headers=PC).json()["code"]["kurz"]
        r = phone.post("/koppeln", content=f"c={kurz[:3]}-{kurz[3:]}&name=Tablet",
                       headers={"Origin": "http://192.168.1.10:8766", **FORM})
        assert r.status_code == 303
        phone.cookies.set(R.COOKIE, r.cookies[R.COOKIE])
        assert phone.get("/").status_code == 200
        falsch = phone.post("/koppeln", content="c=AAAAAA&name=x", headers={"Origin": "http://192.168.1.10:8766", **FORM})
        assert falsch.status_code == 403 and 'href="/koppeln"' in falsch.text


def test_karte_auf_der_startseite():
    html = seite()
    start = html[html.index('id="view-start"'):html.index('id="view-dashboard"')]
    assert 'class="start-handy pc-only" id="start-handy"' in start
    for i in ("handy-qr", "handy-code", "handy-hinweis", "handy-los", "handy-verwalten"):
        assert f'id="{i}"' in start
    js = (STATIC / "handy_start.js").read_text(encoding="utf-8")
    assert "import { qrSvg } from './fernbedienung.js';" in js and "'/api/fernzugang/code'" in js
    assert "initHandyStart" in (STATIC / "start.js").read_text(encoding="utf-8")
