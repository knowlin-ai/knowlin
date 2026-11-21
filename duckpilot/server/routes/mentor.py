"""Mentor 2 (seit 0.41): das Vorgemachte ansehen, als Auftrag merken oder verwerfen (`mentor_auftrag.py`).

Auch vom Handy (über die sichere Adresse mit Kamera): ein Auftrag ist nur Daten – Würfel und Ziele, nichts über
Personen, keine Bilder.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ... import mentor_ziele as MZ
from ... import settings as S
from ... import werkbank_auftrag as WA
from ..runtime import Runtime
from ..security import _json_body


def _ueberblick(runtime: Runtime) -> dict:
    """Mentor als Modul (seit 0.48): eigene Lernziele, Gelerntes mit echten Zahlen, Übungen."""
    ari = getattr(runtime, "ari_schule", None)
    bello = getattr(runtime, "bello_schule", None)
    mar = getattr(runtime, "marionette_dienst", None)
    try:
        ari_stand = ari.status() if ari is not None else None
    except Exception:  # noqa: BLE001 – ohne Ari-Daten bleibt der Überblick trotzdem
        ari_stand = None
    gelernt = MZ.gelernte_ziele(ari_stand, WA.eigene(), bello.stand() if bello is not None else None,
                                mar.bewegungen.alle_koerper() if mar is not None else {})
    st = runtime.backend.state()
    from ... import koerper as K

    liste = [{"id": k.koerper_zustand, "name": k.name} for k in K.alle() if k.simulator or k.eingebaut]
    return {"ok": True, "koerper_liste": liste, **MZ.ueberblick(MZ.Lernziele(S.data_dir()).alle(), gelernt,
                                       set(runtime.backend.eigenschaften()), str(getattr(st, "koerper", "")))}


def register(app: FastAPI, runtime: Runtime) -> None:
    ziele = MZ.Lernziele(S.data_dir())

    @app.get("/api/mentor")
    async def mentor() -> JSONResponse:
        return JSONResponse(_ueberblick(runtime))

    @app.post("/api/mentor/ziel")
    async def mentor_ziel(request: Request) -> JSONResponse:
        body = await _json_body(request)
        if body.get("id"):
            if not ziele.setzen(str(body["id"]), bool(body.get("erledigt"))):
                return JSONResponse({"ok": False, "fehler": "Nicht gefunden."}, status_code=404)
            return JSONResponse(_ueberblick(runtime))
        z, grund = ziele.neu(str(body.get("text") or ""), str(body.get("koerper") or ""))
        if z is None:
            return JSONResponse({"ok": False, "fehler": grund}, status_code=400)
        return JSONResponse(_ueberblick(runtime))

    @app.delete("/api/mentor/ziel/{zid}")
    async def mentor_ziel_weg(zid: str) -> JSONResponse:
        if not ziele.loeschen(zid):
            return JSONResponse({"ok": False, "fehler": "Nicht gefunden."}, status_code=404)
        return JSONResponse(_ueberblick(runtime))

    @app.get("/api/mentor/vorgemacht")
    async def vorgemacht() -> JSONResponse:
        return JSONResponse(runtime.mentor_vorgemacht())

    @app.post("/api/mentor/vorgemacht")
    async def vorgemacht_tun(request: Request) -> JSONResponse:
        body = await _json_body(request)
        beob = getattr(runtime, "mentor_beob", None)
        if body.get("aktion") == "verwerfen":
            if beob is not None:
                beob.leeren()
            return JSONResponse(runtime.mentor_vorgemacht())
        auftrag = beob.auftrag(str(body.get("titel") or "")) if beob is not None else None
        if auftrag is None:
            return JSONResponse({"ok": False, "fehler": "Noch nichts vorgemacht – greif einen Würfel und leg ihn ab."},
                                status_code=400)
        k, grund = WA.speichern(auftrag)
        if k is None:
            return JSONResponse({"ok": False, "fehler": grund}, status_code=400)
        beob.leeren()
        await runtime.broadcast(runtime.mentor_vorgemacht())
        return JSONResponse({"ok": True, "name": k, "titel": auftrag["titel"], "schritte": len(auftrag["schritte"])})
