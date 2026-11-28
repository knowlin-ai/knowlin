#!/usr/bin/env python3
"""Website knowlin.de bauen: `website/index.html` ist als Seiteninhalt geschrieben (so lässt sie sich auch als Vorschau
veröffentlichen); hier bekommt sie Kopf, Sprache und Vorschau-Angaben für Suchmaschinen und Teilen.

    python tools/website.py <ziel-ordner>      # z. B. für GitHub Pages

Die Prüfung (Barrierefreiheit, Tastatur, Breiten, Leistung) macht `tools/website_pruefen.py`.
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUELLE = ROOT / "website"
ADRESSE = "https://knowlin.de/"
ADRESSE_EN = ADRESSE + "en/"
# Englische Seite (seit 0.51, Maintainer: „mache weiter SEO-Optimierung“): gleicher Inhalt, eigene Adresse, eigener
# Titel und Beschreibung – Suchmaschinen sehen je Adresse eine Sprache, hreflang verbindet beide
TITEL_EN = "Knowlin – self-learning companion for Microduck, WonderDuck, Reachy Mini and more"   # wie der Titel im Seitenskript
BESCHREIBUNG_EN = ("Free open-source companion for small robots: simulate Microduck, WonderDuck, Reachy Mini, Open Duck and SO-101 "
                   "on your PC, control them by voice, teach dances.")

KOPF = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f3f4f6" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0d0f12" media="(prefers-color-scheme: dark)">
<link rel="canonical" href="{adresse}">
<link rel="alternate" hreflang="de" href="https://knowlin.de/">
<link rel="alternate" hreflang="en" href="https://knowlin.de/en/">
<link rel="alternate" hreflang="x-default" href="https://knowlin.de/">
<meta property="og:type" content="website">
<meta property="og:url" content="{adresse}">
<meta property="og:title" content="Knowlin – ein Kopf, viele Körper">
<meta property="og:description" content="{beschreibung}">
<meta property="og:image" content="{basis}bilder/vorschau.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Knowlin – ein Kopf, viele Körper: die Startseite mit Knowlins Netz und sieben Roboter-Körpern: Microduck, Reachy Mini, Open Duck Mini, WonderDuck, SO-101, Stack-chan und Bittle X">
<meta property="og:site_name" content="Knowlin">
<meta property="og:locale" content="de_DE">
<meta property="og:locale:alternate" content="en_US">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Knowlin – ein Kopf, viele Körper">
<meta name="twitter:description" content="{beschreibung}">
<meta name="twitter:image" content="{basis}bilder/vorschau.png">
<script type="application/ld+json">{daten}</script>
<link rel="preload" href="schrift/bricolage.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="schrift/plex-400.woff2" as="font" type="font/woff2" crossorigin>
"""


# Suchmaschinen (seit 0.38.30): strukturierte Daten als Software-Eintrag – ohne Personennamen, Herausgeber ist „Knowlin“
def strukturiert(beschreibung: str, adresse: str = ADRESSE, sprache: str = "de") -> str:
    # seit 0.51: Version, Download, Bildschirmfotos und Funktionen – was Suchmaschinen für Software-Einträge auswerten
    bilder = [f"{ADRESSE}bilder/{n}-{sprache}-1600.webp" for n in ("start", "cockpit", "tanz", "aufgaben", "training")]
    funktionen = (("Microduck, WonderDuck, Reachy Mini, Open Duck Mini, SO-101, Stack-chan und Bittle X im Simulator",
                   "Simulate Microduck, WonderDuck, Reachy Mini, Open Duck Mini, SO-101, Stack-chan and Bittle X"),
                  ("Aufgaben: Linie folgen, Farbe folgen, dir folgen, ausweichen, tragen",
                   "Tasks: follow a line, follow a colour, follow you, avoid obstacles, carry"),
                  ("Sprachsteuerung mit Claude, lokalen Modellen oder ganz ohne KI", "Voice control with Claude, local models or no AI"),
                  ("Tänze auf einer Zeitleiste, Tricks, Ablauf-Baukasten und Duck Cards",
                   "Dance timeline, tricks, sequence builder and Duck Cards"),
                  ("Gedächtnis, Lernen, Training und Policies", "Memory, learning, training and policies"))
    return json.dumps({
        "@context": "https://schema.org", "@type": "SoftwareApplication", "name": "Knowlin",
        "alternateName": "duckpilot", "url": adresse, "description": beschreibung,
        "softwareVersion": version(), "downloadUrl": download_url(), "screenshot": bilder,
        "featureList": [f[0] if sprache == "de" else f[1] for f in funktionen],
        "applicationCategory": "DeveloperApplication", "operatingSystem": "Windows, macOS, Linux",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"},
        "license": "https://www.apache.org/licenses/LICENSE-2.0",
        "codeRepository": "https://github.com/knowlin-ai/knowlin", "image": ADRESSE + "bilder/vorschau.png",
        "inLanguage": sprache, "isAccessibleForFree": True,
        "keywords": "Microduck, WonderDuck, Hiwonder, Open Duck Mini, Reachy Mini, SO-101, Stack-chan, Bittle X, LeRobot, Roboter, Simulator, Claude, Sprachsteuerung, Open Source",
        "publisher": {"@type": "Organization", "name": "Knowlin", "url": ADRESSE},
    }, ensure_ascii=False)


