"""Mentor 2 und Ari übt selbst (0.41): Vorgemachtes als Auftrag merken, vom Handy über die sichere Adresse,
Üben im Simulator (nie schlechter als vorher), Eingreifen mit der Hand beim Ausprobieren (HIL)."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

from duckpilot import arm_lernen as L
from duckpilot import arm_ueben as U
from duckpilot import settings as S
from duckpilot import werkbank_auftrag as WA
from duckpilot.mentor_auftrag import Beobachter, beschreiben
from duckpilot.remote import pc_only
from duckpilot.server.oberflaeche import seite


def _sim():
    from duckpilot.backends.so101 import So101Sim

    sim = So101Sim(realtime=False, seed=2)

    async def wach():
        await sim.connect()
        await sim.init()
    asyncio.run(wach())
    for _ in range(60):
        sim.step(0.05)
    return sim


def _laufen(sim, beob, s):
    for _ in range(int(s / 0.05)):
        sim.step(0.05)
        beob.schauen(sim.werkbank)


def test_vorgemachtes_wird_ein_auftrag_den_ari_selbst_ausfuehrt(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "data_dir", lambda: tmp_path)
    sim, beob = _sim(), Beobachter()
    # „Vormachen“: hier führen greifen/ablegen den Arm – der Beobachter sieht nur die Werkbank, wie beim Vormachen
    for ding, ziel in (("roter Würfel", "linke Kiste"), ("gelber Würfel", "blauer Würfel")):
        assert asyncio.run(sim.greifen(ding)).accepted
        _laufen(sim, beob, 6)
        assert asyncio.run(sim.ablegen(ziel)).accepted
        _laufen(sim, beob, 6)
    assert beob.schritte == [{"ding": "roter Würfel", "ziel": "linke Kiste"},
                             {"ding": "gelber Würfel", "ziel": "blauer Würfel"}]
    assert [beschreiben(s) for s in beob.schritte] == ["roter Würfel → linke Kiste", "gelber Würfel → auf blauer Würfel"]
    auftrag = beob.auftrag("  Rot  nach links ")
    k, grund = WA.speichern(auftrag)
    assert k == "rot_nach_links" and not grund
    gemerkt = WA.eigene()[k]
    assert gemerkt["regel"] == "schritte" and gemerkt["titel"] == "Rot nach links"
    # Ari führt ihn selbst aus – vom Ausgangsstand aus, geplant (nicht nachgeahmt)
    sim.werkbank.zuruecksetzen()
    schritte, grund = WA.planen(gemerkt, sim.werkbank)
    assert schritte == [("greifen", "roter Würfel"), ("ablegen", "linke Kiste"),
                        ("greifen", "gelber Würfel"), ("ablegen", "blauer Würfel")], grund
    assert Beobachter().auftrag("x") is None


def test_zoegern_zaehlt_nicht_und_stelle_und_platz():
    class WB:
        def __init__(self):
            self.haelt = None
            self.d = {"name": "roter Würfel", "x": 0.2, "y": 0.0, "z": 0.01, "start": [0.2, 0.0], "in": None, "auf": None}

        def ding(self, n):
            return self.d if n == self.d["name"] else None

    wb, b = WB(), Beobachter()
    wb.haelt = "roter Würfel"
    b.schauen(wb)
    wb.haelt = None                                       # gleich wieder hingelegt
    assert b.schauen(wb) is None and not b.schritte
    wb.haelt = "roter Würfel"
    b.schauen(wb)
    wb.d.update(x=0.24, y=-0.08)
    wb.haelt = None
    assert b.schauen(wb) == {"ding": "roter Würfel", "ziel": "stelle:0.24,-0.08"}
    assert beschreiben(b.schritte[0]) == "roter Würfel → Stelle 24 cm vor, 8 cm rechts"
    assert WA.stelle_aus(b.schritte[0]["ziel"]) == (0.24, -0.08)


def test_vom_handy_nur_lesen_was_die_hand_braucht():
    assert not pc_only("GET", "/api/spiele/hand") and not pc_only("GET", "/api/spiele/hand/dateien/vision_bundle.mjs")
    assert pc_only("POST", "/api/spiele/hand/laden") and pc_only("GET", "/api/spiele") and pc_only("POST", "/api/spiele/start")
    assert pc_only("GET", "/api/spiele/hand/dateien/../settings.json") and pc_only("GET", "/api/ari_lernen")
    assert not pc_only("POST", "/api/mentor/vorgemacht")
    html = seite()
    assert 'class="hud hud-mentor pc-oder-sicher"' in html and 'id="mentor-merken"' in html and 'id="ari-ueben"' in html


def test_ueben_wird_nie_schlechter_und_berichtet():
    a = L.aufgabe("roter Würfel", "linke Kiste")
    X, Y = L.daten(L.lehrer_beispiele(a, n=2, seed=5))
    netz = L.Netz(0)
    netz.lernen(X, Y, epochen=40)                        # absichtlich wenig gelernt
    meldungen = []
    neu, bericht = U.ueben(netz, a, [{"schritte": s["schritte"]} for s in L.lehrer_beispiele(a, n=2, seed=5)],
                           runden=2, je_runde=4, bescheid=meldungen.append)
    assert bericht["nachher"] >= bericht["vorher"] and len(bericht["runden"]) == 2
    assert L.pruefen(neu, a, n=U.PRUEF_N, seed=U.PRUEF_SEED) == bericht["nachher"]
    assert meldungen and meldungen[0].startswith("Runde 1 von 2")
    _, abgebrochen = U.ueben(netz, a, [], runden=3, weiter=lambda: False)
    assert abgebrochen["runden"] == [] and abgebrochen["nachher"] == abgebrochen["vorher"]


class _Motorik:
    def __init__(self):
        self.estop_at, self.stopped_at = -1e9, 0.0

    def kontakt(self, _warum):
        pass


def test_eingreifen_beim_ausprobieren_wird_ein_beispiel(tmp_path, monkeypatch):
    from duckpilot import arm_schule
    from duckpilot.arm_schule import ArmSchule

    monkeypatch.setattr(S, "data_dir", lambda: tmp_path)
    sim = _sim()
    rt = SimpleNamespace(backend=sim, engine=_Motorik(), alltag=None)
    schule = ArmSchule(rt)
    a = schule.aufgabe
    schule._netz, schule._meta = L.Netz(0), {"aufgabe": a["name"], "geschafft": 0, "versuche": 10}   # kann noch nichts

    async def probieren():
        assert schule.ausprobieren()["ok"]
        lehrer = L.Lehrer()
        for _ in range(200):                               # deine Hand (hier: der Lehrer) greift ein
            obs = L.beobachtung(sim.gelenke, sim.werkbank, a)
            rt._mentor_ziel = (time.monotonic(), lehrer(obs))
            for _ in range(3):
                sim.step(L.SCHRITT_S / 3)
            await asyncio.sleep(L.SCHRITT_S)
            if schule.taetigkeit is None:
                break
    asyncio.run(probieren())
    assert schule.meldung.startswith("Geschafft") and "Korrektur" in schule.meldung, schule.meldung
    zeilen = [json.loads(z) for z in (tmp_path / "ari_lernen" / "beispiele.jsonl").read_text(encoding="utf-8").splitlines()]
    assert zeilen[-1]["von"] == "eingriff" and len(zeilen[-1]["schritte"]) >= arm_schule.MIN_TAKTE
    assert schule.status()["beispiele"] == 1
    assert not ArmSchule(SimpleNamespace(backend=sim, engine=_Motorik(), alltag=None)).ueben()["ok"]   # erst lernen
