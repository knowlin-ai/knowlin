"""Kinematik des SO-101 (seit 0.38.48): Wo ist die Greiferspitze, und welche Gelenkwinkel bringen sie an einen Punkt?

Die Kette ist aus `so101_new_calib.xml` übernommen (TheRobotStudio, Apache-2.0) – dieselben Zahlen wie im gebackenen
Modell der 3D-Ansicht (`tests/test_werkbank.py` prüft das). Koordinaten: Meter im Rahmen des Sockels (x vorn, y links,
z oben), Winkel in Grad wie in `duckpilot/arm.py`.

`greifhaltung(x, y, z)` sucht Winkel, mit denen die Spitze senkrecht von oben an den Punkt kommt (gedämpfte kleinste
Quadrate über vier Gelenke, mehrere Startwerte). Nicht erreichbar → None – der Arm sagt dann ehrlich, dass er nicht
hinkommt. Diese Datei gehört zur Basis und importiert nichts aus Knowlin.
"""

from __future__ import annotations

import functools
import math

import numpy as np

from .arm import GRENZEN, POSEN

# (Name, Elternindex, Lage, Drehung w x y z, Gelenk) – so101_new_calib.xml
KETTE = (
    ("shoulder", -1, (0.0388353, 0.0, 0.0624), (0.0, 0.0, -1.0, 0.0), "shoulder_pan"),
    ("upper_arm", 0, (-0.0303992, -0.0182778, -0.0542), (0.5, -0.5, -0.5, -0.5), "shoulder_lift"),
    ("lower_arm", 1, (-0.11257, -0.028, 0.0), (0.707107, 0.0, 0.0, 0.707107), "elbow_flex"),
    ("wrist", 2, (-0.1349, 0.0052, 0.0), (0.707107, 0.0, 0.0, -0.707107), "wrist_flex"),
    ("gripper", 3, (0.0, -0.0611, 0.0181), (0.0172091, -0.0172091, 0.706897, 0.706897), "wrist_roll"),
)
GRIPPERFRAME = (-0.0079, -0.0002181, -0.0981274)  # Stelle „gripperframe“ im Greifer (Modell)
# Greifmitte: 12 mm vom „gripperframe“ zur beweglichen Backe hin – dort liegt ein Würfel zwischen beiden Backen
# (in der 3D-Ansicht nachgemessen; `arm3d.js` setzt den gehaltenen Würfel an dieselbe Stelle)
SPITZE = (GRIPPERFRAME[0] + 0.012, GRIPPERFRAME[1], GRIPPERFRAME[2])
GENAU_M = 0.006                                  # so nah muss die Spitze ans Ziel
SENKRECHT = 0.2                                  # so weit darf die Greifrichtung von „senkrecht nach unten“ abweichen
IK_GELENKE = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex")


def _rot(q: tuple[float, float, float, float]) -> np.ndarray:
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _rz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


_R = [_rot(q) for _, _, _, q, _ in KETTE]
_P = [np.array(p) for _, _, p, _, _ in KETTE]


def rahmen(gelenke: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
    """Lage und Drehung des Greifers (nach dem Handgelenk-Drehen) im Sockelrahmen. Winkel in Grad."""
    R = np.eye(3)
    p = np.zeros(3)
    for (_, _, _, _, gelenk), Ri, Pi in zip(KETTE, _R, _P):
        p = p + R @ Pi
        R = R @ Ri @ _rz(math.radians(float(gelenke.get(gelenk, 0.0))))
    return p, R


def spitze(gelenke: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
    """Lage der Greiferspitze und Greifrichtung (Einheitsvektor) im Sockelrahmen. Winkel in Grad."""
    p, R = rahmen(gelenke)
    return p + R @ np.array(SPITZE), R @ np.array([0.0, 0.0, -1.0])


def _fehler(q: np.ndarray, ziel: np.ndarray, rest: dict[str, float]) -> np.ndarray:
    g = {**rest, **dict(zip(IK_GELENKE, q))}
    p, d = spitze(g)
    return np.concatenate([p - ziel, 0.04 * (d - np.array([0.0, 0.0, -1.0]))])


def greifhaltung(x: float, y: float, z: float, greifer: float = 0.0, drehung: float = 0.0) -> dict[str, float] | None:
    """Gelenkwinkel (Grad), mit denen die Spitze senkrecht von oben bei (x, y, z) ist – oder None. `drehung`: Handgelenk
    (wrist_roll) – bei 0 öffnen die Backen zum Sockel hin und weg, bei ±90 quer dazu. Der Greifer ändert die Lage der
    Spitze nicht – deshalb wird je Punkt und Drehung nur einmal gerechnet (seit 0.38.55, der Planer probiert Varianten)."""
    g = _haltung(round(float(x), 4), round(float(y), 4), round(float(z), 4), round(float(drehung), 1))
    return None if g is None else {**g, "gripper": float(greifer)}


@functools.lru_cache(maxsize=4096)
def _haltung(x: float, y: float, z: float, drehung: float) -> dict[str, float] | None:
    ziel = np.array([x, y, z], dtype=float)
    lo = np.array([GRENZEN[g][0] for g in IK_GELENKE])
    hi = np.array([GRENZEN[g][1] for g in IK_GELENKE])
    rest = {"wrist_roll": float(drehung), "gripper": 0.0}
    pan0 = math.degrees(math.atan2(y, x)) if math.hypot(x, y) > 1e-6 else 0.0
    beste: tuple[float, np.ndarray] | None = None
    for start in ((pan0, -20.0, 40.0, 70.0), (pan0, 20.0, 10.0, 60.0), (pan0, -50.0, 80.0, 60.0), (-pan0, 0.0, 30.0, 60.0)):
        q = np.clip(np.array(start, dtype=float), lo, hi)
        for _ in range(80):
            f = _fehler(q, ziel, rest)
            if np.linalg.norm(f[:3]) < 1e-4:
                break
            J = np.zeros((6, 4))
            for i in range(4):
                dq = np.zeros(4)
                dq[i] = 0.05
                J[:, i] = (_fehler(q + dq, ziel, rest) - f) / 0.05
            q = np.clip(q - np.linalg.solve(J.T @ J + 1e-6 * np.eye(4), J.T @ f), lo, hi)
        f = _fehler(q, ziel, rest)
        gut = float(np.linalg.norm(f[:3]))
        if beste is None or gut < beste[0]:
            beste = (gut, q)
        if gut < 1e-4:                                   # getroffen – die übrigen Startwerte braucht es nicht
            break
    assert beste is not None
    g = {**rest, **{k: round(float(v), 2) for k, v in zip(IK_GELENKE, beste[1])}}
    p, d = spitze(g)
    if float(np.linalg.norm(p - ziel)) > GENAU_M or float(np.linalg.norm(d - np.array([0.0, 0.0, -1.0]))) > SENKRECHT:
        return None
    return g


def bereit_spitze() -> tuple[float, float, float]:
    p, _ = spitze(POSEN["bereit"])
    return float(p[0]), float(p[1]), float(p[2])
