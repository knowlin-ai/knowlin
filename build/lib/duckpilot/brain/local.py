"""Das eigene Sprachmodell der Ente – lokal auf dem PC über Ollama.

Für alles, was ohne Internet gehen soll, oder einfach zum Plaudern ohne API-Kosten:
Ein offenes Modell (z. B. Qwen 3.5 oder Gemma 4) läuft in Ollama auf der Grafikkarte
und bekommt dieselbe Persönlichkeit, denselben Kontext und dasselbe Gedächtnis wie
Claude – was die Ente mit Claude gelernt hat (Tricks, Wissen, Vorlieben), weiß sie
also auch hier. Bewegen kann sie sich mit einer Auswahl der Werkzeuge.

Ollama: https://ollama.com – nach der Installation läuft es im Hintergrund auf
http://127.0.0.1:11434. Modelle lädt man mit `ollama pull …` oder hier in duckpilot.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import DuckAgent, Notify, Reply

log = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:11434"
SUGGESTED = {
    "qwen3.5:9b": "Qwen 3.5, 9 Mrd. – gutes Deutsch, Werkzeuge (≈ 6 GB)",
    "gemma4:12b": "Gemma 4, 12 Mrd. – natürlich im Gespräch (≈ 8 GB)",
    "qwen3:14b": "Qwen 3, 14 Mrd. – gründlicher, etwas langsamer (≈ 9 GB)",
    "ministral-3:14b": "Ministral 3, 14 Mrd. – europäisch, Werkzeuge (≈ 9 GB)",
}
# Kleinere Modelle verlaufen sich in 30 Werkzeugen – die wichtigsten reichen.
LOCAL_TOOLS = {
    "walk", "turn", "go_to", "approach", "umrunden", "head", "look_around", "skill", "sound", "emote", "dance", "explore", "laser_folgen", "mir_folgen",
    "choreography", "pause", "power", "remember", "do_trick", "go_to_place", "forget", "trick_feedback",
    "set_goofy", "stop", "get_status", "parcours_bauen", "parcours_testen", "bewegung_ueben",
}
LOCAL_NOTE = """
- Du läufst gerade als lokales Sprachmodell auf dem PC (ohne Internet). Bleib bei kurzen, freundlichen Antworten \
und nimm Werkzeuge nur, wenn der Mensch etwas Bewegtes möchte. Erfinde keine Werkzeuge."""
THINK = re.compile(r"<think>.*?</think>", re.S)


def _tool_spec(t: dict[str, Any]) -> dict[str, Any]:
    desc = str(t.get("description", ""))
    if len(desc) > 400:
        desc = desc[:397] + "…"
    return {"type": "function", "function": {"name": t["name"], "description": desc, "parameters": t["input_schema"]}}


class LocalBrain:
    def __init__(self, agent: "DuckAgent", url: str = DEFAULT_URL, model: str = "") -> None:
        self.agent = agent
        self.url = (url or DEFAULT_URL).rstrip("/")
        self.model = model
        self.history: list[dict[str, Any]] = []
        self.last_error: str | None = None
        self.max_rounds = 4

    @property
    def configured(self) -> bool:
        return bool(self.model)

    def reset(self) -> None:
        self.history.clear()

    async def _post(self, path: str, body: dict[str, Any], timeout: float = 180.0) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=3.0)) as client:
            r = await client.post(f"{self.url}{path}", json=body)
            if r.status_code == 404 and path == "/api/chat":
                raise RuntimeError(f"Modell „{self.model}“ fehlt in Ollama – erst laden (ollama pull {self.model})")
            r.raise_for_status()
            return r.json()

    async def handle(self, text: str, notify: "Notify | None" = None) -> "Reply":
        from .agent import Reply

        t0 = time.monotonic()
        runner = self.agent.runner
        erlaubt = getattr(self.agent, "local_tools", LOCAL_TOOLS)     # der Kopf hat eigene (seit 0.38.8)
        tools = [_tool_spec(t) for t in runner.tools() if t["name"] in erlaubt]
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.agent._system() + LOCAL_NOTE}]
        messages += self.history[-16:]
        user = {"role": "user", "content": f"{text}\n\n{self.agent._context(text)}"}
        messages.append(user)
        actions: list[dict[str, Any]] = []
        final = ""
        for _ in range(self.max_rounds):
            data = await self._post("/api/chat", {
                "model": self.model, "messages": messages, "tools": tools, "stream": False, "think": False,
                "options": {"num_ctx": 16384, "temperature": 0.7},
            })
            msg = data.get("message") or {}
            content = THINK.sub("", str(msg.get("content") or "")).strip()
            if content:
                final = content
            calls = msg.get("tool_calls") or []
            messages.append({"role": "assistant", "content": content, **({"tool_calls": calls} if calls else {})})
            if not calls:
                break
            for c in calls[:6]:
                fn = c.get("function") or {}
                name = str(fn.get("name") or "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                if name not in erlaubt:
                    result = {"ok": False, "fehler": f"Werkzeug {name} gibt es hier nicht"}
                else:
                    result = await runner.run(name, args if isinstance(args, dict) else {})
                action = {"tool": name, "input": args, "result": result}
                actions.append(action)
                if notify:
                    maybe = notify({"type": "action", **action})
                    if maybe is not None:
                        await maybe
                if isinstance(result, dict) and result.pop("_bild", None) is not None:
                    result["hinweis"] = "Das Bild kann nur Claude ansehen, nicht das eigene Sprachmodell."
                messages.append({"role": "tool", "tool_name": name, "content": json.dumps(result, ensure_ascii=False)})
        final = final or "Quak!"
        # Für den Verlauf nur Frage und Antwort – das hält den Kontext klein
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": final}]
        self.history = self.history[-16:]
        self.last_error = None
        return Reply(final, actions, "lokal", time.monotonic() - t0)

    async def status(self) -> dict[str, Any]:
        """Läuft Ollama, welche Modelle sind da?"""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(4.0, connect=2.0)) as client:
                r = await client.get(f"{self.url}/api/tags")
                r.raise_for_status()
                models = [m.get("name") for m in r.json().get("models", []) if m.get("name")]
            return {"laeuft": True, "modelle": models, "adresse": self.url}
        except Exception as exc:
            return {"laeuft": False, "modelle": [], "adresse": self.url, "fehler": f"{type(exc).__name__}"}

    async def pull(self, model: str, progress) -> None:
        """Ein Modell in Ollama laden (Fortschritt 0…1 über `progress`)."""
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=3.0)) as client:
            async with client.stream("POST", f"{self.url}/api/pull", json={"model": model, "stream": True}) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("error"):
                        raise RuntimeError(ev["error"])
                    total, done = ev.get("total"), ev.get("completed")
                    progress(ev.get("status", ""), (done / total) if total and done else None)
