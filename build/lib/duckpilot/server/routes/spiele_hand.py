"""Handerkennung für die Kamera-Spiele (seit 0.38.14): Stand, Laden auf Klick, Dateien vom eigenen Server.

Alles unter `/api/spiele…` und damit nur am PC (`remote.PC_ONLY`). Geladen wird nur nach dem Klick
„Handerkennung laden“ (`POST /api/spiele/hand/laden`), mit fester Version und Prüfsummen (`modell/hand.py`).
Der Browser holt Laufzeit und Modell danach von hier – nie von einem CDN.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from ...aio import spawn
from ...modell import hand as H
from ..runtime import Runtime

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    store = H.store()
    runtime.hand = store                                # für die Spiele (Schere, Stein, Papier) und Tests

    async def laden() -> None:
        store.job = {"laeuft": True, "text": "startet …", "fehler": None}

        def melden(text: str) -> None:
            store.job["text"] = text

        try:
            res = await asyncio.to_thread(store.ensure, melden)
            store.job = {"laeuft": False, "fehler": None,
                         "text": "fertig – Handerkennung bereit" if res["geladen"] else "war schon da"}
        except Exception as exc:  # noqa: BLE001 – Netz, Prüfsumme, Platte: alles ehrlich melden
            log.warning("Handerkennung nicht geladen: %s", exc)
            store.job = {"laeuft": False, "text": "fehlgeschlagen", "fehler": f"{type(exc).__name__}: {exc}"}

    @app.get("/api/spiele/hand")
    async def hand_status() -> JSONResponse:
        return JSONResponse(await asyncio.to_thread(store.status))

    @app.post("/api/spiele/hand/laden")
    async def hand_laden() -> JSONResponse:
        if store.job.get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "Die Handerkennung wird schon geladen."}, status_code=409)
        if H.offline():
            return JSONResponse({"ok": False, "fehler": "Offline-Modus – die Handerkennung wird nicht geladen."},
                                status_code=409)
        store.job = {"laeuft": True, "text": "startet …", "fehler": None}
        spawn(laden())
        return JSONResponse({"ok": True})

    @app.get("/api/spiele/hand/dateien/{name}")
    async def hand_datei(name: str):
        pfad = await asyncio.to_thread(store.datei, name)
        if pfad is None:
            return JSONResponse({"ok": False, "fehler": "Die Handerkennung ist nicht geladen."}, status_code=404)
        return FileResponse(pfad, media_type=H.medientyp(name), headers={"Cache-Control": "no-cache"})
