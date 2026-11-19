"""Reiter je Quelle auf der Seite „Tricks“ (seit 0.38.66, Wunsch: „bei Tricks sind die Listen oft sehr lang“)."""

from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def test_reiter_sind_eingebaut_und_die_suche_bleibt_ueber_alle():
    html = (STATIC / "teile" / "tricks.html").read_text(encoding="utf-8")
    assert 'id="tricks-reiter"' in html and html.index('id="tricks-suche"') < html.index('id="tricks-reiter"')
    js = (STATIC / "tricks_reiter.js").read_text(encoding="utf-8")
    assert "aria-pressed" in js and "feld?.addEventListener('input', anwenden)" in js
    assert "initTricksReiter" in (STATIC / "tricks_seite.js").read_text(encoding="utf-8")
    assert ".reiter-aus" in (STATIC / "bereiche" / "tricks.css").read_text(encoding="utf-8")


def test_jede_quelle_hat_eine_ueberschrift():
    """Die Reiter entstehen aus den Abschnittsüberschriften – jeder Kachelblock braucht eine."""
    html = (STATIC / "teile" / "tricks.html").read_text(encoding="utf-8")
    teil = html[html.index('<div class="tricks-links">'):html.index('tricks-vorschau-karte')]
    assert teil.count('class="section-head') >= 8
