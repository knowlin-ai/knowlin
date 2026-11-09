"""Isaac-Lab-Karte (seit 0.38.35): Was läuft gerade, was steckt in Pollens Dateien, wie komme ich zurück?

Fragen: „Was ist das beste aktuell? So versteht man das nicht gut“ – „Warum laden wir nicht die Standard-Policy
von Pollen und setzen sie aktiv als default?“ – „und wie man wieder die Standard-Policy aktiviert. Man will sich ja
nichts verstellen“.
"""

import re
from pathlib import Path

from duckpilot.server.oberflaeche import seite

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


def test_oben_steht_was_laeuft_und_der_weg_zurueck():
    html = seite()
    karte = html[html.index('id="isaaclab"'):html.index('id="il-liste"')]
    aktiv, form = karte.index('id="il-aktiv"'), karte.index('id="il-form"')
    assert aktiv < form, "die Anzeige, was läuft, steht vor dem Formular"
    assert aktiv < karte.index('id="il-standard"') < form, "„Zurück auf Pollens Standard“ sitzt bei der Anzeige"
    assert "nach jedem Neustart läuft wieder Pollens Standard" in karte
    assert "Rampen-Policy aus NVIDIAs Vorführung" in karte


def test_pollens_dateien_haben_klarnamen_und_standard_ist_markiert():
    js = (STATIC / "isaaclab.js").read_text(encoding="utf-8")
    for stamm in ("velstand", "alpha_walking", "alpha_sitstand", "alpha_ground_pick", "ball_kick_left", "roulade", "roller"):
        assert re.search(rf"\b{stamm}:", js), stamm
    assert "pollen-robotics/microduck-policies" in js and "Standard · läuft schon in der Physik" in js
    assert "il-aktiv-text" in js


def test_zuruecksetzen_ist_nicht_gespeichert_und_bleibt_beim_neustart_standard():
    """Die Gangart aus „Im Physik-Simulator nutzen“ landet nirgends in den Einstellungen – nach einem Neustart läuft
    wieder Pollens Standard (das sagt die Karte zu)."""
    from duckpilot import settings as S

    assert not any("gangart" in k or "gait" in k for k in S.EDITABLE)
