"""Tanzen zu Musik und Choreomodus (seit 0.36): Musikstücke, Tanzplan, speichern, tanzen."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from ... import choreo as C
from ...aio import spawn
from ..runtime import Runtime


def register(app: FastAPI, runtime: Runtime) -> None:
    def art() -> str:
        return getattr(runtime.backend, "koerper_art", "microduck")

    def posen() -> dict:
        """Posen aus Lernen → Akrobatik – die gibt es nur bei der Microduck (Open Duck und Reachy: keine Akrobatik)."""
        return dict(runtime.acro.book.get("posen", {})) if art() == "microduck" else {}

    @app.get("/api/choreo")
    async def choreo_liste() -> JSONResponse:
        buch = runtime.choreos
        musik = sorted(p.name for p in buch.musik.glob("*") if p.suffix.lower() in C.MUSIK_ENDUNGEN) if buch.musik.exists() else []
        reachy = art() == "reachy_mini"
        out = {"taenze": buch.liste(), "posen": sorted(posen()), "musik": musik,
               "gesten": list(C.REACHY_TANZ) if reachy else C.gesten(),
               "physik": bool(getattr(runtime.backend, "runs_policies", False)),
               "ki": bool(runtime.agent.online), "reachy": reachy}
        if reachy:                  # Reachys eigener Tanz (seit 0.38.13): Bewegungen, Gefühle, Namen für die Oberfläche
            out |= {"gefuehle": C.reachy_gesten(), "namen": C.REACHY_TANZ_TEXT}
        return JSONResponse(out)

    @app.get("/api/choreo/{name}")
    async def choreo_hole(name: str) -> JSONResponse:
        c = runtime.choreos.hole(name)
        return JSONResponse({"ok": bool(c), "choreo": c}, status_code=200 if c else 404)

    @app.post("/api/musik")
    async def musik_hoch(request: Request) -> JSONResponse:
        daten = await request.body()
        try:
            datei = runtime.choreos.musik_ablegen(request.query_params.get("name", ""), daten)
        except ValueError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "datei": datei})

    @app.get("/api/musik/{datei}")
    async def musik_runter(datei: str):
        p = runtime.choreos.musik_pfad(datei)
        if p is None:
            return JSONResponse({"ok": False}, status_code=404)
        return FileResponse(p)

    @app.post("/api/choreo/plan")
    async def choreo_plan(request: Request) -> JSONResponse:
        body = await request.json()
        try:
            return JSONResponse({"ok": True, "choreo": C.plane(body.get("analyse") or {}, sorted(posen()),
                                                               reachy=art() == "reachy_mini")})
        except (TypeError, ValueError) as exc:
            return JSONResponse({"ok": False, "fehler": f"Analyse unlesbar: {exc}"}, status_code=400)

    @app.post("/api/choreo/speichern")
    async def choreo_speichern(request: Request) -> JSONResponse:
        body = await request.json()
        try:
            c = runtime.choreos.speichere(str(body.get("name", "")), body.get("choreo") or {}, str(body.get("musik", "")))
        except (ValueError, TypeError) as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "choreo": c})

    @app.delete("/api/choreo")
    async def choreo_loeschen(request: Request) -> JSONResponse:
        body = await request.json()
        return JSONResponse({"ok": runtime.choreos.loesche(str(body.get("name", "")))})

    @app.post("/api/choreo/ki")
    async def choreo_ki(request: Request) -> JSONResponse:
        """„Mit KI choreografieren“: das eingestellte Gehirn (Claude oder ein anderes Modell) bekommt die Teile des
        Stücks und die Tricks-Liste und speichert einen Tanz mit dem Werkzeug `choreo`. Läuft als normale Chat-Nachricht
        – sichtbar im Gespräch, mit denselben Regeln."""
        body = await request.json()
        if not runtime.agent.online:
            return JSONResponse({"ok": False, "fehler": "Dafür braucht es ein KI-Gehirn (Claude, anderes oder lokales Modell)."},
                                status_code=400)
        name = " ".join(str(body.get("name", "")).split())[:60] or "Neuer Tanz"
        musik = str(body.get("musik", ""))
        musik = musik if runtime.choreos.musik_pfad(musik) else ""
        c = body.get("choreo") or {}
        text = C.ki_auftrag_reachy(name, musik, C.pruefe(c)) if art() == "reachy_mini" else \
            C.ki_auftrag(name, musik, C.pruefe(c), sorted(posen()))
        spawn(runtime.chat(text, via="tanz"))
        return JSONResponse({"ok": True})

    @app.post("/api/gehoer")
    async def gehoer(request: Request) -> JSONResponse:
        """Tanzen nach Gehör: start | messung {bpm, schlag_vor_s, energie} | stopp. Vom Mikrofon kommen nur diese Zahlen –
        das Audio bleibt im Browser. `ruhig` beim Start: Reachy wippt nur mit (Abschnitt „Mitwippen“, Musik oder Radio)."""
        body = await request.json()
        aktion = body.get("aktion")
        runner = runtime.runner
        if aktion == "start":
            r = await runner.run("choreo", {"aktion": "gehoer", "ruhig": bool(body.get("ruhig"))})
            r.pop("_wake", None)
            return JSONResponse(r)
        tanz = getattr(runner, "gehoer", None)
        laeuft = tanz is not None and runtime.engine.current is tanz and not tanz.done
        if aktion == "messung":
            if not laeuft:
                return JSONResponse({"ok": False, "laeuft": False})
            try:
                tanz.hoeren(float(body.get("bpm") or 110), float(body.get("schlag_vor_s") or 0), float(body.get("energie") or 0))
            except (TypeError, ValueError):
                return JSONResponse({"ok": False, "fehler": "Messung unlesbar"}, status_code=400)
            return JSONResponse({"ok": True, "laeuft": True})
        if aktion == "stopp":
            if laeuft:
                await runtime.engine.stop_all("Tanzen nach Gehör beendet")
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "fehler": "unbekannte Aktion"}, status_code=400)

    @app.post("/api/choreo/stopp")
    async def choreo_stopp() -> JSONResponse:
        """Tanz und Musik anhalten (seit 0.38.34) – ausdrücklich kein Not-Aus: keine Sperre, sie bleibt stehen."""
        return JSONResponse(await runtime.runner.run("choreo", {"aktion": "stopp"}))

    @app.post("/api/choreo/tanzen")
    async def choreo_tanzen(request: Request) -> JSONResponse:
        """Einen gespeicherten Tanz tanzen – oder einen ungespeicherten (Probe aus dem Editor). Läuft über dasselbe
        Werkzeug wie bei Claude, also mit allen Sicherheitsregeln (steht sie nicht, startet nichts)."""
        body = await request.json()
        ab = max(0.0, float(body.get("ab") or 0.0))
        args = {"aktion": "tanzen", "name": str(body.get("name", "")), "ab": ab}
        if body.get("choreo"):
            c = C.pruefe(body["choreo"])
            if not c["schritte"]:
                return JSONResponse({"ok": False, "fehler": "Keine Schritte"}, status_code=400)
            args = {"aktion": "tanzen", "name": "Probe", "_choreo": c, "ab": ab}
        r = await runtime.runner.run("choreo", args)
        r.pop("_wake", None)
        return JSONResponse(r)
