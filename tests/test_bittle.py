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


def test_leerlauf_passt_zum_hund():
    """Fund 14.11. beim englischen Website-Bild von Bello: Unten stand auf Deutsch „jagt ihren eigenen Schwanz“ (die
    Albernheiten hatten keine Übersetzung, „ihren“ passte nur zur Ente), und ein Hund ohne Schnabel darf sich kein
    Gefieder putzen."""
    import json
    import random

    from duckpilot import i18n
    from duckpilot.motion.behaviors import ANTICS
    from duckpilot.motion.character import MESSAGES, NUR_MIT_SCHNABEL, REPERTOIRE
    from duckpilot.motion.engine import MotionEngine
    from duckpilot.server.runtime import _leerlauf_text

    en = json.loads((Path(__file__).resolve().parents[1] / "duckpilot" / "i18n" / "en.json").read_text(encoding="utf-8"))
    assert not [n for n in set(MESSAGES) | set(ANTICS) if f"leerlauf.{n}" not in en]
    assert "ihren" not in ANTICS["schwanz_jagen"]["nachricht"]
    alt = i18n.sprache()
    try:
        i18n.setze_sprache("en")
        assert _leerlauf_text("schwanz_jagen") == "chases its own tail"
    finally:
        i18n.setze_sprache(alt)
    sim = BittleSim()
    asyncio.run(sim.connect())
    eng = MotionEngine(sim)
    eng.rng = random.Random(3)
    personas = [p for p, r in REPERTOIRE.items() if any(g in NUR_MIT_SCHNABEL for g, _ in r.get("gesten", []))]
    assert personas
    gezeigt = {eng.idle_gesture(persona=p) for p in personas for _ in range(40)}
    assert not gezeigt & NUR_MIT_SCHNABEL and gezeigt - {None}
