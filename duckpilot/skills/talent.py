"""Got a Talent: 20-Sekunden-Vorführungen aus Pollens Microduck Arena.

Ein Beitrag ist ein Hub-Repo mit `timeline.json` (pollen-robotics/microduck-challenges,
got_a_talent/AGENTS.md):

    {"timeline_version": 1, "duration_s": 20.0,
     "keyframes": [{"t": 0.0, "twist": [0, 0, 0], "head": [0, 0, 0, 0]}, …]}

* stufenweise: die Werte eines Keyframes gelten ab `t` bis zum nächsten,
  fehlende Gruppen sind Nullen (nicht vom Vorgänger übernommen)
* `twist[0]` ist die Sitz-Fahne (1 sitzt, 0 steht), `twist[1..2]` unbenutzt
* `head` = Abweichung von der Grundhaltung in Radiant: Nacken, Kopf nicken, drehen, neigen
* höchstens 20 s, 1000 Keyframes, jede Zahl innerhalb ±10

In der Arena liest eine eigene Policy diese Befehle. duckpilot spielt sie mit den
normalen Bausteinen ab – Kopfziele und Hinsetzen/Aufstehen –, darum laufen sie im
Simulator genauso wie am echten Roboter. Die Kopfwinkel werden auf die Grenzen der
Ente begrenzt.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any, Callable

from .. import hub
from ..api import Head, Twist
from ..motion import behaviors as B
from ..motion.engine import Behavior, Command
from . import Pack, PackInfo, hub_json, siblings

if TYPE_CHECKING:
    from . import SkillManager

MAX_ENTRIES = 30
MIN_TOGGLE_GAP = 2.5   # s – Hinsetzen/Aufstehen braucht seine Zeit


def parse_timeline(data: Any) -> dict[str, Any]:
    """Prüft eine timeline.json nach den Arena-Regeln; ValueError bei Unsinn."""
    if not isinstance(data, dict):
        raise ValueError("keine JSON-Struktur")
    kfs = data.get("keyframes")
    if not isinstance(kfs, list) or not kfs:
        raise ValueError("keine Keyframes")
    if len(kfs) > 1000:
        raise ValueError("mehr als 1000 Keyframes")
    duration = float(data.get("duration_s") or 20.0)
    if not 0 < duration <= 20.0:
        raise ValueError("Dauer muss zwischen 0 und 20 s liegen")
    out = []
    last_t = -1.0
    for k in kfs:
        if not isinstance(k, dict):
            raise ValueError("Keyframe ist kein Objekt")
        t = float(k.get("t", 0.0))
        if t < 0 or t <= last_t:
            raise ValueError("Zeiten müssen bei 0 beginnen und steigen")
        twist = [float(v) for v in (k.get("twist") or [0, 0, 0])][:3] + [0.0] * 3
        head = [float(v) for v in (k.get("head") or [0, 0, 0, 0])][:4] + [0.0] * 4
        if any(not math.isfinite(v) or abs(v) > 10 for v in twist[:3] + head[:4]):
            raise ValueError("Zahl außerhalb ±10")
        out.append({"t": round(t, 3), "sit": twist[0] >= 0.5, "head": [round(v, 4) for v in head[:4]]})
        last_t = t
    if out[0]["t"] != 0:
        raise ValueError("der erste Keyframe muss bei t = 0 liegen")
    sits = sum(1 for a, b in zip(out, out[1:]) if a["sit"] != b["sit"])
    moves = sum(1 for a, b in zip(out, out[1:]) if a["head"] != b["head"])
    return {"dauer": round(duration, 2), "keyframes": out, "sitzwechsel": sits, "kopfwechsel": moves}


class TalentShow(Behavior):
    """Eine Got-a-Talent-Timeline abspielen: Kopfziele stufenweise, Hinsetzen/Aufstehen nach Fahne."""

    name = "vorfuehrung"
    channels = ("base", "head")

    def __init__(self, timeline: dict[str, Any], title: str = "Vorführung") -> None:
        super().__init__()
        self.kfs = timeline["keyframes"]
        self.duration = float(timeline["dauer"])
        self.title = title
        self.timeout = self.duration + 12.0
        self.needs_legs = False          # darf im Sitzen beginnen
        self._toggle_task = None
        self._toggled_at = -99.0
        self.toggles = 0
        self.voice = B.TrickVoice("tanz")             # eine Vorführung: im Takt mitquaken

    def on_start(self, st):
        if self.engine:
            self.engine.note({"type": "trick", "message": f"Vorführung „{self.title}“ ({self.duration:.0f} s)"})

    def _frame(self, t: float) -> dict[str, Any]:
        cur = self.kfs[0]
        for k in self.kfs:
            if k["t"] <= t:
                cur = k
            else:
                break
        return cur

    def tick(self, st, dt):
        if not st.powered or st.fallen:
            return self.finish("die Ente ruht oder liegt – erst aufstehen")
        if self.elapsed >= self.duration:
            return self.finish(f"Vorführung „{self.title}“ zu Ende")
        k = self._frame(self.elapsed)
        busy = self._toggle_task is not None and not self._toggle_task.done()
        if (k["sit"] != bool(st.sitting) and not st.skill and not busy
                and self.elapsed - self._toggled_at >= MIN_TOGGLE_GAP and self.engine):
            self._toggle_task = self.engine.fire(self.engine.backend.do("sit_toggle"))
            self._toggled_at = self.elapsed
            self.toggles += 1
        self.voice.tick(self, self.elapsed)
        n, p, y, r = k["head"]
        return Command(twist=Twist(), head=Head(n, p, y, r).clamped())

    def describe(self):
        return f"Vorführung {self.title} ({self.elapsed:.0f}/{self.duration:.0f} s)"


class Talent(Pack):
    tool_name = "vorfuehrung"

    def __init__(self) -> None:
        self.info = PackInfo(
            id="talent", name="Got a Talent (Microduck Arena)",
            kurz="20-Sekunden-Vorführungen aus Pollens Arena: Kopf, Hinsetzen, Aufstehen – im Takt.",
            text="Pollens Arena hat eine Bühne, auf der Beiträge 20 Sekunden lang vorführen und das Publikum "
                 "abstimmt. Jeder Beitrag ist eine Zeitleiste aus Kopfbewegungen und Hinsetzen/Aufstehen. "
                 "duckpilot spielt sie mit den normalen Bausteinen ab.",
            quelle="https://github.com/pollen-robotics/microduck-challenges", lizenz="je Beitrag",
            herkunft="gemischt", stand="bereit",
            im_simulator="Läuft im Simulator genauso wie am Roboter.")

    def catalog(self, fetch: Callable[[str], bytes]) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for path in ("/api/models?filter=microduck-slot:sitstand&full=true&limit=100",
                     "/api/models?search=talent&full=true&limit=100",
                     "/api/models?search=microduck-got&full=true&limit=100"):
            try:
                models = hub_json(fetch, path)
            except Exception:
                continue
            for m in models if isinstance(models, list) else []:
                repo = m.get("modelId") or m.get("id")
                if repo and "timeline.json" in siblings(m):
                    found.setdefault(repo, m)
        if not found:
            # alles fehlgeschlagen oder nichts da: wenigstens Pollens Referenz versuchen
            found["pollen-robotics/microduck-got-a-talent-reference"] = {"siblings": [{"rfilename": "timeline.json"}]}
        out = []
        for repo, m in list(found.items())[:MAX_ENTRIES]:
            try:
                tl = parse_timeline(json.loads(fetch(f"{hub.HUB}/{repo}/resolve/main/timeline.json")))
            except Exception:
                continue
            files = siblings(m)
            preview = hub.preview_in(files)
            name = hub.trick_name(repo)
            name = name.replace("got-a-talent-reference", "referenz")
            out.append({
                "repo": repo, "name": name,
                "titel": "Pollens Referenz" if repo.startswith(hub.OFFICIAL_ORG + "/") else name.replace("-", " ").title(),
                "herkunft": hub.origin_of(repo), "likes": m.get("likes"), "downloads": m.get("downloads"),
                "seite": f"{hub.HUB}/{repo}",
                "vorschau": f"{hub.HUB}/{repo}/resolve/main/{preview}" if preview else None,
                **tl,
            })
        out.sort(key=lambda o: (o["herkunft"] != "offiziell", -(o["likes"] or 0), -(o["downloads"] or 0)))
        return out

    async def run(self, mgr: "SkillManager", item: str, action: str) -> dict[str, Any]:
        it = await mgr.item(self.info.id, item)
        if not it:
            return {"ok": False, "grund": "Diese Vorführung kenne ich nicht."}
        st = mgr.rt.backend.state()
        if not st.powered:
            return {"ok": False, "grund": "Die Ente ruht – erst aufstehen lassen."}
        mgr.rt.engine.run(TalentShow({"keyframes": it["keyframes"], "dauer": it["dauer"]}, it["titel"]))
        return {"ok": True, "grund": f"„{it['titel']}“ läuft ({it['dauer']:.0f} s)"}

    def tool(self, items):
        names = [i["name"] for i in items or []][:30]
        desc = ("Eine Got-a-Talent-Vorführung aus Pollens Microduck Arena abspielen (bis 20 s: Kopfbewegungen, "
                "Hinsetzen und Aufstehen nach Zeitleiste). Läuft im Simulator und am Roboter.")
        if names:
            desc += " Verfügbar: " + ", ".join(names) + "."
        name_schema: dict[str, Any] = {"type": "string", "description": "Name der Vorführung"}
        if names:
            name_schema["enum"] = names
        return {"name": self.tool_name, "description": desc,
                "input_schema": {"type": "object", "properties": {"name": name_schema}, "required": ["name"]}}

    async def run_tool(self, mgr, args):
        res = await self.run(mgr, str(args.get("name", "")), "")
        return {"ok": res["ok"], ("ergebnis" if res["ok"] else "fehler"): res["grund"]}

