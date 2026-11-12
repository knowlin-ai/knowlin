"""Antrieb und Gedankenspur (seit 0.38.44, Etappe G3): vier Bedürfnisse entscheiden mit, *was* Knowlin von sich aus tut –
nie, *wie oft*; jede eigene Handlung bekommt eine lesbare Zeile. Wünsche des Maintainers: Bedürfnisse „nahezu
unsichtbar oder sehr dezent“, Eigeninitiative als „feinerer Regler“."""

import asyncio
import inspect

from helpers import make

from duckpilot import remote as R
from duckpilot.antrieb import BEDUERFNISSE, STILLT, Antrieb
from duckpilot.brain.tools import ToolRunner
from duckpilot.gedankenspur import GROESSE, Gedankenspur
from duckpilot.motion import eigenstaendig as E


def test_beduerfnisse_wachsen_und_werden_gestillt():
    a = Antrieb()
    a.takt(0, aktiv=False, kontakt=False)
    vorher = dict(a.werte)
    a.takt(30 * 60, aktiv=False, kontakt=False, energie=1.0)                # eine halbe Stunde Ruhe
    assert a.werte["neugier"] > vorher["neugier"] and a.werte["naehe"] > vorher["naehe"]
    assert a.werte["koennen"] > vorher["koennen"] and a.werte["ruhe"] <= vorher["ruhe"]
    a.takt(30 * 60 + 1, aktiv=False, kontakt=True)                          # der Mensch meldet sich: Nähe gestillt
    assert a.werte["naehe"] == 0.1
    n = a.werte["neugier"]
    a.gestillt("erkunden")
    assert a.werte["neugier"] < n / 2


def test_ruhe_waechst_mit_tun_und_bei_knappem_akku():
    a = Antrieb()
    a.takt(0, aktiv=True, kontakt=False)
    a.takt(10 * 60, aktiv=True, kontakt=False)
    assert a.werte["ruhe"] > 0.4
    b = Antrieb()
    b.takt(0, aktiv=False, kontakt=False, akku=0.1)
    assert b.werte["ruhe"] >= 0.8
    assert b.faktor("erkunden", ort=True) < b.faktor("umschauen") < b.faktor("sitzen", ort=True) + 1


def test_antrieb_aendert_was_nicht_wie_oft():
    # Die Wartezeit hängt nur am Regler und am Charakter – nie am Antrieb
    assert "antrieb" not in inspect.signature(E.wartezeit).parameters
    assert "antrieb" not in inspect.signature(E.Eigenstaendig.takt).parameters
    a = Antrieb()
    assert all(0.05 <= a.faktor(art) <= 2.0 for art in STILLT)


def test_bedarf_bleibt_dezent():
    a = Antrieb()
    assert a.hinweis() is None                                             # normal: nichts zu sehen
    a.werte["neugier"] = 0.9
    assert a.hinweis() == "gerade eher neugierig"
    assert set(a.als_dict()["werte"]) == set(BEDUERFNISSE)


def test_gedankenspur_personen_nur_am_pc_und_begrenzt():
    g = Gedankenspur()
    g.merken("schaut sich um", "Neugier (stark)", wie="look_around", zeit=1)
    g.merken("dreht sich zu dir", "Nähe (etwas)", wie="turn", person=True, zeit=2)
    assert [z["was"] for z in g.liste()] == ["dreht sich zu dir", "schaut sich um"]        # neueste zuerst
    assert [z["was"] for z in g.liste(ohne_personen=True)] == ["schaut sich um"]
    for i in range(GROESSE + 5):
        g.merken(f"x{i}", "y")
    assert len(g.liste()) == GROESSE
    g.leeren()
    assert g.liste() == []
    assert any(m == "DELETE" and p.match("/api/gedankenspur") for m, p in R.PC_ONLY)       # leeren nur am PC


def test_absicht_mit_ersatz_oder_nein_steht_in_der_spur():
    async def go():
        sim, eng = await make()
        runner = ToolRunner(eng)
        runner.gedanken = Gedankenspur()
        await runner.run("absicht", {"aktion": "zustimmen"})                    # wie gemeint: keine Zeile
        assert runner.gedanken.liste() == []
        eng.notaus()
        await runner.run("absicht", {"aktion": "gruessen"})
        z = runner.gedanken.liste()[0]
        assert z["quelle"] == "gespraech" and "Not-Aus" in z["ergebnis"] and z["was"].startswith("wollte ")
    asyncio.run(go())
