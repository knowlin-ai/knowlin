"""Reachy Mini steht auf dem Couchtisch (seit 0.38.10) – und lässt sich im Simulator umstellen.

Reachy Mini ist ein Tischroboter ohne Räder. Im Simulator stand er am Startplatz der Ente auf dem Boden; jetzt steht er
standardmäßig auf dem Couchtisch (40 cm hoch, Blick zum Sofa). Im Menü eines Möbelstücks: „Reachy hierhin stellen“
bzw. „Reachy auf den Boden stellen“ – nur mit Reachy im Simulator.
"""

import asyncio
import math

from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.api import DuckState
from duckpilot.backends.reachy import FUSS_M, STANDARD_FLAECHE, ReachyMiniSim
from duckpilot.backends.sim import SimBackend
from duckpilot.backends.world import Box
from duckpilot.brain import handeln as H
from duckpilot.motion.engine import head_towards


def _sim():
    sim = ReachyMiniSim(realtime=False, seed=1)
    sim._task = object()
    return sim


def _welt(sim, name):
    return next(m for m in [*sim.world_model.boxes, *sim.world_model.cylinders] if m.name == name)


def test_standardplatz_auf_dem_couchtisch_mit_blick_zum_sofa():
    sim = _sim()
    tisch, sofa = _welt(sim, "Couchtisch"), _welt(sim, "Sofa")
    assert STANDARD_FLAECHE == "Couchtisch" and sim.standflaeche == "Couchtisch"
    assert (sim.x, sim.y) == (tisch.x, tisch.y)
    st = sim.state()
    assert st.stand_z == tisch.h == 0.4 and st.standflaeche == "Couchtisch"
    zum_sofa = math.atan2(sofa.y - sim.y, sofa.x - sim.x)
    assert math.cos(sim.yaw - zum_sofa) > 0.999 and sim.yaw0 == sim.yaw
    assert st.to_dict()["stand_z"] == 0.4                     # geht so an die Oberfläche (3D: Standhöhe)
    assert DuckState().stand_z == 0.0                         # die Ente bleibt am Boden


def test_platzieren_auf_hocker_und_boden():
    sim = _sim()
    ok, text = sim.platzieren("Hocker")
    hocker = _welt(sim, "Hocker")
    assert ok and "Hocker" in text
    assert (sim.x, sim.y, sim.state().stand_z) == (hocker.x, hocker.y, hocker.h)
    ok, text = sim.platzieren("boden")
    st = sim.state()
    assert ok and st.stand_z == 0.0 and st.standflaeche == "" and "Boden" in text
    assert sim.world_model.collide(sim.x, sim.y, FUSS_M) is None          # frei am Boden, nicht im Möbel
    assert math.hypot(sim.x - hocker.x, sim.y - hocker.y) < 0.6           # gleich vor dem Hocker


def test_unpassende_flaechen_abgelehnt():
    sim = _sim()
    vorher = (sim.x, sim.y, sim.stand_z)
    sim.world_model.boxes.append(Box("Beistelltisch", -1.0, 0.6, 0.1, 0.12, 0.5))
    for name, wort in (("Pflanze", "nicht sicher"), ("Sofa", "nicht sicher"), ("Beistelltisch", "zu klein"),
                       ("Mond", "Kenne keine")):
        ok, grund = sim.platzieren(name)
        assert not ok and wort in grund, (name, grund)
    assert (sim.x, sim.y, sim.stand_z) == vorher                          # bleibt, wo er war
    assert sim.platz_pruefen("Kiste") is None and sim.platz_pruefen("Couchtisch") is None


def test_szene_zuruecksetzen_stellt_ihn_auf_den_tisch():
    sim = _sim()
    sim.platzieren("boden")
    out = sim.szene_zuruecksetzen()
    assert out["ok"] and out["ente"] and sim.standflaeche == "Couchtisch" and sim.state().stand_z == 0.4


