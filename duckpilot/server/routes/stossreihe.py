"""Stoßreihe (Lernen → Training): viele unsichtbare Stöße, ein Robustheits-Profil. Nur am PC (`remote.PC_ONLY`),
nie über MCP – es gibt dafür kein Werkzeug."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...stossreihe_service import StossreiheDienst
from ..runtime import Runtime
from ..security import _json_body


def register(app: FastAPI, runtime: Runtime) -> None:
    runtime.stossreihe = StossreiheDienst(runtime)      # type: ignore[attr-defined]
    svc: StossreiheDienst = runtime.stossreihe          # type: ignore[attr-defined]

    def answer(res: dict) -> JSONResponse:
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)

    @app.get("/api/kollision/reihe")
    async def reihe_status() -> JSONResponse:
        return JSONResponse({"ok": True, **svc.status()})

    @app.post("/api/kollision/reihe")
    async def reihe_start(request: Request) -> JSONResponse:
        return answer(await svc.start(await _json_body(request)))

    @app.post("/api/kollision/reihe/stopp")
    async def reihe_stopp() -> JSONResponse:
        return answer(await svc.stopp())

    @app.get("/api/kollision/reihe/profile")
    async def reihe_profile() -> JSONResponse:
        return JSONResponse(svc.profile())

    @app.get("/api/kollision/reihe/profile/{pid}")
    async def reihe_profil(pid: str) -> JSONResponse:
        res = svc.profil(pid)
        return JSONResponse(res, status_code=200 if res.get("ok") else 404)
