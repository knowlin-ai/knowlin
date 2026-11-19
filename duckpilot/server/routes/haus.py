"""Haushalt und Smart Home (seit 0.45): Einrichten (nur am PC), Geräte schalten, aufräumen vor dem Saugroboter,
Heimkehr zum Ladeplatz.

- Einrichten (`/api/haus/ha`, `/api/haus/hue`, `/api/haus/einstellungen`, `/api/haus/akku_knapp`) nur am PC
  (`remote.PC_ONLY`) – Token und Hue-Schlüssel gehen in den Tresor, nach außen nur „verbunden“.
- Schalten (`/api/haus/schalten`) auch vom gekoppelten Handy; nur freigegebene Geräte (`haus.py`).
- Aufräumen vor dem Saugroboter: nur im einfachen Simulator und nur mit Schnabel und Beinen. Danach startet der Sauger
  nur, wenn einer gewählt ist und keine Sperre nach einem Not-Aus gilt.
- Heimkehr: ist ein Ort „Ladeplatz“ gemerkt und fällt der Akku unter die Schwelle (Standard 15 %), geht der Körper
  dorthin, setzt sich und bittet um einen Akkuwechsel – nie in der Sperre, nie hochgehoben, nie mitten in einem Befehl.
  Einmal je Entladung (erst über Schwelle + 10 % wieder bereit).
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import haus as H
from ...aio import spawn
from ...motion.haushalt import Heimkehr, VorDemSauger
from ..runtime import Runtime
from ..security import _json_body

LADEPLATZ = "Ladeplatz"
KORB = "Korb"
SCHWELLE = 0.15
WIEDER_BEREIT = 0.10
AUFHEBBAR = ("sock", "block", "baustein", "figur")


def _fehler(text: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "fehler": text}, status_code=code)


class HausDienst:
    def __init__(self, rt: Runtime, haus: H.Haus) -> None:
        self.rt = rt
        self.haus = haus
        self.aufraeumen: VorDemSauger | None = None
        self.sauger_danach: str | None = None
        self.heimkehr_bereit = True
        self.heimkehr: Heimkehr | None = None
        self._waechter: asyncio.Task | None = None

    # ── Hilfen ───────────────────────────────────────────────────────────
    def gesperrt(self) -> bool:
        return bool(self.rt.engine.notaus_gesperrt())

    def koerper(self) -> str:
        return self.rt.runner.body()

    def ort(self, name: str) -> tuple[float, float, str] | None:
        mem = self.rt.memory
        if mem is None:
            return None
        key = mem.find_place(name, self.koerper())
        if not key:
            return None
        p = mem.data["orte"][key]
        return float(p["x"]), float(p["y"]), key

    def schwelle(self) -> float:
        try:
            return min(0.5, max(0.05, float(self.haus.einstellungen().get("akku_schwelle", SCHWELLE))))
        except (TypeError, ValueError):
            return SCHWELLE

    async def sagen(self, text: str) -> None:
        await self.rt.broadcast({"type": "chat", "role": "duck", "text": text, "source": "haus", "seconds": 0,
                                 "sprache": self.rt._speech(text)})

    async def melden(self, **daten: Any) -> None:
        await self.rt.broadcast({"type": "haus", **daten})

    def stand(self) -> dict[str, Any]:
        st = self.rt.backend.state()
        eig = self.rt.backend.eigenschaften()
        out = {**self.haus.stand(), "akku": st.battery, "schwelle": self.schwelle(),
               "ladeplatz": self.ort(LADEPLATZ) is not None, "korb": self.ort(KORB) is not None,
               "kann_aufraeumen": {"schnabel", "beine"} <= eig and getattr(self.rt.backend, "world_model", None) is not None,
               "kann_heimkehr": bool({"beine", "raeder"} & eig), "simulator": "simulator" in eig,
               "sauger_danach": self.haus.einstellungen().get("sauger_danach", "")}
        if self.aufraeumen is not None:
            out["aufraeumen"] = {"laeuft": not self.aufraeumen.done, **self.aufraeumen.info()}
        return out

    # ── Geräte ───────────────────────────────────────────────────────────
    async def geraete(self, neu: bool) -> dict[str, Any]:
        geraete, fehler = await asyncio.to_thread(self.haus.geraete, neu)
        return {"ok": True, "geraete": [H.als_dict(g) for g in geraete], "fehler": fehler}

    async def schalten(self, gid: str, aktion: str) -> JSONResponse:
        g = await asyncio.to_thread(self.haus.geraet, gid)
        if g is not None and g.art == "sauger" and aktion == "start" and self.gesperrt():
            return _fehler("Nach dem Not-Aus starte ich in der Sperre keinen Saugroboter – kurz warten.")
        try:
            g = await asyncio.to_thread(self.haus.schalten, gid, aktion)
        except ValueError as exc:
            return _fehler(str(exc))
        except Exception as exc:  # noqa: BLE001 – Netz, Zentrale
            return _fehler(f"Hat nicht geklappt: {str(exc)[:160]}", 502)
        return JSONResponse({"ok": True, "geraet": H.als_dict(g)})

    # ── Aufräumen vor dem Saugroboter ────────────────────────────────────
    def _ziel(self, wort: str) -> tuple[float, float, str] | None:
        o = self.ort(wort or KORB)
        if o is not None:
            return o
        welt = getattr(self.rt.backend, "world_model", None)
        w = (wort or "").strip().lower()
        if welt is not None and w:
            for m in [*welt.boxes, *welt.cylinders]:
                if m.name.lower() == w or w in m.name.lower():
                    st = self.rt.backend.state()
                    d = math.hypot(st.x - m.x, st.y - m.y) or 1.0
                    return m.x + (st.x - m.x) / d * 0.45, m.y + (st.y - m.y) / d * 0.45, f"zum {m.name}"
        return None

    async def aufraeumen_start(self, ziel_wort: str = "", sauger: bool = True) -> dict[str, Any]:
        be = self.rt.backend
        welt = getattr(be, "world_model", None)
        if welt is None:
            return {"ok": False, "fehler": "Aufräumen vor dem Saugroboter geht im einfachen Simulator."}
        if not {"schnabel", "beine"} <= be.eigenschaften():
            return {"ok": False, "fehler": "Dafür braucht der Körper Beine und etwas zum Aufheben."}
        if self.gesperrt():
            return {"ok": False, "fehler": "Nach dem Not-Aus geht sie noch nicht los – kurz warten."}
        st = be.state()
        if not st.powered or st.fallen or st.picked_up:
            return {"ok": False, "fehler": "Erst aufwecken – sie muss stehen."}
        z = self._ziel(ziel_wort)
        if z is None:
            return {"ok": False, "fehler": f"Wohin damit? Merk dir erst einen Ort „{KORB}“ (Umgebung → Orte) oder nenn "
                                           "ein Möbelstück."}
        zx, zy, zname = z
        dinge = [{"name": i.name, "x": i.x, "y": i.y} for i in welt.items
                 if i.kind in AUFHEBBAR and not i.held and math.hypot(i.x - zx, i.y - zy) > 0.35]
        dinge.sort(key=lambda d: math.hypot(d["x"] - st.x, d["y"] - st.y))
        raum = getattr(self.rt, "raum", None)
        b = VorDemSauger(dinge[:8], (zx, zy), zname, karte=getattr(raum, "karte", None))
        self.aufraeumen = b
        self.sauger_danach = (self.haus.einstellungen().get("sauger_danach") or None) if sauger else None
        self.rt.engine.run(b)
        spawn(self._aufraeumen_warten(b))
        text = (f"Ich räume vor dem Saugroboter auf: {len(dinge[:8])} "
                f"{'Ding' if len(dinge[:8]) == 1 else 'Dinge'} zu {zname}." if dinge else
                "Hier liegt nichts herum.")
        await self.melden(art="aufraeumen", laeuft=True, text=text)
        return {"ok": True, "text": text, "dinge": [d["name"] for d in dinge[:8]], "ziel": zname,
                "sauger_danach": bool(self.sauger_danach)}

    async def _aufraeumen_warten(self, b: VorDemSauger) -> None:
        t0 = time.monotonic()
        while not b.done and time.monotonic() - t0 < (b.timeout or 600) + 10:
            await asyncio.sleep(0.5)
            if self.rt.engine.current is not b and not b.done:       # abgebrochen (Not-Aus, anderer Befehl)
                await self.melden(art="aufraeumen", laeuft=False, text="Aufräumen abgebrochen.")
                return
        text = b.result or "fertig"
        if self.sauger_danach and b.ergebnis_art == "erfolg":
            if self.gesperrt():
                text += " Den Saugroboter starte ich nach dem Not-Aus nicht."
            else:
                try:
                    g = await asyncio.to_thread(self.haus.schalten, self.sauger_danach, "start")
                    text += f" {g.name} saugt jetzt."
                except Exception as exc:  # noqa: BLE001
                    text += f" Den Saugroboter konnte ich nicht starten: {str(exc)[:120]}"
        await self.sagen(text)
        await self.melden(art="aufraeumen", laeuft=False, text=text, **b.info())
        try:
            await asyncio.to_thread(self.haus.melden, text)
        except Exception:  # noqa: BLE001 – Meldung ist freiwillig
            pass

    # ── Heimkehr zum Ladeplatz ───────────────────────────────────────────
    def _heimkehr_noetig(self) -> tuple[float, float, str] | None:
        st = self.rt.backend.state()
        if st.battery is None:
            return None
        if st.battery > self.schwelle() + WIEDER_BEREIT:
            self.heimkehr_bereit = True
            return None
        if not self.heimkehr_bereit or st.battery > self.schwelle():
            return None
        if not ({"beine", "raeder"} & self.rt.backend.eigenschaften()):
            return None
        if self.gesperrt() or st.picked_up or st.fallen or not st.powered:
            return None
        lauf = self.rt.engine.current
        if lauf is not None and not lauf.done and not getattr(lauf, "eigenstaendig", False):
            return None                               # nie mitten in einem Befehl – sie fragt beim nächsten Takt wieder
        return self.ort(LADEPLATZ)

    async def heimkehr_pruefen(self) -> bool:
        ziel = self._heimkehr_noetig()
        if ziel is None:
            return False
        self.heimkehr_bereit = False
        x, y, name = ziel
        akku = round((self.rt.backend.state().battery or 0) * 100)
        self.heimkehr = Heimkehr((x, y), name)
        self.rt.engine.run(self.heimkehr)
        text = f"Mein Akku hat nur noch {akku} % – ich gehe zum {name}."
        await self.sagen(text)
        await self.melden(art="heimkehr", text=text)
        spawn(self._heimkehr_warten(self.heimkehr))
        return True

    async def _heimkehr_warten(self, b: Heimkehr) -> None:
        t0 = time.monotonic()
        while not b.done and time.monotonic() - t0 < 100:
            await asyncio.sleep(0.5)
            if self.rt.engine.current is not b and not b.done:
                return
        text = (b.result or "").capitalize() + "."
        await self.sagen(text)
        try:
            await asyncio.to_thread(self.haus.melden, f"Akku knapp: {b.result}")
        except Exception:  # noqa: BLE001
            pass

    async def waechter(self) -> None:
        while True:
            await asyncio.sleep(2.0)
            try:
                await self.heimkehr_pruefen()
            except Exception:  # noqa: BLE001 – der Wächter darf nie stehen bleiben
                pass


def register(app: FastAPI, runtime: Runtime) -> None:
    haus: H.Haus = runtime.haus
    dienst = HausDienst(runtime, haus)
    runtime.haus_dienst = dienst

    @app.get("/api/haus")
    async def haus_stand() -> JSONResponse:
        return JSONResponse(dienst.stand())

    @app.get("/api/haus/geraete")
    async def haus_geraete(neu: bool = False) -> JSONResponse:
        return JSONResponse(await dienst.geraete(neu))

    @app.post("/api/haus/schalten")
    async def haus_schalten(request: Request) -> JSONResponse:
        b = await _json_body(request)
        return await dienst.schalten(str(b.get("id", "")), str(b.get("aktion", "")))

    @app.post("/api/haus/ha")
    async def haus_ha(request: Request) -> JSONResponse:
        b = await _json_body(request)
        try:
            antwort = await asyncio.to_thread(haus.ha_verbinden, str(b.get("adresse", "")), str(b.get("token", "")),
                                              str(b.get("melden", "")).strip())
        except (ValueError, RuntimeError) as exc:
            return _fehler(str(exc))
        except Exception as exc:  # noqa: BLE001 – nicht erreichbar, Token falsch (401)
            return _fehler(f"Home Assistant antwortet nicht wie erwartet: {str(exc)[:160]}", 502)
        return JSONResponse({"ok": True, "antwort": antwort, **haus.stand()})

    @app.post("/api/haus/hue")
    async def haus_hue(request: Request) -> JSONResponse:
        b = await _json_body(request)
        try:
            ok = await asyncio.to_thread(haus.hue_koppeln, str(b.get("adresse", "")))
        except (ValueError, RuntimeError) as exc:
            return _fehler(str(exc))
        except Exception as exc:  # noqa: BLE001
            return _fehler(f"Hue Bridge nicht erreichbar: {str(exc)[:160]}", 502)
        if not ok:
            return JSONResponse({"ok": False, "knopf": True,
                                 "fehler": "Drück den runden Knopf oben auf der Hue Bridge und dann innerhalb von 30 s "
                                           "noch einmal „Koppeln“."})
        return JSONResponse({"ok": True, **haus.stand()})

    @app.delete("/api/haus/{weg}")
    async def haus_trennen(weg: str) -> JSONResponse:
        if weg not in ("ha", "hue"):
            return _fehler("ha oder hue", 404)
        await asyncio.to_thread(haus.trennen, weg)
        return JSONResponse({"ok": True, **haus.stand()})

    @app.post("/api/haus/einstellungen")
    async def haus_einstellungen(request: Request) -> JSONResponse:
        b = await _json_body(request)
        neu: dict[str, Any] = {}
        if "sauger_danach" in b:
            sid = str(b.get("sauger_danach") or "")
            if sid:
                g = await asyncio.to_thread(haus.geraet, sid)
                if g is None or g.art != "sauger":
                    return _fehler("Das ist kein Saugroboter aus der Liste.")
            neu["sauger_danach"] = sid
        if "akku_schwelle" in b:
            v = b.get("akku_schwelle")
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.05 <= v <= 0.5:
                return _fehler("Schwelle: 5 bis 50 %")
            neu["akku_schwelle"] = round(float(v), 2)
        haus._speichern(**neu)
        return JSONResponse({"ok": True, **dienst.stand()})

    @app.post("/api/haus/aufraeumen")
    async def haus_aufraeumen(request: Request) -> JSONResponse:
        b = await _json_body(request)
        r = await dienst.aufraeumen_start(str(b.get("ziel", "")), b.get("sauger", True) is not False)
        return JSONResponse(r, status_code=200 if r.get("ok") else 400)

    @app.post("/api/haus/ort")
    async def haus_ort(request: Request) -> JSONResponse:
        """„Hier ist der Ladeplatz“ / „hier steht der Korb“: Ort an der aktuellen Stelle merken."""
        b = await _json_body(request)
        name = {"ladeplatz": LADEPLATZ, "korb": KORB}.get(str(b.get("was", "")))
        if name is None or runtime.memory is None:
            return _fehler("was: ladeplatz oder korb")
        st = runtime.backend.state()
        key = runtime.memory.remember_place(name, dienst.koerper(), st.x, st.y, st.yaw, "seit 0.45 (Haushalt)")
        return JSONResponse({"ok": True, "ort": key, **dienst.stand()})

    @app.post("/api/haus/akku_knapp")
    async def haus_akku_knapp() -> JSONResponse:
        """Nur im Simulator: Akku auf knapp setzen, um die Heimkehr auszuprobieren."""
        be = runtime.backend
        if "simulator" not in be.eigenschaften() or not hasattr(be, "battery"):
            return _fehler("Nur im Simulator.")
        be.battery = max(0.05, dienst.schwelle() - 0.02)
        dienst.heimkehr_bereit = True
        return JSONResponse({"ok": True, "akku": be.battery, "ladeplatz": dienst.ort(LADEPLATZ) is not None})
