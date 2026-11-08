"""Tailscale für die Handy-Fernbedienung: https-Adresse im eigenen privaten Netz (auch unterwegs).

Tailscale verbindet die eigenen Geräte zu einem privaten Netz. „Tailscale Serve“ stellt einen Dienst auf
diesem PC unter https://<gerät>.<tailnet>.ts.net bereit – mit echtem Zertifikat. Damit erlaubt der Handy-
Browser auch das Mikrofon, und die Ente ist von unterwegs erreichbar. Nach außen ins Internet geht dabei
nichts (das wäre „Funnel“, den duckpilot nie einschaltet).

duckpilot ruft nur das Tailscale-Programm auf (feste Befehle, keine freien Eingaben). Wer über Tailscale
kommt, muss trotzdem gekoppelt sein – wie im WLAN.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any

log = logging.getLogger(__name__)

_cache: dict[str, Any] = {"t": 0.0, "wert": None}
LINK_RE = re.compile(r"https://login\.tailscale\.com/\S+")


def cli() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
            p = os.path.join(base, "Tailscale", "tailscale.exe") if base else ""
            if p and os.path.exists(p):
                return p
    if sys.platform == "darwin" and os.path.exists("/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        return "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    return None


def _run(args: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess:
    exe = cli()
    if not exe:
        raise FileNotFoundError("Tailscale ist auf diesem PC nicht installiert")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, creationflags=flags,
                          stdin=subprocess.DEVNULL)


def status(fresh: bool = False) -> dict[str, Any]:
    """Ist Tailscale da, angemeldet, und wie heißt dieser PC im privaten Netz?"""
    now = time.monotonic()
    if not fresh and _cache["wert"] is not None and now - _cache["t"] < 10:
        return _cache["wert"]
    out: dict[str, Any] = {"installiert": cli() is not None, "laeuft": False, "name": None, "https": False,
                           "fehler": None}
    if out["installiert"]:
        try:
            r = _run(["status", "--json"], timeout=8)
            data = json.loads(r.stdout or "{}")
            out["laeuft"] = data.get("BackendState") == "Running"
            me = data.get("Self") or {}
            name = str(me.get("DNSName") or "").rstrip(".")
            out["name"] = name if name.endswith(".ts.net") else None
            out["https"] = bool(data.get("CertDomains"))
            if not out["laeuft"]:
                out["fehler"] = "Tailscale ist nicht angemeldet – in der Tailscale-App anmelden."
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            out["fehler"] = f"Tailscale antwortet nicht ({type(exc).__name__})."
    _cache.update(t=now, wert=out)
    return out


def serve_target(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}"


def serve_active(port: int) -> bool:
    """Leitet Tailscale Serve https://<name>.ts.net schon auf duckpilot weiter?"""
    try:
        r = _run(["serve", "status", "--json"], timeout=8)
        return serve_target(port) in (r.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return False


def serve_on(port: int) -> dict[str, Any]:
    """https://<name>.ts.net → duckpilot auf diesem PC (nur im eigenen Tailnet, nie ins Internet)."""
    try:
        r = _run(["serve", "--bg", "--https=443", serve_target(port)], timeout=25)
    except subprocess.TimeoutExpired as exc:
        text = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        link = LINK_RE.search(text)
        return {"ok": False, "link": link.group(0) if link else None,
                "fehler": "Tailscale wartet auf eine Bestätigung – den Link öffnen und HTTPS erlauben, dann erneut."}
    except OSError as exc:
        return {"ok": False, "fehler": str(exc)}
    text = f"{r.stdout}\n{r.stderr}"
    link = LINK_RE.search(text)
    _cache["wert"] = None
    if r.returncode != 0 or (link and not serve_active(port)):
        return {"ok": False, "link": link.group(0) if link else None,
                "fehler": ("In deinem Tailnet sind HTTPS-Zertifikate noch aus – den Link öffnen, erlauben, dann erneut "
                           "einrichten.") if link else (text.strip()[:200] or "Tailscale Serve ließ sich nicht einschalten.")}
    return {"ok": True}


def serve_off() -> dict[str, Any]:
    try:
        r = _run(["serve", "--https=443", "off"], timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "fehler": str(exc)}
    _cache["wert"] = None
    return {"ok": r.returncode == 0, "fehler": None if r.returncode == 0 else (r.stderr or r.stdout).strip()[:200]}
