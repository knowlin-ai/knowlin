"""Kontext je Körper (seit 0.38.6, Prüfauftrag): Figuren reparieren, nur Enten quaken, das Gehirn bietet nur an,
was der Körper kann, Knowlet-Tricks bleiben unter Probe, Absicherungen nur am PC."""

import asyncio
import json
import random

from fastapi.testclient import TestClient
from helpers import run_for
from test_gui import tmp_settings, vault  # noqa: F401 – Fixtures

from duckpilot import remote as R
from duckpilot.backends.open_duck import OpenDuckSim
from duckpilot.backends.reachy import ReachyMiniSim
from duckpilot.brain.memory import Memory
from duckpilot.brain.tools import ToolRunner, fehlt_dem_koerper
from duckpilot.config import load
from duckpilot.figuren import FIGUREN, FigurenStore, ist_ente
from duckpilot.motion.engine import MotionEngine
from duckpilot.server.app import Runtime, create_app
from duckpilot.voice import speech as SP

BRUNO = {"duck_name": "Bruno", "entenlaute": "oft", "entenhaft": 0.5, "weitere_enten": 2, "energie": 0.7}


def test_reparatur_wenn_reachy_die_ententwerte_geerbt_hat(tmp_path):
    """Vor 0.38.3 auf Reachy gestellt: Brunos Werte lagen bei Reachy. Bruno kommt zurück zur Microduck."""
    store = FigurenStore(tmp_path)
    neu = store.reparieren("reachy_mini", BRUNO)
    assert neu["duck_name"] == "Reachy" and neu["entenlaute"] == "aus" and neu["weitere_enten"] == 0
    # seit 0.38.10 (Hinweis aus dem Test) sind keine weiteren Enten der Standard – auch nicht aus alten Profilen
    assert store.profil("duckpilot")["duck_name"] == "Bruno" and store.profil("duckpilot")["weitere_enten"] == 0
    assert store.reparieren("reachy_mini", BRUNO) is None          # nur einmal
    assert json.loads((tmp_path / "figuren.json").read_text())["version"] == 3


def test_reparatur_wenn_die_ente_schon_zurueck_ist(tmp_path):
    (tmp_path / "figuren.json").write_text(json.dumps({"profile": {"reachy_mini": BRUNO}}), encoding="utf-8")
    store = FigurenStore(tmp_path)
    neu = store.reparieren("duckpilot", {"duck_name": "Quacki", "entenlaute": "manchmal"})
    assert neu["duck_name"] == "Bruno"                              # die Microduck-Figur bekommt ihren Namen zurück
    assert store.profil("reachy_mini")["entenlaute"] == "aus" and store.profil("reachy_mini")["duck_name"] == "Reachy"
    # eine gesunde Reachy-Figur bleibt, wie sie ist
    (tmp_path / "figuren.json").write_text(json.dumps({"profile": {"reachy_mini": {"duck_name": "Robbi", "entenlaute": "aus"}}}))
    assert FigurenStore(tmp_path).reparieren("duckpilot", {"duck_name": "Bruno"}) is None
    assert FigurenStore(tmp_path).profil("reachy_mini")["duck_name"] == "Robbi"


def test_keine_weiteren_enten_als_standard(tmp_path):
    """0.38.10: Wer schon Version 2 hat, bekommt nur noch den neuen Schritt – weitere Enten einmalig auf 0."""
    (tmp_path / "figuren.json").write_text(json.dumps({"version": 2, "profile": {
        "open_duck_mini": {"duck_name": "Odi", "weitere_enten": 3}}}), encoding="utf-8")
    store = FigurenStore(tmp_path)
    assert store.reparieren("duckpilot", {"duck_name": "Bruno", "weitere_enten": 2}) == {"weitere_enten": 0}
    assert store.profil("open_duck_mini")["weitere_enten"] == 0 and store.profil("open_duck_mini")["duck_name"] == "Odi"
    assert store.reparieren("duckpilot", {"weitere_enten": 2}) is None           # nur einmal – danach darfst du wieder


