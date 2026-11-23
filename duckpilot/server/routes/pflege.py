"""Gelenk-Check und Pflege des echten Roboters."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from ..runtime import (
    Runtime,
    _json_default,
)
from ..security import _json_body

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    # ── Gelenk-Check und Abgleich Training ↔ Roboter ─────────────────────
    @app.get("/api/gelenke")
    async def joints_report() -> JSONResponse:
        from ...joints import ALIGNMENT

        try:
            rep = runtime.backend.joint_report()
        except Exception as exc:                     # die Abgleich-Tabelle gibt es trotzdem
            return JSONResponse({"ok": False, "fehler": f"{type(exc).__name__}: {exc}", "abgleich": ALIGNMENT})
        return JSONResponse({"ok": True, **rep, "abgleich": ALIGNMENT})

    # ── Roboter-Pflege ───────────────────────────────────────────────────
    def _robot_only():
        if runtime.config.backend != "robotd":
            return JSONResponse({"ok": False, "fehler": "Nur mit dem echten Roboter (Einstellungen → Körper)."},
                                status_code=400)
        return None

    @app.get("/api/pflege")
    async def care_overview() -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        return JSONResponse(json.loads(json.dumps(await runtime.care.overview(), default=_json_default)))

    @app.post("/api/pflege/pruefen")
    async def care_check() -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        try:
            return JSONResponse({"ok": True, "ergebnis": await runtime.care.check()})
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=502)

    @app.post("/api/pflege/einspielen")
    async def care_apply(request: Request) -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        body = await request.json()
        if runtime.care.job.get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "läuft schon"}, status_code=409)
        job = await runtime.care.apply(dry_run=body.get("probe") is not False)
        return JSONResponse({"ok": not job.get("fehler"), **job})

    @app.get("/api/pflege/protokoll")
    async def care_logs(dienst: str = "robotd", zeilen: int = 200) -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        try:
            return JSONResponse({"ok": True, **(await runtime.care.logs(dienst, zeilen) or {})})
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400 if isinstance(exc, ValueError) else 502)

    # ── Lautstärke und Fotos der Ente (seit 0.52, Pollens Protokoll 64–68) ──
    @app.post("/api/pflege/lautstaerke")
    async def care_volume(request: Request) -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        body = await _json_body(request)
        try:
            return JSONResponse({"ok": True, **(await runtime.care.set_volume(body.get("prozent")) or {})})
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "fehler": "Lautstärke in Prozent, 0 bis 100"}, status_code=400)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": _ohne_methode(exc, "die Lautstärke")}, status_code=502)

    @app.get("/api/pflege/fotos")
    async def care_photos() -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        try:
            return JSONResponse({"ok": True, "fotos": await runtime.care.photos()})
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": _ohne_methode(exc, "Fotos")}, status_code=502)

    @app.post("/api/pflege/fotos")
    async def care_take_photo() -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        try:
            res = await runtime.care.take_photo() or {}
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": _ohne_methode(exc, "ein Foto auf Zuruf")}, status_code=502)
        ok = bool(res.get("accepted", True)) if isinstance(res, dict) else True
        return JSONResponse({"ok": ok, **({"fehler": res.get("reason")} if not ok and isinstance(res, dict) else {})})

    @app.get("/api/pflege/foto/{name}")
    async def care_photo(name: str, vorschau: int = 0) -> Response:
        if (r := _robot_only()) is not None:
            return r
        try:
            data = await runtime.care.photo(name, preview=bool(vorschau))
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": _ohne_methode(exc, "Fotos")}, status_code=502)
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.delete("/api/pflege/foto/{name}")
    async def care_photo_delete(name: str) -> JSONResponse:
        if (r := _robot_only()) is not None:
            return r
        try:
            return JSONResponse({"ok": True, "geloescht": await runtime.care.delete_photo(name)})
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({"ok": False, "fehler": _ohne_methode(exc, "Fotos")}, status_code=502)


def _ohne_methode(exc: Exception, was: str) -> str:
    """Eine ältere Ente kennt den Aufruf nicht (METHOD_NOT_FOUND) – dann sagen, dass ein Update fehlt."""
    text = str(exc)
    if "-32601" in text or "not found" in text.lower() or "keine solche Methode" in text or "serves" in text:
        return f"Diese Ente kann {was} noch nicht – Update unter Roboter-Pflege. ({text[:120]})"
    return text
