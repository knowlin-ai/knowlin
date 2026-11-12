"""Aufträge an Aris Werkbank (seit 0.38.54, Wunsch des Maintainers nach Anwendungen wie in der SO-101-Gemeinde):
Sortieren nach Farben, Turm bauen, Aufräumen – als Daten, Schritt für Schritt geprüft, der Not-Aus beendet sie."""

import asyncio

from duckpilot.backends.so101 import So101Sim
from duckpilot.backends.werkbank import Werkbank
from duckpilot.brain.fallback import werkbank_befehl
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion.eigenstaendig import sperre
from duckpilot.motion.engine import MotionEngine
from duckpilot.werkbank_auftrag import AUFTRAEGE, planen, pruefen


def _laufen(sim, sekunden):
    for _ in range(int(sekunden / 0.05)):
        sim.step(0.05)


def _bis_fertig(sim, hoechstens=200):
    for _ in range(hoechstens):
        if sim.auftrag is None:
            return
        _laufen(sim, 1.0)
    raise AssertionError("Auftrag wurde nicht fertig")


def _lage(sim):
    return {d["name"].split()[0]: (d["in"], d["auf"]) for d in sim.werkbank.dinge}


async def _wach():
    sim = So101Sim(realtime=False)
    await sim.init()
    _laufen(sim, 1.5)
    return sim


def test_sortieren_turm_aufraeumen():
    async def go():
        sim = await _wach()
        r = await sim.auftrag_starten(AUFTRAEGE["sortieren"])
        assert r.accepted and r.reason == "Nach Farben sortieren: 5 Griffe"
        _bis_fertig(sim)
        assert sim.auftrag_ende == "Nach Farben sortieren – fertig"
        assert _lage(sim) == {"roter": ("linke Kiste", None), "oranger": ("linke Kiste", None),
                              "gelber": ("linke Kiste", None), "blauer": ("rechte Kiste", None),
                              "grüner": ("rechte Kiste", None)}
        assert not (await sim.auftrag_starten(AUFTRAEGE["sortieren"])).accepted   # „Ist schon sortiert.“
        assert (await sim.auftrag_starten(AUFTRAEGE["turm"])).accepted              # Basis erst aus der Kiste holen
        _bis_fertig(sim)
        turm = sorted((d for d in sim.werkbank.dinge if not d["in"] and d["z"] > 0.03), key=lambda d: d["z"])
        assert len(turm) == 2 and turm[0]["auf"] == "blauer Würfel" and turm[1]["auf"] == turm[0]["name"]
        assert abs(turm[1]["z"] - 0.075) < 1e-6
        assert (await sim.auftrag_starten(AUFTRAEGE["aufraeumen"])).accepted
        _bis_fertig(sim)
        assert all(not d["in"] and not d["auf"] and [d["x"], d["y"]] == d["start"] for d in sim.werkbank.dinge)
        assert not (await sim.auftrag_starten(AUFTRAEGE["aufraeumen"])).accepted
    asyncio.run(go())


def test_not_aus_beendet_den_auftrag():
    async def go():
        sim = await _wach()
        assert (await sim.auftrag_starten(AUFTRAEGE["sortieren"])).accepted
        _laufen(sim, 5.0)
        assert sim.beschaeftigt()
        await sim.relax()
        assert sim.auftrag is None and sim.auftrag_ende == "Nach Farben sortieren abgebrochen (Not-Aus)"
        assert sim.werkbank.haelt is None                                         # ohne Kraft fällt der Würfel
        _laufen(sim, 2.0)
        assert not sim.beschaeftigt()
        assert not (await sim.auftrag_starten(AUFTRAEGE["turm"])).accepted          # Motoren aus
    asyncio.run(go())


