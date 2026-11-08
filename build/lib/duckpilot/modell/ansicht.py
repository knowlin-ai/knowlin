"""Backt Pollens Microduck-Modell (MJCF + STL) in eine kompakte Datei für die 3D-Ansicht (DPM2).

Auflösung nach Fläche (ein Dreieck je 2,5 mm², seit 0.38.18 – vorher alle Dreiecke aus Pollens CAD-Export), dazu
fertige Normalen mit Kanten (Knickwinkel 35°). Namen, Gelenkgrenzen, Oberflächenart je Teil und die Posen STAND und SIT sind dabei.
Läuft beim ersten Start auf dem PC (siehe `duckpilot.modell`), oder von Hand über `tools/bake_model.py`.

Braucht numpy und fast-simplification (fürs Vereinfachen; fehlt es, bleibt die volle Auflösung).

Die Meshes stehen unter CC BY-NC-SA 4.0 (© Pollen Robotics). Das Ergebnis ist eine Bearbeitung davon und steht
unter derselben Lizenz – nicht kommerziell, Namensnennung. Es bleibt im Datenordner auf diesem PC.

Dateiformat DPM2 (little endian):
    "DPM2" | uint32 Länge des JSON-Kopfs | JSON (UTF-8) | Füllbytes bis 4er-Grenze
    | uint16 Positionen (je Mesh auf seinen Quader quantisiert: p = min + q · step)
    | int8 Normalen (×127) | uint16 Indizes          – jeder Block auf 4 Bytes aufgefüllt
Der JSON-Kopf nennt pro Mesh die Offsets (in Ecken bzw. Indizes), min und step.
"""

from __future__ import annotations

import json
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

JOINT_NAMES = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
]

# Teile, die von außen nicht zu sehen sind (Platinen, Halter) – wie bei Pollen weggelassen.
HIDDEN = {"pcb__raspberry_pi_zero_2_w", "elec_rpi_robot_hat_pcb", "power_support",
          "banana_pcb_locker", "motor_support", "speaker"}

# Farben, die der CAD-Export falsch hat. Der Akku ist schwarz.
RECOLOR = {"np_f970": (0.16, 0.16, 0.18)}

# Der Kiefer ist im Modell ein festes Teil; der Mund-Servo bewegt ihn. Wir hängen ihn an
# ein eigenes Gelenk, damit der Schnabel in der Ansicht auf- und zugeht.
JAW_MESHES = {"jaw", "jaw_soft"}
# Scharnier im Kopfrahmen (x oben, z nach hinten; der Schnabel zeigt nach -z).
JAW_HINGE = (-0.006, 0.0, -0.02)


def load_stl(path: Path) -> np.ndarray:
    data = path.read_bytes()
    (n,) = struct.unpack_from("<I", data, 80)
    if len(data) != 84 + n * 50:
        raise ValueError(f"{path.name}: kein binäres STL")
    rec = np.frombuffer(data, dtype=np.uint8, offset=84).reshape(n, 50)
    return rec[:, 12:48].copy().view("<f4").reshape(n, 3, 3)




def weld(tris: np.ndarray, eps: float = 1e-6) -> tuple[np.ndarray, np.ndarray]:
    flat = tris.reshape(-1, 3).astype(np.float64)
    keys = np.round(flat / eps).astype(np.int64)
    uniq, inverse = np.unique(keys, axis=0, return_inverse=True)
    verts = np.zeros((len(uniq), 3))
    np.add.at(verts, inverse, flat)
    verts /= np.bincount(inverse)[:, None]
    faces = inverse.reshape(-1, 3)
    keep = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    return verts, faces[keep]


