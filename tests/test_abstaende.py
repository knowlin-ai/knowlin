"""Hinweise 8.11.: „Hier scheint der Abstand nicht zu stimmen“ (Eigenschaften der Gestalt) – „das sollte bei den
Design-Tests auffallen. Und UX/UI.“ Die Abnahme prüft seitdem Abstände zwischen Schaltern, Knöpfen und Feldern."""

from pathlib import Path

from duckpilot.server.app import STATIC

CSS = (STATIC / "style.css").read_text(encoding="utf-8")
ABNAHME = (Path(__file__).resolve().parents[1] / "tools" / "abnahme.py").read_text(encoding="utf-8")


def test_gestalt_schalter_als_zeilen_mit_luft():
    assert ".gestalt-liste > .switch { padding: var(--spacing-04) 0; border-top: 1px solid var(--line-soft); }" in CSS


def test_abnahme_prueft_abstaende_auf_pc_und_handy():
    assert "ABSTAND_JS" in ABNAHME and 'abstaende(page, b, "Persönlichkeit")' in ABNAHME
    assert 'abstaende(page, b, "Einstellungen")' in ABNAHME and "(1440, 900), (390, 844)" in ABNAHME
