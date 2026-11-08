"""Reachy Mini: nur erreichbare Kopflagen (seit 0.38.10).

Beobachtung aus dem Test: Bei „freu dich“ tauchte Reachys Kopf im 3D-Simulator in die Körperschale – jede Achse war für sich
in Pollens Grenzen, die Kombination (Nicken + Neigen + tiefer) aber nicht. Jetzt prüft `reachy_kinematik` die ganze
Lage (sechs Stangen der Stewart-Plattform + Abstand zum Körper) und nimmt Unerreichbares Richtung Neutral zurück –
für Simulator und echten Reachy an einer Stelle. Mit Pollens Modell (nur private Fassung / Datenordner) genau, ohne
mit einer vorsichtigen Ersatzprüfung.
"""

import asyncio
import math
import random

import pytest
from helpers import run_for

from duckpilot.api import Head, Pose
from duckpilot.backends import reachy as R
from duckpilot.backends import reachy_kinematik as K
from duckpilot.backends.reachy import ReachyMiniDaemon, ReachyMiniSim, kopf_ziel, zusammen
from duckpilot.motion.behaviors import EMOTIONS, Choreography, emotion
from duckpilot.motion.engine import MotionEngine
from duckpilot.motion.reachy_gesten import GESTEN

GEO = K.Geometrie.aus_modell()
mit_modell = pytest.mark.skipif(GEO is None, reason="Pollens Reachy-Modell liegt nicht vor (öffentliche Fassung)")
GEOS = [pytest.param(GEO, id="modell", marks=mit_modell), pytest.param(None, id="ersatz")]
D = math.radians


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def geo_wahl():
    """Geometrie für die Dauer eines Tests festlegen (None = Ersatzprüfung) und danach zurücksetzen."""
    def setzen(g):
        K.geometrie_setzen(g)
        K._letzte = None
    yield setzen
    K.geometrie_neu_laden()
    K._letzte = None


def _zufall(rng, weit=1.0):
    return {k: rng.uniform(-g, g) * weit for k, g in K.GRENZE.items()}


def _ecken():
    out = []
    for i in range(64):
        out.append({k: (g if i >> n & 1 else -g) for n, (k, g) in enumerate(K.GRENZE.items())})
    return out


FREUDE_BEOBACHTET = {"x": 0.0, "y": 0.0, "z": -0.008, "roll": D(-14), "pitch": D(26), "yaw": 0.0}


# ── Prüfung und Zurücknehmen ──────────────────────────────────────────────
@pytest.mark.parametrize("geo", GEOS)
def test_neutral_bleibt_neutral(geo):
    assert K.erreichbar(K.NEUTRAL, geo)
    assert K.begrenzen(K.NEUTRAL, geo) == K.NEUTRAL
    assert K.begrenzen({}, geo) == K.NEUTRAL


@pytest.mark.parametrize("geo", GEOS)
def test_zufaellige_und_extreme_lagen_werden_erreichbar(geo):
    rng = random.Random(7)
    lagen = _ecken() + [_zufall(rng) for _ in range(250)] + [_zufall(rng, 0.4) for _ in range(150)]
    lagen += [{"pitch": D(40), "roll": D(40), "z": -0.045}, {"pitch": D(-40), "yaw": D(65), "z": 0.045},
              {"x": 0.03, "y": -0.03, "roll": D(-40)}, {"pitch": 5.0, "roll": -5.0, "yaw": 9.0, "z": 1.0},
              FREUDE_BEOBACHTET]
    for lage in lagen:
        out = K.begrenzen(lage, geo)
        assert set(out) == set(K.ACHSEN)
        assert K.erreichbar(out, geo), (lage, out)


@pytest.mark.parametrize("geo", GEOS)
def test_zurueckgenommen_so_nah_wie_moeglich(geo):
    """Erreichbares bleibt unverändert; Unerreichbares wird nur so weit zurückgenommen, wie nötig: schon ein kleines
    Stück weiter Richtung Wunsch ginge nicht mehr."""
    rng = random.Random(11)
    zurueck = 0
    for _ in range(200):
        lage = _zufall(rng, 0.6)
        out = K.begrenzen(lage, geo)
        if K.erreichbar(lage, geo):
            assert out == pytest.approx(K._klemmen(lage))
            continue
        zurueck += 1
        behalten = ("yaw",) if out["yaw"] == pytest.approx(lage["yaw"]) and lage["yaw"] else ()
        achse = max((k for k in K.ACHSEN if k not in behalten), key=lambda k: abs(lage[k]))
        s = out[achse] / lage[achse]
        assert 0.0 <= s < 1.0
        for k in K.ACHSEN:                                    # nur Richtung Neutral, nie über den Wunsch hinaus
            assert abs(out[k]) <= abs(lage[k]) + 1e-12 and out[k] * lage[k] >= 0
        assert not K.erreichbar(K._mal(lage, min(1.0, s / K.LUFT + 2 ** -K.SCHRITTE + 1e-9), behalten), geo)
    assert zurueck > 10


