"""Prüfkette (seit 0.38.35): ein Fehlschlag irgendwo macht das Ganze rot, der Bericht nennt jeden Schritt."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pruefen_alles as P  # noqa: E402


def test_kette_meldet_jeden_schritt_und_faellt_bei_einem_fehler(tmp_path):
    k = P.Kette(tmp_path)
    assert k.schritt("gut", [sys.executable, "-c", "print('alles fein')"])
    assert not k.schritt("schlecht", [sys.executable, "-c", "raise SystemExit(3)"])
    assert not k.schritt("erwartet", [sys.executable, "-c", "print('1 fehlen')"], ok_wenn=" 0 fehlen")
    k.uebersprungen("website", "--schnell")
    assert not k.bericht()
    text = (tmp_path / "pruefkette.md").read_text(encoding="utf-8")
    assert "NICHT bestanden" in text and "alles fein" in text and "übersprungen" in text
    assert len(list(tmp_path.glob("*.log"))) == 3


def test_kette_gruen_wenn_alles_bestanden(tmp_path):
    k = P.Kette(tmp_path)
    k.schritt("gut", [sys.executable, "-c", "print('ok')"])
    assert k.bericht()
