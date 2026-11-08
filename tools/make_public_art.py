#!/usr/bin/env python3
"""App-Icons der öffentlichen Fassung – aus dem Knowlin-Zeichen.

    python tools/make_public_art.py <ziel-ordner>          # Icons in die öffentliche Fassung
    python tools/make_public_art.py --website               # Favicon und Homescreen-Bild der Website (im Projekt)
    python tools/make_public_art.py --knowlin-ico           # knowlin.ico für die Verknüpfung „Knowlin“ (im Projekt)

Die private Fassung nutzt KI-Bilder einer Kapitäns-Ente (tools/assets/icon-quelle.png, splash.jpg). Die gehen
nicht mit auf GitHub. Öffentlich ist das Knowlin-Zeichen (knowlin-zeichen.png, aus dem Splash-Entwurf des
Maintainers, seit 6.11.2026 öffentlich): Dieses Skript setzt es auf die dunkle Kachel und schreibt daraus
duckpilot.ico, server/static/icon-192.png, icon-512.png, icon-maskable-512.png und apple-touch-icon.png.
Ein Startbild braucht es seit 0.38.24 nicht mehr – beim Start lädt Knowlins Bewusstsein, im Browser gezeichnet.
`knowlin_zeichen()` bleibt als schlichter Ersatz, falls das Zeichen je wieder ausgetauscht werden muss.
Braucht Pillow – nur beim Erzeugen.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_icons import BEAK, background

HEAD = (0xE8, 0xE8, 0xE8)       # helles Grau statt Weiß: ruhiger auf dem dunklen Grund (Ersatz-Zeichen)


def knowlin_zeichen(size: int = 256) -> Image.Image:
    """Schlichtes Knowlin-Zeichen für die öffentliche Fassung: drei verbundene Knoten (Synapsen), hell und orange."""
    k = size / 40
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    hell = (*HEAD, 255)
    for a, b in (((13, 7), (13, 33)), ((13, 21), (25, 9)), ((17, 18), (26, 32))):
        d.line([(a[0] * k, a[1] * k), (b[0] * k, b[1] * k)], fill=hell, width=round(2.6 * k))
    for (x, y), farbe in (((13, 21), hell), ((25, 9), (*BEAK, 255)), ((26, 32), (*BEAK, 255))):
        d.ellipse(((x - 3) * k, (y - 3) * k, (x + 3) * k, (y + 3) * k), fill=farbe)
    return img


def zeichen_kachel(zeichen: Image.Image, size: int, scale: float = 0.66, radius: float = 0.22) -> Image.Image:
    """Knowlin-Zeichen mittig auf der dunklen Kachel mit orangem Schein (wie die App-Kacheln). Auf hellem Grund
    – etwa einem hellen Browser-Tab – verschwände das helle Zeichen ohne Kachel."""
    box = zeichen.getbbox() or (0, 0, *zeichen.size)
    fig = zeichen.crop(box)
    inner = round(size * scale)
    k = inner / max(fig.size)
    fig = fig.resize((max(1, round(fig.width * k)), max(1, round(fig.height * k))), Image.LANCZOS)
    if k > 1:                                              # das Zeichen liegt nur in 256 px vor: beim Vergrößern nachschärfen
        fig = fig.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    out = background(size, radius, edge=bool(radius))
    out.alpha_composite(fig, ((size - fig.width) // 2, (size - fig.height) // 2))
    if radius:                                             # nichts über die runden Ecken hinaus
        out.putalpha(Image.composite(out.getchannel("A"), Image.new("L", out.size, 0), background(size, radius).getchannel("A")))
    return out


def icons(zeichen: Image.Image, static: Path, ico: Path) -> None:
    """App-Icons der öffentlichen Fassung aus dem Knowlin-Zeichen (seit 0.38.24 – vorher ein gezeichneter Entenkopf)."""
    zeichen_kachel(zeichen, 512).save(static / "icon-512.png", optimize=True)
    zeichen_kachel(zeichen, 192).save(static / "icon-192.png", optimize=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [zeichen_kachel(zeichen, s, scale=0.78 if s <= 32 else 0.7) for s in sizes]
    frames[-1].save(ico, sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    zeichen_kachel(zeichen, 512, scale=0.5, radius=0).save(static / "icon-maskable-512.png", optimize=True)
    zeichen_kachel(zeichen, 180, scale=0.6, radius=0).convert("RGB").save(static / "apple-touch-icon.png", optimize=True)


def knowlin_ico(zeichen: Image.Image, ico: Path) -> None:
    """knowlin.ico für die Verknüpfung „Knowlin“ (Startseite, seit 0.38.27) – in beiden Fassungen aus dem Zeichen."""
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [zeichen_kachel(zeichen, s, scale=0.78 if s <= 32 else 0.7) for s in sizes]
    frames[-1].save(ico, sizes=[(s, s) for s in sizes], append_images=frames[:-1])


def website_icons(zeichen: Image.Image, website: Path) -> None:
    """Favicon und Homescreen-Bild der Website – ebenfalls auf der Kachel statt frei auf Transparenz."""
    zeichen_kachel(zeichen, 64, scale=0.74).save(website / "favicon.png", optimize=True)
    zeichen_kachel(zeichen, 180, scale=0.6, radius=0).convert("RGB").save(website / "apple-touch-icon.png", optimize=True)


def main(dest: Path) -> None:
    static = dest / "duckpilot" / "server" / "static"
    static.mkdir(parents=True, exist_ok=True)
    if not (static / "knowlin-zeichen.png").exists():         # nur, falls das echte Zeichen fehlt
        knowlin_zeichen().save(static / "knowlin-zeichen.png", optimize=True)
    zeichen = Image.open(static / "knowlin-zeichen.png").convert("RGBA")
    icons(zeichen, static, dest / "duckpilot.ico")
    knowlin_ico(zeichen, dest / "knowlin.ico")
    # Kein Startbild mehr: seit 0.38.24 lädt beim Start Knowlins Bewusstsein (gezeichnet im Browser, ohne Bild).


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == "--knowlin-ico":
        root = Path(__file__).resolve().parents[1]
        knowlin_ico(Image.open(root / "duckpilot/server/static/knowlin-zeichen.png").convert("RGBA"), root / "knowlin.ico")
    elif sys.argv[1] == "--website":
        root = Path(__file__).resolve().parents[1]
        website_icons(Image.open(root / "duckpilot/server/static/knowlin-zeichen.png").convert("RGBA"), root / "website")
    else:
        main(Path(sys.argv[1]))
