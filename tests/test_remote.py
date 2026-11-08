"""Handy-Fernbedienung: QR-Code, Kopplung, Zugriffsschutz im Heimnetz, zweiter Zugang."""

import json
import socket
import time
import urllib.request

import pytest
from fastapi.testclient import TestClient

from duckpilot import remote as R
from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.qr import encode, rows
from duckpilot.server.app import Runtime, create_app

PC = {"Origin": "http://127.0.0.1:8765"}
PHONE_BASE = "http://192.168.1.10:8766"
PHONE = {"Origin": PHONE_BASE}


# ── QR-Code ────────────────────────────────────────────────────────────────
def test_qr_sizes_and_finder_patterns():
    for text, version in (("a", 1), ("x" * 40, 3), ("http://192.168.178.23:8766/koppeln?c=Ab3_x9Zq-L0pQrSt", 4), ("y" * 200, 10)):
        m = encode(text)
        assert len(m) == 17 + 4 * version and all(len(r) == len(m) for r in m)
        for r0, c0 in ((0, 0), (0, len(m) - 7), (len(m) - 7, 0)):
            assert [m[r0][c0 + i] for i in range(7)] == [1] * 7
            assert m[r0 + 3][c0 + 3] == 1 and m[r0 + 1][c0 + 1] == 0
    assert set("".join(rows("hallo"))) <= {"0", "1"}
    with pytest.raises(ValueError):
        encode("z" * 300)


def test_qr_decodes_with_opencv():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    det = cv2.QRCodeDetector()
    for text in ("http://192.168.178.23:8766/koppeln?c=Ab3_x9Zq-L0pQrSt", "http://10.0.0.7:9000/koppeln?c=" + "k" * 16,
                 "Hallo Ente ü", "x" * 120):
        m = np.array(encode(text), dtype=np.uint8)
        img = (np.pad(1 - m, 4, constant_values=1) * 255).astype(np.uint8)
        ok = False
        for fx in (6, 8, 10):
            if det.detectAndDecode(cv2.resize(img, None, fx=fx, fy=fx, interpolation=cv2.INTER_NEAREST))[0] == text:
                ok = True
                break
        assert ok, text


# ── Kopplung und Geräte ───────────────────────────────────────────────────
def test_network_classes():
    assert R.is_local("127.0.0.1") and R.is_local("::1") and R.is_local(None)
    assert not R.is_local("192.168.1.2")
    assert R.is_home_network("192.168.1.2") and R.is_home_network("10.1.2.3") and R.is_home_network("172.20.0.5")
    assert R.is_home_network("fe80::1") and R.is_home_network("fd12::5") and R.is_home_network("::ffff:192.168.0.9")
    assert not R.is_home_network("8.8.8.8") and not R.is_home_network("127.0.0.1") and not R.is_home_network("quatsch")
    assert R.device_name("Mozilla/5.0 (Linux; Android 14; Pixel 8) Mobile Safari") == "Android-Handy"
    assert R.device_name("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)") == "iPhone"


def test_pairing_is_one_time_and_only_hash_is_stored(tmp_path):
    ra = R.RemoteAccess(tmp_path / "fern.json")
    with pytest.raises(ValueError):
        ra.new_code()                       # aus: kein Code
    ra.set_enabled(True)
    code = ra.new_code()["code"]
    assert ra.code_valid(code) and not ra.code_valid("falsch")
    token = ra.pair(code, "Annas\x00 Handy", "192.168.1.20")
    with pytest.raises(PermissionError):
        ra.pair(code, "nochmal", None)      # einmal verwendbar
    raw = (tmp_path / "fern.json").read_text(encoding="utf-8")
    assert token not in raw and R._hash(token) in raw
    dev = ra.device_for(token)
    assert dev and dev["name"] == "Annas Handy"
    assert ra.device_for("x" * 43) is None and ra.device_for(None) is None
    # neu geladen: Gerät bleibt, Code nicht
    ra2 = R.RemoteAccess(tmp_path / "fern.json")
    assert ra2.enabled and ra2.device_for(token) and ra2.code_state() is None
    assert ra2.revoke(dev["id"]) and ra2.device_for(token) is None


