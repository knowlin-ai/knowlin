"""Ari lernt durch Vormachen (seit 0.38.64, Stufe A; Maintainer: „Ari zuerst“, „A, dann B“): Lehrer, Netz, Aufnahme
aus der Laufzeit, Ausprobieren mit Not-Aus, Export für LeRobot."""

import asyncio
import io
import json
import time
import zipfile
from types import SimpleNamespace

import numpy as np

from duckpilot import arm_lernen as L
from duckpilot import settings as S


def test_lehrer_schafft_es_bei_zufaelliger_lage():
    a = L.aufgabe("roter Würfel", "linke Kiste")
    beispiele = L.lehrer_beispiele(a, n=8, seed=3)
    assert len(beispiele) == 8
    takt = beispiele[0]["schritte"][0]
    assert len(takt[0]) == L.EIN and len(takt[1]) == L.AUS and len(takt[2]) == len(takt[3]) == 6


def test_netz_lernt_aus_beispielen_und_schafft_es_selbst(tmp_path):
    a = L.aufgabe("blauer Würfel", "rechte Kiste")
    X, Y = L.daten(L.lehrer_beispiele(a, n=20, seed=1))
    netz = L.Netz(0)
    assert netz.lernen(X, Y, epochen=300) < 0.02
    assert L.pruefen(netz, a, n=5, seed=77) >= 4                      # andere Lagen als beim Lernen
    netz.speichern(tmp_path / "netz.npz", {"aufgabe": a["name"]})
    wieder, meta = L.Netz.laden(tmp_path / "netz.npz")
    obs = X[0]
    assert meta["aufgabe"] == a["name"] and np.allclose(wieder(obs), netz(obs))


class _Motorik:
    def __init__(self):
        self.estop_at, self.stopped_at = -1e9, 0.0

    def kontakt(self, _warum):
        pass


def _laufzeit(tmp_path, monkeypatch):
    from duckpilot.backends.so101 import So101Sim

    monkeypatch.setattr(S, "data_dir", lambda: tmp_path)
    sim = So101Sim(realtime=False, seed=2)

    async def wach():
        await sim.connect()
        await sim.init()
    asyncio.run(wach())
    for _ in range(60):
        sim.step(0.05)
    return SimpleNamespace(backend=sim, engine=_Motorik(), alltag=None)


def test_aufnahme_aus_dem_vormachen_lernen_ausprobieren_export(tmp_path, monkeypatch):
    from duckpilot import arm_schule
    from duckpilot.arm_schule import ArmSchule

    rt = _laufzeit(tmp_path, monkeypatch)
    schule = ArmSchule(rt)
    assert schule.grund() is None and "linke Kiste" in schule.status()["wahl"]["kisten"]
    assert schule.aufgabe_setzen("roter Würfel", "linke Kiste")["ok"]
    assert not schule.aufgabe_setzen("lila Würfel", "linke Kiste")["ok"]

    async def vormachen():
        """Ein Mensch macht vor – hier spielt der Lehrer die Hand, wie `Runtime._mentor_hand` es täte."""
        assert schule.aufnehmen()["ok"]
        lehrer = L.Lehrer()
        for _ in range(80):
            obs = L.beobachtung(rt.backend.gelenke, rt.backend.werkbank, schule.aufgabe)
            ziel = lehrer(obs)
            if (await rt.backend.nachmachen(ziel)).accepted:
                rt._mentor_ziel = (time.monotonic(), ziel)
            for _ in range(3):
                rt.backend.step(L.SCHRITT_S / 3)
            await asyncio.sleep(L.SCHRITT_S)
            if schule.taetigkeit is None:
                break
    asyncio.run(vormachen())
    assert schule.status()["beispiele"] == 1, schule.meldung
    gespeichert = json.loads((tmp_path / "ari_lernen" / "beispiele.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert gespeichert["von"] == "mensch" and len(gespeichert["schritte"]) >= arm_schule.MIN_TAKTE

    # Lernen (klein, damit der Test schnell bleibt)
    monkeypatch.setattr(arm_schule, "LEHRER_N", 12)
    monkeypatch.setattr(arm_schule, "VERSUCHE", 3)

    async def lernen():
        assert schule.lernen(True)["ok"]
        assert not schule.ausprobieren()["ok"]                          # beschäftigt
        while schule.taetigkeit == "lernen":
            await asyncio.sleep(0.2)
    asyncio.run(lernen())
    g = schule.status()["gelernt"]
    assert g and g["mensch"] == 1 and g["lehrer"] == 12 and g["geschafft"] >= 2, schule.meldung
    assert ArmSchule(rt).status()["gelernt"]["takte"] == g["takte"]      # liegt auf der Platte

    # Ausprobieren in der laufenden App – der Not-Aus beendet es sofort
    async def probieren():
        schule.neu_legen()
        assert schule.ausprobieren()["ok"]
        await asyncio.sleep(0.4)
        rt.engine.estop_at = time.monotonic()
        await asyncio.sleep(0.4)
    asyncio.run(probieren())
    assert schule.taetigkeit is None and schule.meldung == "Angehalten."

    # Export für LeRobot
    daten, name = schule.export()
    assert name == "ari-roter-linke-lerobot.zip"
    z = zipfile.ZipFile(io.BytesIO(daten))
    assert {"episoden.jsonl", "meta/info.json", "meta/tasks.jsonl", "nach_lerobot.py", "LIESMICH.md"} <= set(z.namelist())
    info = json.loads(z.read("meta/info.json"))
    assert info["robot_type"] == "so101_follower" and info["features"]["action"]["names"][0] == "shoulder_pan.pos"
    assert info["total_episodes"] == 13
    ep = json.loads(z.read("episoden.jsonl").decode().splitlines()[0])
    assert len(ep["takte"][0]["state"]) == 6 and len(ep["takte"][0]["env"]) == L.EIN
    compile(z.read("nach_lerobot.py").decode(), "nach_lerobot.py", "exec")


def test_nur_im_simulator_und_nur_am_pc(tmp_path, monkeypatch):
    """Am echten Arm kennt Knowlin die Lage der Würfel nicht; vom Handy aus gibt es das Lernen nicht."""
    from duckpilot import remote
    from duckpilot.arm_schule import NUR_SIM, ArmSchule

    monkeypatch.setattr(S, "data_dir", lambda: tmp_path)
    schule = ArmSchule(SimpleNamespace(backend=object(), engine=_Motorik()))
    assert schule.grund() == NUR_SIM and schule.status()["grund"] == NUR_SIM
    for tun in (schule.aufnehmen, schule.lernen, schule.ausprobieren, schule.neu_legen):
        assert not tun()["ok"]
    assert schule.export() is None
    assert any(p.search("/api/ari_lernen") for _, p in remote.PC_ONLY)
    assert any(p.search("/api/ari_lernen/export") for _, p in remote.PC_ONLY)
