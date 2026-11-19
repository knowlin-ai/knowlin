"""Spiele für jeden Körper (seit 0.44, Fahrplan „Spiele“): „Ente sagt“, Verstecken, Elfmeter.

- **„Ente sagt“** (`ente_sagt.py`): für jeden Körper. Der Browser schickt nur ein Wort für das Handzeichen.
- **Verstecken** (`verstecken.py`): nur im einfachen Simulator und nur mit Beinen oder Rädern. Der Körper läuft über
  `go_to` mit allen Regeln; nach einem Not-Aus startet das Spiel gar nicht erst.
- **Elfmeter** (`motion/elfmeter.py`): nur im einfachen Simulator und nur mit Schussbein (`kick_left`/`kick_right`).

Gespielt werden darf auch vom Handy (nur Wörter und Zahlen, nichts über Personen). Bestwerte als Zahlen in
`<daten>/spiele_alle.json`. Gesagt wird über den normalen Weg der Verkörperung (Chat mit `source: "spiel"`).
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import settings as S
from ...aio import spawn
from ...ente_sagt import EnteSagt
from ...motion.elfmeter import Elfmeter
from ...verstecken import Verstecken, verstecke
from ..runtime import Runtime
from ..security import _json_body

DATEI = "spiele_alle.json"
ZAEHLEN_S = 10.0
VERSTECKEN_MAX_S = 30.0


def _fehler(text: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "fehler": text}, status_code=code)


class AlleSpiele:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self.sagt: EnteSagt | None = None
        self.versteck: Verstecken | None = None
        self.elfer: Elfmeter | None = None
        self._versteck_task: asyncio.Task | None = None

    # ── Gemeinsames ─────────────────────────────────────────────────────
    def bestwerte(self) -> dict[str, Any]:
        try:
            d = json.loads((S.data_dir() / DATEI).read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def bestwert(self, spiel: str, wert: int, kleiner_besser: bool = False) -> bool:
        d = self.bestwerte()
        alt = d.get(spiel)
        if isinstance(alt, int) and (wert >= alt if kleiner_besser else wert <= alt):
            return False
        d[spiel] = int(wert)
        S.data_dir().mkdir(parents=True, exist_ok=True)
        (S.data_dir() / DATEI).write_text(json.dumps(d), encoding="utf-8")
        return True

    async def sagen(self, text: str) -> None:
        await self.rt.broadcast({"type": "chat", "role": "duck", "text": text, "source": "spiel", "seconds": 0,
                                 "sprache": self.rt._speech(text)})

    async def melden(self, **daten: Any) -> None:
        await self.rt.broadcast({"type": "spiel_alle", **daten})     # „spiel“ gehört Reachys Kamera-Spielen

    def gesperrt(self) -> bool:
        return bool(self.rt.engine.notaus_gesperrt())

    async def freuen(self) -> None:
        """Eine kleine Freude mit dem Körper – nie während der Sperre nach einem Not-Aus."""
        if not self.gesperrt() and self.rt.backend.state().powered:
            try:
                await self.rt.runner.run("absicht", {"aktion": "freuen"})
            except Exception:  # noqa: BLE001 – ein Spiel scheitert nicht an einer Geste
                pass

    def stand(self) -> dict[str, Any]:
        out: dict[str, Any] = {"bestwerte": self.bestwerte(), "wer": self.rt.config.duck_name}
        if self.sagt is not None:
            out["sagt"] = self.sagt.stand()
        if self.versteck is not None:
            out["verstecken"] = {"phase": self.versteck.phase, "orte": [o["moebel"] for o in self.versteck.orte],
                                 "versuche": self.versteck.versuche}
        if self.elfer is not None:
            out["elfmeter"] = {"laeuft": not self.elfer.done, "schuss": self.elfer.nr, "tore": self.elfer.tore,
                               "schuesse": self.elfer.schuesse}
        return out

    # ── „Ente sagt“ ─────────────────────────────────────────────────────
    async def sagt_aktion(self, body: dict[str, Any]) -> JSONResponse:
        aktion = body.get("aktion")
        if aktion == "start":
            self.sagt = EnteSagt(self.rt.config.duck_name)
            runde = self.sagt.naechste()
            await self.sagen(f"Los geht's! Nur wenn ich „{self.sagt.wer} sagt“ sage, machst du es nach. {runde['text']}")
            return JSONResponse({"ok": True, "runde": runde, **self.sagt.stand()})
        if aktion == "antwort":
            if self.sagt is None or self.sagt.runde is None:
                return _fehler("Gerade läuft keine Runde.")
            r = self.sagt.antwort(body.get("zeichen"))
            if r["richtig"]:
                spawn(self.freuen())
            if r["vorbei"]:
                r["bestwert"] = self.bestwert("ente_sagt", r["punkte"])
                await self.sagen(r["satz"])
                self.sagt = None
                return JSONResponse({"ok": True, **r})
            runde = self.sagt.naechste()
            await self.sagen(f"{r['satz']} {runde['text']}")
            return JSONResponse({"ok": True, **r, "runde": runde})
        if aktion == "stopp":
            self.sagt = None
            return JSONResponse({"ok": True})
        return _fehler("unbekannte Aktion")

    # ── Verstecken ──────────────────────────────────────────────────────
    def _orte(self) -> list[dict[str, Any]] | None:
        welt = getattr(self.rt.backend, "world_model", None)
        if welt is None:
            return None
        from ...backends.sim import DUCK_RADIUS

        moebel = [{"name": b.name, "x": b.x, "y": b.y, "sx": b.sx, "sy": b.sy} for b in welt.boxes]
        moebel += [{"name": c.name, "x": c.x, "y": c.y, "r": c.r} for c in welt.cylinders]
        return verstecke(moebel, welt.width, welt.depth, lambda x, y: welt.collide(x, y, DUCK_RADIUS + 0.02) is None)

    async def versteck_aktion(self, body: dict[str, Any]) -> JSONResponse:
        aktion = body.get("aktion")
        eig = self.rt.backend.eigenschaften()
        if aktion == "start":
            if not ({"beine", "raeder"} & eig):
                return _fehler("Verstecken geht nur mit einem Körper, der laufen oder fahren kann.")
            orte = self._orte()
            if orte is None:
                return _fehler("Verstecken geht nur im einfachen Simulator.")
            if self.gesperrt():
                return _fehler("Nach dem Not-Aus geht er noch nicht los – kurz warten.")
            st = self.rt.backend.state()
            if not st.powered or st.fallen:
                return _fehler("Erst aufwecken – er muss stehen.")
            self.versteck = Verstecken(orte, seed=int(time.time()))
            self._versteck_task = spawn(self._verstecken(self.versteck))
            await self.melden(art="verstecken", phase="verstecken", text="Augen zu! Ich zähle bis zehn …")
            return JSONResponse({"ok": True, "phase": "verstecken", "orte": [o["moebel"] for o in orte]})
        if self.versteck is None:
            return _fehler("Gerade läuft kein Versteckspiel.")
        if aktion == "raten":
            try:
                r = self.versteck.raten(str(body.get("moebel", "")))
            except ValueError as exc:
                return _fehler(str(exc))
            await self.sagen(r["satz"])
            if r["treffer"]:
                r["bestwert"] = self.bestwert("verstecken", r["versuche"], kleiner_besser=True)
                spawn(self.freuen())
            if r["treffer"] or r.get("ende"):
                await self.melden(art="verstecken", phase=self.versteck.phase, text=r["satz"])
                self.versteck = None
            return JSONResponse({"ok": True, **r})
        if aktion == "aufgeben":
            r = self.versteck.aufgeben()
            if self._versteck_task and not self._versteck_task.done():
                self._versteck_task.cancel()
            await self.sagen(r["satz"])
            await self.melden(art="verstecken", phase="aufgedeckt", text=r["satz"])
            self.versteck = None
            return JSONResponse({"ok": True, **r})
        return _fehler("unbekannte Aktion")

    async def _verstecken(self, spiel: Verstecken) -> None:
        """Losgehen, zählen, und erst raten lassen, wenn er steht (oder nicht weiterkommt)."""
        ziel = spiel.ort
        await self.rt.runner.run("go_to", {"x": ziel["x"], "y": ziel["y"]})
        t0 = time.monotonic()
        while time.monotonic() - t0 < VERSTECKEN_MAX_S:
            await asyncio.sleep(0.25)
            if self.versteck is not spiel:
                return
            st = self.rt.backend.state()
            laeuft = self.rt.engine.current is not None and not self.rt.engine.current.done
            if time.monotonic() - t0 >= ZAEHLEN_S and (not laeuft or math.hypot(st.x - ziel["x"], st.y - ziel["y"]) < 0.12):
                break
        st = self.rt.backend.state()
        spiel.versteckt(st.x, st.y)
        await self.sagen("Zehn! Fertig – such mich!")
        await self.melden(art="verstecken", phase="raten", text="Wo hat er sich versteckt?",
                          orte=[o["moebel"] for o in spiel.orte])

    # ── Elfmeter ────────────────────────────────────────────────────────
    async def elfer_aktion(self, body: dict[str, Any]) -> JSONResponse:
        aktion = body.get("aktion")
        be = self.rt.backend
        if aktion == "start":
            if not callable(getattr(be, "tor_aufstellen", None)):
                return _fehler("Elfmeter geht nur im einfachen Simulator.")
            if not {"kick_left", "kick_right"} & set(be.skills()):
                return _fehler("Dieser Körper kann nicht schießen.")
            if self.gesperrt():
                return _fehler("Nach dem Not-Aus schießt sie noch nicht – kurz warten.")
            if not be.state().powered:
                return _fehler("Erst aufwecken – sie muss stehen.")
            tor = be.tor_aufstellen(True)
            loop = asyncio.get_running_loop()

            def melden(m: dict[str, Any]) -> None:
                loop.call_soon(lambda: spawn(self._elfer_gemeldet(m)))

            self.elfer = Elfmeter(tor, 5, melden=melden, seed=int(time.time()))
            self.rt.engine.run(self.elfer)
            await self.sagen("Elfmeter! Du stehst im Tor – hechte in eine Ecke, bevor ich schieße.")
            return JSONResponse({"ok": True, "schuesse": 5})
        if aktion == "hechten":
            if self.elfer is None or not self.elfer.hechten(str(body.get("seite", ""))):
                return JSONResponse({"ok": False})
            return JSONResponse({"ok": True, "seite": body.get("seite")})
        if aktion == "stopp":
            if self.elfer is not None and not self.elfer.done and self.rt.engine.current is self.elfer:
                self.rt.engine.cancel_current("Elfmeter beendet")
            self.elfer = None
            if callable(getattr(be, "tor_aufstellen", None)):
                be.tor_aufstellen(False)
            return JSONResponse({"ok": True})
        return _fehler("unbekannte Aktion")

    async def _elfer_gemeldet(self, m: dict[str, Any]) -> None:
        if "tor" not in m:
            await self.melden(art="elfmeter", **m)
            return
        satz = "Gehalten!" if m.get("gehalten") else "Tor!" if m["tor"] else "Daneben!"
        ende = m["schuss"] >= m["schuesse"]
        if ende:
            neu = self.bestwert("elfmeter", m["tore"])
            satz += f" Das war's: {m['tore']} von {m['schuesse']} im Tor{' – neuer Bestwert!' if neu else '.'}"
            if callable(getattr(self.rt.backend, "tor_aufstellen", None)):
                self.rt.backend.tor_aufstellen(False)
        await self.sagen(satz)
        await self.melden(art="elfmeter", satz=satz, ende=ende, **m)
        if ende and m["tore"] >= 3:                     # erst am Ende – eine Geste mittendrin löste den Elfmeter ab
            await self.freuen()


def register(app: FastAPI, runtime: Runtime) -> None:
    spiele = AlleSpiele(runtime)
    runtime.alle_spiele = spiele                         # type: ignore[attr-defined]

    @app.get("/api/spiel")
    async def spiel_stand() -> JSONResponse:
        return JSONResponse(spiele.stand())

    @app.post("/api/spiel/sagt")
    async def spiel_sagt(request: Request) -> JSONResponse:
        return await spiele.sagt_aktion(await _json_body(request))

    @app.post("/api/spiel/verstecken")
    async def spiel_verstecken(request: Request) -> JSONResponse:
        return await spiele.versteck_aktion(await _json_body(request))

    @app.post("/api/spiel/elfmeter")
    async def spiel_elfmeter(request: Request) -> JSONResponse:
        return await spiele.elfer_aktion(await _json_body(request))
