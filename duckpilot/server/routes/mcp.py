"""MCP-Zugang für andere Programme (nur am PC, mit Zugangsschlüssel, abschaltbar) und seine Verwaltung."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from ... import mcp_server as M
from ..runtime import Runtime
from ..security import _is_remote, origin_allowed


def register(app: FastAPI, runtime: Runtime) -> None:
    server = M.McpServer(runtime)

    def _refuse(request: Request) -> JSONResponse | None:
        if not runtime.config.mcp:
            return JSONResponse({"error": "MCP-Zugang ist aus – System → Einstellungen → Claude"}, status_code=404)
        if _is_remote(request):
            return JSONResponse({"error": "Nur am PC."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and not origin_allowed(origin, request.headers.get("host")):
            return JSONResponse({"error": "Fremde Herkunft."}, status_code=403)    # Schutz vor DNS-Rebinding
        if not M.token_ok(request.headers.get("authorization")):
            return JSONResponse({"error": "Zugangsschlüssel fehlt oder falsch."}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
        return None

    @app.post("/mcp")
    async def mcp_post(request: Request) -> Response:
        if (refused := _refuse(request)) is not None:
            return refused
        try:
            body = json.loads(await request.body())
        except ValueError:
            return JSONResponse(M._error(None, -32700, "Kein gültiges JSON"), status_code=400)
        batch = body if isinstance(body, list) else [body]
        answers = [a for a in [await server.handle(m) for m in batch] if a is not None]
        headers = {}
        if any(isinstance(m, dict) and m.get("method") == "initialize" for m in batch):
            headers["Mcp-Session-Id"] = M.session_id()
        if not answers:
            return Response(status_code=202, headers=headers)
        return JSONResponse(answers if isinstance(body, list) else answers[0], headers=headers)

    @app.get("/mcp")
    async def mcp_get(request: Request) -> Response:
        if (refused := _refuse(request)) is not None:
            return refused
        return Response(status_code=405, headers={"Allow": "POST"})       # kein Server-Stream nötig

    @app.delete("/mcp")
    async def mcp_delete(request: Request) -> Response:
        if (refused := _refuse(request)) is not None:
            return refused
        return Response(status_code=204)

    # ── Verwaltung in den Einstellungen ──────────────────────────────────────
    def _info(token_once: str | None = None) -> dict:
        port = runtime.config.port
        url = f"http://127.0.0.1:{port}/mcp"
        code_dir = str(Path(__file__).resolve().parents[3])
        python = sys.executable.replace("pythonw.exe", "python.exe")     # Claude Desktop spricht über stdin/stdout
        desktop = {"mcpServers": {"duckpilot": {"command": python, "args": ["-m", "duckpilot.mcp_bridge"],
                                                  "cwd": code_dir}}}
        token = M.get_token()
        return {"an": runtime.config.mcp, "adresse": url, "schluessel": M.token_hint(token),
                "neuer_schluessel": token_once, "aufrufe": server.calls,
                "werkzeuge": [t["name"] for t in server.tools()],
                "claude_desktop": json.dumps(desktop, indent=2, ensure_ascii=False),
                "claude_code": f'claude mcp add --transport http duckpilot {url} --header "Authorization: Bearer '
                               f'{token_once or "<Schlüssel>"}"'}

    @app.get("/api/mcp")
    async def mcp_info() -> JSONResponse:
        return JSONResponse(_info())

    @app.post("/api/mcp/schluessel")
    async def mcp_new_key() -> JSONResponse:
        try:
            token = M.new_token()
        except RuntimeError as exc:
            return JSONResponse({"ok": False, "fehler": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, **_info(token_once=token)})
