"""Fähigkeiten-Schnittstelle und Körper-Eigenschaften (seit 0.38)."""

import asyncio

from helpers import make, run_for

from duckpilot.backends.robotd import RobotdBackend
from duckpilot.motion.apportieren import Apportieren
from duckpilot.motion.erkunden import Erkunden
from duckpilot.motion.faehigkeit import Faehigkeit
from duckpilot.motion.karte import Karte
from duckpilot.motion.purzelbaum import Purzelbaum
from duckpilot.motion.schuss import GezielterSchuss


def run(coro):
    return asyncio.run(coro)


def test_alle_vier_sind_faehigkeiten():
    for cls, name in ((Apportieren, "apportieren"), (GezielterSchuss, "schiessen"), (Purzelbaum, "purzelbaum"),
                      (Erkunden, "erkunden")):
        assert issubclass(cls, Faehigkeit) and cls.faehigkeit == name and "beine" in cls.braucht


def test_koerper_eigenschaften():
    async def go():
        sim, eng = await make()
        e = sim.eigenschaften()
        assert {"beine", "schnabel", "tiefensensor", "simulator", "zuruecksetzen"} <= e and "policies" not in e
    run(go())
    ohne_tof = RobotdBackend("tcp:127.0.0.1:1")
    assert "zuruecksetzen" not in ohne_tof.eigenschaften() and "tiefensensor" not in ohne_tof.eigenschaften()
    assert "tiefensensor" in RobotdBackend("tcp:127.0.0.1:1", tof="tcp:127.0.0.1:2").eigenschaften()


def test_fehlende_eigenschaft_wird_sauber_abgelehnt():
    async def go():
        sim, eng = await make()
        sim.eigenschaften = lambda: frozenset({"beine", "kopf", "schnabel"})     # Körper ohne Tiefensensor
        b = Erkunden(Karte(), 5)
        eng.run(b)
        await run_for(sim, eng, 0.5, until=lambda: b.done)
        return b, eng
    b, eng = run(go())
    assert b.done and b.failed and "fehlt: tiefensensor" in b.result
    assert b.bericht()["ergebnis"] == "abgelehnt"
    ende = [e for e in eng.events if e["type"] == "behavior_end"][-1]
    assert ende["bericht"]["faehigkeit"] == "erkunden"


def test_bericht_nach_erfolg_und_vorbedingung():
    class Probe(Faehigkeit):
        faehigkeit = "probe"
        braucht = frozenset({"beine"})

        def __init__(self, geht):
            super().__init__()
            self.geht = geht

        def vorbedingung(self, st):
            return None if self.geht else "Ball nicht in Sicht"

        def tick(self, st, dt):
            self.plan_b("einmal nachjustiert")
            return self.erfolg("geklappt")

    async def go():
        sim, eng = await make()
        ok, nein = Probe(True), Probe(False)
        eng.run(ok)
        await run_for(sim, eng, 0.3, until=lambda: ok.done)
        eng.run(nein)
        await run_for(sim, eng, 0.3, until=lambda: nein.done)
        return ok, nein
    ok, nein = run(go())
    assert ok.bericht() == {"faehigkeit": "probe", "ergebnis": "erfolg", "text": "geklappt", "plan_b": ["einmal nachjustiert"]}
    assert nein.bericht()["ergebnis"] == "abgelehnt" and nein.result == "Ball nicht in Sicht"
