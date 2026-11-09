"""Karte „Policies aus Isaac Lab übernehmen“ (0.38.27): Markup, Modul, Übersetzung."""

import json
import re
from pathlib import Path

from duckpilot.server.oberflaeche import seite

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
EN = json.loads((STATIC.parents[1] / "i18n" / "ui_en.json").read_text(encoding="utf-8"))


def test_karte_steht_im_training_vor_der_stossreihe_und_nur_am_pc():
    html = seite()
    training = html[html.index('id="view-training"'):]
    assert training.index('id="isaaclab"') < training.index('id="stossreihe"')
    karte = re.search(r'<section class="card il-card pc-only" id="isaaclab".*?</section>', html, re.S).group(0)
    for id_ in ("il-form", "il-datei", "il-waehlen", "il-datei-name", "il-name", "il-aufgabe", "il-go", "il-standard", "il-state", "il-liste", "il-leer"):
        assert f'id="{id_}"' in karte, id_
    assert 'accept=".onnx"' in karte and 'aria-live="polite"' in karte and 'class="sr-only" type="file"' in karte


def test_modul_haengt_am_training_und_schickt_rohdaten():
    js = (STATIC / "isaaclab.js").read_text(encoding="utf-8")
    assert "import { initIsaacLab } from './isaaclab.js';" in (STATIC / "training.js").read_text(encoding="utf-8")
    assert "'Content-Type': 'application/octet-stream'" in js and "/api/isaaclab/standard" in js
    assert "/nutzen`" in js


def test_texte_aus_modul_und_pruefstand_sind_uebersetzt():
    from duckpilot.physics.isaaclab import PRUEFUNGEN

    js = (STATIC / "isaaclab.js").read_text(encoding="utf-8")
    for s in ("für die echte Ente frei", "Prüfstand nicht bestanden", "Im Physik-Simulator nutzen",
              "Läuft im Physik-Simulator", "Keine Antwort von Knowlin."):
        assert s in js and s in EN, s
    for _, titel, _, _ in PRUEFUNGEN:
        assert titel in EN, titel
    for k in ("# % des Befehls", "max. #° gekippt", "wandert # m", "folgt nur zu # %", "„*“ hat den Prüfstand bestanden."):
        assert k in EN, k
