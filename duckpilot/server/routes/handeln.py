"""Anwählen und Handeln (seit 0.37.3): Was kann die Ente mit dem angeklickten Ding tun – und tu es."""

from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...brain import handeln as H
from ..runtime import Runtime


def register(app: FastAPI, runtime: Runtime) -> None:
    def finden(name: str):
        return H.ding_finden(name, runtime.backend, getattr(runtime, "schwarm", None))

    @app.get("/api/handeln")
    async def handeln_info(ding: str = "") -> JSONResponse:
        d = finden(ding)
        if d is None:
            return JSONResponse({"ok": False, "fehler": "unbekanntes Ding"}, status_code=404)
        if d.get("werkbank"):                    # Würfel und Kisten des Arms (seit 0.38.53)
            return JSONResponse({"ok": True, "ding": d, "aktionen": H.werkbank_aktionen(d, runtime.backend),
                                 "tipp": H.WERKBANK_TIPP})
        return JSONResponse({"ok": True, "ding": d, "aktionen": H.aktionen(d["art"], runtime.backend) + H.reachy_aktionen(d, runtime.backend)})

    @app.post("/api/handeln")
    async def handeln(request: Request) -> JSONResponse:
        body = await request.json()
        if "auswahl" in body:                     # angewählt (oder abgewählt) – gilt für „das hier“ im Chat
            d = finden(str(body.get("auswahl") or "")) if body.get("auswahl") else None
            runtime.auswahl = {**d, "seit": time.monotonic()} if d else None
            return JSONResponse({"ok": True, "auswahl": d})
        args = {"ding": str(body.get("ding") or ""), "aktion": str(body.get("aktion") or "")}
        if args["aktion"] in (H.REACHY_STELLEN[0], H.REACHY_BODEN[0]):    # Reachy umstellen (seit 0.38.10)
            r = H.reachy_platzieren(runtime.backend, args["ding"], args["aktion"])
            await runtime.broadcast({"type": "action", "tool": "szene", "input": body, "result": r})
            return JSONResponse(r, status_code=200 if r["ok"] else 409)
        d = finden(args["ding"])
        if d is not None and d.get("werkbank"):  # Arm an der Werkbank: greifen und ablegen (seit 0.38.53)
            wz = H.werkbank_werkzeug(d, args["aktion"])
            if wz is None:
                return JSONResponse({"ok": False, "fehler": "Das geht mit diesem Ding nicht."}, status_code=409)
            r = await runtime.runner.run(*wz)
            r.pop("_wake", None)
            return JSONResponse(r, status_code=200 if r.get("ok", True) else 409)
        if body.get("ziel"):                      # „Schießen auf …“: Ziel aus dem zweiten Klick (seit 0.37.9)
            args["ziel"] = str(body["ziel"])
        r = await runtime.runner.run("handeln", args)
        r.pop("_wake", None)
        return JSONResponse(r, status_code=200 if r.get("ok", True) else 409)

    @app.post("/api/szene")
    async def szene(request: Request) -> JSONResponse:
        """Simulator aufräumen (seit 0.37.14): {"aktion": "zuruecksetzen"} oder {"aktion": "zuruecklegen", "ding": …}."""
        body = await request.json()
        r = runtime.runner.szene(str(body.get("aktion") or "zuruecksetzen"), str(body.get("ding") or ""))
        await runtime.broadcast({"type": "action", "tool": "szene", "input": body, "result": r})
        return JSONResponse(r, status_code=200 if r.get("ok") else 409)
