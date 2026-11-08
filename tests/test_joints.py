"""Gelenk-Check, Pflegeheft und Abgleich Training ↔ Roboter."""

import asyncio

import pytest

from duckpilot.api import JOINT_NAMES
from duckpilot.backends.sim import SimBackend
from duckpilot.joints import ALIGNMENT, build, grade, vetbook_summary


def test_grade_thresholds():
    assert grade(0.02, 0.3) == "gut"
    assert grade(0.12, None) == "auffaellig"
    assert grade(None, 0.75) == "auffaellig"
    assert grade(0.3, 0.1) == "pruefen"
    assert grade(0.0, 0.95) == "pruefen"


def test_build_tracking_error_and_current():
    ist = [0.0] * 15
    soll = [0.0] * 15
    soll[3] = 0.3                         # linkes Knie hinkt 0,3 rad hinterher
    strom = [100.0] * 15
    strom[13] = 1700.0                    # rechtes Knie fast am Anschlag
    rep = build(ist, soll, None, strom, quelle="robotd")
    rows = {r["name"]: r for r in rep["gelenke"]}
    assert rows["left_knee"]["ampel"] == "pruefen" and abs(rows["left_knee"]["fehler"] - 0.3) < 1e-9
    assert rows["right_knee"]["ampel"] == "pruefen" and rows["right_knee"]["last"] > 0.9
    assert rows["mouth"]["fehler"] is None
    assert rep["summe"]["ampel"] == "pruefen"
    assert "Linkes Knie" in rep["summe"]["auffaellig"]
    # stromlos: Nachlauf ist normal, keine Warnung
    assert build(ist, soll, None, strom, quelle="robotd", aktiv=False)["summe"]["ampel"] == "gut"


def test_build_tolerates_garbage():
    rep = build(["x", None, float("nan")], ["y"], quelle="robotd")
    assert len(rep["gelenke"]) == len(JOINT_NAMES)
    assert all(r["ist"] is None or isinstance(r["ist"], float) for r in rep["gelenke"])


def test_sim_reports_angles_only():
    rep = SimBackend(realtime=False).joint_report()
    assert len(rep["gelenke"]) == 15 and rep["hinweis"]
    assert rep["summe"]["nachlauf_max"] is None


def test_vetbook_summary_picks_worn_motor():
    raw = {"motors": [
        {"id": 1, "joint": "left_knee", "wear": {"torqued_s": 7200, "travel_rad": 62.8, "hottest_c": 50,
                                                 "hot_s": 120, "trips": {"overheat": 0, "overload": 0}}},
        {"id": 2, "joint": "right_knee", "wear": {"torqued_s": 3600, "trips": {"overheat": 2, "overload": 1}}},
        {"id": 3, "joint": "head_yaw", "retired": True, "wear": {"trips": {"shock": 9}}},
        "kaputt",
    ], "events": [{"at": "t", "kind": "note", "text": "<b>hallo</b>"}]}
    v = vetbook_summary(raw)
    assert v["zuerst_ansehen"] == ["Rechtes Knie"]               # ausgemusterte Motoren zählen nicht
    left = v["motoren"][0]
    assert left["stunden_unter_strom"] == 2.0 and left["weg_umdrehungen"] == 10.0 and left["heiss_min"] == 2.0
    assert v["ereignisse"][0]["text"] == "<b>hallo</b>"           # Text bleibt Text – der Browser setzt textContent
    assert vetbook_summary("nein") is None


def test_alignment_table_is_complete():
    themes = {a["thema"] for a in ALIGNMENT}
    assert {"Aktionsskala", "Spiel in den Getrieben"} <= themes
    assert all(a["stand"] in ("gleich", "abweichend", "abgedeckt", "wählbar") for a in ALIGNMENT)


def test_robotd_report_and_vetbook_via_fake():
    from duckpilot.backends.fake_robotd import start_server
    from duckpilot.backends.robotd import RobotdBackend

    async def run():
        server, _fake = await start_server("tcp:127.0.0.1:7941")
        be = RobotdBackend("tcp:127.0.0.1:7941")
        await be.connect()
        try:
            for _ in range(40):
                await asyncio.sleep(0.1)
                if be.state().connected:
                    break
            rep = be.joint_report()
            vet = vetbook_summary(await be.vetbook())
        finally:
            await be.close()
            server.close()
        return rep, vet

    rep, vet = asyncio.run(run())
    assert rep["quelle"] == "robotd" and len(rep["gelenke"]) == 15
    assert vet["zuerst_ansehen"] == ["Rechtes Knie"]


def test_physics_report(tmp_path):
    pytest.importorskip("mujoco")
    pytest.importorskip("onnxruntime")
    from test_physics import make_store

    from duckpilot.backends.physics import PhysicsBackend

    be = PhysicsBackend(make_store(tmp_path), realtime=False)
    for _ in range(40):
        be.step(0.05)
    rep = be.joint_report()
    rows = {r["name"]: r for r in rep["gelenke"]}
    assert rows["left_knee"]["soll"] is not None and rows["left_knee"]["last"] is not None
    assert rep["summe"]["nachlauf_max"] < 0.5
