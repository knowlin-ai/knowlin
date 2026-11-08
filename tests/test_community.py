"""Community-Tricks: Katalog vom Hub, Prüfen in der Physik, am Roboter nur Geprüftes."""

import asyncio
import json

import pytest

from duckpilot.skills import community as C

MODELS = [
    {"modelId": "fffiloni/microduck-polite-bow-b1d864", "likes": 3, "downloads": 40, "tags": [],
     "siblings": [{"rfilename": "policy.onnx"}, {"rfilename": "manifest.json"}, {"rfilename": "media/preview.mp4"}]},
    {"modelId": "Lulzx/microduck-backflip", "likes": 9, "downloads": 120, "tags": [],
     "siblings": [{"rfilename": "policy.onnx"}, {"rfilename": "manifest.json"}]},
    {"modelId": "pollen-robotics/microduck-policies", "siblings": [{"rfilename": "a.onnx"}, {"rfilename": "manifest.json"}]},
    {"modelId": "microduckapp/moonwalk", "siblings": [{"rfilename": "policy.onnx"}, {"rfilename": "manifest.json"}]},
    {"modelId": "someone/microduck-sprint", "tags": ["microduck-slot:walk"],
     "siblings": [{"rfilename": "policy.onnx"}, {"rfilename": "manifest.json"}]},
    {"modelId": "someone/notes", "siblings": [{"rfilename": "README.md"}]},
]


def test_catalog_keeps_single_community_tricks_only():
    items = C.CommunityTricks().catalog(lambda url: json.dumps(MODELS).encode())
    assert [i["repo"] for i in items] == ["Lulzx/microduck-backflip", "fffiloni/microduck-polite-bow-b1d864"]
    assert items[0]["titel"] == "Rückwärtssalto" and items[0]["rubrik"] == "Akrobatik"
    assert items[1]["titel"] == "Verbeugung" and items[1]["vorschau"].endswith("media/preview.mp4")


def test_checks_are_remembered(tmp_path):
    ch = C.Checks(tmp_path / "p.json")
    ch.put("a/b", {"urteil": "sicher", "hinweis": "x"})
    again = C.Checks(tmp_path / "p.json")
    assert again.get("a/b")["urteil"] == "sicher" and again.get("a/b")["zeit"]


def test_rehearse_trick_reports_a_verdict(tmp_path):
    pytest.importorskip("mujoco")
    pytest.importorskip("onnxruntime")
    from onnx_fixtures import linear_policy
    from test_physics import make_store

    from duckpilot.physics.practice import rehearse_trick

    store = make_store(tmp_path)
    trick = linear_policy(tmp_path / "trick.onnx")
    res = rehearse_trick(store, str(trick), seconds=1.0)
    assert res["urteil"] in ("sicher", "akrobatisch", "bleibt liegen")
    assert isinstance(res["steht_danach"], bool) and res["dauer_s"] == 1.0


class FakeBackend:
    def __init__(self, backend="robotd"):
        self.kind = backend
        self.runs_policies = backend == "physik"

    def state(self):
        class St:
            fallen = False
        st = St()
        st.backend = "robotd" if self.kind == "robotd" else "sim"
        return st

    def skills(self):
        return ["kick_left"]


class FakeRt:
    def __init__(self, backend):
        self.backend = FakeBackend(backend)
        self.added, self.ran = [], []

        class Eng:
            def run(eng, b, then=False):
                self.ran.append(b)

            def note(eng, e):
                pass
        self.engine = Eng()

    async def add_trick(self, repo, name=None):
        self.added.append(repo)
        return {"ok": True}


class FakeMgr:
    def __init__(self, rt, items):
        self.rt, self.items = rt, items

    async def item(self, pid, key):
        return next((i for i in self.items if key in (i["repo"], i["name"])), None)


def test_robot_runs_only_checked_tricks(tmp_path):
    pack = C.CommunityTricks()
    pack.checks = C.Checks(tmp_path / "p.json")
    items = pack.catalog(lambda url: json.dumps(MODELS).encode())
    rt = FakeRt("robotd")
    mgr = FakeMgr(rt, items)

    async def go():
        r = await pack.run(mgr, "Lulzx/microduck-backflip", "")
        assert not r["ok"] and "noch nicht geprüft" in r["grund"]
        pack.checks.put("Lulzx/microduck-backflip", {"urteil": "bleibt liegen", "hinweis": ""})
        r = await pack.run(mgr, "Lulzx/microduck-backflip", "")
        assert not r["ok"] and "Trotzdem" in r["grund"]
        r = await pack.run(mgr, "Lulzx/microduck-backflip", "trotzdem")
        assert r["ok"] and rt.added == ["Lulzx/microduck-backflip"] and rt.ran
        pack.checks.put("fffiloni/microduck-polite-bow-b1d864", {"urteil": "sicher", "hinweis": ""})
        assert (await pack.run(mgr, "polite-bow-b1d864", ""))["ok"]
    asyncio.run(go())


def test_physics_body_may_try_unchecked_tricks(tmp_path):
    pack = C.CommunityTricks()
    pack.checks = C.Checks(tmp_path / "p.json")
    items = pack.catalog(lambda url: json.dumps(MODELS).encode())
    rt = FakeRt("physik")

    async def go():
        r = await pack.run(FakeMgr(rt, items), "Lulzx/microduck-backflip", "")
        assert r["ok"] and rt.ran and rt.ran[0].voice.plan["start"] == "chirp"
    asyncio.run(go())


def test_tool_lists_names_and_actions():
    pack = C.CommunityTricks()
    items = pack.catalog(lambda url: json.dumps(MODELS).encode())
    t = pack.tool(items)
    assert t["name"] == "community_trick" and "backflip" in t["input_schema"]["properties"]["name"]["enum"]
    assert t["input_schema"]["properties"]["aktion"]["enum"] == ["pruefen", "zeigen"]
