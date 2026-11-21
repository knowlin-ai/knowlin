"""Ablauf-Baukasten und Duck Cards (seit 0.49)."""

from __future__ import annotations

import asyncio
import math

import pytest
from helpers import make


async def run_for(sim, eng, seconds, until=None):
    """Wie helpers.run_for, aber mit echter Wartezeit je Takt: der Dienst wartet über das Werkzeug „wait“ in Echtzeit."""
    for _ in range(int(seconds * 20)):
        await eng.tick(0.05)
        sim.step(0.025)
        sim.step(0.025)
        await asyncio.sleep(0.004)
        if until and until():
            return True
    return False

from duckpilot import ablauf as A


def _tag(i, x, y, w=40):
    return {"id": i, "x": x, "y": y, "w": w}


# ── Prüfen ───────────────────────────────────────────────────────────────
def test_pruefen_nur_bekanntes_und_begrenzt():
    ok, _ = A.pruefen({"name": "Tanz<", "schritte": [{"art": "gehen", "richtung": "vor", "tempo": "schnell"},
                                                   {"art": "laut", "name": "wheee"}]})
    assert ok and ok["name"] == "Tanz" and ok["schritte"][0]["tempo"] == "schnell"
    assert A.pruefen({"schritte": [{"art": "rm -rf"}]})[0] is None
    assert A.pruefen({"schritte": [{"art": "gehen", "richtung": "hoch"}]})[0] is None
    assert A.pruefen({"schritte": [{"art": "trick", "name": "fliegen"}]})[0] is None
    assert A.pruefen({"schritte": []})[1] == "Der Ablauf ist leer."
    viel = {"schritte": [{"art": "stopp"}] * 61}
    assert "60" in A.pruefen(viel)[1]
    tief = {"art": "stopp"}
    for _ in range(4):
        tief = {"art": "wiederholen", "mal": 2, "schritte": [tief]}
    assert A.pruefen({"schritte": [tief]})[0] is None
    r, _ = A.pruefen({"schritte": [{"art": "wiederholen", "mal": 99, "schritte": [{"art": "stopp"}]}]})
    assert r["schritte"][0]["mal"] == A.MAX_MAL
    assert A.anzahl(r["schritte"]) == A.MAX_MAL


# ── Duck Cards lesen (duck-cards/0) ──────────────────────────────────────
def test_karten_reihe_mit_zusatz_wiederholen_und_sturz():
    tags = [_tag(100, 0, 0), _tag(102, 50, 0), _tag(0, 100, 0), _tag(20, 101, 45), _tag(2, 150, 0), _tag(41, 152, 46),
            _tag(103, 200, 0), _tag(84, 250, 0), _tag(101, 300, 0), _tag(4, 350, 0),       # nach „Ende“: nicht gelesen
            _tag(120, 0, 120), _tag(80, 50, 121)]
    r = A.aus_karten(tags, mal=3)
    assert r["ok"] and r["vollstaendig"]
    s = r["ablauf"]["schritte"]
    assert s[0]["art"] == "wiederholen" and s[0]["mal"] == 3
    assert s[0]["schritte"][0] == {"art": "gehen", "richtung": "vor", "tempo": "langsam"}
    assert s[0]["schritte"][1] == {"art": "drehen", "richtung": "links", "schauen": "rechts"}
    assert s[1] == {"art": "laut", "name": "wheee"} and len(s) == 2
    assert r["ablauf"]["bei_sturz"] == [{"art": "laut", "name": "greet"}]
    assert r["quelle"].startswith("https://microduckstudio.com")


def test_karten_unbekannt_und_falsch_gelegt_werden_genannt():
    r = A.aus_karten([_tag(0, 0, 0), _tag(60, 50, 0), _tag(20, 51, 45), _tag(33, 300, 45), _tag(250, 100, 0),
                      _tag(1, 150, 0)])
    assert r["ok"] and not r["vollstaendig"]
    assert [x["art"] for x in r["ablauf"]["schritte"]] == ["gehen", "trick"]         # liest bis zur unbekannten Karte
    text = " ".join(r["meldungen"])
    assert "passt nicht unter „Schuss links“" in text and "eigene Karte 250" in text and "unter keiner Karte" in text
    assert not A.aus_karten([])["ok"]
    assert not A.aus_karten([{"id": "x"}])["ok"]


def test_ablauf_zurueck_in_karten():
    r = A.aus_karten([_tag(102, 0, 0), _tag(3, 50, 0), _tag(21, 50, 45), _tag(103, 100, 0), _tag(64, 150, 0)])
    assert A.als_karten(r["ablauf"]["schritte"]) == [[102], [3, 21], [103], [64]]


