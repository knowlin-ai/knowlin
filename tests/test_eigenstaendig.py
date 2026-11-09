"""Eigenständiges Verhalten (Wunsch des Maintainers 5.11.): Ohne Befehle sucht sich die Verkörperung nach einer Weile selbst
etwas – passend zum Charakter und nur, was ihr Körper kann. Sicherheitsregeln einzeln, am echten Roboter keine
Ortsbewegung, jeder Befehl, jedes Ansprechen und der Not-Aus unterbrechen sofort."""

import asyncio
import json
import random
import time
from dataclasses import replace
from pathlib import Path

import pytest
from helpers import make, run_for
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import settings as S
from duckpilot.api import Twist
from duckpilot.backends.open_duck import OpenDuckSim
from duckpilot.backends.reachy import ReachyMiniSim
from duckpilot.backends.sim import SimBackend
from duckpilot.brain.tools import fehlt_dem_koerper
from duckpilot.config import load
from duckpilot.figuren import FIGUR_KEYS
from duckpilot.motion import behaviors as B
from duckpilot.motion.eigenstaendig import (
    EIGEN,
    Eigenstaendig,
    Lage,
    angebot,
    ortsbewegung,
    sperre,
    waehlen,
    wartezeit,
)
from duckpilot.server.app import Runtime
from duckpilot.server.oberflaeche import seite

STATIC = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"
TRICK_STEHEN = [{"t": 0.0, "kopf": {}}, {"t": 0.5, "kopf": {"nicken": 12}}, {"t": 1.0, "kopf": {}}]
TRICK_LAUFEN = [{"t": 0.0, "fahren": {"vx": 0.1}}, {"t": 1.0, "fahren": {}}]
BALL = {"name": "Ball", "art": "ball", "entfernung_m": 1.0, "richtung_grad": 20}
MENSCH = {"name": "Mensch", "art": "person", "entfernung_m": 1.5, "richtung_grad": -40}


def _lage(backend, **kw) -> Lage:
    return Lage(koerper=getattr(backend, "koerper_art", "microduck"), eigenschaften=frozenset(backend.eigenschaften()),
                skills=tuple(backend.skills() or ()), fehlt=lambda n: fehlt_dem_koerper(n, backend), **kw)


def _arten(angebote) -> set[str]:
    return {b.art for b in angebote}


class _Echt:
    """Der echte Microduck-Roboter (robotd mit Tiefensensor), nur was die Entscheidung braucht."""
    koerper_art = "microduck"

    def eigenschaften(self):
        return frozenset({"beine", "kopf", "schnabel", "policies", "stimmbank", "tiefensensor"})

    def skills(self):
        return ["sit_toggle", "ground_pick", "kick_left", "kick_right", "roulade"]


# ── Charakter ─────────────────────────────────────────────────────────────
def test_wartezeit_nach_charakter_und_einstellung():
    rng = random.Random(1)
    ruhig = [wartezeit(0.0, 0.0, "ab_und_zu", rng) for _ in range(50)]
    lebhaft = [wartezeit(1.0, 1.0, "ab_und_zu", rng) for _ in range(50)]
    assert all(240 <= s <= 360 for s in ruhig) and all(60 <= s <= 120 for s in lebhaft)     # 1–6 min
    oft = [wartezeit(1.0, 1.0, "oft", rng) for _ in range(50)]
    assert all(30 <= s <= 60 for s in oft)
    assert wartezeit(0.5, 0.5, "aus") is None and wartezeit(0.5, 0.5, "quatsch") is None


def test_gewichte_folgen_dem_charakter():
    sim = SimBackend(realtime=False, seed=1)
    lage = _lage(sim, tricks={"winken": TRICK_STEHEN}, dinge=[BALL])
    ruhig = {b.art: b.gewicht for b in angebot(lage, 0.1, 0.1, random.Random(1))}
    lebhaft = {b.art: b.gewicht for b in angebot(lage, 0.9, 0.85, random.Random(1))}
    for art in ("erkunden", "ball", "tanzen", "trick"):
        assert lebhaft[art] > ruhig[art], art
    assert "sitzen" in ruhig and "sitzen" not in lebhaft          # ruhige Charaktere setzen sich hin und ruhen
    assert ruhig["umschauen"] > lebhaft["umschauen"]
    # über viele Ziehungen: lebhaft-verspielt geht öfter los, ruhig bleibt eher stehen
    rng = random.Random(3)
    unterwegs = {"erkunden", "ding", "ball", "laufen"}
    los = lambda e, h: sum(waehlen(angebot(lage, e, h, rng), rng).art in unterwegs for _ in range(400))  # noqa: E731
    assert los(0.9, 0.85) > los(0.1, 0.1) + 40


