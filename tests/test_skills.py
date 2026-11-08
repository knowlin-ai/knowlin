"""Skill-Pakete: an- und abschalten, Kataloge vom (gefälschten) Hub, Got a Talent, Gangarten."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from helpers import make, run_for

from duckpilot import settings as S
from duckpilot.backends.fake_robotd import start_server
from duckpilot.backends.robotd import RobotdBackend
from duckpilot.config import load
from duckpilot.server.app import Runtime, create_app
from duckpilot.skills import SkillManager
from duckpilot.skills.app_moves import title_of
from duckpilot.skills.talent import TalentShow, parse_timeline

H = {"Origin": "http://127.0.0.1:8765"}
REF = "pollen-robotics/microduck-got-a-talent-reference"
TIMELINE = {"timeline_version": 1, "duration_s": 12.0, "keyframes": [
    {"t": 0.0, "twist": [0, 0, 0], "head": [0, 0, 0, 0]},
    {"t": 1.0, "twist": [0, 0, 0], "head": [0, 0, 0.5, 0]},
    {"t": 4.0, "twist": [1, 0, 0], "head": [0, 0, -0.5, 0]},
    {"t": 9.0, "twist": [0, 0, 0], "head": [0, 0.3, 0, 0]},
]}


def model(repo, files, likes=0, downloads=0):
    return {"id": repo, "modelId": repo, "likes": likes, "downloads": downloads,
            "siblings": [{"rfilename": f} for f in files]}


MOVE_FILES = ["policy.onnx", "manifest.json", "media/preview.mp4"]
HUB = {
    "/api/models?author=microduckapp": [model("microduckapp/microduck-moonwalk", MOVE_FILES),
                                        model("microduckapp/microduck-preening", MOVE_FILES),
                                        model("microduckapp/microduck-brand-new-thing", MOVE_FILES),
                                        model("microduckapp/readme-only", ["README.md"])],
    "/api/models?filter=microduck-slot:sitstand": [model(REF, ["policy.onnx", "timeline.json"], downloads=98)],
    "/api/models?search=talent": [model("djduecaster/dfreq-talent", ["policy.onnx", "timeline.json"]),
                                  model("someone/talent-show-video", ["video.mp4"])],
    "/api/models?search=microduck-got": [],
    "/api/models?filter=microduck-slot:walk": (
        [model("pollen-robotics/microduck-sprint-2m-reference", ["policy.onnx", "manifest.json"], downloads=225)]
        + [model(f"DenRakEiw/microduck-senate_duck_{n}", ["policy.onnx"], downloads=20 + i) for i, n in enumerate(range(1000, 1600, 100))]
        + [model("witcheer/microduck-walk-rough", ["policy.onnx"], downloads=57)]),
}
FILES = {
    "microduckapp/microduck-moonwalk/resolve/main/manifest.json": {"name": "moonwalk", "kind": "episodic", "duration_s": 6.2,
                                                                   "entry_pose": "standing", "description": "Glides backwards."},
    "microduckapp/microduck-preening/resolve/main/manifest.json": {"name": "preening", "kind": "episodic", "duration_s": 10.41,
                                                                   "description": "Tidies itself up.\nSecond line."},
    f"{REF}/resolve/main/timeline.json": TIMELINE,
    "djduecaster/dfreq-talent/resolve/main/timeline.json": {"keyframes": [{"t": 0, "head": [0, 0, 20, 0]}]},  # ungültig
}
calls = []


def fake_fetch(url):
    calls.append(url)
    path = url.replace("https://huggingface.co", "")
    for prefix, data in HUB.items():
        if path.startswith(prefix):
            return json.dumps(data).encode()
    key = path.lstrip("/")
    if key in FILES:
        return json.dumps(FILES[key]).encode()
    raise OSError(f"404 {url}")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    rt.skills.fetch = fake_fetch
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        c.runtime = rt
        yield c


def test_registry_lists_packs_and_planned_ones_cannot_be_enabled(client):
    r = client.get("/api/skills").json()
    ids = {p["id"]: p for p in r["pakete"]}
    assert {"app_moves", "talent", "gaits", "quack_nav", "duck_detector"} <= set(ids)
    # von Anfang an: Alltagsbuddy und – seit 0.38.34 – die Trick-Pakete mit Vorschauvideos
    assert [p["id"] for p in r["pakete"] if p["an"]] == ["alltag", "app_moves", "community"]
    assert ids["alltag"]["werkzeug"] == "alltag" and ids["alltag"]["herkunft"] == "duckpilot"
    assert ids["quack_nav"]["verfuegbar"] is False and ids["duck_detector"]["braucht"] == "kamera"
    bad = client.post("/api/skills", json={"id": "quack_nav", "an": True}, headers=H)
    assert bad.status_code == 400
    with pytest.raises(ValueError):
        S.validate({"pakete": ["gibtsnicht"]})


def test_enable_pack_persists_and_gives_claude_a_tool(client):
    r = client.post("/api/skills", json={"id": "talent", "an": True}, headers=H).json()
    assert r["ok"] and next(p for p in r["pakete"] if p["id"] == "talent")["an"]
    assert client.runtime.config.pakete == ["alltag", "app_moves", "community", "talent"]
    assert json.loads(S.settings_path().read_text(encoding="utf-8"))["pakete"] == ["alltag", "app_moves", "community", "talent"]
    names = [t["name"] for t in client.runtime.runner.tools()]
    assert "vorfuehrung" in names and "app_bewegung" in names      # app_moves seit 0.38.34 von Anfang an
    client.post("/api/skills", json={"id": "talent", "an": False}, headers=H)
    assert "vorfuehrung" not in [t["name"] for t in client.runtime.runner.tools()]


def test_timeline_rules():
    tl = parse_timeline(TIMELINE)
    assert tl["dauer"] == 12.0 and tl["sitzwechsel"] == 2 and tl["kopfwechsel"] == 3
    assert tl["keyframes"][2]["sit"] is True
    for bad in ({"keyframes": []}, {"keyframes": [{"t": 1}]}, {"duration_s": 30, "keyframes": [{"t": 0}]},
                {"keyframes": [{"t": 0}, {"t": 0}]}, {"keyframes": [{"t": 0, "head": [0, 0, 11, 0]}]}):
        with pytest.raises(ValueError):
            parse_timeline(bad)


def test_talent_catalog_skips_invalid_entries_and_plays_in_the_simulator(client):
    client.post("/api/skills", json={"id": "talent", "an": True}, headers=H)
    cat = client.get("/api/skills/talent/katalog").json()
    assert cat["ok"] and [e["repo"] for e in cat["eintraege"]] == [REF]
    assert cat["eintraege"][0]["titel"] == "Pollens Referenz" and cat["eintraege"][0]["herkunft"] == "offiziell"
    # zweiter Abruf aus dem Speicher, ohne Hub
    n = len(calls)
    client.get("/api/skills/talent/katalog")
    assert len(calls) == n


def test_talent_show_sits_stands_and_moves_the_head():
    async def go():
        sim, eng = await make()
        show = TalentShow(parse_timeline(TIMELINE), "Test")
        eng.run(show)
        yaws, sat = [], False
        for _ in range(int(13 * 20)):
            await run_for(sim, eng, 0.05)
            st = sim.state()
            yaws.append(st.head.head_yaw)
            sat = sat or st.sitting
        return show, yaws, sat, sim.state()
    show, yaws, sat, st = asyncio.run(go())
    assert show.done and "zu Ende" in show.result
    assert sat and not st.sitting, "hingesetzt und wieder aufgestanden"
    assert max(yaws) > 0.3 and min(yaws) < -0.3
    assert show.toggles == 2


def test_app_moves_catalog_titles_and_robot_only(client):
    client.post("/api/skills", json={"id": "app_moves", "an": True}, headers=H)
    cat = client.get("/api/skills/app_moves/katalog").json()
    repos = [e["repo"] for e in cat["eintraege"]]
    assert "microduckapp/readme-only" not in repos and len(repos) == 3
    moon = next(e for e in cat["eintraege"] if e["name"] == "moonwalk")
    assert moon["titel"] == "Moonwalk" and moon["rubrik"] == "Tanz & Musik" and moon["dauer"] == 6.2
    assert moon["vorschau"].endswith("media/preview.mp4")
    pre = next(e for e in cat["eintraege"] if e["name"] == "preening")
    assert pre["beschreibung"] == "Tidies itself up." and pre["titel"] == "Gefieder putzen"
    assert title_of("microduckapp/microduck-brand-new-thing") == ("Brand new thing", "Albern")
    r = client.post("/api/skills/app_moves/ausfuehren", json={"eintrag": "moonwalk"}, headers=H).json()
    assert not r["ok"] and "echten Roboter" in r["grund"]
    r = client.post("/api/skills/app_moves/ausfuehren", json={"eintrag": "moonwalk", "aktion": "vormerken"}, headers=H).json()
    assert r["ok"] and "microduckapp/microduck-moonwalk" in client.runtime.config.tricks
    tool = next(t for t in client.runtime.runner.tools() if t["name"] == "app_bewegung")
    assert "moonwalk" in tool["input_schema"]["properties"]["name"]["enum"]


def test_inactive_pack_refuses_to_run(client):
    r = client.post("/api/skills/talent/ausfuehren", json={"eintrag": "referenz"}, headers=H).json()
    assert not r["ok"] and "nicht aktiv" in r["grund"]


def test_catalog_falls_back_to_disk_when_hub_is_down(client):
    client.get("/api/skills/gaits/katalog")
    mgr = SkillManager(client.runtime, fetch=lambda url: (_ for _ in ()).throw(OSError("offline")))
    res = asyncio.run(mgr.catalog("gaits", refresh=True))
    assert res["ok"] and res["eintraege"] and "nicht erreichbar" in res["hinweis"]


def test_gaits_catalog_groups_checkpoint_series(client):
    cat = client.get("/api/skills/gaits/katalog").json()["eintraege"]
    assert cat[0]["repo"] == "pollen-robotics/microduck-sprint-2m-reference" and cat[0]["rubrik"] == "Sprint 2 m"
    senate = [e for e in cat if "senate_duck" in e["repo"]]
    assert len(senate) == 3 and senate[0]["weitere"] == 3


def test_gait_load_and_reset_on_the_robot_path():
    async def go():
        server, fake = await start_server("tcp:127.0.0.1:7951")
        be = RobotdBackend("tcp:127.0.0.1:7951", updater="tcp:127.0.0.1:7951")
        await be.connect()
        try:
            for _ in range(40):
                await asyncio.sleep(0.1)
                if be.state().connected:
                    break
            ok = await be.load_gait("pollen-robotics/microduck-sprint-2m-reference")
            assert ok.accepted, ok.reason
            assert fake.sim.slots["walk"].endswith("microduck-sprint-2m-reference/policy.onnx")
            no = await be.load_gait("fffiloni/microduck-polite-bow-b1d864")
            assert not no.accepted and "Trick" in no.reason
            back = await be.reset_gait()
            assert back.accepted and fake.sim.slots["walk"] is None
        finally:
            await be.close()
            server.close()
    asyncio.run(go())


def test_gaits_need_the_robot_in_the_simulator(client):
    client.post("/api/skills", json={"id": "gaits", "an": True}, headers=H)
    r = client.post("/api/skills/gaits/ausfuehren", json={"eintrag": "pollen-robotics/microduck-sprint-2m-reference"},
                    headers=H).json()
    assert not r["ok"] and "echten Roboter" in r["grund"]
    assert "gangart" not in [t["name"] for t in client.runtime.runner.tools()]   # nie für Claude
