"""Sammelt die sichtbaren deutschen Texte der Oberfläche für die Übersetzung (seit 0.34).

`python tools/i18n_texte.py` listet Texte aus `index.html` (Textknoten und title/aria-label/placeholder/alt) in den
übersetzten Bereichen und meldet, welche noch im Katalog `duckpilot/i18n/ui_en.json` fehlen. Der Test
`tests/test_i18n.py` nutzt dieselbe Funktion: In den übersetzten Bereichen darf nichts fehlen.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "duckpilot" / "server" / "static" / "index.html"
KATALOG = ROOT / "duckpilot" / "i18n" / "ui_en.json"

# Bereiche, die englisch sind (Element-ids bzw. Klassen): seit 0.34 Steuern & Co., seit 0.35 alles außer dem Designsystem.
BEREICHE_IDS = {"splash", "tasks", "update-bar", "quit-dialog", "quit-done", "stopp-fenster", "view-cockpit",
                "view-tricks", "view-settings", "ctl", "subnav",
                # seit 0.35: der Rest (das Designsystem bleibt eine deutsche Werkstattseite)
                "view-dashboard", "view-memory", "view-persoenlichkeit", "view-stimme", "view-training", "view-alltag",
                "view-akrobatik", "view-parcours", "alarm-bar", "wizard", "fehler-dialog",
                # seit 0.38: Knowlin-Seiten
                "view-start", "view-umgebung", "view-knowlets", "einzug"}
BEREICHE_KLASSEN = {"rail", "top", "skip-link"}
ATTRS = ("title", "aria-label", "placeholder", "alt")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# Texte ohne Übersetzung: Namen, Einheiten, Zahlen, Tasten
OHNE = re.compile(r"^(duckpilot|Claude|Knowlin|Quacki|Microduck|Pollen|Hugging Face|MuJoCo|BAM|MCP|Esc|Tab|WASD|"
                  r"Shift|Strg|Alt|Enter|Leertaste|[A-Z]|F\d*|\?|[–—·…×/+\-%°:.,()\[\]\d\s]+|[\d.,]+\s?(m|cm|s|ms|m/s|°|°/s|%|Hz|"
                  r"N|kg|rad/s|MB|GB|KB)?)$")


def normal(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


class _Sammler(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stapel: list[bool] = []
        self.nein: list[bool] = []          # translate="no": bleibt, wie es ist (Namen, Sprachwahl, Gesprächsverlauf)
        self.texte: list[str] = []
        self._skip = 0

    def _drin(self) -> bool:
        return any(self.stapel) and not any(self.nein)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        drin = a.get("id") in BEREICHE_IDS or bool(set((a.get("class") or "").split()) & BEREICHE_KLASSEN)
        if tag in ("script", "style"):
            self._skip += 1
        if (self._drin() or drin) and a.get("translate") != "no":
            for k in ATTRS:
                if a.get(k):
                    self.texte.append(normal(a[k]))
        if tag not in VOID:
            self.stapel.append(drin)
            self.nein.append(a.get("translate") == "no")

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        if self._drin():
            for k in ATTRS:
                if a.get(k):
                    self.texte.append(normal(a[k]))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        if tag not in VOID and self.stapel:
            self.stapel.pop()
            self.nein.pop()

    def handle_data(self, data):
        if self._skip or not self._drin():
            return
        s = normal(data)
        if s:
            self.texte.append(s)


def texte_html(pfad: Path | None = None) -> list[str]:
    p = _Sammler()
    if pfad is None:                       # die ganze Seite samt Teilen (seit 0.38.38, static/teile/)
        sys.path.insert(0, str(ROOT))
        from duckpilot.server.oberflaeche import seite

        p.feed(seite())
    else:
        p.feed(pfad.read_text(encoding="utf-8"))
    out: list[str] = []
    for s in p.texte:
        if re.search(r"[A-Za-zÄÖÜäöüß]{2,}", s) and not OHNE.match(s) and s not in out:
            out.append(s)
    return out


def katalog() -> dict[str, str]:
    if not KATALOG.exists():
        return {}
    return {k: v for k, v in json.loads(KATALOG.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def fehlend() -> list[str]:
    k = katalog()
    return [s for s in texte_html() if s not in k]


if __name__ == "__main__":
    f = fehlend()
    if "--json" in sys.argv:
        print(json.dumps({s: "" for s in f}, ensure_ascii=False, indent=1))
    else:
        print(f"{len(texte_html())} Texte, {len(f)} fehlen im Katalog")
        for s in f:
            print(" ", s)
