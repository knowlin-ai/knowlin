"""Stimme der Ente, Plaudern, eigenes Sprachmodell und das lernende Gedächtnis."""

import asyncio
import json
import random
import threading

import numpy as np
import pytest
from fastapi.testclient import TestClient
from helpers import make, run_for

from duckpilot import settings as S
from duckpilot.brain.agent import AgentConfig, DuckAgent
from duckpilot.brain.memory import Memory
from duckpilot.brain.tools import ToolRunner
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app
from duckpilot.voice import install as I
from duckpilot.voice import qwen_prozess as QP
from duckpilot.voice import speech as SP
from duckpilot.voice import tts as T


# ── Abfolge: Sätze und Entenlaute ─────────────────────────────────────────
def test_parse_turns_written_sounds_into_real_ones_and_drops_stage_directions():
    parts = SP.parse("*wackelt mit dem Kopf* Oh, toll! *quak quak* Wie geht's dir? *quak?* (lacht) Gack gack!")
    assert parts == [("text", "Oh, toll!"), ("laut", "greet"), ("text", "Wie geht's dir?"), ("laut", "inquire"),
                     ("laut", "greet")]
    assert SP.parse("Quak! Hallo.") == [("laut", "chirp"), ("text", "Hallo.")]
    assert SP.tag_for("gurr") == "coo" and SP.tag_for("quaaak", "!") == "greet" and SP.tag_for("juhu") == "wheee" and SP.tag_for("pick") == "peck"
    assert SP.spoken_text("(lacht) *winkt* Hallo *quak*") == "Hallo *quak*"


def test_plan_rules():
    rng = random.Random(1)
    # ernst (Stopp, Sicherheit): keine Laute, auch keine geschriebenen
    assert all(p["art"] == "text" for p in SP.plan("*quak* Angehalten.", 0.6, rng, ernst=True))
    # nie zwei Laute hintereinander, höchstens drei
    for seed in range(40):
        items = SP.plan("Eins. Zwei! Drei? Vier. Fünf! Sechs?", 0.6, random.Random(seed), "fröhlich", goofy=True)
        tags = [p["art"] for p in items]
        assert tags.count("laut") <= SP.MAX_LAUTE
        assert all(not (a == b == "laut") for a, b in zip(tags, tags[1:]))
    # aus: nichts eingestreut
    assert all(p["art"] == "text" for p in SP.plan("Hallo du. Schön dich zu sehen.", 0.0, rng))


def test_long_sentences_are_split_at_commas_without_sounds_in_between():
    text = ("Das ist ein ziemlich langer Satz, der immer weiter geht, mit vielen Kommas und Nebensätzen, "
            "die man vorlesen muss, damit es natürlich klingt, und noch mehr Text bis zum Ende. Ja!")
    s = SP.sentences(text)
    assert len(s) == 2 and s[0].endswith(",") and s[-1].endswith("Ja!")
    for seed in range(20):
        items = SP.plan(text, 1.0, random.Random(seed))
        i = next(k for k, p in enumerate(items) if p["art"] == "text")
        assert items[i + 1]["art"] == "text"     # kein Laut mitten im Satz


# ── Klangbearbeitung ──────────────────────────────────────────────────────
def _tone(f0=130.0, sr=22050, seconds=1.5):
    t = np.arange(int(sr * seconds)) / sr
    env = 0.5 * (1 + np.sin(2 * np.pi * 3 * t))
    return (0.4 * env * np.sign(np.sin(2 * np.pi * f0 * t))).astype(np.float32), sr


def _pitch(x, sr):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    f = np.fft.rfftfreq(len(x), 1 / sr)
    band = (f > 60) & (f < 500)
    return f[band][np.argmax(spec[band])]


def test_duck_filter_raises_pitch_and_keeps_length():
    x, sr = _tone()
    y = T.duck_filter(x, sr, 0.6)
    assert abs(len(y) - len(x)) < sr * 0.02
    ratio = _pitch(y, sr) / _pitch(x, sr)
    assert 2 ** (3.5 / 12) < ratio < 2 ** (5 / 12)       # ≈ 4,2 Halbtöne
    assert np.max(np.abs(y)) <= 1.0
    assert T.duck_filter(x, sr, 0.0) is x


def test_mouth_track_and_wav_roundtrip():
    x, sr = _tone(seconds=1.0)
    track = T.mouth_track(x, sr)
    assert len(track) == 10 and max(track) == 1.0 and min(track) >= 0.0
    y, sr2 = T.read_wav(T.to_wav(x, sr))
    assert sr2 == sr and np.allclose(x, y, atol=1e-3)
    assert len(T.time_stretch(x, 1.25, sr)) == int(len(x) * 1.25)


# ── Sprecher ──────────────────────────────────────────────────────────────
class _Cfg:
    stimme_motor = "piper"
    stimme_piper = "kerstin"
    stimme_qwen = ""
    qwen_qualitaet = "schnell"
    entenhaft = 0.4
    entenlaute = "manchmal"


