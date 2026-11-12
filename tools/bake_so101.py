#!/usr/bin/env python3
"""SO-101 für die 3D-Ansicht backen (seit 0.38.47).

    git clone https://github.com/TheRobotStudio/SO-ARM100 && git -C SO-ARM100 checkout <QUELLE["commit"]>
    python tools/bake_so101.py SO-ARM100

Schreibt duckpilot/server/static/model/so101.dpm (Apache-2.0, darf mit duckpilot verteilt werden).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from duckpilot.modell.so101 import QUELLE, bake  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    ziel = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "model" / "so101.dpm"
    print(bake(Path(sys.argv[1]) / QUELLE["ordner"], ziel))