def crease_normals(verts: np.ndarray, faces: np.ndarray, angle_deg: float = 35.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Normalen wie in einem CAD-Programm: über flache Rundungen weich, an Kanten hart.

    Für jede Ecke eines Dreiecks werden die Flächennormalen der Nachbardreiecke an dieser Ecke
    gemittelt – aber nur die, die weniger als `angle_deg` abweichen. Gewichtet nach dem Winkel an der Ecke (seit
    0.38.21): CAD-Exporte zerlegen Flächen in lange, dünne Fächer-Dreiecke; nach Fläche gewichtet zog ein großes
    Dreieck die Normale schief und Rundungen bekamen Schlieren („zerknittert“). Der Eckwinkel hängt nicht davon ab,
    wie die Fläche zerlegt ist (Thürrmer & Wüthrich).
    Ecken mit gleicher Position und gleicher Normale werden wieder zusammengelegt.
    """
    v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    length = np.linalg.norm(fn, axis=1, keepdims=True)
    fu = fn / np.maximum(length, 1e-20)
    def winkel(a, b, c):                      # Innenwinkel an a
        u, w = b - a, c - a
        cosw = np.einsum("ij,ij->i", u, w) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(w, axis=1), 1e-30)
        return np.arccos(np.clip(cosw, -1.0, 1.0))
    ecke = np.stack([winkel(v0, v1, v2), winkel(v1, v2, v0), winkel(v2, v0, v1)], axis=1).reshape(-1)
    corner_v = faces.reshape(-1)
    corner_f = np.repeat(np.arange(len(faces)), 3)
    corner_w = ecke
    order = np.argsort(corner_v, kind="stable")
    cv, cf, cw = corner_v[order], corner_f[order], corner_w[order]
    starts = np.flatnonzero(np.r_[True, cv[1:] != cv[:-1]])
    counts = np.diff(np.r_[starts, len(cv)])
    out = np.zeros((len(corner_v), 3))
    cos = np.cos(np.radians(angle_deg))
    for d in np.unique(counts):
        groups = starts[counts == d]
        for chunk in np.array_split(groups, max(1, int(len(groups) * d * d // 4_000_000) + 1)):
            idx = chunk[:, None] + np.arange(d)[None, :]
            fg = cf[idx]
            nu, na = fu[fg], fu[fg] * cw[idx][..., None]
            mask = (np.einsum("gik,gjk->gij", nu, nu) > cos).astype(np.float64)
            out[order[idx]] = np.einsum("gij,gjk->gik", mask, na)
    out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-20)
    q = np.clip(np.round(out * 127), -127, 127).astype(np.int8)
    key = np.c_[corner_v, q.astype(np.int64)]
    uniq, inverse = np.unique(key, axis=0, return_inverse=True)
    return verts[uniq[:, 0]], uniq[:, 1:4].astype(np.int8), inverse.reshape(-1, 3)


# Kleine, fast verdeckte Teile mit absurd vielen Dreiecken (je Kugellager 21 000 – vierzehnmal verbaut)
# werden behutsam vereinfacht; alles andere bleibt in voller Auflösung.
DECIMATE = {"seeed_bearing__configuration__22x16x4": 1400, "seeed_bearing__configuration_default": 1400,
            "pcb__raspberry_pi_zero_2_w": 3600, "elec_rpi_robot_hat_pcb": 3400}     # Platinen liegen innen


# Dreiecke nach Fläche (seit 0.38.18): Pollens CAD-Export hat bis zu 21 000 Dreiecke je Teil, auch für Stangen und
# Schrauben – zusammen bis 1,4 Mio. im Bild (mit Schatten doppelt). Ein Dreieck je 2,5 mm² Oberfläche sieht in der
# Ansicht gleich aus und braucht ein Viertel bis Fünftel. Ohne fast-simplification bleibt die volle Auflösung.
FLAECHE_JE_DREIECK_MM2 = 2.5
MIN_DREIECKE = 240
# Seit 0.38.21 wieder in voller Auflösung (Hinweis „die originalen sehen teilweise nicht gut aus“): Halterungen
# aus dem Druck wurden bis auf ein Achtel vereinfacht und wirkten zerknittert; selbst bei der Hälfte blieben Schlieren.
# Sichtbare Teile bleiben ganz – nur ungewöhnlich große (über 30 000 Dreiecke) werden auf die Hälfte gebracht, und
# Innenliegendes (DECIMATE) darf stärker. Leicht bleibt die Ansicht durch das Zusammenfassen je Gelenk und Material.
MIN_ANTEIL = 0.5
OHNE_UNTER = 30000
# Stand der Aufbereitung im Dateikopf: Ältere, selbst gebaute Dateien werden einmal neu gebacken (ohne neu zu laden)
AUFBEREITUNG = 4


def aufbereitung(pfad: Path) -> int:
    """Aufbereitung einer DPM-Datei (1 = alte, volle Auflösung; 0 = nicht lesbar)."""
    try:
        with open(pfad, "rb") as f:
            kopf = f.read(8)
            if kopf[:3] != b"DPM":
                return 0
            n = struct.unpack("<I", kopf[4:8])[0]
            return int(json.loads(f.read(n)).get("aufbereitung", 1))
    except (OSError, ValueError, struct.error):
        return 0


def budget_nach_flaeche(verts: np.ndarray, faces: np.ndarray, dichte: float = FLAECHE_JE_DREIECK_MM2) -> int:
    v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    flaeche_mm2 = float(np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1).sum()) / 2 * 1e6
    return max(MIN_DREIECKE, int(flaeche_mm2 / dichte))


def prepare(tris: np.ndarray, budget: int | None = None,
            dichte: float = FLAECHE_JE_DREIECK_MM2) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Verschweißen, nach Fläche vereinfachen (oder auf `budget`), nach außen ausrichten, Normalen mit Kanten.
    `dichte`: mm² je Dreieck – kleiner für gewölbte Schalen und feine Teile (Federn)."""
    verts, faces = weld(tris)
    if budget is None:                       # sichtbares Teil: behutsam (siehe MIN_ANTEIL, OHNE_UNTER)
        n = len(faces)
        budget = n if n < OHNE_UNTER else max(int(n * MIN_ANTEIL), budget_nach_flaeche(verts, faces, dichte))
    vereinfacht = False
    if budget and len(faces) > budget:
        try:
            import fast_simplification
        except ImportError:
            budget = None
    if budget and len(faces) > budget:

        verts, faces = fast_simplification.simplify(verts.astype(np.float32), faces.astype(np.int32),
                                                    target_reduction=1.0 - budget / len(faces))
        verts, faces = np.asarray(verts, dtype=np.float64), np.asarray(faces, dtype=np.int64)
        vereinfacht = True
    v0, v1, v2 = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    if np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() < 0:   # Volumen negativ: Teil steht innen nach außen
        faces = faces[:, ::-1].copy()
    # Vereinfachte Rundungen haben etwas gröbere Knicke – erst ab 42° als Kante zeichnen (bei 55° verschwammen Kanten)
    pos, nrm, faces = crease_normals(verts, faces, 42.0 if vereinfacht else 35.0)
    return pos.astype(np.float64), nrm, faces


# Oberfläche je Teil – entscheidet im Browser über das Material (glänzender Kunststoff, Gummi, Metall …)
FINISH = {
    "top_head_shell": "shell", "bottom_head_shell": "shell", "left_shell": "shell", "right_shell": "shell",
    "upper_leg_left": "shell", "upper_leg_right": "shell",
    "xl330": "servo", "trunk_base": "dark", "yaw2roll": "dark", "bearing_roll": "dark", "yaw_roll_motion": "dark",
    "motor_support": "dark", "np_f970": "dark", "neck_pitch": "dark",
    "sole_left": "rubber", "sole_right": "rubber", "jaw_soft": "soft", "soft_mouth_top": "soft",
    "seeed_bearing__configuration__22x16x4": "metal", "seeed_bearing__configuration_default": "metal",
    "lens": "glass", "m12_lens_holder": "dark",
}


def floats(text: str | None, default: str) -> list[float]:
    return [round(float(x), 7) for x in (text or default).split()]


def keyframe_pose(scene: Path, name: str, joint_order: list[str]) -> dict[str, float]:
    root = ET.parse(scene).getroot()
    for key in root.iter("key"):
        if key.get("name") == name:
            q = [float(x) for x in key.get("qpos").split()]
            return {j: round(v, 6) for j, v in zip(joint_order, q[7:])}
    raise ValueError(f"Pose {name} fehlt in {scene.name}")


def bake(folder: Path, dest: Path, commit: str = "") -> dict:
    """Pollens Roboter-Ordner (robot_walk.xml, scene.xml, assets/*.stl) → DPM2-Datei. Gibt Kennzahlen zurück."""
    mjcf = folder / "robot_walk.xml"
    root = ET.parse(mjcf).getroot()
    mesh_dir = mjcf.parent / root.find("compiler").get("meshdir", ".")
    materials = {m.get("name"): floats(m.get("rgba"), "0.5 0.5 0.5 1")[:3] for m in root.iter("material")}

    meshes: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    def mesh_index(name: str) -> int:
        if name not in meshes:
            # Die Microduck ist klein und rund: feiner als Reachy und Open Duck (Schalen am feinsten)
            meshes[name] = prepare(load_stl(mesh_dir / f"{name}.stl"), DECIMATE.get(name),
                                   0.6 if FINISH.get(name) == "shell" else 1.2)
        return list(meshes).index(name)

    bodies: list[dict] = []
    parts: list[dict] = []
    joint_order: list[str] = []

    def walk(body: ET.Element, parent: int) -> None:
        index = len(bodies)
        joint = body.find("joint")
        entry = {"name": body.get("name"), "parent": parent,
                 "pos": floats(body.get("pos"), "0 0 0"), "quat": floats(body.get("quat"), "1 0 0 0")}
        if joint is not None:
            entry["joint"] = joint.get("name")
            entry["axis"] = floats(joint.get("axis"), "0 0 1")
            entry["range"] = floats(joint.get("range"), "0 0")
            joint_order.append(joint.get("name"))
        bodies.append(entry)
        jaw_parts = []
        for geom in body.findall("geom"):
            if geom.get("class") != "visual" or geom.get("type") != "mesh":
                continue
            name = geom.get("mesh")
            if name in HIDDEN:
                continue
            part = {"mesh": mesh_index(name), "name": name, "finish": FINISH.get(name, "plastic"),
                    "rgb": [round(c, 4) for c in RECOLOR.get(name, materials[geom.get("material")])],
                    "pos": floats(geom.get("pos"), "0 0 0"), "quat": floats(geom.get("quat"), "1 0 0 0")}
            (jaw_parts if name in JAW_MESHES else parts).append({**part, "body": index})
        for site in body.findall("site"):
            if site.get("name") in ("mouth_tip", "tof", "head_camera", "left_foot", "right_foot"):
                entry.setdefault("sites", {})[site.get("name")] = floats(site.get("pos"), "0 0 0")
        if jaw_parts:
            # Eigener Körper für den Unterkiefer, Gelenk ungefähr am Schnabelansatz.
            jaw_index = len(bodies)
            bodies.append({"name": "jaw_hinge", "parent": index, "pos": list(JAW_HINGE), "quat": [1, 0, 0, 0],
                           "joint": "mouth", "axis": [0, 1, 0], "range": [0, 0.5]})
            for p in jaw_parts:
                rel = [round(a - b, 7) for a, b in zip(p["pos"], JAW_HINGE)]
                parts.append({**p, "pos": rel, "body": jaw_index})
        for child in body.findall("body"):
            walk(child, index)

    for top in root.find("worldbody").findall("body"):
        walk(top, -1)

    stand = keyframe_pose(folder / "scene.xml", "STAND", joint_order)
    sit = keyframe_pose(folder / "scene.xml", "SIT", joint_order)

    pos_blobs, nrm_blobs, idx_blobs, mesh_meta = [], [], [], []
    v_off = i_off = 0
    for name, (verts, nrm, faces) in meshes.items():
        if len(verts) > 65535:
            raise ValueError(f"{name}: zu viele Ecken für uint16 ({len(verts)})")
        lo = verts.min(axis=0)
        step = np.maximum(verts.max(axis=0) - lo, 1e-9) / 65535.0
        q = np.clip(np.round((verts - lo) / step), 0, 65535).astype("<u2")
        pos_blobs.append(q.tobytes())
        nrm_blobs.append(nrm.astype("i1").tobytes())
        idx_blobs.append(faces.astype("<u2").tobytes())
        mesh_meta.append({"name": name, "v": [v_off, len(verts)], "i": [i_off, faces.size],
                          "min": [round(float(x), 9) for x in lo], "step": [float(x) for x in step]})
        v_off += len(verts)
        i_off += faces.size

    head = {
        "format": 2, "aufbereitung": AUFBEREITUNG,
        "source": {"repo": "pollen-robotics/microduck_rl", "commit": commit[:7], "mjcf": "robot_walk.xml"},
        "licence": "CC BY-NC-SA 4.0 – Meshes © Pollen Robotics, vereinfacht für duckpilot",
        "units": "Meter, MJCF-Koordinaten (z oben, x vorn)",
        "joints": JOINT_NAMES,
        "poses": {"stand": stand, "sit": sit, "stand_z": 0.12, "sit_z": 0.07},
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
            "dreiecke": sum(m["i"][1] // 3 for m in mesh_meta),
            "gezeichnet": sum(mesh_meta[p["mesh"]]["i"][1] // 3 for p in parts)}
