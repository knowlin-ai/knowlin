"""Pollens MuJoCo-Modell der Microduck für duckpilot aufbereiten (eine Datei, ohne Meshes).

Aus `microduck_rl/src/mjlab_microduck/robot/microduck/robot_groundcontact.xml` (das Modell, mit dem
Pollen die Policies trainiert) wird:
* jede reine Darstellungs-Geometrie entfernt (contype = conaffinity = 0) – Masse und Trägheit
  stehen in eigenen <inertial>-Elementen und bleiben unverändert;
* jede Kollisions-Mesh durch ihre konvexe Hülle ersetzt, direkt als Punktliste in der XML.
  MuJoCo kollidiert ohnehin mit der konvexen Hülle – das Ergebnis ist dasselbe;
* Materialien gestrichen (Farben macht duckpilot selbst).

Aufruf: python tools/bake_physics.py /pfad/zu/microduck_rl
Ergebnis: duckpilot/physics/microduck.xml (CC BY-NC-SA 4.0 wie Pollens Modell).
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import mujoco
import numpy as np
from scipy.spatial import ConvexHull

OUT = Path(__file__).resolve().parents[1] / "duckpilot" / "physics" / "microduck.xml"


def read_stl(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        pts = [list(map(float, ln.split()[1:4])) for ln in data.decode(errors="ignore").splitlines()
               if ln.strip().startswith("vertex")]
        return np.unique(np.array(pts), axis=0)
    n = struct.unpack("<I", data[80:84])[0]
    arr = np.frombuffer(data[84:84 + n * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return np.unique(arr["v"].reshape(-1, 3).astype(np.float64), axis=0)


def main(rl: Path) -> None:
    robot = rl / "src" / "mjlab_microduck" / "robot" / "microduck" / "robot_groundcontact.xml"
    spec = mujoco.MjSpec.from_file(str(robot))
    meshdir = robot.parent / (spec.meshdir or "assets")
    removed = 0
    for g in list(spec.geoms):
        if g.contype == 0 and g.conaffinity == 0:
            spec.delete(g)
            removed += 1
    used = {g.meshname for g in spec.geoms if g.type == mujoco.mjtGeom.mjGEOM_MESH}
    for m in list(spec.meshes):
        if m.name not in used:
            spec.delete(m)
            continue
        verts = read_stl(meshdir / m.file) * np.array(m.scale)
        hull = verts[ConvexHull(verts).vertices]
        m.file = ""
        m.uservert = hull.astype(np.float32).ravel().tolist()
        m.scale = [1, 1, 1]
    for g in spec.geoms:
        g.material = ""
    for mat in list(spec.materials):
        spec.delete(mat)
    spec.meshdir = ""
    spec.compile()
    xml = spec.to_xml()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    head = ("<!-- Microduck, Pollen Robotics (microduck_rl, CC BY-NC-SA 4.0). Für duckpilot aufbereitet: "
            "nur Kollisionskörper (konvexe Hüllen), Trägheit unverändert. tools/bake_physics.py -->\n")
    OUT.write_text(head + xml, encoding="utf-8")
    m = mujoco.MjModel.from_xml_string(xml)
    print(f"{OUT.name}: {OUT.stat().st_size // 1024} KB, {removed} Darstellungsteile entfernt, "
          f"{len(used)} Hüllen, nu={m.nu}, nq={m.nq}, Masse {m.body_subtreemass[1]:.3f} kg")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/root/ref/microduck_rl"))
