"""Choreografie für jeden Körper (seit 0.43): Tanz-Wortschatz je Bauart, abgeleitet aus dem Profil, nie aus dem Namen."""

import asyncio

import pytest
from helpers import run_for

from duckpilot import arm as A
from duckpilot import choreo as C
from duckpilot import koerper
from duckpilot.backends.bittle import TRICKS, BittleSim
from duckpilot.backends.so101 import So101Sim
from duckpilot.backends.stackchan import StackChanSim
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion import koerper_tanz as KT
from duckpilot.motion import tanzstile as TS
from duckpilot.motion.engine import MotionEngine

ANALYSE = {"bpm": 120, "start": 0.5, "energie": [0.2] * 8 + [0.85] * 16 + [0.4] * 8}


def run(coro):
    return asyncio.run(coro)


# ── Stile und Ableitung ──────────────────────────────────────────────────
def test_stil_folgt_aus_dem_profil():
    stile = {k.id: koerper.tanzstil(k) for k in koerper.alle() if k.eingebaut}
    assert set(stile.values()) == set(TS.STILE)                       # jede Bauart hat einen Körper
    assert koerper.tanzstil(None) == "ente"
    fremd = koerper.Koerper("mein_hund", "Hund", "ich", "vierbeiner", frozenset({"beine", "kopf"}), "x:y")
    assert koerper.tanzstil(fremd) == "vierbeiner"
    kopf = koerper.Koerper("mein_kopf", "Kopf", "ich", "stationaer", frozenset({"kopf", "gesicht"}), "x:y")
    assert koerper.tanzstil(kopf) == "kopf"


@pytest.mark.parametrize("stil", sorted(TS.STILE))
def test_plan_nur_mit_dem_eigenen_wortschatz(stil):
    c = C.plane(ANALYSE, ["Pose"], stil=stil)
    assert c == C.plane(ANALYSE, ["Pose"], stil=stil)                  # gleiche Musik, gleicher Tanz
    tl = C.takt_s(120)
    for a, b in zip(c["schritte"], c["schritte"][1:]):
        assert abs(a["t"] + a["takte"] * tl - b["t"]) < 0.01           # lückenlos auf Taktanfängen
    if stil == "ente":
        assert "stil" not in c and {s["art"] for s in c["schritte"]} & {"schritt", "wiegen"}
        return
    assert c["stil"] == stil and C.pruefe(c)["stil"] == stil
    for s in c["schritte"]:
        assert s["art"] in ("trick", "gefuehl", "pause"), s
        if s["art"] == "trick":
            assert s["name"] in C.gesten(stil), s
        if s["art"] == "gefuehl":
            assert s["name"] in C.gefuehle(stil), s


@pytest.mark.parametrize("stil", ["kopf", "arm", "vierbeiner"])
def test_wortschatz_vollstaendig(stil):
    st = TS.STILE[stil]
    assert set(st.bewegungen()) == set(st.texte) and set(st.aus_ente.values()) <= set(st.texte)
    for name in ("schritt", "drehen", "wiegen", "quatsch"):
        assert st.aufloesen(name) in st.texte
    werkzeug = C.werkzeug({"name": "choreo", "description": "", "input_schema": {"properties": {"schritte": {"items": {
        "properties": {"art": {"type": "string", "enum": []}}}}}}}, stil)
    assert set(werkzeug["input_schema"]["properties"]["schritte"]["items"]["properties"]["name"]["enum"]) == \
        set(C.gesten(stil)) | set(C.gefuehle(stil))
    auftrag = C.ki_auftrag_stil("Lied", "", C.plane(ANALYSE, stil=stil), stil)
    assert st.wie in auftrag and "Bein zu Bein" not in auftrag and "Posen" not in auftrag


def test_kopfbewegungen_in_den_grenzen_und_ohne_ruck():
    for name, kfs in TS.KOPF.items():
        assert kfs[0][1:] == kfs[-1][1:], name                        # endet, wo sie begann
        for _, drehen, nicken in kfs:
            assert abs(drehen) <= 60 and -10 <= nicken <= 30, name


def test_arm_tanz_bleibt_in_den_grenzen():
    for name, folge in A.TANZ.items():
        for haltung, schlaege in folge:
            assert A.begrenzen(haltung) == (haltung, []) and schlaege > 0, name
    assert set(A.TANZ) == set(TS.STILE["arm"].texte)
    assert set(TS.STILE["arm"].gefuehle) <= set(A.GESTEN)