def test_gestalt_neugier_macht_neugieriger():
    sim = SimBackend(realtime=False, seed=1)
    ohne = {b.art: b.gewicht for b in angebot(_lage(sim), 0.5, 0.3, random.Random(1))}
    mit = {b.art: b.gewicht for b in angebot(_lage(sim, gestalt=("neugier",)), 0.5, 0.3, random.Random(1))}
    assert mit["erkunden"] > ohne["erkunden"] and mit["umschauen"] > ohne["umschauen"]


def test_nicht_zweimal_dasselbe():
    sim = SimBackend(realtime=False, seed=1)
    angebote = angebot(_lage(sim), 0.5, 0.5, random.Random(2))
    rng = random.Random(4)
    assert all(waehlen(angebote, rng, zuletzt="geste").art != "geste" for _ in range(100))
    assert waehlen([], rng) is None


# ── Körper ────────────────────────────────────────────────────────────────
def test_microduck_im_simulator():
    sim = SimBackend(realtime=False, seed=1)
    arten = _arten(angebot(_lage(sim, tricks={"winken": TRICK_STEHEN}, dinge=[BALL]), 0.3, 0.6, random.Random(1)))
    assert {"trick", "gefuehl", "erkunden", "ding", "ball", "tanzen", "sitzen", "umschauen", "geste"} <= arten
    assert not arten & {"pollen", "laufen", "zuwenden", "antennen"}
    ohne_ball = _arten(angebot(_lage(sim), 0.9, 0.9, random.Random(1)))
    assert "ball" not in ohne_ball and "ding" not in ohne_ball and "trick" not in ohne_ball


def test_open_duck_ohne_pollen_und_ohne_erkunden():
    od = OpenDuckSim(realtime=False, seed=1)
    assert "tiefensensor" not in od.eigenschaften()
    arten = _arten(angebot(_lage(od, dinge=[BALL]), 0.6, 0.6, random.Random(1)))
    assert {"laufen", "umschauen", "antennen", "geste", "tanzen", "ball"} <= arten   # Schuss nachgestellt (0.38.21)
    assert not arten & {"gefuehl", "pollen", "erkunden"}     # keine Pollen-Gefühle, kein Tiefensensor
    # mit nachgerüstetem Tiefensensor darf sie erkunden
    od.extras = frozenset({"tiefensensor"})
    assert "erkunden" in _arten(angebot(_lage(od), 0.6, 0.6, random.Random(1)))


def test_reachy_nur_was_er_kann():
    r = ReachyMiniSim(realtime=False, seed=1)
    lage = _lage(r, tricks={"winken": TRICK_STEHEN}, dinge=[BALL, MENSCH], pollen=("curious1", "cheerful2", "sad1"))
    arten = _arten(angebot(lage, 0.5, 0.5, random.Random(1)))
    assert {"umschauen", "geste", "pollen", "tanzen", "zuwenden", "antennen"} <= arten
    assert not arten & {"erkunden", "ball", "laufen", "ding", "sitzen", "gefuehl", "trick"}
    pollen = next(b for b in angebot(lage, 0.5, 0.5, random.Random(1)) if b.art == "pollen")
    assert pollen.args["name"] in ("curious1", "cheerful2")                  # nie traurig von sich aus
    assert "pollen" not in _arten(angebot(_lage(r), 0.5, 0.5, random.Random(1)))   # Bibliothek nicht geladen


def test_im_sitzen_nur_kopf_und_aufstehen():
    sim = SimBackend(realtime=False, seed=1)
    arten = _arten(angebot(_lage(sim, sitzt=True, dinge=[BALL], tricks={"winken": TRICK_STEHEN}), 0.8, 0.8,
                           random.Random(1)))
    assert arten <= {"geste", "umschauen", "aufstehen", "antennen"} and "aufstehen" in arten


