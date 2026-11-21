"""Marionette (seit 0.48, Mentor): Kopf führen mit dem Handy oder in der Quest, Bewegung aufnehmen und nachmachen.

WS (über `runtime.handle_client_message`): `{"type": "marionette", "gieren", "nicken", "neigen", "quelle"}` höchstens
20 je Sekunde, `{"type": "marionette_ende"}` beim Loslassen. HTTP:
- `GET /api/marionette` – geht es mit diesem Körper, läuft eine Aufnahme, welche Bewegungen sind gemerkt.
- `POST /api/marionette/aufnahme` `{aktion: start|stopp, name?}` – stoppen mit Namen merkt die Bewegung.
- `POST /api/marionette/abspielen` `{name}` – sie macht es nach (Verhalten `Nachspielen`).
- `DELETE /api/marionette/{name}` – vergessen.

Sicherheit: in der Sperre nach dem Not-Aus und stromlos folgt der Kopf nicht; der Not-Aus beendet Führen und
Abspielen. Nur drei Zahlen kommen an – kein Kamerabild, keine Raumdaten der Brille. Auch vom Handy erlaubt (dafür ist
es da); gespeichert wird nur die Bewegung.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import marionette as M
from ... import settings as S
from ...motion.nachspielen import Nachspielen
from ..runtime import Runtime
from ..security import _json_body

KEIN_KOPF = "Dieser Körper hat keinen Kopf zum Führen – ein Arm folgt deiner Hand (Vormachen mit Webcam oder in der Brille)."


class MarionetteDienst:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.bewegungen = M.Bewegungen(S.data_dir())
        self.m: M.Marionette | None = None
        self._zuletzt = 0.0
        self._gemeldet = 0.0

    # ── was geht ─────────────────────────────────────────────────────────
    def koerper(self) -> str:
        return str(getattr(self.rt.backend.state(), "koerper", "") or "unbekannt")

    def grund(self) -> str | None:
        return None if "kopf" in self.rt.backend.eigenschaften() else KEIN_KOPF

    def stand(self) -> dict[str, Any]:
        return {"ok": True, "grund": self.grund(), "fuehrt": self.m is not None,
                "nimmt_auf": bool(self.m and self.m.nimmt_auf), "quelle": self.m.quelle if self.m else None,
                "bewegungen": self.bewegungen.liste(self.koerper()), "max_s": M.AUFNAHME_MAX_S}

    # ── Führen ───────────────────────────────────────────────────────────
    async def nachricht(self, msg: dict[str, Any]) -> None:
        if msg.get("type") == "marionette_ende":
            self.ende()
            return
        lage = M.lage_aus(msg)
        if lage is None or self.grund() is not None:
            return
        eng = self.rt.engine
        jetzt = time.monotonic()
        if jetzt - self._zuletzt < 0.045:
            return
        self._zuletzt = jetzt
        if eng.notaus_gesperrt() or jetzt - getattr(eng, "stopped_at", 0.0) < 0.6 or not self.rt.backend.state().powered:
            if jetzt - self._gemeldet > 3:
                self._gemeldet = jetzt
                await self.rt.broadcast({"type": "marionette", "fehler": "Nach dem Not-Aus oder ohne Strom folgt sie nicht."})
            return
        if self.m is None:
            self.m = M.Marionette(quelle="vr" if msg.get("quelle") == "vr" else "handy")
            self.rt.alltag.touch()
        eng.kontakt("Marionette")
        kopf = self.m.weiter(lage, jetzt)
        eng.look_at(head=kopf, seconds=M.HALTEN_S)

    def ende(self) -> None:
        if self.m is not None and not self.m.nimmt_auf:
            self.m = None

    def not_aus(self) -> None:
        """Vom Not-Aus: Führen und Aufnahme enden (die Engine räumt Blick und Verhalten selbst ab)."""
        self.m = None

    # ── Aufnahme ─────────────────────────────────────────────────────────
    async def aufnahme(self, aktion: str, name: str = "") -> dict[str, Any]:
        if self.grund():
            return {"ok": False, "fehler": self.grund()}
        if aktion == "start":
            if self.m is None:
                self.m = M.Marionette()
            self.m.aufnehmen(time.monotonic())
            await self.rt.broadcast({"type": "marionette", "aufnahme": True})
            return {"ok": True, "text": "Aufnahme läuft – führe den Kopf."}
        if self.m is None:
            return {"ok": False, "fehler": "Es läuft keine Aufnahme."}
        punkte = self.m.aufnahme_ende()
        await self.rt.broadcast({"type": "marionette", "aufnahme": False})
        if not name:
            return {"ok": True, "text": "Aufnahme verworfen."}
        ok, text = self.bewegungen.speichern(self.koerper(), name, punkte)
        return {"ok": ok, "text": text, **({} if ok else {"fehler": text}), "bewegungen": self.bewegungen.liste(self.koerper())}

    def abspielen(self, name: str) -> dict[str, Any]:
        if self.grund():
            return {"ok": False, "fehler": self.grund()}
        b = self.bewegungen.holen(self.koerper(), name)
        if b is None:
            return {"ok": False, "fehler": f"„{name}“ kenne ich nicht."}
        eng = self.rt.engine
        if eng.notaus_gesperrt() or not self.rt.backend.state().powered:
            return {"ok": False, "fehler": "Nach dem Not-Aus oder ohne Strom macht sie nichts nach."}
        self.m = None
        eng.run(Nachspielen(b["name"], b["punkte"]))
        return {"ok": True, "text": f"Sie macht „{b['name']}“ nach."}


def register(app: FastAPI, runtime: Runtime) -> None:
    dienst = MarionetteDienst(runtime)
    runtime.marionette_dienst = dienst

    def antwort(d: dict[str, Any]) -> JSONResponse:
        return JSONResponse(d, status_code=200 if d.get("ok") else 400)

    @app.get("/api/marionette")
    async def marionette_stand() -> JSONResponse:
        return JSONResponse(dienst.stand())

    @app.post("/api/marionette/aufnahme")
    async def marionette_aufnahme(request: Request) -> JSONResponse:
        body = await _json_body(request)
        return antwort(await dienst.aufnahme(str(body.get("aktion") or ""), str(body.get("name") or "")))

    @app.post("/api/marionette/abspielen")
    async def marionette_abspielen(request: Request) -> JSONResponse:
        body = await _json_body(request)
        return antwort(dienst.abspielen(str(body.get("name") or "")))

    @app.delete("/api/marionette/{name}")
    async def marionette_loeschen(name: str) -> JSONResponse:
        ok = dienst.bewegungen.loeschen(dienst.koerper(), name)
        return antwort({"ok": ok, **({} if ok else {"fehler": "Nicht gefunden."}),
                        "bewegungen": dienst.bewegungen.liste(dienst.koerper())})
