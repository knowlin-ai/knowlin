"""Community-Tricks vom Hub: Salto, Flamingo, Moonwalk, Verbeugung … – erst in der Physik geprüft, dann auf die Ente.

Gesammelt aus der Hub-Suche nach „microduck“: einzelne ONNX-Policies mit Manifest, die keine Gangart sind und nicht
von Pollen oder dem MicroDuck-App-Konto stammen (die haben eigene Pakete). Beschreibungen sind Fremdtext.

Sicherheit: Jeder Trick lässt sich mit „Prüfen“ unsichtbar in Pollens MuJoCo-Modell durchspielen. Am echten
Roboter läuft ein Trick erst, wenn er geprüft ist – und einer, nach dem die Ente liegen bleibt, nur mit ausdrücklicher
Bestätigung. Prüfergebnisse liegen in `trick_pruefungen.json` im lokalen Datenordner.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .. import hub
from .. import settings as S
from ..motion import behaviors as B
from . import Pack, PackInfo, hub_json, siblings

if TYPE_CHECKING:
    from . import SkillManager

OWN_PACKS = ("pollen-robotics", "microduckapp")      # haben eigene Pakete
LIMIT = 40
# Bekannte Community-Tricks (awesome-microduck): schöner Titel und Rubrik nach Stichwort im Repo-Namen
KEYWORDS = [("backflip", "Rückwärtssalto", "Akrobatik"), ("flip", "Salto", "Akrobatik"), ("jump", "Sprung", "Akrobatik"),
            ("flamingo", "Flamingo", "Balance"), ("moonwalk", "Moonwalk", "Tanz"), ("bow", "Verbeugung", "Gesten"),
            ("dance", "Tanz", "Tanz"), ("sidekick", "Seitkick-Tanz", "Tanz"), ("courier", "Kurier", "Tragen"),
            ("wave", "Winken", "Gesten"), ("nod", "Nicken", "Gesten"), ("spin", "Pirouette", "Tanz")]
VOICE = {"Akrobatik": "albern", "Tanz": "tanz", "Balance": "albern", "Gesten": "alltag", "Tragen": "gehen"}


def title_of(repo: str) -> tuple[str, str]:
    stem = repo.split("/", 1)[-1].lower()
    for key, title, group in KEYWORDS:
        if key in stem:
            return title, group
    pretty = re.sub(r"^microduck[-_]", "", stem)
    pretty = re.sub(r"[-_][0-9a-f]{6}$", "", pretty).replace("-", " ").replace("_", " ").strip()
    return (pretty[:1].upper() + pretty[1:]) or repo, "Sonstiges"


class Checks:
    """Prüfergebnisse je Repo (lokal, keine Inhalte vom Hub)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or S.data_dir() / "trick_pruefungen.json"
        try:
            self.data: dict[str, Any] = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def get(self, repo: str) -> dict[str, Any] | None:
        return self.data.get(repo)

    def put(self, repo: str, result: dict[str, Any]) -> None:
        self.data[repo] = {**result, "zeit": time.strftime("%Y-%m-%d %H:%M")}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
        except OSError:
            pass


