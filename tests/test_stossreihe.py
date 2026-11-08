"""Stoßreihe: Raster, Klassifikation, Profil, Episoden mit quelle „reihe“, Abbruch, Fehler ohne Physik, nur am PC.

Gerechnet wird mit Test-Policies (tests/onnx_fixtures.py), nie mit Pollens Netzen."""

import asyncio
import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duckpilot import remote as Rm
from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.physics import stossreihe as R
from duckpilot.server.app import Runtime, create_app

PC = {"Origin": "http://127.0.0.1:8765"}
PHONE_BASE = "http://192.168.1.10:8766"


def _physik_da() -> bool:
    try:
        import mujoco  # noqa: F401
        import onnx  # noqa: F401
        import onnxruntime  # noqa: F401

        from duckpilot.modell import ModellStore
    except ImportError:
        return False
    return ModellStore(Path(os.environ["DUCKPILOT_SETTINGS"]).parent).physics_path() is not None


braucht_physik = pytest.mark.skipif(not _physik_da(), reason="Pollens Robotermodell fehlt – einmal "
                                    "`python -m duckpilot.modell` ausführen")


class FakeRt:
    def __init__(self):
        self.nachrichten = []

    async def broadcast_local(self, msg):
        self.nachrichten.append(json.loads(json.dumps(msg)))


