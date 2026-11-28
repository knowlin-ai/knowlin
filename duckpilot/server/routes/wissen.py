"""Ein Kopf, viele Körper (seit 0.56): Übersicht über geteiltes Wissen und Tricks anderer Verkörperungen übernehmen.

- `GET /api/wissen/koerper` – was alle teilen (mit Herkunft), Orte je Zimmer, Tricks der anderen (übertragbar?)
- `POST /api/wissen/trick_uebernehmen` `{von, name}` – Trick einer Verkörperung derselben Familie kopieren
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...brain import wissen_teilen as W
from ..runtime import Runtime
from ..security import _json_body


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/wissen/koerper")
    async def wissen_koerper() -> JSONResponse:
        return JSONResponse(W.uebersicht(runtime.memory, runtime.config.modul))

    @app.post("/api/wissen/trick_uebernehmen")
    async def trick_uebernehmen(request: Request) -> JSONResponse:
        body = await _json_body(request)
        try:
            key = W.trick_uebernehmen(runtime.memory, runtime.config.modul, str(body.get("von") or ""),
                                      str(body.get("name") or ""))
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=409)
        await runtime.broadcast(runtime.memory_message())
        return JSONResponse({"ok": True, "trick": key, **W.uebersicht(runtime.memory, runtime.config.modul)})
