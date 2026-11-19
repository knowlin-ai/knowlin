"""Bello lernt laufen (seit 0.43): MuJoCo-Modell, Evolutionsstrategie, nie schlechter, Gangart „Gelernt“."""

import asyncio
import json
import time

import pytest

from duckpilot import bello_schule as BS
from duckpilot.backends.bittle import GELERNT, BittleSim
from duckpilot.remote import pc_only

mujoco = pytest.importorskip("mujoco")
from duckpilot.physics import bello as B  # noqa: E402


def test_modell_steht_und_trabt_vorwaerts():
    welt = B.Welt()
    stand = welt.lauf({**B.HAND, "schritt": 0.0, "hub": 0.0}, 1, sekunden=2.0)
    assert not stand.gestuerzt and abs(stand.tempo) < 0.01             # steht still, kippt nicht
    lauf = welt.lauf(B.HAND, 1, sekunden=3.0)
    assert not lauf.gestuerzt and lauf.tempo > 0.05 and lauf.neigung < 0.3


def test_kinematik_trifft_den_fusspunkt():
    for vorn in (True, False):
        s, k = B.bein(0.01, -0.09, vorn)
        x, z = B.fuss(s, k)
        assert abs(x - 0.01) < 1e-6 and abs(z + 0.09) < 1e-6
    ziele = B.gelenke(B.HAND, 0.0)
    assert ziele.shape == (8,) and all(abs(v) < 2.4 for v in ziele)


def test_tempo_zaehlt_nur_bis_petois_trab():
    schnell = B.Lauf(1.0, 0.0, 0.0, False)
    assert schnell.punkte() == pytest.approx(B.TEMPO_GRENZE)
    assert B.Lauf(0.2, 0.0, 0.0, True).punkte() < B.Lauf(0.2, 0.0, 0.0, False).punkte()


def test_ohne_verbesserung_bleibt_alles_wie_es_war():
    r = B.lernen(runden=0, pruef_laeufe=2)
    assert not r["gelernt"] and r["parameter"] == {k: round(v, 4) for k, v in B.HAND.items()}
    assert r["vorher"] == r["nachher"]


def test_kurzer_lernlauf_meldet_und_haelt_die_grenzen_ein():
    gemeldet = []
    r = B.lernen(runden=3, richtungen=2, beste=1, seeds_je_probe=1, pruef_laeufe=2, melden=gemeldet.append)
    assert [m["runde"] for m in gemeldet] == [1, 2, 3] and r["runden"] == 3
    for k, (_, lo, hi) in B.PARAMETER.items():
        assert lo - 1e-9 <= r["parameter"][k] <= hi + 1e-9, k
    if r["gelernt"]:
        assert r["nachher"]["punkte"] > r["vorher"]["punkte"] and r["nachher"]["stuerze"] <= r["vorher"]["stuerze"]
    assert B.lernen(runden=50, abbrechen=lambda: True, pruef_laeufe=1)["runden"] == 0


def test_schule_speichert_nur_besseres_und_vergisst(tmp_path, monkeypatch):
    besser = {"gelernt": True, "parameter": {**B.HAND, "takt_hz": 3.5}, "vorher": {"tempo": 0.12}, "nachher":
              {"tempo": 0.5, "stuerze": 0, "neigung": 0.02, "laeufe": 8, "punkte": 0.34}, "runden": 3, "dauer_s": 1.0}
    monkeypatch.setattr(B, "lernen", lambda **kw: dict(besser))
    schule = BS.BelloSchule(tmp_path)
    angewandt = []
    assert schule.starten(3, bei_fertig=angewandt.append)["ok"]
    for _ in range(100):
        if not schule.stand()["laeuft"]:
            break
        time.sleep(0.02)
    stand = schule.stand()
    assert stand["gelernt"] and stand["tempo"] == B.TEMPO_GRENZE          # im Körper nie schneller als Petois Trab
    gespeichert = json.loads((tmp_path / BS.DATEI).read_text(encoding="utf-8"))
    assert set(gespeichert) == {"parameter", "tempo", "bericht", "wann"} and angewandt[0]["tempo"] == B.TEMPO_GRENZE
    monkeypatch.setattr(B, "lernen", lambda **kw: {**besser, "gelernt": False})
    schule.starten(3)
    schule._faden.join(5)
    assert schule.stand()["bericht"]["gelernt"] is False and BS.laden(tmp_path)["parameter"]["takt_hz"] == 3.5
    assert schule.vergessen() and BS.laden(tmp_path) is None
    (tmp_path / BS.DATEI).write_text("kaputt", encoding="utf-8")
    assert BS.laden(tmp_path) is None


def test_bello_laeuft_die_gelernte_gangart():
    async def go():
        sim = BittleSim(realtime=False, seed=1)
        assert GELERNT not in sim.skills() and not (await sim.do(GELERNT)).accepted
        sim.gelernt_setzen({"parameter": {**B.HAND, "takt_hz": 3.0, "schritt": 0.03}, "tempo": 9.0})
        assert GELERNT in sim.skills() and sim.gelernt["tempo"] == 0.36         # gedeckelt
        assert (await sim.do(GELERNT)).accepted and sim.gangart == GELERNT
        assert sim._schritt_takt() == pytest.approx(1.5)
        st = sim.state()
        assert st.gangart == GELERNT and st.to_dict()["gang_form"]["schritt"] == 0.03    # kommt in der Oberfläche an
        sim.gelernt_setzen(None)
        assert sim.gangart == "traben" and GELERNT not in sim.skills()
    asyncio.run(go())


def test_lernen_nur_am_pc():
    assert pc_only("POST", "/api/bello/lernen") and not pc_only("GET", "/api/bello")
