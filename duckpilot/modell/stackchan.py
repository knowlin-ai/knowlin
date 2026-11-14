"""3D-Modell von Stack-chan (seit 0.38.61) – Gehäuse und Füße aus dem offenen Projekt der Stack-chan-Community.

Quelle: `github.com/stack-chan/stack-chan`, Ordner `case/case_SG90` (Gehäuse für SG90-Servos, die verbreitetste
Bauart), fester Stand `QUELLE["commit"]`. Das ganze Repo steht unter Apache-2.0, die Gehäusedaten eingeschlossen – das
gebackene Modell darf deshalb mit Knowlin verteilt werden (Hinweis in `server/static/model/LIZENZ-stackchan.md`), wie
beim SO-101. Der M5Stack-Kasten mit dem Bildschirm vorn gehört nicht zu den Gehäusedaten (ein Gerät von M5Stack); den
zeichnet `static/stackchan3d.js` selbst, ebenso das Gesicht.

Aufbau (wie auf den Fotos im Ordner `case/docs`): Die Füße stehen fest, darüber dreht sich der ganze Kopf – Schale und
M5Stack – um die Hochachse (Servo in den Füßen), und er nickt um die Querachse (Servo seitlich in der Schale).
Koordinaten der STL-Dateien: Millimeter, x quer, y nach hinten (vorn = −y), z oben. Gebacken wird in MJCF-Konvention
(Meter, x vorn, y links, z oben), je Teil schon in seinem Rahmen:

- `fuss`: Ursprung = Drehachse (Mitte der Füße), Boden bei z = 0.
- `schale`: Ursprung = Kopfgelenk (Hochachse durch die Mitte der Schale, Nickachse durch das Lager an der Seite).

Neu backen: `python tools/bake_stackchan.py <Klon von stack-chan>`.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

QUELLE = {"repo": "stack-chan/stack-chan", "commit": "3a436a50e22863adf35f69a275f8d3ab05a81b1a",
          "ordner": "case/case_SG90", "lizenz": "Apache-2.0"}
TEILE = {"fuss": "feet_SG90.stl", "schale": "shell_SG90.stl"}
# Kopfgelenk in Koordinaten der Schale (mm): Hochachse durch die Bodenöffnung der Schale (y 5…21 → Mitte 13),
# Nickachse durch das Lager in der Seitenwand (z ≈ 3,5)
GELENK_SCHALE = (0.0, 13.0, 3.5)
FUSS_HOEHE = 8.0                       # Oberkante der Füße
SPALT = 2.0                            # Servohorn zwischen Füßen und Schale
SCHALE_UNTEN = -27.0                   # Unterkante der Schale in ihren Koordinaten
# Höhe des Kopfgelenks über dem Boden (Meter) – stackchan3d.js nimmt denselben Wert (DREH_Y)
DREH_HOEHE = round((FUSS_HOEHE + SPALT - SCHALE_UNTEN + GELENK_SCHALE[2]) / 1000, 4)


def in_mjcf(tris, ursprung=(0.0, 0.0, 0.0)):
    """STL (mm; x quer, y hinten, z oben) → MJCF (m; x vorn, y links, z oben), verschoben auf `ursprung`."""
    import numpy as np

    t = np.asarray(tris, dtype=np.float64) - np.asarray(ursprung, dtype=np.float64)
    return np.stack([-t[..., 1], t[..., 0], t[..., 2]], axis=-1) / 1000.0


def bake(folder: Path, dest: Path, commit: str = QUELLE["commit"]) -> dict[str, Any]:
    import numpy as np

    from .ansicht import AUFBEREITUNG, load_stl, prepare

    meshes = {
        "fuss": prepare(in_mjcf(load_stl(folder / TEILE["fuss"]))),
        "schale": prepare(in_mjcf(load_stl(folder / TEILE["schale"]), GELENK_SCHALE)),
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
        "format": 2, "art": "stackchan", "aufbereitung": AUFBEREITUNG,
        "source": {"repo": QUELLE["repo"], "commit": commit[:7], "ordner": QUELLE["ordner"]},
        "licence": "Apache-2.0 – Stack-chan, Stack-chan-Community",
        "units": "Meter, MJCF-Koordinaten (z oben, x vorn)",
        "dreh_hoehe": DREH_HOEHE,
        "meshes": mesh_meta,
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
    return {"kb": len(out) // 1024, "meshes": len(meshes), "dreiecke": head["triangles"], "dreh_hoehe": DREH_HOEHE}