def test_speaker_renders_sentences_in_the_background(tmp_path, monkeypatch):
    rendered = []

    def fake_render(self, text, engine, voice, style, quality="schnell"):
        rendered.append((text, engine, voice, style.entenhaft))
        return T.Audio(b"RIFF", [0.5, 1.0], 0.2)

    monkeypatch.setattr(T.Synth, "render", fake_render)
    monkeypatch.setattr(T.PiperEngine, "installed", staticmethod(lambda: True))
    monkeypatch.setattr(T.PiperEngine, "has_voice", lambda self, v: v == "kerstin")
    sp = SP.Speaker(tmp_path, _Cfg())

    async def go():
        plan = sp.prepare("Hallo! Wie geht es dir heute?", "fröhlich")
        assert plan["motor"] == "piper"
        ids = [p["id"] for p in plan["teile"] if p["art"] == "text"]
        assert ids
        audio = await sp.clip(ids[0])
        assert audio.mund == [0.5, 1.0] and sp.mouth_of(ids[0]) == [0.5, 1.0]
        # gleicher Satz, gleiche Stimme → kein zweites Mal rechnen
        n = len(rendered)
        sp.prepare("Hallo! Wie geht es dir heute?", "fröhlich")
        await asyncio.sleep(0.05)
        assert len(rendered) == n
    asyncio.run(go())
    assert rendered[0][1:] == ("piper", "kerstin", 0.4)


def test_speaker_falls_back_to_the_browser_until_the_voice_is_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(T.PiperEngine, "installed", staticmethod(lambda: False))
    sp = SP.Speaker(tmp_path, _Cfg())

    async def go():
        plan = sp.prepare("Hallo.")
        assert plan["motor"] == "browser" and "installiert" in plan["hinweis"]
        assert all("id" not in p for p in plan["teile"])
    asyncio.run(go())


def test_designed_voice_speaks_only_once_the_speaking_model_is_loaded(tmp_path, monkeypatch):
    """Regression 0.37.6 (Anna: „spielt die entworfene Stimme nur im Test ab, das Programm hängt“): Die Fassungen
    kamen vom Entwurfsmodell; gesprochen wird mit dem Sprechmodell, das erst geladen werden muss. Bis dahin spricht die
    Browser-Stimme, das Laden läuft sichtbar im Hintergrund – statt dass Sätze und Mikrofon still warten."""
    import threading

    erlaubt = threading.Event()
    monkeypatch.setattr(T.QwenEngine, "missing", staticmethod(lambda: []))
    monkeypatch.setattr(T.QwenEngine, "voices", lambda self: [{"id": "bruno-2", "name": "Bruno 2"}])
    monkeypatch.setattr(T.QwenEngine, "has_model", lambda self, repo: False)

    def fake_base(self, quality="schnell", progress=None):
        if progress:
            progress(1_200_000_000, 2_400_000_000)
        erlaubt.wait(5)
        self._geladen = T.QWEN_BASE[quality]
        return self._geladen

    monkeypatch.setattr(QP.QwenProzess, "base", fake_base)
    monkeypatch.setattr(T.Synth, "render", lambda self, text, engine, voice, style, quality="schnell":
                        T.Audio(b"RIFF", [0.3], 0.1))
    cfg = _Cfg()
    cfg.stimme_motor, cfg.stimme_qwen = "qwen", "bruno-2"
    sp = SP.Speaker(tmp_path, cfg)

    async def go():
        plan = sp.prepare("Hallo Anna.")
        assert plan["motor"] == "browser" and "Sprechmodell" in plan["hinweis"]
        job = sp.jobs["sprechmodell"]
        assert job["laeuft"] and not sp.info()["bereit"]
        for _ in range(100):
            if job.get("anteil"):
                break
            await asyncio.sleep(0.02)
        assert job["anteil"] == 0.5 and "1,2 von 2,4 GB (50 %)" in job["text"]
        assert "1,2 von 2,4 GB" in sp.info()["grund"]
        sp.prepare("Noch ein Satz.")                       # lädt nicht doppelt
        erlaubt.set()
        for _ in range(100):
            if not job["laeuft"]:
                break
            await asyncio.sleep(0.02)
        assert not job["laeuft"] and job["fehler"] is None and sp.info()["bereit"]
        plan = sp.prepare("Hallo Anna.")
        assert plan["motor"] == "qwen" and all(p.get("id") for p in plan["teile"] if p["art"] == "text")
    asyncio.run(go())


def test_speaking_model_load_error_is_shown_and_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(T.QwenEngine, "missing", staticmethod(lambda: []))
    monkeypatch.setattr(T.QwenEngine, "voices", lambda self: [{"id": "bruno-2", "name": "Bruno 2"}])
    versuche = []

    def kaputt(self, quality="schnell", progress=None):
        versuche.append(quality)
        raise OSError("No space left on device")

    monkeypatch.setattr(QP.QwenProzess, "base", kaputt)
    cfg = _Cfg()
    cfg.stimme_motor, cfg.stimme_qwen = "qwen", "bruno-2"
    sp = SP.Speaker(tmp_path, cfg)

    async def go():
        sp.prepare("Hallo.")
        for _ in range(100):
            if not sp.jobs["sprechmodell"]["laeuft"]:
                break
            await asyncio.sleep(0.02)
        ok, why = sp.ready()
        assert not ok and "lädt nicht" in why and sp.jobs["sprechmodell"]["fehler"]
        assert sp.prepare("Nochmal.")["motor"] == "browser"
        await asyncio.sleep(0.1)
        assert len(versuche) == 2                        # beim nächsten Satz neu versucht
    asyncio.run(go())


