"""Kleine Hilfen für Verhalten und Choreografien (seit 0.38.17 aus behaviors.py ausgelagert)."""

from __future__ import annotations

import math
from typing import Any

DEG = math.pi / 180


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _ohne_entenlaute(backend: Any) -> bool:
    """Körper ohne Entenstimme (Reachy Mini): Choreografien spielen dort weder Töne noch Pollens Entenaufnahmen (`clip`)
    – egal, aus welcher Geste sie kommen (Beobachtung aus dem Test 5.11.: Entenlaute im Leerlauf)."""
    from .reachy_gesten import ist_reachy

    return ist_reachy(backend)
