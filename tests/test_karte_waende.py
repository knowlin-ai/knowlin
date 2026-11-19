"""Karte ohne Löcher in den Wänden (seit 0.38.66) – Regressionstests zum Fund vom 15.11.

„Wieso erkundet er immer noch außerhalb des Raumes?“ und „man sieht die Fehler, dass er durch Wände schaut – bzw.
denkt, da sind Lücken“. Zwei Ursachen:

1. Im Simulator endete ein ToF-Strahl am ersten Ding. Lief er über ein niedriges Möbel (Sofa an der Wand) hinweg,
   landete sein Bodenpunkt hinter der Wand – „freier Boden“ außerhalb des Zimmers, dorthin wollte das Erkunden.
2. Die Wand liegt genau auf einer Zellgrenze. Ihr Treffer lag in der Zelle davor; Strahlen zu anderen Wandstellen
   liefen schräg durch genau diese Zellen und räumten sie frei – die Wand bekam Lücken.
"""

import asyncio
import math

from helpers import make, run_for

from duckpilot.motion.erkunden import Erkunden
from duckpilot.motion.karte import ZELLE, Karte, mitte, zelle


def test_tof_schaut_ueber_das_sofa_nicht_durch_die_wand():
    async def go():
        sim, _eng = await make()
        w = sim.world_model
        sim.x, sim.y, sim.yaw = 0.0, 0.5, math.pi / 2           # vor dem Sofa, Blick zur Wand dahinter
        for _ in range(20):
            sim.step(0.02)
        pts = sim.state().perception.points
        assert pts
        for x, y, _z in pts:
            assert abs(x) <= w.width / 2 + 0.01 and abs(y) <= w.depth / 2 + 0.01, (x, y)
    asyncio.run(go())


def test_wand_als_geschlossene_zellreihe_bei_streifenden_strahlen():
    k = Karte()
    for ex in [i * 0.1 - 1.5 for i in range(31)]:                 # Treffer an der Wand y = 1,5 aus schrägem Winkel
        for sx in (-1.6, 0.0, 1.6):
            k.eintragen(sx, 1.2, [[ex, 1.4996, 0.2], [ex + 0.05, 1.4996, 0.1]])
    reihe = [zelle(x, 1.51) for x in [i * ZELLE - 1.45 for i in range(59)]]
    assert all(k.belegt(c) for c in reihe), [mitte(c) for c in reihe if not k.belegt(c)]
    assert not any(k.frei(c) for c in reihe)


def test_erkunden_bleibt_im_zimmer_und_die_waende_sind_dicht():
    async def go():
        sim, eng = await make()
        w = sim.world_model
        k = Karte()
        schritt = sim.step

        def step(dt):
            schritt(dt)
            st = sim.state()
            if st.perception.points:
                k.eintragen(st.x, st.y, st.perception.points)
        sim.step = step
        eng.run(Erkunden(k, 90))
        await run_for(sim, eng, 95)
        W, D = w.width / 2, w.depth / 2
        draussen = [mitte(c) for c in k.zellen if k.frei(c) and (abs(mitte(c)[0]) > W or abs(mitte(c)[1]) > D)]
        assert not draussen, draussen[:5]
        wand = [c for c in k.zellen if (W < abs(mitte(c)[0]) < W + ZELLE and abs(mitte(c)[1]) < D)
                or (D < abs(mitte(c)[1]) < D + ZELLE and abs(mitte(c)[0]) < W)]
        assert len(wand) > 60 and not [c for c in wand if k.frei(c)]
        assert k.flaeche_m2() > 5.0
    asyncio.run(go())