def test_piper_end_to_end_if_available(tmp_path):
    """Echte Synthese, wenn piper und eine Stimme da sind (sonst übersprungen)."""
    pytest.importorskip("piper")
    import pathlib
    import shutil

    src = pathlib.Path("/root/voices/de-thorsten-low.onnx")
    try:
        da = src.exists()
    except OSError:                                    # fremder Rechner ohne Zugriff auf /root
        da = False
    if not da:
        pytest.skip("keine Teststimme")
    synth = T.Synth(tmp_path)
    model, conf = synth.piper.files("kerstin")
    model.parent.mkdir(parents=True)
    shutil.copy(src, model)
    shutil.copy(src.with_suffix(".onnx.json"), conf)
    audio = synth.render("Hallo, ich bin Quacki.", "piper", "kerstin", T.Style(entenhaft=0.5))
    assert audio.wav[:4] == b"RIFF" and 0.5 < audio.sekunden < 4 and audio.mund


# ── Schnabel spricht mit ──────────────────────────────────────────────────
def test_engine_moves_the_beak_while_speaking():
    async def go():
        sim, eng = await make()
        eng.config.idle_life = False
        eng.speak([1.0] * 10)
        opened = []
        for _ in range(8):
            await eng.tick(0.05)
            opened.append(eng.last_cmd.mouth)
        assert max(opened) > 0.6
        await eng.stop_all()
        await eng.tick(0.05)
        assert eng.last_cmd.mouth == 0.0
    asyncio.run(go())


# ── Gedächtnis: Wissen und Üben ───────────────────────────────────────────
def test_memory_facts_versions_and_feedback(tmp_path):
    mem = Memory(tmp_path / "m.json")
    mem.remember_fact("Anna spielt Gitarre")
    mem.remember_fact("Die Katze heißt Momo")
    with pytest.raises(ValueError):
        mem.remember_fact("Das Passwort ist geheim123")
    assert "Die Katze heißt Momo" in mem.context("sim", "was macht die katze")["wissen"][:1]
    mem.remember_trick("Verbeugung", [{"t": 0, "kopf": {"nicken": 20}}, {"t": 1, "kopf": {}}])
    mem.remember_trick("Verbeugung", [{"t": 0, "kopf": {"nicken": 35}}, {"t": 1.5, "kopf": {}}])
    t = mem.data["tricks"]["Verbeugung"]
    assert t["version"] == 2 and len(t["versionen"]) == 1
    mem.rate_trick("verbeugung", "schlecht", "zu tief")
    ctx = mem.context("sim", "mach die Verbeugung")
    assert ctx["trick_uebung"]["Verbeugung"]["schlecht"] == 1
    assert "zu tief" in ctx["trick_uebung"]["Verbeugung"]["notizen"][0]
    mem.rate_trick("Verbeugung", "zurueck")
    assert mem.data["tricks"]["Verbeugung"]["keyframes"][0]["kopf"]["nicken"] == 20
    with pytest.raises(ValueError):
        mem.rate_trick("Verbeugung", "zurueck")
    assert mem.forget("wissen", "Gitarre") == "Anna spielt Gitarre"
    again = Memory(tmp_path / "m.json")
    assert [f["text"] for f in again.data["wissen"]] == ["Die Katze heißt Momo"]


def test_tools_remember_facts_and_take_feedback(tmp_path):
    async def go():
        sim, eng = await make()
        runner = ToolRunner(eng, Memory(tmp_path / "m.json"))
        r = await runner.run("remember", {"kind": "wissen", "text": "Anna mag Rätsel"})
        assert r["ok"]
        r = await runner.run("remember", {"kind": "wissen", "text": "Meine IBAN ist DE00"})
        assert r["ok"] is False and "Bank" in r["fehler"]
        await runner.run("choreography", {"keyframes": [{"t": 0, "kopf": {"neigen": 10}}, {"t": 0.6, "kopf": {}}]})
        assert (await runner.run("remember", {"kind": "trick", "name": "Kopf schief"}))["ok"]
        r = await runner.run("trick_feedback", {"name": "Kopf schief", "urteil": "schlecht", "notiz": "zu langsam"})
        assert r["ok"] and r["keyframes"] and r["trick"]["schlecht"] == 1
    asyncio.run(go())


