"""Tricks vom Hugging Face Hub: Pollens Bewegungs-Policies für den Microduck.

Wer etwas für den Microduck trainiert, veröffentlicht es als Hub-Repo mit `policy.onnx`
und einer `manifest.json` (Format: docs/policy-manifest.md in pollen-robotics/microduck).
Die offiziellen liegen bei `pollen-robotics`, alles andere ist Community.

Die Suche läuft vom PC aus gegen die öffentliche Hub-API – dieselbe Abfrage, die
`updaterd` auf dem Roboter macht (`policy.search`), nur in Python. Laden und Ausführen
geht nur auf dem echten Roboter: dort holt `updaterd` die Datei (`policy.fetch`) und
`robotd` macht daraus einen Skill (`robot.setSkill`).

Alles, was ein Repo über sich sagt, ist **ungeprüfter Fremdtext**: Er wird angezeigt,
aber nie ausgeführt und entscheidet nichts. Sicher machen einen fremden Trick die
Gelenkgrenzen, der Sturzreflex und die Formprüfung auf dem Roboter – nicht die
Beschreibung. Das erste Mal am besten mit der Ente auf dem Ständer.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

log = logging.getLogger(__name__)

HUB = "https://huggingface.co"
OFFICIAL_ORG = "pollen-robotics"
DESCRIPTION_LIMIT = 160
CACHE_SECONDS = 600
REQUEST_TIMEOUT = 8.0
DESCRIBE_BUDGET = 6.0

# Für die Anzeige: was die offiziellen Repos sind (stehen auch in Pollens Doku)
KNOWN = {
    "pollen-robotics/microduck-policies": "Der offizielle Satz: Gehen, Stehen, Hinsetzen, Picken, Schießen, Rolle …",
}

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _get(url: str, timeout: float = REQUEST_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "duckpilot (+https://github.com/pollen-robotics/microduck)"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read(2_000_000)


def one_line(text: str | None) -> str | None:
    if not text:
        return None
    line = str(text).strip().splitlines()[0].strip() if str(text).strip() else ""
    line = re.sub(r"\s+", " ", line)
    if len(line) > DESCRIPTION_LIMIT:
        line = line[: DESCRIPTION_LIMIT - 1].rstrip() + "…"
    return line or None


def preview_in(files: list[str]) -> str | None:
    """Vorschauvideo nach Pollens Konvention (policy-manifest.md)."""
    for want in ("media/preview.mp4", "preview.mp4"):
        if want in files:
            return want
    for f in files:
        base = f.rsplit("/", 1)[-1].lower()
        if base.startswith("preview") and base.endswith((".mp4", ".webm", ".mov")):
            return f
    return None


def origin_of(repo: str) -> str:
    return "offiziell" if repo.split("/", 1)[0] == OFFICIAL_ORG else "community"


def trick_name(repo: str, manifest_name: str | None = None) -> str:
    """Ein Name, unter dem robot.do den Trick kennt: klein, ohne 'microduck-'."""
    raw = manifest_name or repo.split("/", 1)[-1]
    raw = re.sub(r"^microduck[-_]", "", raw.lower())
    raw = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")
    return raw[:40] or "trick"


def runnable(manifest: dict[str, Any] | None) -> tuple[bool, str]:
    """Kann das als Trick (robot.do) laufen? Nur episodisch mit festem Kommando."""
    if not manifest:
        return True, "ohne Manifest – wird beim Laden auf dem Roboter geprüft"
    enc = (manifest.get("command") or {}).get("encoding")
    if enc in ("phase", "posture_flag"):
        return False, "gehört in einen festen Platz des Roboters (Picken bzw. Hinsetzen), nicht als Trick"
    if manifest.get("kind") == "perpetual" and not manifest.get("unwind_s"):
        return True, "hält, bis man es beendet – braucht eine Dauer"
    return True, ""


def _manifest(repo: str) -> dict[str, Any] | None:
    try:
        return json.loads(_get(f"{HUB}/{repo}/resolve/main/manifest.json", timeout=4.0))
    except Exception:
        return None


def search(query: str = "microduck", fetch=None) -> list[dict[str, Any]]:
    """Hub-Modelle passend zur Suche, mit dem, was sie über sich sagen."""
    q = re.sub(r"[^\w\- ]", "", query or "microduck").strip() or "microduck"
    hit = _cache.get(q)
    if hit and time.time() - hit[0] < CACHE_SECONDS and fetch is None:
        return hit[1]
    get = fetch or _get
    url = f"{HUB}/api/models?search={urllib.parse.quote_plus(q)}&limit=40&full=true"
    models = json.loads(get(url))
    out: list[dict[str, Any]] = []
    for m in models if isinstance(models, list) else []:
        repo = m.get("modelId") or m.get("id")
        if not repo:
            continue
        files = [s.get("rfilename", "") for s in m.get("siblings") or [] if isinstance(s, dict)]
        if files and not any(f.endswith(".onnx") for f in files):
            continue            # kein ONNX, keine Bewegung für die Ente
        preview = preview_in(files)
        onnx = [f for f in files if f.endswith(".onnx")]
        datei = None if len(onnx) <= 1 else ("policy.onnx" if "policy.onnx" in onnx else None)
        out.append({
            "repo": repo,
            "herkunft": origin_of(repo),
            "likes": m.get("likes"),
            "downloads": m.get("downloads"),
            "vorschau": f"{HUB}/{repo}/resolve/main/{preview}" if preview else None,
            "seite": f"{HUB}/{repo}",
            "hat_manifest": "manifest.json" in files,
            "onnx": onnx[:12],
            "datei": datei,
            "beschreibung": KNOWN.get(repo),
            "name": trick_name(repo),
            "geht": len(onnx) <= 1 or datei is not None,
            "hinweis": "" if len(onnx) <= 1 or datei else f"enthält {len(onnx)} Policy-Dateien – eher etwas zum Ausprobieren von Hand",
            "art": None,
            "dauer": None,
        })
    # Beschreibungen aus den Manifesten – begrenzt, wie auf dem Roboter
    wanted = [o for o in out if o["hat_manifest"]][:24]
    if wanted:
        load = (lambda repo: json.loads(fetch(f"{HUB}/{repo}/resolve/main/manifest.json"))) if fetch else _manifest
        deadline = time.monotonic() + DESCRIBE_BUDGET
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(load, o["repo"]): o for o in wanted}
            try:
                for fut in as_completed(futures, timeout=max(0.1, deadline - time.monotonic())):
                    o = futures[fut]
                    try:
                        man = fut.result()
                    except Exception:
                        man = None
                    if not isinstance(man, dict):
                        continue
                    o["beschreibung"] = one_line(man.get("description")) or o["beschreibung"]
                    o["name"] = trick_name(o["repo"], man.get("name"))
                    o["art"] = man.get("kind")
                    o["dauer"] = man.get("duration_s")
                    geht, hinweis = runnable(man)
                    o["geht"] = o["geht"] and geht
                    o["hinweis"] = hinweis or o["hinweis"]
                    if man.get("policies"):
                        o["hinweis"] = f"Satz mit {len(man['policies'])} Policies – für den Roboter-Update gedacht"
                        o["geht"] = False
            except Exception:
                log.info("Hub: nicht alle Beschreibungen rechtzeitig")
    out.sort(key=lambda o: (o["herkunft"] != "offiziell", -(o["likes"] or 0), -(o["downloads"] or 0)))
    if fetch is None:
        _cache[q] = (time.time(), out)
    return out
