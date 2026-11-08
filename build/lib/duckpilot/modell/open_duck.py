"""3D-Modell der Open Duck Mini v2 (seit 0.38.4) – aus dem offenen Projekt von Antoine Pirrone und der Community.

Quelle: `github.com/apirrone/Open_Duck_Mini`, Ordner `mini_bdx/robots/open_duck_mini_v2` (robot.xml + STL), fester
Stand `QUELLE["commit"]`. Das Repo steht unter Apache-2.0 – anders als Pollens Teile darf das gebackene Modell deshalb
mit duckpilot verteilt werden (mit Hinweis in `server/static/model/LIZENZ-open-duck-mini.md`).

Gebacken wird wie bei der Microduck (DPM2, `ansicht.py`): volle Auflösung, Normalen mit Kanten, Gelenke mit Grenzen.
Die Gelenknamen sind fast dieselben wie bei der Microduck (Pirrone hat beide gebaut) – nur hat die Open Duck statt des
Schnabels zwei Antennen. Die Füße stehen als leere Körper `left_foot`/`right_foot` im Modell und werden zu Stellen,
damit die Ansicht sie auf den Boden stellt.

Die Kopfschale hat vorn zwei runde Öffnungen (Kamera und Auge). Im Modell sind sie leer, man sähe ins Innere der
Hülle; beim Backen setzt `augen()` deshalb dunkle Gläser hinein, etwas zurückgesetzt wie eine Linse.

Neu backen: `python tools/bake_open_duck.py <Klon von Open_Duck_Mini>`.
"""

from __future__ import annotations

import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

QUELLE = {"repo": "apirrone/Open_Duck_Mini", "commit": "b23317a485b3cec7d8417f352478778b3475173c",
          "ordner": "mini_bdx/robots/open_duck_mini_v2", "lizenz": "Apache-2.0"}

# Gleiche Reihenfolge wie bei der Microduck (display_joints des Simulators); „mouth“ gibt es hier nicht
JOINT_NAMES = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
]
# Innen liegende Teile (Elektronik, Akkuzellen) – von außen nicht zu sehen
HIDDEN = {"bms", "bno055", "board", "cell", "raspberrypizerow", "usb_c_charger", "power_switch",
          "wj-wk00-0122topcabinetcase_95", "wj-wk00-0123middlecase_56", "wj-wk00-0124bottomcase_45"}
FINISH = {"body_front": "shell", "body_back": "shell", "body_middle_top": "shell", "body_middle_bottom": "shell",
          "head": "shell", "trunk_top": "shell", "trunk_bottom": "shell", "foot_bottom_tpu": "rubber",
          "sg90": "servo", "roll_bearing": "metal", "antenna": "dark"}
# Umrechnung der Gelenkwinkel des Simulators (Konvention der Microduck, JOINT_NAMES) auf die Open Duck:
# ziel = stand_ziel + vorzeichen · (wert − stand_microduck). Stehen der Open Duck wie im offenen Training („home“).
STAND_MICRODUCK = [0.0, -0.0873, -0.4579, -0.0049, 0.4530, 0.3491, 0.3491, 0.0, 0.0, 0.0,
                   0.0, 0.0873, 0.4579, 0.0049, -0.4530]
STAND_ZIEL = [0.002, 0.053, -0.63, 1.368, -0.784, 0.0, 0.0, 0.0, 0.0, 0.0, -0.003, -0.065, 0.635, 1.379, -0.796]
VORZEICHEN = [1, -1, 1, 1, -1, 1, -1, 1, 1, 0, 1, -1, 1, -1, 1]   # Kopfnicken andersherum (nachgemessen)
STAND = {n: v for n, v in zip(JOINT_NAMES, STAND_ZIEL) if n != "mouth"}
AUGEN_IN = ("head",)              # Teile, deren große runde Durchbrüche ein dunkles Glas bekommen
AUGE_MIN_R = 0.004                # Schraubenlöcher (1 mm) bleiben offen
AUGE_RGB = [0.03, 0.03, 0.035]