# ── Einstellungen ─────────────────────────────────────────────────────────
def test_voice_and_brain_settings_are_validated():
    assert S.validate({"stimme_motor": "qwen", "entenhaft": 0.7, "entenlaute": "oft", "plaudern": True,
                       "gehirn": "lokal", "lokal_modell": "qwen3.5:9b"})["lokal_modell"] == "qwen3.5:9b"
    for bad in ({"stimme_piper": "darth"}, {"stimme_qwen": "../x"}, {"entenlaute": "immer"},
                {"lokal_modell": "rm -rf /"}, {"lokal_adresse": "http://example.com:11434"}):
        with pytest.raises(ValueError):
            S.validate(bad)
    assert S.validate({"lokal_adresse": "http://192.168.178.20:11434"})


def test_install_commands_are_fixed_lists():
    assert I.commands("piper") == [["piper-tts>=1.3"]]
    amd = I.commands("qwen", "amd", "gfx1201")
    # feste Fassungen (seit 0.38.40): sonst bleibt ein schon installiertes PyTorch „+cpu“ einfach stehen
    assert amd[0][:2] == ["--index-url", I.AMD_INDEX] and f"torch[device-gfx1201]=={I.AMD_TORCH}" in amd[0]
    assert f"torchaudio=={I.AMD_TORCHAUDIO}" in amd[0] and "+rocm" in I.AMD_TORCH
    assert amd[1] == ["--no-deps", "qwen-tts==0.1.1"]
    assert I.commands("qwen", "amd", "; evil")[0][2] == f"torch[device-gfx1201]=={I.AMD_TORCH}"
    assert I.commands("lernen", "amd", "gfx1201")[0] == ["--index-url", I.AMD_INDEX, f"torch[device-gfx1201]=={I.AMD_TORCH}"]
    assert I.amd_arch(["AMD Radeon RX 9070 XT", "AMD Radeon(TM) Graphics"]) == "gfx1201"
    assert I.suggest_gpu(["NVIDIA GeForce RTX 4070"]) == "nvidia" and I.suggest_gpu([]) == "cpu"


def test_installer_runs_steps_and_reports(monkeypatch):
    seen = []

    async def runner(args, job):
        seen.append(args)
        job["zeilen"].append("ok")
        return 0

    async def go():
        inst = I.Installer()
        job = await inst.install("piper", "cpu", runner=runner)
        assert job["fertig"] and not job["laeuft"] and not job["fehler"]
        with pytest.raises(ValueError):
            await inst.install("rm", "cpu")
    asyncio.run(go())
    assert seen == [["piper-tts>=1.3"]]


def test_qwen_install_is_split_and_hub_pin_fits_both_packages(monkeypatch):
    steps = I.commands("qwen", "cpu")
    assert len(steps) == 4 and I.HUB_PIN in steps[2]          # huggingface_hub kommt vor den Audio-Paketen
    assert I.commands("training") == [[I.HUB_PIN]] and "<1.0" in I.HUB_PIN   # transformers 4.57.3 braucht < 1.0
    present = {"qwen_tts", "torch", "torchaudio", "transformers", "accelerate", "einops", "soundfile", "librosa",
               "onnxruntime"}
    monkeypatch.setattr(T, "_has", lambda m: m in present)
    assert I.missing("qwen") == ["huggingface_hub"] and not I.installed("qwen")
    assert not T.QwenEngine.installed()
    present.add("huggingface_hub")
    assert I.installed("qwen") and T.QwenEngine.missing() == []


def test_voice_errors_say_how_to_repair():
    msg = SP.explain(ModuleNotFoundError("No module named 'huggingface_hub'", name="huggingface_hub"))
    assert "huggingface_hub" in msg and "Reparieren" in msg and "Qwen3-TTS" in msg
    wrong = ImportError("huggingface-hub>=0.34.0,<1.0 is required for a normal functioning of this module, "
                        "but found huggingface-hub==1.1.0.")
    assert "falsche Version" in SP.explain(wrong)
    assert SP.explain(T.EngineError("Keine Stimme")) == "Keine Stimme"
    assert "Piper" in SP.explain(ModuleNotFoundError("x", name="piper"), "piper")


# ── Eigenes Sprachmodell ──────────────────────────────────────────────────
def test_local_brain_uses_tools_and_shares_the_memory(tmp_path):
    async def go():
        sim, eng = await make()
        mem = Memory(tmp_path / "m.json")
        mem.remember_fact("Anna spielt Gitarre")
        runner = ToolRunner(eng, mem)
        agent = DuckAgent(runner, AgentConfig(gehirn="lokal", lokal_modell="qwen3.5:9b", plaudern=True))
        sent = []
        replies = iter([
            {"message": {"role": "assistant", "content": "",
                         "tool_calls": [{"function": {"name": "emote", "arguments": {"emotion": "freude"}}},
                                        {"function": {"name": "trick_vom_hub", "arguments": {}}}]}},
            {"message": {"role": "assistant", "content": "<think>hm</think>Klar! *quak* Spielst du heute Gitarre?"}},
        ])

        async def fake_post(path, body, timeout=180.0):
            sent.append(json.loads(json.dumps(body)))
            return next(replies)

        agent.local._post = fake_post
        assert agent.online
        reply = await agent.handle("Freust du dich?")
        assert reply.source == "lokal" and reply.text == "Klar! *quak* Spielst du heute Gitarre?"
        assert [a["tool"] for a in reply.actions] == ["emote", "trick_vom_hub"]
        assert reply.actions[1]["result"]["ok"] is False          # nicht für das lokale Modell
        assert "Anna spielt Gitarre" in sent[0]["messages"][-1]["content"]
        assert "Plaudern" in sent[0]["messages"][0]["content"]
        assert all(t["function"]["name"] != "trick_vom_hub" for t in sent[0]["tools"])
        await run_for(sim, eng, 0.5)
    asyncio.run(go())


