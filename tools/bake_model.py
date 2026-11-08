#!/usr/bin/env python3
"""Backt Pollens Microduck-Modell (MJCF + STL) von Hand in die DPM2-Datei für die 3D-Ansicht.

    python tools/bake_model.py <pfad>/microduck_rl/src/mjlab_microduck/robot/microduck [ziel.dpm]

Im Normalfall braucht es das nicht: duckpilot lädt Pollens Dateien beim ersten Start selbst von GitHub und
baut das Modell auf dem PC (duckpilot/modell). Das hier ist für die private Fassung mit fertigem Modell im
Paket und zum Vergleichen. Die eigentliche Arbeit steckt in duckpilot/modell/ansicht.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from duckpilot.modell.ansicht import bake

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    folder = Path(sys.argv[1]).expanduser()
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "model" / "microduck.dpm"
    commit = subprocess.run(["git", "-C", str(folder), "log", "-1", "--format=%H"], capture_output=True, text=True).stdout.strip()
    info = bake(folder, dest, commit)
    print(f"{dest}: {info['kb']} KB, {info['meshes']} Meshes, {info['koerper']} Körper, {info['teile']} Teile, "
          f"{info['dreiecke']} Dreiecke ({info['gezeichnet']} gezeichnet)")
