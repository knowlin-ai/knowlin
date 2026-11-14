"""Bittle X als sechster Körper (seit 0.38.59, Maintainer: „Ok mach“ – nach Stack-chan Petois Roboterhund): läuft auf
vier Beinen, dreht den Kopf nur seitlich, hat keinen Schnabel und keine eigene Stimme (Knowlin spricht für ihn), und
der Not-Aus macht ihn stromlos."""

import asyncio
import math
from pathlib import Path

from duckpilot import koerper
from duckpilot.api import Head, Twist
from duckpilot.backends.bittle import KOPF_DREH, BittleSim

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def _laufen(sim, sekunden):
    for _ in range(int(sekunden / 0.05)):
        sim.step(0.05)


def test_profil_figur_und_pruefung():
    from duckpilot.figuren import figur, ist_ente
    from duckpilot.koerper_pruefung import bestanden, pruefen

    p = koerper.holen("bittle")
    assert p.fehler() == [] and p.familie == "vierbeiner" and p.faehigkeiten == {"beine", "kopf", "mikrofon"}
    assert not koerper.eigene_stimme(p.faehigkeiten)                 # Knowlin spricht für ihn
    assert p.lizenz == "MIT" and p.quelle == "https://github.com/PetoiCamp/OpenCat" and not p.echt
    assert figur("bittle")["name"] == "Bello" and not ist_ente("bittle")
    assert bestanden(asyncio.run(pruefen(p.bauen(type("C", (), {"backend": "sim"})()), p)))


def test_laeuft_sitzt_kopf_seitlich_und_not_aus():
    async def go():
        sim = BittleSim(realtime=False)
        await sim.connect()
        await sim.init()
        await sim.enable(True)
        _laufen(sim, 3.0)
        x0 = sim.x
        for _ in range(30):                                            # Totmann: Befehl immer wieder schicken
            await sim.move(Twist(0.15, 0.0, 0.0))
            sim.step(0.05)
        assert math.hypot(sim.x - x0, 0) > 0.05 and sim.state().gait_phase != 0.0
        assert not (await sim.do("ground_pick")).accepted and not (await sim.sound("chirp")).accepted
        await sim.head(Head(0.0, 0.0, 3.0, 0.0))
        _laufen(sim, 1.0)
        assert abs(sim.state().kopf_lage["yaw"]) <= KOPF_DREH + 1e-6
        assert sim.state().holding is None and not sim.state().perception.points
        await sim.relax()
        assert not sim.state().powered
    asyncio.run(go())


def test_oberflaeche_verdrahtet():
    js = (STATIC / "bittle3d.js").read_text(encoding="utf-8")
    assert "export class Bittle" in js and "gait_phase" in js and "sitting" in js
    assert "new Bittle()" in (STATIC / "duck3d.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'value="bittle" data-set="modul"' in html and ".nur-bittle" in (STATIC / "style.css").read_text(encoding="utf-8")
