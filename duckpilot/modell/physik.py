"""Pollens MuJoCo-Modell der Microduck für den Physik-Simulator aufbereiten – auf diesem PC, beim ersten Laden.

Aus `robot_groundcontact.xml` (dem Modell, mit dem Pollen die Policies trainiert) wird:
* jede reine Darstellungs-Geometrie entfernt (contype = conaffinity = 0) – Masse und Trägheit stehen in eigenen
  <inertial>-Elementen und bleiben unverändert;
* nicht mehr gebrauchte Meshes und alle Materialien gestrichen (Farben macht duckpilot selbst).

Die Kollisions-Meshes bleiben Pollens STL-Dateien im Quellordner daneben. MuJoCo kollidiert ohnehin mit ihrer
konvexen Hülle – dasselbe Ergebnis wie `tools/bake_physics.py`, das die Hüllen für die private Fassung direkt in
die XML schreibt (und dafür scipy braucht).
"""

from __future__ import annotations

import re
from pathlib import Path


def bake(robot_xml: Path, dest: Path) -> dict:
    """robot_groundcontact.xml → dest (XML). Die Meshes werden relativ zu dest gefunden."""
    import mujoco

    spec = mujoco.MjSpec.from_file(str(robot_xml))
    removed = 0
    for g in list(spec.geoms):
        if g.contype == 0 and g.conaffinity == 0:
            spec.delete(g)
            removed += 1
    used = {g.meshname for g in spec.geoms if g.type == mujoco.mjtGeom.mjGEOM_MESH}
    for m in list(spec.meshes):
        if m.name not in used:
            spec.delete(m)
    for g in spec.geoms:
        g.material = ""
    for mat in list(spec.materials):
        spec.delete(mat)
    meshdir = robot_xml.parent / (spec.meshdir or "assets")
    spec.compile()
    xml = spec.to_xml()
    # Meshes relativ zur neuen Datei finden (MuJoCo löst meshdir relativ zur XML auf)
    rel = Path(meshdir.resolve().relative_to(dest.parent.resolve())).as_posix()
    xml, n = re.subn(r'meshdir="[^"]*"', f'meshdir="{rel}"', xml, count=1)
    if n != 1:
        raise ValueError("meshdir fehlt im Modell")
    head = ("<!-- Microduck, Pollen Robotics (github.com/pollen-robotics/microduck_rl). Modell Apache-2.0, "
            "Meshes CC BY-NC-SA 4.0. Für duckpilot aufbereitet: nur Kollisionskörper, Trägheit unverändert. -->\n")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".teil")
    tmp.write_text(head + xml, encoding="utf-8")
    model = mujoco.MjModel.from_xml_path(str(tmp))
    tmp.replace(dest)
    return {"entfernt": removed, "huellen": len(used), "nu": int(model.nu), "masse": round(float(model.body_subtreemass[1]), 3)}
