"""Mentor als eigenes Modul und Marionette (seit 0.48)."""

from __future__ import annotations

import asyncio
import math

import pytest
from helpers import make, run_for

from duckpilot import marionette as M
from duckpilot import mentor_ziele as MZ
from duckpilot.motion.nachspielen import Nachspielen

O = {"Origin": "http://127.0.0.1:8765"}


# ── Marionette, rein rechnend ────────────────────────────────────────────
def test_lage_nur_drei_endliche_zahlen_und_begrenzt():
    assert M.lage_aus({"gieren": 0.2, "nicken": -0.1, "neigen": 0}) == (0.2, -0.1, 0.0)
    assert M.lage_aus({"gieren": "x"}) is None
    assert M.lage_aus({"gieren": float("nan")}) is None
    assert M.lage_aus([1, 2, 3]) is None
    assert M.lage_aus({"gieren": 9})[0] == pytest.approx(M.GRENZE)


def test_kopf_richtungen():
    k = M.kopf_von(0.3, 0.2, 0.1)
    assert k.head_yaw > 0             # links bleibt links
    assert k.head_pitch < 0           # „nach oben“ heißt beim Körper: Kopf hebt sich (Nicken nach unten ist +)
    assert k.head_roll > 0


def test_aufnahme_punkte_im_takt_und_mit_grenze():
    m = M.Marionette()
    m.weiter((0.0, 0.0, 0.0), 0.0)
    m.aufnehmen(0.0)
    for i in range(1, 40):
        m.weiter((0.3, 0.0, 0.0), i * 0.033)
    pts = m.aufnahme_ende()
    assert 10 <= len(pts) <= 14 and pts[0][0] < 0.1
    assert all(b[0] - a[0] >= M.PUNKT_S - 1e-9 for a, b in zip(pts, pts[1:]))
    assert pts[-1][2] > pts[0][2]                       # geglättet: der Kopf dreht nach und nach mit
    m.aufnehmen(0.0)
    m.weiter((0, 0, 0), M.AUFNAHME_MAX_S + 1)
    assert not m.nimmt_auf                              # zu lang: Aufnahme endet von selbst


def test_bewegungen_je_koerper(tmp_path):
    b = M.Bewegungen(tmp_path)
    pts = [[i * 0.1, 0.0, 0.1 * i, 0.0] for i in range(10)]
    assert not b.speichern("microduck", "  ", pts)[0]
    assert not b.speichern("microduck", "kurz", pts[:3])[0]
    ok, text = b.speichern("microduck", "Kopf schütteln<script>", pts)
    assert ok and "Kopf schütteln" in text and "<" not in b.liste("microduck")[0]["name"]
    assert b.liste("reachy_mini") == []
    assert b.alle_koerper() == {"microduck": b.liste("microduck")}
    assert b.loeschen("microduck", "Kopf schüttelnscript") and b.liste("microduck") == []


def test_nachspielen_bewegt_den_kopf():
    async def go():
        sim, eng = await make(zufall=1)
        pts = [[i * 0.1, 0.0, 0.5 * min(1.0, i / 5), 0.0] for i in range(16)]
        b = Nachspielen("Umschauen", pts)
        eng.run(b)
        yaws = []
        await run_for(sim, eng, 2.5, until=lambda: yaws.append(sim.state().head.head_yaw) or b.done)
        assert b.done and "nachgemacht" in (b.result or "")
        assert max(yaws) > 0.3
    asyncio.run(go())


# ── Mentor-Überblick, rein rechnend ──────────────────────────────────────
def test_lernziele_ablage(tmp_path):
    z = MZ.Lernziele(tmp_path)
    assert z.neu("x", "")[0] is None
    eins, _ = z.neu("Kopf schütteln, wenn ich nein sage", "microduck")
    assert eins and not eins["erledigt"]
    assert z.setzen(eins["id"], True) and z.alle()[0]["erledigt"]
    assert not z.setzen("gibtsnicht", True)
    assert z.loeschen(eins["id"]) and z.alle() == []


