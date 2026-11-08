"""Tests: Simulator, Verhalten, Werkzeuge, Claude-Schleife (gemockt), robotd-Pfad."""

import asyncio
import json
import math

import pytest
from helpers import make, run_for

from duckpilot.api import Twist
from duckpilot.backends.fake_robotd import start_server
from duckpilot.backends.robotd import RobotdBackend, parse_address
from duckpilot.brain.agent import AgentConfig, DuckAgent
from duckpilot.brain.fallback import parse
from duckpilot.brain.tools import TOOLS, ToolRunner
from duckpilot.motion import behaviors as B
from duckpilot.motion.engine import MotionEngine


def run(coro):
    return asyncio.run(coro)


# ── Simulator ─────────────────────────────────────────────────────────────
def test_deadman_zeroes_velocity():
    async def go():
        sim, eng = await make()
        await sim.move(Twist(0.2, 0, 0))
        for _ in range(10):
            sim.step(0.02)
        assert sim.state().twist.vx > 0.05
        for _ in range(40):  # 0.8 s ohne neuen Intent
            sim.step(0.02)
        assert sim.state().requested.is_zero()
        assert "Totmann" in " ".join(sim.state().limited_by) or sim.state().twist.vx < 0.05
    run(go())


def test_skill_refused_when_sitting():
    async def go():
        sim, eng = await make()
        assert (await sim.do("sit_toggle")).accepted
        await run_for(sim, eng, 2.0)
        assert sim.state().sitting
        res = await sim.do("kick_left")
        assert not res.accepted and "sitzt" in res.reason
    run(go())


def test_fast_bump_falls_and_engine_recovers():
    async def go():
        sim, eng = await make()
        eng.config.recover_delay = 0.5
        sim.x, sim.y, sim.yaw = 1.2, -0.6, 0.0  # direkt vor dem Regal
        eng.run(B.TimedMove(Twist(0.25, 0, 0), 4.0))
        eng.config.obstacle_guard = False
        fell = await run_for(sim, eng, 4.0, until=lambda: sim.fallen)
        assert fell
        await run_for(sim, eng, 0.1)
        assert eng.current is None  # Reflex hat alles gestoppt
        stood = await run_for(sim, eng, 6.0, until=lambda: not sim.fallen)
        assert stood
    run(go())


def test_obstacle_reflex_stops_before_wall():
    async def go():
        sim, eng = await make()
        sim.x, sim.y, sim.yaw = 1.0, -0.6, 0.0
        eng.run(B.TimedMove(Twist(0.22, 0, 0), 6.0))
        await run_for(sim, eng, 6.0)
        assert not sim.fallen
        assert sim.x < 1.82 - 0.175 - 0.085  # Regal-Vorderkante minus Radius: nie berührt
    run(go())


# ── Verhalten ─────────────────────────────────────────────────────────────
def test_walk_and_turn_close_loop():
    async def go():
        sim, eng = await make()
        x0 = sim.x
        eng.run(B.Walk(0.4))
        eng.run(B.Turn(90), then=True)
        await run_for(sim, eng, 15, until=lambda: not eng.busy())
        assert abs((sim.x - x0) - 0.4) < 0.05
        assert abs(math.degrees(sim.yaw) - 90) < 8
    run(go())


def test_kick_and_pick_sequences():
    async def go():
        sim, eng = await make()
        ball = next(i for i in sim.world_model.items if i.kind == "ball")
        bx = ball.x
        eng.run(B.Approach("ball"))
        eng.run(B.SkillRun("kick_left"), then=True)
        await run_for(sim, eng, 40, until=lambda: not eng.busy())
        await run_for(sim, eng, 1.0)
        assert any(e["type"] == "kick" for e in eng.events)
        assert abs(ball.x - bx) > 0.1
        eng.run(B.Approach("socke"))
        eng.run(B.SkillRun("ground_pick"), then=True)
        await run_for(sim, eng, 40, until=lambda: not eng.busy())
        assert sim.holding == "Socke"
    run(go())


