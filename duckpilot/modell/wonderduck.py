"""3D-Modell der WonderDuck von Hiwonder (seit 0.53) – wie Pollens Modelle nachgeladen, nicht mit Knowlin verteilt.

Hiwonders WonderDuck baut auf Pollens Microduck auf (github.com/Hiwonder/wonderduck, Apache-2.0): dieselben 15 Gelenke
mit denselben Namen, dieselbe robotd-Schnittstelle (Protokoll 62). Das 3D-Modell liegt in Hiwonders Studio als GLB
(`github.com/Hiwonder/wonderduck_studio`, fester Stand, Prüfsumme in `QUELLE`) und steht unter CC BY-NC-SA 4.0
(„Credit WonderDuck“). Knowlin lädt es beim ersten Wecken der WonderDuck in den Datenordner und backt daraus
`wonderduck.dpm` (DPM2 wie bei der Ente, `ansicht.py`) – das Ergebnis ist eine Bearbeitung und bleibt auf diesem PC.

Das GLB ist wie ein MJCF aufgebaut: `origin_<x>` (Lage im Elternkörper) → `joint_<g>` (Drehung um die Achse aus
Hiwonders `attitude-model.json`, im Modell in der Ruhelage) → `body_<x>` mit den sichtbaren Teilen. Die Ruhelage ergibt
die Pose STAND. Die Vorzeichen aller Gelenke stimmen mit der Microduck überein (verglichen am 26.11.: Hüfte, Knie,
Knöchel, Hals, Kopf); der Simulator rechnet in der Konvention der Microduck, `von_microduck` verschiebt nur die
Ruhelage. Das GLB hat 3,3 Mio. Dreiecke – gebacken wird nach Fläche auf einen Bruchteil davon.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import time
from pathlib import Path
from typing import Any, Callable

QUELLE = {
    "repo": "Hiwonder/wonderduck_studio", "commit": "531d4f86ad31b0d509cbe7bb22bb698af87888f2",
    "datei": "console/web/public/assets/imu-viewer-resources/robot-f3ce92c68e5f.glb",
    "sha256": "f3ce92c68e5fa551b47d1436f9b22fef70b9b4c08fa97f11d4cfd342f677fbeb", "bytes": 73695360,
    "lizenz": "CC BY-NC-SA 4.0 – WonderDuck robot 3D model, © Hiwonder",
}
RAW = f"https://raw.githubusercontent.com/{QUELLE['repo']}/{QUELLE['commit']}/{QUELLE['datei']}"
SEITE = f"https://github.com/{QUELLE['repo']}/tree/{QUELLE['commit'][:12]}"
LIZENZ = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
MAX_FILE = 96 * 1024 * 1024

JOINT_NAMES = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
]
# Achsen je Gelenk (im Gelenkrahmen), aus Hiwonders attitude-model.json (Stand wie QUELLE)
ACHSEN: dict[str, list[float]] = {
    "left_hip_yaw": [0, 0, -1], "left_hip_roll": [1, 0, 0], "left_hip_pitch": [0, 1, 0], "left_knee": [0, -1, 0],
    "left_ankle": [0, 1, 0], "right_hip_yaw": [0, 0, -1], "right_hip_roll": [1, 0, 0], "right_hip_pitch": [0, -1, 0],
    "right_knee": [0, 1, 0], "right_ankle": [0, -1, 0], "neck_pitch": [0, -1, 0], "head_pitch": [0, 1, 0],
    "head_yaw": [0, 0, 1], "head_roll": [-1, 0, 0], "mouth": [0, 1, 0],
}
# Stand der Microduck (Pollens Keyframe STAND, Reihenfolge JOINT_NAMES) – wie in open_duck.py
STAND_MICRODUCK = [0.0, -0.0873, -0.4579, -0.0049, 0.4530, 0.3491, 0.3491, 0.0, 0.0, 0.0,
                   0.0, 0.0873, 0.4579, 0.0049, -0.4530]
STELLEN = {"origin_left_foot": "left_foot", "origin_right_foot": "right_foot", "origin_camera": "head_camera",
           "origin_tof": "tof"}
FINISH = {"body_yellow": "shell", "body_deep_blue": "shell", "body_black": "dark"}
DICHTE_MM2 = 1.5                      # ein Dreieck je 1,5 mm² sichtbarer Fläche
# Kopf feiner (seit 0.55.1, Maintainer: „der Kopf wirkt unsauber“): Gesichtsrahmen, Kamera und Abstandssensor sitzen
# vorn und groß im Bild – mit 1,5 mm² wurden ihre Öffnungen zackig (Rahmen von 137 000 auf 2 400 Dreiecke).
DICHTE_KOPF_MM2 = 0.3
# Stand des Backens (seit 0.55.1): ältere Dateien lädt und backt Knowlin einmal neu (feinerer Kopf, Kamera-Blick)
# Stand 3 (0.56.1): große Kopfteile (gelbe Schale, Gesicht) nicht mehr auf 36 000 Dreiecke gekappt – die Öffnung des
# Abstandssensors oben war sonst zackig (Maintainer: „sieht auch nicht dolle aus“)
STAND = 3
MAX_DREIECKE_TEIL = 36000             # Indizes sind 16 Bit: höchstens 65 535 Ecken je Teil (mit Kanten-Normalen mehr Ecken)
MAX_DREIECKE_KOPF = 120000            # Kopfteile dürfen mehr – sie werden in Stücke zu höchstens STUECK Dreiecken geteilt
STUECK = 20000                        # 3 × 20 000 Ecken < 65 535: jedes Stück passt sicher in 16-Bit-Indizes


def _ist_kopf(name: str) -> bool:
    return name.startswith(("visual_p_head_", "visual_p_mouth_"))


def stuecke(pos, nrm, faces, n: int = STUECK) -> list[tuple]:
    """Ein fertig aufbereitetes Teil in Stücke zu höchstens `n` Dreiecken teilen – nach dem Berechnen der Normalen,
    damit an den Schnitten keine Lichtkante entsteht."""
    import numpy as np

    if len(faces) <= n:
        return [(pos, nrm, faces)]
    out = []
    for a in range(0, len(faces), n):
        f = faces[a:a + n]
        ecken, neu = np.unique(f.reshape(-1), return_inverse=True)
        out.append((pos[ecken], nrm[ecken], neu.reshape(-1, 3).astype(faces.dtype)))
    return out


def offline() -> bool:
    from . import offline as _off

    return _off()


def _fetch(url: str) -> bytes:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Knowlin (WonderDuck-Modell)"})
    with urllib.request.urlopen(req, timeout=180) as res:
        return res.read(MAX_FILE + 1)


# ── GLB lesen ─────────────────────────────────────────────────────────────
def lies_glb(data: bytes) -> tuple[dict[str, Any], bytes]:
    magic, version, _ = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        raise ValueError("kein glTF-2-Binärmodell")
    n, art = struct.unpack_from("<I4s", data, 12)
    if art != b"JSON":
        raise ValueError("GLB ohne JSON-Abschnitt")
    kopf = json.loads(data[20:20 + n])
    off = 20 + n
    m, art2 = struct.unpack_from("<I4s", data, off)
    if art2 != b"BIN\0":
        raise ValueError("GLB ohne Binärabschnitt")
    return kopf, data[off + 8:off + 8 + m]


def _accessor(kopf: dict[str, Any], binaer: bytes, i: int):
    import numpy as np

    a = kopf["accessors"][i]
    bv = kopf["bufferViews"][a["bufferView"]]
    typ = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}[a["componentType"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    groesse = np.dtype(typ).itemsize
    schritt = bv.get("byteStride") or groesse * n
    roh = np.frombuffer(binaer, dtype=np.uint8, count=schritt * (a["count"] - 1) + groesse * n, offset=start)
    werte = np.lib.stride_tricks.as_strided(roh, shape=(a["count"], groesse * n), strides=(schritt, 1)).copy()
    werte = werte.view(typ).reshape(a["count"], n)
    if a.get("normalized"):
        werte = werte.astype(np.float64) / float(np.iinfo(werte.dtype).max)
    return werte


def dreiecke(kopf: dict[str, Any], binaer: bytes, mesh: int):
    """Alle Dreiecke eines Meshes (n×3×3, Meter) je Material."""
    import numpy as np

    out: dict[int, list] = {}
    for p in kopf["meshes"][mesh]["primitives"]:
        if p.get("mode", 4) != 4:
            continue
        pos = _accessor(kopf, binaer, p["attributes"]["POSITION"]).astype(np.float64)
        idx = _accessor(kopf, binaer, p["indices"]).reshape(-1) if "indices" in p else np.arange(len(pos))
        out.setdefault(p.get("material", 0), []).append(pos[idx.reshape(-1, 3)])
    return {k: np.concatenate(v) for k, v in out.items()}


def _wxyz(q: list[float] | None) -> list[float]:
    x, y, z, w = q or (0.0, 0.0, 0.0, 1.0)
    return [round(w, 7), round(x, 7), round(y, 7), round(z, 7)]


def ruhewinkel(rotation: list[float] | None, achse: list[float]) -> float:
    """Winkel einer reinen Drehung um `achse` (glTF-Quaternion x, y, z, w)."""
    x, y, z, w = rotation or (0.0, 0.0, 0.0, 1.0)
    s = x * achse[0] + y * achse[1] + z * achse[2]
    return round(2.0 * math.atan2(s, w), 6)


# ── Backen ────────────────────────────────────────────────────────────────
def bake(glb: Path, dest: Path, commit: str = QUELLE["commit"]) -> dict[str, Any]:
    import numpy as np

    from .ansicht import AUFBEREITUNG, budget_nach_flaeche, prepare, weld

    kopf, binaer = lies_glb(glb.read_bytes())
    nodes = kopf["nodes"]
    nach_name = {n.get("name"): i for i, n in enumerate(nodes)}
    materialien = kopf.get("materials", [])
    meshes: dict[str, tuple] = {}
    bodies: list[dict[str, Any]] = []
    parts: list[dict[str, Any]] = []
    stand: dict[str, float] = {}

    def teile(body_node: int, index: int) -> None:
        for c in nodes[body_node].get("children", []):
            kind = nodes[c]
            if "mesh" in kind:
                for mat, tris in dreiecke(kopf, binaer, kind["mesh"]).items():
                    key = f"{kind.get('name')}_{mat}"
                    verts, faces = weld(tris)
                    kopfteil = _ist_kopf(kind.get("name") or "")
                    dichte = DICHTE_KOPF_MM2 if kopfteil else DICHTE_MM2
                    grenze = MAX_DREIECKE_KOPF if kopfteil else MAX_DREIECKE_TEIL
                    fertig = prepare(tris, min(len(faces), grenze, budget_nach_flaeche(verts, faces, dichte)))
                    m = materialien[mat] if mat < len(materialien) else {}
                    rgb = (m.get("pbrMetallicRoughness", {}).get("baseColorFactor") or [0.6, 0.6, 0.6])[:3]
                    for i, stueck in enumerate(stuecke(*fertig)):
                        name = key if i == 0 else f"{key}~{i}"
                        meshes[name] = stueck
                        parts.append({"mesh": list(meshes).index(name), "name": name, "body": index,
                                      "finish": FINISH.get(m.get("name"), "plastic"),
                                      "rgb": [round(v, 4) for v in rgb],
                                      "pos": [round(v, 7) for v in kind.get("translation", [0, 0, 0])],
                                      "quat": _wxyz(kind.get("rotation"))})
            elif (kind.get("name") or "").startswith("origin_"):
                ursprung(c, index)

    def ursprung(origin: int, parent: int) -> None:
        o = nodes[origin]
        name = o.get("name", "")
        kind = nodes[o["children"][0]] if o.get("children") else {}
        lage = {"pos": [round(v, 7) for v in o.get("translation", [0, 0, 0])], "quat": _wxyz(o.get("rotation"))}
        if (kind.get("name") or "").startswith("joint_"):
            gelenk = kind["name"].removeprefix("joint_")
            achse = ACHSEN[gelenk]
            stand[gelenk] = ruhewinkel(kind.get("rotation"), achse)
            index = len(bodies)
            bodies.append({"name": name.removeprefix("origin_"), "parent": parent, **lage, "joint": gelenk,
                           "axis": achse, "range": [-3.14, 3.14]})
            teile(kind["children"][0], index)
        elif name in STELLEN and parent >= 0:
            bodies[parent].setdefault("sites", {})[STELLEN[name]] = lage["pos"]
        elif name == "origin_trunk_base":
            index = len(bodies)
            bodies.append({"name": "trunk_base", "parent": -1, "pos": [0.0, 0.0, 0.0], "quat": [1, 0, 0, 0]})
            teile(o["children"][0], index)

    ursprung(nach_name["origin_trunk_base"], -1)
    fehlt = [g for g in JOINT_NAMES if g not in stand]
    if fehlt:
        raise ValueError(f"Gelenke fehlen im Modell: {', '.join(fehlt)}")

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
    ziel = [stand[g] for g in JOINT_NAMES]
    head = {
        "format": 2, "art": "wonderduck", "aufbereitung": AUFBEREITUNG, "wd_stand": STAND,
        "source": {"repo": QUELLE["repo"], "commit": commit[:7], "glb": Path(QUELLE["datei"]).name},
        "licence": "CC BY-NC-SA 4.0 – WonderDuck robot 3D model (Hiwonder), vereinfacht für Knowlin",
        "units": "Meter, MJCF-Koordinaten (z oben, x vorn)",
        "joints": JOINT_NAMES,
        "poses": {"stand": {g: stand[g] for g in JOINT_NAMES if g != "mouth"}},
        "kamera": {"blick": [1, 0, 0], "oben": [0, 0, 1]},       # Kopfkamera schaut im Kopfrahmen nach vorn (+x)
        "von_microduck": {"stand": STAND_MICRODUCK, "ziel": ziel, "vorzeichen": [1] * len(JOINT_NAMES)},
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


# ── Laden ─────────────────────────────────────────────────────────────────
class WonderduckModellStore:
    def __init__(self, root: Path, fetch: Callable[[str], bytes] | None = None) -> None:
        self.dir = root / "hiwonder-modell" / "wonderduck"
        self.fetch = fetch or _fetch
        self.job: dict[str, Any] = {}

    def view_path(self) -> Path | None:
        p = self.dir / "ansicht.dpm"
        return p if p.exists() else None

    def veraltet(self) -> bool:
        """Gebacken mit einem älteren Stand – bis das neue fertig ist, zeigt Knowlin das alte weiter."""
        p = self.view_path()
        if p is None:
            return False
        try:
            with open(p, "rb") as f:
                n = struct.unpack("<I", f.read(8)[4:8])[0]
                return int(json.loads(f.read(n)).get("wd_stand", 1)) < STAND
        except (OSError, ValueError, struct.error):
            return True

    def missing(self) -> bool:
        return not offline() and (self.view_path() is None or self.veraltet())

    def status(self) -> dict[str, Any]:
        try:
            when = (self.dir / "geladen.txt").read_text(encoding="utf-8").strip()
        except OSError:
            when = None
        return {"ansicht": "geladen" if self.view_path() else None, "geladen": when, "quelle": SEITE,
                "repo": QUELLE["repo"], "lizenz": LIZENZ, "job": self.job}

    def ensure(self, progress: Callable[[str], None] | None = None, force: bool = False) -> dict[str, Any]:
        if not force and self.view_path() is not None and not self.veraltet():
            return {}
        if offline():
            raise RuntimeError("Offline-Modus (DUCKPILOT_OFFLINE) – das WonderDuck-Modell wird nicht geladen")
        if progress:
            progress("lade Hiwonders WonderDuck-Modell von GitHub (etwa 70 MB) …")
        data = self.fetch(RAW)
        if len(data) > MAX_FILE or hashlib.sha256(data).hexdigest() != QUELLE["sha256"]:
            raise ValueError("WonderDuck-Modell: Prüfsumme passt nicht – Laden abgebrochen")
        glb = self.dir / "quelle.glb"
        glb.parent.mkdir(parents=True, exist_ok=True)
        tmp = glb.with_name("quelle.glb.teil")
        tmp.write_bytes(data)
        tmp.replace(glb)
        if progress:
            progress("baue das 3D-Modell der WonderDuck …")
        out = bake(glb, self.dir / "ansicht.dpm")
        glb.unlink(missing_ok=True)                # 70 MB Quelle nicht aufheben – gebacken ist es ein paar MB
        (self.dir / "geladen.txt").write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
        return out


def store() -> WonderduckModellStore:
    from .. import settings as S

    return WonderduckModellStore(S.settings_path().parent)
