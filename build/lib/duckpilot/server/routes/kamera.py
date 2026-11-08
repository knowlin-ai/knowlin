"""Kamerabild des echten Roboters."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..runtime import (
    Runtime,
)

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    # ── Kamera des echten Roboters ───────────────────────────────────────
    @app.get("/api/kamera/bild")
    async def camera_picture(breite: int = 0):
        from fastapi.responses import Response

        addr = runtime.camera_address()
        if not addr:
            return JSONResponse({"fehler": "Kamera gibt es nur am echten Roboter"}, status_code=404)
        runtime.camera.address = addr
        runtime.camera.detect_on = runtime.skills.is_enabled("duck_detector")
        try:
            bmp, info = await runtime.camera.picture()
        except Exception as exc:
            return JSONResponse({"fehler": f"{type(exc).__name__}: {exc}"}, status_code=503)
        rgb = runtime.camera.last_rgb
        if breite and rgb is not None and int(rgb.shape[1]) > max(80, breite):
            # Handy-Controller: kleiner rechnen (jedes n-te Pixel), damit das Live-Bild durchs WLAN passt
            import asyncio

            from ...vision import to_bmp

            step = -(-int(rgb.shape[1]) // max(80, breite))
            bmp = await asyncio.to_thread(to_bmp, rgb[::step, ::step].copy())
        return Response(bmp, media_type="image/bmp", headers={"Cache-Control": "no-store",
                                                               "X-Info": json.dumps(info, ensure_ascii=True)})
