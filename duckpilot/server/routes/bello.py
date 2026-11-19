"""Bello lernt laufen (seit 0.43): Lernen starten, Stand abfragen, abbrechen, vergessen (`bello_schule.py`).

Lesen geht überall, Starten, Abbrechen und Vergessen nur am PC (`remote.PC_ONLY`) – es rechnet auf diesem PC.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import settings as S
from ...bello_schule import BelloSchule
from ..runtime import Runtime
from ..security import _json_body


def register(app: FastAPI, runtime: Runtime) -> None:
    schule = BelloSchule(S.data_dir())
    runtime.bello_schule = schule                  # type: ignore[attr-defined]

    def anwenden(gang) -> None:
        """Ergebnis gleich dem Körper geben – nur, wenn gerade Bello da ist (der kennt `gelernt_setzen`)."""
        setzen = getattr(runtime.backend, "gelernt_setzen", None)
        if callable(setzen):
            setzen(gang)

    @app.get("/api/bello")
    async def bello_stand() -> JSONResponse:
        return JSONResponse(schule.stand())

    @app.post("/api/bello/lernen")
    async def bello_lernen(request: Request) -> JSONResponse:
        body = await _json_body(request)
        aktion = body.get("aktion", "start")
        if aktion == "start":
            runden = max(5, min(80, int(body.get("runden") or 30)))
            r = schule.starten(runden, bei_fertig=anwenden)
            return JSONResponse(r, status_code=200 if r["ok"] else 400)
        if aktion == "stopp":
            return JSONResponse({"ok": True, "lief": schule.abbrechen()})
        if aktion == "vergessen":
            ok = schule.vergessen()
            anwenden(None)
            return JSONResponse({"ok": ok})
        return JSONResponse({"ok": False, "fehler": "unbekannte Aktion"}, status_code=400)
