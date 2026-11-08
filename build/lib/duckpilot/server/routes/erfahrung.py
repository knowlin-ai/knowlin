"""Erfahrungsnetz: ansehen, „Warum?“, einzelne Knoten oder Verbindungen vergessen, zurücksetzen (nur am PC)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..runtime import Runtime
from ..security import _is_remote, _json_body


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/erfahrung")
    async def erfahrung_get(request: Request) -> JSONResponse:
        return JSONResponse(runtime.erfahrung.message(remote=_is_remote(request)))

    @app.get("/api/erfahrung/themen")
    async def erfahrung_themen(request: Request) -> JSONResponse:
        """G1 (0.38.27): „Was Knowlin über deine Welt weiß“ – Personen nur am PC."""
        if not runtime.erfahrung.on:
            return JSONResponse({"ok": True, "an": False, "gruppen": []})
        return JSONResponse({"ok": True, "an": True, **runtime.erfahrung.netz.themen(ohne_personen=_is_remote(request))})

    @app.get("/api/erfahrung/knoten/{kid}")
    async def erfahrung_knoten(kid: str, request: Request) -> JSONResponse:
        netz = runtime.erfahrung.netz
        if kid not in netz.knoten or (kid.startswith("person:") and _is_remote(request)):
            return JSONResponse({"ok": False, "fehler": "unbekannt"}, status_code=404)
        nachbarn = sorted(((p, e) for p, e in netz.kanten.items() if kid in p.split("|")), key=lambda x: -x[1]["w"])[:12]
        out = []
        for p, e in nachbarn:
            other = next(x for x in p.split("|") if x != kid)
            if other.startswith("person:") and _is_remote(request):
                continue
            kn = netz.knoten.get(other, {})
            out.append({"id": other, "name": kn.get("name", other), "art": kn.get("art"), "w": e["w"], "n": e["n"], "warum": e["warum"]})
        return JSONResponse({"ok": True, "knoten": {"id": kid, **netz.knoten[kid]}, "verbindungen": out})

    @app.post("/api/erfahrung/vergessen")
    async def erfahrung_forget(request: Request) -> JSONResponse:
        if _is_remote(request):
            return JSONResponse({"ok": False, "fehler": "Vergessen geht nur am PC."}, status_code=403)
        body = await _json_body(request)
        netz = runtime.erfahrung.netz
        if body.get("alles"):
            runtime.sicherung.vorher("Vor „Netz leeren“", ["erfahrung"])        # rückgängig machbar (0.38.24)
            netz.reset()
            ok = True
        elif body.get("b"):
            ok = netz.verbindung_vergessen(str(body.get("a")), str(body.get("b")))
        else:
            ok = netz.vergessen(str(body.get("id")))
        netz.save()
        await runtime.broadcast_local(runtime.erfahrung.message())
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)
