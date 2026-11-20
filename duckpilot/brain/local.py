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
    # seit 0.38.66 (Fund 15.11.: „mit Claude war es besser – auch beim Ballspielen“): Ball, Dinge und die anderen Enten.
    # Ohne diese Werkzeuge konnte das eigene Modell „schieß mir den Ball zu“ gar nicht ausführen – dann sprang die
    # Absicherung ein und hängte jedes Mal „Jetzt mache ich es wirklich.“ an.
    "schiessen", "apportieren", "handeln", "team", "enten", "karte", "wo_gesehen", "pollen_bewegung",
    "tagesrueckblick", "weltbild", "licht", "wetter",  # Erfahrungsnetz 2, LEDs (0.39), Wetter (0.40)
}
LOCAL_NOTE = """
- Du läufst gerade als lokales Sprachmodell auf dem PC (ohne Internet). Bleib bei kurzen, freundlichen Antworten \
(meist ein bis zwei Sätze – alles wird vorgelesen) und nimm Werkzeuge nur, wenn der Mensch etwas Bewegtes möchte. \
Erfinde keine Werkzeuge.
- Schreib keine Befehle in eckigen Klammern in deine Antwort – Bewegungen und Gefühle nur über die Werkzeuge."""
THINK = re.compile(r"<think>.*?</think>", re.S)
# Schneller antworten (seit 0.46.2, Hinweis des Maintainers: „Die App läuft teilweise träge. Auch das Sprechen ist super
# langsam“): Ollama wirft ein Modell nach 5 min ohne Anfrage aus dem Speicher – die nächste Antwort wartet dann viele
# Sekunden aufs Neuladen. Es bleibt jetzt 30 min geladen. Alle Anfragen nutzen dieselben Optionen: ein anderes
# `num_ctx` (z. B. beim Übersetzen der Stimmbeschreibung) lädt das Modell sonst ebenfalls neu.
# `num_predict` begrenzt ausufernde Antworten: alles, was geschrieben wird, muss danach auch vorgelesen werden.
OPTIONEN: dict[str, Any] = {"num_ctx": 16384, "temperature": 0.7, "num_predict": 400}
KEEP_ALIVE = "30m"
# Kleine lokale Modelle schreiben Werkzeuge manchmal als Text: „[emote: staunen] [head: yaw deg=15, seconds=2]“
# (gemeldet 11.11. mit qwen3.5:9b). Solche Marken werden ausgeführt, wenn es das Werkzeug gibt, und nie gezeigt oder
# vorgelesen. Nur [wort: …] – normale Klammern im Text bleiben.
TEXT_WERKZEUG = re.compile(r"\[\s*([a-z_]{2,30})\s*:\s*([^\[\]]{0,160})\]", re.I)


