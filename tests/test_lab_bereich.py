"""Knowlin Lab als Bereich (seit 0.50): Lernwege nach Körperprofil, Raum aus der Quest."""

from __future__ import annotations

import pytest

from duckpilot import koerper as K
from duckpilot import lab_bereich as LB


def _boden(b=3.0, t=2.4, dx=0.5, dy=-0.2):
    return [[dx - b / 2, dy - t / 2], [dx + b / 2, dy - t / 2], [dx + b / 2, dy + t / 2], [dx - b / 2, dy + t / 2]]


def test_lernwege_nach_profil_nie_nach_namen():
    wege = {w["id"]: w for w in LB.lernwege(list(K.alle()), "microduck")}
    assert wege["training"]["jetzt"] and wege["akrobatik"]["jetzt"]
    assert not wege["laufen"]["jetzt"] and "Bittle X" in wege["laufen"]["koerper"]
    assert "SO-101" in wege["vormachen"]["koerper"] and "Microduck" not in wege["vormachen"]["koerper"]
    assert wege["mentor"]["jetzt"]
    bello = {w["id"]: w for w in LB.lernwege(list(K.alle()), "bittle")}
    assert bello["laufen"]["jetzt"] and not bello["training"]["jetzt"]


def test_messung_wird_zum_zimmer_mit_mitte_im_ursprung():
    raum, grund = LB.pruefen({"boden": _boden(), "flaechen": [
        {"art": "table", "x": 0.9, "y": 0.1, "breite": 0.6, "tiefe": 0.4, "hoehe": 0.45},
        {"art": "couch", "x": 0.5, "y": 0.8, "breite": 1.6, "tiefe": 0.6, "hoehe": 0.42},
        {"art": "lamp", "x": 9, "y": 9, "breite": 0.3, "tiefe": 0.3, "hoehe": 1.5},          # außerhalb: weg
        {"art": "table", "x": 0.5, "y": 0, "breite": 0.05, "tiefe": 0.4, "hoehe": 0.4},      # zu schmal: weg
        {"art": "x", "x": "a"}]})
    assert raum and not grund
    assert raum["breite"] == 3.0 and raum["tiefe"] == 2.4 and raum["versatz"] == [0.5, -0.2]
    namen = [m["name"] for m in raum["moebel"]]
    assert namen == ["Tisch", "Sofa"]
    assert raum["moebel"][0]["x"] == pytest.approx(0.4) and raum["moebel"][0]["y"] == pytest.approx(0.3)


def test_unsinnige_messungen_werden_abgewiesen():
    assert LB.pruefen(None)[0] is None
    assert "Boden" in LB.pruefen({"boden": [[0, 0], [1, 1]]})[1]
    assert "1,5 bis 8 m" in LB.pruefen({"boden": _boden(0.8, 0.8)})[1]
    assert LB.pruefen({"boden": [[float("nan"), 0]] * 5})[0] is None
    assert "1,5 bis 8 m" in LB.pruefen({"boden": _boden(20, 2)})[1] or LB.pruefen({"boden": _boden(20, 2)})[0] is None


def test_ablage(tmp_path):
    q = LB.QuestRaum(tmp_path)
    assert q.laden() is None
    raum, _ = LB.pruefen({"boden": _boden()})
    q.speichern(raum)
    assert q.laden()["aktiv"] is False
    q.speichern(q.laden(), aktiv=True)
    q.speichern(raum)                                              # neue Messung behält „aktiv“
    assert q.laden()["aktiv"] is True
    q.loeschen()
    assert q.laden() is None


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
        c.rt = rt
        yield c


def test_server_zimmer_messen_benutzen_und_zurueck(client):
    O = {"Origin": "http://127.0.0.1:8765"}
    d = client.get("/api/lab").json()
    assert d["ok"] and d["raum"] is None and d["kann_raum"] and any(w["id"] == "training" for w in d["lernwege"])
    assert client.post("/api/lab/raum/aktiv", json={"aktiv": True}, headers=O).status_code == 400   # noch keins
    r = client.post("/api/lab/raum", json={"boden": _boden(2.0, 2.0, 0, 0), "flaechen": [
        {"art": "table", "x": 0.5, "y": 0.5, "breite": 0.5, "tiefe": 0.5, "hoehe": 0.4}]}, headers=O).json()
    assert r["ok"] and "2,0" not in r["text"] and r["raum"]["breite"] == 2.0
    welt = client.rt.backend.world_model
    r = client.post("/api/lab/raum/aktiv", json={"aktiv": True}, headers=O).json()
    assert r["ok"] and welt.width == 2.0 and [b.name for b in welt.boxes] == ["Tisch"] and not welt.cylinders
    assert all(abs(i.x) < 1.0 and abs(i.y) < 1.0 for i in welt.items)                  # Dinge bleiben im Zimmer
    be = client.rt.backend
    assert abs(be.x) < 1.0 and abs(be.y) < 1.0
    r = client.post("/api/lab/raum/aktiv", json={"aktiv": False}, headers=O).json()
    assert r["ok"] and welt.width == 4.0 and any(b.name == "Sofa" for b in welt.boxes)
    assert client.delete("/api/lab/raum", headers=O).json()["raum"] is None


def test_kein_zimmerwechsel_in_der_sperre(client):
    O = {"Origin": "http://127.0.0.1:8765"}
    client.post("/api/lab/raum", json={"boden": _boden(2.0, 2.0, 0, 0)}, headers=O)
    client.rt.engine.notaus_gesperrt = lambda: True
    r = client.post("/api/lab/raum/aktiv", json={"aktiv": True}, headers=O)
    assert r.status_code == 400 and "Not-Aus" in r.json()["fehler"]
