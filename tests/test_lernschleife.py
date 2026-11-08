"""Lernschleife: lernen → auf dem Parcours prüfen → vom besten Stand weiter, bis alle Durchgänge im Ziel sind."""
import asyncio
import threading

import pytest

from duckpilot import lernschleife as LS
from duckpilot.physics import lernen as L


class FakeTrainer:
    root = "."

    def __init__(self):
        self.calls = []
        self.job = {"laeuft": False}

    def start(self, spec, quelle, minuten, name, workers=None, *, geraet="auto"):
        n = len(self.calls) + 1
        self.calls.append({"spec": spec, "quelle": quelle, "minuten": minuten, "name": name})
        self.job = {"id": f"j{n}", "laeuft": True, "phase": "lernt"}

        def done():
            self.job = {"id": f"j{n}", "laeuft": False, "phase": "fertig", "ergebnis": f"lokal:r{n}",
                        "bester": {"faehigkeit": 50 + n}, "iteration": 10 * n}
        threading.Timer(0.02, done).start()
        return dict(self.job)

    def status(self):
        return dict(self.job)

    def stop(self, warten=0):
        return self.status()


class FakeCourse:
    name = "Schwelle"


class FakeLab:
    def __init__(self, scores, course=True):
        self.scores, self.tested = scores, []
        self._course = course

        class M:
            def current(_):
                return {"id": "m1", "parcours": {"name": "Schwelle"}} if self._course else {"id": "m1"}
        self.missions = M()

    def course(self):
        return FakeCourse() if self._course else None

    async def test(self, quelle, versuche, auto=False):
        self.tested.append(quelle)
        return {"id": f"t{len(self.tested)}", "im_ziel": self.scores[quelle], "versuche": versuche}

    def cancel(self):
        pass


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(LS, "POLL_S", 0.01)
    monkeypatch.setattr(L, "available", lambda: (True, "bereit"))
    monkeypatch.setattr(L, "aufloesen", lambda root, q: (q, 1.0, q))


def run(loop, body):
    async def go():
        said = []
        loop.chat = lambda t: _say(said, t)
        await loop.start(body)
        await loop._task
        await asyncio.sleep(0)
        return said
    return asyncio.run(go())


async def _say(said, t):
    said.append(t)


def test_loop_learns_until_all_runs_reach_the_goal():
    tr, lab = FakeTrainer(), FakeLab({"standard": 0, "lokal:r1": 1, "lokal:r2": 3})
    loop = LS.LearnLoop(tr, lab, lambda: None)
    said = run(loop, {"minuten": 60, "lernschleife": True})
    j = loop.status()
    assert j["vorher"]["im_ziel"] == 0 and j["geschafft"] and not j["laeuft"]
    assert [c["quelle"] for c in tr.calls] == ["standard", "lokal:r1"]       # Runde 2 setzt auf Runde 1 auf
    assert tr.calls[0]["minuten"] == 15 and tr.calls[0]["spec"] == {"name": "Schwelle"}
    assert lab.tested == ["standard", "lokal:r1", "lokal:r2"]
    assert j["bester"]["quelle"] == "lokal:r2" and "Geschafft" in j["fazit"] and said and "vorher 0 von 3" in said[0]


def test_a_worse_round_never_becomes_the_base():
    tr, lab = FakeTrainer(), FakeLab({"standard": 0, "lokal:r1": 2, "lokal:r2": 1, "lokal:r3": 3})
    loop = LS.LearnLoop(tr, lab, lambda: None)
    run(loop, {"minuten": 60, "lernschleife": True, "runde_minuten": 10})
    assert [c["quelle"] for c in tr.calls] == ["standard", "lokal:r1", "lokal:r1"]
    assert [r["besser"] for r in loop.job["runden"]] == [True, False, True]


def test_already_good_means_nothing_to_learn():
    tr, lab = FakeTrainer(), FakeLab({"standard": 3})
    loop = LS.LearnLoop(tr, lab, lambda: None)
    run(loop, {"minuten": 30})
    assert tr.calls == [] and loop.job["geschafft"] and loop.job["fazit"].startswith("Sie kann es schon")


def test_without_loop_one_run_with_the_whole_budget_also_without_course():
    tr, lab = FakeTrainer(), FakeLab({}, course=False)
    loop = LS.LearnLoop(tr, lab, lambda: None)
    run(loop, {"minuten": 45, "lernschleife": False})
    assert tr.calls == [{"spec": None, "quelle": "standard", "minuten": 45.0, "name": "Ebener Boden"}]
    assert lab.tested == [] and loop.job["ergebnis"] == "lokal:r1"


def test_loop_needs_a_course_and_budget_is_clamped():
    loop = LS.LearnLoop(FakeTrainer(), FakeLab({}, course=False), lambda: None)
    with pytest.raises(ValueError, match="Parcours"):
        asyncio.run(loop.start({"minuten": 30, "lernschleife": True}))
    assert LS.runden_minuten(600) == 60 and LS.runden_minuten(8) == 5 and LS.runden_minuten(3) == 3


def test_runtime_exposes_local_learning(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from duckpilot import settings as S
    from duckpilot.config import load
    from duckpilot.server.app import Runtime, create_app

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(S, "_keyring", lambda: None)
    rt = Runtime(load(memory_path=str(tmp_path / "mem.json")))
    with TestClient(create_app(rt), base_url="http://127.0.0.1:8765") as c:
        m = c.get("/api/lernen").json()
        assert m["type"] == "lernen" and m["schleife"] == {} and "verfuegbar" in m
        r = c.post("/api/lernen/start", json={"minuten": 20, "lernschleife": True},
                   headers={"Origin": "http://127.0.0.1:8765"})
        assert r.status_code == 400 and "Parcours" in r.json()["fehler"]
        res = asyncio.run(rt.free_training({"anbieter": "pc", "minuten": 30}))
        assert not res["ok"] and "Parcours" in res["fehler"]
        assert c.post("/api/lernen/ausprobieren", json={"quelle": "standard"},
                      headers={"Origin": "http://127.0.0.1:8765"}).status_code == 400


def test_ties_are_broken_by_elements_and_falls():
    assert LS.wertung({"im_ziel": 0, "elemente": [{"geschafft": 2}, {"geschafft": 1}], "stuerze": 3}) == (0, 3, -3)
    assert LS.wertung({"im_ziel": 1, "elemente": [], "stuerze": 2}) > LS.wertung({"im_ziel": 0, "elemente": [{"geschafft": 3}]})
