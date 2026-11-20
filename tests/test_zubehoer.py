"""Zubehör der Microduck (seit 0.47): Rollen im einfachen Simulator, Arena-Rennen, Polaroid."""

from __future__ import annotations

import asyncio
import math

import pytest
from helpers import make

from duckpilot import koerper as K
from duckpilot import rennen as R
from duckpilot.api import Twist
from duckpilot.backends.sim import SimBackend
from duckpilot.backends.world import World
from duckpilot.backends.zubehoer import AUSROLLEN, ROLLEN_FAKTOR


async def _bereit() -> SimBackend:
    sim, _ = await make()
    return sim


async def _fahren(sim: SimBackend, twist: Twist, sekunden: float) -> None:
    for _ in range(int(sekunden / 0.02)):
        await sim.move(twist)
        sim.step(0.02)


def test_nur_die_microduck_hat_das_zubehoer():
    assert set(K.holen("duckpilot").zubehoer) == {"rollen", "polaroid"}
    assert all(not k.zubehoer for k in K.alle() if k.id != "duckpilot")
    assert K.holen("duckpilot").als_dict()["zubehoer"] == ["rollen", "polaroid"]


def test_rollen_schneller_nie_seitwaerts_und_rollen_nach():
    async def go():
        sim = await _bereit()
        await _fahren(sim, Twist(0.3, 0.0, 0.0), 3)
        zu_fuss = sim.applied.vx
        await _fahren(sim, Twist(), 2)
        assert sim.rollen_anlegen(True).accepted
        assert sim.state().zubehoer == {"rollen": True, "geduckt": False}
        await _fahren(sim, Twist(0.3, 0.3, 0.0), 3)
        assert sim.applied.vx > zu_fuss * (ROLLEN_FAKTOR - 0.2)
        assert sim.applied.vy == 0.0                                   # seitwärts geht auf Rollen nicht
        v = sim.applied.vx
        await _fahren(sim, Twist(), 0.5)
        assert sim.applied.vx > v - AUSROLLEN * 0.5 - 0.02             # rollt nach statt hart zu bremsen
        assert not sim.rollen_anlegen(False).accepted                        # abnehmen nur im Stand
    asyncio.run(go())


def test_not_aus_auf_rollen_heisst_stillstand():
    async def go():
        sim = await _bereit()
        sim.rollen_anlegen(True)
        await _fahren(sim, Twist(0.3, 0.0, 0.0), 2)
        assert sim.applied.vx > 0.2
        sim.lahm()
        x = sim.x
        for _ in range(50):
            sim.step(0.02)
        assert sim.applied.vx == 0.0 and abs(sim.x - x) < 1e-6
    asyncio.run(go())


def test_mit_rollen_keine_tricks_am_boden_und_geduckt():
    async def go():
        sim = await _bereit()
        assert not sim.rollen_anlegen(False, geduckt=True).accepted         # geduckt ohne Rollen geht nicht
        sim.rollen_anlegen(True)
        r = await sim.do("kick_left")
        assert not r.accepted and "Rollen" in (r.reason or "")
        assert sim.rollen_anlegen(True, geduckt=True).accepted
        assert sim.state().zubehoer["geduckt"] is True
        sim.rollen_anlegen(False)
        assert sim.state().zubehoer == {}
    asyncio.run(go())


# ── Arena-Rennen ──────────────────────────────────────────────────────────
def test_strecke_ohne_moebel_im_weg():
    w = World.living_room()
    punkte = [(t["x"], t["y"]) for t in R.tore()] + [(R.STRECKE[0][0], R.STRECKE[0][1])]
    for (x1, y1), (x2, y2) in zip(punkte, punkte[1:]):
        for k in range(21):
            assert not w.collide(x1 + (x2 - x1) * k / 20, y1 + (y2 - y1) * k / 20, 0.09)


def _runde(fahrt: R.Zeitfahren, t0: float = 0.0) -> list[dict]:
    """Eine Runde auf der Ideallinie abfahren (kleine Schritte), Ereignisse sammeln."""
    pts = [(x - 0.3 * math.cos(r), y - 0.3 * math.sin(r)) for x, y, r, _ in R.STRECKE[:1]]
    for x, y, r, _ in list(R.STRECKE[1:]) + [R.STRECKE[0]]:
        pts.append((x - 0.15 * math.cos(r), y - 0.15 * math.sin(r)))
        pts.append((x + 0.15 * math.cos(r), y + 0.15 * math.sin(r)))
    pts.insert(1, (R.STRECKE[0][0] + 0.15, R.STRECKE[0][1]))
    ev, t = [], t0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        for k in range(1, 11):
            t += 0.05
            e = fahrt.takt(t, x1 + (x2 - x1) * k / 10, y1 + (y2 - y1) * k / 10)
            if e:
                ev.append(e)
    return ev


def test_zeitfahren_zaehlt_tore_der_reihe_nach(tmp_path):
    fahrt = R.Zeitfahren(art="rollen")
    ev = _runde(fahrt)
    assert ev[0].get("start") and ev[-1]["ziel"]
    assert [e["tor"] for e in ev] == [0, 1, 2, 3, 4, 0]
    assert fahrt.fertig and fahrt.fertig > 0 and fahrt.weg
    best = R.Bestzeiten(tmp_path)
    assert best.eintragen(fahrt)
    langsamer = R.Zeitfahren(art="rollen")
    _runde(langsamer)
    langsamer.fertig = fahrt.fertig + 1
    assert not best.eintragen(langsamer)
    assert best.ueberblick() == {"rollen": fahrt.fertig}
    assert best.geist("rollen")[0][0] == 0.0


