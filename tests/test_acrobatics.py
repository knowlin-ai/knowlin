"""Akrobatik: Gleichgewicht der Gliederpuppe, Probe, Üben und Fähigkeitsheft."""

import time

import numpy as np
import pytest

pytest.importorskip("mujoco")

from duckpilot.acrobatics_service import AcrobaticsService, _clean_pose  # noqa: E402
from duckpilot.physics.acrobatics import ACTUATORS, EXERCISES, Acrobat, _hull, margin  # noqa: E402


@pytest.fixture(scope="module")
def acro():
    return Acrobat()


def test_margin_inside_outside_and_degenerate():
    sq = _hull(np.array([[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5]], float))
    assert len(sq) == 4
    assert abs(margin(np.array([0.5, 0.5]), sq) - 0.5) < 1e-9
    assert margin(np.array([2.0, 0.5]), sq) < 0
    assert margin(np.array([0.0, 0.0]), np.zeros((0, 2))) < 0
    assert margin(np.array([0.0, 1.0]), np.array([[0.0, 0.0], [1.0, 0.0]])) == pytest.approx(-1.0)


def test_standing_is_green_and_holds(acro):
    q = acro.pose_from({})
    st = acro.place(q)
    assert st["ampel"] == "gruen" and st["reserve_mm"] > 10
    assert abs(st["fuesse_mm"]["left"]) < 1 and abs(st["fuesse_mm"]["right"]) < 1
    r = acro.hold(q)
    assert r["steht"] and r["kippen_max_grad"] < 10 and len(r["bilder"]) >= 30
    assert len(r["bilder"][0]["joints"]) == len(ACTUATORS)


def test_lifting_a_leg_rests_on_the_other_foot(acro):
    q = acro.pose_from({})
    q[ACTUATORS.index("right_knee")] += 0.8
    q[ACTUATORS.index("right_hip_pitch")] -= 0.8
    st = acro.place(acro.pose_from(acro.as_dict(q)))
    assert st["fuesse_mm"]["right"] > 15 and abs(st["fuesse_mm"]["left"]) < 1
    assert st["ampel"] == "rot"                  # Schwerpunkt noch zwischen den Füßen – sie kippt


def test_extreme_lean_is_red_and_falls(acro):
    q = acro.pose_from({n: 0.6 for n in ("left_ankle",)} | {"right_ankle": -0.6})
    st = acro.place(q)
    r = acro.hold(q)
    assert st["ampel"] in ("rot", "gelb") or not r["steht"]


def test_joint_limits_are_respected(acro):
    q = acro.pose_from({"left_knee": 99.0, "mouth": 1.0, "unbekannt": 1})
    i = ACTUATORS.index("left_knee")
    assert q[i] == pytest.approx(acro.hi[i])


def test_practice_one_leg_improves(acro):
    res = Acrobat().practice(acro.pose_from({}), EXERCISES["links"], generations=10, samples=14)
    assert res["verlauf"][0]["faehigkeit"] < res["faehigkeit"]
    assert res["faehigkeit"] >= 60, res["verlauf"]
    assert res["probe"]["steht"] and res["probe"]["fuss_hoch_mm"]["right"] >= 25


def test_service_book_and_background_job(tmp_path):
    svc = AcrobaticsService(tmp_path)
    ov = svc.overview()
    assert ov["verfuegbar"] and len(ov["gelenke"]) == 14 and {u["id"] for u in ov["uebungen"]} >= {"links", "rechts"}
    assert svc.check({"left_knee": "x"})["ampel"] == "gruen"
    with pytest.raises(ValueError):
        svc.save_pose("   ", {"left_knee": 0.1})
    assert svc.save_pose("  Flamingo  ", {"left_knee": 0.1, "evil": 5})["name"] == "Flamingo"
    assert AcrobaticsService(tmp_path).book["posen"]["Flamingo"] == {"left_knee": 0.1}
    with pytest.raises(ValueError):
        svc.start_practice({}, "salto")
    svc.start_practice({}, "frei")
    with pytest.raises(RuntimeError):
        svc.start_practice({}, "frei")
    for _ in range(300):
        if not svc.job["laeuft"]:
            break
        time.sleep(0.1)
    assert svc.job["fehler"] is None and svc.job["ergebnis"]["faehigkeit"] > 50
    book = AcrobaticsService(tmp_path).book["uebungen"]["frei"]
    assert book["beste"] == svc.job["ergebnis"]["faehigkeit"] and len(book["verlauf"]) == 1
    assert book["start"] == svc.job["ergebnis"]["verlauf"][0]["faehigkeit"]
    assert svc.delete_pose("Flamingo") and not svc.delete_pose("Flamingo")


def test_clean_pose_drops_garbage():
    assert _clean_pose({"left_knee": float("nan"), "right_knee": 9, "head_yaw": 0.2, "x": 1}) == {"head_yaw": 0.2}
    assert _clean_pose("nein") == {}
