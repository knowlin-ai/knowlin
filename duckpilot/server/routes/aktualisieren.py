"""Updates aus dem Netz (seit 0.38.32): Stand, jetzt prüfen, aktualisieren – nur am PC, nie mit dem echten Roboter."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..runtime import Runtime

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    from ...aktualisieren import UpdateFehler

    @app.get("/api/update")
    async def update_stand() -> JSONResponse:
        return JSONResponse({"ok": True, **runtime.aktualisierer.status(),
                             "suchen": bool(getattr(runtime.config, "updates_suchen", True))})

    @app.get("/api/update/fortschritt")
    async def update_fortschritt() -> JSONResponse:
        """Was das Update gerade macht: laden (mit Bytes), prüfen, installieren, paket – fürs Fenster (seit 0.38.38)."""
        return JSONResponse({"ok": True, "laeuft": runtime.aktualisierer.laeuft, **runtime.aktualisierer.fortschritt})

    @app.post("/api/update/pruefen")
    async def update_pruefen() -> JSONResponse:
        try:
            st = await asyncio.to_thread(runtime.aktualisierer.pruefen, True)
        except UpdateFehler as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=503)
        await runtime.broadcast_local(runtime.quit_message())
        return JSONResponse({"ok": True, **st})

    @app.post("/api/update/installieren")
    async def update_installieren() -> JSONResponse:
        akt = runtime.aktualisierer
        st = akt.status()
        neu = st.get("neu")
        if not neu:
            return JSONResponse({"ok": False, "fehler": "Es liegt keine neuere Version vor."}, status_code=400)
        if not st.get("kann"):
            return JSONResponse({"ok": False, "fehler": "Diese Installation aktualisierst du selbst – siehe Release-Seite.",
                                 "seite": neu.get("seite")}, status_code=400)
        if runtime.config.backend != "sim":
            return JSONResponse({"ok": False, "fehler": "Mit dem echten Roboter verbunden – bitte erst auf den Simulator "
                                 "umschalten, dann aktualisieren."}, status_code=409)
        if runtime.on_idle_exit is None or not runtime.config.app_mode:
            return JSONResponse({"ok": False, "fehler": "Aktualisieren geht nur im Programmfenster."}, status_code=400)
        if akt.laeuft:
            return JSONResponse({"ok": False, "fehler": "Das Update läuft schon."}, status_code=409)
        akt.laeuft = True
        try:
            if st["art"] == "installer":
                setup = await asyncio.to_thread(akt.installer_laden, neu["installer"])
                akt.melden("installieren")
                await asyncio.to_thread(akt.installer_starten, setup)
            else:
                await asyncio.to_thread(akt.paket_aktualisieren, neu["version"])
                runtime.restart = True
                if getattr(runtime, "spawn_restart", None):
                    await asyncio.to_thread(runtime.spawn_restart)
        except (UpdateFehler, OSError) as exc:
            akt.laeuft = False
            akt.melden("fehler", text=str(exc)[:300])
            log.warning("Update: %s", exc)
            return JSONResponse({"ok": False, "fehler": str(exc)[:300]}, status_code=400)
        log.info("Update auf %s – Knowlin beendet sich", neu["version"])
        await runtime.broadcast_local({"type": "beendet", "neustart": True, "update": neu["version"]})
        asyncio.get_running_loop().call_later(0.8, runtime.on_idle_exit)
        return JSONResponse({"ok": True, "version": neu["version"]})