# ── Echter Roboter ────────────────────────────────────────────────────────
def test_echter_roboter_ohne_ortsbewegung():
    lage = Lage(koerper="microduck", echt=True, eigenschaften=_Echt().eigenschaften(), skills=tuple(_Echt().skills()),
                tricks={"nicken": TRICK_STEHEN, "rennen": TRICK_LAUFEN}, dinge=[BALL],
                fehlt=lambda n: fehlt_dem_koerper(n, _Echt()))
    for e, h in ((0.1, 0.1), (0.9, 0.9), (0.5, 0.6)):
        for seed in range(8):
            angebote = angebot(lage, e, h, random.Random(seed))
            assert not any(b.ort for b in angebote)
            assert not _arten(angebote) & {"erkunden", "ding", "ball", "laufen", "sitzen", "aufstehen", "zuwenden"}
            for b in angebote:
                if b.art == "tanzen":
                    assert b.args["style"] == "nicken"                       # ohne Schritte
                if b.art == "trick":
                    assert b.args["name"] == "nicken"                        # nie der Trick mit Laufen
    reachy = Lage(koerper="reachy_mini", echt=True, eigenschaften=ReachyMiniSim(realtime=False).eigenschaften(),
                  dinge=[MENSCH])
    arten = _arten(angebot(reachy, 0.6, 0.6, random.Random(1)))
    assert "anschauen" in arten and not arten & {"zuwenden", "tanzen"}       # nur den Kopf drehen


def test_engine_lehnt_ortsbewegung_am_echten_roboter_ab():
    async def go():
        sim, eng = await make()
        eng.last_state = replace(eng.last_state, backend="robotd")
        token = EIGEN.set(True)
        try:
            weg = eng.run(B.Explore(20))
            kopf = eng.run(B.LookAround(4))
        finally:
            EIGEN.reset(token)
        return eng, weg, kopf

    eng, weg, kopf = asyncio.run(go())
    assert weg.failed and weg.done and eng.current is kopf and kopf.eigenstaendig
    assert ortsbewegung(B.Explore(5)) and ortsbewegung(B.SkillRun("sit_toggle")) and not ortsbewegung(B.LookAround(2))
    assert not ortsbewegung(B.Dance("nicken", 4))
    # ein Befehl des Menschen bleibt davon unberührt
    asyncio.run(asyncio.sleep(0))
    assert eng.run(B.Walk(0.2)) is eng.current


# ── Sicherheitssperren, einzeln ───────────────────────────────────────────
SPERREN = ["aus", "kopf", "notaus", "still", "ruhe", "hochgehoben", "gefallen", "stromlos", "skill", "beschaeftigt",
           "spiel", "gespraech", "spricht", "mitfuehlend", "handsteuerung", "blick", "zuhoeren"]


@pytest.mark.parametrize("fall", SPERREN)
def test_jede_sperre_einzeln(fall):
    async def go():
        sim, eng = await make()
        kw = {"haeufigkeit": "ab_und_zu", "im_koerper": True, "ruhe": False, "spiel": False, "gespraech": False}
        assert sperre(eng, **kw) is None                                      # sonst frei
        st = eng.last_state
        if fall == "aus":
            kw["haeufigkeit"] = "aus"
        elif fall == "kopf":
            kw["im_koerper"] = False
        elif fall == "notaus":
            eng.notaus()
        elif fall == "still":
            eng.still = True
        elif fall in ("ruhe", "spiel", "gespraech"):
            kw[fall] = True
        elif fall == "hochgehoben":
            eng.last_state = replace(st, picked_up=True)
        elif fall == "gefallen":
            eng.last_state = replace(st, fallen=True)
        elif fall == "stromlos":
            eng.last_state = replace(st, powered=False)
        elif fall == "skill":
            eng.last_state = replace(st, skill="kick_left")
        elif fall == "beschaeftigt":
            eng.run(B.LookAround(5))
        elif fall == "spricht":
            eng.speak([0.5] * 20)
        elif fall == "mitfuehlend":
            eng.mood.appraise_text("Mir geht es heute gar nicht gut, ich bin so traurig.")
            if not eng.mood.empathic:
                pytest.skip("Stimmung reagiert anders")
        elif fall == "handsteuerung":
            eng.manual_drive(Twist(), hold=5.0)
        elif fall == "blick":
            eng.look_at(point=(1.0, 0.0, 0.0), seconds=5)
        elif fall == "zuhoeren":
            eng.attention(5.0)
        return sperre(eng, **kw)

    assert asyncio.run(go())


def test_notaus_sperre_haelt_auch_nach_langer_ruhe():
    async def go():
        sim, eng = await make()
        eng.notaus()
        uhr = Eigenstaendig(random.Random(1))
        t = time.monotonic()
        gesperrt = sperre(eng, haeufigkeit="oft")
        return [uhr.takt(t + s, gesperrt, warten=False, energie=1, humor=1, haeufigkeit="oft") for s in (0, 100, 10_000)]

    assert not any(asyncio.run(go()))


