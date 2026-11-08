"""Parcours und Auftrag: Geometrie in MuJoCo, Durchlauf, Auftragsschritte, Werkzeuge, Server."""

import asyncio
import json

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")
pytest.importorskip("onnxruntime")
pytest.importorskip("onnx")

from onnx_fixtures import linear_policy  # noqa: E402
from test_physics import make_store  # noqa: E402

from duckpilot.mission import CourseLab, MissionStore, steps  # noqa: E402
from duckpilot.physics import course as K  # noqa: E402
from duckpilot.physics.core import PhysicsCore  # noqa: E402


def _height(core, x, y=0.0):
    gid = np.array([-1], dtype=np.int32)
    dist = mujoco.mj_ray(core.model, core.data, np.array([x, y, 0.5]), np.array([0, 0, -1.0]), None, 1,
                         core.trunk_id, gid)
    return 0.5 - dist


def test_course_geometry_matches_the_description():
    c = K.build({"name": "Probe", "elemente": [
        {"art": "rampe", "hoehe_cm": 4, "laenge_cm": 40, "plateau_cm": 20},
        {"art": "stufen", "anzahl": 2, "hoehe_cm": 2, "tiefe_cm": 15, "plateau_cm": 20},
        {"art": "schwelle", "hoehe_cm": 1.5, "tiefe_cm": 4},
        {"art": "slalom", "anzahl": 3, "abstand_cm": 40, "versatz_cm": 15},
        {"art": "engstelle", "breite_cm": 24, "laenge_cm": 30},
        {"art": "uneben", "hoehe_cm": 1.2, "laenge_cm": 60}]})
    assert abs(c.start[0] + c.length / 2 - 0.05) < 1e-9 and abs(c.goal[0] - c.length / 2 + 0.05) < 1e-9
    core = PhysicsCore(None, course=c)
    mujoco.mj_forward(core.model, core.data)
    ramp, stairs, sill = c.elements[:3]
    # Rampe: 4 cm auf 40 cm, oben 20 cm eben, wieder hinunter
    for frac_m, want in ((0.10, 0.01), (0.20, 0.02), (0.50, 0.04), (0.90, 0.01)):
        assert abs(_height(core, ramp.x0 + frac_m * (ramp.x1 - ramp.x0)) - want) < 0.0015
    # Treppe: Stufe 1 = 2 cm, Stufe 2 = 4 cm, symmetrisch
    assert abs(_height(core, stairs.x0 + 0.07) - 0.02) < 1e-3
    assert abs(_height(core, (stairs.x0 + stairs.x1) / 2) - 0.04) < 1e-3
    assert abs(_height(core, stairs.x1 - 0.07) - 0.02) < 1e-3
    assert abs(_height(core, (sill.x0 + sill.x1) / 2) - 0.015) < 1e-3
    assert abs(_height(core, (ramp.x1 + stairs.x0) / 2)) < 1e-6          # dazwischen ebener Boden
    # Slalom: Stangen in der Mitte, Wegmarken abwechselnd links/rechts
    sl = c.elements[3]
    assert [round(y, 2) for _, y in sl.waypoints] == [0.15, -0.15, 0.15]
    # Engstelle: zwei Wände, die Gasse dazwischen ist frei
    eng = c.elements[4]
    mid = (eng.x0 + eng.x1) / 2
    assert _height(core, mid, 0.0) < 1e-6 and abs(_height(core, mid, 0.13) - 0.12) < 1e-3
    world = c.world()
    assert world["offen"] and any(t.get("marke") == "Ziel" for t in world["teile"]) and len(world["cylinders"]) == 3
    assert any(abs(t["pitch"]) > 0.05 for t in world["teile"])        # die Rampe ist gekippt


def test_course_limits_and_warnings():
    steep = K.build({"elemente": [{"art": "stufen", "hoehe_cm": 5}, {"art": "rampe", "hoehe_cm": 30}]})
    assert "Richtwert" in steep.elements[0].warnung
    assert "erlaubt" in steep.elements[1].warnung and steep.elements[1].p["hoehe_cm"] == 10
    assert steep.summary()["elemente"][0]["kurz"] == "2 × 5 cm, 15 cm tief"
    assert K.build({"elemente": [{"art": "schwelle", "hoehe_cm": 1.5}]}).elements[0].describe() == "1,5 cm hoch"
    for bad in ({"elemente": []}, {"elemente": [{"art": "trampolin"}]}, {"elemente": [{"art": "slalom"}] * 9},
                {"elemente": [{"art": "uneben", "laenge_cm": 150}] * 6}, {"elemente": [{"art": "rampe", "hoehe_cm": "hoch"}]}):
        with pytest.raises(K.CourseError):
            K.build(bad)


