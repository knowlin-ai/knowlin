"""Die Oberfläche aus Teilen (Architektur-Etappe A2, seit 0.38.38).

Früher lag die ganze Oberfläche in einer `index.html` (≈ 196 KB) und einer `style.css` (≈ 202 KB) – jede Änderung an
einer Ansicht berührte die großen Sammeldateien, und Fehler zeigten sich an fremden Stellen. Jetzt:

* `static/index.html` ist das Gerüst. Eine Zeile `<!--#teil tricks-->` steht für `static/teile/tricks.html`.
* `static/bereiche/<name>.css` sind die Stile eines Bereichs; `index.html` bindet sie nach `style.css` ein.

`seite()` setzt die Seite zusammen (so liefert sie der Server aus), `stil()` liefert alle eigenen Stile in der
Reihenfolge, in der der Browser sie liest – beides auch für Tests und Werkzeuge.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).parent / "static"
TEIL = re.compile(r"^[ \t]*<!--#teil ([a-z0-9-]+)-->[ \t]*\n", re.M)
STIL_LINK = re.compile(r'<link rel="stylesheet" href="/static/([^"?]+)"')
GRENZE_KB = 40            # Ziel je Teil und je Bereichs-Stil


def teile() -> list[str]:
    """Namen der Teile in der Reihenfolge des Gerüsts."""
    return TEIL.findall((STATIC / "index.html").read_text(encoding="utf-8"))


def seite() -> str:
    """Die ganze Seite, wie der Browser sie bekommt."""
    geruest = (STATIC / "index.html").read_text(encoding="utf-8")

    def ein(m: re.Match[str]) -> str:
        datei = STATIC / "teile" / f"{m.group(1)}.html"
        if not datei.is_file():
            raise FileNotFoundError(f"Teil fehlt: teile/{m.group(1)}.html")
        text = datei.read_text(encoding="utf-8")
        return text if text.endswith("\n") else text + "\n"

    return TEIL.sub(ein, geruest)


def stil_dateien() -> list[str]:
    """Eigene Stildateien (ohne das Designsystem unter ds/) in der Reihenfolge der Einbindung."""
    return [p for p in STIL_LINK.findall((STATIC / "index.html").read_text(encoding="utf-8")) if not p.startswith("ds/")]


def stil() -> str:
    """Alle eigenen Stile hintereinander – wie der Browser sie nach dem Designsystem liest."""
    return "\n".join((STATIC / p).read_text(encoding="utf-8") for p in stil_dateien())
