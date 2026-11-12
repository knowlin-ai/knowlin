"""Schreibt `duckpilot/arm_huelle.py`: Fühlpunkte auf dem Greifer des SO-101, aus dem gebackenen Modell.

Der Planer an der Werkbank prüft damit, ob Backen oder Greifer auf dem Weg einen Würfel oder eine Kiste träfen (seit
0.38.55, Maintainer: „der Greifer ragt in den Turm“). Das Modell ist von TheRobotStudio (Apache-2.0) und liegt in
`duckpilot/server/static/model/so101.dpm`. Die Punkte liegen auf den Oberflächen (Dreiecke abgetastet, dann auf ein
Gitter von 8 mm ausgedünnt) – fest am Greifer nur der untere Teil (Backe, Finger), die bewegliche Backe ganz.

    python tools/arm_huelle_erzeugen.py          # schreibt die Datei neu
    python tools/arm_huelle_erzeugen.py --pruefen  # nur vergleichen (Exit 1, wenn sie nicht passt)
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from duckpilot.arm_kinematik import _rot  # noqa: E402

MODELL = ROOT / "duckpilot" / "server" / "static" / "model" / "so101.dpm"
ZIEL = ROOT / "duckpilot" / "arm_huelle.py"
GITTER = 0.008               # m zwischen zwei Fühlpunkten (ein Würfel hat 30 mm – keiner rutscht durch)
UNTERER_TEIL = -0.045        # m im Rahmen des Greifers: darunter Backe und Finger, darüber der Motor (weit oben)


def _lesen() -> tuple[dict, np.ndarray, np.ndarray]:
    b = MODELL.read_bytes()
    n = struct.unpack("<I", b[4:8])[0]
    head = json.loads(b[8:8 + n])
    off = 8 + n
    off += (4 - off % 4) % 4
    nv = sum(m["v"][1] for m in head["meshes"])
    ni = sum(m["i"][1] for m in head["meshes"])
    q = np.frombuffer(b, dtype="<u2", count=nv * 3, offset=off).reshape(-1, 3).astype(float)
    off += nv * 6
    off += (4 - off % 4) % 4
    off += nv * 3                                                        # Normalen (int8)
    off += (4 - off % 4) % 4
    idx = np.frombuffer(b, dtype="<u2", count=ni, offset=off)
    return head, q, idx


def _flaeche(head: dict, q: np.ndarray, idx: np.ndarray, koerper: int) -> np.ndarray:
    """Punkte auf allen Dreiecken der Teile dieses Körpers, im Rahmen des Körpers."""
    out = []
    for p in head["parts"]:
        if p["body"] != koerper:
            continue
        m = head["meshes"][p["mesh"]]
        v0, nvm = m["v"]
        i0, nim = m["i"]
        v = np.array(m["min"]) + q[v0:v0 + nvm] * np.array(m["step"])
        v = v @ _rot(p["quat"]).T + np.array(p["pos"])
        tri = v[idx[i0:i0 + nim].reshape(-1, 3)]
        out.append(v)
        for a in np.linspace(0, 1, 5):                                   # Raster auf jedem Dreieck
            for c in np.linspace(0, 1 - a, max(1, int((1 - a) * 4) + 1)):
                out.append(tri[:, 0] * (1 - a - c) + tri[:, 1] * a + tri[:, 2] * c)
    return np.vstack(out)


def _ausduennen(p: np.ndarray) -> np.ndarray:
    k = np.round(p / GITTER).astype(int)
    _, i = np.unique(k, axis=0, return_index=True)
    return p[np.sort(i)]


def punkte() -> tuple[list[list[int]], list[list[int]], dict]:
    head, q, idx = _lesen()
    namen = [b["name"] for b in head["bodies"]]
    greifer, backe = namen.index("gripper"), namen.index("moving_jaw_so101_v1")
    fest = _flaeche(head, q, idx, greifer)
    fest = _ausduennen(fest[fest[:, 2] < UNTERER_TEIL])
    beweglich = _ausduennen(_flaeche(head, q, idx, backe))
    mm = lambda a: [[round(float(x) * 1000, 1) for x in r] for r in a]   # noqa: E731
    return mm(fest), mm(beweglich), head["bodies"][backe]


def text() -> str:
    fest, backe, b = punkte()
    zeilen = lambda a: "\n".join(f"    {tuple(p)}," for p in a)            # noqa: E731
    return f'''"""Fühlpunkte auf dem Greifer des SO-101 (seit 0.38.55) – erzeugt von `tools/arm_huelle_erzeugen.py`, nicht von Hand.

Aus dem Modell von TheRobotStudio (Apache-2.0): Punkte auf den Oberflächen, 8 mm Gitter, in Millimetern. `FEST` im
Rahmen des Greifers (nur Backe und Finger unten), `BACKE` im Rahmen der beweglichen Backe. `huelle(gelenke)` gibt alle
Punkte im Rahmen des Sockels – damit prüft der Planer an der Werkbank, ob der Greifer auf dem Weg etwas träfe.
Diese Datei gehört zur Basis und importiert nichts aus Knowlin außer der Kinematik.
"""

from __future__ import annotations

import math

import numpy as np

from .arm_kinematik import _rot, _rz, rahmen

# bewegliche Backe am Greifer: Lage, Drehung (w x y z), Gelenk „gripper“ um z
BACKE_LAGE = {tuple(b["pos"])}
BACKE_DREHUNG = {tuple(b["quat"])}

FEST = np.array([
{zeilen(fest)}
]) / 1000.0

BACKE = np.array([
{zeilen(backe)}
]) / 1000.0

_RB = _rot(BACKE_DREHUNG)
_PB = np.array(BACKE_LAGE)


def huelle(gelenke: dict[str, float]) -> np.ndarray:
    """Alle Fühlpunkte (n × 3, Meter) im Rahmen des Sockels für diese Gelenkwinkel (Grad)."""
    p, R = rahmen(gelenke)
    Rb = R @ _RB @ _rz(math.radians(float(gelenke.get("gripper", 0.0))))
    return np.vstack([FEST @ R.T + p, BACKE @ Rb.T + p + R @ _PB])
'''


def main() -> int:
    neu = text()
    if "--pruefen" in sys.argv:
        gleich = ZIEL.exists() and ZIEL.read_text(encoding="utf-8") == neu
        print("arm_huelle.py passt zum Modell" if gleich else "arm_huelle.py passt nicht zum Modell – neu erzeugen")
        return 0 if gleich else 1
    ZIEL.write_text(neu, encoding="utf-8")
    print(f"{ZIEL.relative_to(ROOT)} geschrieben")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
