"""Was aus Pollens Repos kommt: Emotionen, Stimme, 3D-Modell, Tricks vom Hub."""

import asyncio
import json
import math
import struct
from pathlib import Path

import pytest
from helpers import make, run_for

from duckpilot import hub
from duckpilot.api import Head, Twist
from duckpilot.backends.fake_robotd import start_server
from duckpilot.backends.robotd import RobotdBackend, _guess_updater
from duckpilot.backends.sim import HOME_HEAD, HOME_NECK, SIT_LEG, STAND_LEG, display_joints
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion import behaviors as B
from duckpilot.motion.engine import MotionEngine

STATIC = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"


def run(coro):
    return asyncio.run(coro)


# ── Emotionen ─────────────────────────────────────────────────────────────
def test_all_fourteen_pollen_emotions_are_there_with_sound():
    assert len(B.POLLEN) == 14
    for name, e in B.POLLEN.items():
        assert e["text"] and e["spec"], name
        clips = e["spec"][0]["klang"] if "klang" in e["spec"][0] else []
        assert clips, name
        for c in clips:
            assert (STATIC / "sounds" / "emotions" / f"{c}.ogg").exists(), c
        ch = B.emotion(name)
        assert ch.linear                                   # 10-Hz-Kurven: linear, nicht ruckelnd
        last = ch.kfs[-1]
        assert last.head is not None and abs(last.head.head_yaw) < 1e-9 and last.pose.z == 0


def test_pollen_signs_match_the_robot():
    # „ja“: Schnabel nickt nach unten (head_pitch > 0); am Boden: Hals nach vorn/unten (neck < 0)
    ja = B.emotion("jawohl")
    assert max(k.head.head_pitch for k in ja.kfs if k.head) > 0.5
    boden = B.emotion("am_boden")
    # Pollen schickt den Hals bis −1,5 rad (folgt nur halb) – wir bis zur Trainingsgrenze −1,1, nicht mehr −0,5
    assert min(k.head.neck_pitch for k in boden.kfs if k.head) <= -1.1 + 1e-9
    assert min(k.pose.z for k in boden.kfs if k.pose) < -0.015
    # Wie Pollen: am Boden setzt sie sich beim Ton (0,3 s) hin – einmal, und nur wenn sie steht
    sits = [k for k in boden.kfs if k.skill]
    assert len(sits) == 1 and sits[0].skill == "hinsetzen" and abs(sits[0].t - 0.3) < 1e-6
    assert [k.t for k in B.emotion("tot_stellen").kfs if k.skill] == [0.0]


def test_explicit_devastated_sits_once_but_an_overlay_never_does():
    async def go():
        sim, eng = await make()
        await run_for(sim, eng, 1)
        eng.run(B.emotion("am_boden"))
        await run_for(sim, eng, 4)
        assert sim.sitting                              # hat sich hingesetzt
        sim2, eng2 = await make()
        await run_for(sim2, eng2, 1)
        assert eng2.play_overlay(B.EMOTIONS["am_boden"], force=True)
        await run_for(sim2, eng2, 4)
        assert not sim2.sitting                         # als Einlage nie die Beine
    run(go())


def test_curious_on_the_robot_keeps_only_the_tilts():
    sim_ch = B.emotion("was_was")
    robot_ch = B.emotion("was_was", robot=True)
    assert any(abs(k.head.neck_pitch) > 0.1 for k in sim_ch.kfs if k.head)
    assert all(k.head.neck_pitch == 0 and k.head.head_pitch == 0 for k in robot_ch.kfs if k.head)
    assert any(abs(k.head.head_roll) > 0.1 for k in robot_ch.kfs if k.head)


def test_pollen_overlays_play_at_full_size_and_only_when_standing():
    async def go():
        sim, eng = await make()
        await run_for(sim, eng, 1)
        eng.config.energie = 0.0                     # ruhig: eigene Gesten kleiner
        assert eng.play_overlay(B.EMOTIONS["jawohl"], force=True)
        full = max(k.head.head_pitch for k in eng.overlay.kfs if k.head)
        assert abs(full - max(k.head.head_pitch for k in B.emotion("jawohl").kfs if k.head)) < 1e-9
        assert B.is_pollen(B.EMOTIONS["jawohl"]) and not B.is_pollen(B.EMOTIONS["freude"])
    run(go())


def test_expressions_switch_off_the_direct_head_hold():
    async def go():
        sim, eng = await make()
        await run_for(sim, eng, 1)
        assert not sim.expressing
        eng.run(B.emotion("jawohl"))
        await run_for(sim, eng, 0.3)
        assert sim.expressing                           # Kopf folgt dann wie am Roboter verzögert, passend zum Ton
    run(go())


def test_delayed_sound_lands_on_its_moment():
    ch = B.emotion("am_boden")             # Pollen: Ton bei 0,3 s
    clipped = [k for k in ch.kfs if k.clip]
    assert len(clipped) == 1 and abs(clipped[0].t - 0.3) < 1e-6


