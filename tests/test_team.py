"""Teamarbeit (0.37.4): Die anderen Enten helfen beim Aufräumen und beim Suchen."""

import asyncio
import math

from helpers import make, run_for

from duckpilot.backends.begleiter import Begleitente
from duckpilot.brain.fallback import parse
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion import team as TM
from duckpilot.motion.schwarm import Schwarm


async def _team(n):
    sim, eng = await make()
    sw = Schwarm(sim, eng, lambda i, a, b, yaw: Begleitente(sim.world_model, i, a, b, yaw))
    sim.nach_schritt.append(sw.step)
    sw.anzahl(n)
    r = ToolRunner(eng)
    r.schwarm = sw
    return sim, eng, sw, r


def test_karte_aus_welt_kennt_moebel_und_waende():
    from duckpilot.backends.world import World
    from duckpilot.motion.karte import zelle

    k = TM.karte_aus_welt(World.living_room())
    assert k.belegt(zelle(0.0, 1.22)) and k.belegt(zelle(2.02, 0.0)) and k.frei(zelle(0.0, 0.0))


def test_gemeinsam_aufraeumen_zum_sofa():
    async def go():
        sim, eng, sw, r = await _team(2)
        res = await r.run("team", {"aktion": "aufraeumen", "ziel": "Sofa"})
        assert res["ok"] and len(res["dinge"]) == 4 and res["helfer"] == ["Kiki", "Pip"]
        await run_for(sim, eng, 120, until=lambda: sw.auftrag is not None and sw.auftrag.fertig)
        a = sw.auftrag
        assert a.fertig and a.ergebnis.startswith("Fertig: 4 Dinge"), a.zustand()
        ziel = a.ziel
        for i in sim.world_model.items:
            if i.kind in TM.AUFHEBBAR:
                assert not i.held and math.hypot(i.x - ziel[0], i.y - ziel[1]) < 0.5, (i.name, i.x, i.y)
        assert any(m.startswith("Kiki: Ich hole") for m in a.meldungen + [a.ergebnis]) or a.gebracht
    asyncio.run(go())


def test_suchtrupp_findet_verdecktes_und_bringt_es():
    async def go():
        sim, eng, sw, r = await _team(3)
        fig = next(i for i in sim.world_model.items if i.kind == "figur")
        fig.x, fig.y = -1.5, -0.95                       # hinter der Kiste – die Hauptente sieht sie nicht
        res = await r.run("team", {"aktion": "suchen", "ding": "schachfigur"})
        assert res["ok"]
        await run_for(sim, eng, 120, until=lambda: sw.auftrag is not None and sw.auftrag.fertig)
        a = sw.auftrag
        assert a.fertig and "gefunden" in a.ergebnis, a.zustand()
        assert any("Gefunden" in m for m in a.meldungen)
        if "gebracht" in a.ergebnis:
            h = sim
            assert math.hypot(fig.x - h.x, fig.y - h.y) < 0.6
    asyncio.run(go())


def test_unerreichbar_wird_gemeldet_und_stopp_legt_ab():
    async def go():
        sim, eng, sw, r = await _team(1)
        for i in sim.world_model.items:
            if i.kind in TM.AUFHEBBAR and i.kind != "sock":
                i.held = True                           # nur die Socke ist im Spiel
        sock = next(i for i in sim.world_model.items if i.kind == "sock")
        sock.x, sock.y = 1.82, -0.6                     # mitten im Regal – da kommt keine hin
        a = TM.Aufraeumen(sw, (0.0, 1.22), "Sofa", ("sock",))
        sw.beauftragen(a)
        await run_for(sim, eng, 90, until=lambda: a.fertig)
        assert a.fertig and "nicht erreicht: Socke" in a.ergebnis, a.zustand()
        sock.x, sock.y = -0.2, 0.2
        a2 = TM.Aufraeumen(sw, (0.0, 1.22), "Sofa", ("sock",))
        sw.beauftragen(a2)
        await run_for(sim, eng, 40, until=lambda: sw.enten[0].holding)
        assert sw.enten[0].holding == "Socke"
        assert sw.auftrag_stopp() == "aufraeumen" and sw.enten[0].holding is None and not sock.held
        import time
        sw.beauftragen(TM.Aufraeumen(sw, (0.0, 1.22), "Sofa", ("sock",)))
        eng.estop_at = time.monotonic()                    # Not-Aus beendet die Teamarbeit
        await run_for(sim, eng, 0.5)
        assert sw.auftrag is None
    asyncio.run(go())


def test_teambefehle_ohne_claude_und_ohne_enten():
    assert parse("Räumt alle Socken zum Sofa")[0] == ("team", {"aktion": "aufraeumen", "ziel": "sofa", "dinge": "socke"})
    assert parse("bringt alle Klötzchen zu mir")[0][1]["ziel"] == "mir"
    assert parse("Helft mir die Schachfigur suchen")[0] == ("team", {"aktion": "suchen", "ding": "schachfigur"})
    assert parse("help me find the chess piece")[0] == ("team", {"aktion": "suchen", "ding": "schachfigur"})
    assert parse("bring mir die Socke")[0][0] == "apportieren"          # allein bleibt allein

    async def go():
        sim, eng = await make()
        res = await ToolRunner(eng).run("team", {"aktion": "aufraeumen", "ziel": "Sofa"})
        assert res["ok"] is False and "Keine weiteren Enten" in res["fehler"]
    asyncio.run(go())


def test_vorsichtig_am_ziel_und_nacharbeiten():
    """0.37.5 (Hinweis aus dem Test „die Enten schieben die Gegenstände am Zielort wieder vor sich her … sollte was
    wegrollen, müssen sie nochmal nacharbeiten“): Nach dem Aufräumen und 40 s freiem Herumlaufen liegt alles noch am
    Ziel; rollt während des Auftrags etwas weg, holt eine Ente es zurück."""
    async def go():
        sim, eng, sw, r = await _team(3)
        await r.run("team", {"aktion": "aufraeumen", "ziel": "Sofa"})
        a = sw.auftrag
        weg = {"done": False}

        def stoss():                                     # das erste Gebrachte rollt weg
            if a.gebracht and not weg["done"]:
                i = next(x for x in sim.world_model.items if x.name == a.gebracht[0])
                if not i.held:
                    i.x, i.y = -0.9, 0.3
                    weg["done"] = True
            return a.fertig
        await run_for(sim, eng, 150, until=stoss)
        assert weg["done"] and a.fertig, a.zustand()
        assert any("weggerollt" in m for m in a.meldungen + [a.ergebnis]) or getattr(a, "nachgeholt", None)
        ziel = a.ziel
        await run_for(sim, eng, 40)
        for i in sim.world_model.items:
            if i.kind in TM.AUFHEBBAR:
                assert math.hypot(i.x - ziel[0], i.y - ziel[1]) < 0.35, (i.name, i.x, i.y)
    asyncio.run(go())