ROBOTS = "User-agent: *\nAllow: /\nSitemap: {adresse}sitemap.xml\n"


def sitemap() -> str:
    from website_koerper import sitemap_eintraege

    tag = time.strftime("%Y-%m-%d")
    paar = (f'<xhtml:link rel="alternate" hreflang="de" href="{ADRESSE}"/>'
            f'<xhtml:link rel="alternate" hreflang="en" href="{ADRESSE_EN}"/>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
            f"  <url><loc>{ADRESSE}</loc><lastmod>{tag}</lastmod>{paar}</url>\n"
            f"  <url><loc>{ADRESSE_EN}</loc><lastmod>{tag}</lastmod>{paar}</url>\n"
            + sitemap_eintraege(tag) + "</urlset>\n")


def englisch(seite: str) -> str:
    """Die deutsche Startseite als englische unter /en/: Sprache, Titel, Beschreibung, Adresse – und Pfade eine Ebene hoch."""
    de_titel = re.search(r"<title>([^<]+)</title>", seite).group(1)
    de_beschr = re.search(r'<meta name="description" content="([^"]+)"', seite).group(1)
    s = seite.replace('<html lang="de">', '<html lang="en">', 1)
    s = s.replace(f"<title>{de_titel}</title>", f"<title>{html.escape(TITEL_EN)}</title>", 1)
    s = s.replace(f'<link rel="canonical" href="{ADRESSE}">', f'<link rel="canonical" href="{ADRESSE_EN}">', 1)
    s = s.replace(f'<meta property="og:url" content="{ADRESSE}">', f'<meta property="og:url" content="{ADRESSE_EN}">', 1)
    s = s.replace(": die Startseite mit Knowlins Netz und sieben Roboter-Körpern:",   # Vorschaubild (seit 0.54 englisch)
                  ": the start page with Knowlin's network and seven robot bodies:").replace(
        "Stack-chan und Bittle X\">", "Stack-chan and Bittle X\">")
    s = s.replace("Knowlin – ein Kopf, viele Körper", "Knowlin – one mind, many bodies")
    s = s.replace('<meta property="og:locale" content="de_DE">\n<meta property="og:locale:alternate" content="en_US">',
                  '<meta property="og:locale" content="en_US">\n<meta property="og:locale:alternate" content="de_DE">')
    s = s.replace(de_beschr, html.escape(BESCHREIBUNG_EN))
    alt = re.search(r'<script type="application/ld\+json">(.+?)</script>', s).group(1)
    s = s.replace(alt, strukturiert(BESCHREIBUNG_EN, ADRESSE_EN, "en"), 1)
    for a, b in (('"bilder/', '"../bilder/'), (", bilder/", ", ../bilder/"), ('url("schrift/', 'url("../schrift/'),
                 ('href="schrift/', 'href="../schrift/'), ('href="favicon.png"', 'href="../favicon.png"'),
                 ('href="apple-touch-icon.png"', 'href="../apple-touch-icon.png"'),
                 ('href="impressum.html"', 'href="../impressum.html"'), ('href="datenschutz.html"', 'href="../datenschutz.html"'),
                 ('href="./"', 'href="../"')):
        s = s.replace(a, b)
    return s


