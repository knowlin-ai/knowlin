"""0.37: Sichtungen („Wo zuletzt gesehen?“), Kartierungsmodus mit A*-Routen, Raum-Route nur am PC, Zwilling."""

import asyncio
import math

from fastapi.testclient import TestClient
from helpers import make, run_for

from duckpilot.brain.fallback import parse
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion import behaviors as B
from duckpilot.motion.karte import Karte, Route, zelle
from duckpilot.physics import zwilling as Z
from duckpilot.sichtungen import Sichtungen, wie_lange


class _P:
    def __init__(self, objects):
        self.objects = objects
        self.points = []


class _St:
    def __init__(self, objects, x=0.0, y=0.0, yaw=0.0):
        self.x, self.y, self.yaw = x, y, yaw
        self.perception = _P(objects)


def test_sichtungen_merken_dinge_aber_nie_menschen(tmp_path):
    s = Sichtungen(tmp_path / "s.json")
    st = _St([{"name": "Socke", "art": "sock", "entfernung_m": 0.47, "richtung_grad": 0},
              {"name": "Sofa", "art": "möbel", "entfernung_m": 0.9, "richtung_grad": 5},
              {"name": "Mensch", "art": "person", "entfernung_m": 1.0, "richtung_grad": 0},
              {"name": "Laserpunkt", "art": "laser", "entfernung_m": 1.0, "richtung_grad": 0}])
    assert s.beobachte(st, 1000.0) == 2
    assert set(s.daten) == {"Socke", "Sofa"} and math.isclose(s.daten["Socke"]["x"], 0.5)
    a = s.antwort("Wo hast du die Socke zuletzt gesehen?", jetzt=1180.0)
    assert a["gefunden"] and a["text"] == "Die Socke habe ich zuletzt vor 3 Minuten gesehen, beim Sofa."
    assert s.antwort("where is the sock", en=True, jetzt=1010.0)["text"]== "I last saw the sock just now, near the sofa."
    assert not s.antwort("Wo ist der Schlüssel?")["gefunden"]
    s.speichern()
    neu = Sichtungen(tmp_path / "s.json")
    assert set(neu.daten) == {"Socke", "Sofa"}
    assert "Mensch" not in (tmp_path / "s.json").read_text("utf-8")
    assert wie_lange(10) == "gerade eben" and wie_lange(7200) == "vor 2 Stunden" and wie_lange(90000) == "gestern"


def test_wo_gesehen_ohne_claude_nach_einem_rundgang():
    async def go():
        sim, eng = await make()
        runner = ToolRunner(eng)

        class Raum:
            sichtungen = Sichtungen()
            karte = Karte()
        runner.raum = Raum()
        rundgang = B.Explore(20)
        rundgang.rng.seed(3)
        eng.run(rundgang)
        await run_for(sim, eng, 20, until=lambda: Raum.sichtungen.beobachte(sim.state()) < 0)
        assert Raum.sichtungen.liste(), "auf dem Rundgang nichts gesehen"
        ding = Raum.sichtungen.liste()[0]
        r = await runner.run("wo_gesehen", {"ding": f"wo ist {ding}"})
        assert r["gefunden"] and ding in r["text"]
        r = await runner.run("wo_gesehen", {"ding": ding, "hingehen": True})
        assert r["gefunden"] and r.get("gestartet")
    asyncio.run(go())


def test_karte_aus_dem_rundgang_und_route_um_den_tisch():
    async def go():
        sim, eng = await make()
        k = Karte()
        n = {"i": 0}

        def messen():
            n["i"] += 1
            if n["i"] % 4 == 0:
                st = sim.state()
                k.eintragen(st.x, st.y, st.perception.points)
            return False
        rundgang = B.Explore(60)
        rundgang.rng.seed(3)                         # derselbe Rundgang bei jedem Lauf
        eng.run(rundgang)
        await run_for(sim, eng, 60, until=messen)
        assert k.flaeche_m2() > 2.0 and len(k.to_dict()["belegt"]) > 30
        # Wand belegt, Raummitte frei
        assert any(k.belegt(zelle(x, 1.49)) or k.belegt(zelle(x, -1.49)) for x in (-1.0, 0.0, 1.0))
        eng.cancel_current("test")
        r = Route(k, (1.2, 0.6), "Ziel")
        eng.run(r)
        await run_for(sim, eng, 60, until=lambda: r.done)
        assert r.result == "angekommen" and math.hypot(sim.x - 1.2, sim.y - 0.6) < 0.1
    asyncio.run(go())


def test_astar_weicht_einer_wand_aus():
    k = Karte()
    for j in range(-10, 11):                         # Wand bei x = 0 von y −0,5 … 0,5
        for _ in range(3):
            k.zellen[(0, j)] = 3.0
    weg = k.route((-0.5, 0.0), (0.5, 0.0))
    assert weg and weg[-1] == (0.525, 0.025)
    assert any(abs(y) > 0.5 for _, y in weg)          # außen herum
    k2 = Karte.laden(__import__("pathlib").Path("/nicht/da"))
    assert k2.messungen == 0