def test_mood_sometimes_uses_pollens_originals():
    async def go():
        sim, eng = await make()
        await run_for(sim, eng, 1)
        used = set()
        for seed in range(40):
            eng.rng.seed(seed)
            eng.overlay = None
            eng._overlay_cooldown = 0
            eng._last_expression = -99
            eng.express("begeistert", force=True)
            used.add(len(eng.overlay.kfs) if eng.overlay else 0)
        assert len(used) >= 2          # mal die eigene, mal Pollens „aufgeregt“
    run(go())


# ── Stimme ────────────────────────────────────────────────────────────────
def test_emotion_sounds_are_listed_for_preloading():
    index = json.loads((STATIC / "sounds" / "emotions" / "index.json").read_text())
    assert sorted(index["dateien"]) == sorted(p.name for p in (STATIC / "sounds" / "emotions").glob("*.ogg"))


def test_voice_bank_has_every_tag():
    index = json.loads((STATIC / "sounds" / "voice" / "index.json").read_text())
    for tag in ("alarm", "greet", "inquire", "peck", "chirp", "coo", "wheee"):
        files = index["tags"][tag]
        assert len(files) >= (2 if tag == "wheee" else 10), tag      # wie Pollen: 10–12 Varianten je Ton
        assert files and all((STATIC / "sounds" / "voice" / f).stat().st_size > 500 for f in files), tag


