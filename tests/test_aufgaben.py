"""Selbstständige Aufgaben (seit 0.55): Linie folgen und Farbe folgen – Rechnung, Simulator, Kamerabild."""

import asyncio
import math

import numpy as np
from helpers import make, run_for

from duckpilot import farbsicht as F
from duckpilot import linie as L
from duckpilot.backends.world import World
from duckpilot.motion.aufgaben import FarbeFolgen, LinieFolgen


def test_linie_ist_eine_glatte_runde_ohne_moebel_darauf():
    pts = L.punkte()
    assert len(pts) > 60
    abstaende = [math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    assert max(abstaende) < 0.09                       # geschlossen und gleichmäßig
    welt = World.living_room()
    frei = [welt.collide(x, y, 0.15) is None for x, y in pts]
    assert all(frei)                                   # kein Möbel und keine Wand nah am Band
    assert min(math.dist((i.x, i.y), p) for i in welt.items for p in pts) > 0.18   # kein Ding auf dem Band


def test_sicht_versatz_und_winkel():
    pts = [(-2.0 + 0.04 * i, 0.0) for i in range(100)]   # gerade Linie entlang x bei y = 0 (offen reicht hier)
    s = L.sicht(0.0, -0.05, 0.0, pts)                  # 5 cm rechts daneben, Blick entlang der Linie
    assert s["art"] == "linie" and abs(s["versatz_m"] - 0.05) < 0.005 and s["winkel_grad"] == 0
    s = L.sicht(0.0, 0.0, math.radians(20), pts)       # schräg nach links: Linie läuft nach rechts weg
    assert s["winkel_grad"] == -20
    assert L.sicht(0.0, 1.0, 0.0, pts) is None         # zu weit weg: nicht im Bild
    assert L.sicht(0.0, 0.0, 0.0, None) is None


def test_farben_der_dinge():
    assert F.farbname("#e8553e") == "rot" and F.farbname("#4a90d9") == "blau"
    assert F.farbname("#e9e2cf") is None and F.farbname("#2f2f33") is None and F.farbname("kaputt") is None


def test_linie_folgen_im_simulator():
    async def go():
        sim, eng = await make()
        sim.world_model.set_linie(True)
        x0, y0 = L.punkte()[0]
        sim.x, sim.y, sim.yaw = x0, y0, math.atan2(L.punkte()[3][1] - y0, L.punkte()[3][0] - x0)
        b = LinieFolgen(seconds=30, tempo=0.12)
        eng.run(b)
        weit = 0.0
        for _ in range(150):                           # 30 s in Schritten
            await run_for(sim, eng, 0.2)
            weit = max(weit, L._naechster(sim.x, sim.y, sim.world_model.linie)[0])
        return b, weit

    b, weit = asyncio.run(go())
    assert b.gesehen and b.strecke > 1.5               # ein gutes Stück der Runde
    assert weit < 0.12                                 # immer nah an der Linie


def test_linie_folgen_ohne_linie_hoert_auf():
    async def go():
        sim, eng = await make()
        b = LinieFolgen(seconds=60)
        eng.run(b)
        await run_for(sim, eng, 10.0)
        return b

    b = asyncio.run(go())
    assert b.done and b.result == "keine Linie gesehen"


def test_farbe_folgen_zum_blauen_kloetzchen():
    async def go():
        sim, eng = await make()
        klotz = next(i for i in sim.world_model.items if i.name == "Klötzchen")
        sim.x, sim.y = klotz.x + 0.6, klotz.y
        sim.yaw = math.pi                               # schaut hin
        b = FarbeFolgen("blau", seconds=20)
        eng.run(b)
        await run_for(sim, eng, 12.0)
        return b, math.hypot(sim.x - klotz.x, sim.y - klotz.y)

    b, d = asyncio.run(go())
    assert b.gesehen and b.da >= 1 and d < 0.4


def test_farbe_folgen_ohne_farbe_hoert_auf():
    async def go():
        sim, eng = await make()
        b = FarbeFolgen("gruen", seconds=60)
        eng.run(b)
        await run_for(sim, eng, 14.0)
        return b

    b = asyncio.run(go())
    assert b.done and b.result == "nichts in dieser Farbe gesehen"


def test_kamerabild_farbe_und_linie():
    bild = np.full((240, 320, 3), 180, np.uint8)               # heller Boden
    bild[150:200, 200:240] = (40, 90, 210)                     # blauer Fleck rechts unten
    f = F.detect_farbe(bild, "blau")
    assert f and 200 <= f["x"] <= 240 and f["y"] > 180
    assert F.detect_farbe(bild, "rot") is None
    bild[:, 150:160] = (20, 20, 22)                            # dunkles Band senkrecht in der Mitte
    mitten = F.detect_linie(bild)
    assert len(mitten) == 3 and all(150 <= m["x"] <= 160 for m in mitten)
    ding = F.linie_auf_boden(mitten, 320, 240, tilt=0.6, head_yaw=0.0)
    assert ding["art"] == "linie" and abs(ding["winkel_grad"]) <= 3 and abs(ding["versatz_m"]) < 0.02


def test_tragen_zu_einem_moebel_auch_ungesehen():
    """Seit 0.55 (Karte „Dinge tragen“): Im Simulator kennt sie die Möbel, auch wenn sie sie gerade nicht sieht."""
    from duckpilot.brain.tools import ToolRunner

    async def go():
        sim, eng = await make()
        r = ToolRunner(eng)
        res = await r.run("apportieren", {"ding": "klötzchen", "zu": "Kiste"})
        await run_for(sim, eng, 60)
        klotz = next(i for i in sim.world_model.items if i.name == "Klötzchen")
        return res, klotz, next(b for b in sim.world_model.boxes if b.name == "Kiste")

    res, klotz, kiste = asyncio.run(go())
    assert res["ok"] and not klotz.held
    assert math.hypot(klotz.x - kiste.x, klotz.y - kiste.y) < 0.5      # neben der Kiste abgelegt