def test_kartieren_per_sprache_und_raum_nur_am_pc():
    assert parse("kartiere das Zimmer")[0] == ("karte", {"aktion": "start", "sekunden": 120})
    assert parse("map the room for 3 minutes")[0] == ("karte", {"aktion": "start", "sekunden": 180})
    from duckpilot.remote import pc_only
    assert pc_only("GET", "/api/raum") and pc_only("POST", "/api/raum")


def test_raum_route(tmp_path):
    from duckpilot.config import load
    from duckpilot.server.app import create_app
    from duckpilot.server.runtime import Runtime

    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        d = c.get("/api/raum", headers={"Origin": "http://127.0.0.1:8765"}).json()
        assert {"kartiert", "flaeche_m2", "karte", "sichtungen"} <= set(d)
        r = c.post("/api/raum", json={"aktion": "sichtungen_vergessen"}, headers={"Origin": "http://127.0.0.1:8765"})
        assert r.json()["ok"]
        assert c.post("/api/raum", json={"aktion": "gibts-nicht"},
                      headers={"Origin": "http://127.0.0.1:8765"}).status_code == 400


def test_zwilling_abgleich_findet_verzoegerung_und_versatz():
    assert 60 < Z.messlauf_dauer_s() < 90 and len(Z.MESSLAUF) == 10
    soll = Z.sollkurve(Z.MESSLAUF[3])
    assert max(abs(x) for x in soll) <= Z.AUSLENKUNG_RAD + 1e-9
    gleich = Z.servo_modell(soll)
    traege = Z.servo_modell(soll, verzoegerung_s=0.1, versatz=math.radians(5))
    erg = Z.abgleich({"left_knee": {"soll": soll, "ist": gleich}, "right_knee": {"soll": soll, "ist": traege},
                      "neck_pitch": {"soll": soll, "ist": gleich}})
    assert erg["gesamt"] == 2 and erg["passen"] == 1                       # Hals ist kein Beingelenk
    r = erg["gelenke"]["right_knee"]
    assert not r["passt"] and {"verzoegerung_ms", "versatz_grad"} <= set(r["auffaellig"])
    assert 4.5 < r["versatz_grad"] < 5.5
    p = Z.profil(erg)
    assert set(p["gelenke"]) == {"left_knee", "right_knee"} and p["art"] == "duckpilot-zwilling"


def test_erkunden_geht_gezielt_an_die_raender():
    """0.37.13 (Anna: „beim Kartieren nicht so sehr gründlich“): gezielt an unerkundete Ränder statt Zufallslauf –
    in zwei Minuten der größte Teil des Wohnzimmers (4 × 3 m, davon ≈ 10 m² frei)."""
    import asyncio

    from helpers import make

    from duckpilot.motion.erkunden import Erkunden, grenzen
    from duckpilot.motion.karte import Karte

    k0 = Karte()
    k0.zellen = {(0, 0): -3.0, (1, 0): -3.0, (0, 1): 3.0}
    assert (0, 0) in grenzen(k0) and (0, 1) not in grenzen(k0)       # nur freie Zellen am Unbekannten

    async def go():
        sim, eng = await make(zufall=2)
        k = Karte()
        b = Erkunden(k, 120)
        eng.run(b)
        for i in range(125 * 20):
            await eng.tick(0.05)
            await asyncio.sleep(0)
            sim.step(0.025)
            sim.step(0.025)
            if i % 2 == 0:
                st = sim.state()
                k.eintragen(st.x, st.y, st.perception.points)
            if b.done:
                break
        return k, b
    k, b = asyncio.run(go())
    assert k.flaeche_m2() >= 8.5 and b.ziele >= 5, (k.flaeche_m2(), b.ziele, b.result)


def test_karte_lernt_auch_beim_fahren_von_hand_und_nie_hinter_der_wand(tmp_path):
    """Gemeldet nach 0.38.32: „Wieso erkennt er nicht weiter, wenn er manuell was sieht?“ und freie Zellen außerhalb
    des Raums (Treffer am Fuß der Wand fielen in die Zelle dahinter)."""
    from duckpilot.backends.sim import SimBackend
    from duckpilot.server.raum import Raum

    raum = Raum(tmp_path, "duckpilot")
    sim = SimBackend(realtime=False, seed=1)
    sim.x, sim.y, sim.yaw = 1.8, 0.0, 0.0                       # dicht vor der rechten Wand (x = 2,0), Blick hin
    sim._update_tof()
    st = sim.state()
    st.connected = True
    assert not raum.kartiert and st.perception.points
    raum.tick(st)
    assert raum.karte.messungen == 1 and raum.karte.flaeche_m2() > 0      # ohne „Raum erkunden“
    w = sim.world_model.width / 2
    assert not [c for c, v in raum.karte.zellen.items() if v < -0.4 and (c[0] + 0.5) * 0.05 > w]
    st.picked_up = True
    raum.tick(st)
    assert raum.karte.messungen == 1                                       # hochgehoben: Standort unsicher
