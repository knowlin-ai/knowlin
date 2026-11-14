"""Stack-chan als fünfter Körper (seit 0.38.58, Maintainer: „Ok mach“ auf den Vorschlag StackChan): ein Kopf mit
Gesicht auf dem Schreibtisch – dreht und nickt in Grenzen, zeigt Gefühle im Gesicht, hat keine Beine und keinen Arm, und
der Not-Aus macht ihn stromlos (Kopf sinkt, Augen zu)."""

import asyncio
import math
from pathlib import Path

from duckpilot import koerper
from duckpilot.api import Head, Twist
from duckpilot.backends.stackchan import AUSDRUECKE, KOPF_DREH, KOPF_NICK, StackChanSim, ausdruck_aus
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion.behaviors import EMOTIONS
from duckpilot.motion.engine import MotionEngine

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def _laufen(sim, sekunden):
    for _ in range(int(sekunden / 0.05)):
        sim.step(0.05)


def test_profil_figur_und_pruefung():
    from duckpilot.figuren import figur, ist_ente
    from duckpilot.koerper_pruefung import bestanden, pruefen

    p = koerper.holen("stackchan")
    assert p.fehler() == [] and p.familie == "stationaer" and "gesicht" in koerper.FAEHIGKEITEN
    assert p.faehigkeiten == {"kopf", "gesicht", "kamera", "mikrofon", "lautsprecher"}
    assert koerper.eigene_stimme(p.faehigkeiten)                     # Lautsprecher: spricht selbst
    assert p.lizenz == "Apache-2.0" and p.quelle == "https://github.com/stack-chan/stack-chan" and not p.echt
    assert figur("stackchan")["name"] == "Stacki" and not ist_ente("stackchan")
    assert bestanden(asyncio.run(pruefen(p.bauen(type("C", (), {"backend": "sim"})()), p)))


def test_steht_fest_kopf_in_grenzen():
    async def go():
        sim = StackChanSim(realtime=False)
        assert sim.standflaeche == "Couchtisch"
        await sim.init()
        _laufen(sim, 3.0)
        x, y, yaw = sim.x, sim.y, sim.yaw
        await sim.move(Twist(0.3, 0.0, 1.0))
        assert "keine Beine" in sim.limited_by[0]
        _laufen(sim, 1.0)
        assert (sim.x, sim.y, sim.yaw) == (x, y, yaw)
        assert not (await sim.do("kick_left")).accepted
        assert not (await sim.sound("chirp")).accepted                  # keine Entenlaute
        await sim.head(Head(0.0, -2.0, 3.0, 0.0))                       # weit über die Grenzen
        _laufen(sim, 1.5)
        lage = sim.state().kopf_lage
        assert abs(lage["yaw"]) <= KOPF_DREH + 1e-6 and abs(lage["pitch"]) <= KOPF_NICK + 1e-6
        assert sim.state().perception.tof_mm is None or not sim.state().perception.points
    asyncio.run(go())


def test_gesicht_gefuehle_mund_und_not_aus():
    async def go():
        sim = StackChanSim(realtime=False)
        assert sim.state().gesicht["wach"] is False                     # schläft am Anfang: Augen zu
        await sim.init()
        _laufen(sim, 3.0)
        g = sim.state().gesicht
        assert g == {"ausdruck": "ruhig", "mund": 0.0, "wach": True, "zustand": None}
        assert sim.gefuehl_zeigen("freude", 1.0) == "froh"
        assert sim.state().gesicht["ausdruck"] == "froh"
        _laufen(sim, 2.0)
        assert sim.state().gesicht["ausdruck"] == "ruhig"               # geht von selbst zurück
        await sim.mouth(0.8)
        _laufen(sim, 0.5)
        assert sim.state().gesicht["mund"] > 0.3                        # Mund bewegt sich mit
        sim.gespraech("denkt")
        assert sim.state().gesicht["zustand"] == "denkt"
        await sim.relax()                                               # Not-Aus: stromlos
        st = sim.state()
        assert not st.powered and st.gesicht["wach"] is False and st.gesicht["mund"] == 0.0
        assert math.isclose(st.kopf_lage["pitch"], math.radians(18), abs_tol=1e-3)   # Kopf gesenkt
    asyncio.run(go())


