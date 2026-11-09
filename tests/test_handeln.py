"""Anwählen und Handeln (0.37.3): Dinge, Möbel und andere Enten anwählen, passende Handlungen, Begegnungen."""

import asyncio
import math

from fastapi.testclient import TestClient
from helpers import make, run_for

from duckpilot.backends.begleiter import Begleitente
from duckpilot.brain import handeln as H
from duckpilot.brain.fallback import parse
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion.handeln import Begegnung, Hinterher
from duckpilot.motion.schwarm import Schwarm
from duckpilot.server.oberflaeche import seite


async def _mit_ente(x=0.4, y=-0.1):
    sim, eng = await make()
    sw = Schwarm(sim, eng, lambda i, a, b, yaw: Begleitente(sim.world_model, i, a, b, yaw))
    sim.nach_schritt.append(sw.step)
    sw.anzahl(1)
    sw.setze_modus("sitzen")                       # bleibt, wo sie ist
    e = sw.enten[0]
    e.x, e.y = x, y
    sw.setze_modus("frei")
    sw._ziel[e.nummer] = (x, y, 1e9)               # will nirgendwohin
    return sim, eng, sw, e


def test_handlungen_passen_zur_art():
    assert [a["id"] for a in H.aktionen("ball")][:2] == ["zielen", "schiessen"]   # „Schießen auf …“ seit 0.37.9
    assert "aufheben" in [a["id"] for a in H.aktionen("figur")] and "bringen" in [a["id"] for a in H.aktionen("sock")]
    assert {"begruessen", "aergern", "folgen"} <= {a["id"] for a in H.aktionen("ente")}
    assert H.aktionen("person") == []                       # Menschen werden nicht „behandelt“
    assert H.werkzeug("Ball", "ball", "aufheben") is None   # passt nicht zur Art
    assert H.werkzeug("Socke", "sock", "bringen") == ("apportieren", {"ding": "socke"})


def test_auswahl_im_chat():
    sel = {"name": "Klemmbaustein"}
    assert H.mit_auswahl("heb das auf", sel) == "heb das auf (gemeint: Klemmbaustein)"
    assert H.mit_auswahl("lauf vor", sel) == "lauf vor"                       # nichts, worauf es zeigt
    assert H.mit_auswahl("heb den Klemmbaustein auf", sel) == "heb den Klemmbaustein auf"
    assert H.mit_auswahl("heb das auf", None) == "heb das auf"
    assert parse(H.mit_auswahl("heb das auf", sel))[0] == ("_pick", {"target": "klemmbaustein"})
    assert parse("ärgere Kiki")[0] == ("handeln", {"ding": "kiki", "aktion": "aergern"})
    assert parse("say hello to Pip")[0] == ("handeln", {"ding": "pip", "aktion": "begruessen"})
    assert parse("hallo")[0] == ("emote", {"emotion": "begruessen"})        # ohne Ente bleibt es ein Gruß
    assert parse("folg mir")[0][0] == "mir_folgen"


def test_hauptente_sieht_andere_enten_und_aergert_eine():
    async def go():
        sim, eng, sw, e = await _mit_ente()
        await run_for(sim, eng, 0.5)
        assert any(o["art"] == "ente" and o["name"] == e.ente_name for o in sim.state().perception.objects)
        assert H.ding_finden("kiki", sim, sw)["art"] == "ente"
        b = Begegnung(e.ente_name, "aergern", sw.reagiere)
        eng.run(b)
        await run_for(sim, eng, 40, until=lambda: b.done)
        assert b.result == f"{e.ente_name} geärgert", b.result
        assert any("protestiert" in str(ev.get("message", "")) for ev in eng.events)
    asyncio.run(go())


def test_reaktion_gruss_und_aergern():
    async def go():
        sim, eng, sw, e = await _mit_ente()
        x0 = e.x
        assert sw.reagiere(e.ente_name, "aergern", (x0 - 0.3, e.y)) == f"{e.ente_name} protestiert"
        assert sw.uebersicht()[0]["tut"] == "protestiert"
        await run_for(sim, eng, 2.6)
        assert e.x > x0 + 0.02                       # weicht zurück, weg von der Hauptente
        assert sw.reagiere("Niemand", "gruss", (0, 0)) is None
    asyncio.run(go())