def test_menue_nur_mit_reachy_im_simulator():
    sim = _sim()
    tisch = H.ding_finden("Couchtisch", sim)
    hocker = H.ding_finden("Hocker", sim)
    assert [a["id"] for a in H.reachy_aktionen(tisch, sim)] == ["reachy_boden"]     # steht schon drauf
    assert [a["id"] for a in H.reachy_aktionen(hocker, sim)] == ["reachy_stellen"]
    assert H.reachy_aktionen(H.ding_finden("Pflanze", sim), sim) == []
    assert H.reachy_aktionen(H.ding_finden("Ball", sim), sim) == []
    ente = SimBackend(realtime=False)
    assert H.reachy_aktionen(H.ding_finden("Hocker", ente), ente) == []
    assert not H.reachy_platzieren(ente, "Hocker", "reachy_stellen")["ok"]
    r = H.reachy_platzieren(sim, "Hocker", "reachy_stellen")
    assert r["ok"] and sim.standflaeche == "Hocker"
    assert H.reachy_platzieren(sim, "Hocker", "reachy_boden")["ok"] and sim.stand_z == 0.0
    assert not H.reachy_platzieren(sim, "Pflanze", "reachy_stellen")["ok"]


def test_route_reachy_hierhin_stellen(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("DUCKPILOT_OFFLINE", "1")
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        ids = [a["id"] for a in c.get("/api/handeln?ding=Hocker").json()["aktionen"]]
        assert "reachy_stellen" not in ids                                 # die Ente ist der Körper
        assert c.post("/api/handeln", json={"ding": "Hocker", "aktion": "reachy_stellen"}).status_code == 409
        ente = rt.backend
        rt.backend = ReachyMiniSim(realtime=False, seed=1)                   # jetzt ist Reachy der Körper
        ids = [a["id"] for a in c.get("/api/handeln?ding=Hocker").json()["aktionen"]]
        assert "reachy_stellen" in ids
        r = c.post("/api/handeln", json={"ding": "Hocker", "aktion": "reachy_stellen"})
        assert r.status_code == 200 and r.json()["ok"] and rt.backend.standflaeche == "Hocker"
        r = c.post("/api/handeln", json={"ding": "Pflanze", "aktion": "reachy_stellen"})
        assert r.status_code == 409
        rt.backend = ente


def test_blick_rechnet_die_standhoehe_ein():
    """Vom Tisch aus schaut er zu einem Ding am Boden deutlicher nach unten als vom Boden aus."""
    boden = DuckState(x=0.0, y=0.0, yaw=0.0)
    tisch = DuckState(x=0.0, y=0.0, yaw=0.0, stand_z=0.4)
    punkt = (0.8, 0.0, 0.0)
    assert head_towards(tisch, punkt)[0].head_pitch > head_towards(boden, punkt)[0].head_pitch + 0.2


def test_gaeste_bleiben_am_boden_und_stossen_sich_nicht_am_tisch_reachy():
    from duckpilot.motion.schwarm import Schwarm

    sim = _sim()
    schwarm = Schwarm(sim, None, lambda i, x, y, yaw: SimBackend(realtime=False))
    assert "haupt" in [k for k, _, _ in schwarm._alle()]                 # sehen und begrüßen kann man ihn weiter
    assert "haupt" not in [k for k, _, _ in schwarm._alle(boden=True)]   # aber kein Hindernis am Boden
    sim.platzieren("boden")
    assert "haupt" in [k for k, _, _ in schwarm._alle(boden=True)]


def test_auf_dem_tisch_schiebt_er_nichts_am_boden():
    sim = _sim()
    ball = next(i for i in sim.world_model.items if i.kind == "ball")
    ball.x, ball.y = sim.x + 0.05, sim.y                                   # liegt „unter“ ihm (am Boden)
    sim._push_items()
    assert (ball.x, ball.y) == (sim.x + 0.05, sim.y)

    async def go():
        for _ in range(10):
            sim.step(0.05)
    asyncio.run(go())
    assert sim.state().stand_z == 0.4 and sim.standflaeche == "Couchtisch"
