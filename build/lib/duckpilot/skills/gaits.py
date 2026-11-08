"""Gangarten: Laufmodelle aus der Microduck Arena und der Community (Tag `microduck-slot:walk`).

Eine Gangart ersetzt das normale Gehen der Ente (den Platz `walk`), statt als Trick
daneben zu laufen – z. B. die Sieger im 2-m-Sprint oder beim Bergauf-Rennen. Am echten
Roboter macht duckpilot dasselbe wie `robotctl policy load walk <repo>`: updaterd holt die
Datei, robotd tauscht den Platz (`robot.loadPolicy`). „Standard“ setzt Pollens Gangart zurück.

Bewusst nur über die Oberfläche, nicht für Claude: das Gehen auszutauschen ist eine
Entscheidung des Menschen. Das erste Mal mit der Ente auf dem Ständer.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable

from .. import hub
from . import Pack, PackInfo, hub_json, siblings

if TYPE_CHECKING:
    from . import SkillManager

LIMIT = 60
# Reihenfolge zählt: das Genauere zuerst
ARENA = {"roller": "Rollen-Sprint", "hill-climb": "Bergauf 1,5 m", "sprint-2m": "Sprint 2 m", "sprint": "Sprint",
         "hill": "Bergauf", "redlight": "Rotes Licht", "tug": "Tauziehen", "walk": "Gehen"}


def label_of(repo: str) -> str:
    s = repo.split("/", 1)[-1].lower()
    for key, label in ARENA.items():
        if key in s:
            return label
    return "Gangart"


class Gaits(Pack):
    def __init__(self) -> None:
        self.info = PackInfo(
            id="gaits", name="Gangarten (Arena & Community)",
            kurz="Neue Laufmodelle statt des normalen Gehens – Sprinter, Bergsteiger, Rollen-Sprinter.",
            text="Aus Pollens Microduck Arena (Referenzen und Bestenliste) und der Community. Eine Gangart ersetzt "
                 "das normale Gehen, bis du wieder auf Standard schaltest. Nur über die Oberfläche, nicht über Claude.",
            quelle=f"{hub.HUB}/models?other=microduck-slot:walk", lizenz="je Repo", herkunft="gemischt",
            braucht="roboter", stand="experimentell",
            im_simulator="Im Simulator nur zum Stöbern – der Simulator läuft mit seiner eingebauten Gangart.",
            hinweis="Fremde Gangarten prüft niemand. Das erste Mal mit der Ente auf dem Ständer.")

    def catalog(self, fetch: Callable[[str], bytes]) -> list[dict[str, Any]]:
        models = hub_json(fetch, "/api/models?filter=microduck-slot:walk&full=true&limit=200")
        out = []
        seen_prefix: dict[str, int] = {}
        for m in models if isinstance(models, list) else []:
            repo = m.get("modelId") or m.get("id")
            files = siblings(m)
            if not repo or (files and not any(f.endswith(".onnx") for f in files)):
                continue
            # Viele Zwischenstände desselben Trainings (…_0896, …_0908): nur die drei besten je Reihe
            stem = re.sub(r"[_-]\d{3,5}$", "", repo)
            seen_prefix[stem] = seen_prefix.get(stem, 0) + 1
            preview = hub.preview_in(files)
            out.append({
                "repo": repo, "name": hub.trick_name(repo), "titel": repo.split("/", 1)[-1],
                "rubrik": label_of(repo), "herkunft": hub.origin_of(repo),
                "likes": m.get("likes") or 0, "downloads": m.get("downloads") or 0,
                "seite": f"{hub.HUB}/{repo}", "_reihe": stem,
                "vorschau": f"{hub.HUB}/{repo}/resolve/main/{preview}" if preview else None,
            })
        out.sort(key=lambda o: (o["herkunft"] != "offiziell", -o["likes"], -o["downloads"]))
        kept, per = [], {}
        for o in out:
            per[o["_reihe"]] = per.get(o["_reihe"], 0) + 1
            if per[o["_reihe"]] <= 3:
                o["weitere"] = max(0, seen_prefix[o["_reihe"]] - 3) if per[o["_reihe"]] == 1 else 0
                kept.append({k: v for k, v in o.items() if k != "_reihe"})
        return kept[:LIMIT]

    async def run(self, mgr: "SkillManager", item: str, action: str) -> dict[str, Any]:
        be = mgr.rt.backend
        if action == "standard":
            res = await be.reset_gait("walk")
            if res.accepted:
                mgr.rt.gait = None
            return {"ok": res.accepted, "grund": res.reason}
        it = await mgr.item(self.info.id, item)
        if not it:
            return {"ok": False, "grund": "Diese Gangart kenne ich nicht."}
        res = await be.load_gait(it["repo"], "walk")
        if res.accepted:
            mgr.rt.gait = it["repo"]
        return {"ok": res.accepted, "grund": res.reason}
