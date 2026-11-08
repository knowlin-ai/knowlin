"""Pollens Robotermodell: Stand, Datei für die 3D-Ansicht, Laden von GitHub (nur am PC)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from ...aio import spawn
from ..runtime import Runtime


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/modell")
    async def modell_status() -> JSONResponse:
        return JSONResponse(runtime.modell_message())

    @app.get("/api/modell/ansicht.dpm")
    async def modell_ansicht():
        path = runtime.modell.view_path()
        if path is None:
            return JSONResponse({"ok": False, "fehler": "Pollens 3D-Modell ist noch nicht geladen"}, status_code=404)
        return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/modell/laden")
    async def modell_laden() -> JSONResponse:
        if runtime.modell.job.get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "lädt schon"}, status_code=409)
        spawn(runtime.load_modell(force=True))
        return JSONResponse({"ok": True})
