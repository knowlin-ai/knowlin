"""Handy koppeln: Seite mit Code-Eingabe."""

from __future__ import annotations

import html
import logging
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import remote as R
from ..runtime import (
    Runtime,
)
from ..security import _remote_page

log = logging.getLogger(__name__)


def register(app: FastAPI, runtime: Runtime) -> None:
    @app.get("/koppeln")
    async def pair_page(request: Request, c: str = "") -> HTMLResponse:
        if c and not runtime.remote.code_valid(c):
            return _remote_page("Der Code ist abgelaufen oder ungültig.",
                                "Am PC auf der Startseite (Auf Handy oder Tablet) einen neuen Code anzeigen.", 400)
        name = R.device_name(request.headers.get("user-agent"))
        # ohne Code in der Adresse (knowlin.local oder von Hand eingetippt, seit 0.38.28): den kurzen Code eintippen
        code_feld = (f'<input type="hidden" name="c" value="{html.escape(c)}">' if c else
                     '<label for="c">Code vom PC</label><input id="c" name="c" maxlength="9" required autocomplete="one-time-code" '
                     'autocapitalize="characters" spellcheck="false" placeholder="z. B. K7P-2QM" style="letter-spacing:.15em">')
        page = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Gerät koppeln – Knowlin</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#161616;color:#f4f4f4;
font:16px/1.5 system-ui,sans-serif}}main{{width:min(26rem,100% - 32px)}}h1{{font-size:1.4rem;margin:0 0 .25rem}}
p{{color:#c6c6c6;margin:0 0 1.25rem}}label{{display:block;font-size:.875rem;color:#c6c6c6;margin-bottom:.25rem}}
input{{box-sizing:border-box;width:100%;font:inherit;padding:12px;background:#262626;color:#f4f4f4;border:0;
border-bottom:1px solid #8d8d8d;margin-bottom:1.25rem}}button{{width:100%;font:inherit;padding:14px;border:0;
background:#f1913c;color:#161616;font-weight:600;cursor:pointer}}</style></head><body><main>
<h1>Dieses Gerät koppeln</h1><p>Danach bedienst du Knowlin von hier aus – solange es im selben WLAN ist wie der PC.</p>
<form method="post" action="/koppeln">{code_feld}
<label for="n">Name des Geräts</label><input id="n" name="name" maxlength="40" value="{html.escape(name)}">
<button type="submit">Koppeln</button></form></main></body></html>"""
        return HTMLResponse(page, headers={"Cache-Control": "no-store", "Referrer-Policy": "same-origin"})

    @app.post("/koppeln")
    async def pair_submit(request: Request):
        raw = (await request.body())[:2000].decode("utf-8", "replace")
        form = parse_qs(raw)
        code = (form.get("c") or [""])[0]
        name = (form.get("name") or [""])[0] or R.device_name(request.headers.get("user-agent"))
        client = request.client.host if request.client else None
        via_ts = bool(runtime.remote.data.get("tailscale") and R.ts_hostname(request.headers.get("host")))
        try:
            token = runtime.remote.pair(code, name, "über Tailscale" if via_ts else client)
        except PermissionError as exc:
            return _remote_page("Koppeln hat nicht geklappt", str(exc), 403, link=("/koppeln", "Nochmal versuchen"))
        await runtime.broadcast_local({"type": "fernzugang", **runtime.remote_message()})
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(R.COOKIE, token, max_age=365 * 24 * 3600, httponly=True, samesite="lax", path="/",
                        secure=via_ts)                     # über Tailscale immer https
        return resp