def test_code_expires_and_dies_after_wrong_tries(tmp_path, monkeypatch):
    ra = R.RemoteAccess(tmp_path / "fern.json")
    ra.set_enabled(True)
    code = ra.new_code()["code"]
    for _ in range(R.MAX_TRIES):
        with pytest.raises(PermissionError):
            ra.pair("geraten", "x", None)
    with pytest.raises(PermissionError):
        ra.pair(code, "x", None)            # nach 5 Fehlversuchen verbraucht
    code = ra.new_code()["code"]
    t = time.time()
    monkeypatch.setattr(R.time, "time", lambda: t + R.CODE_SECONDS + 1)
    assert not ra.code_valid(code)
    with pytest.raises(PermissionError, match="abgelaufen"):
        ra.pair(code, "x", None)


def test_switching_off_blocks_paired_devices(tmp_path):
    ra = R.RemoteAccess(tmp_path / "fern.json")
    ra.set_enabled(True)
    token = ra.pair(ra.new_code()["code"], "Handy", None)
    assert ra.check("192.168.1.20", token, "GET", "/api/settings") is None
    assert ra.check("192.168.1.20", None, "GET", "/api/settings")[0] == 401
    assert ra.check("192.168.1.20", token, "POST", "/api/key")[0] == 403
    assert ra.check("192.168.1.20", token, "POST", "/api/training/start")[0] == 403
    assert ra.check("192.168.1.20", token, "GET", "/api/fernzugang")[0] == 403
    assert ra.check("192.168.1.20", None, "GET", "/static/app.js") is None
    assert ra.check("8.8.8.8", token, "GET", "/api/settings")[0] == 403
    assert ra.check("127.0.0.1", None, "POST", "/api/key") is None
    ra.set_enabled(False)
    assert ra.check("192.168.1.20", token, "GET", "/api/settings")[0] == 403


