"""WonderDuck von Hiwonder (seit 0.53): ihr 3D-Modell laden und ausliefern (`modell/wonderduck.py`).

- `GET /api/wonderduck` – Stand des Modells (geladen? lädt gerade?)
- `GET /api/modell/wonderduck.dpm` – das gebackene Modell (404, solange es fehlt)
- `POST /api/wonderduck/laden` `{neu}` – laden und backen (nur am PC)

Wird die WonderDuck zum Körper und fehlt ihr Modell, lädt Knowlin es im Hintergrund (nie im Offline-Modus). Fortschritt
geht als Meldung `wonderduck` an alle Fenster; ist es fertig, lädt die 3D-Ansicht es nach.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ... import settings as S
from ...aio import spawn
from ...modell.wonderduck import WonderduckModellStore, offline
from ..runtime import Runtime
from ..security import _json_body

log = logging.getLogger(__name__)
ART = "wonderduck"


class WonderduckDienst:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.store = WonderduckModellStore(S.settings_path().parent)

    def aktiv(self) -> bool:
        return getattr(self.rt.backend, "koerper_art", "") == ART

    def meldung(self) -> dict[str, Any]:
        return {"type": "wonderduck", "modell": self.store.status()}

    def beim_zuweisen(self) -> None:
        """Die WonderDuck ist jetzt der Körper: fehlt ihr Modell, im Hintergrund holen."""
        if self.aktiv() and self.store.missing() and not self.store.job.get("laeuft"):
            spawn(self.laden())

    async def laden(self, force: bool = False) -> None:
        if self.store.job.get("laeuft") or offline():
            return
        self.store.job = {"laeuft": True, "text": "startet …", "fehler": None}
        await self.rt.broadcast(self.meldung())
        loop = asyncio.get_running_loop()

        def melde(text: str) -> None:
            self.store.job = {"laeuft": True, "text": text, "fehler": None}
            loop.call_soon_threadsafe(lambda: spawn(self.rt.broadcast(self.meldung())))

        try:
            res = await asyncio.to_thread(self.store.ensure, melde, force)
            self.store.job = {"laeuft": False, "fehler": None, "text": "fertig" if res else "schon da"}
        except Exception as exc:  # noqa: BLE001 – Laden darf nie den Rest stören
            from ...fehlerort import einordnen

            log.warning("WonderDuck-Modell nicht geladen: %s", exc)
            self.store.job = {"laeuft": False, "text": "fehlgeschlagen", "fehler": einordnen(exc, "GitHub")}
        await self.rt.broadcast(self.meldung())


def register(app: FastAPI, runtime: Runtime) -> None:
    dienst = WonderduckDienst(runtime)
    runtime.wonderduck_dienst = dienst

    @app.get("/api/wonderduck")
    async def wonderduck_status() -> JSONResponse:
        return JSONResponse({"ok": True, "aktiv": dienst.aktiv(), **dienst.store.status()})

    @app.get("/api/modell/wonderduck.dpm")
    async def wonderduck_ansicht():
        path = dienst.store.view_path()
        if path is None:
            return JSONResponse({"ok": False, "fehler": "Das WonderDuck-Modell ist noch nicht geladen"}, status_code=404)
        return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/wonderduck/laden")
    async def wonderduck_laden(request: Request) -> JSONResponse:
        body = await _json_body(request)
        if dienst.store.job.get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "lädt schon"}, status_code=409)
        spawn(dienst.laden(force=bool(body.get("neu"))))
        return JSONResponse({"ok": True})

    dienst.beim_zuweisen()                  # schon beim Start die WonderDuck? Dann gleich holen
