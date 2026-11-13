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
