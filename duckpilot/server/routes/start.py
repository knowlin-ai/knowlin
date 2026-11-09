"""Knowlin-Startseite (seit 0.38): Gemeinsames, Verkörperungen je Körper (seit 0.38.3), Verknüpfungen."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import koerper, suite
from ..runtime import Runtime


def _gemeinsam(runtime: Runtime) -> dict:
    """Was alle Verkörperungen teilen (seit 0.38.3): Wissen über die Umwelt, Umgebung, Alltag, Erlebnisse – als Zahlen."""
    mem = getattr(runtime, "memory", None)
    d = mem.data if mem is not None else {}
    try:
        personen = len(runtime.faces.persons()) if getattr(runtime, "faces", None) else 0
    except Exception:  # noqa: BLE001 – die Startseite darf daran nie scheitern
        personen = 0
    return {"wissen": len(d.get("wissen") or ()) + len(d.get("vorlieben") or ()), "orte": len(d.get("orte") or {}),
            "erlebnisse": len(d.get("protokoll") or ()), "personen": personen, "gedaechtnis": mem is not None}


def _figur(runtime: Runtime, modul: str, f: dict) -> dict:
    out = dict(f)
    if f.get("aktiv"):
        try:
            out["stimmung"] = runtime.engine.mood.snapshot().get("name")
        except Exception:  # noqa: BLE001
            out["stimmung"] = None
        mem = getattr(runtime, "memory", None)
        out["tricks"] = len(mem.data.get("tricks") or {}) if mem is not None else 0
    return out


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.post("/api/koerper/wechseln")
    async def koerper_wechseln(request: Request) -> JSONResponse:
        """Zu einer anderen Verkörperung im Simulator wechseln – auch vom Handy (seit 0.38.34, Frage: „Open Duck geht, die
        anderen nicht?“). Mit dem echten Roboter verbunden bleibt der Wechsel beim PC: er trennt die Verbindung."""
        body = await request.json()
        modul = str(body.get("modul", ""))
        profil = next((k for k in koerper.alle() if k.id == modul), None)   # Körperschnittstelle (seit 0.38.35)
        if profil is None:
            return JSONResponse({"ok": False, "fehler": "Diese Verkörperung gibt es nicht."}, status_code=400)
        if not profil.simulator:
            return JSONResponse({"ok": False, "fehler": f"{profil.name} hat keinen Simulator – einrichten am PC."},
                                status_code=409)
        if runtime.config.backend != "sim":
            return JSONResponse({"ok": False, "fehler": "Mit dem echten Roboter verbunden – den Körper wechselst du am PC."},
                                status_code=409)
        patch = {"modul": modul} if modul == "duckpilot" else {"modul": modul, "backend": "sim", "sim_physik": False}
        try:
            await runtime.apply_settings(patch)
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "modul": modul})

    @app.get("/api/module")
    async def module() -> JSONResponse:
        koerper = "physik" if type(runtime.backend).__name__ == "PhysicsBackend" else runtime.backend.state().backend
        from ...figuren import FIGUR_KEYS

        cfg = runtime.config
        jetzt = {k: getattr(cfg, k) for k in FIGUR_KEYS if hasattr(cfg, k)}
        figuren = {m: _figur(runtime, m, f) for m, f in runtime.figuren.alle(cfg.modul, jetzt).items()}
        module = suite.module(koerper, cfg.modul)
        for m in module:
            if m.get("modul") in figuren:
                m["figur"] = figuren[m["modul"]]
        return JSONResponse({"ok": True, "module": module, "kern": suite.kern(), "gemeinsam": _gemeinsam(runtime)})

    @app.post("/api/verknuepfung")
    async def verknuepfung(request: Request) -> JSONResponse:
        """Verknüpfung „Knowlin“ (Startseite) oder „Knowlin - Microduck“ & Co. (direkt in die Verkörperung) anlegen – nur auf Wunsch."""
        from ...desktop import verknuepfung_anlegen

        body = await request.json()
        modul = str(body.get("modul") or "")
        try:
            pfade = await asyncio.to_thread(verknuepfung_anlegen, modul)
        except (RuntimeError, ValueError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "angelegt": pfade})