def test_explore_moves_without_falling():
    async def go():
        sim, eng = await make()
        eng.run(B.Explore(60))
        path = 0.0
        last = (sim.x, sim.y)
        for _ in range(60):
            await run_for(sim, eng, 1.0)
            path += math.hypot(sim.x - last[0], sim.y - last[1])
            last = (sim.x, sim.y)
        assert path > 2.0
        assert not any(e["type"] == "fall" for e in eng.events)
    run(go())


def test_choreography_from_spec_clamps_and_finishes():
    async def go():
        sim, eng = await make()
        ch = B.Choreography.from_spec([
            {"t": 0, "kopf": {"drehen": 500}, "ton": "greet"},
            {"t": 0.5, "kopf": {"nicken": 20}, "schnabel": 3, "koerper": {"hoehe_mm": -100}},
            {"t": 1.0, "kopf": {}, "koerper": {}},
        ], loops=2, title="test")
        assert ch.kfs[0].head.head_yaw <= 1.1 + 1e-9
        assert ch.kfs[1].mouth == 1.0 and ch.kfs[1].pose.z == -0.025
        eng.run(ch)
        await run_for(sim, eng, 3.0, until=lambda: not eng.busy())
        assert not eng.busy()
    run(go())


@pytest.mark.parametrize("emo", list(B.EMOTIONS))
def test_every_emotion_runs(emo):
    async def go():
        sim, eng = await make()
        eng.run(B.emotion(emo))
        assert await run_for(sim, eng, 14, until=lambda: not eng.busy())
        if emo in B.POLLEN:  # Pollens Emotionen bringen ihren aufgenommenen Ton mit
            assert any(e["type"] == "sound" and e.get("clip", "").startswith(emo) for e in eng.events)
    run(go())


# ── Werkzeuge & Sprache ───────────────────────────────────────────────────
def test_tool_schemas_are_valid():
    names = [t["name"] for t in TOOLS]
    assert len(names) == len(set(names))
    for t in TOOLS:
        assert t["input_schema"]["type"] == "object"
        json.dumps(t)


def test_every_tool_executes():
    async def go():
        sim, eng = await make()
        r = ToolRunner(eng)
        calls = {
            "get_status": {}, "walk": {"distance_m": 0.1}, "turn": {"degrees": 30, "then": True},
            "drive": {"vx": 0.1, "seconds": 0.5, "then": True}, "go_to": {"x": 0, "y": 0, "then": True},
            "approach": {"target": "ball", "then": True}, "umrunden": {"target": "couchtisch", "then": True}, "apportieren": {"ding": "socke", "then": True}, "head": {"yaw_deg": 20, "seconds": 0.5, "then": True},
            "look_around": {"seconds": 1, "then": True}, "skill": {"name": "kick_right", "then": True},
            "sound": {"tag": "coo"}, "emote": {"emotion": "ja", "then": True},
            "dance": {"seconds": 2, "then": True}, "explore": {"seconds": 3, "then": True},
            "laser_folgen": {"seconds": 5, "then": True},
            "mir_folgen": {"seconds": 10, "then": True},
            "choreography": {"keyframes": [{"t": 0}, {"t": 0.5, "kopf": {"drehen": 20}}], "then": True},
            "pause": {"seconds": 0.2, "then": True}, "wait": {"max_seconds": 0.5},
            "power": {"action": "sit_down"}, "set_goofy": {"an": False}, "kopf_ruhig": {"an": True}, "stop": {},
            "trick_vom_hub": {"aktion": "laden", "repo": "fffiloni/microduck-polite-bow-b1d864"},
            "choreo": {"aktion": "liste"},   # ohne Choreobuch (setzt der Server): ehrlich „nicht verfügbar“
            "enten": {"aktion": "status"},   # ohne weitere Enten: ehrlich „keine“
            "wo_gesehen": {"ding": "socke"}, "karte": {"aktion": "status"},   # ohne Raumwissen (setzt der Server)
            "handeln": {"ding": "Ball", "aktion": "anschauen", "then": True},
            "team": {"aktion": "status"},   # ohne weitere Enten: ehrlich „keine“
            "schiessen": {"richtung": "links"},
            "szene": {"aktion": "zuruecklegen", "ding": "Ball"},
        }
        assert set(calls) == {t["name"] for t in r.tools()}  # ohne Gedächtnis: die Bewegungswerkzeuge
        for name, args in calls.items():
            res = await r.run(name, args)
            assert res.get("ok", True) is not False or name in ("skill", "trick_vom_hub", "choreo", "enten",
                                                                  "wo_gesehen", "karte", "team"), (name, res)
    run(go())


