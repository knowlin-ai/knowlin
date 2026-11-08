"""Schutz: nur die eigene Oberfläche darf steuern – Herkunft, Host, Handys und Weiterleiter."""

from __future__ import annotations

import html
import ipaddress
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .. import remote as R

log = logging.getLogger(__name__)


# ── Schutz: nur die eigene Oberfläche darf steuern ─────────────────────────
_HOST_RE = re.compile(r"(localhost|[0-9.]{7,15}|\[[0-9A-Fa-f:.]{2,45}\]|[a-z0-9-]{1,40}\.local)(?::[0-9]{1,5})?")


def _host_ok(host_header: str | None) -> bool:
    """Host muss genau localhost oder eine IP (mit Port) sein – schützt vor DNS-Rebinding und vor
    zusammengebastelten Host-Zeilen wie „192.168.1.10/static/x“."""
    if not host_header:
        return False
    m = _HOST_RE.fullmatch(host_header)
    if not m:
        return False
    host = m.group(1)
    if host == "localhost":
        return True
    if host.endswith(".local"):
        from ..mdns import name_erlaubt

        return name_erlaubt(host)        # nur der Name, den dieser PC gerade selbst ansagt (knowlin.local, 0.38.28)
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def origin_allowed(origin: str | None, host_header: str | None, ts_ok: bool = False) -> bool:
    """Gleiche Herkunft: Origin (falls vorhanden) muss genau dieser Server sein.

    ts_ok: Name im eigenen Tailnet (*.ts.net) zulassen – nur wenn der Tailscale-Zugang an ist."""
    if not (ts_ok and R.ts_hostname(host_header)) and not _host_ok(host_header):
        return False
    if origin is None:
        return True  # kein Browser (z. B. Skript auf diesem PC) – darf ohnehin alles
    return origin in (f"http://{host_header}", f"https://{host_header}")


_NOT_PAIRED_PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Knowlin</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#161616;color:#f4f4f4;
font:16px/1.5 system-ui,sans-serif}}main{{max-width:28rem;padding:24px}}h1{{font-size:1.4rem;margin:0 0 .5rem}}
p{{color:#c6c6c6}}</style></head><body><main><h1>{title}</h1><p>{text}</p>{weiter}</main></body></html>"""


def _remote_page(title: str, text: str, status: int, link: tuple[str, str] | None = None) -> HTMLResponse:
    weiter = (f'<p><a href="{html.escape(link[0])}" style="color:#f1913c">{html.escape(link[1])}</a></p>' if link else "")
    return HTMLResponse(_NOT_PAIRED_PAGE.format(title=html.escape(title), text=html.escape(text), weiter=weiter),
                        status_code=status, headers={"Cache-Control": "no-store"})


class SameOriginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, remote: R.RemoteAccess | None = None) -> None:
        super().__init__(app)
        self.remote = remote

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host")
        # Tailscale Serve: Host ist der Name im eigenen Tailnet, die Verbindung kommt technisch von 127.0.0.1
        via_ts = bool(self.remote and self.remote.data.get("tailscale") and R.ts_hostname(host))
        if not via_ts and not _host_ok(host):
            return JSONResponse({"error": "unbekannter Host"}, status_code=403)
        client = request.client.host if request.client else None
        path = request.scope.get("path", "")   # genau der Pfad, den auch der Router nimmt
        if via_ts and not R.is_local(client):
            return JSONResponse({"error": "unbekannter Host"}, status_code=403)   # ts.net-Namen nur über Serve
        # über einen Weiterleiter auf diesem PC (Tailscale, andere Proxys) zählt nie als „der PC selbst“
        fremd = via_ts or not R.is_local(client) or R.proxied(request.headers)
        request.state.remote = fremd
        if fremd:
            verdict = (403, "Nur am PC erreichbar.") if self.remote is None else self.remote.check(
                client, request.cookies.get(R.COOKIE), request.method, path, via_tailscale=via_ts)
            if verdict is None and not via_ts and R.is_local(client):
                verdict = (403, "Über einen Weiterleiter nicht erreichbar.")
            if verdict is None and request.method not in ("GET", "HEAD", "OPTIONS") and not request.headers.get("origin"):
                verdict = (403, "Fremde Herkunft.")          # vom Handy nur aus dem Browser, nie ohne Herkunft
            if verdict is None and request.headers.get("sec-fetch-site") in ("same-site", "cross-site") \
                    and path.startswith("/api/"):
                verdict = (403, "Fremde Herkunft.")          # andere Dienste auf derselben PC-Adresse (anderer Port)
            if verdict is not None:
                code, why = verdict
                if path.startswith("/api/"):
                    return JSONResponse({"ok": False, "error": why, "fehler": why, "nur_pc": code == 403 and R.pc_only(request.method, path)},
                                        status_code=code)
                hint = ("Am PC auf der Startseite unter „Auf Handy oder Tablet“ einen Code anzeigen und den QR-Code "
                        "scannen – oder hier den kurzen Code eintippen.") if code == 401 else ""
                return _remote_page(why, hint or "Knowlin läuft auf deinem PC.", code, link=("/koppeln", "Code eintippen")
                                    if code == 401 else None)
        if request.method not in ("GET", "HEAD", "OPTIONS") and not origin_allowed(request.headers.get("origin"), host, via_ts):
            return JSONResponse({"error": "fremde Herkunft"}, status_code=403)
        if path.startswith("/api/") and request.headers.get("sec-fetch-site") == "cross-site":
            # auch Abrufe (GET) mit Nebenwirkung, etwa Lernkurven vom Hub holen, nur aus der eigenen Oberfläche
            return JSONResponse({"error": "fremde Herkunft"}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            # nach einem Update nie alte Skripte aus dem Browser-Cache mit neuer Seite mischen (kostet lokal nichts:
            # der Browser fragt nach und bekommt bei Gleichstand nur „304 unverändert“)
            response.headers["Cache-Control"] = "no-cache"
        return response


def _open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _is_remote(request: Request) -> bool:
    """Kam die Anfrage nicht vom PC selbst (Handy im WLAN, über Tailscale oder einen anderen Weiterleiter)?"""
    st = getattr(request.state, "remote", None)
    if st is not None:
        return bool(st)
    client = request.client.host if request.client else None
    return not R.is_local(client) or R.proxied(request.headers)


async def _json_body(request: Request) -> dict[str, Any]:
    """JSON-Körper als dict – kaputtes oder anderes JSON wird zu {}."""
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}
