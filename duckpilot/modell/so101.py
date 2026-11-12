"""3D-Modell des SO-101-Arms (seit 0.38.47, Etappe G5) – aus dem offenen Projekt von TheRobotStudio und Hugging Face.

Quelle: `github.com/TheRobotStudio/SO-ARM100`, Ordner `Simulation/SO101` (so101_new_calib.xml + STL), fester Stand
`QUELLE["commit"]`. Das Repo steht unter Apache-2.0 – das gebackene Modell darf deshalb mit Knowlin verteilt werden
(Hinweis in `server/static/model/LIZENZ-so101.md`), wie bei der Open Duck.

Gebacken wird wie bei der Open Duck (DPM2, `ansicht.py`): nur die sichtbaren Teile (Klasse „visual“), Farben aus den
Materialien, Gelenke mit Grenzen. „Neue Kalibrierung“: Null ist bei jedem Gelenk die Mitte seines Bereichs.

Neu backen: `python tools/bake_so101.py <Klon von SO-ARM100>`.
"""

from __future__ import annotations

import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

QUELLE = {"repo": "TheRobotStudio/SO-ARM100", "commit": "a758567c3978dfeefe282ede0500085a48fe8f78",
          "ordner": "Simulation/SO101", "mjcf": "so101_new_calib.xml", "lizenz": "Apache-2.0"}
GELENKE = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
FINISH = {"sts3215_03a_v1": "servo", "sts3215_03a_no_horn_v1": "servo"}


def bake(folder: Path, dest: Path, commit: str = QUELLE["commit"]) -> dict[str, Any]:
    import numpy as np

    from .ansicht import AUFBEREITUNG, floats, load_stl, prepare

    root = ET.parse(folder / QUELLE["mjcf"]).getroot()
    meshdir = folder / (root.find("compiler").get("meshdir") or ".")
    files = {m.get("name") or Path(m.get("file")).stem: m.get("file") for m in root.iter("mesh")}
    farben = {m.get("name"): floats(m.get("rgba"), "0.6 0.6 0.6 1")[:3] for m in root.iter("material")}
    meshes: dict[str, tuple] = {}

    def mesh_index(name: str) -> int:
        if name not in meshes:
            meshes[name] = prepare(load_stl(meshdir / files[name]))
        return list(meshes).index(name)

    bodies: list[dict] = []
    parts: list[dict] = []

    def walk(body: ET.Element, parent: int) -> None:
        index = len(bodies)
        entry: dict[str, Any] = {"name": body.get("name"), "parent": parent,
                                 "pos": floats(body.get("pos"), "0 0 0"), "quat": floats(body.get("quat"), "1 0 0 0")}
        joint = body.find("joint")
        if joint is not None:
            entry.update({"joint": joint.get("name"), "axis": floats(joint.get("axis"), "0 0 1"),
                          "range": floats(joint.get("range"), "0 0")})
        for site in body.findall("site"):
            entry.setdefault("sites", {})[site.get("name")] = floats(site.get("pos"), "0 0 0")
        bodies.append(entry)
        for geom in body.findall("geom"):
            if geom.get("class") != "visual" or geom.get("type") != "mesh":
                continue
            name = geom.get("mesh")
            parts.append({"mesh": mesh_index(name), "name": name, "finish": FINISH.get(name, "plastic"),
                          "body": index, "pos": floats(geom.get("pos"), "0 0 0"),
                          "quat": floats(geom.get("quat"), "1 0 0 0"),
                          "rgb": [round(c, 4) for c in farben.get(geom.get("material"), [0.6, 0.6, 0.6])]})
        for child in body.findall("body"):
            walk(child, index)

    for top in root.find("worldbody").findall("body"):
        walk(top, -1)
    gefunden = [b["joint"] for b in bodies if b.get("joint")]
    if gefunden != GELENKE:
        raise ValueError(f"Gelenke im Modell weichen ab: {gefunden}")

    pos_blobs, nrm_blobs, idx_blobs, mesh_meta = [], [], [], []
    v_off = i_off = 0
    for name, (verts, nrm, faces) in meshes.items():
        if len(verts) > 65535:
            raise ValueError(f"{name}: zu viele Ecken für uint16 ({len(verts)})")
        lo = verts.min(axis=0)
        step = np.maximum(verts.max(axis=0) - lo, 1e-9) / 65535.0
        pos_blobs.append(np.clip(np.round((verts - lo) / step), 0, 65535).astype("<u2").tobytes())
        nrm_blobs.append(nrm.astype("i1").tobytes())
        idx_blobs.append(faces.astype("<u2").tobytes())
        mesh_meta.append({"name": name, "v": [v_off, len(verts)], "i": [i_off, faces.size],
                          "min": [round(float(x), 9) for x in lo], "step": [float(x) for x in step]})
        v_off += len(verts)
        i_off += faces.size
    head = {
        "format": 2, "art": "so101", "aufbereitung": AUFBEREITUNG,
        "source": {"repo": QUELLE["repo"], "commit": commit[:7], "mjcf": QUELLE["mjcf"]},
        "licence": "Apache-2.0 – SO-101, TheRobotStudio und Hugging Face",
        "units": "Meter, MJCF-Koordinaten (z oben, x vorn)",
        "joints": GELENKE, "poses": {"stand": {g: 0.0 for g in GELENKE}},
        "meshes": mesh_meta, "bodies": bodies, "parts": parts,
        "triangles": sum(m["i"][1] // 3 for m in mesh_meta),
    }
    blob = json.dumps(head, separators=(",", ":"), ensure_ascii=False).encode()
    out = bytearray(b"DPM2") + struct.pack("<I", len(blob)) + blob
    for block in (pos_blobs, nrm_blobs, idx_blobs):
        out += b"\0" * (-len(out) % 4)
        out += b"".join(block)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".teil")
    tmp.write_bytes(out)
    tmp.replace(dest)
    return {"kb": len(out) // 1024, "meshes": len(meshes), "koerper": len(bodies), "teile": len(parts),
            "dreiecke": head["triangles"]}
