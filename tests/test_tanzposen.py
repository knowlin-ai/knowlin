"""Tanzposen stehen in der Physik (seit 0.38.42, Maintainer: „bei Tanz nimmt Microduck teilweise Posen, die in der
Physik noch zum Umfallen führen“): zu wackelige Haltungen werden abgeschwächt oder nur angedeutet."""

import numpy as np

from duckpilot import acrobatics_service as A


class Probe:
    """Ersatz für die Physik: steht, solange das erste Gelenk höchstens `grenze` von der Grundstellung abweicht."""

    def __init__(self, grenze: float) -> None:
        self.grenze = grenze
        self.n = len(A.JOINT_NAMES)

    def pose_from(self, joints):
        q = np.zeros(self.n)
        for i, name in enumerate(A.JOINT_NAMES):
            q[i] = float(joints.get(name, 0.0))
        return q

    def as_dict(self, q):
        return {n: round(float(q[i]), 4) for i, n in enumerate(A.JOINT_NAMES)}

    def place(self, q):
        return {"reserve_mm": 10.0 if abs(q[0]) <= self.grenze else -5.0, "nicht_nur_fuesse": False}

    def hold(self, q, seconds=1.0):
        return {"steht": abs(q[0]) <= self.grenze}


def test_sichere_haltung_bleibt_wie_sie_ist():
    pose = {A.JOINT_NAMES[0]: 0.2}
    assert A.sichere_pose(Probe(0.5), pose) == pose


def test_wackelige_haltung_wird_abgeschwaecht():
    erg = A.sichere_pose(Probe(0.5), {A.JOINT_NAMES[0]: 1.0})
    assert erg is not None and 0.45 <= erg[A.JOINT_NAMES[0]] <= 0.5


def test_fast_nur_grundstellung_faellt_aus_dem_tanz():
    assert A.sichere_pose(Probe(0.1), {A.JOINT_NAMES[0]: 1.0}) is None
