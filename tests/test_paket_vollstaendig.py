"""Jede Datei aus dem Quellordner landet auch im Paket (pip, pipx, Windows-Installer).

Gemeldet nach 0.38.32: Pollens Emotionen fehlten im Installer – `motion/pollen_emotions.json` stand nicht in den
package-data, im Quellordner fiel das nie auf."""

import fnmatch
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAKET = ROOT / "duckpilot"


def test_alle_dateien_sind_package_data():
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    muster = cfg["tool"]["setuptools"]["package-data"]["duckpilot"]
    fehlt = []
    for p in PAKET.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts or p.suffix in (".py", ".pyc"):
            continue
        rel = p.relative_to(PAKET).as_posix()
        # setuptools-Muster: „*“ bleibt innerhalb eines Ordners
        if not any(fnmatch.fnmatch(rel, m) and rel.count("/") == m.count("/") for m in muster):
            fehlt.append(rel)
    assert not fehlt, f"Nicht im Paket (pyproject package-data ergänzen): {fehlt}"


def test_jeder_python_ordner_ist_ein_paket():
    ohne = [d.relative_to(ROOT).as_posix() for d in PAKET.rglob("*")
            if d.is_dir() and "__pycache__" not in d.parts and any(d.glob("*.py")) and not (d / "__init__.py").exists()]
    assert not ohne, f"Ordner mit Python-Dateien ohne __init__.py fehlen im Paket: {ohne}"