# Download-Knopf (seit 0.38.31): direkt auf den Installer der aktuellen Version. Die Website baut bei jedem Release neu
# (website.yml), der Link stimmt also immer – und funktioniert ohne Skript und ohne Anfrage an fremde Server.
def version() -> str:
    """Version des neuesten Releases (auf GitHub setzt website.yml KNOWLIN_RELEASE), sonst die aus pyproject.toml –
    so zeigt der Knopf nie auf einen Installer, den es noch nicht gibt, wenn zwischen zwei Releases gebaut wird."""
    import tomllib

    tag = os.environ.get("KNOWLIN_RELEASE", "").strip().lstrip("v")
    if re.fullmatch(r"\d+\.\d+\.\d+", tag):
        return tag
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def download_url() -> str:
    v = version()
    return f"https://github.com/knowlin-ai/knowlin/releases/download/v{v}/Knowlin-Setup-{v}.exe"


def fahrplan() -> str:
    """Abschnitt „Was als Nächstes kommt“ (seit 0.38.65) aus `duckpilot/geplant.py` – dieselbe Liste wie die Kacheln
    „Geplant“ in der App, englisch aus dem Sprachkatalog der Oberfläche. So veraltet die Seite nicht neben der App."""
    sys.path.insert(0, str(ROOT))
    from duckpilot.geplant import liste
    from duckpilot.i18n import ui_text

    gruppen: dict[str, list[dict[str, str]]] = {}
    for eintrag in liste():
        gruppen.setdefault(eintrag["version"], []).append(eintrag)

    def zwei(text: str) -> str:
        return (f'<span class="t" lang="de">{html.escape(text)}</span>'
                f'<span class="t" lang="en">{html.escape(ui_text(text, "en"))}</span>')

    teile = []
    for v, eintraege in gruppen.items():
        punkte = "".join(f"<li><b>{zwei(e['name'])}</b> {zwei(e['kurz'])}</li>" for e in eintraege)
        teile.append(f'<li><h3 class="fahrplan-version">{zwei(v)}</h3><ul>{punkte}</ul></li>')
    return "\n".join(teile)


def teilen(text: str) -> tuple[str, str]:
    """Inhalt der Quelldatei in Kopf (Titel, Meta, Skripte, Stil) und Körper (ab der Kopfleiste) teilen."""
    i = text.index('<header class="leiste">')
    return text[:i], text[i:]


# Impressum und Datenschutz (seit 0.38.27): Inhalt in website/_impressum.html und _datenschutz.html. Name und Anschrift
# stehen nicht im Repo – sie kommen beim Bauen aus der Umgebungsvariablen KNOWLIN_IMPRESSUM (Zeilen mit „|“ getrennt,
# auf GitHub als Repo-Variable). Ohne sie steht ein sichtbarer Platzhalter da, und `.impressum-offen` hält die
# Veröffentlichung auf (website.yml).
PLATZHALTER = '<span class="platzhalter">[Name und Anschrift folgen vor dem Start]</span>'
RECHT = {"impressum": ("Impressum – Knowlin", "Legal notice – Knowlin"),
         "datenschutz": ("Datenschutz – Knowlin", "Privacy – Knowlin")}


def anschrift() -> str | None:
    roh = os.environ.get("KNOWLIN_IMPRESSUM", "").strip()
    if not roh:
        return None
    return "<br>\n".join(html.escape(z.strip()) for z in roh.split("|") if z.strip())