@mit_modell
def test_freude_lage_aus_der_beobachtung():
    """Die beobachtete Lage (pitch +26°, roll −14°, z −8 mm) steckt im Körper – zurückgenommen bleibt sie nah dran."""
    assert GEO.stangen_ok(FREUDE_BEOBACHTET) and GEO.abstand(FREUDE_BEOBACHTET) < 0
    out = K.begrenzen(FREUDE_BEOBACHTET, GEO)
    assert GEO.abstand(out) >= K.ABSTAND_M
    assert math.degrees(out["pitch"]) > 20 and math.degrees(out["roll"]) < -10


@mit_modell
def test_grundstellung_wie_pollens_kinematik():
    """Motorwinkel in der Grundstellung wie Pollens analytische Kinematik (±0,626 rad, abwechselnd)."""
    w = GEO.motorwinkel(K.NEUTRAL)
    assert all(x is not None for x in w)
    assert [round(abs(x), 2) for x in w] == [0.63] * 6 and w[0] * w[1] < 0
    assert not GEO.stangen_ok({**K.NEUTRAL, "z": 0.04})              # so hoch reichen die Stangen nicht
    assert GEO.abstand({**K.NEUTRAL, "z": -0.045}) < 0               # so tief steckt der Kopf im Körper


@mit_modell
def test_ersatzpruefung_ist_vorsichtiger_als_das_modell():
    """Was die Ersatzprüfung (ohne Pollens Modell) erlaubt, ist mit Modell erreichbar – auch auf ihrem Rand."""
    rng = random.Random(5)
    E = K.ERSATZ
    geprueft = 0
    for _ in range(3000):
        t, d, a = rng.uniform(0, E["kipp_grad"]), rng.uniform(-E["dreh_grad"], E["dreh_grad"]), rng.uniform(0, 6.3)
        lo = E["unten"][0] + E["unten"][1] * t + E["unten"][2] * abs(d)
        hi = E["oben"][0] + E["oben"][1] * t + E["oben"][2] * abs(d)
        if lo > hi:
            continue
        xy = E["xy_mm"] / 1000
        lage = {"x": rng.choice([-xy, xy, 0.0]), "y": rng.choice([-xy, xy, 0.0]),
                "z": rng.choice([lo, hi, rng.uniform(lo, hi)]) / 1000,
                "roll": D(t) * math.cos(a), "pitch": D(t) * math.sin(a), "yaw": D(d)}
        assert K.ersatz_erreichbar(lage)
        assert GEO.erreichbar(lage), lage
        geprueft += 1
    assert geprueft > 1000


def test_ersatzpruefung_vorsichtig_bei_kombinationen():
    assert K.ersatz_erreichbar({"pitch": D(12), "roll": D(6)})
    assert not K.ersatz_erreichbar({"pitch": D(26), "roll": D(-14), "z": -0.008})
    assert not K.ersatz_erreichbar({"pitch": D(15), "z": -0.01})          # stark kippen und dabei absenken
    assert K.ersatz_erreichbar({"pitch": D(15), "z": 0.005})              # gekippt geht es eher etwas höher
    assert not K.ersatz_erreichbar({"yaw": D(45), "pitch": D(15)})


# ── Simulator ─────────────────────────────────────────────────────────────
async def _reachy():
    sim = ReachyMiniSim(realtime=False, seed=1)
    sim._task = object()
    eng = MotionEngine(sim)
    await eng.stand_up()
    await run_for(sim, eng, 2.5)
    return sim, eng


@pytest.mark.parametrize("geo", GEOS)
def test_freu_dich_im_simulator_nur_erreichbare_lagen(geo, geo_wahl):
    """„freu dich“ → Reachys eigene Geste: Kopf etwas hoch, Antennen nach außen und zurück, kein starkes Neigen –
    und über die ganze Zeit nur erreichbare Lagen (auch mit Leerlauf und Atmen obendrauf)."""
    geo_wahl(geo)

    async def go():
        sim, eng = await _reachy()
        assert eng.express("freude", force=True)
        lagen, antennen = [], []
        for _ in range(50):
            await run_for(sim, eng, 0.05)
            st = sim.state()
            lagen.append({k: st.kopf_lage[k] for k in K.ACHSEN})
            antennen.append(st.antennen)
        return lagen, antennen
    lagen, antennen = run(go())
    for lage in lagen:
        assert K.erreichbar(lage, geo), lage
    assert max(abs(a[0]) for a in antennen) > 0.9 and max(a[1] for a in antennen) > 0.9    # nach außen
    assert min(a[1] for a in antennen[-10:]) < 0.6                                         # und zurück
    assert max(abs(lage["roll"]) for lage in lagen) < D(15)


