"""Augen und Personen (nur am PC, mit Einwilligung, nur lokal)."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...aio import spawn
from ..runtime import (
    Runtime,
)
from ..security import _json_body

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    # ── Augen und Personen (nur am PC) ───────────────────────────────────
    @app.post("/api/augen/bild")
    async def eyes_frame(request: Request, quelle: str = "simulator") -> JSONResponse:
        data = await request.body()
        try:
            runtime.eyes.receive(data, quelle)
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({"ok": True})

    def _persons_message() -> dict[str, Any]:
        ok, why = runtime.faces.available()
        from ...voice.install import missing

        return {"verfuegbar": ok, "grund": None if ok else why, "pakete_fehlen": missing("gesichter"),
                "modelle_da": runtime.faces.models_present(), "personen": runtime.faces.persons(),
                "an": bool(runtime.alltag.planner.data.get("personen")), "laden": runtime.__dict__.get("faces_job")}

    @app.get("/api/personen")
    async def persons_get() -> JSONResponse:
        return JSONResponse(_persons_message())

    @app.post("/api/personen/modelle")
    async def persons_models() -> JSONResponse:
        if (runtime.__dict__.get("faces_job") or {}).get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "Lädt schon."}, status_code=409)
        job = {"laeuft": True, "anteil": 0.0, "fehler": None}
        runtime.faces_job = job

        async def run() -> None:
            def prog(f: float) -> None:
                job["anteil"] = round(float(f), 3)
            try:
                await asyncio.to_thread(runtime.faces.ensure_models, prog)
            except Exception as exc:
                job["fehler"] = str(exc)
            job["laeuft"] = False
            await runtime.broadcast_local({"type": "personen", **_persons_message()})

        spawn(run())
        return JSONResponse({"ok": True, **_persons_message()})

    @app.post("/api/personen/anlernen")
    async def persons_enroll(request: Request) -> JSONResponse:
        body = await _json_body(request)
        imgs = []
        for item in (body.get("bilder") or [])[:12]:
            if isinstance(item, str):
                b64 = item.split(",", 1)[1] if item.startswith("data:") else item
                try:
                    imgs.append(base64.b64decode(b64, validate=True))
                except ValueError:
                    continue
        res = await asyncio.to_thread(runtime.faces.enroll, str(body.get("name") or ""), imgs,
                                      body.get("einverstanden") is True)
        imgs.clear()                                     # Bilder nie behalten
        return JSONResponse({**res, **_persons_message()}, status_code=200 if res.get("ok") else 400)

    @app.delete("/api/personen/{name}")
    async def persons_delete(name: str) -> JSONResponse:
        ok = await asyncio.to_thread(runtime.faces.delete, name)
        return JSONResponse({"ok": ok, **_persons_message()}, status_code=200 if ok else 404)

    @app.delete("/api/personen")
    async def persons_delete_all() -> JSONResponse:
        n = await asyncio.to_thread(runtime.faces.delete_all)
        runtime._greeted.clear()
        return JSONResponse({"ok": True, "geloescht": n, **_persons_message()})
