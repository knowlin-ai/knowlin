"""duckpilot als MCP-Server: andere Programme (Claude Desktop, Claude Code, eigene Agenten) steuern die Ente.

Model Context Protocol, Transport „Streamable HTTP“ ohne Streaming: `POST /mcp` mit JSON-RPC, Antwort als JSON.
Nur am PC (nie vom Handy, nie über Tailscale oder einen Weiterleiter), nur mit Zugangsschlüssel, nur wenn unter
System → Einstellungen eingeschaltet. Für Programme, die nur stdio können (Claude Desktop), gibt es die Brücke
`python -m duckpilot.mcp_bridge` – sie holt den Schlüssel selbst aus dem Tresor, er steht in keiner Konfigurationsdatei.

Jeder Aufruf geht durch dieselben Werkzeuge wie Claude in duckpilot – mit allen Sicherheitsregeln (Not-Aus gewinnt,
120 s Sperre, Aufstehen nach Sturz erst nach dem Stopp-Fenster). Personen, Kamerabilder, Gedächtnis-Einträge, Training und
Einstellungen gibt es über MCP nicht. Jeder Aufruf erscheint in der Oberfläche als „Von außen (MCP): …“.
"""

from __future__ import annotations

import hmac
import json
import logging
import secrets
import uuid
from typing import TYPE_CHECKING, Any

from . import __version__

if TYPE_CHECKING:  # pragma: no cover
    from .server.runtime import Runtime

log = logging.getLogger(__name__)

KEYRING_USER = "mcp-zugang"
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
# Was andere Programme dürfen: bewegen, ausdrücken, Tricks, Status. Bewusst nicht: Gedächtnis schreiben, Training,
# Alltag/Personen, Kamera, Einstellungen.
ALLOWED = ("get_status", "walk", "turn", "drive", "go_to", "approach", "head", "look_around", "skill", "sound",
           "emote", "dance", "explore", "laser_folgen", "mir_folgen", "choreography", "pause", "wait", "power", "stop",
           "kopf_ruhig", "do_trick", "go_to_place", "recall")
INSTRUCTIONS = ("Steuert eine Microduck (kleiner zweibeiniger Entenroboter von Pollen Robotics) über duckpilot – im "
                "Simulator oder am echten Roboter. Erst get_status, dann bewegen. `stop` hält sofort an. Nach einem "
                "Not-Aus steht sie mindestens 2 Minuten lang nicht von selbst auf. Am echten Roboter: kurze Strecken, mäßiges Tempo.")


# ── Zugangsschlüssel im Tresor ───────────────────────────────────────────────
def get_token() -> str | None:
    from . import settings as S

    kr = S._keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(S.KEYRING_SERVICE, KEYRING_USER) or None
    except Exception:
        return None


def new_token() -> str:
    """Neuen Schlüssel erzeugen und im Tresor ablegen (der alte gilt danach nicht mehr)."""
    from . import settings as S

    kr = S._keyring()
    if kr is None:
        raise RuntimeError("Kein Tresor verfügbar – ohne ihn gibt es keinen MCP-Zugang.")
    token = "dp_" + secrets.token_urlsafe(32)
    kr.set_password(S.KEYRING_SERVICE, KEYRING_USER, token)
    return token


def ensure_token() -> str:
    return get_token() or new_token()


def token_ok(header: str | None) -> bool:
    token = get_token()
    if not token or not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:].strip().encode(), token.encode())


def token_hint(token: str | None) -> str | None:
    return f"dp_…{token[-4:]}" if token else None


# ── JSON-RPC ─────────────────────────────────────────────────────────────────
def _error(mid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _result(mid: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


class McpServer:
    def __init__(self, rt: "Runtime") -> None:
        self.rt = rt
        self.calls = 0

    def tools(self) -> list[dict[str, Any]]:
        out = []
        for t in self.rt.runner.tools():
            if t["name"] not in ALLOWED:
                continue
            schema = json.loads(json.dumps(t["input_schema"]))
            schema.setdefault("properties", {})
            out.append({"name": t["name"], "description": t["description"], "inputSchema": schema})
        return out

    async def handle(self, msg: Any) -> dict[str, Any] | None:
        """Eine JSON-RPC-Nachricht beantworten; None bei Benachrichtigungen (ohne id)."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Ungültige Anfrage")
        method, mid, params = msg["method"], msg.get("id"), msg.get("params") or {}
        if "id" not in msg:
            return None                                   # notifications/initialized u. Ä.
        if method == "initialize":
            asked = str(params.get("protocolVersion") or "")
            version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return _result(mid, {"protocolVersion": version,
                                 "capabilities": {"tools": {"listChanged": False}},
                                 "serverInfo": {"name": "duckpilot", "title": "duckpilot – Microduck",
                                                "version": __version__},
                                 "instructions": INSTRUCTIONS})
        if method == "ping":
            return _result(mid, {})
        if method == "tools/list":
            return _result(mid, {"tools": self.tools()})
        if method == "tools/call":
            return _result(mid, await self.call(str(params.get("name") or ""), params.get("arguments") or {}))
        return _error(mid, -32601, f"Unbekannte Methode {method}")

    async def call(self, name: str, args: Any) -> dict[str, Any]:
        if name not in ALLOWED or name not in {t["name"] for t in self.rt.runner.tools()}:
            return {"content": [{"type": "text", "text": f"Werkzeug {name!r} gibt es über MCP nicht."}], "isError": True}
        if not isinstance(args, dict):
            return {"content": [{"type": "text", "text": "arguments muss ein Objekt sein."}], "isError": True}
        self.calls += 1
        self.rt.engine.note({"type": "mcp", "message": f"Von außen (MCP): {name}"})
        if name not in ("stop", "get_status", "recall", "wait"):
            self.rt.alltag.touch()                        # wie ein Befehl aus dem Fenster: weckt sie auf
        result = await self.rt.runner.run(name, args)
        if isinstance(result, dict):
            result.pop("_bild", None)                     # Bilder nie nach außen
        bad = isinstance(result, dict) and result.get("ok") is False
        await self.rt.broadcast({"type": "action", "tool": name, "input": args, "result": result, "via": "mcp"})
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}],
                "isError": bool(bad)}


def session_id() -> str:
    return uuid.uuid4().hex
