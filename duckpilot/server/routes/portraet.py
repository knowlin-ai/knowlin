"""Porträts der Körper für die Startseite (seit 0.38.51).

Die Porträts aus Pollens Modellen (CC BY-NC-SA) liegen nicht im Repo. Stattdessen rendert die Startseite sie beim ersten
Mal selbst aus den geladenen 3D-Modellen (`static/portraet3d.js`) und legt sie hier im Datenordner ab
(`portraets/<id>.png`) – nur am PC, nur PNG, klein. Mitgelieferte Porträts (`static/figuren/`) gehen vor.
Wunsch des Maintainers: „Wieso laden wir nicht die Bilder der Roboter?“
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ... import suite
from ..runtime import Runtime

PNG = b"\x89PNG\r\n\x1a\n"
GROESSTE = 600_000          # Bytes; ein 256er-Porträt hat etwa 60–120 kB


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/portraet/{kid}.png")
    async def portraet_holen(kid: str):
        pfad = suite.portraet_pfad(kid)
        if pfad is None:
            return JSONResponse({"ok": False, "fehler": "noch kein Porträt"}, status_code=404)
        return FileResponse(pfad, media_type="image/png", headers={"Cache-Control": "no-cache"})

    @app.post("/api/portraet/{kid}")
    async def portraet_ablegen(kid: str, request: Request) -> JSONResponse:
        if kid not in suite.BILD_DATEI:
            return JSONResponse({"ok": False, "fehler": "unbekannter Körper"}, status_code=400)
        daten = await request.body()
        if not daten.startswith(PNG) or len(daten) > GROESSTE:
            return JSONResponse({"ok": False, "fehler": "nur PNG bis 600 kB"}, status_code=400)
        ziel = suite.eigenes_portraet(kid)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        tmp = ziel.with_suffix(".tmp")
        tmp.write_bytes(daten)
        tmp.replace(ziel)
        return JSONResponse({"ok": True})