def test_without_claude_the_local_model_steps_in_and_then_simple_commands(tmp_path):
    async def go():
        sim, eng = await make()
        agent = DuckAgent(ToolRunner(eng), AgentConfig(lokal_modell="gemma4:12b"))

        async def down(path, body, timeout=180.0):
            raise OSError("Ollama läuft nicht")

        agent.local._post = down
        reply = await agent.handle("tanz bitte richtig wild für mich")
        assert reply.source != "lokal" and agent.local.last_error
    asyncio.run(go())


# ── Server ────────────────────────────────────────────────────────────────
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    monkeypatch.setattr(I, "detect_gpus", lambda: ["AMD Radeon RX 9070 XT"])
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        c.runtime = rt
        yield c


def test_voice_api_status_probe_and_guards(client):
    st = client.get("/api/stimme").json()
    assert st["motor"] == "browser" and st["gpu_vorschlag"] == "amd"
    assert {v["id"] for v in st["piper"]["stimmen"]} >= {"thorsten", "thorsten_emotional", "kerstin"}
    assert "Quirlige Ente" in st["qwen"]["vorlagen"]
    probe = client.post("/api/stimme/probe", json={"text": "Hallo *quak* du."}).json()
    assert probe["sprache"]["motor"] == "browser"
    assert [p["art"] for p in probe["sprache"]["teile"]] == ["text", "laut", "text"]
    assert client.post("/api/stimme/laden", json={"stimme": "../../x"}).status_code == 400
    assert client.post("/api/stimme/installieren", json={"paket": "evil", "gpu": "amd"}).status_code == 400
    assert client.post("/api/stimme/entwerfen", json={"beschreibung": "kurz"}).status_code == 400
    assert client.delete("/api/stimme/qwen/..%2F..").status_code in (400, 404)
    assert client.get("/api/stimme/clip/unbekannt.wav").status_code == 404
    assert client.post("/api/gehirn/laden", json={"modell": "x; rm"}).status_code == 400
    # andere Herkunft darf nichts installieren
    r = client.post("/api/stimme/installieren", json={"paket": "piper", "gpu": "cpu"},
                    headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_chat_reply_carries_the_speech_plan_and_beak_follows(client):
    rt = client.runtime
    with client.websocket_connect("/ws", headers={"Origin": "http://127.0.0.1:8765", "Host": "127.0.0.1:8765"}) as ws:
        ws.send_text(json.dumps({"type": "chat", "text": "tanz"}))
        reply = None
        for _ in range(400):
            msg = json.loads(ws.receive_text())
            if msg["type"] == "chat" and msg["role"] == "duck":
                reply = msg
                break
        assert reply and reply["sprache"]["teile"]
        ws.send_text(json.dumps({"type": "speaking", "sekunden": 1.5}))
        ws.send_text(json.dumps({"type": "laut", "ton": "chirp"}))
        ws.send_text(json.dumps({"type": "laut", "ton": "nope"}))
        for _ in range(60):
            msg = json.loads(ws.receive_text())
            if msg["type"] == "event" and msg["event"].get("type") == "sound":
                break
        assert rt.engine._speech
        ws.send_text(json.dumps({"type": "speaking_end"}))
        for _ in range(5):
            ws.receive_text()
        assert not rt.engine._speech


# ── Stimmbeschreibung auf Deutsch ─────────────────────────────────────────
def test_voice_description_is_translated_for_the_model():
    from types import SimpleNamespace

    from duckpilot.voice import describe as D

    async def go():
        # Vorlage → geprüfte englische Fassung, ganz ohne Netz
        de = D.PRESETS_DE["Freche Ente"]
        assert await D.to_english(de) == (T.DESIGN_PRESETS["Freche Ente"], "vorlage")
        # schon englisch → bleibt
        en = "A sleepy old duck with a deep, slow and warm voice"
        assert await D.to_english(en) == (en, "englisch")
        text = "Eine verschlafene alte Ente mit tiefer, langsamer, warmer Stimme"
        # ohne Claude und ohne lokales Modell → Deutsch, mit Hinweis
        assert await D.to_english(text) == (text, "deutsch")
        seen = {}

        class Msgs:
            async def create(self, **k):
                seen.update(k)
                return SimpleNamespace(content=[SimpleNamespace(type="text", text='"A sleepy old duck: deep, slow, warm voice."')])

        agent = SimpleNamespace(client=SimpleNamespace(messages=Msgs()), config=SimpleNamespace(model="m"), local=None)
        out, weg = await D.to_english(text, agent)
        assert weg == "claude" and out == "A sleepy old duck: deep, slow, warm voice." and seen["messages"][0]["content"] == text

        class Local:
            configured = True
            model = "qwen3.5:9b"

            async def _post(self, path, body, timeout=0):
                assert path == "/api/chat" and body["messages"][1]["content"] == text
                return {"message": {"content": "Translation: A sleepy old duck with a deep voice."}}

        out, weg = await D.to_english(text, SimpleNamespace(client=None, local=Local()))
        assert weg == "lokal" and out == "A sleepy old duck with a deep voice."

        class Broken(Local):
            async def _post(self, path, body, timeout=0):
                raise RuntimeError("Ollama aus")

        assert await D.to_english(text, SimpleNamespace(client=None, local=Broken())) == (text, "deutsch")
    asyncio.run(go())
    assert not D.looks_english("Eine fröhliche Ente") and D.looks_english("A happy duck with a bright voice")


def test_model_download_shows_progress_and_resumes(tmp_path, monkeypatch):
    """0.37.7 (Wunsch des Maintainers): Beim Herunterladen großer Modelle Fortschritt sehen; ein abgebrochener Download geht in
    der nächsten Sitzung weiter (halbe Dateien bleiben liegen, huggingface_hub setzt sie fort)."""
    import pytest

    hf = pytest.importorskip("huggingface_hub")
    import huggingface_hub.constants as hf_konst

    q = T.QwenEngine(tmp_path)
    repo = T.QWEN_BASE["schnell"]
    blobs = q._ordner(repo) / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "abc.incomplete").write_bytes(b"x" * 400)          # Rest der letzten Sitzung
    assert q.angefangen(repo) == 400 and not q.has_model(repo)
    monkeypatch.setattr(T, "_repo_bytes", lambda r: 1000)
    gesehen = []

    def fake_snapshot(r, cache_dir):
        assert r == repo and hf_konst.HF_HUB_DISABLE_XET           # klassischer Download: messbar und fortsetzbar
        import time as _t
        _t.sleep(1.3)
        (blobs / "abc.incomplete").rename(blobs / "abc")
        (blobs / "def").write_bytes(b"y" * 600)
        snap = q._ordner(repo) / "snapshots" / "1"
        snap.mkdir(parents=True)
        return str(snap)

    monkeypatch.setattr(hf, "snapshot_download", fake_snapshot)
    pfad = q.download(repo, lambda n, g: gesehen.append((n, g)))
    assert pfad.endswith("1") and gesehen[0] == (400, 1000) and len(gesehen) >= 2
    assert q.has_model(repo)
    assert T.download_text(1_200_000_000, 2_400_000_000) == "1,2 von 2,4 GB (50 %)"


