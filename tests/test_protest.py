"""Beschwerden beim Spielen (0.30.1): manchmal, mit Abstand, nie im Stopp-Fenster, ohne Einfluss aufs Wesen."""

import asyncio
import random
import time
from types import SimpleNamespace

from duckpilot.motion.mood import Mood
from duckpilot.protest import ABSTAND_S, GESTEN, SAETZE, Protest, ProtestDienst, nur_kopf


class Uhr:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _rt(**over):
    st = SimpleNamespace(picked_up=False, powered=True, fallen=False, skill=None)
    played, sounds, notes, sent = [], [], [], []

    async def sound(tag):
        sounds.append(tag)

    async def broadcast(msg):
        sent.append(msg)

    eng = SimpleNamespace(
        config=SimpleNamespace(goofy=False, energie=0.55, emotions=True), _window_open=False, estop_at=-1e9,
        play_overlay=lambda spec, *a, **k: played.append(spec) or True, note=notes.append)
    rt = SimpleNamespace(config=SimpleNamespace(kollision_protest=True),
                         backend=SimpleNamespace(kollision_aktiv=True, state=lambda: st, sound=sound),
                         engine=eng, broadcast=broadcast, _speech=lambda text, *a, **k: {"text": text})
    for k, v in over.items():
        setattr(rt, k, v)
    return rt, st, played, sounds, notes, sent


def test_sometimes_not_always_and_with_gap():
    uhr = Uhr()
    p = Protest(random.Random(7), clock=uhr)
    ja = 0
    for i in range(400):
        uhr.t += ABSTAND_S + 0.1                     # Abstand immer eingehalten: nur der Zufall entscheidet
        if p.soll(("ep", i), 0.5):
            p.waehle("leicht", True)
            ja += 1
    assert 0.4 * 400 < ja < 0.7 * 400                # „ab und an“: grob die Hälfte
    # höchstens eine je Episode, und nie innerhalb des Abstands
    uhr.t += 100
    p.rng = SimpleNamespace(random=lambda: 0.0, choice=random.Random(1).choice)
    assert p.soll("x", 1.0)
    p.waehle("kraeftig", True)
    assert not p.soll("x", 1.0)                      # dieselbe Episode
    uhr.t += 1.0
    assert not p.soll("y", 1.0)                      # zu kurz danach
    uhr.t += ABSTAND_S
    assert p.soll("z", 1.0)


def test_stronger_is_more_likely_and_no_repeats():
    p = Protest(random.Random(3))
    assert p.wahrscheinlichkeit(0.1) < p.wahrscheinlichkeit(0.9) < p.wahrscheinlichkeit(0.0, sturz=True)
    assert Protest.staerke("stoss", {"staerke": 0.85}) == 0.85
    assert Protest.staerke("hand", {"tempo": 2.5}) == 1.0
    assert Protest.staerke("zug", {"kraft_n": 3.0}) == 0.5
    gesten, saetze = [], []
    for _ in range(60):
        r = p.waehle("kraeftig", True)
        gesten.append(r.geste)
        saetze.append(r.satz)
    g = [x for x in gesten if x]
    s = [x for x in saetze if x]
    assert all(a != b for a, b in zip(g, g[1:])) and len(set(g)) >= 3
    assert all(a != b for a, b in zip(s, s[1:])) and set(s) <= set(SAETZE["kraeftig"])


def test_character_colours_it_and_lying_means_sound_not_gesture():
    p = Protest(random.Random(5))
    goofy = [p.waehle("kraeftig", True, goofy=True) for _ in range(20)]
    assert {r.art for r in goofy} == {"goofy"}
    assert all(r.geste in GESTEN["goofy"] or r.ton == "wheee" for r in goofy)
    ruhig = [p.waehle("leicht", True, ruhig=True) for _ in range(20)]
    assert all((r.satz or "Hm.") in SAETZE["ruhig"] for r in ruhig)
    liegend = [p.waehle("sturz", False) for _ in range(20)]
    assert all(r.geste is None and r.ton for r in liegend)


def test_gesture_is_head_only():
    from duckpilot.motion.behaviors import EMOTIONS

    for name in {g for pool in GESTEN.values() for g in pool}:
        assert name in EMOTIONS, name
        assert all("koerper" not in step for step in nur_kopf(EMOTIONS[name]))


def _always(rt):
    d = ProtestDienst(rt, Protest(SimpleNamespace(random=lambda: 0.0, choice=lambda xs: xs[0])))
    return d


def test_executes_gesture_sound_and_sentence_as_play():
    rt, st, played, sounds, notes, sent = _rt()
    d = _always(rt)
    r = asyncio.run(d.ausfuehren("kraeftig"))
    assert r.geste and played and all("koerper" not in s for s in played[0])
    assert notes and notes[0]["type"] == "protest" and notes[0]["kollision"] is True
    assert sent and sent[0]["type"] == "chat" and sent[0]["role"] == "duck" and sent[0]["source"] == "spiel"
    # liegt sie: keine Geste, kein Protest außer nach dem Aufstehen
    st.fallen = True
    played.clear()
    assert asyncio.run(d.ausfuehren("kraeftig")) is None and not played