def test_attempts_report_falls_and_record_a_replay(tmp_path):
    c = K.build(K.PRESETS["Rampe und Stufen"])
    zero = linear_policy(tmp_path / "zero.onnx")        # hält nichts: fällt gleich um
    res = K.evaluate(c, str(zero), attempts=2, label="Test", max_seconds=12)
    assert res["versuche"] == 2 and res["im_ziel"] == 0 and res["urteil"] == "nicht geschafft"
    assert res["stuerze"] >= 2 and {f["versuch"] for f in res["sturzstellen"]} == {1, 2}
    assert "Anlaufstrecke" in res["hinweise"][0]
    assert [e["von"] for e in res["elemente"]] == [2, 2] and res["reibung"][0] == 1.0
    frames = res["wiederholung"]
    assert frames and all(len(f) == 22 for f in frames) and frames[-1][0] <= 12.1
    cancelled = K.run_attempt(c, str(zero), cancel=lambda: True)
    assert cancelled.ende == "abgebrochen"


class FakeTrainer:
    def __init__(self, onnx):
        self.vorschlag = None
        self._runs = [{"id": "r1", "plan": {"aufgabe": "Mjlab-Velocity-Rough-MicroDuck"}, "status": "trainiert",
                       "start": "2026-10-28 10:00", "onnx": str(onnx)}]

    def runs(self):
        return self._runs

    def result(self, token, rid):
        return self._runs[0]["onnx"]

    def measured(self):
        return {}


def test_mission_runs_from_goal_to_automatic_evaluation(tmp_path):
    store = make_store(tmp_path)
    trainer = FakeTrainer(linear_policy(tmp_path / "trained.onnx"))
    lab = CourseLab(tmp_path, lambda: store, trainer)
    assert steps(None, [])[0]["stand"] == "offen"
    out = lab.build({"name": "Rampe", "elemente": [{"art": "rampe", "hoehe_cm": 3}]},
                    "Die Ente soll über eine Rampe")
    assert out["ziel"] == "Die Ente soll über eine Rampe" and out["elemente"][0]["kurz"].startswith("3 cm")
    test = asyncio.run(lab.test("standard", 1))
    assert test["quelle"] == "standard" and test["wiederholung"] and lab.missions.replay(test["id"])
    assert lab.missions.replay("../etc") is None
    st = {s["id"]: s for s in steps(lab.missions.current(), trainer.runs())}
    assert st["basis"]["stand"] == "fertig" and st["vorschlag"]["stand"] == "jetzt"
    plan = {"aufgabe": "Mjlab-Velocity-Rough-MicroDuck", "iterationen": 5000, "anpassungen": {}, "begruendung": "Rampe"}
    lab.missions.link_proposal(plan)
    assert lab.missions.link_run(plan, {"id": "r0"}) and lab.missions.link_run(plan, trainer.runs()[0])
    assert lab.missions.current()["lauf"] == "r1"                  # der neueste Lauf zählt
    assert not lab.missions.link_run({"aufgabe": "Mjlab-Spin-Flat-MicroDuck"}, {"id": "r9"})
    assert asyncio.run(lab.check_finished_runs()) == []          # Lauf noch nicht fertig
    with pytest.raises(ValueError):
        asyncio.run(lab.test("lauf:r1", 1))
    trainer._runs[0]["status"] = "fertig"
    [auto] = asyncio.run(lab.check_finished_runs())
    assert auto and auto["auto"] and auto["quelle"] == "lauf:r1"
    assert asyncio.run(lab.check_finished_runs()) == []          # nur einmal
    st = {s["id"]: s for s in steps(lab.missions.current(), trainer.runs())}
    assert st["training"]["stand"] == "fertig" and st["bewertung"]["stand"] == "fertig"
    # anderes Ziel nach Tests: neuer Auftrag, der alte bleibt im Verlauf
    lab.build({"elemente": [{"art": "slalom"}]}, "Slalom")
    assert len(lab.missions.data["liste"]) == 2 and lab.missions.current()["tests"] == []
    again = MissionStore(tmp_path)
    assert again.current()["ziel"] == "Slalom"
    msg = lab.message(True)
    assert msg["welt"]["bahn"] and msg["quellen"][0]["id"] == "standard" and len(msg["verlauf"]) == 2
    json.dumps(msg)


def test_tools_build_and_test_and_link_the_proposal(tmp_path):
    from helpers import make

    from duckpilot.brain.local import LOCAL_TOOLS
    from duckpilot.brain.tools import ToolRunner

    async def go():
        sim, eng = await make()
        runner = ToolRunner(eng)
        assert "parcours_bauen" not in [t["name"] for t in runner.tools()]
        trainer = FakeTrainer(tmp_path / "x.onnx")
        runner.lab = CourseLab(tmp_path, lambda: make_store(tmp_path), trainer)
        runner.trainer = trainer
        names = [t["name"] for t in runner.tools()]
        assert "parcours_bauen" in names and "parcours_testen" in names
        bad = await runner.run("parcours_bauen", {"elemente": [{"art": "wippe"}]})
        assert bad["ok"] is False and "Unbekanntes Element" in bad["fehler"]
        built = await runner.run("parcours_bauen", {"ziel": "Slalom schaffen", "elemente": [{"art": "slalom", "anzahl": 2}]})
        assert built["ok"] and built["elemente"][0]["art"] == "slalom"
        res = await runner.run("parcours_testen", {"versuche": 1})
        assert res["ok"] and res["versuche"] == 1 and "wiederholung" not in res
        prop = await runner.run("training_vorschlagen", {"aufgabe": "Mjlab-Velocity-Flat-MicroDuck", "begruendung": "Slalom"})
        assert prop["ok"] and runner.lab.missions.current()["vorschlag"]["aufgabe"] == "Mjlab-Velocity-Flat-MicroDuck"
        await eng.close()
    asyncio.run(go())
    assert {"parcours_bauen", "parcours_testen"} <= LOCAL_TOOLS


