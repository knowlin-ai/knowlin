#!/usr/bin/env python3
"""Open Duck Mini v2 für die 3D-Ansicht backen (seit 0.38.4).

    git clone https://github.com/apirrone/Open_Duck_Mini && git -C Open_Duck_Mini checkout <QUELLE["commit"]>
    python tools/bake_open_duck.py Open_Duck_Mini

Schreibt duckpilot/server/static/model/open_duck_mini.dpm (Apache-2.0, darf mit duckpilot verteilt werden).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from duckpilot.modell.open_duck import QUELLE, bake  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    ziel = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "model" / "open_duck_mini.dpm"
    print(bake(Path(sys.argv[1]) / QUELLE["ordner"], ziel))
