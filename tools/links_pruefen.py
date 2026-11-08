"""Externe Links in Oberfläche, Website und Doku prüfen (seit 0.38.33).

Gemeldet nach 0.38.32: „Pollens App-Katalog ansehen“ führte auf eine 404-Seite. Läuft wöchentlich auf GitHub
(.github/workflows/links.yml) und von Hand: `python tools/links_pruefen.py`.

Fehler sind 404/410 und nicht auflösbare Adressen. 401/403/429 zählen nur als Hinweis – manche Seiten sperren
Prüfprogramme, sind für Menschen aber erreichbar.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUELLEN = ["duckpilot/server/static/*.js", "duckpilot/server/static/*.html", "website/*.html", "docs/*.md",
           "README.md", "README.en.md", "SECURITY.md", "CONTRIBUTING.md"]
LINK = re.compile(r"https://[A-Za-z0-9.-]+\.[a-z]{2,}(?:/[^\s\"'<>()`\\\]]*)?")
AUSLASSEN = re.compile(r"\$\{|\{\{|example\.(com|org)|localhost|127\.0\.0\.1|api\.github\.com|/api/|"
                       r"huggingface\.co/[^/]+/[^/]+/resolve/|releases/download/|fonts\.g|schema\.org|w3\.org")


def links() -> dict[str, list[str]]:
    gefunden: dict[str, list[str]] = {}
    for muster in QUELLEN:
        for datei in ROOT.glob(muster):
            for url in LINK.findall(datei.read_text(encoding="utf-8", errors="replace")):
                url = url.rstrip(".,;:!?“”»")
                if not AUSLASSEN.search(url):
                    gefunden.setdefault(url, []).append(datei.relative_to(ROOT).as_posix())
    return gefunden


def pruefen(url: str) -> tuple[str, int | str]:
    for methode in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=methode, headers={"User-Agent": "Knowlin-Linkpruefung"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:       # noqa: S310 – nur https
                return url, r.status
        except urllib.error.HTTPError as exc:
            if methode == "HEAD" and exc.code in (403, 405, 501):
                continue
            return url, exc.code
        except Exception as exc:  # noqa: BLE001
            return url, type(exc).__name__
    return url, "?"


def main() -> int:
    alle = links()
    with ThreadPoolExecutor(8) as pool:
        ergebnisse = list(pool.map(pruefen, sorted(alle)))
    kaputt = [(u, c) for u, c in ergebnisse if c in (404, 410) or isinstance(c, str)]
    hinweis = [(u, c) for u, c in ergebnisse if c in (401, 403, 429)]
    for u, c in hinweis:
        print(f"Hinweis {c}: {u}")
    for u, c in kaputt:
        print(f"KAPUTT {c}: {u}  ({', '.join(sorted(set(alle[u])))})")
    print(f"{len(ergebnisse)} Links geprüft, {len(kaputt)} kaputt, {len(hinweis)} nur Hinweis.")
    return 1 if kaputt else 0


if __name__ == "__main__":
    sys.exit(main())