# ── 3D-Modell und Gelenke ─────────────────────────────────────────────────
def test_baked_model_is_complete():
    if not (STATIC / "model" / "microduck.dpm").exists():      # öffentliche Fassung: Pollens Modell entsteht erst am PC
        pytest.skip("Pollens Modell ist nicht mitgeliefert (öffentliche Fassung)")
    data = (STATIC / "model" / "microduck.dpm").read_bytes()
    assert data[:4] == b"DPM2"
    n = struct.unpack_from("<I", data, 4)[0]
    head = json.loads(data[8:8 + n])
    joints = {b.get("joint") for b in head["bodies"]}
    for j in ("left_hip_pitch", "right_knee", "neck_pitch", "head_pitch", "head_yaw", "head_roll", "mouth"):
        assert j in joints
    assert "CC BY-NC-SA" in head["licence"]
    pad = lambda x: x + (-x % 4)
    nv = sum(m["v"][1] for m in head["meshes"])
    ni = sum(m["i"][1] for m in head["meshes"])
    assert len(data) == pad(pad(pad(8 + n) + nv * 6) + nv * 3) + ni * 2
    assert all(len(m["min"]) == 3 and len(m["step"]) == 3 for m in head["meshes"])
    # volle Auflösung, aber nicht absurd: gezeichnet zwischen 200 000 und 600 000 Dreiecken
    meshes = head["meshes"]
    drawn = sum(meshes[p["mesh"]]["i"][1] // 3 for p in head["parts"])
    assert 200_000 < drawn < 600_000
    assert {p["finish"] for p in head["parts"]} >= {"shell", "servo", "rubber", "metal"}


def test_display_joints_follow_the_robot_convention():
    kw = dict(skill=None, progress=0.0, fallen=False, twist=Twist(), phase=0.0, mouth=0.0)
    stand = display_joints(sitting=False, powered=True, head=Head(), **kw)
    assert stand[:5] == list(STAND_LEG)
    assert stand[10:] == [-v for v in STAND_LEG]                    # rechts gespiegelt
    assert math.isclose(stand[5], HOME_NECK) and math.isclose(stand[6], HOME_HEAD)
    sit = display_joints(sitting=True, powered=True, head=Head(), **kw)
    assert sit[:5] == list(SIT_LEG)
    nod = display_joints(sitting=False, powered=True, head=Head(-0.3, 0.4, 0.2, 0.1), **kw)
    assert math.isclose(nod[5], HOME_NECK - 0.3) and math.isclose(nod[6], HOME_HEAD + 0.4)
    kw2 = {**kw, "twist": Twist(0.2, 0, 0)}
    walk = [display_joints(sitting=False, powered=True, head=Head(), **{**kw2, "phase": p}) for p in (0.5, 2.0, 3.6, 5.0)]
    assert max(w[3] for w in walk) > STAND_LEG[3] + 0.3             # Knie hebt beim Laufen


# ── Tricks vom Hub ────────────────────────────────────────────────────────
FAKE_HUB = {
    "api": [
        {"modelId": "pollen-robotics/microduck-policies", "likes": 9, "downloads": 400,
         "siblings": [{"rfilename": "manifest.json"}, {"rfilename": "walk.onnx"}]},
        {"modelId": "fffiloni/microduck-polite-bow-b1d864", "likes": 3, "downloads": 20,
         "siblings": [{"rfilename": "policy.onnx"}, {"rfilename": "manifest.json"}, {"rfilename": "media/preview.mp4"}]},
        {"modelId": "someone/microduck-ground-pick-v2", "likes": 1,
         "siblings": [{"rfilename": "policy.onnx"}, {"rfilename": "manifest.json"}]},
        {"modelId": "someone/a-text-model", "siblings": [{"rfilename": "model.safetensors"}]},
    ],
    "pollen-robotics/microduck-policies": {"policies": [{"file": "walk.onnx"}] * 10, "description": "official set"},
    "fffiloni/microduck-polite-bow-b1d864": {"name": "polite-bow", "description": "A polite bow.\nSecond line",
                                             "kind": "episodic", "duration_s": 3.0},
    "someone/microduck-ground-pick-v2": {"description": "x" * 400, "command": {"encoding": "phase"}},
}


def fake_fetch(url: str) -> bytes:
    if "/api/models?" in url:
        return json.dumps(FAKE_HUB["api"]).encode()
    for repo, man in FAKE_HUB.items():
        if f"/{repo}/resolve/main/manifest.json" in url:
            return json.dumps(man).encode()
    raise OSError("404")


def test_hub_search_reads_manifests_and_previews():
    found = hub.search("microduck", fetch=fake_fetch)
    repos = [f["repo"] for f in found]
    assert repos[0] == "pollen-robotics/microduck-policies"          # offiziell zuerst
    assert "someone/a-text-model" not in repos                       # kein ONNX
    bow = next(f for f in found if "polite-bow" in f["repo"])
    assert bow["name"] == "polite-bow" and bow["beschreibung"] == "A polite bow."
    assert bow["vorschau"].endswith("/media/preview.mp4") and bow["geht"]
    pick = next(f for f in found if "ground-pick" in f["repo"])
    assert not pick["geht"] and len(pick["beschreibung"]) <= hub.DESCRIPTION_LIMIT
    assert not found[0]["geht"]                                       # ganzer Satz, kein einzelner Trick


def test_trick_names_are_safe():
    assert hub.trick_name("RemiFabre/microduck-flamingo-cycle") == "flamingo-cycle"
    assert hub.trick_name("x/y", "Höflich Verbeugen!") == "h-flich-verbeugen"
    assert _guess_updater("tcp:127.0.0.1:7900") == "tcp:127.0.0.1:7902"
    assert _guess_updater("unix:/run/robotd.sock") is None


def test_sim_refuses_hub_tricks_politely():
    async def go():
        sim, eng = await make()
        res = await sim.add_trick("fffiloni/microduck-polite-bow-b1d864")
        assert not res.accepted and "echten Roboter" in res.reason
    run(go())


def test_load_and_run_a_hub_trick_on_the_robot_path():
    async def go():
        server, fake = await start_server("tcp:127.0.0.1:7941")
        be = RobotdBackend("tcp:127.0.0.1:7941", updater="tcp:127.0.0.1:7941")
        await be.connect()
        eng = MotionEngine(be)
        await eng.start()
        try:
            for _ in range(40):
                await asyncio.sleep(0.1)
                if be.state().connected:
                    break
            res = await be.add_trick("fffiloni/microduck-polite-bow-b1d864")
            assert res.accepted, res.reason
            assert "polite-bow-b1d864" in be.skills()
            refused = await be.add_trick("someone/microduck-ground-pick-v2")
            assert not refused.accepted and "festen Platz" in refused.reason
            # Claude sieht den neuen Trick im Skill-Werkzeug
            runner = ToolRunner(eng)
            skill_tool = next(t for t in runner.tools() if t["name"] == "skill")
            assert "polite-bow-b1d864" in skill_tool["input_schema"]["properties"]["name"]["enum"]
            assert (await eng.stand_up()).accepted
            await asyncio.sleep(2.3)
            assert (await be.do("polite-bow-b1d864")).accepted
        finally:
            await eng.close()
            await be.close()
            server.close()
    run(go())


def test_hub_picks_the_main_file_in_repos_with_several():
    api = [
        {"modelId": "HannesVonEssen/microduck-chimney-climb", "likes": 8,
         "siblings": [{"rfilename": f} for f in ("policy.onnx", "enter/policy.onnx", "exit/policy.onnx", "manifest.json", "replay.mp4")]},
        {"modelId": "allen73/microduck-physical-ai",
         "siblings": [{"rfilename": f} for f in ("alpha_walking.onnx", "roulade.onnx")]},
    ]

    def fetch(url):
        if "/api/models?" in url:
            return json.dumps(api).encode()
        return json.dumps({"description": "climbs", "kind": "episodic", "duration_s": 6}).encode()

    found = {f["repo"]: f for f in hub.search("chimney", fetch=fetch)}
    climb = found["HannesVonEssen/microduck-chimney-climb"]
    assert climb["geht"] and climb["datei"] == "policy.onnx" and climb["vorschau"] is None
    plain = found["allen73/microduck-physical-ai"]
    assert not plain["geht"] and "2 Policy-Dateien" in plain["hinweis"]
