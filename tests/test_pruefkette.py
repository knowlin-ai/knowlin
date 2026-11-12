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


def test_fingerabdruck_trennt_code_website_und_notizen(tmp_path, monkeypatch):
    """Seit 0.38.41: ein neues Website-Bild oder eine Notiz lässt den teuren Code-Teil der Kette aus."""
    import subprocess
    (tmp_path / "duckpilot").mkdir()
    (tmp_path / "website" / "bilder").mkdir(parents=True)
    (tmp_path / "duckpilot" / "a.py").write_text("x = 1\n")
    (tmp_path / "website" / "bilder" / "b.webp").write_bytes(b"alt")
    (tmp_path / "Releaseplan.md").write_text("Plan\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(P, "ROOT", tmp_path)
    code, web = P.fingerabdruck("code"), P.fingerabdruck("website")
    (tmp_path / "website" / "bilder" / "b.webp").write_bytes(b"neu")
    (tmp_path / "Releaseplan.md").write_text("Plan, länger\n")
    assert P.fingerabdruck("code") == code and P.fingerabdruck("website") != web
    (tmp_path / "duckpilot" / "a.py").write_text("x = 2\n")
    assert P.fingerabdruck("code") != code


def test_stand_wird_gemerkt(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "STAND", tmp_path / "stand.json")
    assert P.stand_lesen() == {}
    P.stand_merken("code", "abc")
    P.stand_merken("website", "def")
    assert P.stand_lesen() == {"code": "abc", "website": "def"}