def test_tor_auslassen_zaehlt_nicht():
    fahrt = R.Zeitfahren()
    fahrt.takt(0.0, -0.6, -0.45)
    assert fahrt.takt(0.1, -0.2, -0.45)["start"]
    assert fahrt.takt(0.2, -0.2, 0.7) is None                 # quer übers Feld – kein Tor
    assert fahrt.naechstes == 1
    assert fahrt.takt(0.3, -0.6, -0.45) is None               # rückwärts über den Start: kein Ziel
    assert R.art_von({"rollen": True, "geduckt": True}) == "geduckt" and R.art_von(None) == "zu_fuss"


def _selbst_fahren(rollen: bool) -> R.Zeitfahren:
    from helpers import run_for

    from duckpilot.motion.rennfahrt import Rennfahrt

    async def go():
        sim, eng = await make(zufall=1)                 # ohne Zufall der Engine (Leerlauf, Goofy): ein Weg
        if rollen:
            assert sim.rollen_anlegen(True).accepted
        fahrt = R.Zeitfahren(art=R.art_von(sim.state().zubehoer))
        b = Rennfahrt(fahrt)
        eng.run(b)

        def messen():
            st = sim.state()
            fahrt.takt(st.t, st.x, st.y)
            return fahrt.fertig is not None or b.done
        await run_for(sim, eng, 120, until=messen)
        assert not sim.fallen
        return fahrt
    return asyncio.run(go())


def test_selbst_fahren_schafft_die_runde_auf_rollen_schneller():
    zu_fuss = _selbst_fahren(False)
    auf_rollen = _selbst_fahren(True)
    assert zu_fuss.fertig and auf_rollen.fertig, (zu_fuss.naechstes, auf_rollen.naechstes)
    assert auf_rollen.fertig < zu_fuss.fertig


# ── Polaroid ──────────────────────────────────────────────────────────────
def test_traum_aus_dem_tag_ohne_erfinden():
    from duckpilot.traum import traum

    leer = traum({})
    assert leer["leer"] and "ruhigen Tag" in leer["text"]
    t = traum({"stimmung": "froh", "haeufig": [{"art": "gefuehl", "name": "Freude"}, {"art": "ding", "name": "Ball"},
                                               {"art": "ort", "name": "Sofa"}, {"art": "ding", "name": "Ball"}]})
    assert [m["wort"] for m in t["motive"]] == ["Ball", "Sofa"]
    assert t["motive"][0]["zeichen"] == "⚽" and "sonniger Traum" in t["text"]
    assert "Ball und Sofa" in t["text"]
    assert "dreamt of Ball and Sofa" in traum({"haeufig": [{"art": "ding", "name": "Ball"},
                                                         {"art": "ort", "name": "Sofa"}]}, en=True)["text"]


# ── Werkzeug und ohne Sprachmodell ───────────────────────────────────────
def test_werkzeug_nur_fuer_die_microduck_im_simulator():
    from duckpilot.brain.tools import ToolRunner, fehlt_dem_koerper
    from duckpilot.brain.tools_zubehoer import befehl

    assert befehl("Rollen an") == "rollen_an" and befehl("fahr Rollschuh") == "rollen_an"
    assert befehl("nimm die Rollen ab") == "rollen_ab" and befehl("Rollen ab") == "rollen_ab"
    assert befehl("mach eine Rolle") is None and befehl("wovon träumst du?") == "polaroid"
    assert befehl("fahr ein Rennen") == "rennen"

    async def go():
        sim, eng = await make()
        runner = ToolRunner(eng)
        assert fehlt_dem_koerper("zubehoer", sim) is None
        assert "zubehoer" in [t["name"] for t in runner.tools()]
        r = await runner._zubehoer_befehl("Rollen an")
        assert r["ok"] and sim.rollen
        r = await runner.run("zubehoer", {"aktion": "rennen"})
        assert not r["ok"] and "Server" in r["fehler"]
    asyncio.run(go())

    class Ohne:                       # z. B. das Physikmodell: Profil mit Zubehör, aber keine Rollen
        koerper_art = "microduck"

        def eigenschaften(self):
            return frozenset({"beine", "kopf"})
    assert "Physikmodell" in fehlt_dem_koerper("zubehoer", Ohne())


# ── Mit dem Server ───────────────────────────────────────────────────────
O = {"Origin": "http://127.0.0.1:8765"}


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


def test_server_rollen_rennen_polaroid(client):
    s = client.get("/api/zubehoer").json()
    assert s["verfuegbar"] and len(s["tore"]) == len(R.STRECKE) and s["bestzeiten"] == {}
    r = client.post("/api/zubehoer/rollen", json={"an": True}, headers=O)
    assert r.status_code == 200 and r.json()["zubehoer"]["rollen"]
    r = client.post("/api/zubehoer/polaroid", json={}, headers=O)
    assert r.status_code == 200 and r.json()["text"] and r.json()["motive"]
    r = client.post("/api/zubehoer/rennen", json={"aktion": "start"}, headers=O)
    assert r.status_code == 200 or "aufwecken" in r.json()["fehler"]
    assert client.post("/api/zubehoer/rennen", json={"aktion": "stopp"}, headers=O).json()["ok"]
    client.runtime.engine.notaus_gesperrt = lambda: True
    r = client.post("/api/zubehoer/rennen", json={"aktion": "start"}, headers=O)
    assert r.status_code == 400 and "Not-Aus" in r.json()["fehler"]
