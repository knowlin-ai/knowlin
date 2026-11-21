"""Knowlin Lab als Bereich (seit 0.50): Lernwege und Raum aus der Quest (`lab_bereich.py`).

- `GET /api/lab` – Lernwege mit den Körpern, die sie gehen können, Gelerntes (wie beim Mentor) und das gemessene Zimmer
- `POST /api/lab/raum` `{boden: [[x, y], …], flaechen: [{art, x, y, breite, tiefe, hoehe}, …]}` – aus der Quest
- `POST /api/lab/raum/aktiv` `{aktiv}` – der einfache Simulator benutzt das Zimmer (oder wieder das Wohnzimmer)
- `DELETE /api/lab/raum`

Das Zimmer wechselt nur im Stand, nicht in der Sperre nach dem Not-Aus und nur im einfachen Simulator (die Physik hat
ihr eigenes Modell). Steht sie danach außerhalb, stellt der Simulator sie in die Mitte.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import lab_bereich as LB
from ... import settings as S
from ..runtime import Runtime
from ..security import _json_body
from .mentor import _ueberblick

FARBE = {"Tisch": "#a88565", "Sofa": "#7a8fb3", "Regal": "#b9926f", "Bett": "#9fb0c8", "Schrank": "#b9926f"}


class LabDienst:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.raum = LB.QuestRaum(S.data_dir())

    def welt(self):
        return getattr(self.rt.backend, "world_model", None)

    def stand(self) -> dict[str, Any]:
        from ... import koerper as K

        profile = [k for k in K.alle() if k.simulator or k.eingebaut]
        aktiv = str(getattr(self.rt.backend.state(), "koerper", ""))
        try:
            gelernt = [z for z in _ueberblick(self.rt).get("ziele", []) if not z.get("eigen")]
        except Exception:  # noqa: BLE001 – ohne Gelerntes bleibt der Überblick
            gelernt = []
        return {"ok": True, "lernwege": LB.lernwege(profile, aktiv), "gelernt": gelernt, "raum": self.raum.laden(),
                "kann_raum": self.welt() is not None}

    def raum_anwenden(self) -> bool:
        """Beim Aufbau eines Körpers: das gemessene Zimmer benutzen, wenn es eingeschaltet ist."""
        r = self.raum.laden()
        welt = self.welt()
        if not r or not r.get("aktiv") or welt is None:
            return False
        self._setzen(welt, r["breite"], r["tiefe"], r.get("moebel") or [])
        return True

    def _setzen(self, welt: Any, breite: float, tiefe: float, moebel: list[dict[str, Any]]) -> None:
        from ...backends.world import Box, World

        if moebel is None:                                   # zurück zum Wohnzimmer
            neu = World.living_room()
            welt.width, welt.depth, welt.boxes, welt.cylinders = neu.width, neu.depth, neu.boxes, neu.cylinders
        else:
            welt.width, welt.depth = float(breite), float(tiefe)
            welt.boxes = [Box(m["name"], m["x"], m["y"], m["sx"], m["sy"], m["h"], FARBE.get(m["name"], "#b9a58c"))
                          for m in moebel]
            welt.cylinders = []
        w, d = welt.width / 2 - 0.1, welt.depth / 2 - 0.1
        for i in welt.items:                                 # Dinge bleiben im Zimmer
            i.x, i.y = max(-w, min(w, i.x)), max(-d, min(d, i.y))
        be = self.rt.backend
        if hasattr(be, "x") and (abs(be.x) > w - 0.1 or abs(be.y) > d - 0.1 or welt.collide(be.x, be.y, 0.08)):
            be.x, be.y = 0.0, 0.0                            # außerhalb oder im Möbel: in die Mitte

    async def aktiv(self, an: bool) -> dict[str, Any]:
        welt, eng = self.welt(), self.rt.engine
        if welt is None:
            return {"ok": False, "fehler": "Das Zimmer wechselt nur im einfachen Simulator (nicht in der Physik)."}
        if eng.notaus_gesperrt():
            return {"ok": False, "fehler": "Nach dem Not-Aus erst die Sperre abwarten."}
        if eng.busy():
            return {"ok": False, "fehler": "Erst anhalten – sie ist gerade unterwegs."}
        r = self.raum.laden()
        if an and not r:
            return {"ok": False, "fehler": "Noch kein Zimmer gemessen – in der Quest „Raum übernehmen“."}
        if an:
            self._setzen(welt, r["breite"], r["tiefe"], r.get("moebel") or [])
        else:
            self._setzen(welt, 0, 0, None)
        if r:
            self.raum.speichern(r, aktiv=an)
        await self.rt.broadcast(self.rt.init_message())        # alle Fenster bauen das Zimmer neu
        return {**self.stand(), "text": "Zimmer aus der Quest" if an else "Wohnzimmer"}


def register(app: FastAPI, runtime: Runtime) -> None:
    dienst = LabDienst(runtime)
    runtime.lab_dienst = dienst
    dienst.raum_anwenden()

    def antwort(d: dict[str, Any]) -> JSONResponse:
        return JSONResponse(d, status_code=200 if d.get("ok") else 400)

    @app.get("/api/lab")
    async def lab_stand() -> JSONResponse:
        return JSONResponse(dienst.stand())

    @app.post("/api/lab/raum")
    async def lab_raum(request: Request) -> JSONResponse:
        raum, grund = LB.pruefen(await _json_body(request))
        if raum is None:
            return antwort({"ok": False, "fehler": grund})
        dienst.raum.speichern(raum)
        return antwort({**dienst.stand(), "text": f"Zimmer {raum['breite']:.1f} × {raum['tiefe']:.1f} m, "
                                                  f"{len(raum['moebel'])} Möbel"})

    @app.post("/api/lab/raum/aktiv")
    async def lab_raum_aktiv(request: Request) -> JSONResponse:
        return antwort(await dienst.aktiv(bool((await _json_body(request)).get("aktiv"))))

    @app.delete("/api/lab/raum")
    async def lab_raum_loeschen() -> JSONResponse:
        r = dienst.raum.laden()
        if r and r.get("aktiv") and dienst.welt() is not None:
            await dienst.aktiv(False)
        dienst.raum.loeschen()
        return antwort(dienst.stand())
