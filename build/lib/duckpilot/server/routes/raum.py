"""Raumwissen (seit 0.37): Karte aus dem Kartierungsmodus und „Wo zuletzt gesehen“ – nur am PC (`remote.PC_ONLY`)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..runtime import Runtime


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/raum")
    async def raum() -> JSONResponse:
        return JSONResponse(runtime.raum.anzeige())

    @app.post("/api/raum")
    async def raum_aktion(request: Request) -> JSONResponse:
        body = await request.json()
        aktion = str(body.get("aktion") or "")
        r = runtime.raum
        if aktion == "start":
            res = await runtime.runner.run("karte", {"aktion": "start", "sekunden": body.get("sekunden", 120)})
            if res.get("ok") is False:
                return JSONResponse(res, status_code=409)
        elif aktion == "apportieren":
            res = await runtime.runner.run("apportieren", {"ding": str(body.get("ding") or "socke")})
            if res.get("ok") is False:
                return JSONResponse(res, status_code=409)
        elif aktion == "stopp":
            r.kartieren_stopp()
        elif aktion == "karte_leeren":
            r.kartieren_stopp()
            r.leeren()
        elif aktion == "sichtungen_vergessen":
            r.sichtungen.vergessen()
            r.speichern()
        else:
            return JSONResponse({"ok": False, "fehler": "unbekannte Aktion"}, status_code=400)
        return JSONResponse({"ok": True, **r.anzeige()})
