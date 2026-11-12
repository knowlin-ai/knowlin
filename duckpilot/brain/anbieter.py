"""Andere KI-Modelle als Gehirn (seit 0.35) – für alle, die nicht Claude nutzen.

Ein Baustein für jede Schnittstelle im Stil von OpenAI (`/chat/completions` mit Werkzeugen): OpenAI selbst, Mistral,
OpenRouter, Google Gemini (dessen OpenAI-kompatible Adresse), LM Studio auf dem PC oder eine eigene Adresse. Ollama
bleibt eigens in `local.py` (dort lädt duckpilot auch Modelle).

Was gleich bleibt wie bei Claude: Persönlichkeit, Kontext, Gedächtnis, Werkzeuge – und vor allem die
Sicherheitsregeln. Die stecken nicht im Modell, sondern in den Werkzeugen und der Bewegungs-Engine (Not-Aus,
Gelenkgrenzen, Sturzreflex, Zwei-Klick fürs bezahlte Training). Kein Modell kann sie umgehen.

Schlüssel liegen wie der Claude-Schlüssel nur im Tresor des Systems (je Anbieter ein Eintrag), nie in einer Datei.
Fällt der Anbieter aus, übernehmen die einfachen Befehle ohne KI.
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

# id → (Name, Standard-Adresse, braucht Schlüssel)
ANBIETER: dict[str, tuple[str, str, bool]] = {
    "openai": ("OpenAI", "https://api.openai.com/v1", True),
    "gemini": ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", True),
    "mistral": ("Mistral", "https://api.mistral.ai/v1", True),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", True),
    "lmstudio": ("LM Studio (auf diesem PC)", "http://127.0.0.1:1234/v1", False),
    "eigen": ("Eigene Adresse (OpenAI-kompatibel)", "", False),
}
KEYRING_PREFIX = "anbieter_key_"
NOTE = """
- Du läufst gerade auf einem anderen KI-Modell als Claude. Bleib bei kurzen, freundlichen Antworten, nimm Werkzeuge \
nur, wenn der Mensch etwas Bewegtes oder Nachschlagbares möchte, und erfinde keine Werkzeuge."""
THINK = re.compile(r"<think>.*?</think>", re.S)
MAX_DESC = 1000


def adresse(anbieter: str, eigene: str = "") -> str:
    """Basisadresse eines Anbieters; für LM Studio und „eigen“ zählt die eingetragene Adresse."""
    name, std, _ = ANBIETER.get(anbieter, ANBIETER["openai"])
    return (eigene or std).rstrip("/") if anbieter in ("lmstudio", "eigen") else std


# Modelle, die eigens für Roboter gemacht sind (seit 0.38.46, Etappe G5): z. B. Googles „Gemini Robotics-ER“ – räumliches
# Denken über Bilder, Werkzeugaufrufe; in der Liste ganz oben. Mit Knowlins Werkzeugen noch nicht am echten Gerät geprüft.
ROBOTER_MODELLE = re.compile(r"robotics-er", re.I)


def fuer_roboter(modell: str) -> bool:
    return bool(ROBOTER_MODELLE.search(modell or ""))


def braucht_schluessel(anbieter: str) -> bool:
    return ANBIETER.get(anbieter, ("", "", True))[2]


def _tool_spec(t: dict[str, Any]) -> dict[str, Any]:
    desc = str(t.get("description", ""))
    if len(desc) > MAX_DESC:
        desc = desc[: MAX_DESC - 1] + "…"
    return {"type": "function", "function": {"name": t["name"], "description": desc, "parameters": t["input_schema"]}}


def grund_400(anbieter: str, antwort: str) -> str:
    """Verständlicher Satz zu „400 Bad Request“ – meist ist der Kontext des Modells zu klein (LM Studio: 4096)."""
    try:
        roh = json.loads(antwort)
        roh = roh.get("error", roh)
        roh = roh.get("message", roh) if isinstance(roh, dict) else roh
    except ValueError:
        roh = antwort
    roh = " ".join(str(roh).split())[:200]
    if any(k in roh.lower() for k in ("context", "token", "too long", "n_ctx", "exceed")):
        if anbieter == "lmstudio":
            return ("Das Modell in LM Studio hat zu wenig Kontext für Knowlin. In LM Studio beim Laden des Modells die "
                    f"Kontextlänge auf mindestens 16 384 stellen. ({roh})")
        return f"Die Anfrage ist zu lang für dieses Modell ({roh})"
    return f"Das Modell hat die Anfrage abgelehnt: {roh or 'ohne Begründung'}"


class AnbieterBrain:
    def __init__(self, agent: "DuckAgent", anbieter: str = "", modell: str = "", eigene_adresse: str = "",
                 schluessel: str | None = None) -> None:
        self.agent = agent
        self.anbieter = anbieter if anbieter in ANBIETER else ""
        self.modell = modell
        self.url = adresse(self.anbieter, eigene_adresse) if self.anbieter else ""
        self.schluessel = schluessel
        self.history: list[dict[str, Any]] = []
        self.last_error: str | None = None
        self.max_rounds = 5

    @property
    def configured(self) -> bool:
        return bool(self.anbieter and self.modell and self.url
                    and (self.schluessel or not braucht_schluessel(self.anbieter)))

    def reset(self) -> None:
        self.history.clear()

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.schluessel:
            h["Authorization"] = f"Bearer {self.schluessel}"
        if self.anbieter == "openrouter":
            h["X-Title"] = "duckpilot"
        return h

    async def _post(self, body: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5.0)) as client:
            r = await client.post(f"{self.url}/chat/completions", json=body, headers=self._headers())
            if r.status_code in (401, 403):
                raise RuntimeError("Schlüssel abgelehnt – bitte prüfen")
            if r.status_code == 404:
                raise RuntimeError(f"Modell „{self.modell}“ oder Adresse nicht gefunden")
            if r.status_code == 429:
                raise RuntimeError("zu viele Anfragen oder Guthaben aufgebraucht")
            if r.status_code == 400:
                # gemeldet 11.11. mit LM Studio: nur „400 Bad Request“ – jetzt mit dem Grund des Servers
                raise RuntimeError(grund_400(self.anbieter, r.text))
            r.raise_for_status()
            return r.json()

    async def modelle(self) -> list[str]:
        """Verfügbare Modelle des Anbieters (GET /models), alphabetisch – Modelle für Roboter zuerst (`fuer_roboter`)."""
        import httpx

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            try:
                r = await client.get(f"{self.url}/models", headers=self._headers())
            except httpx.ConnectError as exc:
                if self.anbieter == "lmstudio":
                    raise RuntimeError("LM Studio antwortet nicht – in LM Studio unter „Developer“ den lokalen Server "
                                       "starten (Port 1234) und ein Modell laden.") from exc
                raise RuntimeError(f"Keine Verbindung zu {self.url}") from exc
            if r.status_code in (401, 403):
                raise RuntimeError("Schlüssel abgelehnt – bitte prüfen")
            r.raise_for_status()
            daten = r.json().get("data") or []
        namen = {str(m.get("id", "")).removeprefix("models/") for m in daten if isinstance(m, dict) and m.get("id")}
        return sorted(namen, key=lambda n: (not fuer_roboter(n), n))

    async def handle(self, text: str, notify: "Notify | None" = None) -> "Reply":
        from .agent import Reply

        t0 = time.monotonic()
        runner = self.agent.runner
        alle = runner.tools()
        if self.anbieter == "lmstudio":
            # Modelle auf dem eigenen PC: kleine Auswahl wie bei Ollama – passt in den Kontext und verwirrt sie nicht
            from .local import LOCAL_TOOLS

            erlaubt = getattr(self.agent, "local_tools", LOCAL_TOOLS)
            alle = [t for t in alle if t["name"] in erlaubt]
        tools = [_tool_spec(t) for t in alle]
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.agent._system() + NOTE}]
        messages += self.history[-16:]
        messages.append({"role": "user", "content": f"{text}\n\n{self.agent._context(text)}"})
        actions: list[dict[str, Any]] = []
        final = ""
        for _ in range(self.max_rounds):
            data = await self._post({"model": self.modell, "messages": messages, "tools": tools,
                                     "temperature": 0.7, "max_tokens": 2048})
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            content = THINK.sub("", str(msg.get("content") or "")).strip()
            if content:
                final = content
            calls = msg.get("tool_calls") or []
            messages.append({"role": "assistant", "content": content or None,
                             **({"tool_calls": calls} if calls else {})})
            if not calls:
                break
            for c in calls[:6]:
                fn = c.get("function") or {}
                name = str(fn.get("name") or "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args) if args.strip() else {}
                    except ValueError:
                        args = {}
                known = {t["function"]["name"] for t in tools}
                if name not in known:
                    result: Any = {"ok": False, "fehler": f"Werkzeug {name} gibt es nicht"}
                else:
                    result = await runner.run(name, args if isinstance(args, dict) else {})
                action = {"tool": name, "input": args, "result": result}
                actions.append(action)
                if notify:
                    maybe = notify({"type": "action", **action})
                    if maybe is not None:
                        await maybe
                if isinstance(result, dict) and result.pop("_bild", None) is not None:
                    result["hinweis"] = "Das Bild kann gerade nur Claude ansehen."
                messages.append({"role": "tool", "tool_call_id": str(c.get("id") or name),
                                 "content": json.dumps(result, ensure_ascii=False, default=str)[:2500]})
        # als Text geschriebene Werkzeuge ausführen und aus der Antwort nehmen (wie beim lokalen Modell, seit 0.38.40)
        from .local import text_werkzeuge

        final, als_text = text_werkzeuge(final, {t["name"]: t["input_schema"] for t in alle})
        for name, args in als_text[:4]:
            result = await runner.run(name, args)
            action = {"tool": name, "input": args, "result": result}
            actions.append(action)
            if notify:
                maybe = notify({"type": "action", **action})
                if maybe is not None:
                    await maybe
        final = final or "Quak!"
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": final}]
        self.history = self.history[-16:]
        self.last_error = None
        return Reply(final, actions, "anbieter", time.monotonic() - t0)