@pytest.fixture()
def daten(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    return tmp_path


# ── Raster und Klassifikation (ohne Physik) ──────────────────────────────
def test_grid_is_8_directions_3_strengths_2_heights_and_can_be_narrowed():
    alle = R.raster()
    assert len(alle) == 48 and len({(v["richtung"], v["stufe"], v["hoehe"]) for v in alle}) == 48
    assert alle[0] == {"richtung": "vorn", "stufe": "leicht", "hoehe": "rumpf", "wdh": 0}   # Höhe, Stärke, Richtung
    assert {v["hoehe"] for v in alle[:24]} == {"rumpf"}
    klein = R.raster(["links", "vorn", "vorn"], "kraeftig", ["kopf"])
    assert klein == [{"richtung": "vorn", "stufe": "kraeftig", "hoehe": "kopf", "wdh": 0},
                     {"richtung": "links", "stufe": "kraeftig", "hoehe": "kopf", "wdh": 0}]  # feste Reihenfolge, ohne Doppel
    assert len(R.raster(stufen=["leicht"])) == 16 and R.raster(["vorn-links"])[0]["richtung"] == "vorn_links"
    for bad in ({"richtungen": ["oben"]}, {"stufen": ["brutal"]}, {"hoehen": ["fuss"]}, {"richtungen": 3}):
        with pytest.raises(R.ReiheFehler):
            R.raster(**bad)
    # von wo gestoßen wird: acht Richtungen im 45°-Raster, rundum
    assert sorted(R.RICHTUNGEN.values()) == [-135, -90, -45, 0, 45, 90, 135, 180]


def test_wiederholungen_streuen_reproduzierbar_und_zeigen_grenzfaelle():
    """0.37: je Zelle bis zu fünf leicht gestreute Wiederholungen; Grenzfälle und Ausfallschritte im Profil."""
    r = R.raster(["vorn"], ["mittel"], ["kopf"], 3)
    assert [v["wdh"] for v in r] == [0, 1, 2]
    assert R.streuung("vorn", "mittel", "kopf", 0) == (0.0, 1.0)
    g, f = R.streuung("vorn", "mittel", "kopf", 1)
    assert (g, f) == R.streuung("vorn", "mittel", "kopf", 1) and (g, f) != (0.0, 1.0)
    assert abs(g) <= R.STREUUNG_GRAD and abs(f - 1) <= R.STREUUNG_STAERKE
    for bad in (0, 6, "viele"):
        with pytest.raises(R.ReiheFehler):
            R.raster(wiederholungen=bad)
    v = [{"richtung": "vorn", "stufe": "mittel", "hoehe": "kopf", "wdh": i, "ausgang": a, "schritt": s}
         for i, (a, s) in enumerate([("steht", True), ("faellt", False), ("wackelt", False)])]
    v += [{"richtung": "links", "stufe": "mittel", "hoehe": "kopf", "wdh": i, "ausgang": "steht"} for i in range(3)]
    z = R.zusammenfassen(v)
    assert z["grenzfaelle"] == 1 and z["schritte"] == 1
    assert z["zellen"]["vorn|mittel|kopf"] == {"stehen": 2, "von": 3}
    assert "1 mit Ausfallschritt" in z["text"] and "1 Grenzfall" in z["text"]


def test_outcome_and_summary():
    from duckpilot.physics.kollision import Episode

    def ausgang(ups, fallen_ab=None):
        ep = Episode(art="stoss", reiz={}, t0=0.0, vorher={"yaw": 0.0})
        for i, up in enumerate(ups):
            tr = {"x": 0, "y": 0, "z": 0.1, "roll": 0, "pitch": 0, "yaw": 0, "up": up, "vx": 0, "vy": 0}
            ep.sample(0.1 * i, tr, fallen_ab is not None and i >= fallen_ab, [0.0] * 15)
        return ep.ausgang

    assert ausgang([1.0, 0.99, 0.98]) == "steht"
    assert ausgang([1.0, 0.9, 0.99]) == "wackelt"          # über 18° gekippt, aber wieder aufrecht
    assert ausgang([1.0, 0.6, 0.2, 0.1], fallen_ab=3) == "faellt"
    assert R.neigung_grad(1.0) == 0 and round(R.neigung_grad(0.0)) == 90
    v = [{"richtung": "vorn", "stufe": "leicht", "hoehe": "rumpf", "ausgang": "steht"},
         {"richtung": "vorn", "stufe": "kraeftig", "hoehe": "rumpf", "ausgang": "wackelt"},
         {"richtung": "links", "stufe": "kraeftig", "hoehe": "kopf", "ausgang": "faellt"}]
    z = R.zusammenfassen(v)
    assert (z["gesamt"], z["stehen"], z["ruhig"], z["wackeln"], z["fallen"]) == (3, 2, 1, 1, 1)
    assert z["text"] == "2 von 3 bleiben stehen (1 ruhig, 1 wackelt), 1 fällt."
    assert z["je_richtung"]["vorn"] == {"steht": 1, "wackelt": 1, "faellt": 0}
    assert z["je_staerke"]["kraeftig"]["faellt"] == 1 and z["je_hoehe"]["kopf"]["faellt"] == 1


def test_profile_file_list_and_routes(daten):
    auftrag = {"raster": R.raster(["vorn"], ["leicht", "mittel"], ["rumpf"])}
    versuche = [{**v, "ausgang": a, "neigung_max_grad": 3.0, "episode": {"x": 1}}
                for v, a in zip(auftrag["raster"], ("steht", "faellt"))]
    pol = {"quelle": "standard", "name": "Test", "sha256": "ab" * 32}
    prof = R.schreibe_profil(daten, "20261029-120000", pol, auftrag, versuche, {"dauer_s": 1.5})
    p = daten / "kollision" / "profile" / "20261029-120000.json"
    assert p.exists() and json.loads(p.read_text("utf-8"))["ergebnis"]["text"] == prof["ergebnis"]["text"]
    assert "episode" not in prof["versuche"][0]                     # Episoden stehen im Episoden-Protokoll
    assert prof["raster"]["richtungen"] == ["vorn"] and prof["raster"]["stufen"] == ["leicht", "mittel"]
    assert R.liste(daten)[0]["id"] == "20261029-120000" and R.liste(daten)[0]["sha256"] == "ab" * 6
    with pytest.raises(R.ReiheFehler):
        R.lade_profil(daten, "../../settings")
    rt = Runtime(load(memory_path=str(daten / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/kollision/reihe/profile").json()["profile"][0]["stehen"] == 1
        assert c.get("/api/kollision/reihe/profile/20261029-120000").json()["profil"]["policy"]["name"] == "Test"
        assert c.get("/api/kollision/reihe/profile/20261029-999999").status_code == 404
        st = c.get("/api/kollision/reihe").json()
        assert st["type"] == "stossreihe" and st["raster"]["versuche"] == 48 and st["lauf"] is None


def test_clear_error_without_real_physics(daten, monkeypatch):
    from duckpilot.stossreihe_service import StossreiheDienst

    monkeypatch.setattr(R, "physik_grund", lambda: R.OHNE_PHYSIK)
    svc = StossreiheDienst(FakeRt())
    res = asyncio.run(svc.start({}))
    assert not res["ok"] and "echte Physik" in res["fehler"] and svc.lauf is None
    assert svc.status()["verfuegbar"] is False and svc.status()["grund"] == R.OHNE_PHYSIK
    rt = Runtime(load(memory_path=str(daten / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        r = c.post("/api/kollision/reihe", json={}, headers=PC)
        assert r.status_code == 400 and "echte Physik" in r.json()["fehler"]
        assert c.post("/api/kollision/reihe/stopp", headers=PC).status_code == 400


def test_only_on_the_pc_and_never_via_mcp(daten, monkeypatch):
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.setattr(Rm, "lan_addresses", lambda: ["192.168.1.10"])
    rt = Runtime(load(memory_path=str(daten / "mem.json")))
    app = create_app(rt)
    with TestClient(app, base_url="http://127.0.0.1:8765") as pc:
        rt.remote.set_enabled(True)
        token = rt.remote.pair(rt.remote.new_code()["code"], "Handy", None)
        phone = TestClient(app, base_url=PHONE_BASE, client=("192.168.1.20", 50000))
        phone.cookies.set(Rm.COOKIE, token)
        ph = {"Origin": PHONE_BASE}
        for method, path in (("post", "/api/kollision/reihe"), ("post", "/api/kollision/reihe/stopp"),
                             ("get", "/api/kollision/reihe"), ("get", "/api/kollision/reihe/profile")):
            r = getattr(phone, method)(path, headers=ph, **({"json": {}} if method == "post" else {}))
            assert r.status_code == 403, path
        assert pc.get("/api/kollision/reihe", headers=PC).status_code == 200
        rt.remote.set_enabled(False)
    root = Path(R.__file__).parents[1]
    for f in ("mcp_server.py", "mcp_bridge.py", "brain/tools.py"):
        src = (root / f).read_text("utf-8")
        assert "kollision/reihe" not in src and "stossreihe" not in src, f


# ── mit Physik und Test-Policy ───────────────────────────────────────────
@braucht_physik
def test_a_trial_pushes_and_records_an_episode(tmp_path):
    from onnx_fixtures import linear_policy

    welt = R.Welt(linear_policy(tmp_path / "steif.onnx"), 1.0, "steif")
    leicht = welt.versuch("vorn", "leicht", "rumpf", einschwingen_s=0.4, nachlauf_s=0.8)
    kraeftig = welt.versuch("vorn", "kraeftig", "kopf", einschwingen_s=0.4, nachlauf_s=0.8)
    for r in (leicht, kraeftig):
        assert r["ausgang"] in ("steht", "wackelt", "faellt") and r["episode"]["art"] == "stoss"
        assert r["episode"]["reiz"]["quelle"] == "reihe" and r["episode"]["reiz"]["richtung"] == "vorn"
        assert r["episode"]["reihe"] and len(r["episode"]["reihe"][0]) == 11 + 15
    assert kraeftig["impuls_ns"] > leicht["impuls_ns"] and kraeftig["neigung_max_grad"] > leicht["neigung_max_grad"]
    # von vorn gestoßen: der Rumpf wird nach hinten geschoben
    assert kraeftig["dv_rumpf"][0] < 0
    assert welt.versuch("vorn", "leicht", "rumpf", 0.4, 0.8, abbruch=lambda: True) is None


@braucht_physik
def test_run_in_own_process_writes_profile_and_episodes(daten, monkeypatch):
    from test_physics import make_store

    from duckpilot.stossreihe_service import StossreiheDienst

    make_store(daten)
    monkeypatch.setattr(R, "EINSCHWINGEN_S", 0.4)
    monkeypatch.setattr(R, "NACHLAUF_S", 0.8)
    rt = FakeRt()
    svc = StossreiheDienst(rt)

    async def lauf():
        res = await svc.start({"richtungen": ["vorn", "hinten"], "stufen": ["leicht"], "hoehen": ["rumpf"]})
        assert res["ok"] and res["gesamt"] == 2 and res["lauf"]["laeuft"]
        again = await svc.start({})
        assert not again["ok"] and "läuft schon" in again["fehler"]
        await asyncio.wait_for(svc._task, 300)

    asyncio.run(lauf())
    lauf_ = svc.lauf
    assert lauf_["status"] == "fertig" and not lauf_["laeuft"], lauf_
    prof = R.lade_profil(daten, lauf_["profil"])
    pfad = daten / "policies" / "pollen" / "velstand.onnx"
    assert prof["policy"]["sha256"] == hashlib.sha256(pfad.read_bytes()).hexdigest()
    assert prof["policy"]["quelle"] == "standard" and prof["ergebnis"]["gesamt"] == 2
    assert "von 2 bleiben stehen" in prof["ergebnis"]["text"] and prof["dauer_s"] > 0
    eps = [json.loads(x) for x in (daten / "kollision" / "episoden.jsonl").read_text("utf-8").splitlines()]
    assert len(eps) == 2 and all(e["reiz"]["quelle"] == "reihe" and e["art"] == "stoss" for e in eps)
    fort = [m for m in rt.nachrichten if m["type"] == "stossreihe"]
    assert [m["fertig"] for m in fort if m["letztes"]][:2] == [1, 2] and fort[-1]["gesamt"] == 2
    assert fort[-1]["lauf"]["status"] == "fertig" and "episode" not in fort[-1]["letztes"]


@braucht_physik
def test_cancel_stops_without_a_profile(daten):
    from test_physics import make_store

    from duckpilot.stossreihe_service import StossreiheDienst

    make_store(daten)
    svc = StossreiheDienst(FakeRt())

    async def lauf():
        assert (await svc.start({}))["ok"]
        assert (await svc.stopp())["ok"]
        await asyncio.wait_for(svc._task, 120)
        assert not (await svc.stopp())["ok"]

    asyncio.run(lauf())
    assert svc.lauf["status"] == "abgebrochen" and svc.lauf["profil"] is None and svc.lauf["fertig"] < 48
    assert R.liste(daten) == []
