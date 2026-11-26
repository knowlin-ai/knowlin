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
    assert "document.title = 'Knowlin';" not in quelle and "self-learning companion for Microduck" in quelle


def test_download_knopf_zeigt_auf_den_installer_der_version(tmp_path):
    from website import download_url, version

    seite = (bauen(tmp_path / "seite") / "index.html").read_text(encoding="utf-8")
    v = version()
    assert download_url() == f"https://github.com/knowlin-ai/knowlin/releases/download/v{v}/Knowlin-Setup-{v}.exe"
    assert seite.count(f'href="{download_url()}"') >= 2 and "{{" not in seite


def test_bildschirmfotos_einheitlich_gross():
    # „die Screenshots sind immer unterschiedlich groß auf Website und GitHub“ – alle im selben Format
    import pytest

    Image = pytest.importorskip("PIL.Image")                                # Pillow fehlt in der schlanken Prüfung

    fotos = [p for p in (ROOT / "docs" / "bilder").glob("*.png") if p.stem not in ("banner", "knowlin-avatar")]
    fotos += [p for p in (ROOT / "website" / "bilder").glob("*-1600.webp")]
    groessen = {p.name: Image.open(p).size for p in fotos}
    assert fotos and set(groessen.values()) == {(1600, 965)}, groessen
    seite = (ROOT / "website" / "index.html").read_text(encoding="utf-8")
    assert 'height="673"' not in seite and 'width="1065"' not in seite


def test_download_knopf_folgt_dem_neuesten_release(monkeypatch):
    import website

    monkeypatch.setenv("KNOWLIN_RELEASE", "v0.38.31")
    assert website.version() == "0.38.31" and website.download_url().endswith("/v0.38.31/Knowlin-Setup-0.38.31.exe")
    monkeypatch.setenv("KNOWLIN_RELEASE", "")
    assert website.version() != ""


def test_bilder_mit_pollens_modellen_tragen_den_nachweis():
    # Seit 0.38.40 („Bilder mit den echten Modellen … mit entsprechendem Hinweis“): jedes Bild mit Pollens
    # Modell steht in einem Abschnitt mit Bildnachweis – Urheber, Lizenz und Link –, auch ohne JavaScript
    from website import POLLEN_BILDER

    quelle = (ROOT / "website" / "index.html").read_text(encoding="utf-8")
    abschnitte = re.split(r"<section\b", quelle)
    for name in POLLEN_BILDER:
        drin = [a for a in abschnitte if f'data-bild="{name}"' in a]
        if not drin:
            continue                                     # Bild nur über die Bühne (z. B. reachy) – dort per Körperwahl
        for a in drin:
            nachweis = re.search(r'<p class="bildnachweis"[^>]*data-nachweis="pollen"[^>]*>(.*?)</p>', a, re.S)
            assert nachweis, name
            assert "© Pollen Robotics" in nachweis.group(1) and "creativecommons.org/licenses/by-nc-sa/4.0" in nachweis.group(1)
    assert "id=\"buehne-nachweis\"" in quelle and "NACHWEIS = {" in quelle


