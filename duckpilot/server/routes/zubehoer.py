"""Zubehör der Microduck (seit 0.47): Rollen, Arena-Rennen mit Zeitmessung und Geisterente, NFC-Polaroid.

- `GET /api/zubehoer` – was geht (laut Profil und Körper), Rollen, Strecke, Bestzeiten, laufendes Rennen.
- `POST /api/zubehoer/rollen` `{an, geduckt?}` – anklemmen, abnehmen, ducken (nur im Stand).
- `POST /api/zubehoer/rennen` `{aktion: start|stopp, selbst?}` – selbst fahren oder mit dem Steuerkreuz lenken. Die Zeit
  misst der Dienst aus der gemeldeten Lage; Meldungen gehen als `{"type": "rennen"}` an alle Fenster. Zur Bestzeit
  wird der Weg gespeichert – beim nächsten Mal fährt die Geisterente mit (nur gezeichnet).
- `POST /api/zubehoer/polaroid` – das Polaroid an den Kopf halten: wovon träumt sie? (`traum.py`)

Sicherheit: kein Rennen in der Sperre nach dem Not-Aus, nicht hochgehoben, nicht gestürzt. Der Not-Aus bricht das
selbst fahrende Rennen ab wie jedes Verhalten; ein Sturz beendet die Fahrt ohne Zeit.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import rennen as R
from ... import settings as S
from ...aio import spawn
from ...brain.tools import fehlt_dem_koerper
from ...motion.rennfahrt import Rennfahrt
from ...traum import traum
from ..runtime import Runtime
from ..security import _is_remote, _json_body

RENNEN_MAX_S = 180.0


def _s(x: float) -> str:
    return f"{x:.1f}".replace(".", ",") + " s"


class ZubehoerDienst:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.best = R.Bestzeiten(S.data_dir())
        self.fahrt: R.Zeitfahren | None = None
        self.renner: Rennfahrt | None = None

    def grund(self) -> str | None:
        return fehlt_dem_koerper("zubehoer", self.rt.backend)

    def stand(self) -> dict[str, Any]:
        st = self.rt.backend.state()
        f = self.fahrt
        return {"ok": True, "verfuegbar": self.grund() is None, "grund": self.grund(),
                "zubehoer": getattr(st, "zubehoer", {}) or {}, "tore": R.tore(), "bestzeiten": self.best.ueberblick(),
                "arten": R.ART_NAME, "laeuft": None if f is None else {"art": f.art, "naechstes": f.naechstes,
                                                                    "gestartet": f.start_t is not None}}

    async def melden(self, **daten: Any) -> None:
        await self.rt.broadcast({"type": "rennen", **daten})

    async def sagen(self, text: str, quelle: str) -> None:
        await self.rt.broadcast({"type": "chat", "role": "duck", "text": text, "source": quelle, "seconds": 0})

    def rollen(self, an: bool, geduckt: bool | None) -> dict[str, Any]:
        grund = self.grund()
        if grund:
            return {"ok": False, "fehler": grund}
        r = self.rt.backend.rollen_anlegen(an, geduckt)
        return {"ok": r.accepted, "text": r.reason or "", **({} if r.accepted else {"fehler": r.reason}),
                "zubehoer": self.rt.backend.state().zubehoer}

    async def rennen_start(self, selbst: bool = True) -> dict[str, Any]:
        grund = self.grund()
        if grund:
            return {"ok": False, "fehler": grund}
        if self.rt.engine.notaus_gesperrt():
            return {"ok": False, "fehler": "Nach dem Not-Aus fährt sie noch kein Rennen – kurz warten."}
        st = self.rt.backend.state()
        if not st.powered or st.fallen or st.picked_up:
            return {"ok": False, "fehler": "Erst aufwecken – sie muss stehen."}
        if self.fahrt is not None:
            return {"ok": False, "fehler": "Es läuft schon ein Rennen."}
        art = R.art_von(st.zubehoer)
        fahrt = R.Zeitfahren(art=art)
        self.fahrt = fahrt
        self.renner = Rennfahrt(fahrt) if selbst else None
        if self.renner is not None:
            self.rt.engine.run(self.renner)
        spawn(self._messen(fahrt))
        best = self.best.ueberblick().get(art)
        text = (f"Arena-Rennen {R.ART_NAME[art]}" + (f" – Bestzeit {_s(best)}" if best else "") +
                (". Ich stelle mich an die Startlinie." if selbst else ". Fahr mich über die Startlinie!"))
        await self.melden(phase="bereit", art=art, selbst=selbst, tore=R.tore(), geist=self.best.geist(art),
                          best=best, text=text)
        return {"ok": True, "text": text, "art": art}

    async def rennen_stopp(self, warum: str = "Rennen abgebrochen.") -> dict[str, Any]:
        fahrt, self.fahrt = self.fahrt, None
        if fahrt is None:
            return {"ok": True, "text": "Es lief kein Rennen."}
        if self.renner is not None and self.rt.engine.current is self.renner:
            self.rt.engine.cancel_current("Rennen beendet")
        self.renner = None
        await self.melden(phase="ende", text=warum)
        return {"ok": True, "text": warum}

    async def _messen(self, fahrt: R.Zeitfahren) -> None:
        t0 = time.monotonic()
        while self.fahrt is fahrt:
            await asyncio.sleep(0.05)
            st = self.rt.backend.state()
            if self.grund() is not None:                       # Körper gewechselt
                await self.rennen_stopp("Rennen abgebrochen.")
                return
            if st.fallen or not st.powered or self.rt.engine.notaus_gesperrt():
                await self.rennen_stopp("Gestürzt – das Rennen zählt nicht." if st.fallen else "Rennen abgebrochen.")
                return
            if time.monotonic() - t0 > RENNEN_MAX_S:
                await self.rennen_stopp("Zu lange – das Rennen zählt nicht.")
                return
            if self.renner is not None and self.renner.done and fahrt.fertig is None:
                await self.rennen_stopp(f"Rennen vorbei: {self.renner.result or 'abgebrochen'}.")
                return
            ev = fahrt.takt(st.t, st.x, st.y)
            if not ev:
                continue
            if not ev["ziel"]:
                await self.melden(phase="tor", **ev, art=fahrt.art)
                continue
            neu = self.best.eintragen(fahrt)
            text = f"Im Ziel nach {_s(fahrt.fertig)}" + (" – neue Bestzeit!" if neu else ".")
            self.fahrt, self.renner = None, None
            await self.melden(phase="ziel", zeit=fahrt.fertig, neu=neu, art=fahrt.art, text=text,
                              bestzeiten=self.best.ueberblick())
            await self.sagen(text, "rennen")
            return

    async def polaroid(self, remote: bool) -> dict[str, Any]:
        grund = self.grund()
        if grund:
            return {"ok": False, "fehler": grund}
        erf = getattr(self.rt, "erfahrung", None)
        r = erf.rueckblick(remote=remote) if erf is not None and erf.on else {}
        t = traum(r, en=getattr(self.rt.config, "sprache", "de") == "en")
        await self.rt.broadcast({"type": "polaroid", **t})
        await self.sagen(t["text"], "polaroid")
        return {"ok": True, **t}


def _antwort(d: dict[str, Any]) -> JSONResponse:
    return JSONResponse(d, status_code=200 if d.get("ok") else 400)


def register(app: FastAPI, runtime: Runtime) -> None:
    dienst = ZubehoerDienst(runtime)
    runtime.zubehoer_dienst = dienst
    if getattr(runtime, "runner", None) is not None:
        runtime.runner.zubehoer_dienst = dienst

    @app.get("/api/zubehoer")
    async def zubehoer_stand() -> JSONResponse:
        return JSONResponse(dienst.stand())

    @app.post("/api/zubehoer/rollen")
    async def zubehoer_rollen(request: Request) -> JSONResponse:
        body = await _json_body(request)
        g = body.get("geduckt")
        return _antwort(dienst.rollen(bool(body.get("an", True)), None if g is None else bool(g)))

    @app.post("/api/zubehoer/rennen")
    async def zubehoer_rennen(request: Request) -> JSONResponse:
        body = await _json_body(request)
        if body.get("aktion") == "stopp":
            return _antwort(await dienst.rennen_stopp())
        return _antwort(await dienst.rennen_start(selbst=body.get("selbst", True) is not False))

    @app.post("/api/zubehoer/polaroid")
    async def zubehoer_polaroid(request: Request) -> JSONResponse:
        return _antwort(await dienst.polaroid(remote=_is_remote(request)))