def test_runtime_repariert_beim_start(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    tmp_settings.write_text(json.dumps({**BRUNO, "modul": "reachy_mini", "backend": "sim", "sim_physik": False}))
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    assert rt.config.duck_name == "Reachy" and rt.config.weitere_enten == 0 and rt.config.entenlaute == "aus"
    assert rt.figuren.profil("duckpilot")["duck_name"] == "Bruno"


class _Cfg:
    stimme_motor = "piper"
    stimme_piper = "kerstin"
    stimme_qwen = ""
    qwen_qualitaet = "schnell"
    entenhaft = 0.6
    entenlaute = "oft"
    modul = "reachy_mini"


def test_nur_enten_quaken_in_der_stimme(tmp_path):
    assert ist_ente("duckpilot") and ist_ente("open_duck_mini") and not ist_ente("reachy_mini")
    sp = SP.Speaker(tmp_path, _Cfg())
    assert sp.style("ausgeglichen", False, 0.5, motor="piper").entenhaft == 0.0     # kein Entenfilter bei Reachy
    plan = SP.plan("Hallo. Wie geht es dir? Schön, dich zu sehen. Ich bin da.", 0.0, random.Random(1))
    assert all(i["art"] == "text" for i in plan)
    cfg = _Cfg()
    cfg.modul = "duckpilot"
    assert SP.Speaker(tmp_path, cfg).style("ausgeglichen", False, 0.5, motor="piper").entenhaft == 0.6


def _namen(backend) -> set[str]:
    backend._task = object()
    return {t["name"] for t in ToolRunner(MotionEngine(backend)).tools()}


def test_gehirn_bietet_nur_an_was_der_koerper_kann():
    microduck = _namen(__import__("duckpilot.backends.sim", fromlist=["SimBackend"]).SimBackend(realtime=False, seed=1))
    assert {"explore", "apportieren", "schiessen", "team", "sound", "kopf_ruhig", "skill"} <= microduck
    odi = OpenDuckSim(realtime=False, seed=1)
    duck = _namen(odi)
    assert {"walk", "turn", "dance", "antennen", "sound", "skill"} <= duck
    assert "schiessen" in duck                                   # Schuss im Simulator nachgestellt (seit 0.38.21)
    assert {"explore", "karte", "apportieren", "team", "trick_vom_hub", "training_vorschlagen"}.isdisjoint(duck)
    skill = next(t for t in ToolRunner(MotionEngine(odi)).tools() if t["name"] == "skill")
    assert skill["input_schema"]["properties"]["name"]["enum"] == ["sit_toggle", "kick_left", "kick_right"] and "Hub" not in skill["description"]
    reachy = _namen(ReachyMiniSim(realtime=False, seed=1))
    assert {"sound", "kopf_ruhig", "walk", "explore"}.isdisjoint(reachy) and "antennen" in reachy
    assert "nicht" in fehlt_dem_koerper("explore", odi) and fehlt_dem_koerper("turn", odi) is None


def test_ausfuehren_lehnt_ab_was_fehlt():
    async def go():
        sim = OpenDuckSim(realtime=False, seed=3)
        sim._task = object()
        eng = MotionEngine(sim)
        await eng.stand_up()
        await run_for(sim, eng, 2.5)
        r = ToolRunner(eng)
        return await r.run("apportieren", {"ding": "socke"}), await r.run("explore", {})
    a, e = asyncio.run(go())
    assert not a["ok"] and "schnabel" in a["fehler"] and not e["ok"] and "tiefensensor" in e["fehler"]


def test_knowlet_trick_bleibt_unter_probe_auch_nachbearbeitet(tmp_path):
    mem = Memory(str(tmp_path / "m.json"))
    mem.remember_trick("Fremd", [{"t": 0.5, "head_yaw": 0.2}])
    mem.data["tricks"]["Fremd"].update(probe=False, herkunft="Knowlet X")
    mem.remember_trick("Fremd", [{"t": 0.6, "head_yaw": 0.3}])          # Claude ändert ihn
    t = mem.data["tricks"]["Fremd"]
    assert t["probe"] is False and t["herkunft"] == "Knowlet X" and t["version"] == 2


def test_absicherungen_nur_am_pc():
    assert R.pc_only("POST", "/api/stimme/entwerfen") and R.pc_only("POST", "/api/stimme/uebernehmen")
    assert R.pc_only("POST", "/api/stimme/laden") and R.pc_only("DELETE", "/api/stimme/qwen/abc")
    assert R.pc_only("POST", "/api/fehlerbericht") and not R.pc_only("GET", "/api/stimme")


def test_stimme_gehoert_der_figur(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        figuren = c.get("/api/stimme").json()["figuren"]
        assert [f["modul"] for f in figuren] == list(FIGUREN)
        assert next(f for f in figuren if f["aktiv"])["modul"] == "duckpilot"
        assert next(f for f in figuren if f["modul"] == "reachy_mini")["ente"] is False


def test_oberflaeche_nach_kontext():
    from pathlib import Path

    static = Path(__file__).resolve().parents[1] / "duckpilot" / "server" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    zeile = lambda s: next(z for z in html.splitlines() if s in z)   # noqa: E731
    assert "braucht-tiefensensor" in zeile('data-group="umgebung"')                # Reachy/Open Duck: keine Umgebung
    assert "nur-im-koerper" in zeile('id="raum-start"') and "braucht-tiefensensor" in zeile('id="raum-start"')
    assert "nur-im-koerper" in zeile('id="set-koerper"') and "nur-im-koerper" in zeile('id="set-darstellung"')
    assert "nur-ente" in zeile('id="emo-idle"') and "braucht-beine" in zeile('id="stab-btn"')
    assert "braucht-tiefensensor" in zeile('id="card-tof"')
    assert "keine-ente" in (static / "modul.js").read_text(encoding="utf-8")
    assert "KNOWLIN_WEIT" in (static / "skills.js").read_text(encoding="utf-8")


# ── 0.38.7: Prüfungen vor dem Release, aus Anwendersicht ──────────────────────────────────────────────────────────

def test_name_fragen_geht_ohne_claude():
    from duckpilot.brain.fallback import WER_BIST_DU, FallbackBrain

    assert WER_BIST_DU.search("wie heißt du?") and WER_BIST_DU.search("Who are you") and not WER_BIST_DU.search("tanz")

    async def go():
        from helpers import make

        sim, eng = await make()
        return await FallbackBrain(ToolRunner(eng), lambda: "Bruno").handle("Wie heißt du?")
    r = asyncio.run(go())
    assert r.text == "Ich bin Bruno." and r.source == "einfach"


def test_ohne_ente_beginnt_gross(tmp_settings, vault, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    rt.config.modul = "reachy_mini"
    assert rt._ohne_ente("Quak, mach ich!") == "Mach ich!"


def test_kollision_ohne_mujoco_importierbar():
    """Ohne installierte Physik lief `/api/kollision` in einen Importfehler (frische Installation, 0.38.7).
    In einem eigenen Prozess, damit die übrigen Tests ihre Klassen behalten."""
    import subprocess
    import sys

    code = ("import sys; sys.modules['mujoco'] = None\n"
            "import duckpilot.physics.kollision as k\n"
            "assert k.STUFEN and k.MAX_STOSS_NS > 0\nprint('ok')")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr[-400:]


def test_startseite_kennt_fehlende_portraets(monkeypatch, tmp_path):
    from duckpilot import suite

    monkeypatch.setattr(suite, "FIGUREN_BILDER", tmp_path)
    (tmp_path / "open-duck-mini.png").write_bytes(b"x")
    bilder = {m["id"]: m.get("bild") for m in suite.module("sim")}
    assert bilder["open-duck-mini"] is True and bilder["duckpilot"] is False and "knowlets" not in bilder or bilder["knowlets"] is None


def test_open_duck_sagt_nicht_zu_was_sie_nicht_kann():
    """Abnahmetest 0.38.13: Auf „schieß den Ball“ sagte Odi „ja klar, mach ich!“ – sie hatte den Schuss nicht. Seit
    0.38.21 schießt sie im Simulator (nachgestellt); was sie nicht hat, lehnt sie weiter ehrlich ab (Purzelbaum)."""
    import asyncio

    from duckpilot.backends.open_duck import OpenDuckSim
    from duckpilot.brain.tools import ToolRunner
    from duckpilot.motion.engine import MotionEngine

    sim = OpenDuckSim(realtime=False, seed=1)
    eng = MotionEngine(sim)
    r = asyncio.run(ToolRunner(eng).run("skill", {"name": "roulade"}))
    assert r["ok"] is False and "roulade" in r["fehler"]
    assert asyncio.run(ToolRunner(eng).run("skill", {"name": "sit_toggle"})).get("ok") is not False


def test_ohne_claude_schlaegt_reachy_nichts_vor_was_er_nicht_kann():
    """das Bildschirmfoto 6.11.2026: „Schau dich mal um“ verstand Reachy nicht und schlug „lauf vor“ vor."""
    from duckpilot.brain.fallback import FallbackBrain, parse

    assert parse("Schau dich mal um")[0][0] == "look_around"
    assert parse("guck dich doch kurz um")[0][0] == "look_around"

    async def go():
        sim = ReachyMiniSim(realtime=False, seed=2)
        sim._task = object()
        eng = MotionEngine(sim)
        brain = FallbackBrain(ToolRunner(eng), name=lambda: "Reachy")
        return await brain.handle("Erzähl mir was über Quantenphysik")
    r = asyncio.run(go())
    assert "lauf vor" not in r.text and "schau dich um" in r.text and "Gefieder" not in r.text
