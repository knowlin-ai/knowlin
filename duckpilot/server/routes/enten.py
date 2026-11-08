"""Mehrere Enten im Simulator (seit 0.36.3): Übersicht, Modus der Gruppe, mittanzen."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...motion.schwarm import MODI
from ..runtime import Runtime


def register(app: FastAPI, runtime: Runtime) -> None:
    def info() -> dict:
        sw = getattr(runtime, "schwarm", None)
        if sw is None:
            return {"verfuegbar": False, "grund": "Weitere Enten gibt es im einfachen Simulator (nicht in der echten Physik "
                                                  "und nicht am Roboter).", "enten": [], "anzahl": 0}
        return {"verfuegbar": True, "anzahl": len(sw.enten), "modus": sw.modus, "mittanzen": sw.mittanzen,
                "modi": list(MODI), "enten": sw.uebersicht(),
                "auftrag": sw.auftrag.zustand() if sw.auftrag is not None else None}

    @app.get("/api/enten")
    async def enten() -> JSONResponse:
        return JSONResponse(info())

    @app.post("/api/enten")
    async def enten_setzen(request: Request) -> JSONResponse:
        body = await request.json()
        sw = getattr(runtime, "schwarm", None)
        if sw is None:
            return JSONResponse({"ok": False, **info()}, status_code=409)
        if "modus" in body and not sw.setze_modus(str(body["modus"])):
            return JSONResponse({"ok": False, "fehler": "unbekannter Modus"}, status_code=400)
        if body.get("auftrag") == "stopp":
            sw.auftrag_stopp()
        if "mittanzen" in body:
            sw.mittanzen = bool(body["mittanzen"])
        return JSONResponse({"ok": True, **info()})
