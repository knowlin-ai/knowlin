"""Pollens 3D-Modell von Reachy Mini (seit 0.38.2) – wie bei der Microduck nachgeladen, nicht mit duckpilot verteilt.

Pollens Repo `reachy_mini` steht unter Apache-2.0, die Hardware-Dateien (STL) unter Creative Commons BY-NC-SA
(© Pollen Robotics). duckpilot lädt genau die für die Ansicht gebrauchten Dateien von einem festen Stand (jede mit
Prüfsumme in `reachy_quellen.json`) – oder nimmt sie aus Pollens Python-Paket `reachy_mini`, wenn es auf diesem PC
installiert ist – und backt daraus im Datenordner `reachy_mini.dpm` (DPM2 wie bei der Ente, `ansicht.py`).

Der Kopf hängt bei Reachy Mini an einer Stewart-Plattform (sechs Motoren, sechs Stangen, geschlossene Kette). Die
Datei bringt deshalb neben Teilen und Körpern einen Abschnitt `kinematik` mit: wo jede Stange am Motorarm und am Kopf
ansetzt, wie lang sie ist, und wo Pollens Kopf-Bezugspunkt („head“) im Kopf liegt. Die Ansicht rechnet daraus die
Motorwinkel selbst (wie Pollens Kinematik: Kopflage in der Welt, Körperdrehung extra).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
QUELLEN = json.loads((HERE / "reachy_quellen.json").read_text(encoding="utf-8"))
REPO, COMMIT, ORDNER = QUELLEN["repo"], QUELLEN["commit"], QUELLEN["ordner"]
# Die STL liegen bei Pollen in Git LFS – raw.githubusercontent.com gäbe nur den Zeiger, media.… die Datei.
MEDIA = f"https://media.githubusercontent.com/media/{REPO}/{COMMIT}/{ORDNER}"
SEITE = f"https://github.com/{REPO}/tree/{COMMIT[:12]}/{ORDNER}"
LIZENZ = f"https://github.com/{REPO}/blob/{COMMIT[:12]}/README.md#license"
PACKAGED_VIEW = HERE.parent / "server" / "static" / "model" / "reachy_mini.dpm"
MAX_FILE = 4 * 1024 * 1024
KOPF_Z = 0.177            # Pollens head_z_offset: Kopflage (0,0,0) liegt 17,7 cm über dem Fuß

# Von außen nicht zu sehen (Schrauben, Stecker, Platine, Lautsprecher im Fuß) – spart gut ein Drittel der Dreiecke
HIDDEN = {"b3b_eh", "b3b_eh_1", "bts2_m2_6x8", "phs_1_7x20_5_dc10", "phs_1_7x20_5_dc10_1", "phs_1_7x20_5_dc10_2",
          "phs_1_7x20_5_dc10_3", "5w_speaker", "arducam", "pp01102_arducam_carter", "dc15_a01_led_cap2_dummy"}
FINISH = {"head_front_3dprint": "shell", "head_back_3dprint": "shell", "body_top_3dprint": "shell",
          "body_down_3dprint": "shell", "body_foot_3dprint": "dark", "body_turning_3dprint": "dark",
          "big_lens_d40": "glass", "small_lens_d30": "glass", "m12_fisheye_lens_1_8mm": "glass",
          "bearing_85x110x13": "metal", "stewart_link_rod": "metal", "stewart_link_ball": "metal",
          "stewart_link_ball__2": "metal", "antenna": "dark"}


def offline() -> bool:
    from . import offline as _off

    return _off()


def _fetch(url: str) -> bytes:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "duckpilot (Pollens Reachy-Mini-Modell)"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read(MAX_FILE + 1)


def lokales_paket() -> Path | None:
    """Pollens Paket `reachy_mini`, falls auf diesem PC installiert – dann muss nichts geladen werden."""
    try:
        spec = importlib.util.find_spec("reachy_mini")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    ordner = Path(list(spec.submodule_search_locations)[0]) / "descriptions" / "reachy_mini" / "mjcf"
    return ordner if (ordner / "reachy_mini.xml").exists() else None


class ReachyModellStore:
    def __init__(self, root: Path, fetch: Callable[[str], bytes] | None = None, packaged: bool = True,
                 paket: Callable[[], Path | None] | None = None) -> None:
        self.dir = root / "pollen-modell" / "reachy_mini"
        self.src = self.dir / "quelle"
        self.fetch = fetch or _fetch
        self.paket = paket or lokales_paket
        self.packaged = packaged
        self.job: dict[str, Any] = {}

    def view_path(self) -> Path | None:
        eigen = self.dir / "ansicht.dpm"
        if eigen.exists():
            return eigen
        return PACKAGED_VIEW if self.packaged and PACKAGED_VIEW.exists() else None

    def missing(self) -> bool:
        return (not offline() and self.view_path() is None) or self.veraltet()

    def veraltet(self) -> bool:
        """Selbst gebaut mit älterer Aufbereitung (seit 0.38.18 nach Fläche vereinfacht) – einmal neu backen."""
        from .ansicht import AUFBEREITUNG, aufbereitung

        eigen = self.dir / "ansicht.dpm"
        return eigen.exists() and aufbereitung(eigen) < AUFBEREITUNG

    def status(self) -> dict[str, Any]:
        p = self.view_path()
        try:
            when = (self.dir / "geladen.txt").read_text(encoding="utf-8").strip()
        except OSError:
            when = None
        return {"ansicht": None if p is None else ("paket" if p == PACKAGED_VIEW else "geladen"), "geladen": when,
                "quelle": SEITE, "repo": REPO, "stand": QUELLEN["stand"], "lizenz": LIZENZ, "job": self.job}

    def holen(self, progress: Callable[[str], None] | None = None) -> str:
        """Quelldateien bereitstellen: aus Pollens installiertem Paket (gleiche Prüfsummen) oder von GitHub."""
        paket = self.paket()
        todo = []
        for name, meta in QUELLEN["dateien"].items():
            ziel = self.src / name
            if not (ziel.exists() and ziel.stat().st_size == meta["bytes"]):
                todo.append((name, meta))
        woher = "schon da"
        for i, (name, meta) in enumerate(todo):
            data = None
            if paket is not None and (paket / name).exists():
                data = (paket / name).read_bytes()
                if hashlib.sha256(data).hexdigest() != meta["sha256"]:
                    data = None                       # anderer Stand installiert – dann doch den festen laden
                else:
                    woher = "aus Pollens installiertem Paket"
            if data is None:
                if offline():
                    raise RuntimeError("Offline-Modus (DUCKPILOT_OFFLINE) – Pollens Modell wird nicht geladen")
                if progress:
                    progress(f"lade Pollens Reachy-Mini-Modell von GitHub ({i + 1} von {len(todo)}) …")
                data = self.fetch(f"{MEDIA}/{name}")
                woher = "von GitHub"
                if len(data) > MAX_FILE or hashlib.sha256(data).hexdigest() != meta["sha256"]:
                    raise ValueError(f"{name}: Prüfsumme passt nicht – Laden abgebrochen")
            ziel = self.src / name
            ziel.parent.mkdir(parents=True, exist_ok=True)
            tmp = ziel.with_name(ziel.name + ".teil")
            tmp.write_bytes(data)
            tmp.replace(ziel)
        return woher

    def ensure(self, progress: Callable[[str], None] | None = None, force: bool = False) -> dict[str, Any]:
        if not force and (self.dir / "ansicht.dpm").exists() and not self.veraltet():
            return {}
        woher = self.holen(progress)
        if progress:
            progress("baue das 3D-Modell von Reachy Mini …")
        out = bake(self.src, self.dir / "ansicht.dpm", COMMIT)
        (self.dir / "geladen.txt").write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
        return {**out, "woher": woher}


# ── Backen ────────────────────────────────────────────────────────────────
def _mat(pos: list[float], quat: list[float]):
    import numpy as np

    w, x, y, z = quat
    n = (w * w + x * x + y * y + z * z) ** 0.5 or 1.0
    w, x, y, z = w / n, x / n, y / n, z / n
    m = np.eye(4)
    m[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                 [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                 [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    m[:3, 3] = pos
    return m


def bake(folder: Path, dest: Path, commit: str = "") -> dict[str, Any]:
    """Pollens Ordner `mjcf` (reachy_mini.xml, assets/*.stl) → DPM2-Datei mit Kinematik der Stewart-Plattform."""
    import numpy as np

    from .ansicht import AUFBEREITUNG, FLAECHE_JE_DREIECK_MM2, floats, load_stl, prepare

    root = ET.parse(folder / "reachy_mini.xml").getroot()
    mesh_dir = folder / root.find("compiler").get("meshdir", ".")
    # MuJoCo: ohne name heißt ein Mesh wie seine Datei (ohne Endung)
    files = {m.get("name") or Path(m.get("file")).stem: m.get("file") or f"{m.get('name')}.stl" for m in root.iter("mesh")}
    materials = {m.get("name"): floats(m.get("rgba"), "0.5 0.5 0.5 1")[:3] for m in root.iter("material")}
    meshes: dict[str, tuple] = {}

    def mesh_index(name: str, voll: bool = False) -> int:
        """voll: Teile von Körper und Kopf bleiben unvereinfacht – aus ihnen rechnet die Kinematik, ob der Kopf in den
        Körper taucht (Sicherheitsprüfung vor Befehlen an den echten Reachy); dort zählt jeder Zehntelmillimeter."""
        key = f"{name}#voll" if voll else name
        if key not in meshes:
            tris = load_stl(mesh_dir / files[name])
            # Antennen: die Feder ist fein gewickelt – dort deutlich dichter, sonst wird sie zum Strich
            meshes[key] = prepare(tris, len(tris) if voll else None,
                                  1e-9 if voll else 0.25 if "antenna" in name else FLAECHE_JE_DREIECK_MM2)
        return list(meshes).index(key)

    bodies: list[dict] = []
    parts: list[dict] = []
    welt: list[Any] = []                       # Lage jedes Körpers in der Welt bei Gelenken = 0 (CAD-Stand)
    sites: dict[str, tuple[int, list[float]]] = {}
    nach_name: dict[str, int] = {}

    def walk(body: ET.Element, parent: int) -> None:
        index = len(bodies)
        pos, quat = floats(body.get("pos"), "0 0 0"), floats(body.get("quat"), "1 0 0 0")
        welt.append((welt[parent] if parent >= 0 else np.eye(4)) @ _mat(pos, quat))
        entry: dict[str, Any] = {"name": body.get("name") or f"teil_{index}", "parent": parent, "pos": pos, "quat": quat}
        joint = body.find("joint")
        if joint is not None:
            entry["joint"] = joint.get("name")
            entry["type"] = joint.get("type", "hinge")
            entry["axis"] = floats(joint.get("axis"), "0 0 1")
            if joint.get("range"):
                entry["range"] = floats(joint.get("range"), "0 0")
        bodies.append(entry)
        nach_name[entry["name"]] = index
        for geom in body.findall("geom"):
            if geom.get("class") != "visual" or geom.get("type") != "mesh" or geom.get("mesh") in HIDDEN:
                continue
            name = geom.get("mesh")
            parts.append({"mesh": mesh_index(name, entry.get("joint") in ("yaw_body", "passive_7")), "name": name, "finish": FINISH.get(name, "plastic"), "body": index,
                          "rgb": [round(c, 4) for c in materials.get(geom.get("material"), [0.6, 0.6, 0.6])],
                          "pos": floats(geom.get("pos"), "0 0 0"), "quat": floats(geom.get("quat"), "1 0 0 0")})
        for site in body.findall("site"):
            if site.get("name"):
                sites[site.get("name")] = (index, floats(site.get("pos"), "0 0 0"))
        for child in body.findall("body"):
            walk(child, index)

    for top in root.find("worldbody").findall("body"):
        walk(top, -1)

    # Stewart-Plattform: Motor i (Gelenk stewart_i) → Stange (Kugelgelenk) → Ansatz am Kopf (xl_330)
    kopf = next(i for i, b in enumerate(bodies) if b.get("joint") == "passive_7")
    stangen = []
    for i in range(1, 7):
        horn = next(k for k, b in enumerate(bodies) if b.get("joint") == f"stewart_{i}")
        stange = next(k for k, b in enumerate(bodies) if b.get("joint") == f"passive_{i}")
        if i < 6:
            fern = sites[f"closing_{i}_1"][1]                 # Stangenende (im Stangenrahmen)
            anker = sites[f"closing_{i}_2"][1]                # Ansatz am Kopf (im Kopfrahmen)
        else:                                                  # Stange 6 trägt den Kopf: ihr Ende ist sein Ursprung
            fern, anker = bodies[kopf]["pos"], [0.0, 0.0, 0.0]
        a = welt[stange][:3, :3] @ np.array(fern) + welt[stange][:3, 3]
        b = welt[kopf][:3, :3] @ np.array(anker) + welt[kopf][:3, 3]
        if np.linalg.norm(a - b) > 1e-4:
            raise ValueError(f"Stange {i}: Kette im CAD-Stand nicht geschlossen ({np.linalg.norm(a - b) * 1000:.2f} mm)")
        stangen.append({"motor": f"stewart_{i}", "horn": horn, "stange": stange,
                        "fern": [round(float(x), 7) for x in fern], "anker": [round(float(x), 7) for x in anker],
                        "laenge": round(float(np.linalg.norm(fern)), 6)})
    site_kopf = sites["head"][1]
    site_quat = next(floats(s.get("quat"), "1 0 0 0") for s in root.iter("site") if s.get("name") == "head")
    kinematik = {
        "koerper": next(i for i, b in enumerate(bodies) if b.get("joint") == "yaw_body"),
        "kopf": kopf, "kopf_site": {"pos": site_kopf, "quat": site_quat}, "kopf_z": KOPF_Z, "stangen": stangen,
        "antennen": {"rechts": next(i for i, b in enumerate(bodies) if b.get("joint") == "right_antenna"),
                     "links": next(i for i, b in enumerate(bodies) if b.get("joint") == "left_antenna")},
        "kamera": sites.get("camera_optical", (kopf, [0, 0, 0]))[1],
    }

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
        "format": 2, "art": "reachy_mini", "aufbereitung": AUFBEREITUNG,
        "source": {"repo": REPO, "commit": commit[:7], "mjcf": "reachy_mini.xml"},
        "licence": "CC BY-NC-SA – Hardware-Dateien © Pollen Robotics, aufbereitet für duckpilot",
        "units": "Meter, MJCF-Koordinaten (z oben, x vorn)",
        "meshes": mesh_meta, "bodies": bodies, "parts": parts, "kinematik": kinematik,
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


def store() -> ReachyModellStore:
    from .. import settings as S

    return ReachyModellStore(S.settings_path().parent)
