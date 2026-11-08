"""Parcours bauen und testen, Auftrag (Mission)."""

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
    # ── Parcours und Auftrag ─────────────────────────────────────────────
    @app.get("/api/parcours")
    async def parcours_status() -> JSONResponse:
        return JSONResponse(json.loads(json.dumps(runtime.lab_message(), default=_json_default)))

    @app.post("/api/parcours/bauen")
    async def parcours_build(request: Request) -> JSONResponse:
        from ...physics.course import PRESETS, CourseError

        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"ok": False, "fehler": "Erwartet ein Objekt"}, status_code=400)
        vorlage = str(body.get("vorlage") or "")
        if vorlage:
            if vorlage not in PRESETS:
                return JSONResponse({"ok": False, "fehler": "Unbekannte Vorlage"}, status_code=400)
            spec = {"name": vorlage, **PRESETS[vorlage]}
        else:
            spec = {"name": body.get("name") or "Parcours", "elemente": body.get("elemente") or []}
        try:
            res = runtime.lab.build(spec, body.get("ziel"))
        except CourseError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "parcours": res})

    @app.post("/api/parcours/testen")
    async def parcours_test(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
        quelle = str(body.get("quelle") or "standard")
        if runtime.runner.lab is None:
            return JSONResponse({"ok": False, "fehler": "Der Parcours braucht die echte Physik (Einstellungen → Körper)."},
                                status_code=400)
        if runtime.lab.course() is None:
            return JSONResponse({"ok": False, "fehler": "Es gibt noch keinen Parcours."}, status_code=400)
        if runtime.lab.job.get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "Es läuft schon ein Test."}, status_code=409)
        try:
            versuche = max(1, min(5, int(body.get("versuche") or 3)))
        except (TypeError, ValueError):
            versuche = 3

        async def go() -> None:
            try:
                await runtime.lab.test(quelle, versuche)
            except Exception as exc:
                log.info("Parcours-Test: %s", exc)

        spawn(go())
        return JSONResponse({"ok": True})

    @app.post("/api/parcours/abbrechen")
    async def parcours_cancel() -> JSONResponse:
        runtime.lab.cancel()
        return JSONResponse({"ok": True})

    @app.post("/api/parcours/auftrag")
    async def parcours_mission(request: Request) -> JSONResponse:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
        try:
            if body.get("id"):
                runtime.lab.missions.select(str(body["id"]))
            else:
                runtime.lab.missions.new(str(body.get("ziel") or ""))
        except KeyError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc).strip("'")}, status_code=404)
        runtime._lab_changed()
        return JSONResponse({"ok": True})

    @app.get("/api/parcours/wiederholung/{tid}")
    async def parcours_replay(tid: str) -> JSONResponse:
        frames = runtime.lab.missions.replay(tid)
        if frames is None:
            return JSONResponse({"ok": False, "fehler": "Keine Aufzeichnung"}, status_code=404)
        from ...physics.course import REPLAY_HZ

        return JSONResponse({"ok": True, "bilder": frames, "hz": REPLAY_HZ})

    @app.post("/api/training/vorschlag/verwerfen")
    async def training_drop() -> JSONResponse:
        runtime.trainer.vorschlag = None
        return JSONResponse({"ok": True})
