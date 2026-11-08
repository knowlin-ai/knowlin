"""Pollens Robotermodell der Microduck – von der Originalquelle geladen, nicht mit duckpilot verteilt.

Die 3D-Teile (STL) stehen unter CC BY-NC-SA 4.0 (© Pollen Robotics), die Modellbeschreibung (MJCF) unter
Apache-2.0. duckpilot verteilt beides nicht selbst: beim ersten Start lädt es genau die gebrauchten Dateien aus
`github.com/pollen-robotics/microduck_rl` (fester Stand, jede Datei mit Prüfsumme in `quellen.json`) in den
Datenordner und baut daraus auf diesem PC

* `ansicht.dpm` – das Modell für die 3D-Ansicht (`ansicht.py`, braucht numpy),
* `physik.xml`  – das Modell für den Physik-Simulator (`physik.py`, braucht MuJoCo).

Liegt in der privaten Fassung schon eine fertige Datei im Paket, wird die genommen, solange im Datenordner keine
ist. Ohne Modell zeigt die 3D-Ansicht die einfache Ente und der Physik-Simulator bleibt aus.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
QUELLEN = json.loads((HERE / "quellen.json").read_text(encoding="utf-8"))
REPO = QUELLEN["repo"]
COMMIT = QUELLEN["commit"]
RAW = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{QUELLEN['ordner']}"
SEITE = f"https://github.com/{REPO}/tree/{COMMIT[:12]}/{QUELLEN['ordner']}"
LIZENZ_MESHES = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
LIZENZ_HINWEIS = f"https://github.com/{REPO}/blob/{COMMIT[:12]}/LICENSE-MODELS.md"
PACKAGED_VIEW = HERE.parent / "server" / "static" / "model" / "microduck.dpm"
PACKAGED_PHYSICS = HERE.parent / "physics" / "microduck.xml"
SAFE = re.compile(r"(assets/)?[A-Za-z0-9][\w.-]{0,80}\.(xml|stl)")
MAX_FILE = 8 * 1024 * 1024


def offline() -> bool:
    return os.environ.get("DUCKPILOT_OFFLINE", "") not in ("", "0")


def _get(url: str) -> bytes:
    from .. import hub

    return hub._get(url, timeout=60)


class ModellStore:
    def __init__(self, root: Path, fetch: Callable[[str], bytes] | None = None, packaged: bool = True) -> None:
        self.dir = root / "pollen-modell"
        self.src = self.dir / "quelle"
        self.fetch = fetch or _get
        self.packaged = packaged
        self.job: dict[str, Any] = {}

    # ── was liegt vor ────────────────────────────────────────────────────
    def _find(self, name: str, packaged: Path) -> Path | None:
        """Eigener Bau im Datenordner, sonst ein Ordner aus DUCKPILOT_MODELL (Tests, geteilte Installation),
        sonst die fertige Datei der privaten Fassung im Paket."""
        places = [self.dir / name]
        extra = os.environ.get("DUCKPILOT_MODELL")
        if extra and self.packaged:
            places.append(Path(extra) / name)
        if self.packaged:
            places.append(packaged)
        return next((p for p in places if p.exists()), None)

    def view_path(self) -> Path | None:
        return self._find("ansicht.dpm", PACKAGED_VIEW)

    def physics_path(self) -> Path | None:
        return self._find("physik.xml", PACKAGED_PHYSICS)

    def missing(self) -> bool:
        """Fehlt etwas, das sich laden ließe? (3D-Ansicht immer, Physik nur mit MuJoCo; nie im Offline-Modus)"""
        import importlib.util

        if self.ansicht_veraltet():
            return True                      # neu backen geht auch offline: die Quelldateien liegen schon da
        if offline():
            return False
        return self.view_path() is None or (
            importlib.util.find_spec("mujoco") is not None and self.physics_path() is None)

    def ansicht_veraltet(self) -> bool:
        """Selbst gebaute 3D-Ansicht mit älterer Aufbereitung (vor 0.38.18 volle CAD-Auflösung) und Quellen da."""
        from .ansicht import AUFBEREITUNG, aufbereitung

        eigen = self.dir / "ansicht.dpm"
        return eigen.exists() and aufbereitung(eigen) < AUFBEREITUNG and self.sources_ok()

    def sources_ok(self) -> bool:
        return all((self.src / name).exists() for name in QUELLEN["dateien"])

    def status(self) -> dict[str, Any]:
        def where(p: Path | None) -> str | None:
            if p is None:
                return None
            return "paket" if p in (PACKAGED_VIEW, PACKAGED_PHYSICS) else "geladen"

        try:
            when = (self.dir / "geladen.txt").read_text(encoding="utf-8").strip()
        except OSError:
            when = None
        return {"ansicht": where(self.view_path()), "physik": where(self.physics_path()), "geladen": when,
                "quelle": SEITE, "repo": REPO, "stand": COMMIT[:7], "lizenz": LIZENZ_HINWEIS,
                "lizenz_meshes": LIZENZ_MESHES, "job": self.job}

    # ── laden und bauen ──────────────────────────────────────────────────
    def download(self, progress: Callable[[str], None] | None = None) -> int:
        """Lädt die fehlenden Quelldateien (fester Stand, Prüfsumme je Datei). Gibt die Zahl der geladenen zurück."""
        todo = []
        for name, meta in QUELLEN["dateien"].items():
            if not SAFE.fullmatch(name):
                raise ValueError(f"unerwarteter Dateiname {name!r}")
            path = self.src / name
            if not (path.exists() and path.stat().st_size == meta["bytes"]):
                todo.append((name, meta))
        for i, (name, meta) in enumerate(todo):
            if progress:
                progress(f"lade Pollens Modell von GitHub ({i + 1} von {len(todo)}) …")
            data = self.fetch(f"{RAW}/{name}")
            if len(data) > MAX_FILE or hashlib.sha256(data).hexdigest() != meta["sha256"]:
                raise ValueError(f"{name}: Prüfsumme passt nicht – Download abgebrochen")
            path = self.src / name
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".teil")
            tmp.write_bytes(data)
            tmp.replace(path)
        return len(todo)

    def build_view(self) -> dict[str, Any]:
        from .ansicht import bake

        return bake(self.src, self.dir / "ansicht.dpm", COMMIT)

    def build_physics(self) -> dict[str, Any]:
        from .physik import bake

        return bake(self.src / "robot_groundcontact.xml", self.dir / "physik.xml")

    def ensure(self, view: bool = True, physics: bool = True, progress: Callable[[str], None] | None = None,
               force: bool = False) -> dict[str, Any]:
        """Lädt und baut, was fehlt. physics nur, wenn MuJoCo installiert ist."""
        import importlib.util

        want_view = view and (force or self.view_path() is None or self.ansicht_veraltet())
        want_phys = physics and (force or self.physics_path() is None) and importlib.util.find_spec("mujoco") is not None
        out: dict[str, Any] = {"geladen": 0}
        if not (want_view or want_phys):
            return out
        if offline() and not self.sources_ok():
            raise RuntimeError("Offline-Modus (DUCKPILOT_OFFLINE) – Pollens Modell wird nicht geladen")
        out["geladen"] = self.download(progress)
        if want_view:
            if progress:
                progress("baue das 3D-Modell …")
            out["ansicht"] = self.build_view()
        if want_phys:
            if progress:
                progress("baue das Physik-Modell …")
            out["physik"] = self.build_physics()
        (self.dir / "geladen.txt").write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
        return out


def store() -> ModellStore:
    from .. import settings as S

    return ModellStore(S.settings_path().parent)


def main() -> None:
    """`python -m duckpilot.modell [--neu]` – Pollens Modell von GitHub laden und bauen (ohne die Oberfläche)."""
    import sys

    st = store()
    res = st.ensure(force="--neu" in sys.argv[1:], progress=print)
    print("fertig:", res, "→", st.dir)