def test_server_parcours_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    make_store(tmp_path)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        st = c.get("/api/parcours").json()
        assert st["verfuegbar"] and st["parcours"] is None and "Slalom" in st["vorlagen"]
        assert c.post("/api/parcours/testen", json={}).status_code == 400
        assert c.post("/api/parcours/bauen", json={"vorlage": "gibts nicht"}).status_code == 400
        assert c.post("/api/parcours/bauen", json={"elemente": [{"art": "x"}]}).status_code == 400
        r = c.post("/api/parcours/bauen", json={"vorlage": "Slalom"}).json()
        assert r["ok"] and r["parcours"]["elemente"][0]["art"] == "slalom"
        assert c.get("/api/parcours").json()["schritte"][1]["stand"] == "fertig"
        assert c.get("/api/parcours/wiederholung/nichts").status_code == 404
        assert c.post("/api/parcours/auftrag", json={"id": "gibtsnicht"}).status_code == 404
        assert c.post("/api/parcours/auftrag", json={"ziel": "Neu"}).json()["ok"]
        assert c.get("/api/parcours").json()["auftrag"]["ziel"] == "Neu"
        assert any(t["name"] == "parcours_testen" for t in rt.runner.tools())


def test_review_fixes_cancel_switch_retry_and_validation(tmp_path):
    store = make_store(tmp_path)
    trainer = FakeTrainer(linear_policy(tmp_path / "trained.onnx"))
    lab = CourseLab(tmp_path, lambda: store, trainer)
    lab.build({"elemente": [{"art": "schwelle"}]}, "Schwelle")
    # abgebrochen: kein Ergebnis gespeichert
    lab._cancel = True
    orig = K.evaluate

    def cancelled(*a, **k):
        lab._cancel = True
        return orig(*a, **{**k}) if False else orig(a[0], a[1], 1, max_seconds=1)
    K.evaluate = cancelled
    try:
        with pytest.raises(ValueError):
            asyncio.run(lab.test("standard", 1))
    finally:
        K.evaluate = orig
    assert lab.missions.current()["tests"] == [] and lab.job["text"] == "abgebrochen"
    # Ergebnis für einen inzwischen geänderten Parcours wird verworfen
    mid, spec = lab.missions.current()["id"], lab.missions.current()["parcours"]
    lab.build({"elemente": [{"art": "rampe"}]})
    assert not lab.missions.add_test({"id": "x", "quelle": "standard"}, mid, spec)
    # Parcours-Wechsel räumt Vorschlag und Lauf ab
    lab.missions.link_proposal({"aufgabe": "Mjlab-Velocity-Rough-MicroDuck"})
    lab.missions.link_run({"aufgabe": "Mjlab-Velocity-Rough-MicroDuck"}, {"id": "r1"})
    assert lab.missions.current()["lauf"] == "r1"
    assert lab.missions.link_run({"aufgabe": "Mjlab-Velocity-Rough-MicroDuck"}, {"id": "r2"})   # neuester Lauf zählt
    lab.build({"elemente": [{"art": "slalom"}]})
    m = lab.missions.current()
    assert m["vorschlag"] is None and m["lauf"] is None
    # automatische Prüfung: Fehlschlag wird beim nächsten Mal wiederholt
    lab.missions.link_proposal({"aufgabe": "Mjlab-Velocity-Rough-MicroDuck"})
    lab.missions.link_run({"aufgabe": "Mjlab-Velocity-Rough-MicroDuck"}, {"id": "r1"})
    trainer._runs[0]["status"] = "fertig"
    trainer._runs[0]["onnx"] = str(tmp_path / "fehlt.onnx")
    lab.token = lambda: None
    assert asyncio.run(lab.check_finished_runs()) == [] and "lauf:r1" not in lab._auto_tried
    # Eingaben
    for bad in ({"elemente": 5}, {"elemente": {"art": "rampe"}}, [1, 2]):
        with pytest.raises(K.CourseError):
            K.build(bad)
    assert K.build({"elemente": [{"art": "slalom", "versatz_cm": 8}]}).elements[0].p["versatz_cm"] == 11


def test_replay_timestamps_match_the_frame_rate(tmp_path):
    c = K.build({"elemente": [{"art": "schwelle"}]})
    a = K.run_attempt(c, str(linear_policy(tmp_path / "z.onnx")), record=True, max_seconds=3)
    times = [f[0] for f in a.replay]
    steps_ = {round(b - a_, 2) for a_, b in zip(times, times[1:])}
    assert steps_ == {round(1 / K.REPLAY_HZ, 2)}
