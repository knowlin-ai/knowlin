"""Hilfen: Simulator und Engine ohne Echtzeit gemeinsam takten."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from duckpilot.backends.sim import SimBackend  # noqa: E402
from duckpilot.motion.engine import EngineConfig, MotionEngine  # noqa: E402


async def make(seed=1, powered=True, zufall=None):
    """`zufall`: Saat für den Zufall der Engine (Leerlauf, Goofy) – für Tests, die genau einen Weg prüfen."""
    sim = SimBackend(realtime=False, seed=seed)
    sim._task = object()  # als "verbunden" markieren, ohne Hintergrundschleife
    eng = MotionEngine(sim, EngineConfig(seed=zufall)) if zufall is not None else MotionEngine(sim)
    if powered:
        await eng.stand_up()
        await run_for(sim, eng, 2.5)
    return sim, eng


async def run_for(sim, eng, seconds, until=None):
    for _ in range(int(seconds * 20)):
        await eng.tick(0.05)
        await asyncio.sleep(0)  # gefeuerte Befehle laufen lassen
        sim.step(0.025)
        sim.step(0.025)
        if until and until():
            return True
    return False
