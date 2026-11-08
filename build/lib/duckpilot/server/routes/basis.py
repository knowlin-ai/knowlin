"""Grundlagen: Status, Einstellungen, API-Schlüssel, Ordner, Tricks vom Hub."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import __version__, i18n
from ... import remote as R
from ... import settings as S
from ..runtime import (
    Runtime,
    _json_default,
)
from ..security import _is_remote, _open_folder

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/i18n/{sprache}")
    async def sprachkatalog(sprache: str) -> JSONResponse:
        """Texte der Oberfläche in einer Sprache (Lücken auf Deutsch), seit 0.33."""
        if sprache == "aktuell":                       # die eingestellte Sprache (seit 0.34)
            sprache = runtime.config.sprache
        s = sprache if sprache in i18n.SPRACHEN else i18n.STANDARD
        return JSONResponse({"sprache": s, "sprachen": list(i18n.SPRACHEN), "texte": i18n.katalog(s),
                             "ui": i18n.ui_katalog(s)})

    @app.get("/api/ping")
    async def ping() -> JSONResponse:
        return JSONResponse({"app": "duckpilot", "version": __version__})

    @app.get("/api/status")
    async def status() -> JSONResponse:
        return JSONResponse(json.loads(json.dumps(runtime.runner.status(), default=_json_default)))

    @app.get("/api/settings")
    async def get_settings() -> JSONResponse:
        return JSONResponse(json.loads(json.dumps(runtime.settings_message(), default=_json_default)))

    @app.post("/api/settings")
    async def post_settings(request: Request) -> JSONResponse:
        try:
            patch = await request.json()
            if not isinstance(patch, dict):
                raise ValueError("Erwartet ein Objekt")
            if _is_remote(request) and set(patch) & R.PC_ONLY_SETTINGS:
                why = "Das geht nur direkt am PC."
                return JSONResponse({"ok": False, "fehler": why, "nur_pc": True}, status_code=403)
            result = await runtime.apply_settings(patch)
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({**result, "einstellungen": json.loads(json.dumps(runtime.settings_message(), default=_json_default))})

    @app.post("/api/key")
    async def post_key(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            return JSONResponse({"ok": True, "schluessel": await runtime.set_key(str(body.get("key", "")))})
        except (ValueError, RuntimeError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)

    @app.delete("/api/key")
    async def delete_key() -> JSONResponse:
        return JSONResponse({"ok": True, "schluessel": await runtime.delete_key()})

    @app.post("/api/key/test")
    async def test_key() -> JSONResponse:
        return JSONResponse(await runtime.test_key())

    @app.post("/api/open-folder")
    async def open_folder(request: Request) -> JSONResponse:
        body = await request.json()
        which = body.get("which")
        paths = {"daten": S.data_dir(), "gedaechtnis": runtime.memory.path.parent if runtime.memory else S.data_dir()}
        if which not in paths:
            return JSONResponse({"ok": False}, status_code=400)
        try:
            _open_folder(paths[which])
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=500)
        return JSONResponse({"ok": True})

    @app.get("/api/tricks")
    async def get_tricks(q: str = "microduck") -> JSONResponse:
        res = await runtime.search_tricks(q[:60])
        res["vorgemerkt"] = list(runtime.config.tricks)
        res["skills"] = runtime.backend.skills()
        res["koerper"] = runtime.koerper()
        return JSONResponse(json.loads(json.dumps(res, default=_json_default)))

    @app.post("/api/tricks")
    async def post_trick(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            secs = body.get("sekunden")
            res = await runtime.add_trick(str(body.get("repo", "")), name=body.get("name") or None,
                                          seconds=float(secs) if secs else None, file=body.get("datei") or None)
        except (ValueError, TypeError) as exc:
            return JSONResponse({"ok": False, "grund": str(exc)}, status_code=400)
        return JSONResponse(res)

    @app.delete("/api/tricks")
    async def delete_trick(repo: str) -> JSONResponse:
        return JSONResponse(await runtime.forget_trick(repo))
