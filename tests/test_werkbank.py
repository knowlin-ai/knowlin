"""Werkbank des SO-101 (seit 0.38.48). Wunsch des Maintainers: „die Roboterarme auf einer eigenen Plattform, wo in
Reichweite auch greifbare Objekte oder Boxen sind, wo man Sachen rein- und rausmachen kann“."""

import asyncio
import json
import struct
from pathlib import Path

import numpy as np

from duckpilot import arm_kinematik as K
from duckpilot.backends.so101 import So101Sim
from duckpilot.backends.werkbank import GREIFER_AUF, WERKBANK, startbelegung
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion.engine import MotionEngine

MODELL = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "model" / "so101.dpm"


def _laufen(sim, sekunden):
    for _ in range(int(sekunden / 0.05)):
        sim.step(0.05)


async def _wach():
    sim = So101Sim(realtime=False)
    await sim.init()
    _laufen(sim, 1.5)
    return sim


def test_kette_wie_im_gebackenen_modell():
    b = MODELL.read_bytes()
    n = struct.unpack("<I", b[4:8])[0]
    bodies = {x["name"]: x for x in json.loads(b[8:8 + n])["bodies"]}
    for name, _, pos, quat, gelenk in K.KETTE:
        assert np.allclose(bodies[name]["pos"], pos, atol=1e-6) and np.allclose(bodies[name]["quat"], quat, atol=1e-6)
        assert bodies[name]["joint"] == gelenk
    assert np.allclose(bodies["gripper"]["sites"]["gripperframe"], K.GRIPPERFRAME, atol=1e-6)


def test_greifhaltung_trifft_von_oben_und_kennt_ihre_grenzen():
    dinge, kisten = startbelegung()
    for d in dinge:
        for z in (d["z"], 0.10):
            g = K.greifhaltung(d["x"], d["y"], z)
            assert g is not None, (d["name"], z)
            p, richtung = K.spitze(g)
            assert np.linalg.norm(p - [d["x"], d["y"], z]) < K.GENAU_M and richtung[2] < -0.95
    for k in kisten:
        assert K.greifhaltung(k["x"], k["y"], k["h"] + 0.02) is not None
    assert K.greifhaltung(0.6, 0.0, 0.0) is None                     # zu weit
    assert K.greifhaltung(0.02, 0.0, 0.0) is None                    # im eigenen Sockel


def test_wuerfel_in_die_kiste_und_zurueck():
    async def go():
        sim = await _wach()
        assert sim.standflaeche == "Werkbank" and sim.stand_z == WERKBANK["h"]
        assert (await sim.greifen("roter Würfel")).accepted
        _laufen(sim, 3.5)
        assert sim.state().holding == "roter Würfel"
        schon = await sim.greifen("blau")
        assert not schon.accepted and "halte schon den roten Würfel" in schon.reason   # Akkusativ (Fund 12.11.)
        assert (await sim.ablegen("linke Kiste")).accepted
        _laufen(sim, 4.5)
        rot = sim.werkbank.ding("rot")
        assert sim.werkbank.haelt is None and rot["in"] == "linke Kiste"
        assert (await sim.greifen("rot")).accepted                     # wieder heraus …
        _laufen(sim, 3.5)
        assert (await sim.ablegen("Platz")).accepted                   # … und an seinen Platz
        _laufen(sim, 4.5)
        assert rot["in"] is None and [rot["x"], rot["y"]] == rot["start"]
        nein = await sim.greifen("lila Würfel")                       # seit 0.38.54 gibt es einen grünen
        assert not nein.accepted and "roter Würfel" in nein.reason
        assert not (await sim.ablegen("linke Kiste")).accepted         # hält nichts
        assert sim.state().werkbank["kisten"][0]["name"] == "linke Kiste"
    asyncio.run(go())


def test_not_aus_und_offener_greifer_lassen_fallen():
    async def go():
        sim = await _wach()
        await sim.greifen("blauer Würfel")
        _laufen(sim, 3.5)
        await sim.relax()                                              # Not-Aus beim Tragen
        blau = sim.werkbank.ding("blau")
        assert sim.werkbank.haelt is None and blau["z"] == 0.015 and blau["in"] is None
        assert not (await sim.greifen("blau")).accepted                # ohne Strom greift er nichts
        await sim.init()
        _laufen(sim, 1.5)
        await sim.greifen("gelb")
        _laufen(sim, 3.5)
        await sim.haltung({"greifer": GREIFER_AUF})                    # Greifer auf: es fällt
        _laufen(sim, 1.2)
        assert sim.werkbank.haelt is None
    asyncio.run(go())