def test_jedes_gefuehl_hat_ein_gesicht():
    assert {ausdruck_aus(n) for n in EMOTIONS} <= set(AUSDRUECKE)
    assert ausdruck_aus("gibt es nicht") == "ruhig" and ausdruck_aus("Freude") == "froh"


def test_gefuehl_werkzeug_zeigt_es_im_gesicht():
    async def go():
        sim = StackChanSim(realtime=False)
        eng = MotionEngine(sim)
        await sim.init()
        _laufen(sim, 3.0)
        eng.last_state = sim.state()
        runner = ToolRunner(eng)
        r = await runner.run("emote", {"emotion": "traurig"})
        assert r["ok"] and sim.state().gesicht["ausdruck"] == "traurig"
    asyncio.run(go())


def test_oberflaeche_verdrahtet():
    js = (STATIC / "stackchan3d.js").read_text(encoding="utf-8")
    assert "export class StackChan" in js and "gesichtZeichnen" in js and "userData.einzeln = true" in js
    assert "new StackChan()" in (STATIC / "duck3d.js").read_text(encoding="utf-8")
    assert "stackchan: { klasse: 'stackchan'" in (STATIC / "modul.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'value="stackchan" data-set="modul"' in html and 'class="quick nur-stackchan"' in html
    assert ".nur-stackchan" in (STATIC / "style.css").read_text(encoding="utf-8")


def test_wie_gehts_ist_kein_laufbefehl_und_jeder_nennt_seinen_namen():
    """Funde 14.11. beim Bild für die Website: „Hallo Stacki, wie geht's dir?“ ließ (ohne Sprachmodell) laufen – „geht“
    galt als Laufbefehl –, und Stacki (wie zuvor Ari) meldete „Reachy Mini hat keine Beine“."""
    from duckpilot.brain.fallback import FallbackBrain, parse

    assert parse("Wie geht's dir?") == [] and parse("Hallo Stacki, wie geht's dir?") == [("emote", {"emotion": "begruessen"})]
    assert parse("geh vor") == [("walk", {"distance_m": 0.4})]           # echte Laufbefehle bleiben

    async def go():
        sim = StackChanSim(realtime=False)
        eng = MotionEngine(sim)
        await sim.connect()
        await sim.init()
        _laufen(sim, 3.0)
        eng.last_state = sim.state()
        runner = ToolRunner(eng)
        walk = await runner.run("walk", {"distance_m": 0.3})
        antwort = await FallbackBrain(runner).handle("Hallo Stacki, wie geht's dir?")
        return walk, antwort
    walk, antwort = asyncio.run(go())
    assert walk["fehler"].startswith("Stack-chan hat keine Beine") and "Reachy" not in walk["fehler"]
    assert antwort.text.startswith("Mir geht's gut") and "wach" in antwort.text


def test_leerlauf_geste_in_der_gewaehlten_sprache():
    """Fund 14.11. beim englischen Website-Bild: Unter „Bubbly“ stand die Leerlauf-Geste auf Deutsch („späht umher“)."""
    from duckpilot import i18n
    from duckpilot.server.runtime import _leerlauf_text

    alt = i18n.sprache()
    try:
        i18n.setze_sprache("en")
        assert _leerlauf_text("umherspaehen") == "peers around"
        i18n.setze_sprache("de")
        assert _leerlauf_text("umherspaehen") == "späht umher"
    finally:
        i18n.setze_sprache(alt)
    src = (Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "runtime.py").read_text(encoding="utf-8")
    assert 'event = {**event, "message": _leerlauf_text(str(event["geste"]))' in src
