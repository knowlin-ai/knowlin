"""Mentor 2 (seit 0.41): das Vorgemachte ansehen, als Auftrag merken oder verwerfen (`mentor_auftrag.py`).

Auch vom Handy (über die sichere Adresse mit Kamera): ein Auftrag ist nur Daten – Würfel und Ziele, nichts über
Personen, keine Bilder.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import werkbank_auftrag as WA
from ..runtime import Runtime
from ..security import _json_body


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/mentor/vorgemacht")
    async def vorgemacht() -> JSONResponse:
        return JSONResponse(runtime.mentor_vorgemacht())

    @app.post("/api/mentor/vorgemacht")
    async def vorgemacht_tun(request: Request) -> JSONResponse:
        body = await _json_body(request)
        beob = getattr(runtime, "mentor_beob", None)
        if body.get("aktion") == "verwerfen":
            if beob is not None:
                beob.leeren()
            return JSONResponse(runtime.mentor_vorgemacht())
        auftrag = beob.auftrag(str(body.get("titel") or "")) if beob is not None else None
        if auftrag is None:
            return JSONResponse({"ok": False, "fehler": "Noch nichts vorgemacht – greif einen Würfel und leg ihn ab."},
                                status_code=400)
        k, grund = WA.speichern(auftrag)
        if k is None:
            return JSONResponse({"ok": False, "fehler": grund}, status_code=400)
        beob.leeren()
        await runtime.broadcast(runtime.mentor_vorgemacht())
        return JSONResponse({"ok": True, "name": k, "titel": auftrag["titel"], "schritte": len(auftrag["schritte"])})