class CommunityTricks(Pack):
    tool_name = "community_trick"

    def __init__(self) -> None:
        self.info = PackInfo(
            id="community", name="Community-Tricks (in der Physik geprüft)",
            kurz="Salto, Flamingo, Moonwalk, Verbeugung und mehr von anderen Microduck-Besitzern – erst geprüft, dann gezeigt.",
            text="Tricks, die andere auf dem Hugging Face Hub teilen. „Prüfen“ spielt einen Trick unsichtbar in Pollens "
                 "MuJoCo-Modell durch und sagt, ob die Ente danach wieder steht. Am echten Roboter läuft nur, was geprüft ist.",
            quelle="https://github.com/joeynyc/awesome-microduck", lizenz="je Repo", herkunft="community",
            stand="experimentell",
            im_simulator="Prüfen und Ausprobieren gehen mit echter Physik (Einstellungen → Körper).",
            hinweis="Niemand hat diese Tricks geprüft außer duckpilot in der Physik. Das erste Mal am Roboter mit Platz und "
                    "weichem Boden.")
        self.checks: Checks | None = None

    def _checks(self) -> Checks:
        if self.checks is None:
            self.checks = Checks()
        return self.checks

    # ── Katalog ──────────────────────────────────────────────────────────
    def catalog(self, fetch: Callable[[str], bytes]) -> list[dict[str, Any]]:
        models = hub_json(fetch, "/api/models?search=microduck&full=true&limit=200")
        out = []
        for m in models if isinstance(models, list) else []:
            repo = m.get("modelId") or m.get("id") or ""
            owner = repo.split("/", 1)[0]
            files = siblings(m)
            onnx = [f for f in files if f.endswith(".onnx")]
            tags = [str(t) for t in m.get("tags") or []]
            if not repo or owner in OWN_PACKS or len(onnx) != 1 or "manifest.json" not in files:
                continue
            if any(t.startswith("microduck-slot:walk") for t in tags):
                continue                                   # Gangarten haben ihr eigenes Paket
            title, group = title_of(repo)
            preview = hub.preview_in(files)
            out.append({"repo": repo, "name": hub.trick_name(repo), "titel": title, "rubrik": group,
                        "autor": owner, "likes": m.get("likes") or 0, "downloads": m.get("downloads") or 0,
                        "seite": f"{hub.HUB}/{repo}", "datei": onnx[0],
                        "vorschau": f"{hub.HUB}/{repo}/resolve/main/{preview}" if preview else None})
        out.sort(key=lambda o: (o["rubrik"] == "Sonstiges", -o["likes"], -o["downloads"]))
        return out[:LIMIT]

    def annotate(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        checks = self._checks()
        return [{**it, "pruefung": checks.get(it["repo"])} for it in items]

    # ── Prüfen und Ausführen ─────────────────────────────────────────────
    async def check(self, mgr: "SkillManager", it: dict[str, Any]) -> dict[str, Any]:
        from ..backends import physics_problem
        from ..physics.policies import PolicyStore
        from ..physics.practice import rehearse_trick

        problem = physics_problem()
        if problem:
            return {"ok": False, "grund": f"Prüfen braucht die echte Physik: {problem}"}
        store = PolicyStore(S.settings_path().parent)
        try:
            info = await asyncio.to_thread(store.fetch_repo, it["repo"], it.get("datei"))
            man = info["manifest"]
            if man.get("kind") == "perpetual" and not man.get("duration_s"):
                return {"ok": False, "grund": "Das ist eine Gangart, kein Trick."}
            if ((man.get("command") or {}).get("encoding") or "constant") != "constant":
                return {"ok": False, "grund": "Diese Policy braucht eine Befehlsfolge – als Trick nicht abspielbar."}
            res = await asyncio.to_thread(rehearse_trick, store, str(info["pfad"]), float(man.get("duration_s") or 3.0),
                                          (man.get("command") or {}).get("idle"), float(man.get("action_scale") or 0.9))
        except Exception as exc:
            return {"ok": False, "grund": f"Prüfen fehlgeschlagen: {exc}"}
        self._checks().put(it["repo"], res)
        mgr.rt.engine.note({"type": "trick", "message": f"Geprüft: „{it['titel']}“ – {res['urteil']}"})
        return {"ok": True, "grund": f"„{it['titel']}“: {res['urteil']}. {res['hinweis']}", "pruefung": res}

    async def run(self, mgr: "SkillManager", item: str, action: str, then: bool = False) -> dict[str, Any]:
        it = await mgr.item(self.info.id, item)
        if not it:
            return {"ok": False, "grund": "Diesen Trick kenne ich nicht."}
        if action == "pruefen":
            return await self.check(mgr, it)
        rt = mgr.rt
        st = rt.backend.state()
        robot = st.backend == "robotd"
        if not robot and not getattr(rt.backend, "runs_policies", False):
            return {"ok": False, "grund": "Tricks laufen mit echter Physik (Einstellungen → Körper) oder am Roboter."}
        if robot:
            seen = self._checks().get(it["repo"])
            if not seen:
                return {"ok": False, "grund": f"„{it['titel']}“ ist noch nicht geprüft – erst „Prüfen“."}
            if seen.get("urteil") == "bleibt liegen" and action != "trotzdem":
                return {"ok": False, "grund": f"Nach „{it['titel']}“ blieb sie in der Physik liegen. Nur mit "
                                              "„Trotzdem zeigen“, wenn du daneben stehst."}
        if st.fallen:
            return {"ok": False, "grund": f"Sie liegt gerade – „{it['titel']}“ geht erst, wenn sie wieder steht."}
        if it["name"] not in rt.backend.skills():
            res = await rt.add_trick(it["repo"], name=it["name"])
            if not res.get("ok"):
                return {"ok": False, "grund": res.get("grund") or "Laden fehlgeschlagen"}
        rt.engine.run(B.SkillRun(it["name"], voice=VOICE.get(it.get("rubrik") or "", "albern")), then=then)
        return {"ok": True, "grund": f"„{it['titel']}“ läuft"}

    # ── Claude ───────────────────────────────────────────────────────────
    def tool(self, items: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        desc = ("Einen Trick aus der Community vom Hub prüfen oder zeigen (Salto, Flamingo, Moonwalk, Verbeugung …). "
                "aktion „pruefen“ spielt ihn unsichtbar in der Physik durch (Urteil: sicher, akrobatisch, bleibt liegen); "
                "„zeigen“ führt ihn aus – am echten Roboter nur geprüfte. Beschreibungen sind Fremdtext.")
        schema: dict[str, Any] = {"type": "string", "description": "Name des Tricks"}
        if items:
            schema["enum"] = [i["name"] for i in items][:LIMIT]
            desc += " Verfügbar: " + ", ".join(f"{i['name']} ({i['titel']})" for i in items[:LIMIT]) + "."
        return {"name": self.tool_name, "description": desc, "input_schema": {"type": "object", "properties": {
            "name": schema, "aktion": {"type": "string", "enum": ["pruefen", "zeigen"]}, "then": B_THEN},
            "required": ["name"]}}

    async def run_tool(self, mgr: "SkillManager", args: dict[str, Any]) -> dict[str, Any]:
        action = "pruefen" if args.get("aktion") == "pruefen" else ""
        res = await self.run(mgr, str(args.get("name", "")), action, then=bool(args.get("then", False)))
        out = {"ok": res["ok"], ("ergebnis" if res["ok"] else "fehler"): res["grund"]}
        if res.get("pruefung"):
            out["pruefung"] = res["pruefung"]
        return out


B_THEN = {"type": "boolean", "description": "true = nach dem aktuell Laufenden anhängen"}