def text_werkzeuge(text: str, schemas: dict[str, dict[str, Any]]) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    """Werkzeug-Marken aus dem Text holen → (sauberer Text, [(Werkzeug, Argumente)])."""
    aufrufe: list[tuple[str, dict[str, Any]]] = []

    def ersetzen(m: re.Match[str]) -> str:
        name, roh = m.group(1).lower(), m.group(2).strip()
        schema = schemas.get(name)
        if schema is not None:
            props = (schema.get("properties") or {})
            args: dict[str, Any] = {}
            for teil in (x.strip() for x in roh.split(",") if x.strip()):
                if "=" in teil:
                    k, v = (s.strip() for s in teil.split("=", 1))
                    k = re.sub(r"\s+", "_", k.lower())
                    if k not in props and f"{k}_deg" in props:
                        k = f"{k}_deg"
                else:
                    pflicht = list(schema.get("required") or []) or [p for p in props if p != "then"]
                    k, v = (pflicht[0] if pflicht else ""), teil
                if k not in props:
                    continue
                if props[k].get("type") == "number":
                    try:
                        args[k] = float(v.replace(",", "."))
                    except ValueError:
                        continue
                else:
                    args[k] = v.strip("\"' ")
            if all(r in args for r in schema.get("required") or []):
                aufrufe.append((name, args))
        return ""

    sauber = TEXT_WERKZEUG.sub(ersetzen, text)
    sauber = re.sub(r"[ \t]{2,}", " ", sauber)
    sauber = re.sub(r"\s+([.,!?])", r"\1", sauber).strip()
    return sauber, aufrufe


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
        self.zeiten: dict[str, float] = {}         # letzte Antwort: laden, lesen, schreiben (s) – fürs Protokoll
        self.vorgewaermt: str | None = None        # für welches Modell und welchen Systemtext schon vorgeladen

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

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                   **optionen: Any) -> dict[str, Any]:
        """Eine Runde mit Ollama – immer mit denselben Optionen und `keep_alive`; Zeiten landen in `zeiten`."""
        body: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False, "think": False,
                                "keep_alive": KEEP_ALIVE, "options": {**OPTIONEN, **optionen}}
        if tools:
            body["tools"] = tools
        data = await self._post("/api/chat", body)
        ns = 1e-9
        z = {"laden_s": (data.get("load_duration") or 0) * ns, "lesen_s": (data.get("prompt_eval_duration") or 0) * ns,
             "lesen_token": data.get("prompt_eval_count") or 0, "schreiben_s": (data.get("eval_duration") or 0) * ns,
             "schreiben_token": data.get("eval_count") or 0}
        for k, v in z.items():
            self.zeiten[k] = self.zeiten.get(k, 0) + v
        return data

    def _vorlage(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        runner = self.agent.runner
        erlaubt = getattr(self.agent, "local_tools", LOCAL_TOOLS)     # der Kopf hat eigene (seit 0.38.8)
        tools = [_tool_spec(t) for t in runner.tools() if t["name"] in erlaubt]
        return [{"role": "system", "content": self.agent._system() + LOCAL_NOTE}], tools

    async def vorwaermen(self) -> float | None:
        """Modell laden und Systemtext samt Werkzeugen schon einmal lesen lassen (seit 0.46.2). Ollama merkt sich den
        gelesenen Anfang; die erste echte Antwort muss dann nur noch die Frage lesen. Fehler sind egal."""
        if not self.configured:
            return None
        try:
            system, tools = self._vorlage()
            schluessel = f"{self.model}|{hash(system[0]['content'])}|{len(tools)}"
            if self.vorgewaermt == schluessel:
                return 0.0
            t0 = time.monotonic()
            self.zeiten = {}
            await self.chat([*system, {"role": "user", "content": "."}], tools, num_predict=1)
            self.vorgewaermt = schluessel
            dauer = time.monotonic() - t0
            log.info("Lokales Modell %s vorgewärmt in %.1f s (laden %.1f s, %d Token gelesen in %.1f s)", self.model, dauer,
                     self.zeiten.get("laden_s", 0), self.zeiten.get("lesen_token", 0), self.zeiten.get("lesen_s", 0))
            return dauer
        except Exception as exc:  # noqa: BLE001 – Vorwärmen ist nur ein Gefallen
            log.info("Lokales Modell nicht vorgewärmt: %s", exc)
            return None

    async def handle(self, text: str, notify: "Notify | None" = None) -> "Reply":
        from .agent import Reply

        t0 = time.monotonic()
        self.zeiten = {}
        runner = self.agent.runner
        erlaubt = getattr(self.agent, "local_tools", LOCAL_TOOLS)     # der Kopf hat eigene (seit 0.38.8)
        system, tools = self._vorlage()
        messages: list[dict[str, Any]] = [*system]
        messages += self.history[-16:]
        user = {"role": "user", "content": f"{text}\n\n{self.agent._context(text)}"}
        messages.append(user)
        actions: list[dict[str, Any]] = []
        final = ""
        for _ in range(self.max_rounds):
            data = await self.chat(messages, tools)
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
        # Werkzeuge, die das Modell als Text geschrieben hat, ausführen und aus der Antwort nehmen (seit 0.38.40)
        schemas = {t["name"]: t["input_schema"] for t in runner.tools() if t["name"] in erlaubt}
        final, als_text = text_werkzeuge(final, schemas)
        for name, args in als_text[:4]:
            result = await runner.run(name, args)
            action = {"tool": name, "input": args, "result": result}
            actions.append(action)
            if notify:
                maybe = notify({"type": "action", **action})
                if maybe is not None:
                    await maybe
        final = final or "Quak!"
        # Für den Verlauf nur Frage und Antwort – das hält den Kontext klein
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": final}]
        self.history = self.history[-16:]
        self.last_error = None
        z = self.zeiten
        log.info("Lokale Antwort in %.1f s: laden %.1f s, %d Token lesen %.1f s, %d Token schreiben %.1f s",
                 time.monotonic() - t0, z.get("laden_s", 0), z.get("lesen_token", 0), z.get("lesen_s", 0),
                 z.get("schreiben_token", 0), z.get("schreiben_s", 0))
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
