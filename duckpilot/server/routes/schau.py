"""„Schau mich an“ (seit 0.39): Gesichtserkennung laden, Schauen starten, Blickziele, stoppen – nur am PC.

Für jeden Körper mit Kopf und Kamera (`eigenschaften()`), gedacht für Stack-chan „wie ab Werk“. Die Webcam wertet nur
der Browser aus (`static/schau.js`); hierher kommen nur Zahlen: die Mitte des Gesichts im Bild (0 … 1) und ob gerade
eins zu sehen ist. Bewegt wird über die Engine (`motion/schau.SchauHaltung`) mit allen Sicherheitsregeln: nicht während
der Sperre nach einem Not-Aus, nicht stromlos oder schlafend; der Not-Aus beendet das Schauen sofort.
Geladen wird die Gesichtserkennung nur nach dem Klick (`POST /api/schau/laden`), mit fester Version und Prüfsummen
(`modell/gesicht.py`). Alles unter `/api/schau…` steht in `remote.PC_ONLY`.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ...aio import spawn
from ...modell import gesicht as G
from ...motion.schau import SchauHaltung
from ..runtime import Runtime
from ..security import _json_body

log = logging.getLogger(__name__)
YAW_SPANNE = 55.0          # Grad: Bildrand links/rechts
PITCH_SPANNE = 18.0        # Grad: Bildrand oben/unten
FREUDE_NACH_S = 3.0        # so lange weg, dann freut er sich beim Wiedersehen
FREUDE_ABSTAND_S = 10.0


def blick_aus_bild(x: float, y: float) -> tuple[float, float]:
    """Mitte des Gesichts im (ungespiegelten) Webcam-Bild → Blick in Grad. Körper und Webcam schauen beide zum
    Menschen: links im Bild ist links vom Körper (+), oben im Bild heißt hochschauen (Nicken −)."""
    return (0.5 - x) * 2 * YAW_SPANNE, (y - 0.5) * 2 * PITCH_SPANNE


class Schauen:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.haltung: SchauHaltung | None = None
        self._zuletzt_gesehen = 0.0
        self._gefreut = 0.0

    def grund(self) -> str | None:
        be = self.rt.backend
        eig = be.eigenschaften()
        if not {"kopf", "kamera"} <= eig:
            return "Dieser Körper hat keinen Kopf mit Kamera – Schauen geht nicht."
        eng = self.rt.engine
        if eng.notaus_gesperrt():
            return "Nach dem Not-Aus ruht der Körper noch – danach geht es wieder."
        st = be.state()
        if not st.powered or st.sitting:
            return "Der Körper schläft – erst aufwecken."
        return None

    def laeuft(self) -> bool:
        h = self.haltung
        if h is None or h.done or self.rt.engine.current is not h:
            self.haltung = None
            return False
        return True

    def start(self) -> dict[str, Any]:
        warum = self.grund()
        if warum:
            return {"ok": False, "fehler": warum}
        if not self.rt.gesicht.bereit():
            return {"ok": False, "fehler": "Erst die Gesichtserkennung laden."}
        self.rt.alltag.touch()
        h = SchauHaltung()
        self.haltung = h
        self.rt.engine.run(h)
        return {"ok": True}

    def blick(self, x: float, y: float, gesicht: bool) -> dict[str, Any]:
        if not self.laeuft():
            return {"ok": False, "laeuft": False, "fehler": "Schauen beendet – gerade läuft etwas anderes. Tippe noch einmal auf „Schau mich an“."}
        if self.rt.engine.notaus_gesperrt():
            self.stopp()
            return {"ok": False, "laeuft": False, "fehler": "Not-Aus – Schauen beendet."}
        h = self.haltung
        assert h is not None
        jetzt = time.monotonic()
        if gesicht:
            yaw, pitch = blick_aus_bild(min(1.0, max(0.0, x)), min(1.0, max(0.0, y)))
            weg = jetzt - self._zuletzt_gesehen
            self._zuletzt_gesehen = jetzt
            zeigen = getattr(self.rt.backend, "gefuehl_zeigen", None)
            if weg > FREUDE_NACH_S and jetzt - self._gefreut > FREUDE_ABSTAND_S and zeigen is not None:
                self._gefreut = jetzt
                zeigen("freude", 1.5)                       # wie das Original: freut sich, wenn er dich wiedersieht
        else:
            yaw, pitch = 0.0, -5.0                         # niemand da: geradeaus, leicht hoch
        h.setze(math.radians(yaw), math.radians(pitch))
        return {"ok": True, "yaw": round(yaw, 1), "pitch": round(pitch, 1)}

    def stopp(self) -> dict[str, Any]:
        h, self.haltung = self.haltung, None
        if h is not None and self.rt.engine.current is h:
            self.rt.engine.cancel_current("Schauen beendet")
        return {"ok": True}


def register(app: FastAPI, runtime: Runtime) -> None:
    store = G.store()
    runtime.gesicht = store
    schauen = Schauen(runtime)
    runtime.schauen = schauen

    async def laden() -> None:
        def melden(text: str) -> None:
            store.job["text"] = text

        try:
            res = await asyncio.to_thread(store.ensure, melden)
            store.job = {"laeuft": False, "fehler": None,
                         "text": "fertig – Gesichtserkennung bereit" if res["geladen"] else "war schon da"}
        except Exception as exc:  # noqa: BLE001 – Netz, Prüfsumme, Platte: alles ehrlich melden
            log.warning("Gesichtserkennung nicht geladen: %s", exc)
            store.job = {"laeuft": False, "text": "fehlgeschlagen", "fehler": f"{type(exc).__name__}: {exc}"}

    def antwort(res: dict[str, Any]) -> JSONResponse:
        return JSONResponse(res, status_code=200 if res.get("ok") else 409)

    @app.get("/api/schau")
    async def schau_status() -> JSONResponse:
        s = await asyncio.to_thread(store.status)
        return JSONResponse({**s, "laeuft": schauen.laeuft(), "grund": schauen.grund()})

    @app.post("/api/schau/laden")
    async def schau_laden() -> JSONResponse:
        if store.job.get("laeuft"):
            return JSONResponse({"ok": False, "fehler": "Die Gesichtserkennung wird schon geladen."}, status_code=409)
        if G.offline():
            return JSONResponse({"ok": False, "fehler": "Offline-Modus – die Gesichtserkennung wird nicht geladen."},
                                status_code=409)
        store.job = {"laeuft": True, "text": "startet …", "fehler": None}
        spawn(laden())
        return JSONResponse({"ok": True})

    @app.get("/api/schau/dateien/{name}")
    async def schau_datei(name: str):
        pfad = await asyncio.to_thread(store.datei, name)
        if pfad is None:
            return JSONResponse({"ok": False, "fehler": "Die Gesichtserkennung ist nicht geladen."}, status_code=404)
        return FileResponse(pfad, media_type=G.medientyp(name), headers={"Cache-Control": "no-cache"})

    @app.post("/api/schau/start")
    async def schau_start() -> JSONResponse:
        return antwort(schauen.start())

    @app.post("/api/schau/blick")
    async def schau_blick(request: Request) -> JSONResponse:
        d = await _json_body(request)

        def zahl(k: str) -> float:
            try:
                v = float(d.get(k, 0.5))
            except (TypeError, ValueError):
                return 0.5
            return 0.5 if math.isnan(v) or math.isinf(v) else v

        return antwort(schauen.blick(zahl("x"), zahl("y"), bool(d.get("gesicht"))))

    @app.post("/api/schau/stopp")
    async def schau_stopp() -> JSONResponse:
        return antwort(schauen.stopp())
