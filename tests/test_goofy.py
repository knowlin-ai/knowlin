"""Goofy-Modus: tollpatschig, trotzig, albern – aber sicher und am Ende immer folgsam."""

import asyncio

from helpers import make, run_for

from duckpilot.api import Twist
from duckpilot.backends.sim import SimBackend
from duckpilot.brain.agent import AgentConfig, DuckAgent
from duckpilot.brain.fallback import GOOFY_OK, GOOFY_TROTZ, FallbackBrain
from duckpilot.brain.tools import ToolRunner
from duckpilot.motion import behaviors as B
from duckpilot.motion.engine import MotionEngine


def run(coro):
    return asyncio.run(coro)


async def goofy(level="mittel", seed=1):
    sim, eng = await make()
    eng.config.goofy = True
    eng.config.goofy_level = level
    eng.rng.seed(seed)
    return sim, eng


def test_goofy_emotions_are_valid_and_end_neutral():
    for name in ("schuetteln", "trotzig", "stolpern", "verlegen", "staunen"):
        ch = B.emotion(name)
        last = ch.kfs[-1]
        assert last.head is not None and abs(last.head.head_yaw) < 1e-9, name   # zurück in die Grundhaltung
    for name, antic in B.ANTICS.items():
        B.Choreography.from_spec(antic["spec"])


def test_bump_makes_her_indignant_but_legs_keep_going():
    async def go():
        sim, eng = await goofy()
        eng.run(B.TimedMove(Twist(0.1, 0, 0), 3.0))
        await run_for(sim, eng, 0.5)
        sim.emit("bump", what="Kiste", message="Angestoßen: Kiste")
        assert eng.overlay is not None
        assert any(e["type"] == "goofy" and "Kiste" in e["message"] for e in eng.events)
        await run_for(sim, eng, 0.5)
        assert eng.last_cmd.twist.vx > 0          # die Einlage nimmt den Beinen nichts weg
        assert isinstance(eng.current, B.TimedMove)
    run(go())


def test_stumbles_while_walking_without_falling():
    async def go():
        sim, eng = await goofy("wild", seed=2)
        eng.goofy_params = lambda: {"stumble": 1.0, "idle": 999.0, "trotz": 0.0}  # sicher stolpern
        x0 = sim.x
        eng.run(B.Walk(1.0))
        await run_for(sim, eng, 20, until=lambda: not eng.busy())
        assert abs((sim.x - x0) - 1.0) < 0.06     # kommt trotzdem an
        assert not sim.fallen
        assert any("stolpert" in e.get("message", "") for e in eng.events)
    run(go())


def test_idle_antics_only_when_idle_and_never_turning_on_real_robot():
    class RobotLikeSim(SimBackend):
        def state(self):
            st = super().state()
            st.backend = "robotd"
            return st

    async def go():
        sim, eng = await goofy("wild", seed=4)
        await run_for(sim, eng, 40)
        assert any(e["type"] in ("goofy", "charakter") for e in eng.events)

        robot = RobotLikeSim(realtime=False, seed=1)
        robot._task = object()
        reng = MotionEngine(robot)
        reng.config.goofy, reng.config.goofy_level = True, "wild"
        await reng.stand_up()
        yaw0 = None
        for _ in range(int(80 * 20)):
            await reng.tick(0.05)
            await asyncio.sleep(0)
            robot.step(0.025)
            robot.step(0.025)
            if yaw0 is None and robot.powered:
                yaw0 = robot.yaw
            assert reng.current is None or not isinstance(reng.current, B.Choreography)
        assert abs(robot.yaw - yaw0) < 0.05       # hat sich nicht ungefragt gedreht
        assert any(e["type"] in ("goofy", "charakter") for e in reng.events)
    run(go())


def test_stop_ends_all_nonsense_immediately():
    async def go():
        sim, eng = await goofy()
        eng.play_overlay(B.EMOTIONS["schuetteln"], force=True)
        eng.run(B.Choreography.from_spec(B.ANTICS["schwanz_jagen"]["spec"]))
        await run_for(sim, eng, 0.5)
        await eng.stop_all()
        assert eng.overlay is None and eng.current is None
        await run_for(sim, eng, 0.5)
        assert abs(sim.state().twist.vyaw) < 0.1
    run(go())


def test_shakes_after_getting_up_from_a_fall():
    async def go():
        sim, eng = await goofy()
        eng.config.recover_delay = 0.3
        eng.config.obstacle_guard = False
        sim.x, sim.y, sim.yaw = 1.2, -0.6, 0.0
        eng.run(B.TimedMove(Twist(0.25, 0, 0), 3))
        await run_for(sim, eng, 10)
        assert any("als wäre nichts gewesen" in e.get("message", "") for e in eng.events)
    run(go())


def test_fallback_trotz_then_does_it_anyway():
    async def go():
        sim, eng = await goofy("wild")
        brain = FallbackBrain(ToolRunner(eng))
        seen_trotz = False
        for seed in range(30):
            eng.rng.seed(seed)
            await eng.stop_all()
            reply = await brain.handle("lauf einen halben Meter vor")
            tools = [a["tool"] + ":" + str(a["input"].get("emotion", "")) for a in reply.actions]
            if reply.text in GOOFY_TROTZ:
                seen_trotz = True
                assert tools[:2] == ["emote:trotzig", "emote:schuetteln"]
                assert tools[2] == "walk:"           # und dann wird gelaufen
                assert reply.actions[2]["input"]["then"] is True
                break
            assert reply.text in GOOFY_OK
        assert seen_trotz
        # Stopp ist nie trotzig
        for seed in range(20):
            eng.rng.seed(seed)
            reply = await brain.handle("setz dich")
            assert reply.actions[0]["tool"] == "power"
    run(go())


def test_voice_switches_goofy_on_and_off():
    async def go():
        sim, eng = await make()
        brain = FallbackBrain(ToolRunner(eng))
        await brain.handle("Ente, sei mal albern")
        assert eng.config.goofy
        await brain.handle("Sei wieder normal")
        assert not eng.config.goofy
        await brain.handle("Ich werde verrückt mit dir")  # kein Befehl
        assert not eng.config.goofy
    run(go())


def test_claude_prompt_has_personality_only_when_on():
    async def go():
        sim, eng = await make()
        agent = DuckAgent(ToolRunner(eng), AgentConfig(api_key=None))
        assert "GOOFY-MODUS IST AN" not in agent._system()
        eng.config.goofy = True
        system = agent._system()
        assert "GOOFY-MODUS IST AN" in system and "IMMER" in system and "emote schuetteln" in system
        assert "set_goofy" in {t["name"] for t in agent.runner.tools()}
    run(go())
