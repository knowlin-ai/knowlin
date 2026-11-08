"""Sprachgerüst (0.33) und die Kacheln „Geplant“ unter Erweiterungen."""

import re

import pytest
from fastapi.testclient import TestClient

from duckpilot import __version__, geplant, i18n
from duckpilot import settings as S
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        yield c


def test_german_is_complete_and_other_languages_only_use_its_keys():
    de = i18n._roh("de")
    assert de
    for s in i18n.SPRACHEN:
        roh = i18n._roh(s)
        assert set(roh) <= set(de), f"{s}: Schlüssel ohne deutschen Text {set(roh) - set(de)}"
        for k, v in roh.items():
            assert i18n.platzhalter(v) == i18n.platzhalter(de[k]), (s, k)


def test_missing_text_falls_back_to_german_and_unknown_keys_stay_visible():
    assert i18n.t("kollision.fallen", sprache="en") == "Fallen lassen"            # noch nicht übersetzt
    assert i18n.t("seite.links", sprache="en") == "left"
    assert i18n.t("gibt.es.nicht") == "gibt.es.nicht"
    assert i18n.t("ausweichen.weicht_aus", m=0.314, seite="links") == "Hindernis 0.31 m voraus – weicht links aus"
    assert i18n.katalog("xx") == i18n.katalog("de")
    assert i18n.setze_sprache("xx") == "de" and i18n.sprache() == "de"


def test_language_endpoint(client):
    r = client.get("/api/i18n/en").json()
    assert r["sprache"] == "en" and "de" in r["sprachen"]
    assert r["texte"]["seite.links"] == "left" and r["texte"]["kollision.fallen"] == "Fallen lassen"
    assert client.get("/api/i18n/xx").json()["sprache"] == "de"


def test_planned_tiles_are_all_still_ahead():
    """Bei jedem Release abgleichen: Was ausgeliefert ist, gehört nicht mehr unter „Geplant“."""
    aktuell = tuple(int(x) for x in __version__.split("."))
    for g in geplant.liste():
        assert g["name"] and g["kurz"] and len(g["kurz"]) < 120
        m = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", g["version"])   # 0.37 oder 0.36.1 (Teil 2 eines Release)
        if m:
            v = (int(m[1]), int(m[2]), int(m[3] or 0))
            assert v > aktuell, f"{g['name']} ({g['version']}) ist schon ausgeliefert"
        else:
            assert g["version"] == "ab Lieferung"


def test_planned_tiles_come_with_the_extensions(client):
    r = client.get("/api/skills").json()
    assert r["geplant"] and r["geplant"][0]["version"]


# ── Englisch, Teil 1 (0.34) ───────────────────────────────────────────────────────────────────────────────────────
def test_translated_areas_have_no_german_left_in_the_page():
    """Steuern, Tricks, Einstellungen, Controller, Kollisionsmodus: jeder sichtbare Text steht im Katalog."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import i18n_texte

    assert i18n_texte.fehlend() == []


def test_ui_catalog_templates_keep_their_placeholders():
    ui = i18n.ui_katalog("en")
    assert len(ui) > 500 and i18n.ui_katalog("de") == {}
    for k, v in ui.items():
        assert k.count("#") == v.count("#") and k.count("*") == v.count("*"), k
        assert v.strip(), k


def test_language_setting_and_current_catalog(client):
    assert client.get("/api/i18n/aktuell").json()["sprache"] == "de"
    r = client.post("/api/settings", json={"sprache": "en"}).json()
    assert r["ok"] and "sprache" in r["geaendert"]
    j = client.get("/api/i18n/aktuell").json()
    assert j["sprache"] == "en" and j["ui"]["Steuern"] == "Control" and i18n.sprache() == "en"
    assert not client.post("/api/settings", json={"sprache": "fr"}).json().get("ok", True) or i18n.sprache() == "en"
    client.post("/api/settings", json={"sprache": "de"})
    assert i18n.sprache() == "de"


def test_duck_thinks_and_speaks_in_the_chosen_language(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    for sprache, merkmal in (("de", "Du antwortest auf Deutsch"), ("en", "Always answer in English")):
        rt.agent.config.sprache = sprache
        text = rt.agent._system()
        assert merkmal in text
        assert "Ball schießen, beim Annähern" in text           # Ziel der Aufgabe ist kein Hindernis (Hinweis aus dem Test)


def test_simple_commands_work_in_english_and_stop_always_works():
    from duckpilot.brain.fallback import parse, quick_command

    assert parse("stop") == [("stop", {})] and parse("Stopp!") == [("stop", {})] and parse("freeze") == [("stop", {})]
    assert parse("walk two meters forward") == [("walk", {"distance_m": 2})]
    assert parse("turn right") == [("turn", {"degrees": -90})]
    assert parse("dance and then sit down") == [("dance", {"style": "party", "seconds": 10}),
                                                 ("power", {"action": "sit_down"})]
    assert parse("kick the ball")[0][0] == "_kick" and parse("follow me")[0][0] == "mir_folgen"
    assert quick_command("sit down") and not quick_command("can you dance?")
    assert parse("lauf vor") == [("walk", {"distance_m": 0.4})] and parse("setz dich")[0][1]["action"] == "sit_down"


def test_german_piper_voice_is_not_used_for_english():
    from types import SimpleNamespace

    from duckpilot.voice.speech import Speaker

    sp = Speaker.__new__(Speaker)
    sp.config = SimpleNamespace(stimme_motor="piper", stimme_piper="de_DE-thorsten-medium", sprache="en")
    assert sp.motor() == "browser"
    sp.config.stimme_piper = "en_US-lessac-medium"
    assert sp.motor() == "piper"
    sp.config.sprache, sp.config.stimme_piper = "de", "de_DE-thorsten-medium"
    assert sp.motor() == "piper"


def test_server_translates_the_ducks_own_sentences(tmp_path, monkeypatch):
    """Seit 0.36: Reflex-, Alltags- und Systemsätze der Ente kommen auf Englisch an – angezeigt und gesprochen."""
    assert i18n.ui_text("Angehalten.", "en") == "Stopped."
    assert i18n.ui_text("Eieruhr läuft – ich melde mich in 5 Minuten.", "en") == "Eieruhr is running – I'll let you know in 5 minutes."
    assert i18n.ui_text("laufen +0.40 m", "en") == "walk +0.40 m"
    assert i18n.ui_text("Geht gerade nicht: umgefallen", "en") == "Not possible right now: fallen over"
    assert i18n.ui_text("Angehalten.", "de") == "Angehalten." and i18n.ui_text("Unbekannt hier", "en") == "Unbekannt hier"
    from duckpilot.config import load
    from duckpilot.server.app import Runtime

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    rt.config.sprache = "en"
    m = rt._lokal({"type": "chat", "role": "duck", "text": "Angehalten.", "source": "reflex"})
    assert m["text"] == "Stopped."
    claude = {"type": "chat", "role": "duck", "text": "Angehalten.", "source": "claude"}
    assert rt._lokal(claude) is claude                     # Modellantworten bleiben, wie sie sind
    rt.config.sprache = "de"
    assert rt._lokal({"type": "chat", "role": "duck", "text": "Angehalten.", "source": "reflex"})["text"] == "Angehalten."
