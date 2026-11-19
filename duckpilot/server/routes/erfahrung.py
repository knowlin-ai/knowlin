"""Erfahrungsnetz: ansehen, „Warum?“, einzelne Knoten oder Verbindungen vergessen, zurücksetzen (nur am PC)."""

from __future__ import annotations

import re

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

    @app.get("/api/erfahrung/rueckblick")
    async def erfahrung_rueckblick(request: Request, tag: str = "") -> JSONResponse:
        """Tagesrückblick (seit 0.39): Text, worum es ging, Neues, Momente – Personen nie fürs Handy."""
        if not runtime.erfahrung.on:
            return JSONResponse({"ok": True, "an": False})
        if tag and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", tag):
            return JSONResponse({"ok": False, "fehler": "Tag als JJJJ-MM-TT"}, status_code=400)
        return JSONResponse({"ok": True, "an": True, **runtime.erfahrung.rueckblick(tag or None, remote=_is_remote(request))})

    @app.post("/api/erfahrung/rueckblick/loeschen")
    async def erfahrung_rueckblick_loeschen(request: Request) -> JSONResponse:
        """Einen Moment (tag + t) oder einen ganzen Tag aus dem Tagebuch löschen – nur am PC."""
        if _is_remote(request):
            return JSONResponse({"ok": False, "fehler": "Löschen geht nur am PC."}, status_code=403)
        body = await _json_body(request)
        tb = runtime.erfahrung.tagebuch
        tag = str(body.get("tag") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", tag):
            return JSONResponse({"ok": False, "fehler": "Tag als JJJJ-MM-TT"}, status_code=400)
        try:
            float(body.get("t") or 0)
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "fehler": "t: Zeitstempel"}, status_code=400)
        ok = tb.loeschen(tag, float(body["t"])) if body.get("t") is not None else tb.tag_loeschen(tag)
        tb.speichern()
        return JSONResponse({"ok": ok, **runtime.erfahrung.rueckblick(tag or None)}, status_code=200 if ok else 404)

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