def test_qwen_worker_protocol_progress_and_errors(tmp_path, monkeypatch):
    """0.37.8 (Anna: „Aktivierung hängt – reagiert nicht“): Qwen rechnet in einem eigenen Prozess. Hier der Arbeiter
    im selben Prozess über echte Pipes: Fortschritt kommt an, Fehler kommen als Fehler zurück, der Arbeiter lebt weiter."""
    import os

    def fake_base(self, quality="schnell", progress=None):
        progress(5, 10)
        self.device = "gpu"

    def fake_satz(self, text, vid, style, quality="schnell"):
        if text == "kaputt":
            raise ModuleNotFoundError("No module named 'torch'")
        return (b"ton:" + text.encode(), 24000, 1.0)

    monkeypatch.setattr(T.QwenEngine, "base", fake_base)
    monkeypatch.setattr(T.QwenEngine, "synthesize", fake_satz)
    r1, w1 = os.pipe()
    r2, w2 = os.pipe()
    ein, zu_kind = os.fdopen(r1, "rb"), os.fdopen(w1, "wb")
    vom_kind, aus = os.fdopen(r2, "rb"), os.fdopen(w2, "wb")
    kind = threading.Thread(target=QP.arbeiten, args=(tmp_path, ein, aus), daemon=True)
    kind.start()
    QP._senden(zu_kind, (1, "base", {"quality": "schnell"}))
    assert QP._lesen(vom_kind) == (1, "fortschritt", (5, 10))
    assert QP._lesen(vom_kind) == (1, "ok", "gpu")
    QP._senden(zu_kind, (2, "satz", {"text": "kaputt", "vid": "a", "style": None, "quality": "schnell"}))
    assert QP._lesen(vom_kind) == (2, "fehler", ("ModuleNotFoundError", "No module named 'torch'"))
    QP._senden(zu_kind, (3, "satz", {"text": "Hallo", "vid": "a", "style": None, "quality": "schnell"}))
    assert QP._lesen(vom_kind) == (3, "ok", (b"ton:Hallo", 24000, 1.0))
    zu_kind.close()                                   # duckpilot weg → Arbeiter endet
    kind.join(5)
    assert not kind.is_alive()


