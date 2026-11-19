"""Spracherkennung am PC und die WebSocket-Verbindung der Oberfläche."""

from __future__ import annotations

import asyncio
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

    async def start_paket(ws: WebSocket, device: dict | None) -> None:
        teile = (("Grundausstattung", runtime.init_message), ("Gedächtnis", runtime.memory_message),
                 ("Alltag", runtime.alltag.message),
                 ("Verbindung", lambda: {"type": "verbindung", "fern": device is not None,
                                         "geraet": device["name"] if device else None}),
                 ("Erfahrung", lambda: runtime.erfahrung.message(remote=device is not None)))
        fehler = []
        for name, bauen in teile:
            try:
                text = json.dumps(bauen(), ensure_ascii=False, default=_json_default)
            except Exception as exc:
                log.exception("Start-Paket für das Fenster: %s", name)
                fehler.append(f"{name}: {runtime.startfehler.merken(exc)}")
                continue
            await runtime.send_to(ws, text)
        if fehler:
            await runtime.send_to(ws, json.dumps({"type": "startfehler", "grund": " · ".join(fehler)[:600]},
                                                 ensure_ascii=False))
        else:
            runtime.startfehler.loeschen()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        via_ts = bool(runtime.remote.data.get("tailscale") and R.ts_hostname(ws.headers.get("host")))
        diagnose = runtime.startfehler
        if not origin_allowed(ws.headers.get("origin"), ws.headers.get("host"), via_ts):
            # Herkunft und Adresse sind Seiten-Adressen (z. B. http://127.0.0.1:8765), keine Personendaten
            diagnose.abgelehnt(f"Herkunft passt nicht zur Adresse (Herkunft {str(ws.headers.get('origin'))[:60]}, "
                               f"Adresse {str(ws.headers.get('host'))[:60]})")
            await ws.close(code=1008)
            return
        client = ws.client.host if ws.client else None
        device = None
        if via_ts and not R.is_local(client):
            diagnose.abgelehnt("Tailscale-Adresse, aber nicht vom eigenen PC weitergeleitet")
            await ws.close(code=1008)
            return
        if not via_ts and R.is_local(client) and R.proxied(ws.headers):
            # anderer Weiterleiter auf diesem PC: nie „der PC selbst“ – oft ein Web-Schutz oder VPN, der mitliest
            diagnose.abgelehnt("über einen Weiterleiter (Proxy) auf diesem PC – z. B. Web-Schutz der Sicherheitssoftware oder VPN")
            await ws.close(code=1008)
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
            # erst die Grundausstattung, dann in die Verteilerliste – so kommt nie ein Zustand vor dem Start-Paket.
            # Scheitert ein Teil, bleibt die Verbindung offen und das Fenster bekommt den Grund (Fund 19.11.: vorher
            # schloss die Verbindung kommentarlos, und das Fenster blieb bei „verbinde …“ stehen).
            await start_paket(ws, device)
            runtime.clients.add(ws)
            fern = device is not None

            async def ausfuehren(msg: dict) -> None:
                try:
                    await runtime.handle_client_message(msg, remote=fern)
                except Exception:                # eine kaputte Nachricht darf die Verbindung nicht kappen
                    log.exception("Nachricht %s", str(msg.get("type"))[:40])

            # Nachrichten der Reihe nach – aber der Not-Aus wartet auf nichts (Fund 14.11.: während „Aufwachen“ wirkte
            # er erst nach 11 bis 22 s, weil er hinter dem laufenden Werkzeug in derselben Schlange stand). Er läuft
            # sofort neben allem, was gerade arbeitet, und was davor bestellt und noch nicht dran war, verfällt.
            schlange: asyncio.Queue[dict] = asyncio.Queue()

            async def arbeiter() -> None:
                while True:
                    await ausfuehren(await schlange.get())

            arbeit = asyncio.create_task(arbeiter())
            try:
                while True:
                    raw = await ws.receive_text()
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("type") == "stop":
                        while not schlange.empty():
                            schlange.get_nowait()
                        await ausfuehren(msg)
                    else:
                        schlange.put_nowait(msg)
            finally:
                arbeit.cancel()
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
