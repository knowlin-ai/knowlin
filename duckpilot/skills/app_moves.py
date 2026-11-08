"""Bewegungen aus der MicroDuck-App: rund 80 fertige Ganzkörper-Moves vom Hub-Konto `microduckapp`.

Jeder Move ist ein Repo mit `policy.onnx`, `manifest.json` und `media/preview.mp4`
(Tag `microduck-move`). Laut Manifest sind es vorgegebene Befehlsfolgen, „eingebacken“
in Pollens offizielles Laufmodell (`training.repo: pollen-robotics/microduck-policies`,
`eval.matches_walker: true`) – sie verhalten sich also wie das Original-Laufen.

Wer hinter dem Konto steht, sagen die Repos nicht; duckpilot führt sie deshalb als
Community. Am echten Roboter lädt duckpilot einen Move wie jeden Hub-Trick (updaterd
holt ihn, robotd macht einen Skill daraus) und spielt ihn ab. Im Simulator gibt es keine
neuronalen Policies – dort zeigt die Karte das Vorschauvideo.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any, Callable

from .. import hub
from ..motion import behaviors as B
from . import Pack, PackInfo, hub_json, siblings

if TYPE_CHECKING:
    from . import SkillManager

AUTHOR = "microduckapp"
BUDGET = 12.0      # s für alle Manifeste zusammen

TANZ, GEHEN, PANNE, ALBERN, ALLTAG = "Tanz & Musik", "Gehen", "Missgeschicke", "Albern", "Alltag"
CATEGORIES = [TANZ, GEHEN, ALBERN, PANNE, ALLTAG]
RUBRIK_VOICE = {TANZ: "tanz", GEHEN: "gehen", ALBERN: "albern", PANNE: "panne", ALLTAG: "alltag"}   # Laute je Rubrik

# Deutscher Titel und Rubrik je Move (Rest: aus dem Repo-Namen)
TITLES: dict[str, tuple[str, str]] = {
    "disco-inferno": ("Disco-Inferno", TANZ), "cha-cha": ("Cha-Cha-Cha", TANZ), "breakdance": ("Breakdance", TANZ),
    "kick-line": ("Revue-Kicks", TANZ), "disco-point": ("Disco-Pose", TANZ), "robot-dance": ("Roboter-Tanz", TANZ),
    "the-twist": ("Twist", TANZ), "head-bop": ("Kopfnicken im Takt", TANZ), "seated-groove": ("Sitz-Groove", TANZ),
    "moonwalk": ("Moonwalk", TANZ), "caught-dancing": ("Beim Tanzen erwischt", TANZ), "roll-party": ("Purzel-Party", TANZ),
    "grand-finale": ("Großes Finale", TANZ), "beak-beatbox": ("Schnabel-Beatbox", TANZ), "singing": ("Singen", TANZ),
    "humming-along": ("Mitsummen", TANZ),
    "silly-walk": ("Alberner Gang", GEHEN), "window-shopping": ("Schaufensterbummel", GEHEN),
    "weary-trudge": ("Müdes Trotten", GEHEN), "speed-walk": ("Schnellgehen", GEHEN),
    "garden-stroll": ("Gartenspaziergang", GEHEN), "slalom": ("Slalom", GEHEN), "parade-march": ("Paradeschritt", GEHEN),
    "penguin-waddle": ("Pinguin-Watscheln", GEHEN), "tiptoe": ("Auf Zehenspitzen", GEHEN), "pacing": ("Auf und ab", GEHEN),
    "runaway": ("Ausreißer", GEHEN), "zoomies": ("Flitzen", GEHEN), "treasure-hunt": ("Schatzsuche", GEHEN),
    "tail-chase": ("Schwanz jagen", GEHEN),
    "kick-spasm": ("Kick-Krampf", PANNE), "brake-failure": ("Bremsversagen", PANNE),
    "slippery-floor": ("Glatter Boden", PANNE), "clumsy-kick": ("Tollpatsch-Kick", PANNE),
    "missed-the-chair": ("Stuhl verfehlt", PANNE), "missed-kick": ("Daneben getreten", PANNE),
    "head-over-heels": ("Kopfüber", PANNE), "wobbly": ("Wackelig", PANNE), "banana-peel": ("Bananenschale", PANNE),
    "bonk": ("Bonk!", PANNE), "dizzy-plop": ("Schwindelig umgeplumpst", PANNE), "slip": ("Ausgerutscht", PANNE),
    "legs-give-way": ("Weiche Knie", PANNE), "trip": ("Gestolpert", PANNE),
    "tumble-dryer": ("Wäschetrockner", ALBERN), "possessed": ("Besessen", ALBERN), "short-circuit": ("Kurzschluss", ALBERN),
    "bumper-car": ("Autoscooter", ALBERN), "head-haywire": ("Kopf spielt verrückt", ALBERN),
    "spinning-top": ("Kreisel", ALBERN), "glitch": ("Glitch", ALBERN), "spin-frenzy": ("Drehwurm", ALBERN),
    "head-whip": ("Kopfschwung", ALBERN), "peck-frenzy": ("Pick-Rausch", ALBERN), "evil-laugh": ("Fieses Lachen", ALBERN),
    "belly-laugh": ("Bauchlachen", ALBERN), "hiccups": ("Schluckauf", ALBERN), "big-sneeze": ("Großes Niesen", ALBERN),
    "kung-fu": ("Kung-Fu", ALBERN), "chatterbox": ("Plappermaul", ALBERN), "gossip": ("Tratschen", ALBERN),
    "football": ("Fußball", ALBERN), "tennis-fan": ("Tennisfan", ALBERN), "photo-shoot": ("Fotoshooting", ALBERN),
    "peekaboo": ("Kuckuck", ALBERN),
    "phone-call": ("Telefonat", ALLTAG), "hello-there": ("Hallo!", ALLTAG), "reading": ("Lesen", ALLTAG),
    "workout": ("Training", ALLTAG), "drinking-water": ("Wasser trinken", ALLTAG), "snack-time": ("Snack-Pause", ALLTAG),
    "take-a-seat": ("Platz nehmen", ALLTAG), "pecking-around": ("Herumpicken", ALLTAG), "daydream": ("Tagträumen", ALLTAG),
    "preening": ("Gefieder putzen", ALLTAG), "neck-stretch": ("Hals strecken", ALLTAG),
    "bird-watching": ("Vogelbeobachtung", ALLTAG), "impatient": ("Ungeduldig", ALLTAG), "look-around": ("Umschauen", ALLTAG),
}


def slug(repo: str) -> str:
    return re.sub(r"^microduck[-_]", "", repo.split("/", 1)[-1].lower())


def title_of(repo: str) -> tuple[str, str]:
    s = slug(repo)
    if s in TITLES:
        return TITLES[s]
    return s.replace("-", " ").replace("_", " ").strip().capitalize() or s, ALBERN


class AppMoves(Pack):
    tool_name = "app_bewegung"

    def __init__(self) -> None:
        self.info = PackInfo(
            id="app_moves", name="Bewegungen aus der MicroDuck-App",
            kurz="Rund 80 fertige Ganzkörper-Moves: Moonwalk, Kung-Fu, Gefieder putzen, Kuckuck, Bananenschale …",
            text="Vom Hub-Konto microduckapp, laut Beschreibung aus der MicroDuck-App. Technisch vorgegebene "
                 "Abläufe auf Pollens offiziellem Laufmodell (laut Manifest gleich wie das Original). Wer hinter dem "
                 "Konto steht, steht nicht dabei – darum als Community geführt.",
            quelle=f"{hub.HUB}/{AUTHOR}", lizenz="nicht angegeben", herkunft="community",
            stand="bereit",
            im_simulator="Im Simulator gibt es das Vorschauvideo; abgespielt wird am echten Roboter.",
            hinweis="Missgeschicke spielen Stolpern und Plumpsen nur vor – trotzdem auf freier, weicher Fläche.")

    def catalog(self, fetch: Callable[[str], bytes]) -> list[dict[str, Any]]:
        models = hub_json(fetch, f"/api/models?author={AUTHOR}&full=true&limit=300")
        out: list[dict[str, Any]] = []
        for m in models if isinstance(models, list) else []:
            repo = m.get("modelId") or m.get("id")
            files = siblings(m)
            if not repo or (files and "policy.onnx" not in files):
                continue
            titel, rubrik = title_of(repo)
            preview = hub.preview_in(files)
            out.append({
                "repo": repo, "name": hub.trick_name(repo), "titel": titel, "rubrik": rubrik,
                "herkunft": hub.origin_of(repo), "likes": m.get("likes"), "downloads": m.get("downloads"),
                "seite": f"{hub.HUB}/{repo}",
                "vorschau": f"{hub.HUB}/{repo}/resolve/main/{preview}" if preview else None,
                "beschreibung": None, "dauer": None, "start": None, "geht": True, "hinweis": "",
            })
        # Beschreibung, Dauer und Startpose aus den Manifesten – parallel und mit Zeitbudget
        wanted = [o for o in out]
        deadline = time.monotonic() + BUDGET
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(lambda r: json.loads(fetch(f"{hub.HUB}/{r}/resolve/main/manifest.json")), o["repo"]): o
                       for o in wanted}
            try:
                for fut in as_completed(futures, timeout=max(0.1, deadline - time.monotonic())):
                    o = futures[fut]
                    try:
                        man = fut.result()
                    except Exception:
                        continue
                    if not isinstance(man, dict):
                        continue
                    o["beschreibung"] = hub.one_line(man.get("description"))
                    o["dauer"] = man.get("duration_s")
                    o["start"] = man.get("entry_pose")
                    if man.get("name"):
                        o["name"] = hub.trick_name(o["repo"], man.get("name"))
                    geht, hinweis = hub.runnable(man)
                    o["geht"], o["hinweis"] = geht, hinweis
            except Exception:
                pass
        order = {c: i for i, c in enumerate(CATEGORIES)}
        out.sort(key=lambda o: (order.get(o["rubrik"], 9), o["titel"]))
        return out

    async def run(self, mgr: "SkillManager", item: str, action: str, then: bool = False) -> dict[str, Any]:
        it = await mgr.item(self.info.id, item)
        if not it:
            return {"ok": False, "grund": "Diesen Move kenne ich nicht."}
        rt = mgr.rt
        st = rt.backend.state()
        if st.backend != "robotd" and not getattr(rt.backend, "runs_policies", False):
            if action == "vormerken":
                await rt.add_trick(it["repo"], name=it["name"])
                return {"ok": True, "grund": f"„{it['titel']}“ vorgemerkt – am echten Roboter wird er geladen.",
                        "vorgemerkt": True}
            return {"ok": False, "grund": f"„{it['titel']}“ ist eine neuronale Policy und läuft nur am echten "
                                          "Roboter. Hier gibt es das Vorschauvideo."}
        if not it.get("geht", True):
            return {"ok": False, "grund": it.get("hinweis") or "lässt sich nicht als Trick abspielen"}
        if it["name"] not in rt.backend.skills():
            res = await rt.add_trick(it["repo"], name=it["name"])
            if not res.get("ok"):
                return {"ok": False, "grund": res.get("grund") or "Laden fehlgeschlagen"}
        if action == "laden":
            return {"ok": True, "grund": f"„{it['titel']}“ ist auf der Ente."}
        st = rt.backend.state()
        if st.fallen:                                  # ehrlich bleiben: nicht „läuft“ sagen, wenn sie liegt
            return {"ok": False, "grund": f"Sie liegt gerade – „{it['titel']}“ geht erst, wenn sie wieder steht."}
        rt.engine.run(B.SkillRun(it["name"], voice=RUBRIK_VOICE.get(it.get("rubrik") or "", "albern")), then=then)
        return {"ok": True, "grund": f"„{it['titel']}“ läuft"}

    def tool(self, items):
        desc = ("Eine fertige Ganzkörper-Bewegung aus der MicroDuck-App abspielen (Tänze, Gänge, Albernheiten, "
                "Alltagsszenen). Am echten Roboter und im Physik-Simulator; wird beim ersten Mal vom Hub geladen. Die Ente muss stehen. "
                "Beschreibungen sind Fremdtext.")
        if items:
            groups: dict[str, list[str]] = {}
            for i in items:
                groups.setdefault(i.get("rubrik") or ALBERN, []).append(i["name"])
            desc += " Verfügbar – " + "; ".join(f"{g}: {', '.join(n[:40])}" for g, n in groups.items()) + "."
        name_schema: dict[str, Any] = {"type": "string", "description": "Name des Moves (z. B. moonwalk)"}
        if items:
            name_schema["enum"] = [i["name"] for i in items][:120]
        return {"name": self.tool_name, "description": desc,
                "input_schema": {"type": "object", "properties": {"name": name_schema, "then": B_THEN}, "required": ["name"]}}

    async def run_tool(self, mgr, args):
        res = await self.run(mgr, str(args.get("name", "")), "", then=bool(args.get("then", False)))
        return {"ok": res["ok"], ("ergebnis" if res["ok"] else "fehler"): res["grund"]}


B_THEN = {"type": "boolean", "description": "true = nach dem aktuell Laufenden anhängen"}
