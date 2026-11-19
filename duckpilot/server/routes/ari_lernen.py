"""Ari lernt durch Vormachen (seit 0.38.64): Aufgabe, Aufnehmen, Lernen, Ausprobieren, Export für LeRobot – und seit
0.42 die Beispiele auf den Hugging Face Hub (Zwei-Klick, privat als Standard). Nur am PC (`remote.PC_ONLY`), nur im Simulator – der Ablauf steckt in `arm_schule.py`."""

from __future__ import annotations

from asyncio import to_thread

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from ... import ari_hub
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

    @app.post("/api/ari_lernen/hub")
    async def ari_lernen_hub(request: Request) -> JSONResponse:
        from ... import training

        body = await _json_body(request)
        if body.get("bestaetigt") is not True:                    # zweiter Klick in der Oberfläche
            return JSONResponse({"ok": False, "fehler": "Bitte das Hochladen bestätigen."}, status_code=400)
        paket = svc.export()
        if paket is None:
            return JSONResponse({"ok": False, "fehler": "Noch keine Beispiele für diese Aufgabe"}, status_code=404)
        token = await to_thread(training.get_token)
        if not token:
            return JSONResponse({"ok": False, "fehler": "Erst den Hugging-Face-Schlüssel hinterlegen (Lernen → Training)."},
                                status_code=400)
        daten, datei = paket
        try:
            out = await to_thread(lambda: ari_hub.teile(daten, token, name=datei.removesuffix("-lerobot.zip"),
                                                        oeffentlich=bool(body.get("oeffentlich"))))
        except ari_hub.HubFehler as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        except Exception as exc:  # noqa: BLE001 – Netz, Hub: ehrlich sagen
            return JSONResponse({"ok": False, "fehler": f"Hochladen ging nicht ({type(exc).__name__})"}, status_code=502)
        return JSONResponse({"ok": True, **out})