@pytest.mark.parametrize("geo", GEOS)
def test_alle_gefuehle_und_entengesten_bleiben_erreichbar(geo):
    """Reachys Gesten und – falls doch eine Entengeste kommt – auch die, über die Zeit abgetastet."""
    specs = [(n, s, 1.4) for n, s in GESTEN.items()] + [(n, EMOTIONS[n], 1.4) for n in list(EMOTIONS)[:40]]
    for name, spec, k in specs:
        ch = Choreography.from_spec(spec, scale=k)
        t = 0.0
        while t <= ch.length:
            h = ch._interp("head", t) or Head()
            p = ch._interp("pose", t) or Pose()
            ziel = kopf_ziel(h, p)
            for zusatz in ({}, {"z": -0.004, "pitch": 0.05}):         # mit Atmen/Sprechen obendrauf
                K._letzte = None
                out = K.begrenzen({k2: ziel.get(k2, 0) + zusatz.get(k2, 0) for k2 in K.ACHSEN}, geo)
                assert K.erreichbar(out, geo), (name, t, out)
            t += 0.1


@mit_modell
def test_reachy_gesten_brauchen_kaum_zuruecknehmen():
    """Reachys eigene Gesten sind so vorsichtig, dass sie (ohne Zusätze) praktisch unverändert gehen."""
    for name, spec in GESTEN.items():
        ch = Choreography.from_spec(spec)
        t = 0.0
        while t <= ch.length:
            ziel = kopf_ziel(ch._interp("head", t) or Head(), ch._interp("pose", t) or Pose())
            assert GEO.erreichbar({k: ziel.get(k, 0.0) for k in K.ACHSEN}), (name, t, ziel)
            t += 0.1


def test_emote_werkzeug_nimmt_reachys_geste():
    ch = emotion("freude", reachy=True)
    assert any(kf.antennen for kf in ch.kfs)
    assert max(abs(kf.head.head_roll) for kf in ch.kfs if kf.head) == 0.0      # kein Neigen
    assert min(kf.head.head_pitch for kf in ch.kfs if kf.head) < 0             # Kopf hoch
    assert not any(kf.antennen for kf in emotion("freude").kfs)                 # die Ente bleibt, wie sie war


# ── Echter Reachy: dieselbe Prüfung vor set_target ────────────────────────
@pytest.mark.parametrize("geo", GEOS)
def test_daemon_schickt_nur_erreichbare_lagen(geo, geo_wahl, monkeypatch):
    geo_wahl(geo)
    aufrufe = []
    echt = R.begrenzen

    def spion(lage, *a, **kw):
        aufrufe.append(dict(lage))
        return echt(lage, *a, **kw)
    monkeypatch.setattr(R, "begrenzen", spion)
    d = ReachyMiniDaemon()
    gesendet = []

    async def rufen(methode, pfad, body=None):
        gesendet.append((pfad, body))
        return {}
    d._rufen = rufen
    d._wach = True
    d._body_yaw = 0.7

    async def go():
        await d.head(Head(-0.6, 0.8, 1.0, 0.35))        # Nacken vor, Kopf stark nicken, drehen, neigen
        await d.pose(Pose(-0.03, 0.0, 0.0))             # und dabei tief
        await d._senden()
    run(go())
    assert aufrufe, "der Daemon muss über reachy_kinematik.begrenzen gehen"
    ziel = [b for p, b in gesendet if p == "/api/move/set_target"][-1]
    lage = dict(ziel["target_head_pose"])
    lage["yaw"] -= ziel["target_body_yaw"]                # Pollen: Welt; geprüft wird relativ zum Körper
    assert K.erreichbar(lage, geo)
    assert lage == pytest.approx(K.begrenzen(aufrufe[-1], geo), abs=1e-4)
    assert ziel["target_body_yaw"] == 0.7


def test_zusammen_ist_die_eine_stelle(monkeypatch):
    """Simulator und Daemon bilden die Lage beide mit `zusammen` – und das geht über `begrenzen`."""
    gesehen = []
    monkeypatch.setattr(R, "begrenzen", lambda lage: gesehen.append(lage) or K.NEUTRAL)
    assert zusammen({"pitch": 0.3}, {"z": -0.01}) == K.NEUTRAL
    assert gesehen[-1]["pitch"] == 0.3 and gesehen[-1]["z"] == -0.01
