"""Spracherkennung am PC und die WebSocket-Verbindung der Oberfläche."""

from __future__ import annotations

import json
import logging
import time

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from ... import remote as R
from ..runtime import (
    Runtime,
    _json_default,
)
from ..security import origin_allowed

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    register_test(app)

    @app.post("/api/stt")
    async def stt(request: Request) -> JSONResponse:
        if runtime.stt is None:
            return JSONResponse({"error": "lokale Spracherkennung ist nicht aktiv"}, status_code=400)
        audio = await request.body()
        if len(audio) > 10_000_000:
            return JSONResponse({"error": "Aufnahme zu groß"}, status_code=413)
        t0 = time.monotonic()
        try:
            text = await runtime.stt.transcribe(audio)
        except Exception as exc:
            return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)
        return JSONResponse({"text": text, "seconds": round(time.monotonic() - t0, 2)})

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        via_ts = bool(runtime.remote.data.get("tailscale") and R.ts_hostname(ws.headers.get("host")))
        if not origin_allowed(ws.headers.get("origin"), ws.headers.get("host"), via_ts):
            await ws.close(code=1008)
            return
        client = ws.client.host if ws.client else None
        device = None
        if via_ts and not R.is_local(client):
            await ws.close(code=1008)
            return
        if not via_ts and R.is_local(client) and R.proxied(ws.headers):
            await ws.close(code=1008)          # anderer Weiterleiter auf diesem PC: nie „der PC selbst“
            return
        if via_ts or not R.is_local(client):
            if runtime.remote.check(client, ws.cookies.get(R.COOKIE), "GET", "/ws", via_tailscale=via_ts) is not None:
                await ws.close(code=4401)
                return
            device = runtime.remote.device_for(ws.cookies.get(R.COOKIE))
        await ws.accept()
        ws.fern_geraet = device["id"] if device else None
        if device is None:
            runtime.keep_open = False        # neues Fenster am PC: Schließen beendet wieder wie gewohnt
        try:
            # erst die Grundausstattung, dann in die Verteilerliste – so kommt nie ein Zustand vor dem Start-Paket
            for first in (runtime.init_message(), runtime.memory_message(), runtime.alltag.message(),
                          {"type": "verbindung", "fern": device is not None, "geraet": device["name"] if device else None},
                          runtime.erfahrung.message(remote=device is not None)):
                await runtime.send_to(ws, json.dumps(first, ensure_ascii=False, default=_json_default))
            runtime.clients.add(ws)
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    try:
                        await runtime.handle_client_message(msg, remote=device is not None)
                    except Exception:            # eine kaputte Nachricht darf die Verbindung nicht kappen
                        log.exception("Nachricht %s", str(msg.get("type"))[:40])
        except WebSocketDisconnect:
            pass
        finally:
            runtime.clients.discard(ws)


def register_test(app: FastAPI) -> None:
    """Verbindungstest vor dem ersten Start am echten Roboter (seit 0.38.16) – nur lesend, nur am PC."""
    from ...verbindungstest import KOERPER, pruefen

    @app.post("/api/verbindungstest")
    async def verbindungstest(request: Request) -> JSONResponse:
        body = await request.json()
        koerper = str(body.get("koerper") or "microduck")
        if koerper not in KOERPER:
            return JSONResponse({"ok": False, "fehler": "unbekannter Körper"}, status_code=400)
        return JSONResponse(await pruefen(koerper, str(body.get("adresse") or "")[:200]))