def test_hund_tanzt_nur_tricks_am_platz():
    st = TS.STILE["vierbeiner"]
    assert set(st.texte) | set(st.gefuehle) <= set(TRICKS)
    assert not {"moonwalk", "rueckwaerts", "salto", "rollen"} & set(st.texte)


# ── Abspielen ────────────────────────────────────────────────────────────
async def _wach(sim):
    sim._task = object()
    eng = MotionEngine(sim)
    await eng.stand_up()
    await run_for(sim, eng, 2.5)
    return eng


def test_ari_tanzt_und_der_not_aus_haelt_an():
    async def go():
        sim = So101Sim(realtime=False)
        eng = await _wach(sim)
        tanz = KT.musik_tanz("arm", C.plane(ANALYSE, stil="arm"), titel="Probe")
        assert isinstance(tanz, KT.KoerperMusikTanz)
        eng.run(tanz)
        await run_for(sim, eng, 4.0)
        assert str(sim.geste_name or "").startswith("tanz:")
        bewegt = dict(sim.gelenke)
        await run_for(sim, eng, 0.6)
        assert bewegt != sim.gelenke                                  # er tanzt wirklich
        await eng.not_aus("Test")
        await run_for(sim, eng, 0.5)
        assert eng.current is None and not sim.powered
        assert not (await sim.tanz_schritt("wiegen", 2.0, 110)).accepted    # nach dem Not-Aus nichts
    run(go())


def test_ari_tanzt_nicht_mit_einem_wuerfel():
    async def go():
        sim = So101Sim(realtime=False)
        await _wach(sim)
        sim.werkbank.haelt = sim.werkbank.dinge[0]["name"]
        r = await sim.tanz_schritt("wiegen", 4.0, 110)
        assert not r.accepted and "Würfel" in r.reason
    run(go())


def test_bello_wiederholt_seinen_trick_bis_zum_schrittende():
    async def go():
        sim = BittleSim(realtime=False, seed=1)
        eng = await _wach(sim)
        assert (await sim.tanz_schritt("nicken", 6.0, 110)).accepted
        starts = []
        sim.emit = lambda art, **kw: starts.append(kw.get("skill")) if art == "skill_start" else None
        await run_for(sim, eng, 6.5)
        assert starts.count("nicken") >= 2 and sim._tanz is None
        assert not (await sim.tanz_schritt("moonwalk", 4.0, 110)).accepted   # nimmt ihn mit: nicht im Tanz
    run(go())


def test_stacki_tanzt_mit_kopf_gesicht_und_licht():
    async def go():
        sim = StackChanSim(realtime=False, seed=1)
        eng = await _wach(sim)
        tanz = KT.musik_tanz("kopf", C.plane(ANALYSE, stil="kopf"), titel="Probe")
        eng.run(tanz)
        drehen = set()
        for _ in range(40):
            await run_for(sim, eng, 0.25)
            lage = sim.state().kopf_lage
            drehen.add((round(lage["yaw"], 2), round(lage["pitch"], 2)))     # drehen oder nicken
        assert len(drehen) > 3                                        # der Kopf bewegt sich im Takt
        assert sim._tanz_bis > sim.t                                  # Licht tanzt mit
        eng.cancel_current("Test")
        assert sim._tanz_bis == 0.0                                   # und hört mit auf
    run(go())


def test_werkzeuge_bieten_je_koerper_nur_seinen_tanz():
    async def go():
        for cls, stil in ((So101Sim, "arm"), (StackChanSim, "kopf"), (BittleSim, "vierbeiner")):
            sim = cls(realtime=False)
            eng = await _wach(sim)
            runner = ToolRunner(eng)
            assert runner._tanzstil() == stil
            werkzeug = next((t for t in runner.tools() if t["name"] == "choreo"), None)
            if werkzeug is not None:
                namen = werkzeug["input_schema"]["properties"]["schritte"]["items"]["properties"]["name"]["enum"]
                assert set(namen) == set(C.gesten(stil)) | set(C.gefuehle(stil))
            r = await runner.run("dance", {"style": "party", "seconds": 4})
            assert r.get("ok", True) and isinstance(eng.current, KT.KoerperMusikTanz), (stil, r)
            gehoer = KT.gehoer_tanz(stil, ruhig=True)
            assert isinstance(gehoer, KT.KoerperGehoerTanz) and gehoer.stufe() == 0
    run(go())
