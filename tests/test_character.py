"""Charakter im Leerlauf und die eigenen Gesten-Laute."""

import asyncio
import re
import statistics
from pathlib import Path

from helpers import make, run_for

from duckpilot.backends.sim import SimBackend
from duckpilot.motion import behaviors as B
from duckpilot.motion import character as C
from duckpilot.motion import sounds as S
from duckpilot.motion.engine import MotionEngine

STATIC = Path(__file__).resolve().parent.parent / "duckpilot" / "server" / "static"
SPOT = {name: (0.15 + 0.35 * c, [0.1, 0.35, 0.6, 0.9][r]) for r, row in enumerate(C.NAMES) for c, name in enumerate(row)}


def run(coro):
    return asyncio.run(coro)


async def as_persona(name, seed=3, sim=None, eng=None):
    if sim is None:
        sim, eng = await make()
    eng.config.energie, eng.config.humor = SPOT[name]
    eng.rng.seed(seed)
    eng.idle.rng.seed(seed)
    assert eng.persona == name
    return sim, eng


def gestures(eng):
    return [e["geste"] for e in eng.events if e["type"] == "charakter"]


def test_persona_grid_matches_the_pad():
    js = (STATIC / "personality.js").read_text(encoding="utf-8")
    rows = re.findall(r"\[('[^\]]+')\]", js.split("const DESCRIBE")[0])
    assert [re.findall(r"'([^']+)'", r) for r in rows] == C.NAMES
    for name, (e, h) in SPOT.items():
        assert C.persona(e, h) == name


def test_every_repertoire_entry_exists_and_never_drives_the_legs():
    for persona, rep in C.REPERTOIRE.items():
        for gname, weight in rep["gesten"]:
            assert weight > 0
            known = gname in C.GESTURES or gname in B.ANTICS or gname in B.EMOTIONS
            assert known, (persona, gname)
    for gname, spec in C.GESTURES.items():
        assert not any("fahren" in kf or "skill" in kf for kf in spec), gname
        ch = B.Choreography.from_spec(spec)
        assert ch.kfs[-1].head is not None and abs(ch.kfs[-1].head.head_yaw) < 1e-9, gname   # endet in der Grundhaltung
    assert C.REPERTOIRE[C.NEUTRAL]["gesten"] == []
    assert set(C.TRAITS) == set(C.REPERTOIRE) == {n for row in C.NAMES for n in row}


def test_neutral_stays_calm_everyone_else_shows_character():
    async def go():
        sim, eng = await as_persona("Ausgeglichen")
        await run_for(sim, eng, 60)
        assert gestures(eng) == []
        for name in C.REPERTOIRE:
            if name == C.NEUTRAL:
                continue
            sim, eng = await as_persona(name)
            hi = C.REPERTOIRE[name]["abstand"][1]
            await run_for(sim, eng, hi * 2.5 + 10)
            seen = gestures(eng)
            assert seen, name
            allowed = {g for g, _ in C.REPERTOIRE[name]["gesten"]}
            assert set(seen) <= allowed, (name, seen)
    run(go())


def test_lively_characters_do_more():
    async def go():
        counts = {}
        for name in ("Gelassen", "Quirlig"):
            sim, eng = await as_persona(name, seed=5)
            await run_for(sim, eng, 90)
            counts[name] = len(gestures(eng))
        assert counts["Quirlig"] >= 3 * max(1, counts["Gelassen"])
    run(go())


def test_mimik_differs_by_character():
    async def go():
        stats = {}
        for name in ("Verträumt", "Gemütlich", "Quirlig", "Gelassen"):
            sim, eng = await as_persona(name, seed=7)
            eng.config.idle_life = True
            pitches, yaws, zs = [], [], []
            for _ in range(30 * 20):
                cmd = eng.idle._step(eng.last_state, 0.05)
                if cmd:
                    pitches.append(cmd.head.head_pitch)
                    yaws.append(cmd.head.head_yaw)
                    zs.append(cmd.pose.z)
                eng.last_state = sim.state()
            changes = sum(1 for a, b in zip(yaws, yaws[1:]) if abs(a - b) > 1e-6)
            stats[name] = (statistics.mean(pitches), changes, statistics.mean(zs))
        assert stats["Verträumt"][0] < stats["Gemütlich"][0] - 0.1      # Verträumt schaut nach oben
        assert stats["Quirlig"][1] > 2 * stats["Gelassen"][1]           # Quirlig schaut viel öfter umher
        assert stats["Gemütlich"][2] < stats["Quirlig"][2]              # Gemütlich sackt etwas tiefer
    run(go())


def test_no_character_antics_when_she_comforts_someone():
    async def go():
        sim, eng = await as_persona("Chaos-Ente")
        eng.hear("ich bin heute so traurig", show=False)
        assert eng.mood.empathic
        await run_for(sim, eng, 8)
        assert gestures(eng) == []
    run(go())


def test_real_robot_never_gets_leg_antics():
    class RobotLikeSim(SimBackend):
        def state(self):
            st = super().state()
            st.backend = "robotd"
            return st

    async def go():
        robot = RobotLikeSim(realtime=False, seed=2)
        robot._task = object()
        eng = MotionEngine(robot)
        await eng.stand_up()
        await run_for(robot, eng, 2.5)
        await as_persona("Chaos-Ente", seed=11, sim=robot, eng=eng)
        yaw0 = robot.yaw
        for _ in range(40):
            eng.idle_gesture()
            eng.overlay = None
            eng._overlay_cooldown = 0
            assert eng.current is None
        await run_for(robot, eng, 30)
        assert abs(robot.yaw - yaw0) < 0.05
        assert "schwanz_jagen" not in gestures(eng)
    run(go())


def test_sitting_duck_only_moves_her_head():
    async def go():
        sim, eng = await as_persona("Gemütlich")
        await eng.backend.do("sit_toggle")
        await run_for(sim, eng, 3)
        assert sim.state().sitting
        picked = set()
        for _ in range(30):
            g = eng.idle_gesture()
            eng.overlay = None
            eng._overlay_cooldown = 0
            if g:
                picked.add(g)
        assert picked and all(C.sits_ok(C.GESTURES.get(g) or B.EMOTIONS.get(g, [])) for g in picked)
    run(go())


# ── Laute ─────────────────────────────────────────────────────────────────
def test_every_own_gesture_has_varied_sounds():
    names = list(B.OWN) + list(B.ANTICS) + list(C.GESTURES)
    for name in names:
        clips = S.clips(name)
        assert len(clips) >= 3, name
        for c in clips:
            assert (STATIC / "sounds" / f"{c}.ogg").stat().st_size > 1500, c
            track = S.mouth(c)
            assert track and max(track) > 0.3, c                       # der Schnabel geht auf
    for name in B.OWN:
        spec = B.EMOTIONS[name]
        assert spec[0]["klang"] == S.clips(name)
        assert not any("ton" in kf for kf in spec), name               # keine einzelnen Stimmbank-Töne mehr


def test_beak_opens_with_the_sound():
    async def go():
        sim, eng = await make()
        notes = []
        eng.listeners.append(lambda e: notes.append(e) if e["type"] == "sound" else None)
        ch = B.emotion("traurig")          # Keyframes ohne Schnabel – den öffnet der Laut
        ch.engine = eng
        mouths = []
        for _ in range(int(ch.length * 20) + 2):
            cmd = ch._step(sim.state(), 0.05)
            if cmd:
                mouths.append(cmd.mouth or 0.0)
        assert notes and notes[0]["clip"].startswith("gesten/traurig_")
        assert max(mouths) > 0.3 and mouths[0] < 0.1
    run(go())