def test_qwen_worker_runs_as_its_own_process(tmp_path):
    """Echter Kindprozess: startet, beantwortet Aufträge, meldet Fehler und lässt sich beenden; die Oberfläche (hier der
    Test) wartet nie ohne Frist."""
    import pytest

    q = QP.QwenProzess(tmp_path)
    try:
        with pytest.raises(ValueError, match="unbekannter Auftrag"):
            q._auftrag("quatsch", {}, 60)
        pid = q._proc.pid
        with pytest.raises(T.EngineError, match="gibt es nicht mehr"):
            q.synthesize("Hallo", "fehlt", T.Style(), "schnell")
        assert q._proc.pid == pid and q._proc.poll() is None    # derselbe Arbeiter lebt noch
    finally:
        q.beenden()
    assert q._proc is None and not q.loaded()


def test_designed_voice_gets_no_duck_filter(tmp_path):
    """0.37.8 (Anna: „wenn die Qwen-Stimme aktiviert ist, braucht es den Filter nicht mehr“)."""
    cfg = _Cfg()
    sp = SP.Speaker(tmp_path, cfg)
    assert sp.style("fröhlich", False, 0.5).entenhaft == 0.4          # Piper: Filter wie eingestellt
    cfg.stimme_motor = "qwen"
    assert sp.style("fröhlich", False, 0.5).entenhaft == 0.0
    from duckpilot.server.app import STATIC

    js = (STATIC / "stimme.js").read_text("utf-8")
    assert "d.disabled = qwen;" in js


def _qwen_bereit(monkeypatch, piper=False):
    monkeypatch.setattr(T.QwenEngine, "missing", staticmethod(lambda: []))
    monkeypatch.setattr(T.QwenEngine, "voices", lambda self: [{"id": "bruno-2", "name": "Bruno 2"}])
    monkeypatch.setattr(QP.QwenProzess, "loaded", lambda self, q="schnell": True)
    monkeypatch.setattr(T.PiperEngine, "installed", staticmethod(lambda: piper))
    monkeypatch.setattr(T.PiperEngine, "has_voice", lambda self, v: piper)
    gerechnet = []

    def fake_render(self, text, engine, voice, style, quality="schnell"):
        gerechnet.append((engine, voice, style.entenhaft))
        return T.Audio(b"RIFF", [0.5], 1.0, 0.1)

    monkeypatch.setattr(T.Synth, "render", fake_render)
    return gerechnet


def test_slow_designed_voice_hands_the_whole_answer_to_piper(tmp_path, monkeypatch):
    """0.37.9 (Anna: „springt aufgrund geringer Leistung auf die Browserstimme zurück“, Laptop ohne Grafikkarte):
    gemessen zu langsam → die ganze Antwort spricht Piper (falls geladen), nicht Satz für Satz gemischt."""
    gerechnet = _qwen_bereit(monkeypatch, piper=True)
    cfg = _Cfg()
    cfg.stimme_motor, cfg.stimme_qwen = "qwen", "bruno-2"
    sp = SP.Speaker(tmp_path, cfg)
    sp.messen("qwen", T.Audio(b"", [], 2.0, 7.0))               # 3,5 s Rechnen je Sekunde Sprache
    assert sp.faktor["qwen"] == 3.5 and sp.messungen["qwen"] == 1

    async def go():
        plan = sp.prepare("Heute habe ich im Wohnzimmer drei Socken gefunden. Eine lag unter dem Sofa.")
        assert plan["motor"] == "piper" and "zu langsam" in plan["hinweis"] and "3,5" in plan["hinweis"]
        await asyncio.sleep(0.05)
        assert {g[0] for g in gerechnet} == {"piper"} and gerechnet[0][2] == 0.4   # Piper mit Entenfilter
        info = sp.info()
        assert info["tempo"]["qwen"]["faktor"] == 3.5 and info["rueckfall"] == "piper"
    asyncio.run(go())


def test_fast_designed_voice_speaks_and_tells_the_page_how_long_to_wait(tmp_path, monkeypatch):
    gerechnet = _qwen_bereit(monkeypatch, piper=False)
    cfg = _Cfg()
    cfg.stimme_motor, cfg.stimme_qwen = "qwen", "bruno-2"
    sp = SP.Speaker(tmp_path, cfg)
    sp.messen("qwen", T.Audio(b"", [], 2.0, 1.0))
    sp.messen("qwen", T.Audio(b"", [], 2.0, 0.6))               # gleitender Mittelwert
    assert sp.faktor["qwen"] == round(0.5 * 0.7 + 0.3 * 0.3, 3)

    async def go():
        plan = sp.prepare("Hallo Anna. Schön, dass du da bist.")
        assert plan["motor"] == "qwen" and "hinweis" not in plan and 15 <= plan["warten_s"] <= 45
        await asyncio.sleep(0.05)
        assert gerechnet and all(g[0] == "qwen" and g[2] == 0.0 for g in gerechnet)
        sp.messen("qwen", T.Audio(b"", [], 1.0, 9.0))
        sp.messen("qwen", T.Audio(b"", [], 1.0, 9.0))
        assert sp.prepare("Noch eine lange Antwort mit sehr vielen Wörtern darin.")["motor"] == "browser"
    asyncio.run(go())


