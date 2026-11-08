"""Reachy Mini (seit 0.38.2): Pollens 3D-Modell, Bewegungsbibliotheken, abspielen, Töne für den Simulator."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ...aio import spawn
from ..runtime import Runtime


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/reachy")
    async def reachy_status() -> JSONResponse:
        msg = runtime.reachy_message()
        return JSONResponse({"ok": True, "aktiv": runtime.ist_reachy(), **{k: v for k, v in msg.items() if k != "type"},
                             "liste": runtime.reachy_bewegungen.liste()})

    @app.get("/api/modell/reachy.dpm")
    async def reachy_ansicht():
        path = runtime.reachy_modell.view_path()
        if path is None:
            return JSONResponse({"ok": False, "fehler": "Pollens Reachy-Mini-Modell ist noch nicht geladen"}, status_code=404)
        return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/reachy/laden")
    async def reachy_laden(request: Request) -> JSONResponse:
        body = await request.json() if request.headers.get("content-length") not in (None, "0") else {}
        was = {"modell": ("modell",), "bewegungen": ("bewegungen",)}.get(str(body.get("was") or ""), ("modell", "bewegungen"))
        if runtime._reachy_lade_job.get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "lädt schon"}, status_code=409)
        spawn(runtime.reachy_laden(force=bool(body.get("neu")), was=was))
        return JSONResponse({"ok": True})

    @app.post("/api/reachy/bewegung")
    async def reachy_bewegung(request: Request) -> JSONResponse:
        body = await request.json()
        res = await runtime.reachy_spielen(str(body.get("name") or ""))
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)

    # Pollens Apps (seit 0.38.19): auflisten, starten, anhalten, aus Pollens Katalog installieren
    @app.get("/api/reachy/apps")
    async def reachy_apps(katalog: int = 0) -> JSONResponse:
        return JSONResponse(await runtime.reachy_apps(katalog=bool(katalog)))

    @app.post("/api/reachy/apps/starten")
    async def reachy_app_starten(request: Request) -> JSONResponse:
        res = await runtime.reachy_app_starten(str((await request.json()).get("name") or ""))
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)

    @app.post("/api/reachy/apps/stoppen")
    async def reachy_app_stoppen() -> JSONResponse:
        res = await runtime.reachy_app_stoppen()
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)

    @app.post("/api/reachy/apps/installieren")
    async def reachy_app_installieren(request: Request) -> JSONResponse:
        res = await runtime.reachy_app_installieren(str((await request.json()).get("name") or ""))
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)

    @app.get("/api/reachy/apps/auftrag/{job}")
    async def reachy_app_auftrag(job: str) -> JSONResponse:
        return JSONResponse(await runtime.reachy_app_auftrag(job))

    @app.get("/api/reachy/ton/{art}/{datei}")
    async def reachy_ton(art: str, datei: str):
        path = runtime.reachy_bewegungen.ton_pfad(art, datei)
        if path is None:
            return JSONResponse({"ok": False, "fehler": "Ton nicht gefunden"}, status_code=404)
        return FileResponse(path, headers={"Cache-Control": "max-age=86400"})
