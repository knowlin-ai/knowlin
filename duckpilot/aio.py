"""Hintergrund-Aufgaben sicher starten.

`asyncio.ensure_future(...)` ohne gemerkte Referenz kann der Garbage Collector mitten im Lauf einsammeln, und
Fehler darin verschwinden still („Task exception was never retrieved“). `spawn` merkt sich jede Aufgabe, bis sie
fertig ist, und schreibt Fehler ins Protokoll.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from typing import Any

log = logging.getLogger(__name__)
_RUNNING: set[asyncio.Future[Any]] = set()


def spawn(aw: Awaitable[Any]) -> asyncio.Future[Any]:
    task = asyncio.ensure_future(aw)
    _RUNNING.add(task)
    task.add_done_callback(_finished)
    return task


def _finished(task: asyncio.Future[Any]) -> None:
    _RUNNING.discard(task)
    if not task.cancelled() and task.exception() is not None:
        log.error("Hintergrund-Aufgabe fehlgeschlagen", exc_info=task.exception())


def running() -> int:
    return len(_RUNNING)