# ── Über den Server ───────────────────────────────────────────────────────
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


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_phone_pairs_and_then_controls_but_not_secrets(app):
    rt = app.runtime
    port = _free_port()
    with TestClient(app, base_url="http://127.0.0.1:8765") as pc:
        phone = TestClient(app, base_url=PHONE_BASE, client=("192.168.1.20", 50000), follow_redirects=False)
        # aus: Handy kommt nicht herein
        r = phone.get("/")
        assert r.status_code == 403 and "ausgeschaltet" in r.text
        r = pc.post("/api/fernzugang", json={"an": True, "port": port}, headers=PC)
        assert r.json()["ok"] and r.json()["lauscht"], r.json()
        # an, aber nicht gekoppelt
        r = phone.get("/")
        assert r.status_code == 401 and "nicht gekoppelt" in r.text and "QR-Code" in r.text
        assert phone.get("/api/settings").status_code == 401
        assert phone.get("/static/app.js").status_code == 200
        # das Handy darf die Fernbedienung nicht selbst verwalten
        assert phone.post("/api/fernzugang/code", headers=PHONE).status_code in (401, 403)
        # Code am PC holen
        r = pc.post("/api/fernzugang/code", headers=PC).json()
        assert r["ok"] and r["code"]["link"].startswith("http://192.168.1.10:")
        assert r["code"]["qr"] and len(r["code"]["qr"]) >= 21
        code = r["code"]["code"]
        # Kopplungsseite: Code wird nur geprüft, nicht verbraucht – und sauber maskiert
        page = phone.get(f"/koppeln?c={code}", headers={"User-Agent": "Mozilla/5.0 (iPhone)"})
        assert page.status_code == 200 and 'value="iPhone"' in page.text
        # no-referrer würde Browser „Origin: null“ schicken lassen – dann scheitert das Koppeln
        assert page.headers["referrer-policy"] == "same-origin"
        assert phone.get('/koppeln?c="><script>').status_code == 400
        # fremde Webseite kann nicht koppeln
        r = phone.post("/koppeln", content=f"c={code}&name=Evil", headers={"Origin": "http://evil.example",
                                                                       "Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 403
        r = phone.post("/koppeln", content=f"c={code}&name=Annas%20Handy",
                       headers={**PHONE, "Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 303 and r.headers["location"] == "/"
        cookie = r.headers["set-cookie"]
        assert R.COOKIE in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
        phone.cookies.set(R.COOKIE, r.cookies[R.COOKIE])
        # jetzt darf es steuern …
        assert phone.get("/").status_code == 200
        assert phone.get("/api/settings").status_code == 200
        # … aber nicht an Schlüssel, Installationen, bezahltes Training oder die Fernbedienung selbst
        for method, path in (("post", "/api/key"), ("delete", "/api/key"), ("post", "/api/training/start"),
                             ("post", "/api/training/token"), ("post", "/api/open-folder"), ("get", "/api/fernzugang"),
                             ("post", "/api/stimme/installieren"), ("post", "/api/gehirn/laden")):
            r = getattr(phone, method)(path, headers=PHONE, **({"json": {}} if method == "post" else {}))
            assert r.status_code == 403 and r.json()["nur_pc"], path
        # WebSocket: Handy bekommt init und weiß, dass es Fernbedienung ist
        with phone.websocket_connect("/ws", headers={"Host": "192.168.1.10:8766", "Origin": PHONE_BASE}) as ws:
            types = [ws.receive_json() for _ in range(4)]
            assert [m["type"] for m in types[:3]] == ["init", "memory", "alltag"]
            assert types[3] == {"type": "verbindung", "fern": True, "geraet": "Annas Handy"}
        # PC sieht das Gerät, meldet es ab → Handy ist draußen
        st = pc.get("/api/fernzugang").json()
        assert [d["name"] for d in st["geraete"]] == ["Annas Handy"] and "hash" not in st["geraete"][0]
        assert pc.delete(f"/api/fernzugang/geraet/{st['geraete'][0]['id']}", headers=PC).json()["ok"]
        assert phone.get("/api/settings").status_code == 401
        # nicht aus dem Heimnetz: abgelehnt, egal mit welchem Cookie
        stranger = TestClient(app, base_url=PHONE_BASE, client=("203.0.113.5", 1))
        assert stranger.get("/api/ping").status_code == 403
        pc.post("/api/fernzugang", json={"an": False}, headers=PC)
        assert not rt.remote_listener.listening


def test_second_listener_serves_the_same_app(app):
    port = _free_port()
    rt = app.runtime
    rt.remote.set_enabled(True)
    rt.remote.set_port(port)
    with TestClient(app, base_url="http://127.0.0.1:8765") as pc:
        assert rt.remote_listener.listening
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=5) as r:
            assert json.load(r)["app"] == "duckpilot"
        # Port belegt → klare Meldung statt Absturz
        blocker = socket.socket()
        blocker.bind(("0.0.0.0", 0))
        blocker.listen(1)
        busy = blocker.getsockname()[1]
        try:
            r = pc.post("/api/fernzugang", json={"port": busy}, headers=PC).json()
            assert not r["lauscht"] and "belegt" in (r["fehler"] or "")
            assert pc.post("/api/fernzugang", json={"port": 8765}, headers=PC).status_code == 400
        finally:
            blocker.close()
        r = pc.post("/api/fernzugang", json={"port": port}, headers=PC).json()
        assert r["lauscht"] and not r["fehler"]
    assert not rt.remote_listener.listening


def test_pc_ui_has_card_and_phone_hides_pc_only(app):
    with TestClient(app, base_url="http://127.0.0.1:8765") as pc:
        html = pc.get("/").text
        for needle in ('id="set-fern"', 'id="fern-an"', 'id="fern-qr"', 'class="field-help fern-only"', 'pc-only" id="key-form"'):
            assert needle in html, needle
        js = pc.get("/static/fernbedienung.js").text
        assert "innerHTML" not in js


def test_host_header_must_be_exactly_a_host():
    from duckpilot.server.app import _host_ok

    for ok in ("127.0.0.1:8765", "localhost", "localhost:8765", "192.168.1.10:8766", "[::1]:8765", "[fe80::1]"):
        assert _host_ok(ok), ok
    for bad in ("192.168.1.10/static/x", "192.168.1.10:8766/static/x", "evil.example", "127.0.0.1.nip.io",
                "192.168.1.10:8766@evil", "", None, "999.1.1.1", "localhost:8765#x"):
        assert not _host_ok(bad), bad


def test_full_devices_do_not_burn_the_code(tmp_path):
    ra = R.RemoteAccess(tmp_path / "fern.json")
    ra.set_enabled(True)
    for i in range(R.MAX_DEVICES):
        ra.pair(ra.new_code()["code"], f"g{i}", None)
    code = ra.new_code()["code"]
    with pytest.raises(PermissionError, match="abmelden"):
        ra.pair(code, "zu viel", None)
    ra.revoke(ra.devices()[0]["id"])
    assert ra.pair(code, "jetzt", None)          # derselbe Code klappt nach dem Abmelden


def test_phone_cannot_change_pc_settings_or_post_without_origin(app):
    with TestClient(app, base_url="http://127.0.0.1:8765"):
        rt = app.runtime
        rt.remote.set_enabled(True)
        token = rt.remote.pair(rt.remote.new_code()["code"], "Handy", None)
        phone = TestClient(app, base_url=PHONE_BASE, client=("192.168.1.20", 50000))
        phone.cookies.set(R.COOKIE, token)
        for key, val in (("model", "claude-opus-5-5"), ("robot", "tcp:10.0.0.9:7900"), ("lokal_adresse", "http://10.0.0.9:11434"),
                         ("memory", False), ("backend", "robotd")):
            r = phone.post("/api/settings", json={key: val}, headers=PHONE)
            assert r.status_code == 403 and r.json()["nur_pc"], key
        assert phone.post("/api/settings", json={"tts": False}, headers=PHONE).status_code == 200
        # ohne Origin (kein Browser) oder von einer anderen Seite derselben Adresse: abgelehnt
        assert phone.post("/api/settings", json={"tts": True}).status_code == 403
        assert phone.get("/api/settings", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
        assert phone.get("/api/settings", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
        rt.remote.set_enabled(False)


def test_tailscale_requests_never_count_as_the_pc(app, monkeypatch):
    TSB = "https://ente.tail1234.ts.net"
    with TestClient(app, base_url="http://127.0.0.1:8765"):
        rt = app.runtime
        # Tailscale Serve leitet von 127.0.0.1 weiter – Host ist der ts.net-Name
        ts = TestClient(app, base_url=TSB, client=("127.0.0.1", 40000), follow_redirects=False)
        assert ts.get("/api/settings").status_code == 403                      # Zugang aus: Name unbekannt
        rt.remote.set_enabled(True)
        rt.remote.set_tailscale(True, "ente.tail1234.ts.net")
        r = ts.get("/api/settings")
        assert r.status_code == 401                                             # zählt nicht als PC, braucht Kopplung
        assert ts.get("/").status_code == 401
        code = rt.remote.new_code()["code"]
        assert rt.remote_message(with_qr=True)["code"]["link"].startswith(TSB + "/koppeln?c=")
        r = ts.post("/koppeln", content=f"c={code}&name=Handy", headers={"Origin": TSB,
                                                                          "Content-Type": "application/x-www-form-urlencoded"})
        assert r.status_code == 303 and "secure" in r.headers["set-cookie"].lower()
        ts.cookies.set(R.COOKIE, r.cookies[R.COOKIE])
        assert ts.get("/api/settings", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
        assert ts.post("/api/key", json={"key": "x"}, headers={"Origin": TSB}).status_code == 403
        assert ts.get("/api/fernzugang").status_code == 403
        assert rt.remote.devices()[0]["adresse"] == "über Tailscale"
        # PC-Einstellungen und Augen/Personen auch über Tailscale nicht (kommt technisch von 127.0.0.1)
        H = {"Origin": TSB}
        r = ts.post("/api/settings", json={"memory": False}, headers=H)
        assert r.status_code == 403 and r.json()["nur_pc"]
        assert ts.post("/api/settings", json={"tts": False}, headers=H).status_code == 200
        r = ts.post("/api/alltag/optionen", json={"personen": True, "augen": "webcam"}, headers=H)
        assert r.status_code == 403 and not rt.alltag.planner.data["personen"]
        assert ts.post("/api/alltag/optionen", json={"durchsagen": True}, headers=H).status_code == 200
        # ein ts.net-Name direkt aus dem Netz (nicht über Serve) wird abgewiesen
        lan = TestClient(app, base_url=TSB, client=("192.168.1.20", 1))
        assert lan.get("/api/ping").status_code == 403
        # ausschalten sperrt wieder
        rt.remote.set_tailscale(False)
        assert ts.get("/api/settings").status_code == 403
        rt.remote.set_enabled(False)


def test_ts_hostname_is_strict():
    assert R.ts_hostname("ente.tail1234.ts.net") == "ente.tail1234.ts.net"
    assert R.ts_hostname("Ente.Tail1234.ts.net:443") == "ente.tail1234.ts.net"
    for bad in ("ts.net", "evil.com", "ente.ts.net.evil.com", "ente.tail1234.ts.net/x", "a b.ts.net", None, ""):
        assert R.ts_hostname(bad) is None, bad


def test_phone_cannot_switch_on_eyes_and_other_local_proxies_are_not_the_pc(app):
    with TestClient(app, base_url="http://127.0.0.1:8765") as pc:
        rt = app.runtime
        rt.remote.set_enabled(True)
        token = rt.remote.pair(rt.remote.new_code()["code"], "Handy", None)
        phone = TestClient(app, base_url=PHONE_BASE, client=("192.168.1.20", 50000))
        phone.cookies.set(R.COOKIE, token)
        for patch in ({"sehen": True}, {"personen": True}, {"begruessen": False}, {"augen": "webcam"}):
            assert phone.post("/api/alltag/optionen", json=patch, headers=PHONE).status_code == 403, patch
        assert not rt.alltag.planner.data["sehen"]
        assert pc.post("/api/alltag/optionen", json={"sehen": True},
                       headers={"Origin": "http://127.0.0.1:8765"}).json()["ok"]          # am PC geht es
        # ein anderer Weiterleiter auf diesem PC (setzt X-Forwarded-For) gilt nie als „der PC selbst“
        r = pc.post("/api/settings", json={"memory": False},
                    headers={"Origin": "http://127.0.0.1:8765", "X-Forwarded-For": "203.0.113.9"})
        assert r.status_code == 403
        assert pc.get("/api/settings", headers={"Tailscale-User-Login": "x@example.com"}).status_code == 403
        rt.remote.set_enabled(False)


def test_who_is_home_is_never_told_to_a_phone():
    import asyncio

    from duckpilot.skills.alltag import AlltagService

    async def go():
        svc = AlltagService.__new__(AlltagService)
        tok = R.REMOTE_TURN.set(True)
        try:
            r = await AlltagService._who(svc)
        finally:
            R.REMOTE_TURN.reset(tok)
        assert not r["ok"] and "PC" in r["fehler"]
    asyncio.run(go())


def test_who_is_home_over_http_is_refused_for_phones(app):
    with TestClient(app, base_url="http://127.0.0.1:8765"):
        rt = app.runtime
        rt.remote.set_enabled(True)
        token = rt.remote.pair(rt.remote.new_code()["code"], "Handy", None)
        phone = TestClient(app, base_url=PHONE_BASE, client=("192.168.1.20", 50000))
        phone.cookies.set(R.COOKIE, token)
        rt.alltag.planner.set_options(personen=True)
        r = phone.post("/api/alltag/befehl", json={"aktion": "wer_ist_da"}, headers=PHONE).json()
        assert not r["ok"] and "PC" in r["fehler"]
        rt.remote.set_enabled(False)
