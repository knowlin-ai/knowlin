"""Impressum und Datenschutz der Website (0.38.27): Name und Anschrift kommen nur beim Bauen aus KNOWLIN_IMPRESSUM,
ohne sie steht ein Platzhalter da und die Veröffentlichung wird aufgehalten."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import website  # noqa: E402


def test_ohne_anschrift_platzhalter_und_sperre(tmp_path, monkeypatch):
    monkeypatch.delenv("KNOWLIN_IMPRESSUM", raising=False)
    ziel = website.bauen(tmp_path / "seite")
    imp = (ziel / "impressum.html").read_text(encoding="utf-8")
    assert "[Name und Anschrift folgen vor dem Start]" in imp and (ziel / ".impressum-offen").exists()
    assert "§ 5 DDG" in imp and 'href="./"' in imp
    ds = (ziel / "datenschutz.html").read_text(encoding="utf-8")
    assert "GitHub Pages" in ds and "knowlin.sprache" in ds and "Art. 15 bis 21 DSGVO" in ds
    start = (ziel / "index.html").read_text(encoding="utf-8")
    assert 'href="impressum.html"' in start and 'href="datenschutz.html"' in start


def test_mit_anschrift_ohne_sperre_und_sicher_eingesetzt(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWLIN_IMPRESSUM", "Erika Muster|Beispielweg 1|12345 <Ort>")
    ziel = website.bauen(tmp_path / "seite")
    imp = (ziel / "impressum.html").read_text(encoding="utf-8")
    assert "Erika Muster<br>" in imp and "12345 &lt;Ort&gt;" in imp and "Platzhalter" not in imp
    assert not (ziel / ".impressum-offen").exists()


def test_veroeffentlichen_wartet_auf_das_impressum():
    # im Projekt unter tools/github, in der öffentlichen Fassung unter .github
    wf = next(p for p in (ROOT / "tools" / "github", ROOT / ".github") if (p / "workflows" / "website.yml").exists())
    yml = (wf / "workflows" / "website.yml").read_text(encoding="utf-8")
    assert "KNOWLIN_IMPRESSUM: ${{ vars.KNOWLIN_IMPRESSUM }}" in yml and ".impressum-offen" in yml