def test_eingestellte_laengere_sperre_gilt_auch_fuer_beschwerden():
    """Audit 0.38.14: Mit 10 min Sperre beschwert sie sich auch nach 3 min noch nicht (vorher fest 120 s)."""
    rt, st, played, sounds, notes, sent = _rt()
    rt.engine.sperre_s = 600.0
    rt.engine.estop_at = time.monotonic() - 180.0
    d = _always(rt)
    assert asyncio.run(d.ausfuehren("sturz")) is None
    assert not (played or sounds or notes or sent)
    rt.engine.sperre_s = 60.0                       # kürzer als 120 s gibt es nicht
    rt.engine.estop_at = time.monotonic() - 90.0
    assert asyncio.run(d.ausfuehren("sturz")) is None


def test_never_in_stop_window_after_estop_when_off_or_lifted():
    for change in ("window", "estop", "off", "lifted", "rest", "mode_off"):
        rt, st, played, sounds, notes, sent = _rt()
        if change == "window":
            rt.engine._window_open = True             # Mikrofon offen: sonst hört die Erkennung die Ente statt „Stopp“
        elif change == "estop":
            rt.engine.estop_at = time.monotonic()
        elif change == "off":
            rt.config.kollision_protest = False
        elif change == "lifted":
            st.picked_up = True
        elif change == "rest":
            st.powered = False
        else:
            rt.backend.kollision_aktiv = False
        d = _always(rt)
        assert asyncio.run(d.ausfuehren("sturz")) is None, change
        assert not (played or sounds or notes or sent), change


def test_one_per_episode_and_throws_only_when_they_hit():
    rt, *_ = _rt()
    d = _always(rt)
    calls = []
    d._planen = lambda key, lage, st, verzug, sturz=False: calls.append((key, lage))   # noqa: E731
    d.reiz("wurf", {}, 1.0)
    assert calls == []                                 # Wurf: erst am Ende, wenn klar ist, ob er traf
    d.ende({"art": "wurf", "ausgang": "steht", "reiz": {}})
    assert calls == []                                 # daneben
    d.ende({"art": "wurf", "ausgang": "wackelt", "reiz": {}})
    assert calls == [(1.0, "kraeftig")]
    calls.clear()
    d.reiz("stoss", {"staerke": 0.25}, 2.0)
    assert calls == [(2.0, "leicht")]
    d.reiz("zug", {}, 3.0)
    d.ende({"art": "zug", "ausgang": "steht_wieder_auf", "reiz": {}})
    assert calls[-2:] == [(3.0, "zug"), (3.0, "sturz")]
    # echte Planung: dieselbe Episode nur einmal
    rt2, *_ = _rt()
    d2 = _always(rt2)
    d2.reiz("stoss", {"staerke": 1.0}, 9.0)
    d2.ende({"art": "stoss", "ausgang": "wackelt", "reiz": {"staerke": 1.0}})
    assert d2.protest._keys.count(9.0) == 1


def test_protest_does_not_touch_mood_memory_or_experience(tmp_path, monkeypatch):
    from duckpilot import settings as S
    from duckpilot.erfahrung_service import ErfahrungService

    monkeypatch.setenv("DUCKPILOT_SETTINGS", str(tmp_path / "settings.json"))
    mood = Mood()
    before = mood.snapshot()
    ev = {"type": "protest", "kollision": True, "message": "Beschwert sich beim Spielen: Na hör mal!"}
    assert mood.appraise(ev) is None and mood.snapshot() == before
    svc = ErfahrungService(SimpleNamespace(memory=object()))
    n, kanten = len(svc.netz.knoten), dict(svc.netz.kanten)
    svc.on_event(ev)
    assert len(svc.netz.knoten) == n and svc.netz.kanten == kanten
    assert S.settings_path().parent == tmp_path
    from duckpilot.brain.tools import ToolRunner

    logged = []
    fake = SimpleNamespace(memory=SimpleNamespace(log_event=lambda *a: logged.append(a)))
    ToolRunner._log_event(fake, ev)
    assert logged == []


def test_setting_exists_and_switch_in_panel():
    from pathlib import Path

    from duckpilot import settings as S
    from duckpilot.config import Config

    assert Config().kollision_protest is True and "kollision_protest" in Config().public()
    assert S.validate({"kollision_protest": False}) == {"kollision_protest": False}
    html = (Path(__file__).parents[1] / "duckpilot/server/static/index.html").read_text("utf-8")
    assert 'data-set="kollision_protest"' in html


def test_wired_to_real_episodes(tmp_path):
    import pytest

    pytest.importorskip("mujoco")
    pytest.importorskip("onnxruntime")
    pytest.importorskip("onnx")
    from test_kollision import physics

    from duckpilot.kollision_service import KollisionService

    b = physics(tmp_path)
    b.kollision_an(True)

    async def broadcast(m):
        pass

    rt = SimpleNamespace(ws_extra={}, backend=b, broadcast=broadcast,
                         config=SimpleNamespace(backend="sim", kollision_protest=True),
                         engine=SimpleNamespace(config=SimpleNamespace(auto_recover=True, recover_delay=3.0)))
    svc = KollisionService(rt)
    assert svc.status()["protest"] is True
    seen = []
    svc.protest.reiz = lambda art, reiz, key: seen.append((art, key))
    b.kollision_reiz("stoss", b.kollision.stoss, ziel="rumpf", staerke=0.5)
    svc._neue_episode()
    svc._neue_episode()                                  # dieselbe Episode nur einmal melden
    assert seen == [("stoss", b.episode.t0)]
