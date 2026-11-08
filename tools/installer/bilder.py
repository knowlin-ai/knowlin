"""Bilder für den Windows-Installer (seit 0.38.34, Frage: „Kann man den Installer optisch an die App anpassen?“).

Erzeugt aus dem Knowlin-Zeichen (duckpilot/server/static/knowlin-zeichen.png) die Seitenleiste und das kleine Bild oben
rechts im Design der App: dunkler Grund wie die 3D-Bühne und das Zeichen – sonst nichts.
Läuft beim Bau auf GitHub (installer.yml) vor Inno Setup; BMP, weil das jede Inno-Setup-6-Fassung liest.

    python tools/installer/bilder.py <zielordner>
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
ZEICHEN = ROOT / "duckpilot" / "server" / "static" / "knowlin-zeichen.png"
GRUND_OBEN, GRUND_UNTEN = (34, 36, 40), (24, 25, 28)      # --p-gray-80 → --p-gray-90


def _verlauf(b: int, h: int) -> Image.Image:
    bild = Image.new("RGB", (b, h))
    zeichnen = ImageDraw.Draw(bild)
    for y in range(h):
        t = y / max(1, h - 1)
        zeichnen.line([(0, y), (b, y)], fill=tuple(round(o + (u - o) * t) for o, u in zip(GRUND_OBEN, GRUND_UNTEN, strict=True)))
    return bild


def seitenleiste(b: int, h: int, zeichen: Image.Image) -> Image.Image:
    bild = _verlauf(b, h)
    groesse = round(b * 0.62)
    z = zeichen.resize((groesse, groesse), Image.LANCZOS)
    bild.paste(z, ((b - groesse) // 2, round(h * 0.30) - groesse // 2), z)
    return bild


def klein(s: int, zeichen: Image.Image) -> Image.Image:
    bild = Image.new("RGB", (s, s), GRUND_OBEN)
    rand = round(s * 0.1)
    z = zeichen.resize((s - 2 * rand, s - 2 * rand), Image.LANCZOS)
    bild.paste(z, (rand, rand), z)
    return bild


def main() -> None:
    ziel = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    ziel.mkdir(parents=True, exist_ok=True)
    zeichen = Image.open(ZEICHEN).convert("RGBA")
    for faktor, name in ((1, "100"), (1.5, "150"), (2, "200")):
        seitenleiste(round(164 * faktor), round(314 * faktor), zeichen).save(ziel / f"wizard-{name}.bmp")
        klein(round(55 * faktor), zeichen).save(ziel / f"wizard-klein-{name}.bmp")
    print("Installer-Bilder in", ziel)


if __name__ == "__main__":
    main()