# ── Uhr ───────────────────────────────────────────────────────────────────
def test_uhr_zaehlt_ruhe_und_faengt_bei_kontakt_von_vorn_an():
    uhr = Eigenstaendig(random.Random(1))
    kw = {"energie": 1.0, "humor": 1.0, "haeufigkeit": "ab_und_zu"}
    assert not uhr.takt(0.0, None, warten=False, **kw)
    assert not uhr.takt(50.0, None, warten=False, **kw)                     # 1–2 min bei lebhaft
    assert not uhr.takt(100.0, None, warten=False, kontakt_at=90.0, **kw)   # der Mensch war da: von vorn
    assert not uhr.takt(150.0, None, warten=False, **kw)
    assert not uhr.takt(300.0, None, warten=True, **kw)                     # eine Leerlauf-Geste läuft: kurz warten
    assert uhr.takt(301.0, None, warten=False, **kw)
    assert not uhr.takt(302.0, None, warten=False, **kw)                    # danach wieder von vorn
    assert not uhr.takt(1000.0, "Not-Aus", warten=False, **kw)
    assert uhr.status(1000.0)["gesperrt"] == "Not-Aus"
    aus = Eigenstaendig(random.Random(1))
    assert not any(aus.takt(t, None, warten=False, energie=1, humor=1, haeufigkeit="aus") for t in (0, 500, 5000))


# ── Unterbrechen ──────────────────────────────────────────────────────────
async def _eigen(eng, b):
    token = EIGEN.set(True)
    try:
        return eng.run(b)
    finally:
        EIGEN.reset(token)


@pytest.mark.parametrize("wie", ["angesprochen", "zuhoeren", "handsteuerung", "blick", "befehl", "befehl_dahinter",
                                 "notaus"])
def test_jede_unterbrechung(wie):
    async def go():
        sim, eng = await make()
        b = await _eigen(eng, B.LookAround(20))
        assert b.eigenstaendig and eng.current is b
        await run_for(sim, eng, 0.3)
        neu = None
        if wie == "angesprochen":
            eng.angesprochen()
        elif wie == "zuhoeren":
            eng.attention(3)
        elif wie == "handsteuerung":
            eng.manual_drive(Twist(0.1, 0, 0))
        elif wie == "blick":
            eng.look_at(seconds=0)
        elif wie == "befehl":
            neu = eng.run(B.Turn(30))
        elif wie == "befehl_dahinter":
            neu = eng.run(B.Turn(30), then=True)                 # nie hinter einer eigenen Beschäftigung warten
        elif wie == "notaus":
            eng.notaus()
            await eng.stop_all("Stopp-Knopf")
        await run_for(sim, eng, 0.1)
        return eng, b, neu

    eng, b, neu = asyncio.run(go())
    assert eng.current is not b and b not in eng.queue
    if neu is not None:
        assert eng.current is neu and not getattr(neu, "eigenstaendig", False)


def test_ansprechen_beendet_eigene_geste_aber_keinen_befehl():
    async def go():
        sim, eng = await make()
        token = EIGEN.set(True)
        try:
            assert eng.play_overlay(B.EMOTIONS["nicken"], force=True)
        finally:
            EIGEN.reset(token)
        eng.angesprochen()
        geste_weg = eng.overlay is None
        befehl = eng.run(B.LookAround(10))
        eng.angesprochen()
        return geste_weg, eng.current is befehl

    geste_weg, befehl_bleibt = asyncio.run(go())
    assert geste_weg and befehl_bleibt


