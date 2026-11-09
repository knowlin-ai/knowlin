"""Hinweise vom 7.11. (0.38.24): „beim Öffnen der Anwendung waren bei den Microducks direkt mehrere – ich
dachte, per Default starten wir erstmal mit einer“ und „nur die Kreise rausnehmen bei der Ansicht Hirnaktivität“."""

import json

from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.server.app import STATIC, Runtime
from duckpilot.server.oberflaeche import seite


def test_jeder_start_beginnt_mit_einer_ente(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tmp_settings.write_text(json.dumps({"modul": "duckpilot", "backend": "sim", "sim_physik": False, "weitere_enten": 3}))
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    assert rt.config.weitere_enten == 0 and S.load_user_settings()["weitere_enten"] == 0
    assert rt.schwarm is not None and len(rt.schwarm.enten) == 0
    # in der laufenden Sitzung lassen sie sich dazuholen – erst der nächste Start beginnt wieder allein
    rt.schwarm.anzahl(2)
    assert len(rt.schwarm.enten) == 2


def test_hinweis_sagt_es():
    html = seite()
    assert "Knowlin startet immer mit einer Ente" in html and "Gäste bleiben bis zum Beenden" in html


def test_hirnaktivitaet_ohne_kreise():
    js = (STATIC / "hirn.js").read_text(encoding="utf-8")
    assert "function bahnen(" not in js and "bahnen(w, hgt)" not in js
    hintergrund = js[js.index("function kopfHintergrund("):js.index("// Impulse:")]
    assert "ctx.stroke()" not in hintergrund                          # die Hülle leuchtet nur, ohne Umrisslinien


def test_auch_nach_koerperwechsel_allein(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    """Fund 7.11. abends: „wieso startet die Microduck gleich wieder mit mehreren Enten?“ – das Profil der Microduck
    hielt noch „3 weitere“ und holte sie beim Wechsel in die Microduck zurück."""
    import asyncio

    from duckpilot.figuren import FigurenStore

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tmp_settings.write_text(json.dumps({"modul": "reachy_mini", "backend": "sim", "sim_physik": False}))
    (tmp_settings.parent / "figuren.json").write_text(json.dumps({"_stand": 3, "duckpilot": {"weitere_enten": 3}}))
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    assert FigurenStore(tmp_settings.parent).profil("duckpilot").get("weitere_enten", 0) == 0   # beim Start bereinigt
    asyncio.run(rt.apply_settings({"modul": "duckpilot"}))
    assert rt.config.modul == "duckpilot" and rt.config.weitere_enten == 0
    # in der Sitzung dazuholen, wegwechseln und zurück: wieder allein
    asyncio.run(rt.apply_settings({"weitere_enten": 2}))
    asyncio.run(rt.apply_settings({"modul": "open_duck_mini"}))
    asyncio.run(rt.apply_settings({"modul": "duckpilot"}))
    assert rt.config.weitere_enten == 0 and len(rt.schwarm.enten) == 0
