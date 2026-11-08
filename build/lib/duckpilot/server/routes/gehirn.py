"""Eigenes Sprachmodell (Ollama)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import settings as S
from ...aio import spawn
from ..runtime import (
    Runtime,
)

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    # ── Eigenes Sprachmodell (Ollama) ────────────────────────────────────
    @app.get("/api/gehirn")
    async def brain_status() -> JSONResponse:
        from ...brain.local import SUGGESTED

        st = await runtime.agent.local.status()
        return JSONResponse({**st, "vorschlaege": SUGGESTED, "gewaehlt": runtime.config.lokal_modell,
                             "gehirn": runtime.config.gehirn, "fehler_zuletzt": runtime.agent.local.last_error,
                             "laden": runtime.pulls})

    @app.post("/api/gehirn/laden")
    async def brain_pull(request: Request) -> JSONResponse:
        body = await request.json()
        model = str(body.get("modell", "")).strip()
        try:
            S.validate({"lokal_modell": model})
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        if not model or runtime.pulls.get(model, {}).get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "läuft schon oder kein Modell"}, status_code=409)
        spawn(runtime.pull_model(model))
        return JSONResponse({"ok": True})

    # ── Andere KI-Modelle (seit 0.35, nur am PC) ─────────────────────────
    @app.get("/api/anbieter")
    async def anbieter_status() -> JSONResponse:
        from ...brain.anbieter import ANBIETER

        cfg = runtime.config
        return JSONResponse({
            "anbieter": [{"id": k, "name": n, "adresse": a, "schluessel": b,
                          "hat_schluessel": bool(S.get_anbieter_key(k)) if b else None} for k, (n, a, b) in ANBIETER.items()],
            "gewaehlt": cfg.anbieter, "modell": cfg.anbieter_modell, "adresse": cfg.anbieter_adresse,
            "aktiv": cfg.gehirn == "anbieter", "bereit": runtime.agent.anbieter.configured,
            "fehler_zuletzt": runtime.agent.anbieter.last_error, "tresor": S.vault_available()})

    @app.post("/api/anbieter/schluessel")
    async def anbieter_key(request: Request) -> JSONResponse:
        body = await request.json()
        anbieter = str(body.get("anbieter", ""))
        from ...brain.anbieter import ANBIETER

        if anbieter not in ANBIETER or not ANBIETER[anbieter][2]:
            return JSONResponse({"ok": False, "fehler": "Dieser Anbieter braucht keinen Schlüssel"}, status_code=400)
        try:
            S.set_anbieter_key(anbieter, str(body.get("schluessel", "")))
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        runtime._new_agent()
        return JSONResponse({"ok": True})

    @app.delete("/api/anbieter/schluessel")
    async def anbieter_key_weg(request: Request) -> JSONResponse:
        body = await request.json()
        S.delete_anbieter_key(str(body.get("anbieter", "")))
        runtime._new_agent()
        return JSONResponse({"ok": True})

    @app.post("/api/anbieter/modelle")
    async def anbieter_modelle(request: Request) -> JSONResponse:
        """Modelle des gewählten Anbieters abfragen – zugleich ein Verbindungstest."""
        from ...brain.anbieter import ANBIETER, AnbieterBrain

        body = await request.json()
        anbieter = str(body.get("anbieter", runtime.config.anbieter))
        if anbieter not in ANBIETER:
            return JSONResponse({"ok": False, "fehler": "Unbekannter Anbieter"}, status_code=400)
        try:
            adresse = S.validate({"anbieter_adresse": body.get("adresse", runtime.config.anbieter_adresse)})["anbieter_adresse"]
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        brain = AnbieterBrain(runtime.agent, anbieter, "-", adresse, S.get_anbieter_key(anbieter))
        if not brain.url:
            return JSONResponse({"ok": False, "fehler": "Erst eine Adresse eintragen"}, status_code=400)
        try:
            return JSONResponse({"ok": True, "modelle": await brain.modelle()})
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": f"{type(exc).__name__}: {exc}"[:200]}, status_code=502)

