"""Banner der README und Vorschaubild der Website aus der aktuellen Startseite bauen.

Seit 0.38.56 (Fund des Maintainers: „die Website stimmt nicht mehr“ – das Vorschaubild zeigte noch drei Körper ohne
Ari und die alte Startseite). Vorher waren beide Bilder einmal von Hand gebaut; jetzt entstehen sie aus derselben
Aufnahme wie die Website (`website/bilder/start-en-1600.webp`, von `tools/website_bilder.py`) und der Liste der Körper
in `duckpilot/suite.py` – damit sie nicht wieder veralten.

    python tools/website_bilder.py <ordner> --nur start    # zuerst die Aufnahme der Startseite
    python tools/vorschau_bilder.py                         # dann docs/bilder/banner.png und website/bilder/vorschau.png
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AUFNAHME = ROOT / "website" / "bilder" / "start-en-1600.webp"
ZEICHEN = ROOT / "duckpilot" / "server" / "static" / "knowlin-zeichen.png"
SCHRIFT = ROOT / "website" / "schrift"
ZIELE = ((ROOT / "docs" / "bilder" / "banner.png", 1280, 640, 2), (ROOT / "website" / "bilder" / "vorschau.png", 1200, 630, 1))


def koerper() -> list[str]:
    """Die fertigen Körper in der Reihenfolge der Startseite (geplante wie der Mentor fehlen)."""
    from duckpilot.suite import KOERPER_MODUL, MODULE

    namen = {"duckpilot": "Microduck", "reachy-mini": "Reachy Mini", "open-duck-mini": "Open Duck Mini", "so101": "SO-101"}
    out = []
    for m in MODULE:
        mid, status = m[0], m[3]
        if status == "fertig" and mid in KOERPER_MODUL:
            out.append(namen.get(mid, m[1]))
    return out


def seite(breite: int, hoehe: int) -> str:
    chips = "".join(f'<span class="chip"><i></i>{n}</span>' for n in koerper())
    s = breite / 1280
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Plex; src: url("{(SCHRIFT / 'plex-400.woff2').as_uri()}"); font-weight: 400; }}
@font-face {{ font-family: Plex; src: url("{(SCHRIFT / 'plex-600.woff2').as_uri()}"); font-weight: 600; }}
html, body {{ margin: 0; width: {breite}px; height: {hoehe}px; overflow: hidden; }}
body {{ background: radial-gradient(ellipse at 75% 40%, #23262c 0%, #121417 55%, #0d0f12 100%); color: #f1f2f4;
  font-family: Plex, sans-serif; position: relative; }}
.links {{ position: absolute; left: {64 * s}px; top: 50%; transform: translateY(-50%); width: {500 * s}px; }}
.marke {{ display: flex; align-items: center; gap: {16 * s}px; font-weight: 600; font-size: {40 * s}px; letter-spacing: -0.01em; }}
.marke img {{ width: {62 * s}px; height: {62 * s}px; }}
h1 {{ font-weight: 400; font-size: {58 * s}px; line-height: 1.08; letter-spacing: -0.02em; margin: {38 * s}px 0 {24 * s}px; }}
p {{ color: #aab0ba; font-size: {19 * s}px; line-height: 1.5; margin: 0 0 {30 * s}px; }}
.chips {{ display: flex; flex-wrap: nowrap; gap: {8 * s}px; }}
.chip {{ border: 1px solid #3a3f47; border-radius: 999px; padding: {7 * s}px {12 * s}px; font-size: {14.5 * s}px; white-space: nowrap;
  display: inline-flex; align-items: center; gap: {9 * s}px; color: #f1f2f4; }}
.chip i {{ width: {7 * s}px; height: {7 * s}px; border-radius: 50%; background: #f6a94b; }}
.fenster {{ position: absolute; right: {48 * s}px; top: 50%; transform: translateY(-50%); width: {640 * s}px; border-radius: {12 * s}px;
  overflow: hidden; border: 1px solid #2a2e35; box-shadow: 0 {30 * s}px {80 * s}px rgba(0,0,0,.55); background: #171a1f; }}
.fenster img {{ display: block; width: 100%; }}
</style></head><body>
<div class="links">
  <div class="marke"><img src="{ZEICHEN.as_uri()}" alt="">Knowlin</div>
  <h1>One mind,<br>many bodies.</h1>
  <p>A self-learning companion that embodies small robots – virtual in the simulator today, in your real
  surroundings tomorrow.</p>
  <div class="chips">{chips}</div>
</div>
<div class="fenster"><img src="{AUFNAHME.as_uri()}" alt=""></div>
</body></html>"""


def main() -> int:
    from playwright.sync_api import sync_playwright

    if not AUFNAHME.exists():
        print(f"Fehlt: {AUFNAHME} – erst tools/website_bilder.py <ordner> --nur start")
        return 1
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        b = p.chromium.launch()
        for ziel, breite, hoehe, faktor in ZIELE:
            html = Path(tmp) / f"{ziel.stem}.html"
            html.write_text(seite(breite, hoehe), encoding="utf-8")
            page = b.new_page(viewport={"width": breite, "height": hoehe}, device_scale_factor=faktor)
            page.goto(html.as_uri())
            page.wait_for_function("() => document.fonts.ready.then(() => [...document.images].every((i) => i.complete))")
            page.screenshot(path=str(ziel))
            page.close()
            print(f"{ziel.relative_to(ROOT)} ({breite * faktor} × {hoehe * faktor})")
        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
