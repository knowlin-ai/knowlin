"""Skill-Pakete ein- und ausschalten."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import geplant
from ..runtime import (
    Runtime,
    _json_default,
)

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    # ── Skill-Pakete ─────────────────────────────────────────────────────
    @app.get("/api/skills")
    async def get_skills() -> JSONResponse:
        return JSONResponse({"pakete": runtime.skills.listing(), "koerper": runtime.koerper(), "gangart": runtime.gait,
                             "geplant": geplant.liste()})

    @app.post("/api/skills")
    async def post_skills(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            listing = await runtime.skills.set_enabled(str(body.get("id", "")), bool(body.get("an")))
        except (ValueError, TypeError, AttributeError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "pakete": listing})

    @app.get("/api/skills/{pid}/katalog")
    async def get_catalog(pid: str, neu: bool = False) -> JSONResponse:
        try:
            res = await runtime.skills.catalog(pid, refresh=neu)
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=404)
        res["koerper"] = runtime.koerper()
        res["skills"] = runtime.backend.skills()
        res["gangart"] = runtime.gait
        return JSONResponse(json.loads(json.dumps(res, default=_json_default)))

    @app.post("/api/skills/{pid}/ausfuehren")
    async def run_pack(pid: str, request: Request) -> JSONResponse:
        try:
            body = await request.json()
            res = await runtime.skills.run(pid, str(body.get("eintrag", ""))[:200], str(body.get("aktion", ""))[:20])
        except (ValueError, TypeError, AttributeError) as exc:
            return JSONResponse({"ok": False, "grund": str(exc)}, status_code=400)
        return JSONResponse(res)

    @app.get("/api/arm")
    async def arm_tricks() -> JSONResponse:
        """Aris Tricks (seit 0.38.55): seine Gesten und Aufträge an der Werkbank – statt der Gefühle mit Kopf."""
        from ... import arm as A
        from ...werkbank_auftrag import AUFTRAEGE, alle

        return JSONResponse({
            "gesten": [{"name": g, "titel": t, "dauer": round(A.dauer(g), 1)} for g, t in A.TITEL.items() if g in A.GESTEN],
            "auftraege": [{"name": k, "titel": v["titel"], "beschreibung": v.get("beschreibung", ""), "eigen": k not in AUFTRAEGE}
                          for k, v in alle().items()],
        })

    @app.get("/api/emotions")
    async def get_emotions() -> JSONResponse:
        return JSONResponse(runtime.emotions_catalog())