def test_warm_up_renders_a_short_sentence_after_loading(tmp_path, monkeypatch):
    gerechnet = _qwen_bereit(monkeypatch)
    monkeypatch.setattr(QP.QwenProzess, "loaded", lambda self, q="schnell": False)
    monkeypatch.setattr(QP.QwenProzess, "base", lambda self, q="schnell", progress=None: None)
    monkeypatch.setattr(T.QwenEngine, "has_model", lambda self, repo: True)
    cfg = _Cfg()
    cfg.stimme_motor, cfg.stimme_qwen = "qwen", "bruno-2"
    sp = SP.Speaker(tmp_path, cfg)
    sp.warm_up()
    for _ in range(100):
        if not sp.jobs["sprechmodell"]["laeuft"]:
            break
        import time
        time.sleep(0.02)
    assert gerechnet == [("qwen", "bruno-2", 0.0)] and sp.messungen["qwen"] == 1


def test_eingebettetes_python_baut_ohne_abschottung(tmp_path, monkeypatch):
    """Gemeldet nach 0.38.32 (Installer, Qwen3-TTS mit AMD): „No module named 'setuptools'“ beim Paket `rocm` – das
    eingebettete Python übergeht PYTHONPATH, über das pip seine abgeschottete Bauumgebung einbindet."""
    (tmp_path / "python.exe").write_bytes(b"")
    assert not I.eingebettet(tmp_path / "python.exe")
    (tmp_path / "python313._pth").write_text("python313.zip\n.\nLib\\site-packages\nimport site\n")
    assert I.eingebettet(tmp_path / "python.exe")
    steps = I.commands("qwen", "amd", "gfx1201", eingebettet=True)
    assert steps[0] == I.BAUWERKZEUGE and any(p.startswith("setuptools") for p in steps[0])
    assert all(s[0] == "--no-build-isolation" for s in steps[1:])
    assert steps[1][1:3] == ["--index-url", I.AMD_INDEX]
    assert I.commands("qwen", "amd", "gfx1201") == [s[1:] for s in steps[1:]]      # sonst wie bisher
    seen = []

    async def runner(args, job):
        seen.append(args)
        return 0

    monkeypatch.setattr(I, "eingebettet", lambda exe=None: True)
    asyncio.run(I.Installer().install("piper", "cpu", runner=runner))
    assert seen == [I.BAUWERKZEUGE, ["--no-build-isolation", "piper-tts>=1.3"]]


def test_pip_bekommt_den_proxy_des_systems(monkeypatch):
    """Gemeldet nach 0.38.33: Downloads von AMDs Paketquelle liefen in „Read timed out“ – pip liest den Proxy aus den
    Windows-Internetoptionen nicht selbst."""
    import urllib.request

    monkeypatch.setattr(urllib.request, "getproxies", lambda: {"https": "http://proxy.firma:8080", "http": "http://proxy.firma:8080"})
    env = I.pip_umgebung({"PATH": "x"})
    assert env["HTTPS_PROXY"] == "http://proxy.firma:8080" and env["PATH"] == "x"
    assert I.pip_umgebung({"HTTPS_PROXY": "http://eigener:1"})["HTTPS_PROXY"] == "http://eigener:1"   # nichts überschreiben
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    assert "HTTPS_PROXY" not in I.pip_umgebung({})


def test_torch_bau_erkennt_prozessor_fassung(monkeypatch):
    # Gemeldet 11.11.: Qwen rechnete auf einer Radeon RX 9070 XT, weil PyTorch „+cpu“ installiert war
    from importlib import metadata

    for version, erwartet in (("2.14.1+cpu", "cpu"), ("2.12.0+rocm7.14.1", "rocm"), ("2.9.0+cu128", "cuda")):
        monkeypatch.setattr(metadata, "version", lambda name, v=version: v)
        monkeypatch.setattr(I, "_installierte", lambda: [])
        assert I.torch_bau() == erwartet

    def fehlt(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", fehlt)
    assert I.torch_bau() is None


def test_stimmfehler_verstaendlich():
    from duckpilot.voice.speech import explain

    weg = explain(RuntimeError("ChunkedEncodingError: ('Connection broken: IncompleteRead(77187461 bytes read)')"))
    assert "abgebrochen" in weg and "bei dir" in weg and "IncompleteRead" not in weg
    halb = explain(OSError("Error no file named pytorch_model.bin, model.safetensors … found in directory C:\\x"))
    assert "nicht vollständig" in halb
    assert len(explain(ValueError("x" * 5000))) < 320


def test_geduldig_spricht_trotz_langsamkeit_mit_eigener_stimme():
    # „Oder es wird trotzdem nutzbar und darf halt langsamer sein“ (11.11.)
    from types import SimpleNamespace

    from duckpilot.voice.speech import Speaker

    sp = Speaker.__new__(Speaker)
    sp.faktor = {"qwen": 12.6}
    sp.config = SimpleNamespace(qwen_geduldig=True)
    assert sp._schaffts("qwen", ["Hallo, ich bin Quacki."])[0] is False      # ohne Geduld: zu langsam
    assert sp._gesamt_s("qwen", ["Hallo.", "Wie geht's?"]) > 10