def test_hinterher_folgt_mit_abstand():
    async def go():
        sim, eng, sw, e = await _mit_ente(0.6, 0.0)
        b = Hinterher(e.ente_name, 8)
        eng.run(b)
        await run_for(sim, eng, 8, until=lambda: b.done)
        d = math.hypot(sim.x - e.x, sim.y - e.y)
        assert 0.2 < d < 0.6, d
    asyncio.run(go())


def test_werkzeug_handeln():
    async def go():
        sim, eng, sw, e = await _mit_ente()
        r = ToolRunner(eng)
        r.schwarm = sw
        assert (await r.run("handeln", {"ding": "Ball", "aktion": "schiessen"}))["ok"]
        res = await r.run("handeln", {"ding": "Ball", "aktion": "aufheben"})
        assert res["ok"] is False and "schiessen" in res["moeglich"]
        assert (await r.run("handeln", {"ding": "Gibtsnicht", "aktion": "hinlaufen"}))["ok"] is False
        assert (await r.run("handeln", {"ding": e.ente_name, "aktion": "begruessen"}))["ok"]
    asyncio.run(go())


def test_route_handeln(tmp_path):
    from duckpilot.config import load
    from duckpilot.server.app import create_app
    from duckpilot.server.runtime import Runtime

    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        h = {"Origin": "http://127.0.0.1:8765"}
        d = c.get("/api/handeln?ding=Socke", headers=h).json()
        assert d["ok"] and d["ding"]["art"] == "sock" and d["aktionen"][0]["id"] == "aufheben"
        assert c.get("/api/handeln?ding=Mensch", headers=h).status_code == 404
        assert c.post("/api/handeln", json={"auswahl": "Sofa"}, headers=h).json()["auswahl"]["art"] == "möbel"
        assert rt.auswahl["name"] == "Sofa"
        assert c.post("/api/handeln", json={"auswahl": None}, headers=h).json()["auswahl"] is None
        # „Schießen auf …“ (seit 0.37.9): Ball angewählt, Ziel mit dem zweiten Klick
        r = c.post("/api/handeln", json={"ding": "Ball", "aktion": "zielen", "ziel": "Regal"}, headers=h).json()
        assert r.get("ok", True) and "Regal" in str(r), r
        assert rt.engine.current is not None and "Regal" in rt.engine.current.describe()


def test_oberflaeche_anwaehlen():
    from pathlib import Path

    static = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
    html = seite()
    app = (static / "app.js").read_text("utf-8")
    d3 = (static / "duck3d.js").read_text("utf-8")
    assert 'id="auswahl-pop"' in html and 'id="auswahl-chip"' in html
    assert "auswahl.klick(p, x, y);" in app and ".auswahl-pop'" in app
    assert "setAuswahl(sel)" in d3 and "out.name = best.name" in d3 and "o.userData.ente = e" in d3


def test_menue_bietet_nur_an_was_der_koerper_kann():
    """Frage 7.11.: „Manche Funktionen wie Aufheben kann sie [die Open Duck] doch gar nicht, oder?“ – richtig:
    ohne Schnabel kein Aufheben und kein Bringen; ohne Beine (Reachy) gar keine Handlung am Ding."""
    from duckpilot.backends.open_duck import OpenDuckSim
    from duckpilot.backends.reachy import ReachyMiniSim
    from duckpilot.backends.sim import SimBackend
    from duckpilot.motion.engine import MotionEngine

    ids = lambda art, be: [a["id"] for a in H.aktionen(art, be)]                       # noqa: E731
    assert "aufheben" in ids("sock", SimBackend(realtime=False)) and "bringen" in ids("sock", SimBackend(realtime=False))
    odi = OpenDuckSim(realtime=False)
    assert "aufheben" not in ids("sock", odi) and "bringen" not in ids("sock", odi)
    assert "hinlaufen" in ids("sock", odi) and "schiessen" in ids("ball", odi)
    assert ids("sock", ReachyMiniSim(realtime=False)) == []

    async def go():
        eng = MotionEngine(odi)
        r = await ToolRunner(eng).run("handeln", {"ding": "socke", "aktion": "aufheben"})
        assert not r["ok"] and "Schnabel" in r["fehler"] and "aufheben" not in r["moeglich"]
    asyncio.run(go())
