"""Beenden wie bei Windows: ganz, im Hintergrund oder neu starten."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..runtime import (
    Runtime,
)
from ..security import _json_body

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/beenden")
    async def quit_state() -> JSONResponse:
        return JSONResponse(runtime.quit_message())

    @app.post("/api/beenden")
    async def quit_app(request: Request) -> JSONResponse:
        body = await _json_body(request)
        return await _quit(str(body.get("art") or "ganz"))

    async def _quit(art: str) -> JSONResponse:
        """Wie bei Windows-Programmen: ganz beenden, im Hintergrund weiterlaufen oder neu starten."""
        if art not in ("ganz", "hintergrund", "neustart"):
            return JSONResponse({"ok": False, "fehler": "art: ganz, hintergrund oder neustart"}, status_code=400)
        if runtime.on_idle_exit is None or not runtime.config.app_mode:
            return JSONResponse({"ok": False, "fehler": "Nur im Programmfenster möglich – sonst die Konsole schließen."},
                                status_code=400)
        if art == "hintergrund":
            runtime.keep_open = True
            if runtime.alltag.on and runtime.alltag.mode != "ruhe":
                await runtime.alltag.set_mode("ruhe", "läuft im Hintergrund weiter")
            return JSONResponse({"ok": True, **runtime.quit_message()})
        runtime.restart = art == "neustart"
        if runtime.restart and getattr(runtime, "spawn_restart", None):
            await asyncio.to_thread(runtime.spawn_restart)   # neuer Prozess zuerst – er wartet, bis der Port frei ist
        await runtime.broadcast_local({"type": "beendet", "neustart": runtime.restart})
        asyncio.get_running_loop().call_later(0.6, runtime.on_idle_exit)
        return JSONResponse({"ok": True, "neustart": runtime.restart})

    @app.post("/api/fernzugang/beenden")
    async def remote_quit() -> JSONResponse:
        """duckpilot ganz beenden (läuft mit Handy-Fernbedienung sonst im Hintergrund weiter)."""
        return await _quit("ganz")
