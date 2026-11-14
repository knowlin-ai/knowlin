#!/usr/bin/env python3
"""Stack-chan für die 3D-Ansicht backen (seit 0.38.61): Gehäuse und Füße aus den offenen Gehäusedaten.

    git clone https://github.com/stack-chan/stack-chan && git -C stack-chan checkout <QUELLE["commit"]>
    python tools/bake_stackchan.py stack-chan

Schreibt duckpilot/server/static/model/stackchan.dpm (Apache-2.0, darf mit Knowlin verteilt werden).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from duckpilot.modell.stackchan import QUELLE, bake  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    ziel = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static" / "model" / "stackchan.dpm"
    print(bake(Path(sys.argv[1]) / QUELLE["ordner"], ziel))
