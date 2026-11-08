#!/usr/bin/env python3
"""App-Icons aus einem Bild erzeugen (Kapitäns-Ente): transparent wie bisher, Handy-Kacheln im duckpilot-Design: Fenster/Verknüpfung (.ico), Browser, Handy-App.

    python tools/make_icons.py [tools/assets/icon-quelle.png]

Erzeugt duckpilot.ico (16–256 px), server/static/icon-192.png, icon-512.png, icon-maskable-512.png und
apple-touch-icon.png. Kleine Größen zeigen nur Kopf und Mütze, damit man auf 16 px noch etwas erkennt.
Braucht Pillow – nur beim Erzeugen, nie zur Laufzeit.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "duckpilot" / "server" / "static"
# duckpilot-Design (server/static/ds/tokens.css): Carbon Gray 90 als Fläche, Schnabel-Orange als Akzent
TOP, BOTTOM = (0x33, 0x33, 0x33), (0x16, 0x16, 0x16)   # gray-hover-90 → gray-100
BEAK = (0xF0, 0x96, 0x2C)                               # --p-beak-500
EDGE = (0x52, 0x52, 0x52)                               # gray-70: feine Kante wie bei den Karten
CROP_FULL = (130, 0, 1130, 1000)                   # Kopf, Mütze, Halstuch
CROP_HEAD = (175, 15, 1040, 880)                   # nur Kopf und Mütze (für 16–48 px)


def background(size: int, radius: float, edge: bool = True) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        k = y / max(1, size - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * k) for a, b in zip(TOP, BOTTOM)))
    bg = grad.resize((size, size)).convert("RGBA")
    # Schein in Schnabel-Orange hinter dem Kopf: hebt die dunkle Mütze vom dunklen Grund ab
    glow = Image.new("L", (size, size), 0)
    r = size * 0.36
    cx, cy = size * 0.52, size * 0.40
    ImageDraw.Draw(glow).ellipse((cx - r, cy - r, cx + r, cy + r), fill=150)
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.16))
    bg = Image.composite(Image.new("RGBA", (size, size), (*BEAK, 255)), bg, glow)
    if radius:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=round(radius * size), fill=255)
        bg.putalpha(mask)
        if edge and size >= 64:
            w = max(1, size // 128)
            ImageDraw.Draw(bg).rounded_rectangle((w // 2, w // 2, size - 1 - w // 2, size - 1 - w // 2),
                                                 radius=round(radius * size), outline=(*EDGE, 255), width=w)
    return bg


def tile(src: Image.Image, size: int, crop, scale: float = 0.94, radius: float = 0.22, plain: bool = False) -> Image.Image:
    """Figur auf einer Kachel – oder mit `plain` frei auf transparentem Grund (wie das bisherige Icon)."""
    fig = src.crop(crop)
    inner = round(size * scale)
    fig = fig.resize((inner, inner), Image.LANCZOS)
    out = Image.new("RGBA", (size, size)) if plain else background(size, radius)
    x = (size - inner) // 2
    y = (size - inner) // 2 if plain else size - inner   # Kachel: unten bündig, der Hals „steht“ im Bild
    if not plain:                                         # weicher Schatten unter der Figur
        shadow = Image.new("RGBA", fig.size, (0, 0, 0, 0))
        shadow.putalpha(fig.getchannel("A").point(lambda a: a * 0.55))
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(1, size // 64)))
        out.alpha_composite(shadow, (x + max(1, size // 128), y + max(1, size // 96)))
    out.alpha_composite(fig, (x, y))
    if radius and not plain:                              # Figur nicht über die runden Ecken hinaus
        out.putalpha(Image.composite(out.getchannel("A"), Image.new("L", out.size, 0), background(size, radius).getchannel("A")))
    return out


def main() -> None:
    src = Image.open(sys.argv[1] if len(sys.argv) > 1 else ROOT / "tools" / "assets" / "icon-quelle.png").convert("RGBA")
    # Fenster, Browser-Tab, Verknüpfung, installierte App: transparent wie bisher – nur die Ente
    tile(src, 512, CROP_FULL, scale=1.0, plain=True).save(STATIC / "icon-512.png", optimize=True)
    tile(src, 192, CROP_FULL, scale=1.0, plain=True).save(STATIC / "icon-192.png", optimize=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [tile(src, s, CROP_HEAD if s <= 48 else CROP_FULL, scale=1.0, plain=True) for s in sizes]
    frames[-1].save(ROOT / "duckpilot.ico", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    # Handy-Startbildschirm verlangt eine volle Fläche: dort die dunkle duckpilot-Kachel
    tile(src, 512, CROP_FULL, scale=0.78, radius=0).save(STATIC / "icon-maskable-512.png", optimize=True)
    tile(src, 180, CROP_FULL, scale=0.9, radius=0).convert("RGB").save(STATIC / "apple-touch-icon.png", optimize=True)
    print("Icons geschrieben:", ", ".join(["duckpilot.ico", "icon-192.png", "icon-512.png", "icon-maskable-512.png",
                                          "apple-touch-icon.png"]))


if __name__ == "__main__":
    main()
