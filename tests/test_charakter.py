"""Charakter übergeordnet bei Knowlin (seit 0.38.10, Wunsch des Maintainers): Grundcharakter für alle, je Verkörperung eine
Ausprägung darum herum und die Eigenschaften ihrer Gestalt. Knowlin ist anfangs seriös."""

import asyncio
import json

import pytest
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import settings as S
from duckpilot.brain.kopf import art
from duckpilot.config import Config, load
from duckpilot.figuren import FIGUR_KEYS, FIGUREN, GESTALT, FigurenStore, gestalt_standard, gestalt_text
from duckpilot.server.app import Runtime
from duckpilot.server.oberflaeche import seite


@pytest.fixture()
def rt(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return Runtime(load(memory_path=str(tmp_path / "mem.json")))


def test_knowlin_ist_anfangs_serioes():
    c = Config()
    assert c.grund_energie < 0.5 and c.grund_humor < 0.2
    assert "seriös" in art(c.grund_energie, c.grund_humor) and "Witze" in art(c.grund_energie, c.grund_humor)
    assert "verspielt" in art(0.5, 0.8) and "Lebhaft" in art(0.8, 0.8)
    assert "emotions" not in FIGUR_KEYS and "eigenschaften" in FIGUR_KEYS        # Gefühle zeigen gilt für alle


def test_grund_verschieben_laesst_verkoerperungen_stehen(rt, tmp_settings):  # noqa: F811
    """Wunsch des Maintainers 5.11.: Knowlins Grundcharakter wirkt nur auf Knowlin – die Verkörperungen wandern nicht mit."""
    asyncio.run(rt.apply_settings({"energie": 0.6, "humor": 0.3}))
    rt.figuren.setze("reachy_mini", {"energie": 0.4, "humor": 0.2})
    asyncio.run(rt.apply_settings({"grund_energie": 0.45, "grund_humor": 0.3}))
    assert rt.config.grund_energie == 0.45 and rt.config.energie == pytest.approx(0.6) and rt.config.humor == pytest.approx(0.3)
    reachy = rt.figuren.profil("reachy_mini")
    assert reachy["energie"] == pytest.approx(0.4) and reachy["humor"] == pytest.approx(0.2)
    gespeichert = json.loads(tmp_settings.read_text(encoding="utf-8"))
    assert gespeichert["grund_humor"] == 0.3 and gespeichert["humor"] == pytest.approx(0.3)
    assert "Witze" not in rt.kopf._system()                                          # Knowlin selbst ändert sich


def test_startwerte_passen_zum_koerper():
    from duckpilot.motion.character import persona

    start = {m: FIGUREN[m]["start"] for m in FIGUREN}
    assert start["duckpilot"]["energie"] > 0.6 and 0.3 < start["duckpilot"]["humor"] < 0.5     # lebhaft-verspielt
    assert start["reachy_mini"]["energie"] < 0.34 and start["reachy_mini"]["humor"] < 0.5      # ruhig-neugierig
    assert start["open_duck_mini"]["humor"] >= 0.5                                              # tollpatschig-verspielt
    assert len({persona(s["energie"], s["humor"]) for s in start.values()}) == 3               # drei verschiedene


def test_figur_profil_verschiebt_eine_verkoerperung_einzeln(rt, tmp_settings):  # noqa: F811
    gesendet = []

    async def mit(msg):
        gesendet.append(msg)
    rt.broadcast = mit
    asyncio.run(rt.apply_settings({"energie": 0.6, "humor": 0.3}))
    # schlafende Verkörperung: nur ihr Profil in figuren.json, die wache bleibt
    r = asyncio.run(rt.apply_settings({"figur_profil": {"modul": "reachy_mini", "energie": 0.15, "humor": 0.8}}))
    assert r["ok"] and r["geaendert"] == ["figur_profil"]
    assert rt.figuren.profil("reachy_mini")["energie"] == 0.15 and rt.figuren.profil("reachy_mini")["humor"] == 0.8
    assert rt.config.energie == 0.6 and rt.config.humor == 0.3
    assert "figur_profil" not in json.loads(tmp_settings.read_text(encoding="utf-8"))
    assert any(m.get("type") == "init" for m in gesendet)                          # das Feld zeigt den neuen Platz
    reachy = next(f for f in rt.init_message()["config"]["verkoerperungen"] if f["modul"] == "reachy_mini")
    assert reachy["energie"] == 0.15 and reachy["humor"] == 0.8
    # die wache Verkörperung: über die normalen Werte energie/humor
    r = asyncio.run(rt.apply_settings({"figur_profil": {"modul": "duckpilot", "energie": 0.9, "humor": 0.1}}))
    assert set(r["geaendert"]) == {"energie", "humor"} and rt.engine.config.energie == 0.9
    assert json.loads(tmp_settings.read_text(encoding="utf-8"))["energie"] == 0.9
    with pytest.raises(ValueError):
        asyncio.run(rt.apply_settings({"figur_profil": {"modul": "roboterhund", "energie": 0.5}}))
    with pytest.raises(ValueError):
        asyncio.run(rt.apply_settings({"figur_profil": {"modul": "reachy_mini", "energie": 7}}))


def test_knowlin_feld_punkte_ziehbar():
    from pathlib import Path

    static = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"
    js = (static / "charakter.js").read_text(encoding="utf-8")
    assert "figur_profil: { modul, energie, humor }" in js and "id: f.modul" in js
    pad = (static / "personality.js").read_text(encoding="utf-8")
    assert "onMarke" in pad and "ArrowLeft" in pad[pad.index("markeZiehbar(d, m) {"):]   # auch per Tastatur
    assert "stopPropagation" in pad                                                     # Knowlins Punkt bleibt
    html = seite()
    assert "wandern mit" not in html and "um ihren Charakter einzeln anzupassen" in html


def test_eigenschaften_der_gestalt(rt):
    assert gestalt_standard("reachy_mini") == ["antennen", "zuhoeren", "trocken"]
    assert "Schnabel" in gestalt_text("duckpilot", None) and gestalt_text("duckpilot", []) == ""
    assert "Schnabel" not in gestalt_text("reachy_mini", ["schnabel"])               # nur, was die Gestalt hat
    liste = rt.gestalt_liste()
    assert [e["id"] for e in liste] == [e["id"] for e in GESTALT["duckpilot"]] and liste[0]["an"]
    asyncio.run(rt.apply_settings({"eigenschaften": ["watscheln"]}))
    assert [e["id"] for e in rt.gestalt_liste() if e["an"]] == ["watscheln"]
    assert "watschelt" in rt.agent._system() and "klappert vor Freude" not in rt.agent._system()
    with pytest.raises(ValueError):
        S.validate({"eigenschaften": ["fliegen"]})


def test_neue_verkoerperung_bekommt_ihre_gestalt(tmp_path):
    store = FigurenStore(tmp_path)
    neu = store.wechsel("duckpilot", "reachy_mini", {"duck_name": "Quacki", "eigenschaften": ["schnabel"]})
    assert neu["eigenschaften"] is None                                              # Vorgabe der Gestalt
    assert store.profil("duckpilot")["eigenschaften"] == ["schnabel"]                # Quacki behält seine


def test_grundcharakter_als_feld_mit_verkoerperungen(rt):
    from pathlib import Path

    static = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"
    html = seite()
    assert 'id="pad-knowlin"' in html and 'data-set="grund_humor"' not in html          # Feld statt Schieberegler
    js = (static / "charakter.js").read_text(encoding="utf-8")
    assert "schluessel: ['grund_energie', 'grund_humor']" in js and "goofy: false" in js
    figuren = rt.init_message()["config"]["verkoerperungen"]
    assert {f["modul"] for f in figuren} >= {"duckpilot", "reachy_mini"}
    assert all(0 <= f["energie"] <= 1 and 0 <= f["humor"] <= 1 for f in figuren)
