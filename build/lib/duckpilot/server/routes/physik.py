"""Echte Physik (MuJoCo) im Simulator."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...aio import spawn
from ..runtime import (
    Runtime,
    _json_default,
)

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    # ── Echte Physik ─────────────────────────────────────────────────────
    @app.get("/api/physik")
    async def physik_status() -> JSONResponse:
        return JSONResponse(json.loads(json.dumps(runtime.physik_message(), default=_json_default)))

    @app.post("/api/physik/laden")
    async def physik_load() -> JSONResponse:
        if runtime.physik_job.get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "lädt schon"}, status_code=409)
        spawn(runtime.load_policies())
        return JSONResponse({"ok": True})

    @app.post("/api/physik/zuruecksetzen")
    async def physik_reset() -> JSONResponse:
        reset = getattr(runtime.backend, "reset_body", None)
        if reset is None:
            return JSONResponse({"ok": False, "fehler": "Nur im Physik-Simulator"}, status_code=400)
        await runtime.engine.stop_all("Zurücksetzen")
        reset()
        return JSONResponse({"ok": True})

    @app.post("/api/physik/ueben")
    async def physik_practice(request: Request) -> JSONResponse:
        body = await request.json()
        res = await runtime.runner.run("bewegung_ueben", {"keyframes": body.get("keyframes") or [],
                                                         "loops": body.get("loops") or 1, "title": body.get("titel")})
        await runtime.broadcast(runtime.physik_message())
        return JSONResponse(json.loads(json.dumps(res, default=_json_default)), status_code=200 if res.get("ok") else 400)
