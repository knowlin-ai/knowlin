"""NFC-Tags: Zuordnung Tag → Satz, Berührung melden (Handy über Web NFC, Probe-Knopf)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..runtime import Runtime
from ..security import _is_remote, _json_body


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/api/nfc")
    async def nfc_list() -> JSONResponse:
        return JSONResponse({"ok": True, **runtime.nfc.message()})

    @app.post("/api/nfc/tag")
    async def nfc_put(request: Request) -> JSONResponse:
        body = await _json_body(request)
        res = runtime.nfc.put(body.get("uid"), body.get("name"), body.get("satz"))
        if res.get("ok"):
            await runtime.broadcast(runtime.nfc.message())
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)

    @app.delete("/api/nfc/tag/{uid}")
    async def nfc_delete(uid: str) -> JSONResponse:
        ok = runtime.nfc.remove(uid)
        if ok:
            await runtime.broadcast(runtime.nfc.message())
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)

    @app.post("/api/nfc/beruehrt")
    async def nfc_touch(request: Request) -> JSONResponse:
        body = await _json_body(request)
        res = await runtime.nfc_touched(body.get("uid"), remote=_is_remote(request))
        return JSONResponse(res, status_code=200 if res.get("ok") else 400)
