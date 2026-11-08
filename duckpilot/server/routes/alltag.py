"""Alltagsbuddy: Wecker, Erinnerungen, Ruhe/Aktiv."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import remote as R
from ..runtime import (
    Runtime,
)
from ..security import _is_remote, _json_body

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    # ── Alltagsbuddy ─────────────────────────────────────────────────────
    def _alltag_off() -> JSONResponse | None:
        if not runtime.alltag.on:
            return JSONResponse({"ok": False, "fehler": "Der Alltagsbuddy ist aus (System → Erweiterungen)."}, status_code=400)
        return None

    @app.get("/api/alltag")
    async def alltag_get() -> JSONResponse:
        return JSONResponse({"ok": True, **runtime.alltag.message()})

    @app.post("/api/alltag/befehl")
    async def alltag_command(request: Request) -> JSONResponse:
        if (r := _alltag_off()) is not None:
            return r
        body = await _json_body(request)
        runtime.alltag.touch(wake=False)
        tok = R.REMOTE_TURN.set(_is_remote(request))      # „wer ist da“ nie an ein Handy
        try:
            res = await runtime.alltag.command(body)
        finally:
            R.REMOTE_TURN.reset(tok)
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)

    @app.post("/api/alltag/todo/{tid}")
    async def alltag_todo(tid: str, request: Request) -> JSONResponse:
        body = await _json_body(request)
        it = runtime.alltag.planner.finish_todo(tid, bool(body.get("erledigt", True)))
        await runtime.alltag.push()
        return JSONResponse({"ok": it is not None})

    @app.post("/api/alltag/todos/aufraeumen")
    async def alltag_clear() -> JSONResponse:
        n = runtime.alltag.planner.clear_done()
        await runtime.alltag.push()
        return JSONResponse({"ok": True, "entfernt": n})

    @app.delete("/api/alltag/{art}/{iid}")
    async def alltag_delete(art: str, iid: str) -> JSONResponse:
        try:
            it = runtime.alltag.planner.remove(art, iid)
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        await runtime.alltag.push()
        return JSONResponse({"ok": it is not None})

    @app.post("/api/alltag/alarm/{aid}")
    async def alltag_alarm(aid: str, request: Request) -> JSONResponse:
        body = await _json_body(request)
        runtime.alltag.touch(wake=False)
        if body.get("schlummern"):
            try:
                minutes = int(body.get("minuten") or 5)
                item = runtime.alltag.snooze(aid, minutes)
            except (TypeError, ValueError) as exc:
                return JSONResponse({"ok": False, "fehler": str(exc) or "Ungültige Minuten."}, status_code=400)
            ok = item is not None
        else:
            ok = runtime.alltag.ack(aid)
        await runtime.alltag.push()
        return JSONResponse({"ok": ok})

    @app.post("/api/alltag/optionen")
    async def alltag_options(request: Request) -> JSONResponse:
        body = await _json_body(request)
        if _is_remote(request) and set(body) & R.PC_ONLY_OPTIONS:
            why = "Sehen und Personen erkennen schaltest du nur direkt am PC ein oder aus."
            return JSONResponse({"ok": False, "fehler": why, "nur_pc": True}, status_code=403)
        try:
            if "modus" in body:
                await runtime.alltag.set_mode(str(body.pop("modus")), "über die Oberfläche")
            opts = runtime.alltag.planner.set_options(**{k: v for k, v in body.items()
                                                          if k in ("ruhe_nach_min", "wecken", "durchsagen", "sehen",
                                                                   "personen", "begruessen", "augen")})
        except (ValueError, TypeError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        await runtime.alltag.push()
        return JSONResponse({"ok": True, "optionen": opts})

    @app.post("/api/alltag/ics")
    async def alltag_ics(request: Request) -> JSONResponse:
        if (r := _alltag_off()) is not None:
            return r
        raw = await request.body()
        if len(raw) > 2_000_000:
            return JSONResponse({"ok": False, "fehler": "Datei zu groß (höchstens 2 MB)."}, status_code=413)
        text = raw.decode("utf-8", errors="replace")
        if "BEGIN:VCALENDAR" not in text[:2000]:
            return JSONResponse({"ok": False, "fehler": "Das ist keine Kalenderdatei (.ics)."}, status_code=400)
        try:
            res = await asyncio.to_thread(runtime.alltag.planner.import_ics, text)
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        await runtime.alltag.push()
        return JSONResponse({"ok": True, **res})
