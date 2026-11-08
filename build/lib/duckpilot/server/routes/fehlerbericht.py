"""„Das lief schief“: Fehlerbericht mit Aufzeichnung der letzten 30 s (seit 0.36.2)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ... import __version__
from ... import settings as S
from .. import fehlerbericht as F
from ..runtime import Runtime


def register(app: FastAPI, runtime: Runtime) -> None:
    def ordner():
        return S.settings_path().parent / "fehlerberichte"   # im Datenordner, nie in OneDrive

    @app.post("/api/fehlerbericht")
    async def bericht_erstellen(request: Request) -> JSONResponse:
        body = await request.json()
        werte = S.load_user_settings() | {k: v for k, v in vars(runtime.config).items() if not k.startswith("_")}
        b = runtime.blackbox.bericht(version=__version__, einstellungen=werte, ente=runtime.config.duck_name or "",
                                     beschreibung=str(body.get("beschreibung", "")),
                                     log=F.log_zeilen(S.data_dir() / "duckpilot.log"))
        pfad = F.speichern(ordner(), b)
        return JSONResponse({"ok": True, "datei": pfad.name, "bericht": b, "issue": F.issue_link(b, pfad.name)})

    @app.get("/api/fehlerbericht/{datei}")
    async def bericht_laden(datei: str):
        p = ordner() / datei
        if "/" in datei or "\\" in datei or not datei.startswith("bericht-") or not p.is_file():
            return JSONResponse({"ok": False}, status_code=404)
        return FileResponse(p, filename=datei, media_type="application/json")
