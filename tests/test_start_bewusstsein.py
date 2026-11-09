"""Wunsch 7.11. (0.38.24): „statt meinem Splashscreen mach auch wie bei dem Übergang zu den Körpern, dass
Knowlins Bewusstsein lädt“ – und die öffentliche Fassung nutzt nur die dafür vorgesehenen Bilder."""

import json
import sys
from pathlib import Path

import pytest

from duckpilot.server.app import STATIC
from duckpilot.server.oberflaeche import seite, stil

ROOT = Path(__file__).resolve().parents[1]


def test_start_zeigt_bewusstsein_statt_startbild():
    html = seite()
    start = html[html.index('id="splash"'):html.index("</script>", html.index('id="splash"'))]
    assert "splash.jpg" not in html and "<img" in start and "knowlin-zeichen.png" in start
    assert start.count("<i></i>") == 8 and "Knowlins Bewusstsein lädt …" in start and "Klick oder Taste überspringt" in start
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "box.classList.add('is-wach')" in app and "splash.ready(`Knowlin ist wach" in app
    assert "setTimeout(close, 8000)" in app                                   # kommt die App nicht hoch: trotzdem weg
    css = stil()
    block = css[css.index("/* Start: Knowlins Bewusstsein"):css.index("/* ── Handy-Fernbedienung")]
    assert "@keyframes einfliegen" in block and "prefers-reduced-motion" in block and "#" not in block.replace("#splash", "")
    en = json.loads((ROOT / "duckpilot" / "i18n" / "ui_en.json").read_text(encoding="utf-8"))
    assert en["Knowlins Bewusstsein lädt …"] and en["Knowlin ist wach · *"]


def test_oeffentliche_icons_aus_dem_knowlin_zeichen(tmp_path):
    Image = pytest.importorskip("PIL.Image")                                  # Pillow braucht nur, wer Icons erzeugt
    sys.path.insert(0, str(ROOT / "tools"))
    from make_public_art import main

    static = tmp_path / "duckpilot" / "server" / "static"
    static.mkdir(parents=True)
    (static / "knowlin-zeichen.png").write_bytes((STATIC / "knowlin-zeichen.png").read_bytes())
    main(tmp_path)
    assert not (static / "splash.jpg").exists()                               # kein Startbild mehr
    for name, groesse in (("icon-192.png", 192), ("icon-512.png", 512), ("icon-maskable-512.png", 512),
                          ("apple-touch-icon.png", 180)):
        bild = Image.open(static / name).convert("RGBA")
        assert bild.size == (groesse, groesse)
        assert bild.getpixel((groesse // 2, groesse - 3))[3] == 255           # auf der Kachel, nicht frei auf Transparenz
    assert (tmp_path / "duckpilot.ico").exists()


def test_export_laesst_private_bilder_weg():
    sys.path.insert(0, str(ROOT / "tools"))
    from export_public import PRIVAT

    for rel in ("duckpilot/server/static/splash.jpg", "tools/assets/icon-quelle.png", "duckpilot/server/static/model/microduck.dpm",
                "duckpilot/server/static/model/reachy_mini.dpm", "duckpilot/server/static/figuren/microduck.png",
                "duckpilot/server/static/figuren/reachy-mini.png"):
        assert rel in PRIVAT