def loecher(tris, min_r: float = AUGE_MIN_R) -> list[dict[str, Any]]:
    """Runde Durchbrüche durch eine Wand: auf zwei gegenüberliegenden ebenen Flächen je ein Kreis an derselben Stelle.
    Gibt Mitte (auf der Außenseite), Normale nach außen, Radius und Wandstärke zurück."""
    import numpy as np

    t = np.asarray(tris, dtype=np.float64)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
    d = (n * t[:, 0]).sum(1)
    gruppen: dict[tuple, list[int]] = {}
    for i, (ni, di) in enumerate(zip(np.round(n, 2), np.round(d, 4))):
        gruppen.setdefault((*ni.tolist(), float(di)), []).append(i)
    kreise = []
    for key, idx in gruppen.items():
        if len(idx) < 16:
            continue
        rand: dict[tuple, int] = {}
        for i in idx:
            for j in range(3):
                e = tuple(sorted((tuple(np.round(t[i, j], 6)), tuple(np.round(t[i, (j + 1) % 3], 6)))))
                rand[e] = rand.get(e, 0) + 1
        nachbarn: dict[tuple, list[tuple]] = {}
        for (a, b), c in rand.items():
            if c == 1:
                nachbarn.setdefault(a, []).append(b)
                nachbarn.setdefault(b, []).append(a)
        gesehen: set[tuple] = set()
        for start in nachbarn:
            if start in gesehen:
                continue
            ring, stapel = [], [start]
            while stapel:
                q = stapel.pop()
                if q not in gesehen:
                    gesehen.add(q)
                    ring.append(q)
                    stapel += nachbarn[q]
            P = np.array(ring)
            m = P.mean(0)
            r = np.linalg.norm(P - m, axis=1)
            if len(P) >= 12 and min_r <= r.mean() < 0.03 and r.std() < 0.05 * r.mean():
                kreise.append({"n": np.array(key[:3]), "m": m, "r": float(r.mean())})
    ecken = t.reshape(-1, 3)
    out = []
    for i, a in enumerate(kreise):                              # Paare: Außen- und Innenseite derselben Wand
        for b in kreise[i + 1:]:
            if a["n"] @ b["n"] < -0.99 and abs(a["r"] - b["r"]) < 0.0005:
                dicke = float(abs((a["m"] - b["m"]) @ a["n"]))
                quer = (a["m"] - b["m"]) - ((a["m"] - b["m"]) @ a["n"]) * a["n"]
                if not (0.0005 < dicke < 0.01 and np.linalg.norm(quer) < 0.001):
                    continue
                for aussen in (a, b):                           # nur Durchbrüche in der äußeren Hülle
                    if aussen["m"] @ aussen["n"] > (ecken @ aussen["n"]).max() - 0.002:
                        out.append({"mitte": aussen["m"], "normale": aussen["n"], "r": a["r"], "dicke": dicke})
    return out


def glas(loch: dict[str, Any], segmente: int = 32):
    """Geschlossene flache Scheibe im Durchbruch: innen bündig, außen 0,8 mm zurückgesetzt."""
    import numpy as np

    nn = loch["normale"] / np.linalg.norm(loch["normale"])
    u = np.cross(nn, [0.0, 0.0, 1.0] if abs(nn[2]) < 0.9 else [1.0, 0.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(nn, u)
    r = loch["r"] * 0.995
    vorn = loch["mitte"] - nn * 0.0008
    hinten = loch["mitte"] - nn * (loch["dicke"] + 0.0003)
    w = np.linspace(0, 2 * np.pi, segmente, endpoint=False)
    ring = [r * (np.cos(x) * u + np.sin(x) * v) for x in w]
    tris = []
    for k in range(segmente):
        a, b = ring[k], ring[(k + 1) % segmente]
        tris += [[vorn, vorn + a, vorn + b], [hinten, hinten + b, hinten + a],
                 [vorn + a, hinten + a, hinten + b], [vorn + a, hinten + b, vorn + b]]
    return np.array(tris)


def bake(folder: Path, dest: Path, commit: str = QUELLE["commit"]) -> dict[str, Any]:
    import numpy as np

    from .ansicht import AUFBEREITUNG, floats, load_stl, prepare

    root = ET.parse(folder / "robot.xml").getroot()
    files = {m.get("name") or Path(m.get("file")).stem: m.get("file") for m in root.iter("mesh")}
    meshes: dict[str, tuple] = {}

    def mesh_index(name: str) -> int:
        if name not in meshes:
            meshes[name] = prepare(load_stl(folder / files[name]))
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
        if body.get("name") in ("left_foot", "right_foot"):          # Füße als Stelle beim Elternkörper
            bodies[parent].setdefault("sites", {})[body.get("name")] = entry["pos"]
        bodies.append(entry)
        for geom in body.findall("geom"):
            name = geom.get("mesh")
            if geom.get("type") != "mesh" or name in HIDDEN:
                continue
            lage = {"body": index, "pos": floats(geom.get("pos"), "0 0 0"), "quat": floats(geom.get("quat"), "1 0 0 0")}
            parts.append({"mesh": mesh_index(name), "name": name, "finish": FINISH.get(name, "plastic"), **lage,
                          "rgb": [round(c, 4) for c in floats(geom.get("rgba"), "0.6 0.6 0.6 1")[:3]]})
            if name in AUGEN_IN:                                  # leere Augenöffnungen schließen (dunkles Glas)
                for k, loch in enumerate(loecher(load_stl(folder / files[name]))):
                    key = f"{name}_glas_{k}"
                    meshes[key] = prepare(glas(loch))
                    parts.append({"mesh": list(meshes).index(key), "name": key, "finish": "glass", **lage,
                                  "rgb": AUGE_RGB})
        for child in body.findall("body"):
            walk(child, index)

    for top in root.find("worldbody").findall("body"):
        walk(top, -1)
    # Die Wurzel „base“ steht im Modell 40 cm hoch – die Höhe setzt die Ansicht selbst (Füße auf den Boden)
    bodies[0]["pos"] = [0.0, 0.0, 0.0]

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
        "format": 2, "art": "open_duck_mini", "aufbereitung": AUFBEREITUNG,
        "source": {"repo": QUELLE["repo"], "commit": commit[:7], "mjcf": "robot.xml"},
        "licence": "Apache-2.0 – Open Duck Mini v2, Antoine Pirrone und Mitwirkende",
        "units": "Meter, MJCF-Koordinaten (z oben, x vorn)",
        "joints": JOINT_NAMES, "antennen": ["right_antenna", "left_antenna"],
        "poses": {"stand": STAND},
        "von_microduck": {"stand": STAND_MICRODUCK, "ziel": STAND_ZIEL, "vorzeichen": VORZEICHEN},
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
