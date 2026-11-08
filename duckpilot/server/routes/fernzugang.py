"""Handy-Fernbedienung verwalten (nur am PC – siehe remote.PC_ONLY)."""

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
    # ── Handy-Fernbedienung (verwalten nur am PC – siehe remote.PC_ONLY) ─────
    @app.get("/api/fernzugang")
    async def remote_get() -> JSONResponse:
        from ... import tailscale as TS

        msg = runtime.remote_message(with_qr=True)
        msg["tailscale"]["status"] = await asyncio.to_thread(TS.status)
        return JSONResponse(msg)

    @app.post("/api/fernzugang")
    async def remote_post(request: Request) -> JSONResponse:
        body = await _json_body(request)
        try:
            port = body.get("port")
            if port is not None and (isinstance(port, bool) or not isinstance(port, int)):
                raise ValueError("Port muss eine Zahl sein")
            an = body.get("an")
            await runtime.set_remote(an=bool(an) if an is not None else None, port=port)
            if "autostart" in body:
                from ...desktop import set_autostart

                await asyncio.to_thread(set_autostart, bool(body["autostart"]))
            if "tailscale" in body:
                res = await runtime.set_tailscale(bool(body["tailscale"]))
                if not res.get("ok"):
                    return JSONResponse({**runtime.remote_message(), "ok": False, "fehler": res.get("fehler"),
                                         "link": res.get("link")}, status_code=400)
        except (ValueError, RuntimeError, OSError) as exc:
            return JSONResponse({**runtime.remote_message(), "ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, **runtime.remote_message(with_qr=True)})

    @app.post("/api/fernzugang/code")
    async def remote_code() -> JSONResponse:
        try:
            runtime.remote.new_code()
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        msg = runtime.remote_message(with_qr=True)
        if not msg["adressen"] and not msg["tailscale"]["an"]:
            return JSONResponse({**msg, "ok": False,          # „fehler“ zuletzt – sonst überschreibt es der Status (0.38.28)
                                 "fehler": "Kein Heimnetz gefunden – ist der PC im WLAN oder per Kabel im Netz?"}, status_code=400)
        return JSONResponse({"ok": True, **msg})

    @app.delete("/api/fernzugang/code")
    async def remote_code_cancel() -> JSONResponse:
        runtime.remote.cancel_code()
        return JSONResponse({"ok": True, **runtime.remote_message()})

    @app.delete("/api/fernzugang/geraet/{did}")
    async def remote_revoke(did: str) -> JSONResponse:
        if not runtime.remote.revoke(did):
            return JSONResponse({"ok": False, "fehler": "Gerät nicht gefunden"}, status_code=404)
        await runtime.kick_remote_clients(did)
        return JSONResponse({"ok": True, **runtime.remote_message()})

    @app.delete("/api/fernzugang/geraete")
    async def remote_revoke_all() -> JSONResponse:
        runtime.remote.revoke_all()
        await runtime.kick_remote_clients()
        return JSONResponse({"ok": True, **runtime.remote_message()})
