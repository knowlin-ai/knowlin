"""Gibt es PyTorch mit ROCm in den festen Fassungen für dieses Python? (seit 0.38.40, im Installer-Workflow)

Fragt nur die Liste der Fassungen in AMDs Paketquelle ab, ohne die Gigabytes zu laden. Fehlt eine Fassung, bliebe
Qwen3-TTS auf einer Radeon beim Prozessor – dann `AMD_TORCH`/`AMD_TORCHAUDIO` in duckpilot/voice/install.py anpassen.
"""

from __future__ import annotations

import subprocess
import sys

from duckpilot.voice import install as I


def main() -> int:
    fehlt = []
    for paket, fassung in (("torch", I.AMD_TORCH), ("torchaudio", I.AMD_TORCHAUDIO)):
        out = subprocess.run([sys.executable, "-m", "pip", "index", "versions", paket, "--index-url", I.AMD_INDEX],
                             capture_output=True, text=True, timeout=180)
        print(f"{paket}: {out.stdout.strip()[:300] or out.stderr.strip()[:300]}")
        if fassung not in out.stdout:
            fehlt.append(f"{paket}=={fassung}")
    if fehlt:
        print(f"Für Python {sys.version_info.major}.{sys.version_info.minor} nicht in {I.AMD_INDEX}: {', '.join(fehlt)}")
        return 1
    print("PyTorch mit ROCm: feste Fassungen vorhanden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
