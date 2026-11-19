"""Spiele für jeden Körper (seit 0.44): „Ente sagt“, Verstecken, Elfmeter – und VR (nur gebaut, nicht mit Brille geprüft)."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from helpers import make, run_for

from duckpilot import settings as S
from duckpilot.backends.sim import DUCK_RADIUS
from duckpilot.backends.world import World
from duckpilot.config import load
from duckpilot.ente_sagt import LEBEN, SPAET_S, ZEICHEN, EnteSagt
from duckpilot.motion.elfmeter import ZIELE, Elfmeter
from duckpilot.remote import pc_only
from duckpilot.server.app import Runtime, create_app
from duckpilot.server.oberflaeche import STATIC, seite
from duckpilot.verstecken import VERSUCHE, Verstecken, bei, verstecke

H = {"Origin": "http://127.0.0.1:8765"}


class Uhr:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# ── „Ente sagt“ ──────────────────────────────────────────────────────────
def test_ente_sagt_regeln():
    uhr = Uhr()
    s = EnteSagt("Quacki", seed=3, uhr=uhr)
    gesehen_sagt, gesehen_ohne = False, False
    for _ in range(40):
        if s.vorbei:
            break
        r = s.naechste()
        runde = dict(s.runde)
        assert runde["zeichen"] != s.vorher                       # nie das, was die Hand schon zeigt
        assert r["text"].startswith("Quacki sagt:") == r["sagt"]
        if r["sagt"]:
            gesehen_sagt = True
            assert s.antwort(runde["zeichen"])["richtig"]
        else:
            gesehen_ohne = True
            punkte = s.punkte
            res = s.antwort(runde["zeichen"])                     # ohne „sagt“ nachgemacht: falsch
            assert not res["richtig"] and ("Reingelegt" in res["satz"] or "Ha!" in res["satz"])
            assert s.punkte == punkte
    assert gesehen_sagt and gesehen_ohne


def test_ente_sagt_zu_spaet_leben_und_frist():
    uhr = Uhr()
    s = EnteSagt(seed=1, uhr=uhr)
    s.punkte = 6
    assert s.frist == pytest.approx(3.5)
    while True:                                                   # eine Runde mit „sagt“ finden
        s.naechste()
        if s.runde["sagt"]:
            break
        s.antwort("keine" if s.runde["zeichen"] != "keine" else "stein")          # nicht nachgemacht: richtig
    ziel = s.runde["zeichen"]
    uhr.t += s.runde["frist_s"] + SPAET_S + 0.1
    r = s.antwort(ziel)                                           # richtig gezeigt, aber zu spät
    assert r["gezeigt"] == "keine" and (r["richtig"] == (ziel == "keine"))
    s2 = EnteSagt(seed=2)
    for _ in range(LEBEN):
        s2.naechste()
        falsch = next(z for z in ZEICHEN if z != s2.runde["zeichen"]) if s2.runde["sagt"] else s2.runde["zeichen"]
        r = s2.antwort(falsch)
    assert r["vorbei"] and "Spiel vorbei" in r["satz"]
    with pytest.raises(ValueError):
        s2.naechste()


# ── Verstecken ───────────────────────────────────────────────────────────
def _orte():
    w = World.living_room()
    moebel = [{"name": b.name, "x": b.x, "y": b.y, "sx": b.sx, "sy": b.sy} for b in w.boxes]
    moebel += [{"name": c.name, "x": c.x, "y": c.y, "r": c.r} for c in w.cylinders]
    return w, verstecke(moebel, w.width, w.depth, lambda x, y: w.collide(x, y, DUCK_RADIUS + 0.02) is None)


def test_verstecke_frei_und_im_zimmer():
    w, orte = _orte()
    assert {o["moebel"] for o in orte} == {b.name for b in w.boxes} | {c.name for c in w.cylinders}
    for o in orte:
        assert abs(o["x"]) < w.width / 2 and abs(o["y"]) < w.depth / 2
        assert w.collide(o["x"], o["y"], DUCK_RADIUS) is None, o
    assert bei("Sofa") == "beim Sofa" and bei("Pflanze") == "bei der Pflanze"


def test_verstecken_raten_waermer_kaelter_und_aufdecken():
    _, orte = _orte()
    v = Verstecken(orte, seed=1)
    with pytest.raises(ValueError, match="nicht geraten"):
        v.raten("Sofa")
    v.versteckt(v.ort["x"], v.ort["y"])
    falsch = sorted((o for o in orte if o is not v.ort), key=lambda o: -((o["x"] - v.ort["x"]) ** 2 + (o["y"] - v.ort["y"]) ** 2))
    assert v.raten(falsch[0]["moebel"])["satz"] == "Nein, da nicht."
    assert v.raten(falsch[-1]["moebel"])["satz"] == "Wärmer!"
    with pytest.raises(ValueError, match="Kein Versteck"):
        v.raten("Kühlschrank")
    r = v.raten(v.ort["moebel"].upper())
    assert r["treffer"] and r["versuche"] == 3 and v.phase == "gefunden"
    v2 = Verstecken(orte, seed=2)
    v2.versteckt(v2.ort["x"], v2.ort["y"])
    andere = [o for o in orte if o is not v2.ort]
    for i in range(VERSUCHE):
        r = v2.raten(andere[i % len(andere)]["moebel"])
    assert r["ende"] and v2.phase == "aufgedeckt" and v2.ort["text"] in r["satz"]


def test_verstecken_kam_nicht_hin_gilt_das_naechste_versteck():
    _, orte = _orte()
    v = Verstecken(orte, seed=1)
    anderer = next(o for o in orte if o is not v.ort)
    v.versteckt(anderer["x"] + 0.05, anderer["y"])
    assert v.ort is anderer


# ── Elfmeter ─────────────────────────────────────────────────────────────
def test_elfmeter_torwart_haelt_und_verraet_die_ecke_nicht_vorher():
    async def go():
        sim, eng = await make()
        tor = sim.tor_aufstellen()
        assert sim.state().spielfeld == {"tor": tor}
        gemeldet = []
        e = Elfmeter(tor, 2, melden=gemeldet.append, seed=4)
        eng.run(e)
        gehechtet = False
        for _ in range(120):
            await run_for(sim, eng, 1.0)
            if e.phase == "schiessen" and not gehechtet:
                assert e.hechten(e.seite) and not e.hechten("links")   # einmal je Schuss
                gehechtet = True
            if e.phase in ("pause", "hinlegen"):
                gehechtet = False
            if e.done:
                break
        assert e.done and e.nr == 2, e.result
        neu = [m for m in gemeldet if m.get("neu")]
        assert len(neu) == 2 and all("seite" not in m for m in neu)        # Ecke erst nach dem Schuss
        ergebnis = [m for m in gemeldet if "tor" in m]
        assert all(m["seite"] in ZIELE and m["gehechtet"] == m["seite"] for m in ergebnis)
        assert e.tore == 0 and e.gehalten == sum(1 for m in ergebnis if m["gehalten"])
        assert not e.hechten("links")                                       # vorbei
    asyncio.run(go())


def test_elfmeter_braucht_den_einfachen_simulator():
    async def go():
        _, eng = await make()

        class OhneBall:
            pass

        e = Elfmeter({"x": -2.0, "y": 0.0, "breite": 0.7})
        e.engine = type("E", (), {"backend": OhneBall()})()
        e.tick(None, 0.05)
        assert e.done and e.failed and "einfachen Simulator" in e.result
    asyncio.run(go())


# ── Mit dem Server ───────────────────────────────────────────────────────
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "daten"))            # Bestwerte nicht in den echten Datenordner
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        c.runtime = rt
        yield c


def test_ente_sagt_ueber_den_server(client):
    s = client.get("/api/spiel").json()
    assert s["wer"] and s["bestwerte"] == {}
    r = client.post("/api/spiel/sagt", json={"aktion": "start"}, headers=H).json()
    assert r["ok"] and r["runde"]["text"] and r["leben"] == LEBEN
    for _ in range(30):
        spiel = client.runtime.alle_spiele.sagt
        falsch = "keine" if spiel.runde["zeichen"] != "keine" else "stein"
        r = client.post("/api/spiel/sagt", json={"aktion": "antwort", "zeichen": falsch if spiel.runde["sagt"] else
                                                  spiel.runde["zeichen"]}, headers=H).json()
        if r["vorbei"]:
            break
    assert r["vorbei"] and r["punkte"] == 0
    assert client.post("/api/spiel/sagt", json={"aktion": "antwort"}, headers=H).status_code == 400


def test_verstecken_und_elfmeter_nicht_nach_dem_not_aus(client):
    rt = client.runtime
    rt.engine.estop_at = time.monotonic()                                 # gerade Not-Aus: Sperre läuft
    r = client.post("/api/spiel/verstecken", json={"aktion": "start"}, headers=H)
    assert r.status_code == 400 and "Not-Aus" in r.json()["fehler"]
    r = client.post("/api/spiel/elfmeter", json={"aktion": "start"}, headers=H)
    assert r.status_code == 400 and "Not-Aus" in r.json()["fehler"]
    assert client.post("/api/spiel/verstecken", json={"aktion": "raten", "moebel": "Sofa"}, headers=H).status_code == 400
    assert client.post("/api/spiel/elfmeter", json={"aktion": "stopp"}, headers=H).json()["ok"]
    assert rt.backend.state().spielfeld == {}


def test_spiele_auch_vom_handy():
    for pfad in ("/api/spiel/sagt", "/api/spiel/verstecken", "/api/spiel/elfmeter"):
        assert not pc_only("POST", pfad)


# ── Oberfläche und VR ────────────────────────────────────────────────────
def test_oberflaeche_spiele_fuer_alle_und_vr():
    html = seite()
    for kennung in ('id="sp-sagt"', 'id="sp-versteck"', 'id="sp-elfer"', 'id="sp-vorhang"', 'id="sp-torwart"',
                    'id="vr-start"', 'id="vr-notaus"', "bereiche/spiele.css"):
        assert kennung in html, kennung
    assert 'class="card set-card g-half sp-karte braucht-beine" id="sp-versteck"' in html
    assert 'ks-raster nur-reachy' in html                                   # Reachys Kamera-Spiele bleiben seine
    modul = (STATIC / "modul.js").read_text(encoding="utf-8")
    assert "const NUR_REACHY = [];" in modul
    vr = (STATIC / "vr.js").read_text(encoding="utf-8")
    assert "isSecureContext" in vr and "'squeeze', notaus" in vr and "type: 'stop'" in vr and "NICHT" in vr
    assert "fetch(" not in vr and "WebSocket" not in vr
    js = (STATIC / "spiele_alle.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "fetch(" not in js
    assert (STATIC / "app.js").stat().st_size < 73728
