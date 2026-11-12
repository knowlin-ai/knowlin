"""Wertekern (seit 0.38.42, Etappe G1): Werte gehen an jedes Sprachmodell, jede Grenze ist mit einem Test belegt, und
die Oberfläche zeigt genau diese Texte."""

import re
from pathlib import Path

import pytest
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import werte as W
from duckpilot.brain.anbieter import NOTE
from duckpilot.brain.local import LOCAL_NOTE
from duckpilot.config import load
from duckpilot.server.app import Runtime

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def rt(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return Runtime(load(memory_path=str(tmp_path / "mem.json")))


def test_jedes_gehirn_bekommt_die_werte(rt):
    """Claude, lokales und anderes Modell bauen auf `_system()` auf (lokal und anbieter hängen nur Hinweise an);
    der Kopf hat seinen eigenen Prompt – alle tragen denselben Wertekern."""
    koerper, kopf = rt.agent._system(), rt.kopf._system()
    for w in W.WERTE:
        assert w[0] in koerper and w[0] in kopf
    assert "Werte" not in NOTE and "Werte" not in LOCAL_NOTE          # nichts überschreibt sie
    assert W.prompt("en").count("\n- ") == len(W.WERTE) and "always apply" in W.prompt("en")


def test_jede_grenze_ist_mit_einem_test_belegt():
    for text_de, text_en, beleg in W.GRENZEN:
        datei, name = beleg.split("::")
        quelle = (ROOT / datei).read_text(encoding="utf-8")
        assert re.search(rf"^def {name}\(", quelle, re.M), f"{text_de}: {beleg} fehlt"
        assert text_en and text_de.endswith(".")


def test_oberflaeche_zeigt_genau_diese_texte():
    html = (ROOT / "duckpilot" / "server" / "static" / "index.html").read_text(encoding="utf-8")
    karte = html[html.index('id="werte-karte"'):]
    karte = karte[:karte.index("</section>")]
    eintraege = re.findall(r"<li>(.*?)</li>", karte)
    assert eintraege == [w[0] for w in W.WERTE] + [g[0] for g in W.GRENZEN]
