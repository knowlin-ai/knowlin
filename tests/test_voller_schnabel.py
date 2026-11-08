"""Frage 8.11.: „Wenn sie was im Mund hat, kann sie den Mund nicht bewegen zum Reden, oder?“ – Richtig: Mit
vollem Schnabel bleibt er beim Sprechen zu (sonst fiele das Ding herunter); ohne etwas im Schnabel spricht er mit."""

import asyncio

from helpers import make, run_for


def _sprechen(halten: bool) -> float:
    async def go():
        sim, eng = await make()
        if halten:
            sim.holding = "Socke"
        eng.speak([1.0] * 30)
        groesst = 0.0
        for _ in range(20):
            await run_for(sim, eng, 0.1)
            groesst = max(groesst, sim.mouth_now)
        return groesst
    return asyncio.run(go())


def test_mit_vollem_schnabel_bleibt_er_zu():
    assert _sprechen(halten=True) < 0.01


def test_ohne_etwas_spricht_der_schnabel_mit():
    assert _sprechen(halten=False) > 0.3
