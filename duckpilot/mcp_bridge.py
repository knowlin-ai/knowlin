"""stdio-Brücke zum MCP-Zugang von duckpilot – für Programme, die MCP-Server nur als Befehl starten (Claude Desktop).

    python -m duckpilot.mcp_bridge

Liest JSON-RPC-Zeilen von stdin, reicht sie an `http://127.0.0.1:<port>/mcp` weiter und schreibt die Antworten nach
stdout. Den Zugangsschlüssel holt sie selbst aus dem Tresor des Betriebssystems – in der Konfigurationsdatei von
Claude Desktop steht er nicht. duckpilot muss laufen, und unter System → Einstellungen muss der MCP-Zugang an sein.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable

Post = Callable[[bytes], tuple[int, str]]


def relay(line: str, post: Post) -> str | None:
    """Eine Zeile weiterreichen; Antwort-Zeile oder None (Benachrichtigung)."""
    line = line.strip()
    if not line:
        return None
    try:
        msg = json.loads(line)
    except ValueError:
        return json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Kein gültiges JSON"}})
    mid = msg.get("id") if isinstance(msg, dict) else None
    try:
        status, text = post(line.encode("utf-8"))
    except OSError as exc:
        if mid is None:
            return None
        why = ("duckpilot läuft nicht oder der MCP-Zugang ist aus – duckpilot starten und unter System → "
               f"Einstellungen → Claude „Andere Programme dürfen steuern (MCP)“ einschalten ({exc})")
        return json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": why}}, ensure_ascii=False)
    if status == 202 or not text.strip():
        return None
    if status >= 400 and mid is not None:
        try:
            why = json.loads(text).get("error") or text
        except ValueError:
            why = text
        return json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": f"duckpilot: {why}"}},
                          ensure_ascii=False)
    return text


def http_post(url: str, token: str | None) -> Post:
    def post(body: bytes) -> tuple[int, str]:
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            **({"Authorization": f"Bearer {token}"} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
    return post


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--hilfe" in argv or "--help" in argv:
        print(__doc__)
        return 0
    from . import mcp_server as M
    from .config import load

    cfg = load()
    host = "127.0.0.1" if cfg.host in ("0.0.0.0", "::") else cfg.host
    post = http_post(f"http://{host}:{cfg.port}/mcp", M.get_token())
    for line in sys.stdin:
        out = relay(line, post)
        if out is not None:
            sys.stdout.write(out.replace("\n", " ") + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
