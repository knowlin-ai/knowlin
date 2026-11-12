#!/usr/bin/env python3
"""Baut aus diesem Projekt die öffentliche Fassung für GitHub – in einen eigenen, leeren Ordner.

    python tools/export_public.py <ziel-ordner>

Was anders ist als in der privaten Fassung:
* **Pollens Modell fehlt** (`server/static/model/microduck.dpm`, `physics/microduck.xml`): Bearbeitungen der
  CC-BY-NC-SA-Meshes. duckpilot lädt die Originale beim ersten Start von GitHub (duckpilot/modell) und baut sie
  auf dem PC des Nutzers.
* **Eigene Bilder statt der KI-Kapitänsente**: Die App-Icons setzt `tools/make_public_art.py` aus dem Knowlin-Zeichen;
  `tools/assets/icon-quelle.png` bleibt privat.
* **Keine Arbeitsnotizen** (Gespraechsnotizen.md, Microduck-Notizen.md) und keine Caches.
* **CI** für GitHub Actions: ruff und pytest.

Zum Schluss sucht ein Geheimnis-Scan nach Schlüsseln, Tokens und persönlichen Pfaden. Findet er etwas, bricht
der Export mit Fehler ab – dann nichts veröffentlichen, sondern erst die Stelle bereinigen.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Pfade relativ zu ROOT, die nie mitgehen
PRIVAT = {
    "duckpilot/server/static/model/microduck.dpm",   # Bearbeitung von Pollens Meshes (CC BY-NC-SA)
    "duckpilot/server/static/model/reachy_mini.dpm", # dito für Reachy Mini (seit 0.38.2)
    "duckpilot/physics/microduck.xml",               # enthält die Hüllen der Meshes
    "tools/assets/icon-quelle.png",                  # KI-Bild der Kapitänsente
    "duckpilot/server/static/splash.jpg",            # dito – wird neu gezeichnet
    # knowlin-zeichen.png (aus Splash-Entwurf) geht seit 6.11.2026 mit – Wunsch als öffentliches Zeichen
    "duckpilot/server/static/figuren/microduck.png",  # Porträts aus Pollens Meshes (seit 0.38.4) – öffentlich
    "duckpilot/server/static/figuren/reachy-mini.png",  # zeigt die Startseite dafür die gezeichneten Umrisse
    "duckpilot.ico",
    "duckpilot/server/static/icon-192.png", "duckpilot/server/static/icon-512.png",
    "duckpilot/server/static/icon-maskable-512.png", "duckpilot/server/static/apple-touch-icon.png",
    "Gespraechsnotizen.md", "Microduck-Notizen.md",  # Arbeitsnotizen
    "Releaseplan.md", "ZWEIG.md",                    # private Planung und Testanleitung der Zweige
    "Konzept-Geist.md",                              # Konzept im Entwurf (seit 11.11.2026), erst nach Abstimmung öffentlich
    ".env",                                          # Schlüssel, falls jemand ihn so hinterlegt hat
    "tools/privat_namen.txt",
    "docs/befund-architektur-design.md",             # interner Prüfbericht                        # Namen aus Umfeld für den Scan – nie veröffentlichen
}
OHNE_ORDNER = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".venv", "venv", "node_modules", ".mypy_cache",
               ".claude", "build", "dist", "Archiv"}   # Bauergebnisse (pip wheel, Installer) – nie veröffentlichen                  # Arbeitsordner von Helfern (git-Worktrees) – nie veröffentlichen
OHNE_ENDUNG = {".pyc", ".pyo", ".teil", ".log"}

# Geheimnis-Scan: (Name, Muster). Bewusst streng – lieber einmal zu viel anhalten.
SCAN = [
    ("Anthropic-Schlüssel", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("Hugging-Face-Token", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("GitHub-Token", re.compile(r"\b(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}")),
    ("AWS-Schlüssel", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("privater Schlüssel", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Kaggle-Schlüssel", re.compile(r'"key"\s*:\s*"[0-9a-f]{32}"')),
    ("Windows-Benutzerpfad", re.compile(r"C:\\\\?Users\\\\?(?!<|%|\{|Name|you|du\b)[A-Za-z]", re.I)),
    # private Bezüge (Beruf des Maintainers) – zerlegt geschrieben, damit der Scan sich nicht selbst findet
    ("persönlicher Bezug", re.compile(r"\b(Neben" r"tätigkeit|Renten" r"versicherung|D" r"RV\b|Arbeit" r"geber)", re.I)),
    ("E-Mail-Adresse", re.compile(r"\b[\w.+-]+@(?!example\.|anthropic\.com|users\.noreply|knowlin\.de)[\w-]+\.(de|com|net|org)\b")),
]

def _private_namen() -> list[tuple[str, re.Pattern[str]]]:
    """Namen aus dem privaten Umfeld (Familie, Haushalt) – stehen bewusst nicht im öffentlichen Skript, sondern in
    `tools/privat_namen.txt` (ein Name pro Zeile, `#` für Kommentare), die selbst nie mitgeht."""
    datei = ROOT / "tools" / "privat_namen.txt"
    if not datei.exists():
        return []
    namen = [z.strip() for z in datei.read_text(encoding="utf-8").splitlines() if z.strip() and not z.startswith("#")]
    if not namen:
        return []
    return [("privater Name", re.compile(r"\b(" + "|".join(re.escape(n) for n in namen) + r")\b", re.I))]


SCAN += _private_namen()

# Bekannte, harmlose Treffer: Platzhalter in Tests (sk-ant-aus-…-000…), Autorenzeile in three.js
ERLAUBT = re.compile(r"sk-ant-aus-d\w\w-[a-z]+-(0+|1+)$|banksean@gmail\.com")
TEXT_ENDUNG = {".py", ".js", ".css", ".html", ".md", ".toml", ".txt", ".json", ".yml", ".yaml", ".bat", ".sh", ".xml",
               ".webmanifest", ".cfg", ".ini"}

# GitHub-Dateien (Prüfung, DCO, CodeQL, Dependabot) liegen in tools/github/ und landen im Export unter .github/
GITHUB = Path(__file__).resolve().parent / "github"

GITIGNORE = """# Schlüssel nie einchecken
.env
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.venv/
*.egg-info/
duckpilot.toml
neustart.log*
.claude/
*.teil
build/
dist/
# Pollens Modelle (CC BY-NC-SA) werden auf dem PC gebaut und nie eingecheckt – die Open Duck (Apache-2.0) schon
duckpilot/server/static/model/microduck.dpm
duckpilot/server/static/model/reachy_mini.dpm
duckpilot/physics/microduck.xml
duckpilot/server/static/figuren/microduck.png
duckpilot/server/static/figuren/reachy-mini.png
"""


# Kein Klarname des Maintainers im öffentlichen Repo (Wunsch beim Launch, 8.11.): Bezüge in Kommentaren, Änderungs-
# protokoll und Beispielen werden beim Export neutral – „…s Hinweis“ → „Hinweis“, Beispielnamen → Alex. Die Namen selbst
# stehen in tools/privat_namen.txt; der Scan unten bricht ab, falls doch einer übrig bleibt.
def _anonym_regeln() -> list[tuple[re.Pattern[str], str]]:
    datei = ROOT / "tools" / "privat_namen.txt"
    zeilen = datei.read_text(encoding="utf-8").splitlines() if datei.exists() else []
    vorname = next((z.split(":", 1)[1].strip() for z in zeilen if z.startswith("#maintainer:")), "")
    if not vorname:
        return []
    v = re.escape(vorname)
    return [
        (re.compile(rf"© (\d{{4}}) {v}\b"), r"© \1 The Knowlin Authors"),
        (re.compile(rf"\b{v}s\s+"), ""),
        (re.compile(rf"\({v}(?:,\s*|:\s*|\s+)"), "("),
        (re.compile(rf"\bvon {v}\b"), "des Maintainers"),
        (re.compile(rf"\b{v}\b"), "Alex"),
        (re.compile(rf"\b{v.lower()}\b"), "alex"),
    ]


def anonymisieren(dest: Path) -> int:
    regeln = _anonym_regeln()
    n = 0
    for p in sorted(dest.rglob("*")) if regeln else []:
        if not p.is_file() or p.suffix not in TEXT_ENDUNG:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        neu = text
        for pat, ersatz in regeln:
            neu = pat.sub(ersatz, neu)
        if neu != text:
            p.write_text(neu, encoding="utf-8")
            n += 1
    return n


def roadmap() -> str:
    """Öffentliche Roadmap aus den Geplant-Kacheln (duckpilot/geplant.py) – ohne private Termine."""
    sys.path.insert(0, str(ROOT))
    from duckpilot.geplant import liste
    from duckpilot.i18n import ui_text

    zeilen = ["# Roadmap", "", "What comes next – the same list as the “planned” tiles in the app.",
              "Versions are a plan, not a promise.", "", "| Version | Feature | What it means |", "| --- | --- | --- |"]
    zeilen += [f"| {ui_text(g['version'], 'en')} | {ui_text(g['name'], 'en')} | {ui_text(g['kurz'], 'en')} |"
               for g in liste()]
    return "\n".join(zeilen) + "\n"


def files() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if p.is_dir() or any(part in OHNE_ORDNER or part.endswith(".egg-info") for part in rel.parts) or p.suffix in OHNE_ENDUNG:
            continue
        if rel.as_posix() in PRIVAT:
            continue
        out.append(rel)
    return out


def scan(dest: Path) -> list[str]:
    funde = []
    for p in sorted(dest.rglob("*")):
        if not p.is_file() or p.suffix not in TEXT_ENDUNG:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for name, pat in SCAN:
            for m in pat.finditer(text):
                if ERLAUBT.fullmatch(m.group(0)) or ERLAUBT.match(m.group(0)):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                funde.append(f"{p.relative_to(dest)}:{line}: {name} ({m.group(0)[:24]}…)")
    return funde


def main(dest: Path) -> None:
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"{dest} ist nicht leer – bitte einen neuen, leeren Ordner angeben.")
    if dest.resolve().is_relative_to(ROOT):
        raise SystemExit("Der Zielordner darf nicht im Projekt liegen.")
    n = 0
    for rel in files():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
        n += 1
    from make_public_art import main as art

    art(dest)
    shutil.copytree(GITHUB, dest / ".github", dirs_exist_ok=True)
    shutil.rmtree(dest / "tools" / "github", ignore_errors=True)        # steht schon unter .github/
    (dest / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (dest / "docs" / "ROADMAP.md").write_text(roadmap(), encoding="utf-8")
    for rel in PRIVAT:
        if rel.endswith((".dpm", ".xml", "icon-quelle.png", ".md")) and (dest / rel).exists():
            raise SystemExit(f"{rel} ist im Export gelandet – Abbruch")
    anonymisieren(dest)
    funde = scan(dest)
    if funde:
        print("Geheimnis-Scan hat angeschlagen – NICHT veröffentlichen:", *funde, sep="\n  ")
        raise SystemExit(1)
    print(f"Öffentliche Fassung in {dest}: {n} Dateien, Icons aus dem Knowlin-Zeichen, CI. Geheimnis-Scan: sauber.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]).expanduser())