def test_eigener_platz_und_zuruecksetzen():
    async def go():
        sim = await _wach()
        ok, grund = sim.platzieren("Couchtisch")
        assert not ok and "Werkbank" in grund
        assert any(b.name == "Werkbank" for b in sim.world_model.boxes)
        await sim.greifen("rot")
        _laufen(sim, 3.5)
        sim.szene_zuruecksetzen()
        assert sim.werkbank.haelt is None and sim.werkbank.ding("rot")["x"] == sim.werkbank.ding("rot")["start"][0]
    asyncio.run(go())


def test_werkzeuge_greifen_und_ablegen():
    async def go():
        sim = So101Sim(realtime=False)
        eng = MotionEngine(sim)
        r = ToolRunner(eng)
        werkzeuge = {t["name"]: t for t in r.tools()}
        assert "roter Würfel" in werkzeuge["greifen"]["description"]
        assert "linke Kiste" in werkzeuge["ablegen"]["description"]
        await sim.init()
        _laufen(sim, 1.5)
        assert (await r.run("greifen", {"ding": "roter Würfel"}))["ok"]
        weit = await r.run("ablegen", {"ziel": "Mond"})
        assert not weit["ok"]
        bild = await r.run("selbstbild", {})
        assert bild["werkbank"]["kisten"] == ["linke Kiste", "rechte Kiste"]
        eng.notaus()
        assert not (await r.run("greifen", {"ding": "blau"}))["ok"]     # Sperre nach dem Not-Aus
    asyncio.run(go())


def test_zustand_sagt_den_wuerfel_richtig():
    """Fund 12.11.: Unter dem Zustand stand „hält roter Würfel“, und das Sprachmodell las „im Schnabel“ – der Arm hat
    keinen Schnabel. Jetzt: „hält den roten Würfel im Greifer“; die Ente behält ihren Schnabel."""
    from duckpilot.api import DuckState

    sim = So101Sim(realtime=False)
    st = sim.state()
    st.holding, st.connected = "roter Würfel", True
    st.werkbank = sim.werkbank.als_dict()
    assert st.summary().endswith("hält den roten Würfel im Greifer")
    ente = DuckState(connected=True, holding="Ball")
    assert ente.summary().endswith("hält Ball im Schnabel")


def test_wuerfel_und_kisten_anklicken():
    """Fund 12.11.: Beim Klick auf die Werkbank stand „Reachy auf den Boden stellen“, Würfel ließen sich nicht greifen.
    Jetzt sind Würfel und Kisten anklickbar, das Menü bietet Greifen und Ablegen, und Ari bleibt an seiner Werkbank."""
    from duckpilot.brain import handeln as H

    sim = So101Sim(realtime=False)
    werkbank = H.ding_finden("Werkbank", sim)
    assert H.reachy_aktionen(werkbank, sim) == []                       # kein „auf den Boden stellen“
    rot = H.ding_finden("roter Würfel", sim)
    assert rot["art"] == "wuerfel" and rot.get("werkbank")
    assert [a["id"] for a in H.werkbank_aktionen(rot, sim)] == ["greifen"]
    links = H.ding_finden("linke Kiste", sim)
    assert links["art"] == "kiste" and H.werkbank_aktionen(links, sim) == []       # nichts in der Hand
    assert H.werkbank_werkzeug(rot, "greifen") == ("greifen", {"ding": "roter Würfel"})

    async def go():
        await sim.init()
        _laufen(sim, 1.5)
        assert (await sim.greifen("roter Würfel")).accepted
        _laufen(sim, 4.0)
        assert sim.werkbank.haelt == "roter Würfel"
        ids = [a["id"] for a in H.werkbank_aktionen(rot, sim)]
        assert ids[0] == "platz" and "hineinlegen:linke Kiste" in ids
        assert [a["id"] for a in H.werkbank_aktionen(links, sim)] == ["hineinlegen"]
        blau = [a["id"] for a in H.werkbank_aktionen(H.ding_finden("blauer Würfel", sim), sim)]
        assert blau == ["stapeln"]                                      # nicht greifen, aber darauf stellen (0.38.54)
        assert H.werkbank_werkzeug(links, "hineinlegen") == ("ablegen", {"ziel": "linke Kiste"})
        assert H.werkbank_werkzeug(rot, "hineinlegen:rechte Kiste") == ("ablegen", {"ziel": "rechte Kiste"})
    asyncio.run(go())


def test_reachy_darf_weiter_auf_den_boden():
    from duckpilot.backends.reachy import ReachyMiniSim
    from duckpilot.brain import handeln as H

    sim = ReachyMiniSim(realtime=False)
    tisch = H.ding_finden(sim.standflaeche, sim)
    assert [a["id"] for a in H.reachy_aktionen(tisch, sim)] == [H.REACHY_BODEN[0]]
