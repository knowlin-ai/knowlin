"""Herkunft (seit 0.38.10, Wunsch des Maintainers): Hirnaktivität und Gedächtnis zeigen, wo Knowlin etwas gelernt hat – ohne
Körper (Kopf) oder in welcher Verkörperung, im Simulator oder echt. Alte Einträge bleiben „unbekannt“."""

import asyncio
from pathlib import Path

import pytest
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.brain.erfahrung import Erfahrungsnetz, key
from duckpilot.brain.memory import HERKUNFT, Memory
from duckpilot.config import load
from duckpilot.server.app import Runtime


@pytest.fixture()
def rt(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return Runtime(load(memory_path=str(tmp_path / "mem.json")))


def test_netz_zaehlt_herkunft_je_knoten_und_verbindung(tmp_path):
    netz = Erfahrungsnetz(tmp_path / "e.json")
    ball, freude = key("ding", "Ball"), key("gefuehl", "Freude")
    netz.erleben({ball: "Ball", freude: "Freude"}, herkunft="duckpilot:sim")
    netz.erleben({ball: "Ball"}, herkunft="kopf")
    netz.erleben({ball: "Ball"})                                      # ohne Angabe: zählt nicht mit
    assert netz.knoten[ball]["herkunft"] == {"duckpilot:sim": 1, "kopf": 1}
    kante = next(iter(netz.kanten.values()))
    assert kante["herkunft"]["duckpilot:sim"] >= 1
    msg = netz.message()
    assert next(k for k in msg["knoten"] if k["id"] == ball)["herkunft"] == {"duckpilot:sim": 1, "kopf": 1}


def test_gedaechtnis_merkt_sich_wer(tmp_path):
    mem = Memory(str(tmp_path / "m.json"))
    mem.herkunft = lambda: "reachy_mini:sim"
    mem.remember_fact("Der Mensch spielt Gitarre")
    tok = HERKUNFT.set("kopf")
    try:
        mem.remember_preference("leiser sprechen")
    finally:
        HERKUNFT.reset(tok)
    assert mem.data["wissen"][-1]["von"] == "reachy_mini:sim" and mem.data["vorlieben"][-1]["von"] == "kopf"


def test_runtime_herkunft_kopf_und_koerper(rt):
    assert rt.erfahrung.herkunft() == "duckpilot:sim"
    out = []

    async def bc(m):
        out.append(m)
    rt.broadcast = bc
    asyncio.run(rt.chat("Ich heiße Kim", "text", "kopf"))       # der Kopf hört – und merkt sich als „kopf“
    asyncio.run(rt.chat("toll gemacht", "text"))                # die Verkörperung hört
    lob = rt.erfahrung.netz.knoten.get(key("rueckmeldung", "lob"))
    assert lob and lob["herkunft"].get("duckpilot:sim") == 1
    namen = rt.herkunft_namen()
    assert namen["kopf"] == "Knowlin" and namen["duckpilot"] == "Quacki"
    assert rt.memory_message()["herkuenfte"] == namen


def test_oberflaeche_zeigt_herkunft():
    static = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
    hirn = (static / "hirn.js").read_text(encoding="utf-8")
    assert "passt(k.herkunft, filter)" in hirn and "herkunftListe(" in hirn
    assert 'id="brain-herkunft"' in (static / "index.html").read_text(encoding="utf-8")
    assert "gemerkt von" in (static / "gedaechtnis_ui.js").read_text(encoding="utf-8")   # seit 0.38.17 eigenes Modul
