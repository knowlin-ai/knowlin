"""Knowlin im Kopf (seit 0.38.8, Quickstart-Entwurf): Auf der Startseite antwortet der gemeinsame Kopf – ohne Körper,
ohne Entenlaute, mit eigenem Verlauf. Für Körperliches weckt er eine Figur; „Stopp“ wirkt trotzdem sofort."""

import asyncio
import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import remote as R
from duckpilot.backends.open_duck import OpenDuckSim
from duckpilot.backends.reachy import ReachyMiniSim
from duckpilot.brain.kopf import EIGENE_TOOLS, KOPF_TOOLS, KopfRunner
from duckpilot.config import load
from duckpilot.server.app import Runtime
from duckpilot.server.oberflaeche import seite
from duckpilot.voice import speech as SP

STATIC = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"


@pytest.fixture()
def rt(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return Runtime(load(memory_path=str(tmp_path / "mem.json")))


def _frage(rt, text, an="kopf"):
    out = []

    async def bc(m):
        out.append(m)
    rt.broadcast = bc
    asyncio.run(rt.chat(text, "text", an))
    return out


def _antwort(out):
    return next(m for m in out if m.get("type") == "chat" and m.get("role") == "duck")


def test_kopf_antwortet_als_knowlin_ohne_ki(rt):
    a = _antwort(_frage(rt, "Wie heißt du?"))
    assert a["an"] == "kopf" and a["text"] == "Ich bin Knowlin. Eine intelligente, selbstlernende Lebensform." and "wecken" not in a
    assert _antwort(_frage(rt, "Hallo"))["text"] == "Hallo. Ich bin Knowlin."
    kann = _antwort(_frage(rt, "Was kannst du?"))["text"]
    assert "nutze ich einen meiner Roboter: Quacki, Reachy, Odi oder Ari" in kann          # Ari (SO-101) seit 0.38.47
    for zweideutig in ("bewohn", "Körperliche"):                     # Hinweis aus dem Test 5.11.: klang anzüglich
        assert zweideutig not in kann
    assert "Für Bewegung nutzt du Roboter" in rt.kopf._system() and "Körper bewohnen (" not in rt.kopf._system()
    # was er ohne KI-Modell nicht versteht, sagt er ehrlich – und wo man eins einstellt
    assert "Einstellungen → KI-Modell" in _antwort(_frage(rt, "erzähl mir was über Quacki"))["text"]


def test_koerperliches_fragt_nach_dem_koerper_und_ja_geht_hinein(rt):
    a = _antwort(_frage(rt, "tanz"))
    assert a["text"] == "Dafür brauche ich einen Körper. Quacki, die Microduck, kann das – soll ich Quacki nutzen?"
    assert a["vorschlag"] == {"modul": "duckpilot", "figur": "Quacki", "auftrag": "tanz"} and "wecken" not in a
    assert not rt.im_koerper                                  # ungefragt geht er in keinen Körper
    ja = _antwort(_frage(rt, "Ja, gern"))
    assert ja["text"] == "Gut. Ich gehe in Quacki." and ja["wecken"] == "duckpilot" and ja["auftrag"] == "tanz"
    assert "wecken" not in _antwort(_frage(rt, "ja"))         # der Vorschlag gilt nur einmal


def test_nein_bleibt_ohne_koerper(rt):
    _frage(rt, "lauf vor")
    a = _antwort(_frage(rt, "nein, lieber nicht"))
    assert a["text"] == "Gut. Ich bleibe ohne Körper." and "wecken" not in a and rt.kopf.runner.vorschlag is None


def test_vorschlag_verfaellt(rt, monkeypatch):
    from duckpilot.brain import kopf as K

    _frage(rt, "tanz")
    rt.kopf.runner.vorschlag["seit"] -= K.VORSCHLAG_GILT_S + 1
    assert "wecken" not in _antwort(_frage(rt, "ja"))


def test_figur_passt_zum_wunsch(rt):
    rt.config.modul = "reachy_mini"                            # Reachy hatte zuletzt einen Körper
    asyncio.run(rt._swap_body())
    assert _antwort(_frage(rt, "lauf vor"))["vorschlag"]["modul"] == "duckpilot"    # Reachy hat keine Beine
    a = _antwort(_frage(rt, "tanz"))
    assert a["vorschlag"]["modul"] == "reachy_mini" and "der Reachy Mini" in a["text"]   # tanzen kann Reachy
    rt.config.modul = "open_duck_mini"
    asyncio.run(rt._swap_body())
    assert _antwort(_frage(rt, "zeig mir einen Purzelbaum"))["vorschlag"]["modul"] == "duckpilot"  # Odi kann keinen
    assert _antwort(_frage(rt, "lauf vor"))["vorschlag"]["modul"] == "open_duck_mini"


def test_koerper_tabelle_passt_zu_den_koerpern():
    from duckpilot.backends.sim import SimBackend
    from duckpilot.brain.kopf import kann
    from duckpilot.brain.tools import fehlt_dem_koerper

    echt = {"duckpilot": SimBackend(realtime=False, seed=1), "open_duck_mini": OpenDuckSim(realtime=False, seed=1),
            "reachy_mini": ReachyMiniSim(realtime=False, seed=1)}
    for modul, be in echt.items():
        for w in ("walk", "turn", "dance", "head", "emote", "explore", "apportieren", "schiessen", "laser_folgen",
                  "trick_vom_hub", "antennen"):
            assert kann(modul, w) == (fehlt_dem_koerper(w, be) is None), (modul, w)
        for skill in ("sit_toggle", "roulade", "kick_left"):
            assert kann(modul, "skill", {"name": skill}) == (skill in be.skills()), (modul, skill)


@pytest.mark.parametrize("satz,modul", [("weck Quacki", "duckpilot"), ("Reachy wecken", "reachy_mini"),
                                        ("wechsle zu Odi", "open_duck_mini"), ("wake Reachy", "reachy_mini"),
                                        ("bitte weck quacki auf", "duckpilot"), ("nimm Quacki", "duckpilot")])
def test_figur_wecken_per_satz(rt, satz, modul):
    a = _antwort(_frage(rt, satz))
    assert a["wecken"] == modul and "auftrag" not in a


def test_kein_wecken_mitten_im_satz(rt):
    a = _antwort(_frage(rt, "erzähl mir was zu Quacki"))
    assert "wecken" not in a and "vorschlag" not in a


def test_namen_im_gespraech_und_in_den_einstellungen(rt, tmp_settings):  # noqa: F811
    a = _antwort(_frage(rt, "Ich heiße anna"))
    assert a["text"] == "Hallo, Anna." and rt.config.nutzer_name == "Anna"
    assert json.loads(tmp_settings.read_text(encoding="utf-8"))["nutzer_name"] == "Anna"   # bleibt auf dem PC
    assert _antwort(_frage(rt, "Ich nenne dich Nova"))["text"] == "Nova. Den Namen behalte ich."
    assert rt.config.kopf_name == "Nova"
    assert _antwort(_frage(rt, "Wer bist du?"))["text"] == "Ich bin Nova. Eine intelligente, selbstlernende Lebensform."
    assert _antwort(_frage(rt, "Hallo"))["text"] == "Hallo, Anna. Ich bin Nova."
    assert rt.kopf._system().startswith("Du bist Nova: eine intelligente, selbstlernende Lebensform.")
    ctx = json.loads(rt.kopf._context("x").removeprefix("[Kontext] "))
    assert ctx["dein_name"] == "Nova" and ctx["mensch"] == "Anna"
    # „sag hallo“ ist kein Name
    assert rt.config.nutzer_name == "Anna" and "Hallo" not in _antwort(_frage(rt, "sag hallo"))["text"][:6]


def test_namen_pruefen():
    from duckpilot import settings as S

    assert S.validate({"kopf_name": ""})["kopf_name"] == "Knowlin"           # leer = Knowlin
    assert S.validate({"nutzer_name": ""})["nutzer_name"] == ""               # leer = „Hallo Mensch“
    with pytest.raises(ValueError):
        S.validate({"kopf_name": "x" * 25})
    with pytest.raises(ValueError):
        S.validate({"nutzer_name": "x" * 41})


def test_stopp_wirkt_auch_vom_kopf(rt):
    out = _frage(rt, "stopp")
    a = _antwort(out)
    assert a["text"] == "Angehalten." and a["an"] == "kopf" and a["source"] == "reflex"
    assert rt.engine.estop_at > 0


def test_kopf_hat_eigenen_verlauf_und_quakt_nie(rt):
    rt.agent.history.append({"role": "user", "content": [{"type": "text", "text": "Figur"}]})
    _frage(rt, "Wie heißt du?")
    assert len(rt.agent.history) == 1                          # das Gespräch der Figur bleibt, wie es war
    rt.config.modul = "duckpilot"                              # auch wenn die Figur eine Ente ist
    assert rt._ohne_ente("Quak! Hallo.", kopf=True) == "Hallo."
    assert rt._ohne_ente("Quak! Hallo.") == "Quak! Hallo."


def test_figur_bekommt_ihre_nachrichten_ohne_kopf_marke(rt):
    out = _frage(rt, "Wie heißt du?", an="figur")
    assert all("an" not in m for m in out if m.get("type") == "chat")
    assert "Quacki" in _antwort(out)["text"]


def test_werkzeuge_des_kopfes(rt):
    runner = KopfRunner(rt.runner, rt.kopf_figuren)
    namen = [t["name"] for t in runner.tools()]
    assert set(namen) <= set(KOPF_TOOLS) | set(EIGENE_TOOLS) and namen[-3:] == list(EIGENE_TOOLS)
    rem = next(t for t in runner.tools() if t["name"] == "remember")
    assert rem["input_schema"]["properties"]["kind"]["enum"] == ["vorliebe", "wissen"]
    assert "keyframes" not in rem["input_schema"]["properties"]
    wecken = next(t for t in runner.tools() if t["name"] == "figur_wecken")
    assert wecken["input_schema"]["properties"]["modul"]["enum"] == ["duckpilot", "reachy_mini", "open_duck_mini", "so101"]
    r = asyncio.run(runner.run("walk", {"meter": 1}))
    assert not r["ok"] and "Ohne Körper" in r["fehler"]
    assert not asyncio.run(runner.run("remember", {"kind": "trick", "name": "x"}))["ok"]
    assert asyncio.run(runner.run("figur_wecken", {"modul": "reachy_mini", "auftrag": "nick"}))["auftrag"] == "nick"
    assert not asyncio.run(runner.run("figur_wecken", {"modul": "nix"}))["ok"]
    assert not asyncio.run(runner.run("namen_setzen", {"wer": "kopf", "name": "Nova"}))["ok"]   # ohne Einstellungen
    tok = R.REMOTE_TURN.set(True)
    try:
        assert "nur am PC" in runner.wecken("duckpilot")["fehler"]
    finally:
        R.REMOTE_TURN.reset(tok)


class _Block(SimpleNamespace):
    def model_dump(self, exclude_none=True):
        return {k: v for k, v in vars(self).items() if v is not None}


class _FakeClaude:
    """Schlägt erst einen Körper vor, dann antwortet es mit Text – wie Claude, ohne Netz."""

    def __init__(self):
        self.calls = []
        self.messages = self

    async def create(self, **kw):
        self.calls.append(kw)
        if len(self.calls) == 1:
            return SimpleNamespace(stop_reason="tool_use", usage=None, content=[
                _Block(type="tool_use", id="t1", name="koerper_vorschlagen",
                       input={"modul": "duckpilot", "auftrag": "Zeig mir einen kleinen Tanz"})])
        return SimpleNamespace(stop_reason="end_turn", usage=None, content=[
            _Block(type="text", text="*quak* Dafür brauche ich einen Körper. Soll ich Quacki nutzen?")])


def test_kopf_mit_claude_schlaegt_vor_und_ja_geht_ohne_claude(rt):
    fake = _FakeClaude()
    rt.agent.client = fake
    a = _antwort(_frage(rt, "Kannst du mir zeigen, wie du tanzt?"))
    assert a["vorschlag"]["modul"] == "duckpilot" and a["vorschlag"]["auftrag"] == "Zeig mir einen kleinen Tanz"
    assert a["source"] == "claude" and "quak" not in a["text"].lower() and "wecken" not in a
    system = fake.calls[0]["system"][0]["text"]
    assert system.startswith("Du bist Knowlin: eine intelligente, selbstlernende Lebensform.") and "seriös" in system
    assert {t["name"] for t in fake.calls[0]["tools"]} <= set(KOPF_TOOLS) | set(EIGENE_TOOLS)
    assert "[Kontext]" in fake.calls[0]["messages"][0]["content"][0]["text"]
    assert len(rt.kopf.history) == 4 and rt.agent.history == []
    ja = _antwort(_frage(rt, "ja"))                       # die Zustimmung braucht kein KI-Modell
    assert ja["wecken"] == "duckpilot" and ja["auftrag"] == "Zeig mir einen kleinen Tanz" and len(fake.calls) == 2


def test_kopf_ohne_netz_faellt_auf_einfache_saetze(rt):
    class Kaputt:
        messages = None

        def __init__(self):
            self.messages = self

        async def create(self, **kw):
            raise ConnectionError("offline")
    rt.agent.client = Kaputt()
    a = _antwort(_frage(rt, "Wie spät ist es?"))
    assert a["source"] == "einfach" and a["error"] and rt.kopf.history == []


class _Cfg:
    stimme_motor = "piper"
    stimme_piper = "kerstin"
    stimme_qwen = ""
    qwen_qualitaet = "schnell"
    entenhaft = 0.6
    entenlaute = "oft"
    modul = "duckpilot"


def test_kopf_spricht_ohne_entenfilter(tmp_path):
    sp = SP.Speaker(tmp_path, _Cfg())
    assert sp.style("ausgeglichen", False, 0.5, motor="piper").entenhaft == 0.6
    assert sp.style("ausgeglichen", False, 0.5, motor="piper", ente=False).entenhaft == 0.0
    sp.rng = random.Random(1)
    plan = sp.prepare("Hallo. Wie geht es dir? Schön, dich zu sehen. Ich bin da.", ente=False)
    assert all(i["art"] == "text" for i in plan["teile"])


def test_startseite_quickstart_aufbau():
    html = seite()
    start = html[html.index('id="view-start"'):html.index('id="view-dashboard"')]
    # oben der Kopf mit Gruß und Dialog, darunter die Figuren
    assert start.index('id="mind"') < start.index('id="kopf-gruss"') < start.index('id="kopf-form"') < start.index('id="start-module"')
    assert ">Hallo Mensch<" in start and 'role="log"' in start and 'for="kopf-text"' in start
    ui = json.loads((Path(__file__).resolve().parents[1] / "duckpilot" / "i18n" / "ui_en.json").read_text(encoding="utf-8"))
    assert ui["Hallo Mensch"] == "Hello human"
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "msg.an === 'kopf'" in app and "...(imKopf ? { an: 'kopf' } : {})" in app
    assert "send: extra.kopf ? null : send" in app               # der Kopf bewegt keinen Schnabel
    mind = (STATIC / "mind.js").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in mind and "IntersectionObserver" in mind and "document.hidden" in mind


def test_kopf_hat_eigene_waehlbare_stimme(tmp_path, monkeypatch):
    """Seit 0.38.10: Knowlins Stimme ist wählbar (Piper, entworfen, Browser) – ohne künstliches Absenken."""
    from duckpilot.voice import tts

    assert "tiefe" not in tts.Style.__dataclass_fields__                     # das Absenken ist raus
    cfg = _Cfg()
    cfg.kopf_stimme_motor, cfg.kopf_stimme_piper, cfg.kopf_stimme_qwen = "piper", "thorsten", ""
    sp = SP.Speaker(tmp_path, cfg)
    piper = sp.synth.piper
    monkeypatch.setattr(piper, "installed", lambda: True)
    geladen = {"kerstin"}
    monkeypatch.setattr(piper, "has_voice", lambda v: v in geladen)
    plan = sp.prepare_kopf("Ich bin Knowlin.")
    assert plan["motor"] == "browser" and plan["stimme"] == "kopf"          # Thorsten fehlt: Browser, ganz normal
    assert cfg.stimme_piper == "kerstin" and cfg.modul == "duckpilot"        # die Verkörperung bleibt, wie sie war
    geladen.add("thorsten")
    gerechnet = []

    async def go():
        monkeypatch.setattr(sp, "_render", lambda text, motor, voice, st, q: gerechnet.append((motor, voice, st)))
        p = sp.prepare_kopf("Hallo. Ich bin da.")
        await asyncio.sleep(0.05)
        return p
    p = asyncio.run(go())
    assert p["motor"] == "piper" and all("id" in t for t in p["teile"]) and all(t["art"] == "text" for t in p["teile"])
    motor, voice, st = gerechnet[0]
    assert voice == "thorsten" and st.entenhaft == 0 and not st.goofy
    cfg.kopf_stimme_motor = "browser"
    assert sp.prepare_kopf("Hallo.")["motor"] == "browser" and sp.kopf_motor() == "browser"


def test_stimmen_seite_im_kopf():
    from pathlib import Path

    static = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
    app = (static / "app.js").read_text(encoding="utf-8")
    assert "{ view: 'stimme', part: 'stimme', label: 'Knowlins Stimme' }], kopf: true }" in app   # erreichbar ohne Körper
    stimme = (static / "stimme.js").read_text(encoding="utf-8")
    assert "kopf_stimme_motor" in stimme and "...fuer()" in stimme
    assert "tief" not in (static / "voice.js").read_text(encoding="utf-8").split("export function speak")[1][:400]
