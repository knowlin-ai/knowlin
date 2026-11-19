"""Ari lernt durch Vormachen (seit 0.38.64): Aufgabe, Aufnehmen, Lernen, Ausprobieren, Export für LeRobot.
Nur am PC (`remote.PC_ONLY`), nur im Simulator – der Ablauf steckt in `arm_schule.py`."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from ...arm_schule import ArmSchule
from ..runtime import Runtime
from ..security import _json_body


def register(app: FastAPI, runtime: Runtime) -> None:
    runtime.ari_schule = ArmSchule(runtime)      # type: ignore[attr-defined]
    svc: ArmSchule = runtime.ari_schule          # type: ignore[attr-defined]

    @app.get("/api/ari_lernen")
    async def ari_lernen_status() -> JSONResponse:
        return JSONResponse({"ok": True, **svc.status()})

    @app.post("/api/ari_lernen")
    async def ari_lernen_tun(request: Request) -> JSONResponse:
        body = await _json_body(request)
        aktion = str(body.get("aktion") or "")
        if aktion == "aufgabe":
            res = svc.aufgabe_setzen(str(body.get("wuerfel") or ""), str(body.get("kiste") or ""))
        elif aktion == "neu_legen":
            res = svc.neu_legen()
        elif aktion == "aufnehmen":
            res = svc.aufnehmen()
        elif aktion == "abbrechen":
            res = svc.abbrechen()
        elif aktion == "lernen":
            res = svc.lernen(bool(body.get("lehrer", True)))
        elif aktion == "ausprobieren":
            res = svc.ausprobieren()
        elif aktion == "ueben":                    # Stufe B (seit 0.41)
            res = svc.ueben()
        else:
            res = {"ok": False, "fehler": "Unbekannte Aktion"}
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)

    @app.get("/api/ari_lernen/export")
    async def ari_lernen_export() -> Response:
        paket = svc.export()
        if paket is None:
            return JSONResponse({"ok": False, "fehler": "Noch keine Beispiele für diese Aufgabe"}, status_code=404)
        daten, name = paket
        return Response(daten, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
