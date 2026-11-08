"""Rauchtest für das gebaute Paket (seit 0.38.33): läuft in einer frischen Umgebung ohne Zusatzpakete, außerhalb des
Quellordners – so wie Knowlin nach dem Windows-Installer oder `pipx install knowlin` startet.

Gemeldet nach 0.38.32: Im Installer fehlten Pollens Emotionen (Datei nicht im Paket), und die Hugging-Face-Vorschläge
brauchten ein Paket, das dort nicht installiert ist. Im Quellordner mit allen Paketen fiel beides nie auf.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib import resources
from pathlib import Path


def main() -> int:
    import duckpilot

    ort = Path(duckpilot.__file__).resolve().parent
    fehler = []
    if (ort.parent / "pyproject.toml").exists():
        fehler.append(f"läuft aus dem Quellordner ({ort}) statt aus dem installierten Paket")
    basis = resources.files("duckpilot")
    for datei in ("server/static/index.html", "server/static/app.js", "server/static/vendor/three.module.min.js",
                  "server/static/vendor/jsm/shaders/FXAAShader.js", "i18n/ui_en.json", "motion/pollen_emotions.json"):
        if not (basis / datei).is_file():
            fehler.append(f"fehlt im Paket: {datei}")
    from duckpilot.motion import choreografie as C

    if not C._load_pollen():
        fehler.append("Pollens Emotionen lassen sich nicht laden")
    from duckpilot.physics import isaaclab_hf as HF

    if importlib.util.find_spec("huggingface_hub") is None and not isinstance(HF._hub()[0], HF.EigeneApi):
        fehler.append("Hugging Face geht ohne huggingface_hub nicht")
    from duckpilot.server.app import Runtime, create_app  # noqa: F401 – Oberfläche lässt sich aufbauen

    # Pflichtpakete wirklich da (httpx kam bis anthropic 1.x von selbst mit – lokales Modell, andere Anbieter)
    for modul in ("httpx", "anthropic", "fastapi", "uvicorn", "keyring", "numpy", "zeroconf"):
        if importlib.util.find_spec(modul) is None:
            fehler.append(f"Pflichtpaket fehlt: {modul}")

    for f in fehler:
        print("FEHLER:", f)
    print(f"Paket {duckpilot.__version__} aus {ort}: {'in Ordnung' if not fehler else f'{len(fehler)} Fehler'}")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