def test_stapeln_hat_grenzen():
    async def go():
        sim = await _wach()
        wb = sim.werkbank
        for ding, ziel in (("roter Würfel", "auf blauer Würfel"), ("gelber Würfel", "auf roter Würfel")):
            assert (await sim.greifen(ding)).accepted
            _laufen(sim, 4.0)
            assert (await sim.ablegen(ziel)).accepted
            _laufen(sim, 5.0)
        assert wb.ding("gelber Würfel")["auf"] == "roter Würfel"
        assert not (await sim.greifen("roter Würfel")).accepted                     # darauf liegt der gelbe
        assert (await sim.greifen("grüner Würfel")).accepted
        _laufen(sim, 4.0)
        hoch = await sim.ablegen("auf gelber Würfel")
        assert not hoch.accepted and "drei Würfel" in hoch.reason
        assert not (await sim.ablegen("auf roter Würfel")).accepted                 # schon belegt
    asyncio.run(go())


def test_auftraege_sind_nur_daten():
    assert pruefen({"titel": "x", "regel": "python", "code": "import os"})[0] is None
    assert pruefen("rm -rf")[0] is None
    assert pruefen({"titel": "", "regel": "zurueck"})[0] is None
    zu_viel = {"titel": "x", "regel": "schritte", "schritte": [{"ding": "a", "ziel": "b"}] * 21}
    assert pruefen(zu_viel)[0] is None
    gut, _ = pruefen({"titel": "Rot nach links", "regel": "farbe", "links": ["Rot"], "rechts": [], "extra": 1})
    assert gut == {"titel": "Rot nach links", "beschreibung": "", "regel": "farbe", "links": ["rot"], "rechts": []}
    turm, _ = pruefen({"titel": "Hoch", "regel": "turm", "hoehe": 9})
    assert turm["hoehe"] == 3                                                      # höher reicht der Arm nicht
    schritte, _ = planen(gut, Werkbank())
    assert schritte == [("greifen", "roter Würfel"), ("ablegen", "linke Kiste")]


def test_einfache_befehle_und_werkzeug():
    wb = Werkbank()
    assert werkbank_befehl("sortier die würfel nach farben", wb) == {"auftrag": "sortieren"}
    assert werkbank_befehl("bau einen turm", wb) == {"auftrag": "turm"}
    assert werkbank_befehl("räum bitte auf", wb) == {"auftrag": "aufraeumen"}
    assert werkbank_befehl("leg den grünen auf den blauen", wb) == {
        "schritte": [{"ding": "grüner Würfel", "ziel": "auf blauer Würfel"}]}
    assert werkbank_befehl("put the red cube in the right box", wb) == {
        "schritte": [{"ding": "roter Würfel", "ziel": "rechte Kiste"}]}
    assert werkbank_befehl("wink mal", wb) is None

    async def go():
        sim = So101Sim(realtime=False)
        eng = MotionEngine(sim)
        r = ToolRunner(eng)
        assert "auftrag" in {t["name"] for t in r.tools()}
        await sim.init()
        _laufen(sim, 1.5)
        assert (await r.run("auftrag", {"auftrag": "turm"}))["ok"]
        _laufen(sim, 2.0)
        eng.last_state = sim.state()
        assert sperre(eng, haeufigkeit=0.6) == "beschäftigt"    # keine Eigeninitiative mitten im Auftrag
        eng.notaus()
        assert not (await r.run("auftrag", {"auftrag": "turm"}))["ok"]
    asyncio.run(go())


