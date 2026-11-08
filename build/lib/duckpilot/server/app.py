"""Server für die Oberfläche: 3D, Dashboard, Chat, Sprache, Einstellungen – lokal, auf Wunsch auch vom Handy.

Aufbau: `runtime.Runtime` hält den Zustand, `security` prüft Herkunft und Handys, `routes/*` registrieren je Bereich
ihre Endpunkte. Dieses Modul setzt alles zusammen und bleibt der Einstieg (Runtime, create_app … von hier importierbar).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from . import routes as _routes
from .runtime import STATIC, Runtime, _plans_from
from .security import SameOriginMiddleware, _host_ok, origin_allowed

# Einstieg für Aufrufer und Tests: diese Namen bleiben hier importierbar
__all__ = ["STATIC", "Runtime", "SameOriginMiddleware", "_host_ok", "_plans_from", "create_app", "origin_allowed"]

log = logging.getLogger(__name__)


ICON_REFS = ("/static/icon-192.png", "/static/apple-touch-icon.png", "/manifest.webmanifest")


def icon_stamp() -> str:
    """Kurze Prüfsumme der Icons – ändert sich nur, wenn sich ein Icon ändert."""
    h = hashlib.sha1()
    for name in ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"):
        p = STATIC / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:8]


def create_app(runtime: Runtime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await runtime.start()
        yield
        await runtime.stop()

    app = FastAPI(title="duckpilot", lifespan=lifespan)
    app.add_middleware(SameOriginMiddleware, remote=runtime.remote)
    # Komprimiert Oberfläche, Skripte und Modell (≈ 4 MB weniger fürs Handy übers WLAN); Bilder und Töne sind es schon
    app.add_middleware(GZipMiddleware, minimum_size=1400, compresslevel=6, exclude_content_types=(
        "text/event-stream", "image/png", "image/jpeg", "image/webp", "image/gif", "audio/ogg", "audio/mpeg", "audio/wav",
        "font/woff2"))
    runtime.app = app
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    stamp = icon_stamp()

    @app.get("/")
    async def index() -> HTMLResponse:
        # Icons mit Prüfsumme in der Adresse: Browser und Edge-App-Fenster merken sich Symbole nach der Adresse –
        # ein neues Icon braucht eine neue Adresse, sonst bleibt das alte stehen
        page = (STATIC / "index.html").read_text(encoding="utf-8")
        for ref in ICON_REFS:
            page = page.replace(f'"{ref}"', f'"{ref}?v={stamp}"')
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    @app.get("/manifest.webmanifest")
    async def manifest() -> JSONResponse:
        """Die installierte App heißt wie die Ente."""
        base = json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
        name = runtime.config.duck_name or "Knowlin"
        base.update(name=name, short_name=name[:12], description=f"{name} – gesteuert mit Knowlin")
        for icon in base.get("icons", []):
            icon["src"] = f"{icon['src']}?v={stamp}"
        return JSONResponse(base, media_type="application/manifest+json", headers={"Cache-Control": "no-store"})

    for name in _routes.MODULES:
        importlib.import_module(f"{__package__}.routes.{name}").register(app, runtime)
    return app
