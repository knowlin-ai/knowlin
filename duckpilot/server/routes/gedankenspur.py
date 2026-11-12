"""Gedankenspur und Antrieb (seit 0.38.44, Etappe G3): ansehen überall, leeren nur am PC; Zeilen über Personen nur am PC."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..runtime import Runtime
from ..security import _is_remote


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/gedankenspur")
    async def gedankenspur(request: Request) -> JSONResponse:
        return JSONResponse({"zeilen": runtime.gedanken.liste(ohne_personen=_is_remote(request)),
                             "antrieb": runtime.antrieb.als_dict()})

    @app.delete("/api/gedankenspur")
    async def gedankenspur_leeren(request: Request) -> JSONResponse:
        if _is_remote(request):
            return JSONResponse({"ok": False, "fehler": "Die Gedankenspur lässt sich nur am PC leeren."}, status_code=403)
        runtime.gedanken.leeren()
        return JSONResponse({"ok": True})