def unterseite(name: str, titel: tuple[str, str], inhalt: str, kopf: str, beschreibung: str, fuss: str, *,
               index: bool = False, haupt_klasse: str = "recht") -> str:
    """Eine Unterseite im Kleid der Startseite: Kopfleiste mit Sprachumschalter, Inhalt, Fußzeile."""
    stil = kopf[kopf.index("<style>"):kopf.index("</style>") + len("</style>")]
    sprachskript = kopf[kopf.index("<script>"):kopf.index("</script>") + len("</script>")]
    de, en = titel
    seite_adresse = f"{ADRESSE}{name}.html"
    return (KOPF.format(adresse=seite_adresse, basis=ADRESSE, beschreibung=beschreibung, daten=strukturiert(beschreibung)).replace(
        '<meta property="og:title" content="Knowlin – ein Kopf, viele Körper">', f'<meta property="og:title" content="{de}">')
        + f"<title>{de}</title>\n" + ("" if index else '<meta name="robots" content="noindex">\n')
        + '<link rel="icon" href="favicon.png">\n'
        + sprachskript + "\n" + stil + "\n</head>\n<body>\n"
        + '<a class="sprung" href="#titel"><span class="t" lang="de">Zum Inhalt springen</span>'
          '<span class="t" lang="en">Skip to content</span></a>\n'
        + '<header class="leiste"><div class="huelle">'
          '<a class="marke" href="./" aria-label="Knowlin – Startseite"><img src="bilder/zeichen-64.webp" alt="" width="30" height="30">Knowlin</a>'
          '<nav class="navi" aria-label="Seite"><a href="./"><span class="t" lang="de">Zur Startseite</span>'
          '<span class="t" lang="en">Back to the start page</span></a></nav>'
          '<div class="sprache" role="group" aria-label="Sprache · Language">'
          '<button type="button" id="sprache-de" data-sprache="de" aria-pressed="true">DE</button>'
          '<button type="button" id="sprache-en" data-sprache="en" aria-pressed="false">EN</button></div>'
          "</div></header>\n"
        + f'<main class="huelle {haupt_klasse}" aria-label="{de} · {en}">\n{inhalt}\n</main>\n' + fuss
        + "<script>\n(() => {\n  const zeigen = (l) => { document.documentElement.lang = l;\n"
          "    for (const b of document.querySelectorAll('[data-sprache]')) b.setAttribute('aria-pressed', String(b.dataset.sprache === l)); };\n"
          "  zeigen(document.documentElement.lang === 'en' ? 'en' : 'de');\n"
          "  for (const b of document.querySelectorAll('[data-sprache]')) b.addEventListener('click', () => {\n"
          "    zeigen(b.dataset.sprache); try { localStorage.setItem('knowlin.sprache', b.dataset.sprache); } catch (e) { /* egal */ } });\n"
          "})();\n</script>\n</body>\n</html>\n")


def rechtsseite(name: str, kopf: str, beschreibung: str, fuss: str, adresse: str) -> str:
    inhalt = (QUELLE / f"_{name}.html").read_text(encoding="utf-8").replace("{{IMPRESSUM_ANSCHRIFT}}", adresse)
    return unterseite(name, RECHT[name], inhalt, kopf, beschreibung, fuss)


# Odi ausprobieren (T4, seit 0.38.29): Odi läuft ganz im Browser – Teile der App-Ansicht (Modell-Lader, Licht, Boden)
# und das offene Modell der Open Duck Mini (Apache-2.0) werden beim Bauen dazugelegt, nichts doppelt im Repo.
# Pollens Modelldateien (Microduck, Reachy Mini; CC BY-NC-SA) kommen hier nie hin. Bilder, auf denen sie zu sehen sind,
# dürfen seit 0.38.40 auf die Seite (9.11.) – mit Bildnachweis; welche das sind, steht in POLLEN_BILDER.
POLLEN_BILDER = ("cockpit", "reachy", "charakter", "tanz", "team", "akrobatik", "training")
STATIC = ROOT / "duckpilot" / "server" / "static"
DEMO_DATEIEN = ("duckmodel.js", "formen3d.js", "licht3d.js", "raum3d.js", "vendor/three.module.min.js",
                "vendor/BufferGeometryUtils.js", "vendor/OrbitControls.js", "vendor/THREE-LICENSE",
                "vendor/jsm/environments/RoomEnvironment.js", "model/LIZENZ-open-duck-mini.md")
# Das Modell selbst als JSON (Base64): jeder Webserver liefert JSON aus und packt es unterwegs (gzip) – ein eigenes
# Binärformat (.dpm) lehnen manche Hoster und Vorschauen ab.
MODELL_QUELLE = "model/open_duck_mini.dpm"
MODELL_ZIEL = "model/odi-modell.json"
VERBOTEN = ("microduck", "reachy")
AUSPROBIEREN = ("Odi ausprobieren – Knowlin", "Try Odi – Knowlin")
# Vorerst aus (8.11., Maintainer: „Im Browser ausprobieren enttäuscht ggf. die Erwartungen – die App kann ja viel mehr“).
# Seite, Demo-Dateien und Prüfung bleiben im Repo; wieder an, sobald die Demo mehr zeigt.
MIT_AUSPROBIEREN = False