# ── Laufzeit ──────────────────────────────────────────────────────────────
@pytest.fixture()
def rt(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    r.backend._task = object()                                   # ohne Hintergrundschleife, Takt von Hand
    return r


async def _wach(rt):
    rt.im_koerper = True
    gesendet = []

    async def mit(msg):
        gesendet.append(msg)
    rt.broadcast = mit
    await rt.engine.stand_up()
    await run_for(rt.backend, rt.engine, 2.5)
    return gesendet


def test_laufzeit_handelt_und_meldet_im_ticker(rt):
    async def go():
        await _wach(rt)
        assert rt.config.eigenstaendig == "ab_und_zu" and rt.eigenstaendig_sperre() is None
        res = await rt.eigenstaendig_handeln("erkunden")
        b = rt.engine.current
        await run_for(rt.backend, rt.engine, 0.5)
        return res, b

    res, b = asyncio.run(go())
    assert res["ok"] and res["werkzeug"] == "explore" and type(b).__name__ == "Explore" and b.eigenstaendig
    ticker = [e for e in rt.engine.events if e.get("type") == "charakter" and e.get("eigenstaendig")]
    assert ticker and ticker[-1]["art"] == "erkunden" and "erkundet" in ticker[-1]["message"]


def test_laufzeit_uhr_loest_nach_ruhe_aus(rt):
    async def go():
        await _wach(rt)
        rt._eigen_uhr().rng = random.Random(5)
        t = time.monotonic()
        vorher = await rt.eigenstaendig_takt(t)
        nachher = await rt.eigenstaendig_takt(t + 400)              # länger als jede Wartezeit
        return vorher, nachher

    vorher, nachher = asyncio.run(go())
    assert vorher is None and nachher and nachher["ok"]


def test_laufzeit_trick_aus_dem_gedaechtnis_und_ding_anstupsen(rt):
    async def go():
        await _wach(rt)
        rt.memory.remember_trick("verbeugen", TRICK_STEHEN)
        trick = await rt.eigenstaendig_handeln("trick")
        t = rt.engine.current
        await rt.engine.stop_all("Test")
        rt.engine.estop_at = -1e9
        ding = await rt.eigenstaendig_handeln("ding")
        return trick, t, ding, rt.engine.current, list(rt.engine.queue)

    trick, t, ding, hin, danach = asyncio.run(go())
    assert trick["ok"] and trick["args"]["name"] == "verbeugen" and t.eigenstaendig
    assert ding["ok"] and hin.eigenstaendig and danach and all(b.eigenstaendig for b in danach)
    assert danach[-1].needs_target                                   # nicht ins Leere picken


def test_laufzeit_ansprechen_und_notaus_unterbrechen(rt):
    async def go():
        await _wach(rt)
        await rt.eigenstaendig_handeln("erkunden")
        b = rt.engine.current
        await rt.handle_client_message({"type": "listening"})        # Mikrofon auf = Ansprechen
        weg1 = rt.engine.current is not b
        await rt.eigenstaendig_handeln("umschauen")
        c = rt.engine.current
        await rt.handle_client_message({"type": "stop"})
        weg2 = rt.engine.current is None and c.eigenstaendig
        gesperrt = rt.eigenstaendig_sperre()
        spaeter = await rt.eigenstaendig_takt(time.monotonic() + 10_000)
        return weg1, weg2, gesperrt, spaeter

    weg1, weg2, gesperrt, spaeter = asyncio.run(go())
    assert weg1 and weg2 and "Not-Aus" in gesperrt and spaeter is None


def test_laufzeit_echter_roboter_nie_von_der_stelle(rt):
    async def go():
        await _wach(rt)
        rt.config.backend = "robotd"                                  # so tun, als wäre es der echte Roboter
        lage = rt.eigenstaendig_lage()
        ergebnisse = [await rt.eigenstaendig_handeln(art) for art in ("erkunden", "ding", "ball", "sitzen", "tanzen")]
        return lage, ergebnisse

    lage, ergebnisse = asyncio.run(go())
    assert lage.echt
    assert ergebnisse[:4] == [None, None, None, None]                 # gar nicht erst angeboten
    tanz = ergebnisse[4]
    assert tanz is None or tanz["args"]["style"] == "nicken"


def test_laufzeit_im_kopf_und_ruhe_nichts(rt):
    async def go():
        await _wach(rt)
        rt.im_koerper = False
        a = rt.eigenstaendig_sperre()
        rt.im_koerper = True
        await rt.apply_settings({"eigenstaendig": "aus"})
        b = rt.eigenstaendig_sperre()
        return a, b

    a, b = asyncio.run(go())
    assert "Kopf" in a and b == "ausgeschaltet"


# ── Einstellung und Oberfläche ────────────────────────────────────────────
def test_einstellung_und_schalter(tmp_settings):  # noqa: F811
    assert S.validate({"eigenstaendig": "oft"}) == {"eigenstaendig": "oft"}
    with pytest.raises(ValueError):
        S.validate({"eigenstaendig": "immer"})
    assert "eigenstaendig" in FIGUR_KEYS                                # jede Verkörperung für sich
    html = seite()
    for wert in ("aus", "ab_und_zu", "oft"):
        assert f'value="{wert}" data-set="eigenstaendig"' in html
    S.save_user_settings({"eigenstaendig": "oft"})
    assert json.loads(tmp_settings.read_text(encoding="utf-8"))["eigenstaendig"] == "oft"
