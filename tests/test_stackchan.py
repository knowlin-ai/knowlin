"""Stack-chan als fünfter Körper (seit 0.38.58, Maintainer: „Ok mach“ auf den Vorschlag StackChan): ein Kopf mit
Gesicht auf dem Schreibtisch – dreht und nickt in Grenzen, zeigt Gefühle im Gesicht, hat keine Beine und keinen Arm, und
der Not-Aus macht ihn stromlos (Kopf sinkt, Augen zu)."""

import asyncio
import math
from pathlib import Path

from duckpilot import koerper
from duckpilot.api import Head, Twist
from duckpilot.backends.stackchan import AUSDRUECKE, KOPF_DREH, KOPF_HOCH, KOPF_RUNTER, StackChanSim, ausdruck_aus
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
    assert p.faehigkeiten == {"kopf", "gesicht", "beruehrung", "kamera", "mikrofon", "lautsprecher"}
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
        assert abs(lage["yaw"]) <= KOPF_DREH + 1e-6 and -KOPF_HOCH - 1e-6 <= lage["pitch"] <= KOPF_RUNTER + 1e-6
        assert sim.state().perception.tof_mm is None or not sim.state().perception.points
    asyncio.run(go())


def test_gesicht_gefuehle_mund_und_not_aus():
    async def go():
        sim = StackChanSim(realtime=False)
        assert sim.state().gesicht["wach"] is False                     # schläft am Anfang: Augen zu
        await sim.init()
        _laufen(sim, 3.0)
        g = sim.state().gesicht
        assert g == {"ausdruck": "ruhig", "mund": 0.0, "wach": True, "zustand": None, "led": None}
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
        assert math.isclose(st.kopf_lage["pitch"], KOPF_RUNTER, abs_tol=1e-3)   # Kopf gesenkt
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


def test_originalgehaeuse_liegt_bei_knowlin():
    """Seit 0.38.61 (Maintainer: „Haben wir für die neuen Roboter keine original 3D Modelle?“ – „Ja“): Gehäuse und Füße
    aus den offenen Gehäusedaten der Stack-chan-Community (Apache-2.0), gebacken in `static/model/stackchan.dpm`, mit
    Lizenzhinweis; die Figur lädt sie und steht bis dahin in denselben Maßen gezeichnet da."""
    import json
    import struct

    from duckpilot.modell import stackchan as M

    b = (STATIC / "model" / "stackchan.dpm").read_bytes()
    assert b[:4] == b"DPM2"
    n = struct.unpack("<I", b[4:8])[0]
    head = json.loads(b[8:8 + n])
    assert head["art"] == "stackchan" and "Apache-2.0" in head["licence"]
    assert [m["name"] for m in head["meshes"]] == ["fuss", "schale"]
    assert head["source"]["commit"] == M.QUELLE["commit"][:7] and head["dreh_hoehe"] == M.DREH_HOEHE
    lizenz = (STATIC / "model" / "LIZENZ-stackchan.md").read_text(encoding="utf-8")
    assert "Apache License 2.0" in lizenz and "Stack-chan-Community" in lizenz and M.QUELLE["commit"] in lizenz
    js = (STATIC / "stackchan3d.js").read_text(encoding="utf-8")
    assert "/static/model/stackchan.dpm" in js and f"DREH_Y = {M.DREH_HOEHE}" in js


def test_wie_das_original_beruehrung_schlaf_leds():
    """Seit 0.38.62 (Funktionsabgleich mit M5Stacks StackChan, Maintainer: „Ok“): Kopf in den echten Grenzen (fast nur
    nach oben nicken), Berührung oben auf dem Kopf (streicheln → froh, schütteln → schwindelig), nach fünf Minuten ohne
    Ansprache schläft er ein, LEDs grün beim Zuhören und blau beim Sprechen. Nach dem Not-Aus spürt er nichts."""
    from duckpilot.api import Head
    from duckpilot.backends.stackchan import SCHLAF_NACH, kopf_lage
    from duckpilot.brain.fallback import parse
    assert "beruehrung" in koerper.FAEHIGKEITEN and "beruehrung" in koerper.holen("stackchan").faehigkeiten
    assert kopf_lage(Head(head_pitch=-2.0))["pitch"] == round(-KOPF_HOCH, 4)      # hoch bis 80°
    assert kopf_lage(Head(head_pitch=1.0))["pitch"] == round(KOPF_RUNTER, 4)      # runter nur 10°
    sim = StackChanSim(realtime=False)
    asyncio.run(sim.init())
    _laufen(sim, 3.0)
    assert sim.beruehren("streicheln").accepted
    assert sim.state().gesicht["ausdruck"] == "froh"
    assert sim.beruehren("schuetteln").accepted
    assert sim.state().gesicht["ausdruck"] == "schwindelig"
    assert not sim.beruehren("kitzeln").accepted
    sim.gespraech("zuhoeren", 5)
    assert sim.state().gesicht["led"] == "gruen"
    sim.gespraech(None)
    sim._angesprochen = sim.t - SCHLAF_NACH - 1                                  # fünf Minuten nichts
    g = sim.state().gesicht
    assert g["zustand"] == "schlaeft" and not g["wach"] and g["led"] is None
    sim.gefuehl_zeigen("freude")                                                 # Ansprache weckt ihn
    assert sim.state().gesicht["wach"]
    k = frozenset(sim.skills()) | sim.eigenschaften()
    assert parse("Ich streichel dich mal", k) == [("beruehren", {"art": "streicheln"})]
    assert parse("Ich streichel dich mal") == []                                 # andere Körper: kein Kommando
    asyncio.run(sim.relax())
    assert not sim.beruehren("streicheln").accepted
    js = (STATIC / "stackchan3d.js").read_text(encoding="utf-8")
    assert "a === 'schwindelig'" in js and "ledStoff" in js and "zz" in js