def test_englische_seite_mit_eigener_adresse_und_hreflang(tmp_path):
    # seit 0.51 („mache weiter SEO-Optimierung“): /en/ mit eigenem Titel, Beschreibung, Adresse; beide per hreflang verbunden
    from website import ADRESSE_EN, BESCHREIBUNG_EN

    ziel = bauen(tmp_path / "seite")
    de = (ziel / "index.html").read_text(encoding="utf-8")
    en = (ziel / "en" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in en and f'<link rel="canonical" href="{ADRESSE_EN}">' in en
    assert "Microduck" in re.search(r"<title>([^<]+)</title>", en).group(1)
    assert BESCHREIBUNG_EN in en and 70 <= len(BESCHREIBUNG_EN) <= 160
    for seite in (de, en):
        assert 'hreflang="de" href="https://knowlin.de/"' in seite and 'hreflang="en" href="https://knowlin.de/en/"' in seite
        assert 'hreflang="x-default"' in seite
    daten = json.loads(re.search(r'<script type="application/ld\+json">(.+?)</script>', en).group(1))
    assert daten["inLanguage"] == "en" and daten["url"] == ADRESSE_EN and daten["softwareVersion"]
    assert daten["downloadUrl"].endswith(".exe") and len(daten["screenshot"]) >= 3 and daten["featureList"]
    # alle Dateien eine Ebene höher – keine relativen Pfade, die unter /en/ ins Leere zeigen
    lose = re.findall(r'(?:src|href|srcset)="(?!\.\./|https?:|#|mailto|data:|/)[^"]+"', en)
    from website_koerper import KOERPER  # seit 0.52.1: Körper-Seiten liegen unter /en/<slug>/

    lose = [x for x in lose if x not in {f'href="{k["slug"]}/"' for k in KOERPER}]
    assert not lose, lose[:5]
    assert not re.findall(r'url\("(?!\.\./)', en)
    karte = (ziel / "sitemap.xml").read_text(encoding="utf-8")
    assert f"<loc>{ADRESSE_EN}</loc>" in karte and 'xmlns:xhtml=' in karte


def test_sprache_folgt_der_adresse_nicht_dem_browser():
    quelle = (ROOT / "website" / "index.html").read_text(encoding="utf-8")
    assert "navigator.language" not in quelle and "location.href = SEITE[l]" in quelle


def test_eine_seite_je_koerper_mit_hreflang_sitemap_und_links(tmp_path):
    """Seit 0.52.1: /microduck/, /en/microduck/ … – eigene Titel und Beschreibungen, gegenseitig per hreflang verbunden."""
    from website_koerper import KOERPER, adresse, pfade

    ziel = bauen(tmp_path / "seite")
    karte = (ziel / "sitemap.xml").read_text(encoding="utf-8")
    titel = set()
    for pfad in pfade():
        s = (ziel / pfad).read_text(encoding="utf-8")
        sprache = "en" if pfad.startswith("en/") else "de"
        slug = pfad.removeprefix("en/").split("/")[0]
        assert f'<html lang="{sprache}">' in s and s.count("<h1") == 1 and s.count("<title>") == 1
        t = re.search(r"<title>([^<]+)</title>", s).group(1)
        b = re.search(r'<meta name="description" content="([^"]+)"', s).group(1)
        assert t.endswith("– Knowlin") and len(t) <= 60 and 70 <= len(b) <= 160, (pfad, len(t), len(b))
        titel.add(t)
        assert f'<link rel="canonical" href="{adresse(slug, sprache)}">' in s
        for l in ("de", "en"):
            assert f'hreflang="{l}" href="{adresse(slug, l)}"' in s
        daten = json.loads(re.search(r'<script type="application/ld\+json">(.+?)</script>', s).group(1))
        assert {g["@type"] for g in daten["@graph"]} == {"WebPage", "BreadcrumbList"}
        assert f"<loc>{adresse(slug, sprache)}</loc>" in karte
        assert 'src="/bilder/' in s and ".dpm" not in s          # Bilder ja, Pollens Modelldateien nie
    assert len(titel) == len(pfade()) == 2 * len(KOERPER)    # jeder Titel nur einmal
    for start in ("index.html", "en/index.html"):
        s = (ziel / start).read_text(encoding="utf-8")
        for k in KOERPER:
            assert f'href="{k["slug"]}/">' in s            # die Namen unter dem Netz (seit 25.11.)


def test_koerperseiten_mit_pollens_bild_nennen_die_lizenz(tmp_path):
    from website_koerper import KOERPER

    ziel = bauen(tmp_path / "seite")
    for k in KOERPER:
        s = (ziel / k["slug"] / "index.html").read_text(encoding="utf-8")
        haupt = s.split("<main")[1].split("</main>")[0]
        assert ("CC BY-NC-SA 4.0" in haupt) == (k["pollen"] or k.get("hiwonder", False)), k["slug"]


def test_steckbrief_fuehrt_auf_die_koerperseite():
    """Rückmeldung 25.11. („Ich dachte es gibt nun Unterseiten?“): jeder Steckbrief hat einen sichtbaren Knopf dorthin."""
    from website_koerper import KOERPER

    s = (Path(__file__).resolve().parents[1] / "website" / "index.html").read_text(encoding="utf-8")
    seiten = dict(re.findall(r"(\w+): '([a-z0-9-]+)'", s.split("const SEITEN = {")[1].split("}")[0]))
    assert set(seiten.values()) <= {k["slug"] for k in KOERPER}         # die WonderDuck nur im Menü (seit 0.53)
    assert "koerper-seite-knopf" in s and "Alles zu ${k.name}" in s and "Everything about ${k.name}" in s


def test_menue_mit_koerpern_auf_startseite_und_koerperseiten(tmp_path):
    """26.11. („wieso gibt es … bei Körper keine Dropdowns?“, „nur zurück zur Startseite – sieht komisch aus“):
    überall dieselbe Leiste mit „Körper“ zum Aufklappen und einem Menü-Knopf fürs Handy."""
    from website_koerper import KOERPER, MENUE, pfade

    ziel = bauen(tmp_path / "seite")
    for pfad in ["index.html", "en/index.html", *pfade()]:
        s = (ziel / pfad).read_text(encoding="utf-8")
        assert s.count('class="menue-koerper"') == 1 and 'class="menue-knopf"' in s and "menue-knopf" in s.split("<script>")[-1]
        nav = s.split('id="navi"')[1].split("</nav>")[0]
        for k in KOERPER:
            assert f'{k["slug"]}/"' in nav
        assert all(f'#{anker}"' in nav for anker, _, _ in MENUE)
        if pfad not in ("index.html", "en/index.html"):
            slug = pfad.removeprefix("en/").split("/")[0]
            assert f'href="/{"en/" if pfad.startswith("en/") else ""}{slug}/" aria-current="page"' in nav
            assert "Zur Startseite" not in s and "Back to the start page" not in s