def test_ablage(tmp_path):
    ab = A.Ablaeufe(tmp_path)
    assert ab.speichern({"schritte": [{"art": "stopp"}]})[0] is None            # ohne Namen
    assert ab.speichern({"name": "Gruß", "schritte": [{"art": "laut", "name": "greet"}]})[0] == "Gruß"
    assert list(ab.alle()) == ["Gruß"]
    assert ab.loeschen("Gruß") and not ab.loeschen("Gruß")


# ── Abspielen im Simulator ───────────────────────────────────────────────
class _Rt:
    def __init__(self, sim, eng):
        from duckpilot.brain.tools import ToolRunner

        self.backend, self.engine, self.runner = sim, eng, ToolRunner(eng)
        self.meldungen = []

    async def broadcast(self, m):
        self.meldungen.append(m)


def _dienst(rt):
    from duckpilot.server.routes.ablauf import AblaufDienst

    d = AblaufDienst.__new__(AblaufDienst)
    d.rt, d.laeuft, d._task, d._estop = rt, None, None, 0.0
    d.ablage = A.Ablaeufe(__import__("pathlib").Path("/nonexistent"))
    return d


def _laufen(ablauf, vorher=None, sekunden=30):
    async def go():
        sim, eng = await make(zufall=1)
        rt = _Rt(sim, eng)
        if vorher:
            vorher(sim, eng)
        d = _dienst(rt)
        r = await d.start({"ablauf": ablauf})
        yaw0 = sim.state().yaw
        await run_for(sim, eng, sekunden, until=lambda: d.laeuft is None)
        return r, rt.meldungen, sim, math.degrees(sim.state().yaw - yaw0)
    return asyncio.run(go())


def test_abspielen_dreht_wiederholt_und_meldet():
    ab = {"name": "Kreis", "schritte": [{"art": "wiederholen", "mal": 2, "schritte": [{"art": "drehen", "richtung": "links"}]},
                                       {"art": "laut", "name": "wheee"}]}
    r, meldungen, sim, grad = _laufen(ab)
    assert r["ok"] and "3 Schritte" in r["text"]
    schritte = [m for m in meldungen if m.get("phase") == "schritt"]
    assert [m["nr"] for m in schritte] == [1, 2, 3]
    assert meldungen[-1]["phase"] == "ende" and "fertig" in meldungen[-1]["text"]
    assert 150 < (grad % 360) < 210                                              # zweimal 90° links


def test_was_der_koerper_nicht_kann_wird_genannt():
    async def go():
        sim, eng = await make(zufall=1)
        rt = _Rt(sim, eng)
        sim.skills = lambda: []                                                   # Körper ohne diese Tricks
        d = _dienst(rt)
        await d.start({"ablauf": {"schritte": [{"art": "trick", "name": "roulade"}, {"art": "stopp"}]}})
        await run_for(sim, eng, 10, until=lambda: d.laeuft is None)
        return rt.meldungen
    m = asyncio.run(go())
    assert "Übersprungen" in m[-1]["text"] and "Rolle" in m[-1]["text"]


def test_kein_start_in_der_sperre_und_not_aus_bricht_ab():
    async def go():
        sim, eng = await make(zufall=1)
        rt = _Rt(sim, eng)
        d = _dienst(rt)
        eng.notaus_gesperrt = lambda: True
        r = await d.start({"ablauf": {"schritte": [{"art": "stopp"}]}})
        assert not r["ok"] and "Not-Aus" in r["fehler"]
        eng.notaus_gesperrt = lambda: False
        await d.start({"ablauf": {"schritte": [{"art": "gehen", "richtung": "vor", "tempo": "langsam"}] * 5}})
        await run_for(sim, eng, 1)
        eng.estop_at = 12345.0                                                  # Not-Aus von irgendwo
        await run_for(sim, eng, 3, until=lambda: d.laeuft is None)
        return d, rt.meldungen
    d, m = asyncio.run(go())
    assert d.laeuft is None and m[-1]["text"] == "Ablauf abgebrochen."


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
        yield c


def test_server_karten_speichern_starten(client):
    O = {"Origin": "http://127.0.0.1:8765"}
    r = client.post("/api/ablauf/karten", json={"tags": [_tag(0, 0, 0), _tag(84, 50, 0)]}, headers=O).json()
    assert r["ok"] and len(r["ablauf"]["schritte"]) == 2
    ab = {**r["ablauf"], "name": "Hallo"}
    s = client.post("/api/ablauf/speichern", json={"ablauf": ab}, headers=O).json()
    assert s["ok"] and s["ablaeufe"]["Hallo"]["karten"] == [[0], [84]]
    assert client.post("/api/ablauf/start", json={"name": "Gibtsnicht"}, headers=O).status_code == 400
    assert client.post("/api/ablauf/start", json={"name": "Hallo"}, headers=O).status_code == 200
    assert client.post("/api/ablauf/stopp", headers=O).json()["ok"]
    assert client.delete("/api/ablauf/Hallo", headers=O).json()["ablaeufe"] == {}
