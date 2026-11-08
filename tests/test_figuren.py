"""Figuren je Körper (seit 0.38.3): eigener Name, Charakter, Stimme, Tricks – gemeinsames Wissen und Umgebung."""

import asyncio

from fastapi.testclient import TestClient
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot.backends.reachy import ReachyMiniSim
from duckpilot.config import load
from duckpilot.figuren import FIGUR_KEYS, FigurenStore
from duckpilot.server.app import Runtime, create_app


def test_wechsel_sichert_und_laedt_profile(tmp_path, tmp_settings):  # noqa: F811
    store = FigurenStore(tmp_path)
    quacki = {"duck_name": "Quacki", "energie": 0.8, "humor": 0.9, "entenhaft": 0.45, "entenlaute": "oft",
              "wake_word": "ente", "weitere_enten": 2, "stimme_motor": "qwen", "stimme_qwen": "abc"}
    reachy = store.wechsel("duckpilot", "reachy_mini", quacki)
    assert reachy["duck_name"] == "Reachy" and reachy["wake_word"] == "reachy"
    assert reachy["entenhaft"] == 0.0 and reachy["entenlaute"] == "aus" and reachy["weitere_enten"] == 0
    assert reachy["stimme_motor"] == "piper"                     # Quackis entworfene Stimme bleibt bei Quacki
    zurueck = store.wechsel("reachy_mini", "duckpilot", {**reachy, "energie": 0.3})
    assert zurueck["duck_name"] == "Quacki" and zurueck["energie"] == 0.8 and zurueck["stimme_qwen"] == "abc"
    assert store.profil("reachy_mini")["energie"] == 0.3        # Reachys eigene Änderung bleibt bei Reachy
    assert set(FIGUR_KEYS) >= {"duck_name", "energie", "humor", "stimme_piper", "entenhaft", "weitere_enten"}


def test_koerperwechsel_ist_figurwechsel(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        rt.memory.remember_trick("winken", [{"t": 0.5, "head_yaw": 0.3}])
        rt.memory.remember_place("küche", "sim", 1.0, 2.0, 0.0)
        c.post("/api/settings", json={"energie": 0.9})
        r = c.post("/api/settings", json={"modul": "reachy_mini", "backend": "sim", "sim_physik": False}).json()
        assert r["ok"] and isinstance(rt.backend, ReachyMiniSim)
        assert rt.config.duck_name == "Reachy" and rt.config.entenlaute == "aus" and rt.config.energie == 0.3
        assert "winken" not in rt.memory.data["tricks"] and "küche" in rt.memory.data["orte"]   # Umgebung teilen sie
        text = rt.agent._system()
        assert "KEINE Ente" in text and "Quacki (Microduck)" in text and "*quak*" not in text
        figuren = {m["id"]: m.get("figur") for m in c.get("/api/module").json()["module"]}
        assert figuren["reachy-mini"]["aktiv"] and figuren["duckpilot"]["name"] == "Quacki"
        c.post("/api/settings", json={"modul": "duckpilot"})
        assert rt.config.duck_name == "Quacki" and rt.config.energie == 0.9 and "winken" in rt.memory.data["tricks"]
        assert "Reachy (Reachy Mini)" in rt.agent._system()


def test_reachy_macht_keine_entenlaute():
    async def go():
        sim = ReachyMiniSim(realtime=False, seed=1)
        return await sim.sound("quak")
    r = asyncio.run(go())
    assert not r.accepted and "keine Ente" in r.reason


def _frisch(tmp_settings, tmp_path, werte):  # noqa: F811
    import json

    tmp_settings.write_text(json.dumps(werte), encoding="utf-8")
    return Runtime(load(memory_path=str(tmp_path / "mem.json")))


def test_frische_einstellungen_mit_reachy_heissen_nicht_quacki(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    """Prüfbefund 5.11.: settings.json nur mit modul=reachy_mini → die Verkörperung hieß „Quacki“ mit Weckwort „ente“
    (die Grundwerte von Config gehören der Microduck). Ursache: Startwerte kamen nur beim Körperwechsel."""
    import json

    from duckpilot.figuren import FIGUREN, start_ergaenzen

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "figuren.json").write_text(json.dumps({"version": 3, "profile": {}}), encoding="utf-8")  # keine Reparatur
    rt = _frisch(tmp_settings, tmp_path, {"backend": "sim", "modul": "reachy_mini"})
    assert rt.config.duck_name == "Reachy" and rt.config.wake_word == "reachy" and rt.config.entenlaute == "aus"
    assert json.loads(tmp_settings.read_text(encoding="utf-8"))["duck_name"] == "Reachy"
    rt = _frisch(tmp_settings, tmp_path, {"backend": "sim", "modul": "open_duck_mini", "duck_name": "Ottilie"})
    assert rt.config.duck_name == "Ottilie" and rt.config.wake_word == "odi"        # Selbstgesetztes bleibt
    assert rt.config.energie == FIGUREN["open_duck_mini"]["start"]["energie"]
    assert start_ergaenzen("duckpilot", {}) == {}                                   # Quackis Werte sind die Grundwerte


def test_gruss_in_der_gewaehlten_sprache(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    from duckpilot import i18n

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = _frisch(tmp_settings, tmp_path, {"backend": "sim", "modul": "open_duck_mini", "sprache": "en", "tts": True})
    gesagt = []

    async def sagt(text):
        gesagt.append(text)
    rt._duck_says = sagt
    try:
        asyncio.run(rt._begruessen())
    finally:
        i18n.setze_sprache("de")
    assert gesagt and "ready" in gesagt[0] and "Odi" in gesagt[0] and "bereit" not in gesagt[0]


def test_leerlauf_texte_auf_englisch(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    from duckpilot import i18n
    from duckpilot.motion.character import MESSAGES

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = _frisch(tmp_settings, tmp_path, {"backend": "sim", "sprache": "en"})
    try:
        texte = {e["name"]: e["text"] for e in rt.emotions_catalog() if e["art"] == "charakter"}
    finally:
        i18n.setze_sprache("de")
    assert texte["aufhorchen"] == "pricks up its ears" and texte["mustern"] == "studies the room"
    for name in MESSAGES:                                       # jede Geste hat beide Sprachen
        assert i18n.t(f"leerlauf.{name}", "de") == MESSAGES[name] and i18n.t(f"leerlauf.{name}", "en") != MESSAGES[name]


def test_vergleich_mit_knowlin_ganz_aus_dem_katalog():
    from pathlib import Path

    from duckpilot import i18n

    js = (Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static" / "charakter.js").read_text("utf-8")
    assert "t('charakter.vergleich'" in js and "tr(`${name} ist" not in js
    satz = i18n.t("charakter.vergleich", "en", name="Reachy",
                  wie=f"{i18n.t('charakter.etwas', 'en')} {i18n.t('charakter.lebhafter', 'en')}")
    assert satz == "Reachy is a little livelier than Knowlin."
