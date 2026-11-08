"""Pollens Robotermodell im laufenden duckpilot laden – Fortschritt geht an alle Fenster."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..aio import spawn

if TYPE_CHECKING:  # pragma: no cover
    from ..server.runtime import Runtime

log = logging.getLogger(__name__)


async def load(rt: "Runtime", force: bool = False) -> None:
    """Von GitHub laden und auf diesem PC für 3D-Ansicht und Physik aufbereiten."""
    store = rt.modell
    if store.job.get("laeuft"):
        return
    store.job = {"laeuft": True, "text": "startet …", "fehler": None}
    await rt.broadcast(rt.modell_message())
    loop = asyncio.get_running_loop()

    def progress(text: str) -> None:
        store.job["text"] = text
        loop.call_soon_threadsafe(lambda: spawn(rt.broadcast(rt.modell_message())))

    try:
        res = await asyncio.to_thread(store.ensure, True, True, progress, force)
        fertig = [n for n, k in (("3D-Ansicht", "ansicht"), ("Physik", "physik")) if k in res]
        store.job = {"laeuft": False, "fehler": None, "text": f"fertig: {', '.join(fertig)}" if fertig else "schon da"}
    except Exception as exc:
        log.warning("Pollens Modell nicht geladen: %s", exc)
        store.job = {"laeuft": False, "text": "fehlgeschlagen", "fehler": f"{type(exc).__name__}: {exc}"}
    await rt.broadcast(rt.modell_message())
    await rt.broadcast(rt.physik_message())
