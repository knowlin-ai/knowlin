"""Körperschnittstelle (seit 0.38.35): welche Körper es gibt, ihr Wortschatz und abgelehnte Erweiterungen."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ... import koerper as K
from ..runtime import Runtime


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/koerper")
    async def koerper_liste() -> JSONResponse:
        """Alle Profile (eingebaute und Erweiterungen) und welcher gerade dranhängt."""
        return JSONResponse({"aktiv": runtime.config.modul, "koerper": [k.als_dict() for k in K.alle()],
                             "abgelehnt": K.abgelehnt(), "schnittstelle": K.SCHNITTSTELLE})

    @app.get("/api/koerper/wortschatz")
    async def koerper_wortschatz() -> JSONResponse:
        return JSONResponse(K.wortschatz())