def test_fallback_parser():
    assert parse("Stopp!") == [("stop", {})]
    assert parse("lauf einen Meter vor und dann dreh dich nach rechts") == [
        ("walk", {"distance_m": 1}), ("turn", {"degrees": -90})]
    assert parse("geh 30 cm zurück") == [("walk", {"distance_m": -0.3})]
    assert parse("schieß den ball")[0][0] == "_kick"


# ── Claude-Schleife mit gemocktem Client ──────────────────────────────────
class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def create(self, **kwargs):
        import anthropic

        self.calls.append(kwargs)
        return anthropic.types.Message.model_validate(self.script.pop(0))


def _msg(content, stop):
    return {"id": "msg_x", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
            "content": content, "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10}}


def test_agent_tool_loop_with_mock():
    async def go():
        sim, eng = await make()
        agent = DuckAgent(ToolRunner(eng), AgentConfig(api_key=None))
        fake = FakeMessages([
            _msg([{"type": "text", "text": "Klar!"},
                  {"type": "tool_use", "id": "tu_1", "name": "walk", "input": {"distance_m": 0.3}},
                  {"type": "tool_use", "id": "tu_2", "name": "emote", "input": {"emotion": "freude", "then": True}}],
                 "tool_use"),
            _msg([{"type": "text", "text": "Ich laufe los und freue mich."}], "end_turn"),
        ])

        class Client:
            messages = fake

        agent.client = Client()
        seen = []
        reply = await agent.handle("Lauf ein Stück und freu dich", notify=seen.append)
        assert reply.text == "Ich laufe los und freue mich."
        assert [a["tool"] for a in reply.actions] == ["walk", "emote"]
        assert len(seen) == 2
        # zweite Anfrage enthält tool_result-Blöcke zu beiden tool_use-ids
        second = agent.history[2]["content"]
        assert {c["tool_use_id"] for c in second} == {"tu_1", "tu_2"}
        assert "[Kontext]" in fake.calls[0]["messages"][0]["content"][0]["text"]
        assert eng.current is not None and eng.queue  # läuft, Gefühl eingereiht
    run(go())


def test_agent_rolls_back_on_api_error():
    async def go():
        sim, eng = await make()
        agent = DuckAgent(ToolRunner(eng), AgentConfig(api_key=None))

        class Boom:
            async def create(self, **kw):
                raise RuntimeError("kein Netz")

        class Client:
            messages = Boom()

        agent.client = Client()
        reply = await agent.handle("tanz bitte einmal richtig wild für mich")
        assert "nicht erreichbar" in reply.text
        assert agent.history == []
        assert eng.current is not None  # einfache Steuerung hat übernommen
    run(go())


# ── robotd-Pfad über den Fake-Server ──────────────────────────────────────
def test_parse_address():
    assert parse_address("tcp:127.0.0.1:7900") == ("tcp", ("127.0.0.1", 7900))
    assert parse_address("unix:/run/robotd.sock") == ("unix", "/run/robotd.sock")


def test_robotd_backend_end_to_end():
    async def go():
        server, fake = await start_server("tcp:127.0.0.1:7931")
        be = RobotdBackend("tcp:127.0.0.1:7931", tof="tcp:127.0.0.1:7931")
        await be.connect()
        eng = MotionEngine(be)
        await eng.start()
        try:
            for _ in range(40):
                await asyncio.sleep(0.1)
                if be.state().connected:
                    break
            assert be.state().connected
            assert (await eng.stand_up()).accepted
            await asyncio.sleep(2.3)
            assert be.state().powered and be.state().enabled
            eng.run(B.Walk(0.25))
            eng.run(B.SkillRun("kick_left"), then=True)
            for _ in range(120):
                await asyncio.sleep(0.1)
                if not eng.busy():
                    break
            results = [e.get("result") for e in eng.events if e["type"] == "behavior_end"]
            assert any("gelaufen" in r for r in results), results
            assert any("kick_left ausgeführt" in r for r in results), results
            assert be.state().perception.tof_mm is not None
            refused = await be.do("unbekannt")
            assert not refused.accepted
        finally:
            await eng.close()
            await be.close()
            server.close()
    run(go())


def test_carry_sock_to_sofa():
    async def go():
        sim, eng = await make()
        eng.run(B.Approach("socke"))
        eng.run(B.SkillRun("ground_pick"), then=True)
        eng.run(B.Approach("sofa"), then=True)
        eng.run(B.SkillRun("ground_pick"), then=True)
        await run_for(sim, eng, 80, until=lambda: not eng.busy())
        sock = next(i for i in sim.world_model.items if i.name == "Socke")
        assert not sim.fallen and not sock.held
        assert sock.y > 0.7  # liegt vor dem Sofa (Vorderkante y = 0.945)
    run(go())


def test_config_example_parses(tmp_path):
    from duckpilot.config import PROJECT_DIR, load

    cfg = load(PROJECT_DIR / "duckpilot.example.toml")
    assert cfg.backend == "sim" and cfg.port == 8765 and cfg.head_signs == [1.0, 1.0, 1.0, 1.0]
    assert "api_key" not in cfg.public()


def test_woken_from_rest_she_still_walks_to_the_ball_and_kicks():
    """Aus der Ruhe geweckt: Annähern und Tritt warten aufs Aufstehen, statt abzubrechen (Bug 0.20)."""
    async def go():
        sim, eng = await make(powered=False)              # Ruhe: Motoren aus
        eng.run(B.Approach("ball"))
        eng.run(B.SkillRun("kick_left"), then=True)
        await eng.stand_up()                               # sanftes Wecken: ohne stop_all
        await run_for(sim, eng, 25, until=lambda: any(e["type"] in ("kick", "kick_miss") for e in eng.events))
        kinds = [e["type"] for e in eng.events]
        assert "kick" in kinds and "kick_miss" not in kinds, kinds
    asyncio.run(go())


def test_no_kick_into_the_air_when_the_approach_failed():
    async def go():
        sim, eng = await make()
        for item in sim.world_model.items:
            if item.kind == "ball":
                item.x, item.y = 50.0, 50.0                # außer Sicht
        eng.run(B.Approach("ball"))
        eng.run(B.SkillRun("kick_left"), then=True)
        # seit 0.38.21 sucht sie länger (umsehen, umherlaufen, wieder umsehen), bevor sie aufgibt
        await run_for(sim, eng, 100, until=lambda: any("ausgelassen" in str(e.get("result", "")) for e in eng.events))
        assert not any(e["type"] in ("kick", "kick_miss") for e in eng.events)
        assert any("ausgelassen" in str(e.get("result", "")) for e in eng.events)
    asyncio.run(go())


def test_sim_battery_charges_while_resting():
    from duckpilot.backends.sim import SimBackend

    sim = SimBackend(realtime=False, seed=1)
    sim.battery = 0.0
    for _ in range(600):
        sim.step(1.0)                                      # 10 min ohne Motoren
    assert 0.3 < sim.battery < 0.4


def test_kick_from_21_cm_walks_the_last_centimetres_and_hits():
    """Aus 21 cm trat sie früher zweimal ins Leere – jetzt geht sie selbst heran."""
    async def go():
        sim, eng = await make()
        ball = next(i for i in sim.world_model.items if i.kind == "ball")
        sim.x, sim.y, sim.yaw = ball.x - 0.245, ball.y + 0.03, 0.15
        await run_for(sim, eng, 0.5)
        eng.run(B.KickBall("kick_left"))
        await run_for(sim, eng, 20, until=lambda: any(e["type"] in ("kick", "kick_miss") for e in eng.events))
        kinds = [e["type"] for e in eng.events]
        assert "kick" in kinds and "kick_miss" not in kinds, kinds
    asyncio.run(go())


def test_claude_style_from_rest_approach_then_stand_up_still_kicks():
    """Claude startet aus der Ruhe „zum Ball“ + Tritt und ruft dann noch power stand_up – nichts darf abbrechen."""
    async def go():
        sim, eng = await make(powered=False)
        runner = ToolRunner(eng)
        r = await runner.run("approach", {"target": "ball"})
        assert "selbst auf" in r.get("hinweis", ""), r
        await runner.run("skill", {"name": "kick_left", "then": True})
        await runner.run("power", {"action": "stand_up"})          # Claude „zur Sicherheit“
        await run_for(sim, eng, 25, until=lambda: any(e["type"] in ("kick", "kick_miss") for e in eng.events))
        kinds = [e["type"] for e in eng.events]
        assert "kick" in kinds and "kick_miss" not in kinds, [e for e in eng.events if e["type"] == "behavior_end"]
    asyncio.run(go())


def test_no_self_stand_up_within_two_minutes_after_estop():
    async def go():
        import time
        sim, eng = await make(powered=False)
        eng.estop_at = time.monotonic()
        r = await ToolRunner(eng).run("walk", {"distance_m": 0.3})
        assert not r["ok"] and "Not-Aus" in r["fehler"]                # ehrlich abgelehnt statt „gestartet“
        assert eng.current is None
        await run_for(sim, eng, 2)
        assert not sim.state().powered                               # sie bleibt liegen
    asyncio.run(go())


def test_kick_with_wobbly_perception_and_lazy_gait_like_real_physics():
    """Wie in echter Physik: Messung springt (±3 cm, ±5°), langsame Befehle setzt der Gang schlecht um.
    Die Zielmarke darf nicht zappeln, und der Tritt muss trotzdem treffen."""
    import random

    from duckpilot.backends.sim import SimBackend

    class Wobbly(SimBackend):
        def _visible_objects(self):
            out = super()._visible_objects()
            for o in out:
                o["entfernung_m"] = round(max(0.05, o["entfernung_m"] + self.rng.uniform(-0.03, 0.03)), 2)
                o["richtung_grad"] = round(o["richtung_grad"] + self.rng.uniform(-5, 5))
            return out

        def _step_base(self, dt):
            r = self.requested
            vx = 0.0 if abs(r.vx) < 0.05 else r.vx * 0.6         # Trippeln unter 5 cm/s, sonst 60 %
            self.requested = Twist(vx, r.vy, r.vyaw)
            super()._step_base(dt)
            self.requested = r

    async def go():
        sim = Wobbly(realtime=False, seed=6)
        sim.rng = random.Random(6)
        sim._task = object()
        eng = MotionEngine(sim)
        await eng.stand_up()
        await run_for(sim, eng, 2.5)
        marks = []
        eng.run(B.KickBall("kick_left"))
        for _ in range(40 * 20):
            await eng.tick(0.05)
            await asyncio.sleep(0)
            sim.step(0.025); sim.step(0.025)
            t = eng.current.target() if eng.current is not None else None
            if t:
                marks.append(t)
            if any(e["type"] in ("kick", "kick_miss") for e in eng.events):
                break
        kinds = [e["type"] for e in eng.events]
        assert "kick" in kinds and "kick_miss" not in kinds, [e.get("result") for e in eng.events if e["type"] == "behavior_end"]
        moves = sum(1 for a, b in zip(marks, marks[1:]) if a != b)
        assert marks and moves / len(marks) < 0.1, (moves, len(marks))   # Zielmarke ruhig: < 2 Sprünge pro Sekunde
    asyncio.run(go())



def test_auto_recover_respects_estop_rest_and_pickup():
    """Sturz-Reflex: nie selbst aufstehen nach einem Not-Aus, in Ruhe (stromlos) oder hochgehoben."""
    import time

    async def go(prepare):
        sim, eng = await make()
        eng.powering_until = 0
        await prepare(sim, eng)
        sim._fall("Test")
        await run_for(sim, eng, 10)
        return sim.state()

    async def estop(sim, eng):
        eng.estop_at = time.monotonic()

    async def rest(sim, eng):
        await ToolRunner(eng).run("power", {"action": "rest"})
        await run_for(sim, eng, 3)

    async def nothing(sim, eng):
        pass

    assert asyncio.run(go(estop)).fallen
    st = asyncio.run(go(rest))
    assert st.fallen or not st.powered
    assert not asyncio.run(go(nothing)).fallen          # ohne Not-Aus steht sie wie gewohnt selbst auf


def test_walk_then_true_from_sitting_stands_up_first():
    async def go():
        sim, eng = await make()
        eng.powering_until = 0
        r = ToolRunner(eng)
        await r.run("power", {"action": "sit_down"})
        await run_for(sim, eng, 4)
        x0 = sim.x
        res = await r.run("walk", {"distance_m": 0.3, "then": True})
        assert res["ok"]
        await run_for(sim, eng, 15)
        assert sim.x - x0 > 0.2, [e.get("result") for e in eng.events if e["type"] == "behavior_end"]
    asyncio.run(go())


def test_head_only_emote_while_sitting_does_not_stand_up():
    async def go():
        sim, eng = await make()
        r = ToolRunner(eng)
        await r.run("power", {"action": "sit_down"})
        await run_for(sim, eng, 4)
        await r.run("emote", {"emotion": "ja"})
        await run_for(sim, eng, 6)
        assert sim.state().sitting
    asyncio.run(go())


def test_estop_wins_over_a_stand_up_in_progress():
    """Not-Aus während des Aufstehens: danach wird nichts mehr eingeschaltet."""
    import time

    async def go():
        sim, eng = await make(powered=False)
        orig = sim.init

        async def slow_init():
            res = await orig()
            await asyncio.sleep(0.05)
            return res
        sim.init = slow_init
        task = asyncio.ensure_future(eng.stand_up())
        await asyncio.sleep(0.01)
        eng.estop_at = time.monotonic()              # Not-Aus mitten hinein
        await eng.stop_all("Not-Aus")
        res = await task
        assert not res.accepted and "Not-Aus" in res.reason
        assert not sim.state().enabled
    asyncio.run(go())


def test_approach_measures_progress_again_after_the_ball_rolled_away():
    async def go():
        sim, eng = await make()
        ball = next(i for i in sim.world_model.items if i.kind == "ball")
        a = B.Approach("ball")
        eng.run(a)
        await run_for(sim, eng, 6)
        ball.x += 0.6                                  # rollt weg
        await run_for(sim, eng, 6)
        assert not a.done or "kommt nicht näher" not in a.result, a.result
    asyncio.run(go())


def test_simple_commands_do_not_say_will_do_when_everything_was_refused():
    import time

    from duckpilot.brain.fallback import FallbackBrain

    async def go():
        sim, eng = await make(powered=False)
        eng.estop_at = time.monotonic()                     # Not-Aus-Sperre: Laufen wird abgelehnt
        brain = FallbackBrain(ToolRunner(eng))
        reply = await brain.handle("lauf vor")
        assert "mach ich" not in reply.text and "Geht gerade nicht" in reply.text, reply.text
    asyncio.run(go())


def test_claude_errors_are_plain_language():
    from duckpilot.brain.agent import friendly_error

    class AuthenticationError(Exception):
        status_code = 401

    class RateLimitError(Exception):
        status_code = 429

    assert "API-Schlüssel" in friendly_error(AuthenticationError("invalid x-api-key"))
    assert "zu viele" in friendly_error(RateLimitError("x"))
    assert "Guthaben" in friendly_error(Exception("Your credit balance is too low"))
    assert "x-api-key" not in friendly_error(AuthenticationError("invalid x-api-key"))