def test_gelernte_ziele_nur_aus_echten_zahlen():
    ari = {"aufgabe": {"wuerfel": "roter Würfel", "kiste": "linke Kiste"}, "beispiele": 7,
           "gelernt": {"geschafft": 9, "versuche": 10}}
    g = MZ.gelernte_ziele(ari, {"rot_links": {"titel": "Rot links", "schritte": [1, 2]}}, {"gelernt": True, "tempo": 0.31},
                          {"microduck": [{"name": "Nicken", "dauer": 2.0, "punkte": 20}]})
    arten = {z["art"]: z for z in g}
    assert arten["vormachen"]["fortschritt"] == pytest.approx(0.9) and "9 von 10" in arten["vormachen"]["stand"]
    assert "31 cm/s" in arten["ueben"]["stand"]
    assert arten["marionette"]["bewegung"] == "Nicken"
    nur_beispiele = MZ.gelernte_ziele({"aufgabe": {}, "beispiele": 2, "gelernt": None}, {}, None, {})
    assert nur_beispiele[0]["fortschritt"] is None and "noch nicht gelernt" in nur_beispiele[0]["stand"]
    assert MZ.gelernte_ziele(None, {}, {"gelernt": False}, {}) == []
    u = MZ.ueberblick([], g, {"kopf", "beine"}, "microduck")
    assert {x["id"]: x["geht"] for x in u["uebungen"]}["vormachen_hand"] is False
    assert u["zahlen"]["bewegungen"] == 1


# ── Mit dem Server ───────────────────────────────────────────────────────
@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "daten"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        c.runtime = rt
        yield c


def _fuehren(rt, gieren, n=8):
    async def go():
        for i in range(n):
            rt.marionette_dienst._zuletzt = 0.0
            await rt.marionette_dienst.nachricht({"type": "marionette", "gieren": gieren, "nicken": 0.1, "neigen": 0.0})
            await asyncio.sleep(0.03)
    asyncio.run(go())


def test_server_fuehren_aufnehmen_nachmachen(client):
    rt = client.runtime
    s = client.get("/api/marionette").json()
    assert s["grund"] is None and s["bewegungen"] == []
    assert client.post("/api/marionette/aufnahme", json={"aktion": "start"}, headers=O).status_code == 200
    if rt.backend.state().powered:
        _fuehren(rt, 0.4)
        assert rt.engine.gaze.head is not None and rt.engine.gaze.head.head_yaw > 0.05
    rt.marionette_dienst.m.punkte = [[i * 0.1, 0.0, 0.04 * i, 0.0] for i in range(12)]   # Aufnahme unabhängig vom Strom
    r = client.post("/api/marionette/aufnahme", json={"aktion": "stopp", "name": "Umschauen"}, headers=O).json()
    assert r["ok"] and r["bewegungen"][0]["name"] == "Umschauen"
    m = client.get("/api/mentor").json()
    assert any(z["art"] == "marionette" and z["titel"] == "Umschauen" for z in m["ziele"])
    assert {k["id"] for k in m["koerper_liste"]} >= {"microduck", "reachy_mini"}
    r = client.post("/api/marionette/abspielen", json={"name": "Umschauen"}, headers=O)
    assert r.status_code == 200 or "Strom" in r.json()["fehler"]
    assert client.delete("/api/marionette/Umschauen", headers=O).json()["bewegungen"] == []


def test_server_nach_dem_not_aus_folgt_der_kopf_nicht(client):
    rt = client.runtime
    rt.engine.notaus_gesperrt = lambda: True
    rt.engine.look_at(seconds=0)
    _fuehren(rt, 0.5)
    assert rt.engine.gaze.head is None
    assert rt.marionette_dienst.m is None


def test_server_lernziele(client):
    r = client.post("/api/mentor/ziel", json={"text": "Winken lernen", "koerper": "so101"}, headers=O).json()
    z = next(z for z in r["ziele"] if z["eigen"])
    assert z["titel"] == "Winken lernen" and z["stand"] == "offen" and r["zahlen"]["offen"] == 1
    r = client.post("/api/mentor/ziel", json={"id": z["id"], "erledigt": True}, headers=O).json()
    assert r["zahlen"]["offen"] == 0
    assert client.post("/api/mentor/ziel", json={"text": ""}, headers=O).status_code == 400
    assert client.delete(f"/api/mentor/ziel/{z['id']}", headers=O).status_code == 200
    assert client.delete("/api/mentor/ziel/weg", headers=O).status_code == 404


def test_mentor_kachel_ist_fertig():
    from duckpilot import suite

    m = next(x for x in suite.module() if x["id"] == "mentor")
    assert m["stand"] == "fertig" and m["ansicht"] == "mentor"


def test_kopflose_koerper_bekommen_einen_grund():
    class Arm:
        def eigenschaften(self):
            return frozenset({"arm", "greifer"})

    class Rt:
        backend = Arm()
    d = __import__("duckpilot.server.routes.marionette", fromlist=["MarionetteDienst"]).MarionetteDienst.__new__(
        __import__("duckpilot.server.routes.marionette", fromlist=["MarionetteDienst"]).MarionetteDienst)
    d.rt = Rt()
    assert "Hand" in d.grund()
    assert math.isfinite(M.HALTEN_S)
