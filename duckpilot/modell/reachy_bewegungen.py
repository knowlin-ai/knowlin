"""Pollens Bewegungsbibliotheken für Reachy Mini (seit 0.38.2): Emotionen und Tänze, mit Ton.

Pollen nimmt für Reachy Mini Bewegungen auf (Kopflage, Antennen, Körperdrehung über der Zeit; viele mit Ton) und
stellt sie als Datensätze auf Hugging Face bereit – dieselben, die Pollens eigene Apps abspielen:

- `pollen-robotics/reachy-mini-emotions-library` – Gefühle (fröhlich, neugierig, traurig, überrascht …)
- `pollen-robotics/reachy-mini-dances-library` – Tänze

duckpilot verteilt sie nicht. Es nimmt sie aus Pollens Hugging-Face-Zwischenspeicher, wenn Pollens SDK auf diesem PC
schon lief, sonst lädt es sie auf Wunsch (oder beim ersten Öffnen von Reachy Mini) von einem festen Stand des
Datensatzes in den Datenordner. Was davon wie lizenziert ist, steht auf der Seite des Datensatzes (Link im Status).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from ..backends.reachy_ausdruck import Aufnahme

DATENSAETZE = {
    "emotionen": "pollen-robotics/reachy-mini-emotions-library",
    "taenze": "pollen-robotics/reachy-mini-dances-library",
}
TOENE = (".wav", ".mp3", ".ogg", ".oga", ".opus", ".flac", ".m4a", ".aac")
SAFE = re.compile(r"(data/)?[A-Za-z0-9][\w.-]{0,100}\.(json|wav|mp3|ogg|oga|opus|flac|m4a|aac)")
MAX_FILE = 12 * 1024 * 1024
MAX_DATEIEN = 400


def offline() -> bool:
    return os.environ.get("DUCKPILOT_OFFLINE", "") not in ("", "0")


def _fetch(url: str) -> bytes:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "duckpilot (Pollens Reachy-Mini-Bewegungen)"})
    with urllib.request.urlopen(req, timeout=60) as res:
        data = res.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise ValueError(f"Datei zu groß: {url}")
    return data


def hf_zwischenspeicher(datensatz: str) -> Path | None:
    """Pollens SDK lädt die Datensätze über huggingface_hub – liegt schon ein Stand im Zwischenspeicher, nimm ihn."""
    basis = Path(os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
                 or Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub")
    snaps = basis / f"datasets--{datensatz.replace('/', '--')}" / "snapshots"
    try:
        staende = sorted((p for p in snaps.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for s in staende:
        if any(s.glob("*.json")) or any((s / "data").glob("*.json")):
            return s
    return None


class ReachyBewegungen:
    def __init__(self, root: Path, fetch: Callable[[str], bytes] | None = None,
                 cache: Callable[[str], Path | None] | None = None) -> None:
        self.dir = root / "pollen-modell" / "reachy_mini" / "bewegungen"
        self.fetch = fetch or _fetch
        self.cache = cache or hf_zwischenspeicher
        self.job: dict[str, Any] = {}
        self._aufnahmen: dict[str, Aufnahme] | None = None

    # ── was liegt vor ────────────────────────────────────────────────────
    def _stand(self, kurz: str) -> dict[str, Any] | None:
        try:
            return json.loads((self.dir / kurz / "stand.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def da(self) -> bool:
        return any(self._stand(k) for k in DATENSAETZE)

    def aufnahmen(self) -> dict[str, Aufnahme]:
        """Name → Aufnahme. Gleiche Namen in beiden Bibliotheken: der Tanz heißt dann „tanz_…“."""
        if self._aufnahmen is None:
            out: dict[str, Aufnahme] = {}
            for kurz, ds in DATENSAETZE.items():
                ordner = self.dir / kurz
                for f in sorted(ordner.glob("*.json")):
                    if f.name == "stand.json":
                        continue
                    try:
                        daten = json.loads(f.read_text(encoding="utf-8"))
                        ton = next((f.with_suffix(e).name for e in TOENE if f.with_suffix(e).exists()), None)
                        a = Aufnahme.aus_json(f.stem, daten, ds, ton)
                    except (OSError, ValueError, KeyError, TypeError, IndexError):
                        continue
                    a.art = kurz
                    out[f.stem if f.stem not in out else f"tanz_{f.stem}"] = a
            self._aufnahmen = out
        return self._aufnahmen

    def get(self, name: str) -> Aufnahme | None:
        return self.aufnahmen().get(str(name).strip())

    def ton_pfad(self, kurz: str, datei: str) -> Path | None:
        if kurz not in DATENSAETZE or not SAFE.fullmatch(datei) or "/" in datei:
            return None
        p = self.dir / kurz / datei
        return p if p.exists() else None

    def liste(self) -> list[dict[str, Any]]:
        return [{"name": n, "art": a.art, "beschreibung": a.beschreibung, "dauer": round(a.dauer, 1),
                 "ton": a.ton} for n, a in self.aufnahmen().items()]

    def status(self) -> dict[str, Any]:
        staende = {k: self._stand(k) for k in DATENSAETZE}
        return {"da": self.da(), "anzahl": len(self.aufnahmen()), "job": self.job,
                "datensaetze": {k: {"name": ds, "seite": f"https://huggingface.co/datasets/{ds}",
                                    "stand": (staende[k] or {}).get("stand"), "geladen": (staende[k] or {}).get("geladen"),
                                    "woher": (staende[k] or {}).get("woher")}
                                for k, ds in DATENSAETZE.items()}}

    # ── laden ────────────────────────────────────────────────────────────
    def _aus_ordner(self, kurz: str, quelle: Path, stand: str) -> int:
        ziel = self.dir / kurz
        ziel.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in [*quelle.glob("*"), *(quelle / "data").glob("*")]:
            if f.is_file() and SAFE.fullmatch(f.name) and f.stat().st_size <= MAX_FILE and n < MAX_DATEIEN:
                shutil.copyfile(f, ziel / f.name)
                n += 1
        (ziel / "stand.json").write_text(json.dumps({"stand": stand, "geladen": time.strftime("%Y-%m-%d %H:%M"),
                                                     "woher": "aus Pollens SDK-Zwischenspeicher"}), encoding="utf-8")
        return n

    def _von_hf(self, kurz: str, ds: str, progress: Callable[[str], None] | None) -> int:
        info = json.loads(self.fetch(f"https://huggingface.co/api/datasets/{ds}"))
        sha = str(info.get("sha") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError(f"{ds}: kein fester Stand gemeldet")
        namen = [s.get("rfilename", "") for s in info.get("siblings", [])]
        namen = [n for n in namen if SAFE.fullmatch(n)][:MAX_DATEIEN]
        if not any(n.endswith(".json") for n in namen):
            raise ValueError(f"{ds}: keine Bewegungen gefunden")
        ziel = self.dir / kurz
        ziel.mkdir(parents=True, exist_ok=True)
        for i, n in enumerate(namen):
            if progress and i % 5 == 0:
                progress(f"lade Pollens {'Emotionen' if kurz == 'emotionen' else 'Tänze'} ({i + 1} von {len(namen)}) …")
            data = self.fetch(f"https://huggingface.co/datasets/{ds}/resolve/{sha}/{n}")
            if n.endswith(".json"):
                json.loads(data)                                   # muss lesbares JSON sein
            out = ziel / Path(n).name
            tmp = out.with_name(out.name + ".teil")
            tmp.write_bytes(data)
            tmp.replace(out)
        (ziel / "stand.json").write_text(json.dumps({"stand": sha[:12], "geladen": time.strftime("%Y-%m-%d %H:%M"),
                                                     "woher": "von Hugging Face"}), encoding="utf-8")
        return len(namen)

    def ensure(self, progress: Callable[[str], None] | None = None, force: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for kurz, ds in DATENSAETZE.items():
            if self._stand(kurz) and not force:
                continue
            lokal = self.cache(ds)
            if lokal is not None:
                out[kurz] = self._aus_ordner(kurz, lokal, lokal.name[:12])
                continue
            if offline():
                raise RuntimeError("Offline-Modus (DUCKPILOT_OFFLINE) – Pollens Bewegungen werden nicht geladen")
            out[kurz] = self._von_hf(kurz, ds, progress)
        self._aufnahmen = None
        return out