def demo_dazulegen(ziel: Path) -> None:
    for rel in DEMO_DATEIEN:
        if any(v in rel.lower() for v in VERBOTEN):
            raise SystemExit(f"{rel}: Pollens Modelle gehören nicht auf die Website")
        dst = ziel / "demo" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(STATIC / rel, dst)
    roh = (STATIC / MODELL_QUELLE).read_bytes()
    (ziel / "demo" / MODELL_ZIEL).write_text(json.dumps({
        "format": "DPM2, Base64", "modell": "Open Duck Mini v2", "lizenz": "Apache-2.0 – siehe LIZENZ-open-duck-mini.md",
        "daten": base64.b64encode(roh).decode("ascii")}), encoding="utf-8")


def bauen(ziel: Path) -> Path:
    ziel = Path(ziel)
    if ziel.exists():
        shutil.rmtree(ziel)
    muster = ("_*", "*.md") if MIT_AUSPROBIEREN else ("_*", "*.md", "demo")
    shutil.copytree(QUELLE, ziel, ignore=shutil.ignore_patterns(*muster))
    text = (QUELLE / "index.html").read_text(encoding="utf-8")
    from website_koerper import MENUE_JS, alle, navigation

    text = text.replace("{{NAVIGATION}}", navigation()).replace("{{MENUE_JS}}", MENUE_JS)
    text = text.replace("{{DOWNLOAD}}", download_url()).replace("{{VERSION}}", version()).replace("{{FAHRPLAN}}", fahrplan())
    kopf, koerper = teilen(text)
    beschreibung = re.search(r'<meta name="description" content="([^"]+)"', kopf).group(1)
    seite = KOPF.format(adresse=ADRESSE, basis=ADRESSE, beschreibung=beschreibung, daten=strukturiert(beschreibung)) + kopf + "</head>\n<body>\n" + koerper + "\n</body>\n</html>\n"
    (ziel / "index.html").write_text(seite, encoding="utf-8")
    (ziel / "en").mkdir(exist_ok=True)
    (ziel / "en" / "index.html").write_text(englisch(seite), encoding="utf-8")      # seit 0.51
    fuss = koerper[koerper.index("<footer>"):koerper.index("</footer>") + len("</footer>")] + "\n"
    adresse = anschrift()
    for name in RECHT:
        (ziel / f"{name}.html").write_text(rechtsseite(name, kopf, beschreibung, fuss, adresse or PLATZHALTER), encoding="utf-8")
    stil = kopf[kopf.index("<style>"):kopf.index("</style>") + len("</style>")]
    for pfad, inhalt in alle(stil, fuss, download_url()).items():        # seit 0.52.1: eine Seite je Körper
        (ziel / pfad).parent.mkdir(parents=True, exist_ok=True)
        (ziel / pfad).write_text(inhalt, encoding="utf-8")
    if MIT_AUSPROBIEREN:
        (ziel / "ausprobieren.html").write_text(unterseite("ausprobieren", AUSPROBIEREN,
                                                           (QUELLE / "_ausprobieren.html").read_text(encoding="utf-8"),
                                                           kopf, beschreibung, fuss, index=True, haupt_klasse="probe-seite"),
                                                encoding="utf-8")
        demo_dazulegen(ziel)
    if adresse is None:
        (ziel / ".impressum-offen").write_text("Name und Anschrift fehlen (KNOWLIN_IMPRESSUM)\n", encoding="utf-8")
    (ziel / "robots.txt").write_text(ROBOTS.format(adresse=ADRESSE), encoding="utf-8")
    (ziel / "sitemap.xml").write_text(sitemap(), encoding="utf-8")
    (ziel / ".nojekyll").write_text("", encoding="utf-8")        # GitHub Pages: Dateien unverändert ausliefern
    (ziel / "CNAME").write_text("knowlin.de\n", encoding="utf-8")
    return ziel


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(f"Website gebaut in {bauen(Path(sys.argv[1]))}")
