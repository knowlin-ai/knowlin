"""Sicherungspunkte (seit 0.38.24): Liste, anlegen, zurücksetzen, wiederherstellen, löschen, Export und Import.

Alles nur am PC – ein Sicherungspunkt enthält das ganze Gedächtnis. Zurücksetzen, Wiederherstellen und Löschen
brauchen `bestaetigt: true` (die Oberfläche fragt mit einem zweiten Klick nach)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from ...sicherungspunkte import MAX_ZIP, SicherungFehler
from ..runtime import Runtime
from ..security import _is_remote, _json_body

NUR_PC = {"ok": False, "fehler": "Sicherungspunkte gibt es nur direkt am PC.", "nur_pc": True}


def register(app: FastAPI, runtime: Runtime) -> None:
    def sv():
        return runtime.sicherung

    def fehler(exc: Exception, code: int = 400) -> JSONResponse:
        return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=code)

    @app.get("/api/sicherung")
    async def uebersicht(request: Request) -> JSONResponse:
        if _is_remote(request):
            return JSONResponse(NUR_PC, status_code=403)
        return JSONResponse({"ok": True, **sv().uebersicht()})

    @app.post("/api/sicherung")
    async def aktion(request: Request) -> JSONResponse:
        if _is_remote(request):
            return JSONResponse(NUR_PC, status_code=403)
        body = await _json_body(request)
        was = body.get("aktion")
        bereiche = body.get("bereiche") if isinstance(body.get("bereiche"), list) else None
        try:
            if was == "anlegen":
                punkt = sv().anlegen(str(body.get("name") or ""))
                return JSONResponse({"ok": True, "punkt": punkt, **sv().uebersicht()})
            if was not in ("zuruecksetzen", "wiederherstellen", "loeschen"):
                return fehler(ValueError("unbekannte Aktion"))
            if body.get("bestaetigt") is not True:
                return fehler(ValueError("Bitte bestätigen (zweiter Klick)."), 409)
            if was == "zuruecksetzen":
                res = await sv().zuruecksetzen(bereiche or [])
            elif was == "wiederherstellen":
                res = await sv().wiederherstellen(str(body.get("id") or ""), bereiche)
            else:
                sv().punkte.loeschen(str(body.get("id") or ""))
                res = {}
        except SicherungFehler as exc:
            return fehler(exc, 404 if "gibt es nicht" in str(exc) else 400)
        except ValueError as exc:
            return fehler(exc)
        return JSONResponse({"ok": True, **res, **sv().uebersicht()})

    @app.get("/api/sicherung/{pid}/export")
    async def export(pid: str, request: Request) -> Response:
        if _is_remote(request):
            return JSONResponse(NUR_PC, status_code=403)
        try:
            daten = sv().punkte.export(pid)
        except SicherungFehler as exc:
            return fehler(exc, 404)
        return Response(daten, media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="knowlin-sicherung-{pid}.zip"', "Cache-Control": "no-store"})

    @app.post("/api/sicherung/import")
    async def importieren(request: Request) -> JSONResponse:
        if _is_remote(request):
            return JSONResponse(NUR_PC, status_code=403)
        daten = b""
        async for teil in request.stream():
            daten += teil
            if len(daten) > MAX_ZIP:
                return fehler(SicherungFehler("Die Datei ist zu groß."), 413)
        try:
            punkt = sv().punkte.importieren(daten)
        except SicherungFehler as exc:
            return fehler(exc)
        return JSONResponse({"ok": True, "punkt": punkt, **sv().uebersicht()})
