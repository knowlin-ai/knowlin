"""Reachy wie in Pollens App (0.40): umherschauen, Gesicht folgen, von selbst schlafen gehen und aufwachen."""

from __future__ import annotations

import asyncio
import math

from duckpilot.api import DuckState
from duckpilot.backends import reachy as R
from duckpilot.backends.reachy_ausdruck import SCHLAF_LAGE
from duckpilot.brain.fallback import parse
from duckpilot.motion.behaviors import LookAround
from duckpilot.server.oberflaeche import seite


def _laufen(sim, s: float) -> None:
    for _ in range(int(s / 0.05)):
        sim.step(0.05)


def test_schlaeft_nach_zehn_minuten_ein_und_wacht_bei_ansprache_auf():
    async def go():
        sim = R.ReachyMiniSim(realtime=False)
        await sim.init()
        _laufen(sim, 2.0)
        assert not sim.schlaeft()
        sim.t += R.SCHLAF_NACH_S                             # zehn Minuten nichts
        _laufen(sim, 1.0)
        st = sim.state()
        assert sim.schlaeft() and st.kopf_lage["pitch"] == round(SCHLAF_LAGE["pitch"], 4)
        assert min(abs(a) for a in sim.antennen) > 2.0       # Antennen angelegt
        sim.gespraech("zuhoeren")                            # jemand spricht ihn an
        _laufen(sim, 1.0)
        assert not sim.schlaeft() and sim.state().kopf_lage["pitch"] != round(SCHLAF_LAGE["pitch"], 4)
        sim.t += R.SCHLAF_NACH_S - 5
        sim.angesprochen()                                   # Gesicht vor der Kamera hält ihn wach
        sim.t += 10
        assert not sim.schlaeft()
        await sim.relax()                                    # Not-Aus: stromlos, kein „Schlaf“-Wecken
        assert not sim.schlaeft() and not sim.state().powered
    asyncio.run(go())


class _Daemon(R.ReachyMiniDaemon):
    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:1")
        self.rufe: list[str] = []

    async def _rufen(self, methode, pfad, body=None):
        self.rufe.append(pfad)
        return {}


def test_echter_reachy_geht_schlafen_und_wacht_auf_aber_nie_nach_dem_not_aus():
    async def go():
        d = _Daemon()
        await d.init()
        d._wach = True
        d._angesprochen -= R.SCHLAF_NACH_S + 1
        await d._muede()
        assert d.rufe[-1] == "/api/move/play/goto_sleep" and d._auto_schlaf and not d._wach
        d.gespraech("zuhoeren")
        await asyncio.sleep(0.01)
        assert d.rufe[-1] == "/api/move/play/wake_up" and d._wach and not d._auto_schlaf
        d._angesprochen -= R.SCHLAF_NACH_S + 1
        await d._muede()
        await d.relax()                                      # Not-Aus während er schläft
        n = len(d.rufe)
        d.gespraech("zuhoeren")
        await asyncio.sleep(0.01)
        assert len(d.rufe) == n and not d._wach              # weckt ihn nicht
        d._wach, d._spielt_bis = True, 1e12                  # während einer Aufnahme schläft er nicht ein
        d._angesprochen -= R.SCHLAF_NACH_S + 1
        await d._muede()
        assert d._wach
    asyncio.run(go())


def test_umschauen_springt_natuerlich_von_ziel_zu_ziel():
    b = LookAround(12, seed=3)
    st = DuckState()
    yaws, t = [], 0.0
    while not b.done:
        c = b.tick(st, 0.05)
        b.elapsed = t = t + 0.05
        if c is not None and c.head is not None:
            yaws.append(c.head.head_yaw)
    assert max(yaws) > 0.4 and min(yaws) < -0.4 and all(abs(y) <= 0.9 + 1e-9 for y in yaws)
    ruhig = sum(1 for a, b2 in zip(yaws, yaws[1:]) if abs(a - b2) < 1e-6)
    assert ruhig > len(yaws) * 0.4                           # verweilt dazwischen (nicht dauernd in Bewegung)
    assert abs(yaws[-1]) < 0.05                              # endet geradeaus
    assert LookAround(12, seed=3).ziel == LookAround(12, seed=3).ziel


def test_oberflaeche_und_saetze():
    html = seite()
    reachy = html[html.index('class="quick nur-reachy"'):]
    reachy = reachy[:reachy.index("</div>")]
    assert "data-schau" in reachy and '"look_around"' in reachy and 'data-args=\'{"seconds":20}\'' in reachy
    assert parse("Gute Nacht") == [("power", {"action": "rest"})]
    assert math.isclose(R.SCHLAF_NACH_S, 600.0)
