"""Sichtbare Texte der Erweiterungen nennen nie „duckpilot“ (seit 0.38.35: der Hinweis der Community-Tricks tat es,
sichtbar, seit die Pakete von Anfang an an sind – gefunden von der Abnahme)."""

from dataclasses import asdict

from duckpilot.skills import PACKS


def test_kein_duckpilot_in_sichtbaren_pakettexten():
    for pid, pack in PACKS.items():
        info = asdict(pack.info)
        for feld in ("name", "kurz", "text", "im_simulator", "hinweis"):
            assert "duckpilot" not in str(info.get(feld) or "").lower(), (pid, feld)
