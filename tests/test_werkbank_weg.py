"""Freier Weg an Aris Werkbank (seit 0.38.55, Fund des Maintainers: „der Greifer ragt in den Turm“).

Der Planer tastet jeden Weg mit Fühlpunkten auf Greifer und Backe ab (`duckpilot/arm_huelle.py`, aus dem Modell) und
fährt nicht durch Würfel, Kistenwände oder die Werkbank – lieber gedreht, weniger weit offen oder mit ehrlichem Nein."""

import asyncio
import importlib.util
from pathlib import Path

from duckpilot.arm import POSEN
from duckpilot.backends import werkbank_weg as W
from duckpilot.backends.so101 import So101Sim
from duckpilot.backends.werkbank import PARKEN, WUERFEL, Werkbank

ROOT = Path(__file__).resolve().parents[1]


def _laufen(sim, sekunden, wache=None):
    for _ in range(int(sekunden / 0.05)):
        sim.step(0.05)
        if wache:
            wache(sim)


def test_huelle_passt_zum_modell():
    spec = importlib.util.spec_from_file_location("arm_huelle_erzeugen", ROOT / "tools" / "arm_huelle_erzeugen.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (ROOT / "duckpilot" / "arm_huelle.py").read_text(encoding="utf-8") == mod.text(), \
        "arm_huelle.py neu erzeugen: python tools/arm_huelle_erzeugen.py"


def test_bereit_ist_frei_und_der_turm_bleibt_unberuehrt():
    """Der Turm steht auf dem blauen Würfel; danach greift Ari daneben – kein Fühlpunkt darf je im Turm stecken."""
    wb = Werkbank()
    hin = W.hindernisse(wb.dinge, wb.kisten, WUERFEL, set())
    assert W.beruehrt(POSEN["bereit"], hin, False, WUERFEL) is None       # Ruhehaltung: nichts im Greifer

    async def go():
        sim = So101Sim(realtime=False)
        await sim.init()
        _laufen(sim, 1.5)
        for ding, ziel in (("roter Würfel", "auf blauer Würfel"), ("gelber Würfel", "auf roter Würfel")):
            assert (await sim.greifen(ding)).accepted
            _laufen(sim, 4.0)
            assert (await sim.ablegen(ziel)).accepted
            _laufen(sim, 5.0)
        turm = [d for d in sim.werkbank.dinge if d["name"] in ("blauer Würfel", "roter Würfel", "gelber Würfel")]
        assert sorted(round(d["z"], 3) for d in turm) == [0.015, 0.045, 0.075]
        turm_hin = W.hindernisse(turm, [], WUERFEL, set())
        treffer = []

        def wache(s):
            if (hit := W.beruehrt(s.gelenke, turm_hin, s.werkbank.haelt is not None, WUERFEL)) is not None:
                treffer.append(hit)

        for ding, ziel in (("oranger Würfel", "linke Kiste"), ("grüner Würfel", "rechte Kiste")):
            assert (await sim.greifen(ding)).accepted
            _laufen(sim, 4.0, wache)
            assert (await sim.ablegen(ziel)).accepted
            _laufen(sim, 5.0, wache)
            assert sim.werkbank.ding(ding)["in"] == ziel
        assert treffer == []
    asyncio.run(go())


def test_steht_unter_bereit_etwas_parkt_er_darueber():
    wb = Werkbank()
    rot, blau, gelb = wb.ding("rot"), wb.ding("blau"), wb.ding("gelb")
    for i, d in enumerate((blau, rot)):                  # Turm genau unter der Ruhehaltung
        d["x"], d["y"], d["z"] = 0.21, 0.0, WUERFEL / 2 + i * WUERFEL
    rot["auf"] = blau["name"]
    plan, _ = wb.greifen_plan(gelb["name"], PARKEN[1])                # kommt von oben
    assert plan is not None
    wb.haelt = gelb["name"]
    plan, grund = wb.ablegen_plan("linke Kiste", plan[-1][0])
    assert plan is not None, grund
    assert plan[-1][0] == PARKEN[1]


def test_eng_umstellt_sagt_er_nein_statt_hindurch():
    wb = Werkbank()
    rot = wb.ding("rot")
    for d, (dx, dy) in zip(wb.dinge[1:], ((0.032, 0), (-0.032, 0), (0, 0.032), (0, -0.032))):
        d["x"], d["y"] = rot["x"] + dx, rot["y"] + dy
    plan, grund = wb.greifen_plan("rot")
    assert plan is None and "stoßen" in grund and "Platz" in grund
