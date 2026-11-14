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


def test_keine_entengelenke_im_zustand():
    """Abnahme 14.11.: Bellos Zustandsansicht zeigte die Gelenke der Ente samt „Schnabel“."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'class="card card-joints braucht-beine ohne-bittle"' in html


def test_bellos_tricks_nach_petoi():
    """Seit 0.38.61 (Funktionsabgleich mit Petoi, Maintainer: „Ja und weiter“): zehn eigene Tricks im Simulator – sie
    laufen als Skill mit Fortschritt, stehen als Kacheln auf der Trickseite, im skill-Werkzeug mit Bedeutung und gehen
    ohne KI-Modell per Zuruf („Pfote!“, „Platz!“). Nach dem Not-Aus geht keiner."""
    import re

    from duckpilot.backends.bittle import TRICKS
    from duckpilot.brain.fallback import parse, quick_command

    assert len(TRICKS) >= 10
    sim = BittleSim(realtime=False)

    async def wach():
        await sim.connect()
        await sim.init()
        await sim.enable(True)
    asyncio.run(wach())
    _laufen(sim, 3)
    assert set(TRICKS) <= set(sim.skills())
    assert asyncio.run(sim.do("pfote")).accepted
    _laufen(sim, 1.0)
    st = sim.state()
    assert st.skill == "pfote" and 0.2 < st.skill_progress < 0.6
    _laufen(sim, 2.0)
    assert sim.state().skill is None
    assert not asyncio.run(sim.do("roulade")).accepted                   # Entenpurzelbaum bleibt Sache der Enten
    asyncio.run(sim.relax())
    assert not asyncio.run(sim.do("salto")).accepted                     # stromlos: kein Trick
    # Kacheln = Liste des Simulators, 3D-Figur kennt jeden Trick
    html = (STATIC / "teile" / "tricks.html").read_text(encoding="utf-8")
    assert re.findall(r'data-bello="(\w+)"', html) == list(TRICKS)
    js = (STATIC / "bittle3d.js").read_text(encoding="utf-8")
    for name in TRICKS:
        assert re.search(rf"\b{name}: \(p\)", js), name
    # Zuruf ohne KI-Modell; „an seinen Platz“ und „eine Strecke“ sind keine Kommandos
    k = frozenset(sim.skills())
    assert parse("Gib Pfote!", k) == [("skill", {"name": "pfote"})] and quick_command("Gib Pfote!", k)
    assert parse("Mach Platz", k) == [("skill", {"name": "platz"})]
    assert parse("Stell dich tot", k) == [("skill", {"name": "tot_stellen"})]
    assert ("skill", {"name": "platz"}) not in parse("leg den Ball an seinen Platz", k)
    assert ("skill", {"name": "strecken"}) not in parse("lauf eine Strecke", k)
    # bei der Ente bleibt „mach die Verbeugung“ ein Fall fürs Sprachmodell (gelernter Trick), kein Hundekommando
    assert parse("mach die Verbeugung") == [] and not quick_command("Gib Pfote!")


def test_skill_werkzeug_beschreibt_bellos_tricks():
    from duckpilot.brain.tools import ToolRunner
    from duckpilot.motion.engine import MotionEngine

    sim = BittleSim()
    asyncio.run(sim.connect())
    tools = {t["name"]: t for t in ToolRunner(MotionEngine(sim)).tools()}
    skill = tools["skill"]
    assert "pfote" in skill["input_schema"]["properties"]["name"]["enum"]
    assert "Pfote geben" in skill["description"] and "vom Hub" not in skill["description"]


def test_maennchen_und_kein_entenprompt_fuer_andere_koerper():
    """Fund des Maintainers (15.11.): „mach männchen“ bei Bello – das lokale Modell antwortete „Hmpf, ein Männchen? Ich
    zeig dir mein tolles Entenmännchen!“. Ursachen: kein Männchen-Trick, und Hund, Schreibtischkopf und Arm bekamen die
    Entenregeln (Albern-Modus, Entenlaute, Schnabel, Ball, Wohnzimmer). Jetzt: Männchen per Zuruf ohne KI, und der
    Text für die KI richtet sich nach der Körperschnittstelle."""
    from duckpilot.backends.so101 import So101Sim
    from duckpilot.backends.stackchan import StackChanSim
    from duckpilot.brain.agent import AgentConfig, DuckAgent
    from duckpilot.brain.fallback import parse, quick_command
    from duckpilot.brain.tools import ToolRunner
    from duckpilot.motion.engine import MotionEngine

    sim = BittleSim(realtime=False)
    k = frozenset(sim.skills())
    assert "maennchen" in k and parse("mach männchen", k) == [("skill", {"name": "maennchen"})]
    assert quick_command("Mach Männchen!", k)
    for koerper_sim in (BittleSim(realtime=False), StackChanSim(realtime=False), So101Sim(realtime=False)):
        eng = MotionEngine(koerper_sim)
        eng.config.goofy = True
        agent = DuckAgent(ToolRunner(eng), AgentConfig(api_key=None))
        text = agent._system()
        assert "KEINE Ente" in text, type(koerper_sim).__name__
        for ente in ("GOOFY-MODUS IST AN", "liebenswerte Ente", "*quak*", "Schnabel klappern", "ground_pick",
                     "Entenlaute nur über"):
            assert ente not in text, (type(koerper_sim).__name__, ente)
    eng = MotionEngine(So101Sim(realtime=False))
    assert "Werkbank" in DuckAgent(ToolRunner(eng), AgentConfig(api_key=None))._system()
    assert "kick_left" not in DuckAgent(ToolRunner(MotionEngine(BittleSim(realtime=False))),
                                         AgentConfig(api_key=None))._system()
