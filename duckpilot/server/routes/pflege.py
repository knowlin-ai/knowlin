"""Gelenk-Check und Pflege des echten Roboters."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..runtime import (
    Runtime,
    _json_default,
)

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    # ── Gelenk-Check und Abgleich Training ↔ Roboter ─────────────────────
    @app.get("/api/gelenke")
    async def joints_report() -> JSONResponse:
        from ...joints import ALIGNMENT

        try:
            rep = runtime.backend.joint_report()
        except Exception as exc:                     # die Abgleich-Tabelle gibt es trotzdem
            return JSONResponse({"ok": False, "fehler": f"{type(exc).__name__}: {exc}", "abgleich": ALIGNMENT})
        return JSONResponse({"ok": True, **rep, "abgleich": ALIGNMENT})

    # ── Roboter-Pflege ───────────────────────────────────────────────────
    def _robot_only():
        if runtime.config.backend != "robotd":
            return JSONResponse({"ok": False, "fehler": "Nur mit dem echten Roboter (Einstellungen → Körper)."},
                                status_code=400)
        return None

    @app.get("/api/pflege")
    async def care_overview() -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        return JSONResponse(json.loads(json.dumps(await runtime.care.overview(), default=_json_default)))

    @app.post("/api/pflege/pruefen")
    async def care_check() -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        try:
            return JSONResponse({"ok": True, "ergebnis": await runtime.care.check()})
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=502)

    @app.post("/api/pflege/einspielen")
    async def care_apply(request: Request) -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        body = await request.json()
        if runtime.care.job.get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "läuft schon"}, status_code=409)
        job = await runtime.care.apply(dry_run=body.get("probe") is not False)
        return JSONResponse({"ok": not job.get("fehler"), **job})

    @app.get("/api/pflege/protokoll")
    async def care_logs(dienst: str = "robotd", zeilen: int = 200) -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        try:
            return JSONResponse({"ok": True, **(await runtime.care.logs(dienst, zeilen) or {})})
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400 if isinstance(exc, ValueError) else 502)
