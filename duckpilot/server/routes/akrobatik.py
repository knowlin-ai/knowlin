"""Akrobatik mit der Gliederpuppe (nur Simulation)."""

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
    # ── Akrobatik (Gliederpuppe, nur Simulation) ─────────────────────────
    def _acro_err(exc: Exception, code: int = 400) -> JSONResponse:
        return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=code)

    @app.get("/api/akrobatik")
    async def acro_overview() -> JSONResponse:
        return JSONResponse({"ok": True, **(await asyncio.to_thread(runtime.acro.overview))})

    @app.post("/api/akrobatik/pruefen")
    async def acro_check(request: Request) -> JSONResponse:
        body = await _json_body(request)
        try:
            return JSONResponse({"ok": True, **(await asyncio.to_thread(runtime.acro.check, body.get("pose")))})
        except ImportError as exc:
            return _acro_err(exc, 503)

    @app.post("/api/akrobatik/probe")
    async def acro_probe(request: Request) -> JSONResponse:
        body = await _json_body(request)
        try:
            return JSONResponse({"ok": True, **(await asyncio.to_thread(runtime.acro.probe, body.get("pose")))})
        except ImportError as exc:
            return _acro_err(exc, 503)

    @app.post("/api/akrobatik/ueben")
    async def acro_practice(request: Request) -> JSONResponse:
        body = await _json_body(request)
        try:
            job = runtime.acro.start_practice(body.get("pose"), str(body.get("uebung", "")))
        except RuntimeError as exc:
            return _acro_err(exc, 409)
        except (ValueError, ImportError) as exc:
            return _acro_err(exc)
        return JSONResponse({"ok": True, "job": job})

    @app.get("/api/akrobatik/job")
    async def acro_job() -> JSONResponse:
        return JSONResponse({"ok": True, "job": runtime.acro.job})

    @app.post("/api/akrobatik/abbrechen")
    async def acro_cancel() -> JSONResponse:
        runtime.acro.cancel()
        return JSONResponse({"ok": True})

    @app.post("/api/akrobatik/haltung")
    async def acro_save_pose(request: Request) -> JSONResponse:
        body = await _json_body(request)
        try:
            return JSONResponse({"ok": True, **runtime.acro.save_pose(body.get("name", ""), body.get("pose"))})
        except ValueError as exc:
            return _acro_err(exc)

    @app.delete("/api/akrobatik/haltung/{name}")
    async def acro_delete_pose(name: str) -> JSONResponse:
        return JSONResponse({"ok": runtime.acro.delete_pose(name)})
