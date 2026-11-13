"""Freies Ablegen und eigene Tricks für Ari (seit 0.38.55, Fragen des Maintainers: „wieso kann ich einen Würfel nicht
einfach ablegen im Radius des Arms?“ und „wieso hat Ari noch fremde Tricks?“)."""

import asyncio
import math
from pathlib import Path
from types import SimpleNamespace

from duckpilot import arm as A
from duckpilot.backends.so101 import So101Sim
from duckpilot.backends.werkbank import RADIUS, Werkbank
from duckpilot.brain import handeln as H
from duckpilot.brain.fallback import werkbank_befehl
from duckpilot.werkbank_auftrag import planen, stelle_aus

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def _laufen(sim, sekunden):
    for _ in range(int(sekunden / 0.05)):
        sim.step(0.05)


def test_stellen_aus_worten():
    assert stelle_aus("vorne links") == (0.27, -0.12)          # aus deiner Sicht: vorn bei dir, links deine linke Seite
    assert stelle_aus("in der Mitte") == (0.22, 0.0)
    assert stelle_aus("hinten") == (0.17, 0.0)
    assert stelle_aus("front right") == (0.27, 0.12)
    assert stelle_aus("stelle:0.2,0.1") == (0.2, 0.1)
    assert stelle_aus("linke Kiste") is None and stelle_aus("roter Würfel") is None and stelle_aus("stelle:x") is None


def test_ablegen_an_freier_stelle():
    async def go():
        sim = So101Sim(realtime=False)
        await sim.init()
        _laufen(sim, 1.5)
        wb = sim.werkbank
        for ding, ziel in (("roter Würfel", "vorne links"), ("gelber Würfel", "vorne links")):   # 2. Mal: daneben
            assert (await sim.greifen(ding)).accepted
            _laufen(sim, 4.0)
            r = await sim.ablegen(ziel)
            assert r.accepted, r.reason
            _laufen(sim, 5.0)
        rot, gelb = wb.ding("rot"), wb.ding("gelb")
        assert math.hypot(rot["x"] - 0.27, rot["y"] + 0.12) < 0.015 and not rot["in"] and rot["z"] == 0.015
        assert math.hypot(rot["x"] - gelb["x"], rot["y"] - gelb["y"]) >= 0.04       # nicht aufeinander, nicht ineinander
        assert (await sim.greifen("grüner Würfel")).accepted
        _laufen(sim, 4.0)
        weit = await sim.ablegen("stelle:0.45,0.0")
        assert not weit.accepted and "zu weit" in weit.reason
    asyncio.run(go())


def test_chat_ohne_sprachmodell():
    wb = Werkbank()
    assert werkbank_befehl("leg den roten vorne links ab", wb) == {"schritte": [{"ding": "roter Würfel", "ziel": "vorne links"}]}
    assert werkbank_befehl("leg den roten in die linke Kiste", wb) == {"schritte": [{"ding": "roter Würfel", "ziel": "linke Kiste"}]}
    assert werkbank_befehl("leg ihn hinten ab", wb) is None                   # hält nichts: „ihn“ ist niemand
    wb.haelt = "roter Würfel"
    befehl = werkbank_befehl("leg ihn hinten rechts ab", wb)
    assert befehl == {"schritte": [{"ding": "roter Würfel", "ziel": "hinten rechts"}]}
    schritte, _ = planen({"titel": "x", "regel": "schritte", **befehl}, wb)
    assert schritte == [("ablegen", "hinten rechts")]                          # hält ihn schon: nicht erst zurücklegen


def test_klick_auf_die_werkbank():
    wb = Werkbank()
    be = SimpleNamespace(werkbank=wb, x=-1.82, y=0.25, yaw=0.0)
    d = H.werkbank_stelle(be, -1.57, 0.17)                                       # Welt → Sockelrahmen
    assert (d["x"], d["y"], d["art"], d["frei"]) == (0.25, -0.08, "stelle", True)
    assert H.werkbank_aktionen(d, be) == []                                      # hält nichts
    wb.haelt = "roter Würfel"
    aktion = H.werkbank_aktionen(d, be)[0]["id"]
    assert aktion == "stelle:0.250,-0.080"
    assert H.werkbank_werkzeug(d, aktion) == ("ablegen", {"ziel": aktion})
    weit = H.werkbank_stelle(be, -1.2, 0.25)
    assert not weit["frei"] and "zu weit" in weit["hinweis"] and H.werkbank_aktionen(weit, be) == []
    gedreht = H.werkbank_stelle(SimpleNamespace(werkbank=wb, x=0.0, y=0.0, yaw=math.pi / 2), 0.0, 0.2)
    assert abs(gedreht["x"] - 0.2) < 1e-6 and abs(gedreht["y"]) < 1e-6


def test_freie_stelle_meidet_kisten_und_wuerfel():
    wb = Werkbank()
    for x in (0.17, 0.22, 0.27):                                                 # jede benannte Stelle ist erreichbar
        for y in (-0.12, 0.0, 0.12):
            assert RADIUS[0] <= math.hypot(x, y) <= RADIUS[1]
    for d in wb.dinge:
        assert not wb.stelle_frei(d["x"], d["y"])
    for k in wb.kisten:
        assert not wb.stelle_frei(k["x"], k["y"])
    x, y = wb.freie_stelle(0.28, 0.0)                                            # dort liegt der blaue Würfel
    assert wb.stelle_frei(x, y) and RADIUS[0] <= math.hypot(x, y) <= RADIUS[1]


def test_tricks_seite_des_arms():
    assert set(A.TITEL) <= set(A.GESTEN)
    html = (STATIC / "teile" / "tricks.html").read_text(encoding="utf-8")
    assert 'class="braucht-arm"' in html and 'id="arm-gesten"' in html and 'id="arm-auftraege"' in html
    assert 'emo-own braucht-kopf" id="emo-own"' in html                         # Gefühle mit Kopf nicht beim Arm
    assert "'arm']" in (STATIC / "modul.js").read_text(encoding="utf-8")
    assert ".ohne-arm .braucht-arm" in (STATIC / "style.css").read_text(encoding="utf-8")


def test_knowlin_spricht_fuer_koerper_ohne_stimme():
    """Entscheidung des Maintainers (13.11.): „Knowlin kann für ihn sprechen“ – Ari hat keine Stimme, Knowlin leiht ihm seine."""
    from duckpilot.backends.reachy import ReachyMiniSim
    from duckpilot.backends.sim import SimBackend
    from duckpilot.koerper import eigene_stimme

    assert not eigene_stimme(So101Sim(realtime=False).eigenschaften())
    assert eigene_stimme(SimBackend(realtime=False).eigenschaften())             # Microduck: Stimmbank
    assert eigene_stimme(ReachyMiniSim(realtime=False).eigenschaften())              # Reachy: Lautsprecher
    gespraech = (STATIC.parent / "runtime_gespraech.py").read_text(encoding="utf-8")
    assert "kopf = kopf or not self._koerper_hat_stimme()" in gespraech
    assert "Knowlin spricht" in (STATIC / "app.js").read_text(encoding="utf-8")
    assert "const kopf = () => !!(h.imKopf && h.imKopf()) || stumm();" in (STATIC / "stimme.js").read_text(encoding="utf-8")
