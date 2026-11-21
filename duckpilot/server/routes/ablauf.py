"""Ablauf-Baukasten und Duck Cards (seit 0.49): Abläufe abspielen, speichern, aus Karten lesen (`ablauf.py`).

- `GET /api/ablauf` – gespeicherte Abläufe (mit den Duck Cards zum Hinlegen), läuft gerade einer?
- `POST /api/ablauf/start` `{ablauf}` oder `{name}` · `POST /api/ablauf/stopp`
- `POST /api/ablauf/speichern` `{ablauf}` · `DELETE /api/ablauf/{name}`
- `POST /api/ablauf/karten` `{tags: [{id, x, y, w}], mal?}` – erkannte Duck Cards → Ablauf (nur Nummern und Lagen)

Jeder Schritt läuft über die Werkzeuge des Körpers (walk, turn, head, skill, sound, pause) – mit ihren Regeln. Was der
Körper nicht kann, wird übersprungen und genannt („nur zeigen, was der Körper kann“). Meldungen gehen als
`{"type": "ablauf"}` an alle Fenster. Sicherheit: kein Start in der Sperre nach dem Not-Aus; der Not-Aus beendet den
Ablauf sofort; fällt sie, endet die erste Reihe – steht sie wieder, läuft die Reihe „Wenn sie fällt“.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import ablauf as A
from ... import settings as S
from ...aio import spawn
from ...brain.tools import fehlt_dem_koerper
from ..runtime import Runtime
from ..security import _json_body

STRECKE_M = 0.3
DREHEN_GRAD = 90
TEMPO_M_S = {"langsam": 0.08, "normal": 0.15, "schnell": 0.25}
SCHAUEN_GRAD = {"links": (40, 0), "rechts": (-40, 0), "hoch": (0, -25), "runter": (0, 25), "gerade": (0, 0)}
AUFSTEHEN_S = 20.0
NAMEN = {"gehen": "gehen", "drehen": "drehen", "schauen": "schauen", "trick": "Tricks", "laut": "Laute", "stopp": "anhalten"}


class Abgebrochen(Exception):
    pass


class AblaufDienst:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.ablage = A.Ablaeufe(S.data_dir())
        self.laeuft: dict[str, Any] | None = None
        self._task: asyncio.Task | None = None
        self._estop = 0.0

    def stand(self) -> dict[str, Any]:
        alle = {k: {**v, "karten": A.als_karten(v["schritte"]), "karten_sturz": A.als_karten(v.get("bei_sturz") or []),
                    "anzahl": A.anzahl(v["schritte"])}
                for k, v in self.ablage.alle().items()}
        return {"ok": True, "ablaeufe": alle, "laeuft": self.laeuft, "quelle": A.QUELLE, "druck": A.DRUCK,
                "karten": {str(k): {"code": c, "name": n} for k, (c, n) in A.KARTEN.items()}}

    async def melden(self, **d: Any) -> None:
        await self.rt.broadcast({"type": "ablauf", **d})

    # ── Start und Stopp ──────────────────────────────────────────────────
    async def start(self, body: dict[str, Any]) -> dict[str, Any]:
        if body.get("name") and not body.get("ablauf"):
            ablauf = self.ablage.alle().get(str(body["name"]))
            if ablauf is None:
                return {"ok": False, "fehler": f"Einen Ablauf „{body['name']}“ gibt es nicht."}
        else:
            ablauf, grund = A.pruefen(body.get("ablauf"))
            if ablauf is None:
                return {"ok": False, "fehler": grund}
        eng = self.rt.engine
        if eng.notaus_gesperrt():
            return {"ok": False, "fehler": "Nach dem Not-Aus startet noch kein Ablauf – kurz warten."}
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._estop = getattr(eng, "estop_at", 0.0)
        self.laeuft = {"name": ablauf["name"] or "Ablauf", "nr": 0, "gesamt": A.anzahl(ablauf["schritte"])}
        self._task = spawn(self._abspielen(ablauf))
        return {"ok": True, "text": f"Ablauf „{self.laeuft['name']}“ – {self.laeuft['gesamt']} Schritte."}

    async def stopp(self, warum: str = "Ablauf angehalten.") -> dict[str, Any]:
        t, self._task = self._task, None
        if t is not None and not t.done():
            t.cancel()
            if self.laeuft is not None:
                await self.rt.runner.run("stop", {})
        if self.laeuft is not None:
            self.laeuft = None
            await self.melden(phase="ende", text=warum)
        return {"ok": True, "text": warum}

    def not_aus(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task, self.laeuft = None, None

    # ── Abspielen ────────────────────────────────────────────────────────
    async def _abspielen(self, ablauf: dict[str, Any]) -> None:
        uebersprungen: set[str] = set()
        await self.melden(phase="start", name=self.laeuft["name"], gesamt=self.laeuft["gesamt"])
        try:
            try:
                await self._reihe(ablauf["schritte"], [], uebersprungen)
                text = "Ablauf fertig."
            except _Gefallen:
                text = await self._nach_sturz(ablauf, uebersprungen)
            if uebersprungen:
                text += " Übersprungen, weil dieser Körper es nicht kann: " + ", ".join(sorted(uebersprungen)) + "."
            self.laeuft = None
            await self.melden(phase="ende", text=text)
        except (asyncio.CancelledError, Abgebrochen):
            self.laeuft = None
            await self.melden(phase="ende", text="Ablauf abgebrochen.")

    async def _nach_sturz(self, ablauf: dict[str, Any], uebersprungen: set[str]) -> str:
        if not ablauf["bei_sturz"]:
            return "Sie ist gefallen – Ablauf beendet."
        await self.melden(phase="sturz", text="Sie ist gefallen – sobald sie steht, kommt die Reihe „Wenn sie fällt“.")
        ende = time.monotonic() + AUFSTEHEN_S
        while time.monotonic() < ende:
            self._pruefe_notaus()
            st = self.rt.backend.state()
            if not st.fallen and st.powered:
                break
            await asyncio.sleep(0.2)
        else:
            return "Sie liegt noch – die Reihe „Wenn sie fällt“ fällt aus."
        try:
            await self._reihe(ablauf["bei_sturz"], ["sturz"], uebersprungen)
        except _Gefallen:
            return "Wieder gefallen – Ablauf beendet."
        return "Nach dem Sturz weitergemacht – Ablauf fertig."

    def _pruefe_notaus(self) -> None:
        if getattr(self.rt.engine, "estop_at", 0.0) != self._estop:
            raise Abgebrochen

    async def _reihe(self, schritte: list[dict[str, Any]], pfad: list[Any], uebersprungen: set[str]) -> None:
        for i, s in enumerate(schritte):
            if s["art"] == "wiederholen":
                for runde in range(s["mal"]):
                    await self._reihe(s["schritte"], [*pfad, i, runde], uebersprungen)
                continue
            self._pruefe_notaus()
            if self.laeuft is not None:
                self.laeuft["nr"] += 1
                await self.melden(phase="schritt", pfad=[*pfad, i], nr=self.laeuft["nr"], gesamt=self.laeuft["gesamt"])
            await self._schritt(s, uebersprungen)
            st = self.rt.backend.state()
            if st.fallen:
                raise _Gefallen

    async def _werkzeug(self, name: str, args: dict[str, Any], was: str, uebersprungen: set[str]) -> bool:
        if fehlt_dem_koerper(name, self.rt.backend) is not None:
            uebersprungen.add(was)
            return False
        r = await self.rt.runner.run(name, args)
        return not (isinstance(r, dict) and r.get("ok") is False)

    async def _schritt(self, s: dict[str, Any], uebersprungen: set[str]) -> None:
        art = s["art"]
        if s.get("schauen") and art != "schauen":
            yaw, pitch = SCHAUEN_GRAD[s["schauen"]]
            await self._werkzeug("head", {"yaw_deg": yaw, "pitch_deg": pitch, "seconds": 4}, "schauen", uebersprungen)
        if art == "gehen":
            d = STRECKE_M if s["richtung"] == "vor" else -STRECKE_M
            ok = await self._werkzeug("walk", {"distance_m": d, "speed": TEMPO_M_S[s.get("tempo", "normal")]},
                                      "gehen", uebersprungen)
        elif art == "drehen":
            ok = await self._werkzeug("turn", {"degrees": DREHEN_GRAD if s["richtung"] == "links" else -DREHEN_GRAD},
                                      "drehen", uebersprungen)
        elif art == "stopp":
            ok = await self._werkzeug("pause", {"seconds": 1.0}, "anhalten", uebersprungen)
        elif art == "schauen":
            yaw, pitch = SCHAUEN_GRAD[s["richtung"]]
            ok = await self._werkzeug("head", {"yaw_deg": yaw, "pitch_deg": pitch, "seconds": 1.5}, "schauen", uebersprungen)
            if ok:
                await self._werkzeug("pause", {"seconds": 1.5}, "schauen", uebersprungen)
        elif art == "trick":
            skills = set(self.rt.backend.skills() or [])
            if s["name"] not in skills:
                uebersprungen.add(A.kartenname({v: k for k, v in A.TRICKS.items()}[s["name"]]))
                return
            ok = await self._werkzeug("skill", {"name": s["name"]}, "Tricks", uebersprungen)
        elif art == "laut":
            ok = await self._werkzeug("sound", {"tag": s["name"]}, "Laute", uebersprungen)
            if ok:
                await asyncio.sleep(0.6)
            return
        else:
            return
        if ok:
            await self.rt.runner.run("wait", {"max_seconds": 20})


class _Gefallen(Exception):
    pass


def register(app: FastAPI, runtime: Runtime) -> None:
    dienst = AblaufDienst(runtime)
    runtime.ablauf_dienst = dienst
    if getattr(runtime, "runner", None) is not None:
        runtime.runner.ablauf_dienst = dienst

    def antwort(d: dict[str, Any]) -> JSONResponse:
        return JSONResponse(d, status_code=200 if d.get("ok") else 400)

    @app.get("/api/ablauf")
    async def ablauf_stand() -> JSONResponse:
        return JSONResponse(dienst.stand())

    @app.post("/api/ablauf/start")
    async def ablauf_start(request: Request) -> JSONResponse:
        return antwort(await dienst.start(await _json_body(request)))

    @app.post("/api/ablauf/stopp")
    async def ablauf_stopp() -> JSONResponse:
        return antwort(await dienst.stopp())

    @app.post("/api/ablauf/speichern")
    async def ablauf_speichern(request: Request) -> JSONResponse:
        body = await _json_body(request)
        name, grund = dienst.ablage.speichern(body.get("ablauf"))
        return antwort({"ok": True, "name": name, **dienst.stand()} if name else {"ok": False, "fehler": grund})

    @app.delete("/api/ablauf/{name}")
    async def ablauf_loeschen(name: str) -> JSONResponse:
        ok = dienst.ablage.loeschen(name)
        return antwort({"ok": True, **dienst.stand()} if ok else {"ok": False, "fehler": "Nicht gefunden."})

    @app.post("/api/ablauf/karten")
    async def ablauf_karten(request: Request) -> JSONResponse:
        body = await _json_body(request)
        tags = body.get("tags") if isinstance(body.get("tags"), list) else []
        try:
            mal = int(body.get("mal", 2))
        except (TypeError, ValueError):
            mal = 2
        r = A.aus_karten(tags, max(1, min(A.MAX_MAL, mal)))
        if r.get("ok"):                              # Gruppen für den Baukasten: Karte plus Zusatzkarten darunter
            r["gruppen"] = A.als_karten(r["ablauf"]["schritte"])
            r["gruppen_sturz"] = A.als_karten(r["ablauf"]["bei_sturz"])
        return antwort(r)
