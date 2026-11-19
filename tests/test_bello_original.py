"""Bello wie das Original (seit 0.38.65, Releaseplan des Maintainers: „Bello wie das Original – Maße nach Petois
MIT-Modell, Gangarten“): Bittle X mit den Maßen aus Petois offenem Simulationsmodell, drei Gangarten (Krabbeln, Traben,
Hoppeln) und Bewegungen nach Petois Kürzeln (Rückwärts, Auf der Stelle, Moonwalk, Umarmen, Komm her, Rollen).
Gezeichnet bleibt er selbst – Petois Zahlen, keine Dateien."""

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from duckpilot.api import Twist
from duckpilot.backends.bittle import GANGARTEN, GRUND_GANGART, TRICKS, BittleSim

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
MODUL = (STATIC / "bittle3d.js").as_uri()


def _node(code: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    r = subprocess.run([node, "--input-type=module", "-e", code], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _wach() -> BittleSim:
    sim = BittleSim(realtime=False)

    async def go():
        await sim.connect()
        await sim.init()
        await sim.enable(True)
    asyncio.run(go())
    _laufen(sim, 3.0)
    return sim


def _laufen(sim, sekunden, twist=None):
    for _ in range(int(sekunden / 0.05)):
        if twist is not None:
            asyncio.run(sim.move(twist))                          # Totmann: immer wieder schicken
        sim.step(0.05)


def test_masse_nach_petois_modell():
    """Hüften ±7,35 cm vorn/hinten und ±4,85 cm seitlich, Oberschenkel 4,6 cm, Unterschenkel 5,5 cm, Platte 12,7 × 9 cm
    (bittle_simple.xml im Repo PetoiCamp/OpenCat-Quadruped-Robot, MIT)."""
    out = _node(f"import {{ MASSE }} from '{MODUL}'; console.log(JSON.stringify(MASSE));")
    assert (out["hueftX"], out["hueftZ"], out["oben"], out["unten"]) == (0.0735, 0.0485, 0.046, 0.055)
    assert (out["laenge"], out["breite"]) == (0.127, 0.09)
    js = (STATIC / "bittle3d.js").read_text(encoding="utf-8")
    assert "MASSE.hueftX, -MASSE.hueftZ" in js and ".stl" not in js and ".obj" not in js   # keine Meshes von außen


def test_steht_sitzt_und_laeuft_auf_dem_boden():
    """Mit den längeren Unterschenkeln hingen vorher im Sitzen die Vorderpfoten 2 cm in der Luft und beim Strecken die
    Hinterpfoten. Jetzt kommt die Rumpfhöhe aus den Beinen, und Sitzen/Strecken neigen den Rumpf, bis vorn und hinten
    ein Fuß aufsteht. Krabbeln hat fast immer drei Füße am Boden, Traben und Hoppeln mindestens zwei."""
    code = (f"import {{ bodenHoehe, fussHoehen, gangBeine, GANGARTEN, TRICKS }} from '{MODUL}';"
            "const auf = (p, n) => { const y = bodenHoehe(p.s, p.k, n); return fussHoehen(p.s, p.k, n, y); };"
            "const stand = auf({ s: [0.45, 0.45, -0.45, -0.45], k: [-0.85, -0.85, 0.85, 0.85] }, 0);"
            "const gaenge = {}; for (const g of Object.keys(GANGARTEN)) { let min = 9, unter = 0;"
            "  for (let i = 0; i < 144; i++) { const b = gangBeine(g, i / 144 * 2 * Math.PI); const h = auf(b, b.n);"
            "    min = Math.min(min, h.filter((v) => v < 0.003).length); unter = Math.min(unter, ...h); }"
            "  gaenge[g] = { min, unter }; }"
            "const zwei = {}; for (const t of ['pfote', 'kratzen', 'komm_her', 'strecken', 'verbeugen', 'schnueffeln', 'graben', 'liegestuetze']) {"
            "  const p = TRICKS[t](0.5); const h = auf(p, p.n);"
            "  zwei[t] = [Math.min(h[0], h[1]), Math.min(h[2], h[3])]; }"
            "console.log(JSON.stringify({ stand, gaenge, zwei }));")
    out = _node(code)
    assert all(abs(h) < 1e-6 for h in out["stand"])                        # alle vier Füße auf dem Boden
    assert out["gaenge"]["krabbeln"]["min"] >= 3
    assert out["gaenge"]["traben"]["min"] >= 2 and out["gaenge"]["hoppeln"]["min"] >= 2
    assert all(g["unter"] > -1e-6 for g in out["gaenge"].values())        # nie ein Fuß im Boden
    for trick, (vorn, hinten) in out["zwei"].items():                    # vorn und hinten steht je ein Fuß auf
        assert abs(vorn) < 0.002 and abs(hinten) < 0.002, (trick, vorn, hinten)


def test_gangarten_umschalten_und_tempo():
    sim = _wach()
    assert sim.state().gangart == GRUND_GANGART == "traben"
    tempo = {}
    for gang in ("krabbeln", "traben", "hoppeln"):
        r = asyncio.run(sim.do(gang))
        assert r.accepted and sim.state().gangart == gang
        x0 = sim.x
        _laufen(sim, 3.0, Twist(0.25, 0.0, 0.0))
        tempo[gang] = (sim.x - x0) / 3.0
        assert sim.state().twist.vx <= GANGARTEN[gang][1] + 1e-9
        _laufen(sim, 1.0)                                                 # anhalten (Totmann)
    assert tempo["krabbeln"] < tempo["traben"] < tempo["hoppeln"]
    # rückwärts höchstens halb so schnell wie vorwärts
    asyncio.run(sim.do("krabbeln"))
    _laufen(sim, 2.0, Twist(-0.15, 0.0, 0.0))
    assert sim.state().twist.vx >= -GANGARTEN["krabbeln"][1] / 2 - 1e-9
    # Gangart wechseln geht auch im Sitzen; Unbekanntes bleibt ehrlich abgelehnt
    _laufen(sim, 1.0)
    asyncio.run(sim.do("sit_toggle"))
    _laufen(sim, 2.0)
    assert asyncio.run(sim.do("hoppeln")).accepted and sim.state().gangart == "hoppeln"
    assert not asyncio.run(sim.do("galopp")).accepted


def test_bewegungen_nach_petoi():
    """Rückwärts und Moonwalk nehmen ihn ein Stück mit, auf der Stelle bleibt er stehen; der Not-Aus beendet sofort."""
    sim = _wach()
    for trick, richtung in (("rueckwaerts", -1), ("moonwalk", -1), ("auf_der_stelle", 0)):
        x0 = sim.x
        assert asyncio.run(sim.do(trick)).accepted
        _laufen(sim, TRICKS[trick][1] + 0.5)
        weg = sim.x - x0
        if richtung:
            assert weg < -0.1, (trick, weg)
        else:
            assert abs(weg) < 0.01, (trick, weg)
        assert sim.state().skill is None
    for trick in ("umarmen", "komm_her", "rollen"):
        x0 = sim.x
        assert asyncio.run(sim.do(trick)).accepted
        _laufen(sim, TRICKS[trick][1] + 0.3)
        assert abs(sim.x - x0) < 0.01 and sim.state().skill is None
    asyncio.run(sim.do("moonwalk"))
    _laufen(sim, 1.0)
    asyncio.run(sim.relax())                                              # Not-Aus: stromlos, Trick vorbei, steht still
    x0 = sim.x
    _laufen(sim, 1.0)
    assert not sim.state().powered and sim.state().skill in (None, "_relax") and abs(sim.x - x0) < 0.02


def test_oberflaeche_kennt_gangarten_und_tricks():
    js = (STATIC / "bittle3d.js").read_text(encoding="utf-8")
    out = _node(f"import {{ GANGARTEN, TRICKS }} from '{MODUL}'; console.log(JSON.stringify("
                "{ gang: Object.keys(GANGARTEN), tricks: Object.keys(TRICKS) }));")
    assert set(out["gang"]) == set(GANGARTEN) and set(out["tricks"]) == set(TRICKS)
    assert "st.gangart" in js
    html = (STATIC / "teile" / "tricks.html").read_text(encoding="utf-8")
    assert re.findall(r'data-bello-gang="(\w+)"', html) == list(GANGARTEN)
    seite = (STATIC / "tricks_seite.js").read_text(encoding="utf-8")
    assert "#bello-gangarten [data-bello-gang]" in seite and "aria-pressed" in seite
    assert "tricksSeite.gangart(st.gangart)" in (STATIC / "app.js").read_text(encoding="utf-8")


def test_zuruf_ohne_ki():
    from duckpilot.brain.fallback import parse

    k = frozenset(BittleSim(realtime=False).skills())
    assert parse("Krabbel!", k) == [("skill", {"name": "krabbeln"})]
    assert parse("trab los", k) == [("skill", {"name": "traben"})]
    assert parse("Hoppel!", k) == [("skill", {"name": "hoppeln"})]
    assert parse("trab rückwärts", k) == [("skill", {"name": "rueckwaerts"})]
    assert parse("mach den Moonwalk", k) == [("skill", {"name": "moonwalk"})]
    assert parse("tritt auf der Stelle", k) == [("skill", {"name": "auf_der_stelle"})]
    assert parse("umarme mich", k) == [("skill", {"name": "umarmen"})]
    assert parse("wink mich her", k) == [("skill", {"name": "komm_her"})]
    assert parse("roll dich", k) == [("skill", {"name": "rollen"})]
    # „komm her“ und „geh rückwärts“ bleiben Laufbefehle; ohne Hund sind die Wörter keine Kommandos
    assert parse("komm her", k)[0][0] == "walk" and parse("geh rückwärts", k)[0][0] == "walk"
    assert parse("krabbel") == [] and parse("roll dich") == [("skill", {"name": "roulade"})]


def test_roll_den_ball_ist_kein_purzelbaum():
    """Fund beim Bauen (15.11.): „roll den Ball“ wurde wegen des englischen Worts „roll“ zum Purzelbaum."""
    from duckpilot.brain.fallback import parse

    assert parse("roll den Ball") == []
    # seit 0.38.66 ein Zuspiel: „roll the ball to me“ = gezielt zum Menschen (Fund 15.11. Ballspielen)
    assert parse("roll the ball to me") == [("schiessen", {"ziel": "mir"})]
    assert parse("do a roll") == [("skill", {"name": "roulade"})]
