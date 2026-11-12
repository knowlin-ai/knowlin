"""SO-101 als neuer Körper im Simulator (seit 0.38.47, Etappe G5 aus dem Konzept „Knowlins Kopf“): derselbe Kopf mit
einem Arm statt einer Ente – der Aktionskatalog grüßt mit Winken, Kopf-Werkzeuge gibt es nicht, der Not-Aus gewinnt."""

import asyncio
import json
import struct
from pathlib import Path

from duckpilot import arm as A
from duckpilot import koerper
from duckpilot.backends.so101 import So101Sim
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion.engine import MotionEngine

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def _laufen(sim, sekunden):
    for _ in range(int(sekunden / 0.05)):
        sim.step(0.05)


def test_profil_und_figur():
    from duckpilot.figuren import figur, ist_ente

    p = koerper.holen("so101")
    assert p.fehler() == [] and p.familie == "arm" and p.faehigkeiten == {"arm", "greifer"}
    assert p.lizenz == "Apache-2.0" and p.quelle.startswith("https://github.com/TheRobotStudio/")
    assert figur("so101")["name"] == "Ari" and not ist_ente("so101")


def test_aufwecken_geste_und_not_aus():
    async def go():
        sim = So101Sim(realtime=False)
        assert sim.sitting and not sim.powered and sim.standflaeche == "Werkbank"           # eigene Werkbank (0.38.48)
        assert not (await sim.geste("winken")).accepted                 # Motoren aus: nichts bewegt sich
        assert (await sim.init()).accepted
        _laufen(sim, 1.5)
        assert abs(sim.gelenke["shoulder_lift"] - A.POSEN["bereit"]["shoulder_lift"]) < 0.5
        r = await sim.geste("winken")
        assert r.accepted and sim.geste_name == "winken"
        _laufen(sim, A.dauer("winken") + 0.3)
        assert sim.geste_name is None and sim.state().skill is None
        await sim.geste("winken")
        _laufen(sim, 0.5)
        await sim.relax()                                               # Not-Aus mitten in der Geste
        assert not sim.powered and sim.geste_name is None
        assert not (await sim.haltung({"greifer": 50})).accepted
        _laufen(sim, 1.5)
        assert all(abs(sim.gelenke[g] - A.POSEN["ruhe"][g]) < 0.5 for g in A.GELENKE)   # sackt in die Ruhelage
        st = sim.state()
        assert st.koerper == "so101" and len(st.display_joints) == 6 and not st.powered
    asyncio.run(go())


def test_grenzen_und_namen():
    ziel, unbekannt = A.begrenzen({"greifer": 500, "shoulder_pan": -500, "ellbogen": 10, "nase": 3, "wrist_roll": True})
    assert ziel == {"gripper": 99.0, "shoulder_pan": -109.0, "elbow_flex": 10.0}
    assert unbekannt == ["nase", "wrist_roll"]
    for name, folge in A.GESTEN.items():                                # jede Geste bleibt in den Grenzen
        for haltung, s in folge:
            assert s > 0 and A.begrenzen(haltung) == (haltung, []), name


def test_werkzeuge_fuer_einen_arm():
    async def go():
        sim = So101Sim(realtime=False)
        eng = MotionEngine(sim)
        r = ToolRunner(eng)
        namen = {t["name"] for t in r.tools()}
        assert {"arm", "absicht", "selbstbild"} <= namen
        assert not namen & {"head", "look_around", "emote", "dance", "choreo", "turn", "walk", "sound"}
        assert (await r.run("emote", {"emotion": "freude"}))["ok"] is False
        await sim.init()
        gruss = await r.run("absicht", {"aktion": "gruessen"})
        assert gruss["ok"] and gruss["antwort"] == "ersatz" and gruss["wie"] == "winkt mit dem Arm"
        assert (await r.run("arm", {"haltung": "zeigen"}))["ok"]
        falsch = await r.run("arm", {"gelenke": {"nase": 3}})
        assert not falsch["ok"] and "unbekannt" in falsch["fehler"]
        eng.notaus()                                                     # nach dem Not-Aus bleibt der Arm still
        assert not (await r.run("arm", {"geste": "winken"}))["ok"]
        assert (await r.run("absicht", {"aktion": "gruessen"}))["antwort"] == "nein"
    asyncio.run(go())


def test_modell_und_lizenz_liegen_bei_knowlin():
    b = (STATIC / "model" / "so101.dpm").read_bytes()
    assert b[:4] == b"DPM2"
    n = struct.unpack("<I", b[4:8])[0]
    head = json.loads(b[8:8 + n])
    assert head["joints"] == list(A.GELENKE) and head["art"] == "so101" and "Apache-2.0" in head["licence"]
    assert "gripperframe" in json.dumps(head["bodies"])
    lizenz = (STATIC / "model" / "LIZENZ-so101.md").read_text(encoding="utf-8")
    assert "Apache License 2.0" in lizenz and "TheRobotStudio" in lizenz
    assert "./arm3d.js" in (STATIC / "duck3d.js").read_text(encoding="utf-8")