def test_tic_tac_toe():
    """Nach dem Vorbild „LeX-O“: du setzt per Klick, Ari greift seinen Stein und legt ihn aufs Feld."""
    import random

    from duckpilot.backends.werkbank_spiel import ari_waehlt, gewinner
    from duckpilot.brain import handeln as H
    from duckpilot.brain.fallback import spiel_befehl

    assert ari_waehlt(["ari", "ari", None, "du", "du", None, None, None, None]) == 2      # gewinnen geht vor
    assert ari_waehlt(["du", "du", None, None, "ari", None, None, None, None]) == 2       # sonst verhindern
    assert ari_waehlt([None] * 4 + ["du"] + [None] * 4, random.Random(1)) in (0, 2, 6, 8)
    assert gewinner(["du", "ari", "ari", None, "du", None, None, None, "du"]) == "du"

    async def go():
        sim = await _wach()
        assert not (await sim.spiel_aktion("zug", 5)).accepted                  # erst starten
        assert (await sim.spiel_aktion("start")).accepted
        wb = sim.werkbank
        assert len(wb.felder) == 9 and wb.kisten == [] and len(wb.dinge) == 5
        assert spiel_befehl("feld 5", wb) == {"aktion": "zug", "feld": 5}
        feld = H.ding_finden("Feld 1", sim)
        assert feld["art"] == "feld" and H.werkbank_werkzeug(feld, "setzen") == ("tictactoe", {"aktion": "zug", "feld": 1})
        assert not (await sim.auftrag_starten(AUFTRAEGE["turm"])).accepted       # nicht mitten im Spiel
        for nr in (1, 3, 7, 9, 2, 4, 6, 8, 5):
            sp = wb.spiel
            if sp.dran != "du":
                break
            if sp.brett[nr - 1]:
                continue
            assert (await sim.spiel_aktion("zug", nr)).accepted
            assert not (await sim.spiel_aktion("zug", nr)).accepted              # Ari ist dran bzw. belegt
            _bis_fertig(sim)
        sp = wb.spiel
        assert sp.ergebnis in ("Ari gewinnt diese Runde.", "Unentschieden.", "Du gewinnst – gut gespielt!")
        steine = {d["feld"] for d in wb.dinge if d["name"].startswith("Aris") and d.get("feld")}
        assert steine == {i + 1 for i, f in enumerate(sp.brett) if f == "ari"}   # jeder Stein liegt auf seinem Feld
        assert not (await sim.greifen("dein Stein 1")).accepted                  # deine Steine fasst Ari nicht an
        assert (await sim.spiel_aktion("ende")).accepted
        assert wb.spiel is None and wb.felder == [] and len(wb.dinge) == 5 and len(wb.kisten) == 2
    asyncio.run(go())


def test_not_aus_mitten_im_spielzug():
    async def go():
        sim = await _wach()
        await sim.spiel_aktion("start")
        assert (await sim.spiel_aktion("zug", 1)).accepted
        _laufen(sim, 2.0)
        await sim.relax()
        sp = sim.werkbank.spiel
        assert sp.dran is None and "abgebrochen" in sp.ergebnis
        assert not (await sim.spiel_aktion("zug", 2)).accepted
    asyncio.run(go())


def test_auftraege_merken_und_als_knowlet_teilen(tmp_path, monkeypatch):
    """„Vielleicht kannst du manches einbetten zum Nachladen?“ – eigene Aufträge lassen sich merken, als Knowlet packen
    und woanders übernehmen. Im Paket stehen nur Daten; was keine bekannte Regel ist, wird abgelehnt."""
    import io
    import json
    import sys
    import zipfile

    import pytest

    from duckpilot import knowlets as K
    from duckpilot import werkbank_auftrag as W

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")

    async def go():
        sim = await _wach()
        r = ToolRunner(MotionEngine(sim))
        out = await r.run("auftrag", {"links": ["rot"], "rechts": ["blau"], "merken_als": "Rot links!"})
        assert out["ok"] and "Gemerkt als „rot_links“" in out["info"]
    asyncio.run(go())
    assert W.eigene()["rot_links"]["links"] == ["rot"] and "rot_links" in W.alle()
    assert W.speichern({"titel": "Turm", "regel": "turm"})[0] == "turm_eigen"            # eingebaute bleiben eingebaut

    paket = K.packe(titel="Ordnung", modul="so101", auftraege=W.eigene(), lizenz="CC0-1.0")
    geprueft = K.pruefe(paket)
    assert set(geprueft["auftraege"]) == {"Rot links!", "Turm"}
    assert [a["name"] for a in K.vorschau(geprueft, set(), set())["auftraege"]] == ["Rot links!", "Turm"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("knowlet.json", json.dumps({"format": K.FORMAT, "name": "Böse", "fuer": "so101"}))
        z.writestr("auftraege/boese.json", json.dumps({"titel": "x", "regel": "python", "code": "import os"}))
    with pytest.raises(K.KnowletFehler, match="Auftrag ungültig"):
        K.pruefe(buf.getvalue())
