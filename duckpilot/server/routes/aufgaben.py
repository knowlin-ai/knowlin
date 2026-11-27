"""Selbstständige Aufgaben (seit 0.55): Linie folgen, Farbe folgen – dazu die Klebeband-Linie im Simulator.

- `GET /api/aufgaben` – liegt eine Linie (Punkte für die 3D-Ansicht), kann der Körper die Aufgaben, Farben
- `POST /api/aufgaben/linie` `{an}` – im Simulator die Linie auf den Boden kleben oder wegnehmen; Meldung
  `{"type": "linie", "linie": …}` an alle Fenster

Gestartet werden die Aufgaben wie alles andere über Werkzeuge (`linie_folgen`, `farbe_folgen`, `explore`,
`mir_folgen`, `apportieren`) – so gelten dieselben Regeln: Not-Aus, Sperre danach, nur was der Körper kann.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...brain.tools import fehlt_dem_koerper
from ...farbsicht import FARBNAME, FARBZIELE
from ..runtime import Runtime
from ..security import _json_body


def _welt(rt: Runtime) -> Any:
    return getattr(rt.backend, "world_model", None)


def stand(rt: Runtime) -> dict[str, Any]:
    welt = _welt(rt)
    linie = getattr(welt, "linie", None) if welt is not None else None
    return {"ok": True, "simulator": welt is not None, "linie": [list(p) for p in linie] if linie else None,
            "grund": fehlt_dem_koerper("linie_folgen", rt.backend),
            "farben": [{"id": k, "name": FARBNAME[k], "hex": v[1]} for k, v in FARBZIELE.items()]}


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/aufgaben")
    async def aufgaben() -> JSONResponse:
        return JSONResponse(stand(runtime))

    @app.post("/api/aufgaben/linie")
    async def aufgaben_linie(request: Request) -> JSONResponse:
        body = await _json_body(request)
        welt = _welt(runtime)
        if welt is None:
            return JSONResponse({"ok": False, "fehler": "Die Linie gibt es nur im Simulator – am Roboter klebst du "
                                                         "selbst ein dunkles Band auf den Boden."}, status_code=409)
        welt.set_linie(bool(body.get("an")))
        s = stand(runtime)
        await runtime.broadcast({"type": "linie", "linie": s["linie"]})
        return JSONResponse(s)
