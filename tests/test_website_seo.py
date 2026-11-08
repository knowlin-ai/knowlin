"""Suchmaschinen (0.38.30, Wunsch beim Launch: „kannst du Knowlin noch SEO-optimieren?“)."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from website import ADRESSE, bauen  # noqa: E402


def test_titel_beschreibung_daten_robots_sitemap(tmp_path):
    ziel = bauen(tmp_path / "seite")
    seite = (ziel / "index.html").read_text(encoding="utf-8")
    titel = re.search(r"<title>([^<]+)</title>", seite).group(1)
    assert "Microduck" in titel and len(titel) <= 90
    beschreibung = re.search(r'<meta name="description" content="([^"]+)"', seite).group(1)
    assert 70 <= len(beschreibung) <= 160
    assert seite.count("<title>") == 1 and f'<link rel="canonical" href="{ADRESSE}">' in seite
    daten = json.loads(re.search(r'<script type="application/ld\+json">(.+?)</script>', seite).group(1))
    assert daten["@type"] == "SoftwareApplication" and daten["offers"]["price"] == "0"
    assert daten["publisher"] == {"@type": "Organization", "name": "Knowlin", "url": ADRESSE}   # kein Personenname
    robots = (ziel / "robots.txt").read_text(encoding="utf-8")
    assert "Allow: /" in robots and f"Sitemap: {ADRESSE}sitemap.xml" in robots
    assert f"<loc>{ADRESSE}</loc>" in (ziel / "sitemap.xml").read_text(encoding="utf-8")
    # Rechtsseiten: nicht indexieren, Vorschaubild mit richtiger Adresse
    recht = (ziel / "impressum.html").read_text(encoding="utf-8")
    assert '<meta name="robots" content="noindex">' in recht
    assert f'content="{ADRESSE}bilder/vorschau.png"' in recht and "impressum.htmlbilder" not in recht


def test_sprachwechsel_behaelt_aussagekraeftigen_titel():
    quelle = (ROOT / "website" / "index.html").read_text(encoding="utf-8")
    assert "document.title = 'Knowlin';" not in quelle and "learning companion for Microduck" in quelle


def test_download_knopf_zeigt_auf_den_installer_der_version(tmp_path):
    from website import download_url, version

    seite = (bauen(tmp_path / "seite") / "index.html").read_text(encoding="utf-8")
    v = version()
    assert download_url() == f"https://github.com/knowlin-ai/knowlin/releases/download/v{v}/Knowlin-Setup-{v}.exe"
    assert seite.count(f'href="{download_url()}"') >= 2 and "{{" not in seite
