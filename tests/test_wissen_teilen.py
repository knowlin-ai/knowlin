"""Ein Kopf, viele Körper (seit 0.56): geteiltes Wissen sichtbar, Tricks innerhalb einer Familie übernehmen."""

import pytest

from duckpilot.brain import wissen_teilen as W
from duckpilot.brain.memory import HERKUNFT, Memory

KF = [{"t": 0.0, "head_pitch": 0.2}, {"t": 0.5, "head_pitch": -0.2}]


def _mem(tmp_path):
    m = Memory(tmp_path / "m.json")
    m.set_figur("duckpilot")
    tok = HERKUNFT.set("duckpilot:sim")
    m.remember_fact("unsere Katze heißt Momo")
    m.remember_trick("Verbeugung", KF, 1, "tief")
    HERKUNFT.reset(tok)
    m.remember_place("Küche", "sim", 1.0, 0.5, 0.0, "")
    return m


def test_uebersicht_zeigt_geteiltes_und_herkunft(tmp_path):
    m = _mem(tmp_path)
    m.set_figur("wonderduck")
    u = W.uebersicht(m, "wonderduck")
    assert u["geteilt"]["wissen"] == {"anzahl": 1, "von": {"Quacki": 1}}
    assert u["geteilt"]["orte"] == {"anzahl": 1, "zimmer": {"simulator": 1}}
    quacki = next(a for a in u["andere"] if a["modul"] == "duckpilot")
    assert quacki["passt"] and quacki["tricks"] == [{"name": "Verbeugung", "schon_da": False}]


def test_trick_von_quacki_zu_wondi_aber_nicht_zu_stacki(tmp_path):
    m = _mem(tmp_path)
    m.set_figur("wonderduck")
    key = W.trick_uebernehmen(m, "wonderduck", "duckpilot", "Verbeugung")
    t = m.data["tricks"][key]
    assert t["keyframes"] == KF and t["uebernommen_von"] == "duckpilot" and "von Quacki übernommen" in t["beschreibung"]
    assert "Verbeugung" in m.data["tricks_je_figur"]["duckpilot"]          # Original bleibt bei Quacki
    with pytest.raises(ValueError, match="kennt schon"):
        W.trick_uebernehmen(m, "wonderduck", "duckpilot", "Verbeugung")
    m.set_figur("stackchan")
    with pytest.raises(ValueError, match="anderen Körper"):
        W.trick_uebernehmen(m, "stackchan", "duckpilot", "Verbeugung")
    assert W.uebersicht(m, "stackchan")["andere"][0]["passt"] is False
