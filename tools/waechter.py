"""Wächter vor jedem Push (seit 0.38.42): Seit Knowlin nur noch im öffentlichen Repo entsteht, prüft er das Repo selbst –
was früher der Export beim Kopieren erledigte.

    python tools/waechter.py

1. Keine privaten Namen – die Liste liegt nie im Repo, sondern in `~/.config/knowlin/privat_namen.txt` (oder der Datei aus
   `KNOWLIN_PRIVAT_NAMEN`), ein Name pro Zeile, `#` für Kommentare. Fehlt sie, schlägt der Wächter fehl.
2. Keine Schlüssel, Tokens, Benutzerpfade oder E-Mail-Adressen (Muster aus `tools/export_public.py`).
3. Keine Dateien, die nie öffentlich sein dürfen (Pollens Modelle und Porträts, private Bilder – `PRIVAT`).
Rückgabewert 0 und „sauber“ nur, wenn nichts gefunden wurde.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import export_public as E  # noqa: E402

STANDARD = Path.home() / ".config" / "knowlin" / "privat_namen.txt"
# Dateien, die den Wächter selbst beschreiben, dürfen die Muster nennen
AUSGENOMMEN = {"tools/waechter.py", "tools/export_public.py", "tests/test_waechter.py"}
# Diese privaten Dateien haben öffentlich eine eigene Fassung (tools/make_public_art.py zeichnet die Icons neu);
# „.env“ bleibt per .gitignore draußen
ERSETZT = {"duckpilot.ico", "duckpilot/server/static/icon-192.png", "duckpilot/server/static/icon-512.png",
           "duckpilot/server/static/icon-maskable-512.png", "duckpilot/server/static/apple-touch-icon.png", ".env"}


def namen_datei() -> Path:
    return Path(os.environ.get("KNOWLIN_PRIVAT_NAMEN") or STANDARD)


def namen_muster(datei: Path) -> re.Pattern[str] | None:
    namen = [z.strip() for z in datei.read_text(encoding="utf-8").splitlines() if z.strip() and not z.startswith("#")]
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in namen) + r")\b", re.I) if namen else None


def dateien(wurzel: Path) -> list[str]:
    r = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=wurzel, capture_output=True, text=True,
                       check=True)
    return sorted(d for d in r.stdout.splitlines() if (wurzel / d).is_file())


def pruefen(wurzel: Path, namen: re.Pattern[str] | None) -> list[str]:
    funde = [f"{d}: darf nie öffentlich sein" for d in sorted(E.PRIVAT - ERSETZT) if (wurzel / d).exists()]
    muster = [m for m in E.SCAN if m[0] != "privater Name"] + ([("privater Name", namen)] if namen else [])
    for d in dateien(wurzel):
        if d in AUSGENOMMEN or Path(d).suffix not in E.TEXT_ENDUNG:
            continue
        text = (wurzel / d).read_text(encoding="utf-8", errors="ignore")
        for name, pat in muster:
            for m in pat.finditer(text):
                if E.ERLAUBT.fullmatch(m.group(0)) or E.ERLAUBT.match(m.group(0)):
                    continue
                funde.append(f"{d}:{text.count(chr(10), 0, m.start()) + 1}: {name}")
    return funde


def main() -> int:
    datei = namen_datei()
    if not datei.exists():
        print(f"Namensliste fehlt: {datei} – aus Notion „Interne Dokumentation → Private Namen“ anlegen")
        return 1
    funde = pruefen(ROOT, namen_muster(datei))
    for f in funde[:40]:
        print(f)
    print(f"{len(funde)} Funde" if funde else "sauber")
    return 1 if funde else 0


if __name__ == "__main__":
    raise SystemExit(main())
