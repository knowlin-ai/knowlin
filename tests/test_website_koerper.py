"""Website, README und Vorschaubild nennen alle fertigen Körper (seit 0.38.56, Fund des Maintainers: „die Website
stimmt nicht mehr“ – Vorschaubild und Bildtexte sprachen noch von drei Körpern, Ari fehlte)."""

import importlib.util
import re
from pathlib import Path

from duckpilot.suite import KOERPER_MODUL, MODULE

ROOT = Path(__file__).resolve().parents[1]
TEXTE = ("website/index.html", "tools/website.py", "README.md", "README.en.md", "CONTRIBUTING.md", "docs/handbuch.md")
VERALTET = re.compile(r"\b(drei|zwei|three|two) (Verkörperungen|Roboter-Körper\w*|Körper\b|embodiments|bodies)", re.I)


def _vorschau():
    spec = importlib.util.spec_from_file_location("vorschau_bilder", ROOT / "tools" / "vorschau_bilder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_keine_veraltete_zahl_der_koerper():
    funde = [f"{p}: {m.group(0)}" for p in TEXTE for m in VERALTET.finditer((ROOT / p).read_text(encoding="utf-8"))
             if not m.group(0).startswith("zwei Körper")]          # „Ein Interface, zwei Körper“: Simulator und echt
    assert funde == []


def test_vorschaubild_nennt_alle_fertigen_koerper():
    fertig = [m for m in MODULE if m[3] == "fertig" and m[0] in KOERPER_MODUL]
    namen = _vorschau().koerper()
    assert len(namen) == len(fertig) and "SO-101" in namen and "Mentor" not in namen


def test_lernen_mit_festem_blick():
    """„Nimm mal lieber das Bild bei Lernen“ (13.11.): Website-Bild des Trainingsfelds mit festem Blick und vollem Feld."""
    js = (ROOT / "duckpilot" / "server" / "static" / "trainingsfeld.js").read_text(encoding="utf-8")
    assert "canvas.dataset.blick" in js and "canvas.feldZeichnen = () =>" in js and "sparen(0)" in js
    werkzeug = (ROOT / "tools" / "website_bilder.py").read_text(encoding="utf-8")
    assert 'TRAINING_BLICK = "' in werkzeug and "c.feldZeichnen()" in werkzeug


def test_idee_von_mit_fuer_dich():
    """Vision auf der Website (14.11.): „er lernt von mir, mit mir, für mich“ – Assistenten mit Wesenszug."""
    seite = (ROOT / "website" / "index.html").read_text(encoding="utf-8")
    assert '<section id="idee"' in seite and 'href="#idee"' in seite
    for teil in ("Von dir", "Mit dir", "Für dich", "From you", "With you", "For you", "Wesenszug"):
        assert teil in seite


def test_sperre_ohne_feste_zeit():
    """„Die 120 s Not-Aus stören mich – sag einfach, dass man es definieren kann“ (14.11.): öffentliche Texte nennen
    keine feste Sperrzeit; die Regel (15 s bis 10 min, Standard 120 s) steht weiter im Code."""
    fest = re.compile(r"120\s?(<small>)?s\b|120 Sekunden|zwei Minuten Sperre|2 Minuten Sperre|Standard zwei Minuten"
                      r"|two minutes by default|120 s lock", re.I)
    for p in ("website/index.html", "README.md", "README.en.md", "CONTRIBUTING.md", "SECURITY.md", "docs/handbuch.md"):
        assert not fest.search((ROOT / p).read_text(encoding="utf-8")), p


def test_vitrine_zeigt_alle_sechs_koerper_und_das_neue():
    """„Die Vitrine zeigt noch fast nur die Microduck; alle sechs Körper und die neuen Funktionen (Ari lernt durch
    Vormachen, Bellos Tricks, Stacki, Suche bei den Tricks) sollen vorkommen“ (Releaseplan 0.38.65)."""
    seite = (ROOT / "website" / "index.html").read_text(encoding="utf-8")
    vitrine = seite[seite.index('id="funktionen"'):seite.index('<section id="werte">')]
    for name in ("cockpit|tanz|akrobatik|team|training", "reachy", "odi", "vormachen", "stackchan", "bello_tricks",
                 "tricks_suche"):
        assert re.search(rf'data-bild="({name})"', vitrine), name
    for bild in ("vormachen", "bello_tricks", "tricks_suche"):                 # die neuen Bilder gibt es auch
        for sprache in ("de", "en"):
            assert (ROOT / "website" / "bilder" / f"{bild}-{sprache}-1600.webp").exists(), (bild, sprache)
    assert "<b>6</b>" in vitrine and "Was in ihr steckt" not in seite


def test_fahrplan_und_roadmap_aus_den_geplant_kacheln(tmp_path):
    """Roadmap und Stand (Releaseplan 0.38.65): Website und docs/ROADMAP.md kommen aus duckpilot/geplant.py – vorher
    stand in ROADMAP.md noch der Plan von vor dem 15.11. (Rollschuhe in 0.39), weil sie seit 0.38.42 niemand neu baute."""
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    import export_public

    import website
    from duckpilot.geplant import liste

    assert (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8") == export_public.roadmap()
    gebaut = (website.bauen(tmp_path / "w") / "index.html").read_text(encoding="utf-8")
    assert "{{FAHRPLAN}}" not in gebaut and 'href="#fahrplan"' in gebaut
    for g in liste():
        assert g["name"] in gebaut
