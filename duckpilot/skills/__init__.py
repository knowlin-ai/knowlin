"""Skill-Pakete: Erweiterungen aus der Community und von Pollen, einzeln an- und abschaltbar.

Ein Paket bündelt eine Quelle (meist der Hugging Face Hub), einen Katalog daraus und
was man damit tun kann. Aktiv ist ein Paket, wenn seine Kennung in `Config.pakete`
steht (System → Erweiterungen). Aktive Pakete erscheinen auf der
Tricks-Seite mit eigenem Abschnitt und – wenn sie eins mitbringen – als Werkzeug für Claude.

Neues Paket = eine Unterklasse von `Pack` und ein Eintrag in `PACKS`. Geplante Pakete
stehen mit `stand="geplant"` in der Liste, lassen sich aber noch nicht aktivieren.

Alles, was ein Katalog vom Hub mitbringt (Namen, Beschreibungen), ist ungeprüfter
Fremdtext: Er wird angezeigt, entscheidet aber nichts und wird nie ausgeführt.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from .. import hub
from .. import settings as S

if TYPE_CHECKING:
    from ..server.app import Runtime

log = logging.getLogger(__name__)

MEMORY_SECONDS = 600          # Katalog im Speicher
DISK_SECONDS = 6 * 3600       # Katalog auf der Platte; älter wird neu geholt, bleibt aber Notnagel


@dataclass
class PackInfo:
    id: str
    name: str
    kurz: str                     # ein Satz für die Karte
    text: str                     # was es ist, was im Simulator geht
    quelle: str                   # Link
    lizenz: str
    herkunft: str                 # "offiziell" | "community" | "gemischt" | "duckpilot"
    braucht: str = ""             # "" | "roboter" | "kamera"
    stand: str = "bereit"         # "bereit" | "experimentell" | "geplant"
    im_simulator: str = ""        # was davon im Simulator geht
    hinweis: str = ""             # Sicherheit o. Ä.


class Pack:
    info: PackInfo
    tool_name: str | None = None

    def available(self) -> tuple[bool, str]:
        if self.info.stand == "geplant":
            why = {"roboter": "kommt, sobald die Ente da ist", "kamera": "kommt mit der Kamera-Anbindung"}
            return False, why.get(self.info.braucht, "geplant")
        return True, ""

    # Katalog vom Hub (synchron, läuft im Thread). fetch(url) -> bytes
    def catalog(self, fetch: Callable[[str], bytes]) -> list[dict[str, Any]]:
        return []

    async def run(self, mgr: "SkillManager", item: str, action: str) -> dict[str, Any]:
        return {"ok": False, "grund": "Dieses Paket hat nichts zum Ausführen."}

    def tool(self, items: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        return None

    async def run_tool(self, mgr: "SkillManager", args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "fehler": "unbekanntes Werkzeug"}


class PlannedPack(Pack):
    def __init__(self, info: PackInfo) -> None:
        self.info = info


def hub_json(fetch: Callable[[str], bytes], path: str) -> Any:
    return json.loads(fetch(f"{hub.HUB}{path}"))


def siblings(model: dict[str, Any]) -> list[str]:
    return [s.get("rfilename", "") for s in model.get("siblings") or [] if isinstance(s, dict)]


def _registry() -> dict[str, Pack]:
    from .alltag import AlltagPack
    from .app_moves import AppMoves
    from .community import CommunityTricks
    from .detector import DuckDetectorPack
    from .gaits import Gaits
    from .talent import Talent

    packs: list[Pack] = [
        AlltagPack(),
        AppMoves(),
        Talent(),
        Gaits(),
        CommunityTricks(),
        PlannedPack(PackInfo(
            id="quack_nav", name="Karte & Navigation (quack-nav)",
            kurz="Wohnung kartieren, sich wiederfinden, zu benannten Orten laufen, vor Treppenkanten stoppen.",
            text="Ein Community-Projekt, das auf der Ente neben robotd läuft und den Tiefensensor für Karte, "
                 "Ortung und Wegeplanung nutzt. Es bietet Werkzeuge an, die Claude direkt verwenden könnte. "
                 "Bisher nur im Simulator getestet (Vorab-Release).",
            quelle="https://github.com/andreagenovese/quacknav", lizenz="Apache-2.0", herkunft="community",
            braucht="roboter", stand="geplant")),
        DuckDetectorPack(),
    ]
    return {p.info.id: p for p in packs}


PACKS: dict[str, Pack] = _registry()


def activatable() -> set[str]:
    return {pid for pid, p in PACKS.items() if p.available()[0]}


class SkillManager:
    """Hält Kataloge, schaltet Pakete und bietet aktiven Paketen Claude-Werkzeuge an."""

    def __init__(self, runtime: "Runtime", fetch: Callable[[str], bytes] | None = None) -> None:
        self.rt = runtime
        self.fetch = fetch or hub._get
        self._mem: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    # ── Zustand ──────────────────────────────────────────────────────────
    def enabled_ids(self) -> list[str]:
        ok = activatable()
        return [p for p in (self.rt.config.pakete or []) if p in ok]

    def is_enabled(self, pid: str) -> bool:
        return pid in self.enabled_ids()

    def listing(self) -> list[dict[str, Any]]:
        on = set(self.enabled_ids())
        out = []
        for pid, p in PACKS.items():
            ok, why = p.available()
            out.append({**asdict(p.info), "an": pid in on, "verfuegbar": ok, "grund": why,
                        "werkzeug": p.tool_name})
        return out

    async def set_enabled(self, pid: str, on: bool) -> list[dict[str, Any]]:
        if pid not in PACKS:
            raise ValueError(f"Kein Skill-Paket '{pid}'")
        ok, why = PACKS[pid].available()
        if on and not ok:
            raise ValueError(f"{PACKS[pid].info.name}: {why}")
        current = [p for p in (self.rt.config.pakete or []) if p in PACKS]
        new = [*current, pid] if on and pid not in current else [p for p in current if p != pid or on]
        await self.rt.apply_settings({"pakete": new})
        return self.listing()

    # ── Kataloge ─────────────────────────────────────────────────────────
    def _disk(self, pid: str) -> Path:
        return S.settings_path().parent / "cache" / f"skills-{pid}.json"

    def cached(self, pid: str) -> list[dict[str, Any]] | None:
        hit = self._mem.get(pid)
        if hit:
            return hit[1]
        try:
            data = json.loads(self._disk(pid).read_text(encoding="utf-8"))
            items = data.get("items")
            if isinstance(items, list):
                self._mem[pid] = (float(data.get("t", 0)), items)
                return items
        except Exception:
            pass
        return None

    async def catalog(self, pid: str, refresh: bool = False) -> dict[str, Any]:
        """Katalog eines Pakets – mit dem, was das Paket lokal dazu weiß (z. B. Prüfergebnisse)."""
        res = await self._catalog(pid, refresh)
        annotate = getattr(PACKS.get(pid), "annotate", None)
        if annotate is not None and res.get("eintraege"):
            res = {**res, "eintraege": annotate(res["eintraege"])}
        return res

    async def _catalog(self, pid: str, refresh: bool = False) -> dict[str, Any]:
        if pid not in PACKS:
            raise ValueError(f"Kein Skill-Paket '{pid}'")
        pack = PACKS[pid]
        hit = self._mem.get(pid)
        if hit and not refresh and time.time() - hit[0] < MEMORY_SECONDS:
            return {"ok": True, "eintraege": hit[1], "stand": hit[0], "quelle": "speicher"}
        disk_t = 0.0
        stale = None
        try:
            data = json.loads(self._disk(pid).read_text(encoding="utf-8"))
            disk_t, stale = float(data.get("t", 0)), data.get("items")
        except Exception:
            pass
        if stale is not None and not refresh and time.time() - disk_t < DISK_SECONDS:
            self._mem[pid] = (disk_t, stale)
            return {"ok": True, "eintraege": stale, "stand": disk_t, "quelle": "platte"}
        loop = asyncio.get_running_loop()
        try:
            items = await loop.run_in_executor(None, pack.catalog, self.fetch)
        except Exception as exc:
            log.info("Katalog %s: %s", pid, exc)
            if stale is not None:
                self._mem[pid] = (disk_t, stale)
                return {"ok": True, "eintraege": stale, "stand": disk_t, "quelle": "platte",
                        "hinweis": "Hub nicht erreichbar – das ist der zuletzt geladene Stand."}
            return {"ok": False, "eintraege": [], "fehler": f"Hub nicht erreichbar: {type(exc).__name__}: {exc}"}
        now = time.time()
        self._mem[pid] = (now, items)
        try:
            path = self._disk(pid)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"t": now, "items": items}, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            log.info("Katalog %s nicht gespeichert: %s", pid, exc)
        return {"ok": True, "eintraege": items, "stand": now, "quelle": "hub"}

    async def item(self, pid: str, key: str) -> dict[str, Any] | None:
        """Einen Eintrag per Repo oder Kurzname finden (lädt den Katalog bei Bedarf)."""
        items = self.cached(pid)
        if items is None:
            items = (await self.catalog(pid)).get("eintraege") or []
        key = (key or "").strip().lower()
        for it in items:
            if key in (str(it.get("repo", "")).lower(), str(it.get("name", "")).lower(), str(it.get("titel", "")).lower()):
                return it
        return None

    # ── Ausführen ────────────────────────────────────────────────────────
    async def run(self, pid: str, item: str, action: str = "") -> dict[str, Any]:
        if pid not in PACKS:
            raise ValueError(f"Kein Skill-Paket '{pid}'")
        if not self.is_enabled(pid):
            return {"ok": False, "grund": f"Das Paket „{PACKS[pid].info.name}“ ist nicht aktiv."}
        return await PACKS[pid].run(self, item, action)

    # ── Claude ───────────────────────────────────────────────────────────
    def tools(self) -> list[dict[str, Any]]:
        out = []
        for pid in self.enabled_ids():
            t = PACKS[pid].tool(self.cached(pid))
            if t:
                out.append(t)
        return out

    def tool_names(self) -> set[str]:
        return {PACKS[p].tool_name for p in self.enabled_ids() if PACKS[p].tool_name}

    async def run_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        for pid in self.enabled_ids():
            if PACKS[pid].tool_name == name:
                return await PACKS[pid].run_tool(self, args or {})
        return {"ok": False, "fehler": f"Werkzeug {name} gehört zu keinem aktiven Paket"}
