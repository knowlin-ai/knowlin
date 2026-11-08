"""Kollisionsmodus (nur Simulator mit echter Physik): Ente anstoßen, Ball und Würfel greifen, rollen, werfen."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...kollision_service import KollisionService
from ..runtime import Runtime
from ..security import _json_body


def register(app: FastAPI, runtime: Runtime) -> None:
    runtime.kollision = KollisionService(runtime)      # type: ignore[attr-defined]
    svc: KollisionService = runtime.kollision          # type: ignore[attr-defined]

    def answer(res: dict) -> JSONResponse:
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)

    @app.get("/api/kollision")
    async def kollision_status() -> JSONResponse:
        return JSONResponse({"ok": True, **svc.status()})

    @app.post("/api/kollision")
    async def kollision_schalten(request: Request) -> JSONResponse:
        body = await _json_body(request)
        return answer(await svc.schalten(bool(body.get("aktiv"))))

    for art in ("stoss", "wurf", "rollen", "objekt"):
        def make(a: str):
            async def route(request: Request) -> JSONResponse:
                return answer(await svc.tun(a, await _json_body(request)))
            route.__name__ = f"kollision_{a}"
            return route
        app.post(f"/api/kollision/{art}")(make(art))
