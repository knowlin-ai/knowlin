"""Pollens Policies für die Physik am PC: der offizielle Satz und Tricks/Gangarten vom Hub.

Der offizielle Satz liegt in `pollen-robotics/microduck-policies` (manifest.json + ONNX-Dateien,
Schema 2, docs/policy-manifest.md). duckpilot lädt ihn einmal in den lokalen App-Datenordner
und ordnet die Dateien den Rollen zu, die der Simulator braucht:

* walk      – Gehen, Stehen, Kopf und Körper (VelStand), auch das Aufstehen nach einem Sturz
* sitstand  – Hinsetzen und Aufstehen (Flag im Befehl)
* ground_pick – etwas aufheben (Phase im Befehl)
* kick_left, kick_right, roulade – One-Shots mit konstantem Befehl

Einzelne Policies vom Hub (`<user>/microduck-<name>`, eine policy.onnx + manifest.json) kommen
dazu: als Trick (episodic) oder als Gangart (perpetual, ersetzt walk).

Alles, was aus einem Manifest kommt, ist Fremdtext: Namen werden geprüft, Pfade nie übernommen.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

from .. import hub

log = logging.getLogger(__name__)

OFFICIAL = "pollen-robotics/microduck-policies"
ROLES = ("walk", "sitstand", "ground_pick", "kick_left", "kick_right", "roulade")
ROLE_LABEL = {"walk": "Gehen & Stehen", "sitstand": "Hinsetzen", "ground_pick": "Aufheben",
              "kick_left": "Schuss links", "kick_right": "Schuss rechts", "roulade": "Purzelbaum"}
SAFE_FILE = re.compile(r"[A-Za-z0-9][\w.-]{0,80}\.onnx")
SAFE_NAME = re.compile(r"[A-Za-z0-9][\w-]{0,40}")
MAX_ONNX = 60 * 1024 * 1024


def _download(url: str, dest: Path, fetch: Callable[[str], bytes] | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = (fetch or (lambda u: hub._get(u, timeout=60)))(url)
    if len(data) > MAX_ONNX:
        raise ValueError(f"{dest.name}: zu groß ({len(data) // 1_000_000} MB)")
    tmp = dest.with_suffix(dest.suffix + ".teil")
    tmp.write_bytes(data)
    tmp.replace(dest)


def role_of(entry: dict[str, Any]) -> str | None:
    """Welche Rolle hat ein Eintrag des offiziellen Manifests?"""
    file = str(entry.get("file") or "")
    name = str(entry.get("name") or Path(file).stem).lower()
    stem = Path(file).stem.lower()
    cmd = entry.get("command") or {}
    enc = str(cmd.get("encoding") or "constant")
    mode = str(entry.get("mode") or "walk")
    if enc == "posture_flag" or "sitstand" in stem:
        return "sitstand"
    if enc == "phase":
        return "ground_pick" if mode == "walk" and "roller" not in stem else None
    for key in ("kick_left", "kick_right", "roulade"):
        if key in name or key in stem:
            return key
    # eigene Aufsteh-Policy (robotd: optionaler Slot „stand“) – sonst richtet VelStand sie auf
    if str(entry.get("slot") or "") == "stand" or stem in ("stand", "standup", "standing") or name in ("stand", "standup"):
        return "stand"
    if stem in ("velstand", "walk") or name in ("velstand", "walk"):
        return "walk"
    if entry.get("kind") == "perpetual" and str(entry.get("slot") or "") == "walk" and mode == "walk":
        return "walk"
    return None


class PolicyStore:
    def __init__(self, root: Path, fetch: Callable[[str], bytes] | None = None) -> None:
        self.root = root / "policies"
        self.official = self.root / "pollen"
        self.hub_dir = self.root / "hub"
        self.fetch = fetch
        self.job: dict[str, Any] = {}

    # ── offizieller Satz ─────────────────────────────────────────────────
    def manifest(self) -> dict[str, Any] | None:
        try:
            return json.loads((self.official / "manifest.json").read_text(encoding="utf-8"))
        except Exception:
            return None

    def roles(self) -> dict[str, dict[str, Any]]:
        """Rolle → {pfad, eintrag} für alles, was lokal vorliegt."""
        man = self.manifest()
        out: dict[str, dict[str, Any]] = {}
        entries = (man or {}).get("policies") or []
        for e in entries if isinstance(entries, list) else []:
            if not isinstance(e, dict):
                continue
            file = str(e.get("file") or "")
            if not SAFE_FILE.fullmatch(file):
                continue
            role = role_of(e)
            path = self.official / file
            if role and role not in out and path.exists():
                out[role] = {"pfad": path, "eintrag": e}
        return out

    def ready(self) -> bool:
        return "walk" in self.roles()

    # ── selbst trainierte Policies (seit 0.37.14 gemerkt) ────────────────
    # „Ausprobieren“ eines Trainingslaufs setzte die Policy nur bis zum Neustart ein – danach lief wieder Pollens
    # Original, ohne dass es jemand merkte (Befund aus dem Test: „die neue Fassung ist bei mir nicht angekommen“).
    def eigene(self) -> list[dict[str, str]]:
        try:
            liste = json.loads((self.root / "eigene.json").read_text(encoding="utf-8"))
        except Exception:
            return []
        out = []
        for e in liste if isinstance(liste, list) else []:
            if isinstance(e, dict) and SAFE_NAME.fullmatch(str(e.get("name") or "")) and Path(str(e.get("pfad") or "")).exists():
                out.append({"name": str(e["name"]), "pfad": str(e["pfad"]), "art": str(e.get("art") or "trick"),
                            "aufgabe": str(e.get("aufgabe") or "")})
        return out

    def merke_eigen(self, pfad: str, name: str, art: str, aufgabe: str = "") -> None:
        liste = [e for e in self.eigene() if e["name"] != name]
        liste.append({"name": name, "pfad": str(pfad), "art": art, "aufgabe": aufgabe})
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / "eigene.json.teil"
        tmp.write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.root / "eigene.json")

    def download_official(self, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
        base = f"{hub.HUB}/{OFFICIAL}/resolve/main"
        if progress:
            progress("lade das Verzeichnis der Policies …")
        _download(f"{base}/manifest.json", self.official / "manifest.json", self.fetch)
        man = self.manifest() or {}
        wanted = []
        for e in man.get("policies") or []:
            file = str((e or {}).get("file") or "")
            if SAFE_FILE.fullmatch(file) and role_of(e):
                wanted.append(file)
        if not wanted:
            raise ValueError("Im Manifest steht keine passende Policy.")
        for i, file in enumerate(wanted):
            if progress:
                progress(f"lade {file} ({i + 1} von {len(wanted)}) …")
            _download(f"{base}/{file}", self.official / file, self.fetch)
        (self.official / "geladen.txt").write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
        return {"dateien": wanted, "rollen": sorted(self.roles())}

    # ── einzelne Policies vom Hub ────────────────────────────────────────
    def fetch_repo(self, repo: str, file: str | None = None) -> dict[str, Any]:
        """Lädt <repo>: manifest.json (falls da) und die ONNX-Datei. → {pfad, manifest, name}"""
        if not re.fullmatch(r"[A-Za-z0-9][\w.-]{0,95}/[\w.-]{1,96}", repo):
            raise ValueError("kein Hub-Repo (org/name)")
        if file is not None and not SAFE_FILE.fullmatch(Path(file).name):
            raise ValueError("ungültiger Dateiname")
        folder = self.hub_dir / repo.replace("/", "__")
        base = f"{hub.HUB}/{repo}/resolve/main"
        manifest: dict[str, Any] = {}
        try:
            _download(f"{base}/manifest.json", folder / "manifest.json", self.fetch)
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                manifest = {}
        except Exception:
            manifest = {}
        name = Path(file).name if file else "policy.onnx"
        if file and "/" in file:
            remote = file if re.fullmatch(r"[\w./-]{1,120}\.onnx", file) and ".." not in file else name
        else:
            remote = name
        _download(f"{base}/{remote}", folder / name, self.fetch)
        for k in ("obs_len", "action_len"):
            if k in manifest and int(manifest[k]) != {"obs_len": 61, "action_len": 14}[k]:
                raise ValueError(f"passt nicht zur Microduck ({k} = {manifest[k]})")
        if manifest.get("robot", {}).get("model") not in (None, "microduck"):
            raise ValueError("ist für einen anderen Roboter")
        # derselbe Name wie in der Hub-Liste (hub.trick_name) – sonst fehlte dort „Vorführen“ bei Namen mit
        # Großbuchstaben oder Leerzeichen
        clean = hub.trick_name(repo, manifest.get("name") if isinstance(manifest.get("name"), str) else None)
        return {"pfad": folder / name, "manifest": manifest, "name": clean}

    def status(self) -> dict[str, Any]:
        roles = self.roles()
        try:
            when = (self.official / "geladen.txt").read_text(encoding="utf-8").strip()
        except OSError:
            when = None
        return {"bereit": "walk" in roles, "rollen": {r: (r in roles) for r in ROLES},
                "namen": ROLE_LABEL, "geladen": when, "quelle": f"{hub.HUB}/{OFFICIAL}", "job": self.job}
