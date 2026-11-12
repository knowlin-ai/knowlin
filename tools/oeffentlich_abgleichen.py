"""Öffentliche Fassung in den Klon übernehmen – ein Befehl statt vieler Einzelschritte (seit 0.38.41).

    python tools/oeffentlich_abgleichen.py <klon> [--export <ordner>]

Exportiert mit `tools/export_public.py` (samt Geheimnis-Scan), holt im Klon den Stand von GitHub (`git pull --ff-only`),
kopiert neue und geänderte Dateien hinein und nimmt Dateien, die es in der Fassung nicht mehr gibt, mit `git rm` heraus –
nur Dateien, die Git kennt, nie ganze Ordner. Zum Schluss steht `git add -A` und die Liste der Änderungen da; committen
und pushen bleibt ein eigener, bewusster Schritt.
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEG = ("__pycache__", ".egg-info", ".pytest_cache")


def _dateien(ordner: Path) -> set[str]:
    return {p.relative_to(ordner).as_posix() for p in ordner.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(ordner).parts and not any(w in p.as_posix() for w in WEG)}


def abgleichen(fassung: Path, klon: Path) -> tuple[list[str], list[str]]:
    """Kopiert neue/geänderte Dateien und entfernt verschwundene per `git rm`; gibt (geändert, entfernt) zurück."""
    neu, alt = _dateien(fassung), _dateien(klon)
    geaendert = sorted(d for d in neu if d not in alt or not filecmp.cmp(fassung / d, klon / d, shallow=False))
    for d in geaendert:
        (klon / d).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fassung / d, klon / d)
    bekannt = set(subprocess.run(["git", "ls-files"], cwd=klon, capture_output=True, text=True,
                                 check=True).stdout.splitlines())
    entfernt = sorted(d for d in alt - neu if d in bekannt)
    if entfernt:
        subprocess.run(["git", "rm", "-q", "--", *entfernt], cwd=klon, check=True)
    subprocess.run(["git", "add", "-A"], cwd=klon, check=True)
    return geaendert, entfernt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("klon")
    ap.add_argument("--export", help="Ordner für den Export (Standard: ein frischer Ordner im Temp-Verzeichnis)")
    a = ap.parse_args(argv)
    klon = Path(a.klon).resolve()
    fassung = Path(a.export).resolve() if a.export else Path(tempfile.mkdtemp(prefix="knowlin-export-")) / "fassung"
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "export_public.py"), str(fassung)], capture_output=True,
                       text=True)
    print((r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr).strip() else "")
    if r.returncode != 0 or "Geheimnis-Scan: sauber" not in r.stdout:
        print("Export nicht sauber – nichts übernommen")
        return 1
    subprocess.run(["git", "pull", "-q", "--ff-only"], cwd=klon, check=True)
    geaendert, entfernt = abgleichen(fassung, klon)
    print(f"{len(geaendert)} geändert/neu, {len(entfernt)} entfernt")
    for d in geaendert[:40]:
        print("  +", d)
    for d in entfernt[:40]:
        print("  -", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
