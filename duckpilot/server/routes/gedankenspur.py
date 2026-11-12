"""Gedankenspur und Antrieb (seit 0.38.44, Etappe G3): ansehen überall, leeren nur am PC; Zeilen über Personen nur am PC.
Rückblick (seit 0.38.45, Etappe G4): Lehren ansehen überall; korrigieren, löschen und „jetzt zurückblicken“ nur am PC."""

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

    def _nur_pc(request: Request) -> JSONResponse | None:
        if _is_remote(request):
            return JSONResponse({"ok": False, "fehler": "Lehren lassen sich nur am PC ändern."}, status_code=403)
        return None

    def _mit_namen(lehren: list[dict]) -> list[dict]:
        from ...figuren import figur

        return [{**x, "koerper_name": figur(x["koerper"]).get("name") or x["koerper"]} for x in lehren]

    @app.get("/api/rueckblick")
    async def rueckblick() -> JSONResponse:
        return JSONResponse({"lehren": _mit_namen(runtime.lehrbuch.liste()), "zuletzt": runtime.lehrbuch.zuletzt or None})

    @app.post("/api/rueckblick/jetzt")
    async def rueckblick_jetzt(request: Request) -> JSONResponse:
        if (nein := _nur_pc(request)) is not None:
            return nein
        neu = runtime.zurueckblicken()
        return JSONResponse({"ok": True, "neu": len(neu), "lehren": _mit_namen(runtime.lehrbuch.liste())})

    @app.post("/api/rueckblick/{lid}")
    async def rueckblick_korrigieren(lid: str, request: Request) -> JSONResponse:
        if (nein := _nur_pc(request)) is not None:
            return nein
        try:
            body = await request.json()
            x = runtime.lehrbuch.korrigieren(lid, str((body if isinstance(body, dict) else {}).get("richtung") or ""))
        except ValueError as e:
            return JSONResponse({"ok": False, "fehler": str(e)}, status_code=400)
        if x is None:
            return JSONResponse({"ok": False, "fehler": "Diese Lehre gibt es nicht mehr."}, status_code=404)
        return JSONResponse({"ok": True, "lehre": x})

    @app.delete("/api/rueckblick/{lid}")
    async def rueckblick_loeschen(lid: str, request: Request) -> JSONResponse:
        if (nein := _nur_pc(request)) is not None:
            return nein
        ok = runtime.lehrbuch.loeschen(lid)
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)
